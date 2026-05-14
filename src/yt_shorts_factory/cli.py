"""Typer CLI entrypoint."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

from yt_shorts_factory.assets import asmr as asmr_module
from yt_shorts_factory.assets import gameplay as gameplay_module
from yt_shorts_factory.assets import sfx as sfx_module
from yt_shorts_factory.config import (
    AsmrConfig,
    DedupConfig,
    GameplayConfig,
    KokoroConfig,
    MusicConfig,
    PipelineConfig,
    RedditConfig,
    SfxConfig,
    SortType,
    TtsBackend,
    TtsConfig,
)
from yt_shorts_factory.pipeline import generate
from yt_shorts_factory.sources import dedup as dedup_module
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


def _resolve_sort(value: str) -> SortType:
    if value not in ("top", "hot", "new", "rising"):
        raise typer.BadParameter(
            f"--sort must be one of top/hot/new/rising, got {value!r}"
        )
    return value  # type: ignore[return-value]


def _build_reddit_cfg(
    base: RedditConfig,
    *,
    subreddit: str | None,
    subreddits: str | None,
    time_filter: str,
    sort: str,
    fresh: bool,
) -> RedditConfig:
    if subreddits is not None:
        sub_list = [s.strip() for s in subreddits.split(",") if s.strip()]
    else:
        sub_list = list(base.subreddits)
    return RedditConfig(
        subreddit=subreddit,
        subreddits=sub_list,
        time_filter=time_filter,
        sort=_resolve_sort(sort),
        include_fresh=fresh,
        limit=base.limit,
        min_chars=base.min_chars,
        max_chars=base.max_chars,
        skip_nsfw=base.skip_nsfw,
        skip_stickied=base.skip_stickied,
        user_agent=base.user_agent,
    )


def _apply_common_overrides(
    cfg: PipelineConfig,
    *,
    voice: str | None,
    tts_backend: str,
    speedup: float | None,
    niche: str | None,
    caps: bool,
    sfx_on: bool,
    music_dir: Path | None,
    gameplay: list[Path],
    asmr_on: bool,
    output_dir: Path,
) -> set[str]:
    """Apply the shared CLI overrides used by both ``generate-cmd`` and ``batch``."""
    if tts_backend not in ("edge", "kokoro"):
        raise typer.BadParameter(f"--tts must be 'edge' or 'kokoro', got {tts_backend!r}")
    backend: TtsBackend = "kokoro" if tts_backend == "kokoro" else "edge"

    user_overrides: set[str] = set()
    if voice is not None:
        user_overrides.add("voice")
    if speedup is not None:
        user_overrides.add("audio_speedup")

    cfg.tts = TtsConfig(
        backend=backend,
        voice=voice if voice is not None else cfg.tts.voice,
        male_voices=cfg.tts.male_voices,
        female_voices=cfg.tts.female_voices,
        rate=cfg.tts.rate,
        pitch=cfg.tts.pitch,
        volume=cfg.tts.volume,
        audio_speedup=speedup if speedup is not None else cfg.tts.audio_speedup,
        auto_gender=cfg.tts.auto_gender,
        fallback_to_edge=cfg.tts.fallback_to_edge,
        rotate_voices=cfg.tts.rotate_voices,
    )

    if niche and niche.lower() == "none":
        cfg.niche = None
    else:
        cfg.niche = niche

    cfg.subtitles.uppercase = caps

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
            prune_low_res_segments=cfg.gameplay.prune_low_res_segments,
            avoid_recent_repeats=cfg.gameplay.avoid_recent_repeats,
        )

    cfg.asmr = AsmrConfig(
        enabled=asmr_on,
        cache_dir=cfg.asmr.cache_dir,
        sources=cfg.asmr.sources,
        local_files=cfg.asmr.local_files,
        segment_seconds=cfg.asmr.segment_seconds,
        max_disk_mb=cfg.asmr.max_disk_mb,
        preferred_height=cfg.asmr.preferred_height,
        pip_width=cfg.asmr.pip_width,
        pip_height=cfg.asmr.pip_height,
        pip_x=cfg.asmr.pip_x,
        pip_y=cfg.asmr.pip_y,
        avoid_recent_repeats=cfg.asmr.avoid_recent_repeats,
        cookies_from_browser=cfg.asmr.cookies_from_browser,
    )

    cfg.output_dir = output_dir
    return user_overrides


@app.command()
def generate_cmd(
    subreddit: str | None = typer.Option(
        None, "--subreddit", "-r",
        help="Pin a single subreddit. Defaults to the rotation pool from config.",
    ),
    subreddits: str | None = typer.Option(
        None, "--subreddits",
        help="Comma-separated rotation pool (overrides config.subreddits).",
    ),
    time_filter: str = typer.Option("day", "--time-filter", "-t"),
    sort: str = typer.Option(
        "top", "--sort", help="Reddit sort mode: top | hot | new | rising."
    ),
    fresh: bool = typer.Option(
        True, "--fresh/--no-fresh",
        help="When True, also mix in 'new' posts so the pool always has fresh content.",
    ),
    voice: str | None = typer.Option(
        None, "--voice", help="Override the TTS voice. Default is auto by narrator gender + niche."
    ),
    tts_backend: str = typer.Option(
        "kokoro", "--tts",
        help="TTS backend: kokoro (default, top quality, local) or edge (free, online).",
    ),
    speedup: float | None = typer.Option(
        None, "--speedup",
        help=(
            "atempo speedup. 1.0 = no change (default; user pref). "
            "Niche overlay leaves it at 1.0."
        ),
    ),
    niche: str | None = typer.Option(
        "auto", "--niche",
        help=(
            "Niche profile: auto | drama | comedy | horror | "
            "relationship | confession | everyday | none."
        ),
    ),
    caps: bool = typer.Option(True, "--caps/--no-caps"),
    sfx_on: bool = typer.Option(True, "--sfx/--no-sfx"),
    asmr_on: bool = typer.Option(
        True, "--asmr/--no-asmr",
        help="Split-screen ASMR/cooking overlay in the bottom half.",
    ),
    music_dir: Path | None = typer.Option(None, "--music-dir"),
    gameplay: list[Path] = typer.Option([], "--gameplay", "-g"),
    output_dir: Path = typer.Option(Path("out"), "--output-dir", "-o"),
    config: Path | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate a single Short end-to-end."""
    _setup_logging(verbose)
    cfg = _load_config(config)
    cfg.reddit = _build_reddit_cfg(
        cfg.reddit,
        subreddit=subreddit,
        subreddits=subreddits,
        time_filter=time_filter,
        sort=sort,
        fresh=fresh,
    )
    user_overrides = _apply_common_overrides(
        cfg,
        voice=voice,
        tts_backend=tts_backend,
        speedup=speedup,
        niche=niche,
        caps=caps,
        sfx_on=sfx_on,
        music_dir=music_dir,
        gameplay=gameplay,
        asmr_on=asmr_on,
        output_dir=output_dir,
    )

    result = generate(cfg, user_overrides=user_overrides)
    console.rule("[green]Done")
    console.print(f"Story:    [bold]{result.story.title}[/bold]")
    console.print(f"Sub:      r/{result.story.subreddit}  Score: {result.story.score}")
    console.print(f"Niche:    {result.niche_name or '-'}")
    console.print(f"Gender:   {result.detected_gender}")
    console.print(f"Output:   {result.output_path}")
    console.print(f"Voice:    {result.voice_path}")
    console.print(f"Subs:     {result.subtitles_path}")
    console.print(f"B-roll:   {result.gameplay_path}")
    if result.asmr_path is not None:
        console.print(f"ASMR:     {result.asmr_path}")
    console.print(f"SFX cues: {len(result.sfx_clips)}")
    if result.music_path:
        console.print(f"Music:    {result.music_path.name}")


