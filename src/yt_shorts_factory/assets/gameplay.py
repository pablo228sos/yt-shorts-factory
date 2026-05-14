"""Background gameplay B-roll manager.

Two-tier cache layout inside `cache_dir`:

    cache/gameplay/
      sources/   long no-copyright source videos (downloaded once, kept around)
      segments/  random N-second slices fed to the composer

Resolution order on `pick_clip`:
1. Explicit `local_files` from config (highest priority — user knows best).
2. A random pre-extracted segment in `segments/`.
3. A new random slice from a downloaded source in `sources/`.
4. Download the next configured source URL via yt-dlp, then slice from it.

Step 4 makes the pipeline fully autonomous: a freshly-cloned repo with an
empty cache can still produce a Short, assuming yt-dlp + ffmpeg are on PATH.
"""

from __future__ import annotations

import logging
import random
import shutil
import subprocess
import sys
from pathlib import Path

from yt_shorts_factory.config import GameplayConfig

log = logging.getLogger(__name__)


def _sources_dir(cache_dir: Path) -> Path:
    return cache_dir / "sources"


def _segments_dir(cache_dir: Path) -> Path:
    return cache_dir / "segments"


def _mp4s(d: Path) -> list[Path]:
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.mp4") if p.is_file() and p.stat().st_size > 0)


def _dir_size_mb(d: Path) -> float:
    if not d.exists():
        return 0.0
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) / (1024 * 1024)


