"""Typer CLI entrypoint."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

from yt_shorts_factory.assets import gameplay as gameplay_module
from yt_shorts_factory.assets import sfx as sfx_module
from yt_shorts_factory.config import (
    GameplayConfig,
    KokoroConfig,
    MusicConfig,
    PipelineConfig,
    RedditConfig,
    SfxConfig,
    TtsBackend,
    TtsConfig,
)
from yt_shorts_factory.pipeline import generate
from yt_shorts_factory.sources import reddit as reddit_source
from yt_shorts_factory.tts import kokoro as kokoro_module

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
    voice: str | None = typer.Option(
        None, "--voice", help="Override the TTS voice. Default is set by the niche profile."
    ),
    tts_backend: str = typer.Option(
        "edge", "--tts", help="TTS backend: edge (default, free, online) or kokoro (local)."
    ),
    speedup: float = typer.Option(
        1.18,
        "--speedup",
        help=(
            "atempo speedup applied to the voice. 1.0 = no change. "
            "1.18 is the typical brainrot pace."
        ),
    ),
    niche: str | None = typer.Option(
        "auto",
        "--niche",
        help=(
            "Niche profile: auto | drama | comedy | horror | "
            "relationship | everyday | none."
        ),
    ),
    caps: bool = typer.Option(
        True,
        "--caps/--no-caps",
        help="Render subtitles in ALL CAPS (TikTok-style).",
    ),
    sfx_on: bool = typer.Option(
        True,
        "--sfx/--no-sfx",
        help="Enable procedurally-generated SFX (vine boom / ding / whoosh / suspense).",
    ),
    music_dir: Path | None = typer.Option(
        None, "--music-dir", help="Folder of royalty-free background music tracks."
    ),
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

    if tts_backend not in ("edge", "kokoro"):
        raise typer.BadParameter(f"--tts must be 'edge' or 'kokoro', got {tts_backend!r}")
    backend: TtsBackend = "kokoro" if tts_backend == "kokoro" else "edge"
    cfg.tts = TtsConfig(
        backend=backend,
        voice=voice if voice is not None else cfg.tts.voice,
        rate=cfg.tts.rate,
        pitch=cfg.tts.pitch,
        volume=cfg.tts.volume,
        audio_speedup=speedup,
    )

    if niche and niche.lower() == "none":
        cfg.niche = None
    else:
        cfg.niche = niche

    # Subtitle CAPS toggle (everything else comes from the config file).
    cfg.subtitles.uppercase = caps

    # SFX toggle.
    cfg.sfx = SfxConfig(
        enabled=sfx_on,
        sfx_dir=cfg.sfx.sfx_dir,
        vine_boom_db=cfg.sfx.vine_boom_db,
        ding_db=cfg.sfx.ding_db,
        whoosh_db=cfg.sfx.whoosh_db,
        max_sfx_per_video=cfg.sfx.max_sfx_per_video,
        min_gap_seconds=cfg.sfx.min_gap_seconds,
    )

    if music_dir is not None:
        cfg.music = MusicConfig(
            enabled=cfg.music.enabled,
            music_dir=music_dir,
            base_volume_db=cfg.music.base_volume_db,
            duck_under_voice_db=cfg.music.duck_under_voice_db,
            niche_subdir_map=cfg.music.niche_subdir_map,
        )

    if gameplay:
        cfg.gameplay = GameplayConfig(
            cache_dir=cfg.gameplay.cache_dir,
            sources=cfg.gameplay.sources,
            local_files=list(gameplay),
            preferred_height=cfg.gameplay.preferred_height,
        )
    cfg.output_dir = output_dir

    result = generate(cfg)
    console.rule("[green]Done")
    console.print(f"Story:    [bold]{result.story.title}[/bold]")
    console.print(f"Score:    {result.story.score}")
    console.print(f"Niche:    {result.niche_name or '-'}")
    console.print(f"Output:   {result.output_path}")
    console.print(f"Voice:    {result.voice_path}")
    console.print(f"Subs:     {result.subtitles_path}")
    console.print(f"B-roll:   {result.gameplay_path}")
    console.print(f"SFX cues: {len(result.sfx_clips)}")
    if result.music_path:
        console.print(f"Music:    {result.music_path.name}")


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


@app.command("download-tts-models")
def download_tts_models_cmd(
    model_dir: Path = typer.Option(Path("cache/tts/kokoro"), "--model-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Download the Kokoro ONNX model + voicepack (~310 MB, one-time)."""
    _setup_logging(verbose)
    cfg = KokoroConfig(model_dir=model_dir)
    model_path, voices_path = kokoro_module.download_models(cfg)
    console.rule("[green]Done")
    console.print(f"Model:   {model_path}")
    console.print(f"Voices:  {voices_path}")
    console.print("Use [bold]--tts kokoro[/bold] on `generate-cmd` to enable.")


@app.command("synthesize-sfx")
def synthesize_sfx_cmd(
    sfx_dir: Path = typer.Option(Path("cache/sfx"), "--sfx-dir"),
    force: bool = typer.Option(False, "--force", help="Regenerate even if present."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate the default SFX library (vine boom / ding / whoosh / suspense)."""
    _setup_logging(verbose)
    cfg = SfxConfig(sfx_dir=sfx_dir)
    paths = sfx_module.synthesize_default_sfx(cfg, force=force)
    console.rule("[green]Done")
    for p in paths:
        console.print(f"  {p}")


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
