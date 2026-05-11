"""Typer CLI entrypoint."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

from yt_shorts_factory.assets import gameplay as gameplay_module
from yt_shorts_factory.config import (
    GameplayConfig,
    PipelineConfig,
    RedditConfig,
    TtsConfig,
)
from yt_shorts_factory.pipeline import generate
from yt_shorts_factory.sources import reddit as reddit_source

app = typer.Typer(
    add_completion=False,
    help="Automated Reddit-story YouTube Shorts factory.",
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_time=False)],
    )


def _load_config(config_path: Path | None) -> PipelineConfig:
    if config_path is None:
        return PipelineConfig()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return PipelineConfig.model_validate(data)


@app.command()
def generate_cmd(
    subreddit: str = typer.Option("AmItheAsshole", "--subreddit", "-r"),
    time_filter: str = typer.Option("day", "--time-filter", "-t"),
    voice: str = typer.Option("en-US-GuyNeural", "--voice"),
    gameplay: list[Path] = typer.Option(
        [],
        "--gameplay",
        "-g",
        help="Local gameplay clip(s). May be passed multiple times.",
    ),
    output_dir: Path = typer.Option(Path("out"), "--output-dir", "-o"),
    config: Path | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate a single Short end-to-end."""
    _setup_logging(verbose)
    cfg = _load_config(config)
    cfg.reddit = RedditConfig(
        subreddit=subreddit,
        time_filter=time_filter,
        limit=cfg.reddit.limit,
        min_chars=cfg.reddit.min_chars,
        max_chars=cfg.reddit.max_chars,
        skip_nsfw=cfg.reddit.skip_nsfw,
        skip_stickied=cfg.reddit.skip_stickied,
        user_agent=cfg.reddit.user_agent,
    )
    cfg.tts = TtsConfig(voice=voice, rate=cfg.tts.rate, pitch=cfg.tts.pitch, volume=cfg.tts.volume)
    if gameplay:
        cfg.gameplay = GameplayConfig(
            cache_dir=cfg.gameplay.cache_dir,
            sources=cfg.gameplay.sources,
            local_files=list(gameplay),
        )
    cfg.output_dir = output_dir

    result = generate(cfg)
    console.rule("[green]Done")
    console.print(f"Story:    [bold]{result.story.title}[/bold]")
    console.print(f"Score:    {result.story.score}")
    console.print(f"Output:   {result.output_path}")
    console.print(f"Voice:    {result.voice_path}")
    console.print(f"Subs:     {result.subtitles_path}")
    console.print(f"B-roll:   {result.gameplay_path}")


@app.command("download-gameplay")
def download_gameplay_cmd(
    cache_dir: Path = typer.Option(Path("cache/gameplay"), "--cache-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Pre-download every default gameplay source into the cache.

    Run this once after `pip install -e .` so the first `generate-cmd` doesn't
    have to wait on yt-dlp. Subsequent runs reuse the cache.
    """
    _setup_logging(verbose)
    cfg = GameplayConfig(cache_dir=cache_dir)
    console.print(f"Downloading {len(cfg.sources)} gameplay source(s) -> {cache_dir}")
    available = gameplay_module.ensure_sources(cfg)
    console.rule("[green]Done")
    if not available:
        console.print("[red]No sources downloaded.[/red] Check yt-dlp installation.")
        raise typer.Exit(1)
    for p in available:
        size_mb = p.stat().st_size / (1024 * 1024)
        console.print(f"  {p.name}  [dim]{size_mb:.1f} MB[/dim]")


@app.command("list-stories")
def list_stories_cmd(
    subreddit: str = typer.Option("AmItheAsshole", "--subreddit", "-r"),
    time_filter: str = typer.Option("day", "--time-filter", "-t"),
    limit: int = typer.Option(10, "--limit", "-n"),
) -> None:
    """List the top candidate stories (for debugging filter settings)."""
    _setup_logging(False)
    cfg = RedditConfig(subreddit=subreddit, time_filter=time_filter, limit=limit)
    stories = reddit_source.fetch_stories(cfg)
    if not stories:
        console.print("[yellow]No stories passed filters.[/yellow]")
        raise typer.Exit(0)
    for s in stories:
        console.print(f"[bold]{s.score:>6}[/bold] {s.title}  [dim]({len(s.body)} chars)[/dim]")


if __name__ == "__main__":
    app()