def _probe_duration(path: Path) -> float:
    """Return media duration in seconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)


def _yt_dlp_cmd() -> list[str]:
    """Resolve the yt-dlp invocation.

    Prefer running it as a Python module via the current interpreter
    (`python -m yt_dlp`), because that works whether the installed yt-dlp
    lives in a venv's `Scripts/`, on the system PATH, or anywhere in
    between. Fall back to the `yt-dlp` binary if the module isn't
    importable (e.g. user installed yt-dlp via apt/winget instead of pip).
    """
    try:
        import yt_dlp  # noqa: F401

        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        binary = shutil.which("yt-dlp")
        if binary is None:
            raise RuntimeError(
                "yt-dlp not available. Run `pip install yt-dlp` or place "
                "gameplay clips in the cache directory manually."
            ) from None
        return [binary]


def download_source(
    url: str,
    sources_dir: Path,
    *,
    cookies_from_browser: str | None = None,
    preferred_height: int = 1080,
) -> Path:
    """Pull a single long gameplay video into `sources/` via yt-dlp.

    ``preferred_height`` selects the maximum vertical resolution. 1080p is
    the sweet spot for 1080x1920 Shorts: 1.78x downscale (sharp) instead
    of 2.7x upscale (blurry) from 720p.
    """
    sources_dir.mkdir(parents=True, exist_ok=True)
    before = set(_mp4s(sources_dir))
    out_template = str(sources_dir / "%(id)s.%(ext)s")
    # Prefer ``preferred_height``, accept anything up to it, fall back gracefully.
    fmt = (
        f"bv*[height<={preferred_height}][ext=mp4]+ba[ext=m4a]/"
        f"b[height<={preferred_height}][ext=mp4]/"
        f"bv*[height<={preferred_height}]+ba/b[height<={preferred_height}]/b"
    )
    cmd = [
        *_yt_dlp_cmd(),
        "-f",
        fmt,
        "--merge-output-format",
        "mp4",
        "--no-playlist",
        # Be resilient to flaky Wi-Fi / mobile-hotspot drops: resume
        # partial downloads, keep retrying transient errors, never bail
        # on a fragment timeout. This is what previously caused users
        # to end up with no ASMR overlay when their connection blipped
        # mid-download.
        "--continue",
        "--retries",
        "20",
        "--fragment-retries",
        "20",
        "--retry-sleep",
        "fragment:exp=1:60",
        "--socket-timeout",
        "30",
        "-o",
        out_template,
    ]
    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    cmd.append(url)
    log.info("Downloading gameplay source: %s", url)
    subprocess.run(cmd, check=True)
    after = set(_mp4s(sources_dir))
    new = sorted(after - before)
    if not new:
        # Some yt-dlp builds reuse a filename if the same id was downloaded
        # before — fall back to the newest file.
        new = sorted(after, key=lambda p: p.stat().st_mtime)
    if not new:
        raise RuntimeError(f"yt-dlp produced no mp4 in {sources_dir}")
    return new[-1]


def _extract_segment(
    source: Path,
    segments_dir: Path,
    segment_seconds: float,
    rng: random.Random,
    *,
    skip_intro_seconds: float = 0.0,
    skip_outro_seconds: float = 0.0,
) -> Path:
    """Cut a random N-second slice out of `source` into `segments_dir`.

    ``skip_intro_seconds`` / ``skip_outro_seconds`` carve dead bands at
    the start and end of the source so we never sample the title card,
    spawn screen, or end-of-video splash \u2014 those segments look terrible
    as gameplay B-roll (e.g. the Subway Surfers idle ``9,802,624``
    coins spawn screen).
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not available; cannot extract gameplay segments.")
    segments_dir.mkdir(parents=True, exist_ok=True)
    total = _probe_duration(source)
    intro = max(0.0, float(skip_intro_seconds))
    outro = max(0.0, float(skip_outro_seconds))
    usable_start = intro + 2.0
    usable_end = total - outro - segment_seconds - 2.0
    if total <= segment_seconds + 1 or usable_end <= usable_start:
        # Source too short for the requested skip bands \u2014 fall back to a
        # tiny margin at each edge so we still cut something rather than
        # crashing the pipeline.
        if total <= segment_seconds + 1:
            start = 0.0
            length = max(total - 0.1, 1.0)
        else:
            start = rng.uniform(2.0, total - segment_seconds - 2.0)
            length = segment_seconds
    else:
        start = rng.uniform(usable_start, usable_end)
        length = segment_seconds
    out = segments_dir / f"{source.stem}_{int(start)}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{length:.3f}",
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def ensure_sources(cfg: GameplayConfig) -> list[Path]:
    """Download every configured source that's not already cached.

    Returns the list of sources currently on disk after the run. Safe to call
    repeatedly — it skips URLs whose id is already cached.
    """
    sources_dir = _sources_dir(cfg.cache_dir)
    sources_dir.mkdir(parents=True, exist_ok=True)
    cached = _mp4s(sources_dir)
    cached_ids = {p.stem for p in cached}
    for url in cfg.sources:
        if _dir_size_mb(sources_dir) > cfg.max_disk_mb:
            log.warning(
                "Gameplay cache > %d MB, skipping remaining sources", cfg.max_disk_mb
            )
            break
        # Cheap heuristic: skip if any cached source filename appears in the URL.
        if any(cid and cid in url for cid in cached_ids):
            log.info("Skipping already-cached source: %s", url)
            continue
        try:
            download_source(
                url,
                sources_dir,
                cookies_from_browser=cfg.cookies_from_browser,
                preferred_height=cfg.preferred_height,
            )
        except subprocess.CalledProcessError as exc:
            log.warning(
                "yt-dlp failed for %s: %s. "
                "If you see 'Sign in to confirm you're not a bot', set "
                "`gameplay.cookies_from_browser` to your browser name "
                "(firefox/chrome/edge) so yt-dlp can borrow its cookies.",
                url,
                exc,
            )
            continue
    return _mp4s(sources_dir)


