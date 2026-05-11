from __future__ import annotations

import random
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from yt_shorts_factory.assets.gameplay import (
    download_source,
    ensure_sources,
    pick_clip,
)
from yt_shorts_factory.config import GameplayConfig


def _make_clip(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 1024)
    return path


def _no_default_sources(cache: Path) -> GameplayConfig:
    """Build a GameplayConfig with an empty sources list (default has URLs)."""
    return GameplayConfig(cache_dir=cache, sources=[])


def test_pick_clip_prefers_local_files(tmp_path: Path) -> None:
    clip = _make_clip(tmp_path / "explicit.mp4")
    cfg = GameplayConfig(
        cache_dir=tmp_path / "cache",
        local_files=[clip],
        sources=[],
    )
    chosen = pick_clip(cfg, rng=random.Random(0))
    assert chosen == clip


def test_pick_clip_returns_cached_segment(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    segment = _make_clip(cache / "segments" / "seg_0.mp4")
    cfg = _no_default_sources(cache)
    chosen = pick_clip(cfg, rng=random.Random(0))
    assert chosen == segment


def test_pick_clip_extracts_from_source_when_no_segment(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    src = _make_clip(cache / "sources" / "abc123.mp4")
    cfg = _no_default_sources(cache)

    def fake_probe(path: Path) -> float:
        return 600.0  # plenty long

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        # The last positional arg is the output mp4 path; create the file.
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00" * 2048)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with (
        patch("yt_shorts_factory.assets.gameplay._probe_duration", fake_probe),
        patch("yt_shorts_factory.assets.gameplay.subprocess.run", fake_run),
        patch("yt_shorts_factory.assets.gameplay.shutil.which", return_value="/usr/bin/ffmpeg"),
    ):
        chosen = pick_clip(cfg, rng=random.Random(0))

    assert chosen.parent == cache / "segments"
    assert chosen.exists() and chosen.stat().st_size > 0
    assert src.stem in chosen.name


def test_pick_clip_raises_when_no_sources(tmp_path: Path) -> None:
    cfg = _no_default_sources(tmp_path / "empty")
    with pytest.raises(RuntimeError, match="No gameplay B-roll"):
        pick_clip(cfg, rng=random.Random(0))


def test_pick_clip_ignores_missing_local_files(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    segment = _make_clip(cache / "segments" / "fallback.mp4")
    cfg = GameplayConfig(
        cache_dir=cache,
        local_files=[tmp_path / "does_not_exist.mp4"],
        sources=[],
    )
    chosen = pick_clip(cfg, rng=random.Random(0))
    assert chosen == segment


def test_pick_clip_legacy_top_level_clip(tmp_path: Path) -> None:
    """Clips dropped directly in cache_dir/*.mp4 (pre-segments layout) still work."""
    cache = tmp_path / "cache"
    legacy = _make_clip(cache / "old_clip.mp4")
    cfg = _no_default_sources(cache)
    chosen = pick_clip(cfg, rng=random.Random(0))
    assert chosen == legacy


def test_download_source_invokes_yt_dlp(tmp_path: Path) -> None:
    sources = tmp_path / "sources"

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        assert "yt-dlp" in cmd[0]
        # Simulate yt-dlp dropping a file.
        (sources / "deadbeef.mp4").write_bytes(b"x" * 1024)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with (
        patch("yt_shorts_factory.assets.gameplay.shutil.which", return_value="/usr/bin/yt-dlp"),
        patch("yt_shorts_factory.assets.gameplay.subprocess.run", fake_run),
    ):
        out = download_source("https://example.com/v", sources)

    assert out.name == "deadbeef.mp4"
    assert out.read_bytes() == b"x" * 1024


def test_ensure_sources_skips_cached(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    sources_dir = cache / "sources"
    _make_clip(sources_dir / "knownid.mp4")
    cfg = GameplayConfig(
        cache_dir=cache,
        sources=["https://www.youtube.com/watch?v=knownid", "https://example.com/other"],
    )

    calls: list[str] = []

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd[-1])
        (sources_dir / "newid.mp4").write_bytes(b"y" * 512)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with (
        patch("yt_shorts_factory.assets.gameplay.shutil.which", return_value="/usr/bin/yt-dlp"),
        patch("yt_shorts_factory.assets.gameplay.subprocess.run", fake_run),
    ):
        ensure_sources(cfg)

    # First URL should be skipped (knownid already cached); second URL invoked.
    assert calls == ["https://example.com/other"]


def test_download_source_raises_without_yt_dlp(tmp_path: Path) -> None:
    with (
        patch("yt_shorts_factory.assets.gameplay.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="yt-dlp not available"),
    ):
        download_source("https://x", tmp_path)
