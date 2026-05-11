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
) -> Path:
    """Pull a single long gameplay video into `sources/` via yt-dlp."""
    sources_dir.mkdir(parents=True, exist_ok=True)
    before = set(_mp4s(sources_dir))
    out_template = str(sources_dir / "%(id)s.%(ext)s")
    cmd = [
        *_yt_dlp_cmd(),
        # 720p is plenty for a 1080-wide vertical crop and keeps downloads small.
        "-f",
        "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b",
        "--merge-output-format",
        "mp4",
        "--no-playlist",
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
) -> Path:
    """Cut a random N-second slice out of `source` into `segments_dir`."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not available; cannot extract gameplay segments.")
    segments_dir.mkdir(parents=True, exist_ok=True)
    total = _probe_duration(source)
    if total <= segment_seconds + 1:
        start = 0.0
        length = max(total - 0.1, 1.0)
    else:
        # Leave a small margin at each edge so we never hit codec-EOF weirdness.
        start = rng.uniform(2.0, total - segment_seconds - 2.0)
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


def pick_clip(cfg: GameplayConfig, *, rng: random.Random | None = None) -> Path:
    """Return a path to a ready-to-compose gameplay clip.

    Always returns a clip if any of `local_files`, cached segments, cached
    sources, or `sources` is non-empty and at least one source can be
    downloaded.
    """
    rng = rng or random.Random()

    if cfg.local_files:
        existing = [p for p in cfg.local_files if p.exists()]
        if existing:
            return rng.choice(existing)

    segments_dir = _segments_dir(cfg.cache_dir)
    sources_dir = _sources_dir(cfg.cache_dir)

    segments = _mp4s(segments_dir)
    if segments:
        return rng.choice(segments)

    sources = _mp4s(sources_dir)
    if not sources and cfg.sources:
        ensure_sources(cfg)
        sources = _mp4s(sources_dir)

    if not sources:
        # Last-chance: someone may have dropped a clip directly into the
        # top-level cache_dir (legacy MVP layout).
        legacy = _mp4s(cfg.cache_dir)
        if legacy:
            return rng.choice(legacy)
        raise RuntimeError(
            "No gameplay B-roll available. Either set `gameplay.local_files`, "
            f"drop clips into `{cfg.cache_dir}`, list `gameplay.sources` URLs, "
            "or install yt-dlp so we can download the defaults."
        )

    source = rng.choice(sources)
    return _extract_segment(source, segments_dir, cfg.segment_seconds, rng)
