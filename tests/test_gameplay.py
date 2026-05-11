from __future__ import annotations

import random
from pathlib import Path

import pytest

from yt_shorts_factory.assets.gameplay import pick_clip
from yt_shorts_factory.config import GameplayConfig


def _make_clip(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 1024)
    return path


def test_pick_clip_prefers_local_files(tmp_path: Path) -> None:
    clip = _make_clip(tmp_path / "explicit.mp4")
    cfg = GameplayConfig(
        cache_dir=tmp_path / "cache",
        local_files=[clip],
    )
    chosen = pick_clip(cfg, rng=random.Random(0))
    assert chosen == clip


def test_pick_clip_falls_back_to_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    clip = _make_clip(cache / "cached.mp4")
    cfg = GameplayConfig(cache_dir=cache)
    chosen = pick_clip(cfg, rng=random.Random(0))
    assert chosen == clip


def test_pick_clip_raises_when_no_sources(tmp_path: Path) -> None:
    cfg = GameplayConfig(cache_dir=tmp_path / "empty")
    with pytest.raises(RuntimeError, match="No gameplay B-roll"):
        pick_clip(cfg, rng=random.Random(0))


def test_pick_clip_ignores_missing_local_files(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cached_clip = _make_clip(cache / "real.mp4")
    cfg = GameplayConfig(
        cache_dir=cache,
        local_files=[tmp_path / "does_not_exist.mp4"],
    )
    chosen = pick_clip(cfg, rng=random.Random(0))
    assert chosen == cached_clip
