"""Background music bed picker.

This is intentionally minimal. The user drops royalty-free tracks they
already own (e.g. from Pixabay Music, YouTube Audio Library, Freesound)
into ``cfg.music_dir``. Optionally they can split tracks into
sub-folders matching niche moods (``drama/``, ``horror/``, ``comedy/``,
``lofi/``).

  - If no music files are found the pipeline silently runs without a bed.
  - If a niche sub-folder is requested but empty, we fall back to the
    top-level ``music_dir``.

We don't auto-download music in this PR — Pixabay's CDN URLs change and
we don't want to ship copyrighted clips. Future PR can add a curated
download CLI.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from yt_shorts_factory.config import MusicConfig

log = logging.getLogger(__name__)


_AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac")


def _audio_files(d: Path) -> list[Path]:
    if not d.exists():
        return []
    return sorted(
        p for p in d.iterdir() if p.is_file() and p.suffix.lower() in _AUDIO_EXTS
    )


def pick_music(
    cfg: MusicConfig,
    niche_subdir: str | None = None,
    *,
    rng: random.Random | None = None,
) -> Path | None:
    """Pick a random music track from the niche sub-folder (with fallback).

    Returns ``None`` when no track is available (which is fine — the
    composer treats music as optional).
    """
    if not cfg.enabled:
        return None
    rng = rng or random.Random()
    base = Path(cfg.music_dir)
    if niche_subdir:
        sub = base / niche_subdir
        tracks = _audio_files(sub)
        if tracks:
            return rng.choice(tracks)
    tracks = _audio_files(base)
    if not tracks:
        log.info("No background music found in %s; skipping music bed.", base)
        return None
    return rng.choice(tracks)
