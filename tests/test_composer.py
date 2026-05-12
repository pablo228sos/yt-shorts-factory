"""Composer tests — verify the filter graph builder without invoking ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from yt_shorts_factory.assets.sfx import SfxClip
from yt_shorts_factory.config import RenderConfig
from yt_shorts_factory.render.composer import (
    _build_filter_graph,
    _clamp_atempo,
    compose,
)


def test_clamp_atempo_within_range() -> None:
    assert _clamp_atempo(1.18) == pytest.approx([1.18])
    assert _clamp_atempo(1.0) == pytest.approx([1.0])
    assert _clamp_atempo(0.7) == pytest.approx([0.7])


def test_clamp_atempo_chains_for_out_of_range() -> None:
    # 3.0x -> [2.0, 1.5]
    ratios = _clamp_atempo(3.0)
    assert len(ratios) == 2
    assert ratios[0] == pytest.approx(2.0)
    assert ratios[1] == pytest.approx(1.5)


def test_build_filter_graph_minimal() -> None:
    """No SFX, no music: just gameplay + voice + duck gameplay audio."""
    graph = _build_filter_graph(
        cfg=RenderConfig(),
        subs_arg="subs.ass",
        speedup=1.0,
        duration_s=60.0,
        voice_idx=1,
        music_idx=None,
        sfx_clips=[],
        intro_padding_s=0.15,
        music_base_db=-22.0,
        music_sidechain=True,
    )
    assert "flags=lanczos" in graph
    assert "atempo=1.0" in graph
    assert "subtitles='subs.ass'" in graph
    # amix inputs = voice + gameplay = 2
    assert "amix=inputs=2" in graph


def test_build_filter_graph_with_sfx_and_music() -> None:
    sfx = [
        SfxClip(path=Path("/fake/vine_boom.mp3"), start_s=5.0, gain_db=-4.0),
        SfxClip(path=Path("/fake/ding.mp3"), start_s=20.0, gain_db=-8.0),
    ]
    graph = _build_filter_graph(
        cfg=RenderConfig(),
        subs_arg="subs.ass",
        speedup=1.18,
        duration_s=60.0,
        voice_idx=1,
        music_idx=2,
        sfx_clips=[(3, sfx[0]), (4, sfx[1])],
        intro_padding_s=0.15,
        music_base_db=-22.0,
        music_sidechain=True,
    )
    # amix inputs = voice + music + sfx0 + sfx1 + gameplay = 5
    assert "amix=inputs=5" in graph
    assert "sidechaincompress" in graph
    # SFX delays should include the intro padding (5.0 + 0.15 = 5150 ms).
    assert "adelay=5150:all=1" in graph
    assert "adelay=20150:all=1" in graph


def test_compose_invokes_ffmpeg_with_expected_args(tmp_path: Path) -> None:
    gameplay = tmp_path / "g.mp4"
    voice = tmp_path / "v.mp3"
    subs = tmp_path / "s.ass"
    out = tmp_path / "out.mp4"
    for p in (gameplay, voice, subs):
        p.write_bytes(b"\x00" * 16)

    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = list(cmd)
        out.write_bytes(b"\x00" * 32)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with (
        patch("yt_shorts_factory.render.composer.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("yt_shorts_factory.render.composer._ffprobe_duration", return_value=60.0),
        patch("yt_shorts_factory.render.composer.subprocess.run", fake_run),
    ):
        compose(
            gameplay_path=gameplay,
            voice_path=voice,
            subtitles_path=subs,
            output_path=out,
            cfg=RenderConfig(),
            speedup=1.18,
        )

    cmd = captured["cmd"]
    assert cmd[0] == "ffmpeg"
    assert "libx264" in cmd
    assert "-crf" in cmd
    # filter graph must contain lanczos + atempo.
    fc_idx = cmd.index("-filter_complex")
    fc = cmd[fc_idx + 1]
    assert "flags=lanczos" in fc
    assert "atempo=1.18" in fc