def _video_height(path: Path) -> int | None:
    """Probe ``path`` and return its vertical pixel count, or None on failure."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=height",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return None
    try:
        return int(out.splitlines()[0])
    except (ValueError, IndexError):
        return None


def prune_low_res_segments(cfg: GameplayConfig) -> int:
    """Delete cached segments whose vertical resolution is below ``preferred_height``.

    Returns the number of files removed. Called once at the start of each
    pick to invalidate stale 720p slices left over from a previous run
    that used a lower ``preferred_height``.
    """
    if not cfg.prune_low_res_segments:
        return 0
    segments_dir = _segments_dir(cfg.cache_dir)
    if not segments_dir.exists():
        return 0
    removed = 0
    for seg in _mp4s(segments_dir):
        h = _video_height(seg)
        if h is not None and h < cfg.preferred_height:
            log.info(
                "Pruning stale low-res segment: %s (%dp < %dp)",
                seg.name,
                h,
                cfg.preferred_height,
            )
            try:
                seg.unlink()
                removed += 1
            except OSError:
                pass
    return removed


# Process-local memory of the last N segment paths we've returned so the
# batch CLI doesn't pick the same segment twice in a row.
_RECENT_SEGMENTS: list[Path] = []
_RECENT_SEGMENTS_LIMIT = 5


def _remember_segment(path: Path) -> None:
    _RECENT_SEGMENTS.append(path)
    while len(_RECENT_SEGMENTS) > _RECENT_SEGMENTS_LIMIT:
        _RECENT_SEGMENTS.pop(0)


def reset_recent_memory() -> None:
    """Forget recently-returned segments (used by tests)."""
    _RECENT_SEGMENTS.clear()


def _pick_non_recent(
    candidates: list[Path], *, rng: random.Random, avoid_recent: bool
) -> Path:
    if not avoid_recent or len(candidates) <= 1:
        return rng.choice(candidates)
    fresh = [c for c in candidates if c not in _RECENT_SEGMENTS]
    if fresh:
        return rng.choice(fresh)
    return rng.choice(candidates)


def pick_clip(cfg: GameplayConfig, *, rng: random.Random | None = None) -> Path:
    """Return a path to a ready-to-compose gameplay clip.

    Always returns a clip if any of `local_files`, cached segments, cached
    sources, or `sources` is non-empty and at least one source can be
    downloaded.

    Stale low-resolution segments (e.g. 720p left over from a previous
    ``preferred_height`` setting) are pruned on entry so the composer
    never picks them up after a 1080p upgrade.
    """
    rng = rng or random.Random()

    prune_low_res_segments(cfg)

    if cfg.local_files:
        existing = [p for p in cfg.local_files if p.exists()]
        if existing:
            choice = _pick_non_recent(
                existing, rng=rng, avoid_recent=cfg.avoid_recent_repeats
            )
            _remember_segment(choice)
            return choice

    segments_dir = _segments_dir(cfg.cache_dir)
    sources_dir = _sources_dir(cfg.cache_dir)

    segments = _mp4s(segments_dir)
    if segments:
        choice = _pick_non_recent(
            segments, rng=rng, avoid_recent=cfg.avoid_recent_repeats
        )
        _remember_segment(choice)
        return choice

    sources = _mp4s(sources_dir)
    if not sources and cfg.sources:
        ensure_sources(cfg)
        sources = _mp4s(sources_dir)

    if not sources:
        # Last-chance: someone may have dropped a clip directly into the
        # top-level cache_dir (legacy MVP layout).
        legacy = _mp4s(cfg.cache_dir)
        if legacy:
            choice = _pick_non_recent(
                legacy, rng=rng, avoid_recent=cfg.avoid_recent_repeats
            )
            _remember_segment(choice)
            return choice
        raise RuntimeError(
            "No gameplay B-roll available. Either set `gameplay.local_files`, "
            f"drop clips into `{cfg.cache_dir}`, list `gameplay.sources` URLs, "
            "or install yt-dlp so we can download the defaults."
        )

    source = _pick_non_recent(sources, rng=rng, avoid_recent=cfg.avoid_recent_repeats)
    segment = _extract_segment(
        source,
        segments_dir,
        cfg.segment_seconds,
        rng,
        skip_intro_seconds=getattr(cfg, "skip_intro_seconds", 0.0),
        skip_outro_seconds=getattr(cfg, "skip_outro_seconds", 0.0),
    )
    _remember_segment(segment)
    return segment