@app.command("batch")
def batch_cmd(
    count: int = typer.Option(10, "--count", "-n", help="How many videos to generate."),
    subreddits: str | None = typer.Option(
        None, "--subreddits",
        help="Comma-separated rotation pool (overrides config.subreddits).",
    ),
    time_filter: str = typer.Option("day", "--time-filter", "-t"),
    sort: str = typer.Option("top", "--sort"),
    fresh: bool = typer.Option(True, "--fresh/--no-fresh"),
    tts_backend: str = typer.Option("kokoro", "--tts"),
    speedup: float | None = typer.Option(None, "--speedup"),
    niche: str | None = typer.Option("auto", "--niche"),
    caps: bool = typer.Option(True, "--caps/--no-caps"),
    sfx_on: bool = typer.Option(True, "--sfx/--no-sfx"),
    asmr_on: bool = typer.Option(True, "--asmr/--no-asmr"),
    music_dir: Path | None = typer.Option(None, "--music-dir"),
    output_dir: Path = typer.Option(Path("out"), "--output-dir", "-o"),
    sleep_between: float = typer.Option(
        2.0, "--sleep",
        help="Seconds to wait between videos (lowers Reddit-API rate-limit risk).",
    ),
    skip_dedup: bool = typer.Option(
        False, "--skip-dedup",
        help="Render every available story even if we've already rendered it.",
    ),
    config: Path | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate N Shorts in a row, rotating across subreddits and B-roll sources.

    Each iteration picks the highest-scoring story not yet present in the
    dedup db, applies the niche profile, and renders. The gameplay /
    ASMR pickers remember the last few choices so consecutive videos use
    visually different backgrounds.
    """
    _setup_logging(verbose)
    cfg = _load_config(config)
    cfg.reddit = _build_reddit_cfg(
        cfg.reddit,
        subreddit=None,
        subreddits=subreddits,
        time_filter=time_filter,
        sort=sort,
        fresh=fresh,
    )
    cfg.dedup = DedupConfig(enabled=not skip_dedup, db_path=cfg.dedup.db_path)
    user_overrides = _apply_common_overrides(
        cfg,
        voice=None,
        tts_backend=tts_backend,
        speedup=speedup,
        niche=niche,
        caps=caps,
        sfx_on=sfx_on,
        music_dir=music_dir,
        gameplay=[],
        asmr_on=asmr_on,
        output_dir=output_dir,
    )

    sub_pool = list(cfg.reddit.subreddits)
    if not sub_pool:
        raise typer.BadParameter("No subreddits configured. Use --subreddits a,b,c.")

    rendered = 0
    fails: list[str] = []
    for i in range(count):
        # Round-robin subreddit: pin one per iteration so each video comes
        # from a different sub even when the rotation pool is small. The
        # pipeline itself can still draw from all subs via include_fresh.
        pinned_sub = sub_pool[i % len(sub_pool)]
        cfg.reddit.subreddit = pinned_sub
        cfg.reddit.subreddits = sub_pool
        console.rule(f"[cyan]Batch {i + 1}/{count}  r/{pinned_sub}")
        try:
            result = generate(cfg, user_overrides=user_overrides)
        except Exception as exc:
            console.print(f"[red]Iteration {i + 1} failed: {exc}")
            fails.append(f"#{i + 1} r/{pinned_sub}: {exc}")
            continue
        rendered += 1
        console.print(
            f"[green]  done[/green] {result.output_path.name}  "
            f"niche={result.niche_name}  gender={result.detected_gender}"
        )
        if sleep_between > 0 and i < count - 1:
            time.sleep(sleep_between)

    console.rule(
        f"[bold]Batch summary: {rendered}/{count} rendered  "
        f"({len(fails)} failed)"
    )
    if fails:
        for fail in fails:
            console.print(f"  - {fail}")
    processed_total = dedup_module.count_processed(cfg.dedup)
    console.print(f"Dedup db now contains {processed_total} processed posts.")


@app.command("download-gameplay")
def download_gameplay_cmd(
    cache_dir: Path = typer.Option(Path("cache/gameplay"), "--cache-dir"),
    kind: str = typer.Option(
        "gameplay", "--kind",
        help="What to download: 'gameplay' (top half) or 'asmr' (bottom half).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Pre-download every default gameplay (or ASMR) source into the cache.

    Run this once after `pip install -e .` so the first `generate-cmd` doesn't
    have to wait on yt-dlp. Subsequent runs reuse the cache. Use ``--kind asmr``
    to pre-fill the ASMR overlay cache.
    """
    _setup_logging(verbose)
    if kind not in ("gameplay", "asmr"):
        raise typer.BadParameter("--kind must be 'gameplay' or 'asmr'")
    if kind == "asmr":
        cache = cache_dir if cache_dir != Path("cache/gameplay") else Path("cache/asmr")
        cfg = AsmrConfig(cache_dir=cache)
        console.print(f"Downloading {len(cfg.sources)} ASMR source(s) -> {cache}")
        available = asmr_module.ensure_sources(cfg)
    else:
        cfg_gp = GameplayConfig(cache_dir=cache_dir)
        console.print(f"Downloading {len(cfg_gp.sources)} gameplay source(s) -> {cache_dir}")
        available = gameplay_module.ensure_sources(cfg_gp)
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
    console.print("Kokoro is now the default backend. Use [bold]--tts edge[/bold] to override.")


@app.command("synthesize-sfx")
def synthesize_sfx_cmd(
    sfx_dir: Path = typer.Option(Path("cache/sfx"), "--sfx-dir"),
    force: bool = typer.Option(False, "--force"),
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
    subreddit: str | None = typer.Option(
        None, "--subreddit", "-r",
        help="Single subreddit. Omit to use the rotation pool from config.",
    ),
    subreddits: str | None = typer.Option(
        None, "--subreddits",
        help="Comma-separated pool to scan.",
    ),
    time_filter: str = typer.Option("day", "--time-filter", "-t"),
    sort: str = typer.Option("top", "--sort"),
    fresh: bool = typer.Option(True, "--fresh/--no-fresh"),
    limit: int = typer.Option(15, "--limit", "-n"),
) -> None:
    """List candidate stories with score + length (for debugging filter settings)."""
    _setup_logging(False)
    base = RedditConfig(limit=limit)
    cfg = _build_reddit_cfg(
        base,
        subreddit=subreddit,
        subreddits=subreddits,
        time_filter=time_filter,
        sort=sort,
        fresh=fresh,
    )
    stories = reddit_source.fetch_stories(cfg)
    if not stories:
        console.print("[yellow]No stories passed filters.[/yellow]")
        raise typer.Exit(0)
    for s in stories[:limit]:
        console.print(
            f"[bold]{s.score:>6}[/bold] [dim]r/{s.subreddit:<20}[/dim] "
            f"{s.title}  [dim]({len(s.body)} chars)[/dim]"
        )


@app.command("dedup-status")
def dedup_status_cmd(
    db_path: Path = typer.Option(Path("cache/processed.sqlite"), "--db"),
) -> None:
    """Show how many posts the dedup db has logged."""
    cfg = DedupConfig(db_path=db_path)
    count = dedup_module.count_processed(cfg)
    console.print(f"Dedup db at [bold]{db_path}[/bold] contains {count} processed posts.")


@app.command("dedup-reset")
def dedup_reset_cmd(
    db_path: Path = typer.Option(Path("cache/processed.sqlite"), "--db"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Delete the dedup db (next batch will re-render previously processed posts)."""
    cfg = DedupConfig(db_path=db_path)
    if not yes:
        confirm = typer.confirm(f"Delete {db_path}? Past renders will be re-eligible.")
        if not confirm:
            raise typer.Exit(0)
    dedup_module.reset(cfg)
    console.print(f"[green]Reset {db_path}[/green]")


if __name__ == "__main__":
    app()
