"""Bottom-half ASMR / cooking / soap-carving B-roll manager.

Mirror of ``gameplay.py`` for the split-screen overlay. We download from
the same yt-dlp pipeline but into ``cfg.cache_dir`` (separate from the
gameplay cache so the two never bleed into each other) and skip the
``preferred_height`` prune \u2014 ASMR clips are routinely lower resolution
and we don't upscale.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from yt_shorts_factory.assets import gameplay as gameplay_module
from yt_shorts_factory.config import AsmrConfig, GameplayConfig

log = logging.getLogger(__name__)


def _to_gameplay_cfg(cfg: AsmrConfig) -> GameplayConfig:
    """Adapt ``AsmrConfig`` into the format ``gameplay`` helpers expect.

    We reuse all of gameplay.py's download / segment / pruning logic and
    just point it at a different cache + source list.
    """
    return GameplayConfig(
        cache_dir=cfg.cache_dir,
        sources=cfg.sources,
        local_files=cfg.local_files,
        segment_seconds=cfg.segment_seconds,
        max_disk_mb=cfg.max_disk_mb,
        preferred_height=cfg.preferred_height,
        # ASMR uploads often top out at 720p; don't aggressively prune.
        prune_low_res_segments=False,
        avoid_recent_repeats=cfg.avoid_recent_repeats,
        cookies_from_browser=cfg.cookies_from_browser,
    )


def ensure_sources(cfg: AsmrConfig) -> list[Path]:
    """Download every configured ASMR source not already cached."""
    return gameplay_module.ensure_sources(_to_gameplay_cfg(cfg))


def pick_clip(cfg: AsmrConfig, *, rng: random.Random | None = None) -> Path | None:
    """Return a path to a ready-to-compose ASMR clip, or ``None`` if disabled.

    ``None`` is returned both when the feature is disabled in config and
    when no clips are available and yt-dlp can't fetch any \u2014 the composer
    simply falls back to single-pane gameplay in that case.
    """
    if not cfg.enabled:
        return None
    try:
        return gameplay_module.pick_clip(_to_gameplay_cfg(cfg), rng=rng)
    except RuntimeError as exc:
        log.warning("ASMR overlay unavailable: %s", exc)
        return None
