from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from yt_shorts_factory.assets.sfx import (
    SfxClip,
    place_sfx,
    synthesize_default_sfx,
)
from yt_shorts_factory.config import SfxConfig
from yt_shorts_factory.transcribe.whisper import Word


def _fake_ffmpeg(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
    """Pretend ffmpeg ran; touch the output file so the synthesizer thinks it succeeded."""
    out = Path(cmd[-1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\x00" * 64)
    return subprocess.CompletedProcess(cmd, 0, "", "")


def test_synthesize_default_sfx_creates_all_files(tmp_path: Path) -> None:
    cfg = SfxConfig(sfx_dir=tmp_path / "sfx")
    with (
        patch("yt_shorts_factory.assets.sfx.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("yt_shorts_factory.assets.sfx.subprocess.run", _fake_ffmpeg),
    ):
        paths = synthesize_default_sfx(cfg)

    names = {p.name for p in paths}
    assert {"vine_boom.mp3", "ding.mp3", "whoosh.mp3", "suspense.mp3"} <= names


def test_synthesize_default_sfx_idempotent(tmp_path: Path) -> None:
    """Existing files shouldn't be regenerated unless force=True."""
    cfg = SfxConfig(sfx_dir=tmp_path / "sfx")
    cfg.sfx_dir.mkdir(parents=True, exist_ok=True)
    for name in ("vine_boom.mp3", "ding.mp3", "whoosh.mp3", "suspense.mp3"):
        (cfg.sfx_dir / name).write_bytes(b"\x00" * 64)

    call_count = {"n": 0}

    def counter(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        call_count["n"] += 1
        return _fake_ffmpeg(cmd, **_kw)

    with (
        patch("yt_shorts_factory.assets.sfx.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("yt_shorts_factory.assets.sfx.subprocess.run", counter),
    ):
        synthesize_default_sfx(cfg)

    assert call_count["n"] == 0


def test_place_sfx_returns_empty_when_disabled(tmp_path: Path) -> None:
    cfg = SfxConfig(enabled=False, sfx_dir=tmp_path / "sfx")
    clips = place_sfx([Word("Hello", 0.0, 0.5)], "Hello.", cfg)
    assert clips == []


def test_place_sfx_drops_vine_boom_on_question_mark(tmp_path: Path) -> None:
    cfg = SfxConfig(sfx_dir=tmp_path / "sfx", min_gap_seconds=0.0)
    cfg.sfx_dir.mkdir(parents=True, exist_ok=True)
    (cfg.sfx_dir / "vine_boom.mp3").write_bytes(b"x" * 64)

    words = [
        Word("Did", 0.50, 0.70),
        Word("you", 0.70, 0.85),
        Word("see?", 0.85, 1.10),
        Word("Wow", 1.30, 1.60),
    ]
    clips = place_sfx(words, "Did you see? Wow.", cfg)
    assert any(c.path.name == "vine_boom.mp3" for c in clips)


def test_place_sfx_respects_max_count(tmp_path: Path) -> None:
    cfg = SfxConfig(
        sfx_dir=tmp_path / "sfx",
        max_sfx_per_video=2,
        min_gap_seconds=0.0,
    )
    cfg.sfx_dir.mkdir(parents=True, exist_ok=True)
    (cfg.sfx_dir / "vine_boom.mp3").write_bytes(b"x" * 64)

    # Five questions in a row — only two should make it through.
    words: list[Word] = []
    for i in range(5):
        base = 1.0 + i * 3.0
        words.append(Word(f"word{i}?", base, base + 0.3))
    clips = place_sfx(words, " ".join(w.text for w in words), cfg)
    assert len(clips) <= 2


def test_sfxclip_dataclass_immutable() -> None:
    clip = SfxClip(path=Path("/x"), start_s=1.0, gain_db=-4.0)
    try:
        clip.start_s = 2.0  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("SfxClip should be frozen")
