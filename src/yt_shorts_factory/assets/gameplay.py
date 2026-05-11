"""Background gameplay B-roll manager.

Resolution order:
1. If the user supplied explicit `local_files`, pick a random one.
2. If `cache_dir` already contains *.mp4 files, pick a random one.
3. If `sources` contains URLs, lazily download the first one with yt-dlp
   (if available) and cache it.

For unit testing and CI we never reach step 3.
"""

from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

from yt_shorts_factory.config import GameplayConfig


def _cached_files(cache_dir: Path) -> list[Path]:
    if not cache_dir.exists():
        return []
    return sorted(p for p in cache_dir.glob("*.mp4") if p.is_file() and p.stat().st_size > 0)


def _download(url: str, cache_dir: Path) -> Path:
    if shutil.which("yt-dlp") is None:
        raise RuntimeError(
            "yt-dlp not available. Install it or place gameplay clips in "
            f"{cache_dir} manually."
        )
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(cache_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f",
        "bv*[ext=mp4]+ba/b[ext=mp4]/b",
        "--merge-output-format",
        "mp4",
        "-o",
        out_template,
        url,
    ]
    subprocess.run(cmd, check=True)
    cached = _cached_files(cache_dir)
    if not cached:
        raise RuntimeError(f"yt-dlp did not produce an mp4 in {cache_dir}")
    return cached[-1]


def pick_clip(cfg: GameplayConfig, *, rng: random.Random | None = None) -> Path:
    """Return a path to a gameplay clip, downloading if necessary."""
    rng = rng or random.Random()
    if cfg.local_files:
        existing = [p for p in cfg.local_files if p.exists()]
        if existing:
            return rng.choice(existing)
    cached = _cached_files(cfg.cache_dir)
    if cached:
        return rng.choice(cached)
    if cfg.sources:
        return _download(cfg.sources[0], cfg.cache_dir)
    raise RuntimeError(
        "No gameplay B-roll available. Set `gameplay.local_files`, drop "
        f"clips into `{cfg.cache_dir}`, or list `gameplay.sources` URLs."
    )
