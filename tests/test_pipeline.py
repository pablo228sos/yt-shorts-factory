"""End-to-end pipeline test with all heavy I/O mocked.

We don't actually call Edge TTS, Whisper, or ffmpeg here — instead we
verify that `pipeline.generate` orchestrates the stages in the right
order and writes the cleaned script + subtitles to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from yt_shorts_factory.config import GameplayConfig, PipelineConfig
from yt_shorts_factory.pipeline import generate
from yt_shorts_factory.sources.reddit import RedditStory
from yt_shorts_factory.transcribe.whisper import Word


def _story() -> RedditStory:
    return RedditStory(
        id="xyz",
        subreddit="AmItheAsshole",
        title="AITA for testing this?",
        author="tester",
        body=("This is a story body. " * 60),
        permalink="/r/AmItheAsshole/comments/xyz/",
        score=500,
        num_comments=42,
    )


def _fake_synthesize(text: str, out_path: Path, _cfg: Any) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"\x00" * 128)
    return out_path


def _fake_compose(**kwargs: Any) -> Path:
    out = Path(kwargs["output_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\x00" * 256)
    return out


def _setup_cfg(tmp_path: Path) -> PipelineConfig:
    gameplay_clip = tmp_path / "gameplay" / "clip.mp4"
    gameplay_clip.parent.mkdir(parents=True, exist_ok=True)
    gameplay_clip.write_bytes(b"\x00" * 1024)
    return PipelineConfig(
        output_dir=tmp_path / "out",
        work_dir=tmp_path / "work",
        gameplay=GameplayConfig(
            cache_dir=tmp_path / "cache",
            local_files=[gameplay_clip],
        ),
    )


def test_pipeline_orchestrates_all_stages(tmp_path: Path) -> None:
    cfg = _setup_cfg(tmp_path)
    fake_words = [Word("Hello", 0.0, 0.4), Word("world.", 0.4, 0.9)]

    with (
        patch(
            "yt_shorts_factory.pipeline.edge_tts_module.synthesize",
            side_effect=_fake_synthesize,
        ) as m_tts,
        patch(
            "yt_shorts_factory.pipeline.whisper_module.transcribe_words",
            return_value=fake_words,
        ) as m_whisper,
        patch(
            "yt_shorts_factory.pipeline.composer_module.compose",
            side_effect=_fake_compose,
        ) as m_compose,
    ):
        result = generate(cfg, story=_story())

    assert m_tts.called
    assert m_whisper.called
    assert m_compose.called

    assert result.output_path.exists()
    assert result.voice_path.exists()
    assert result.subtitles_path.exists()
    assert result.subtitles_path.read_text(encoding="utf-8").count("Dialogue:") >= 1
    assert result.cleaned_text


def test_pipeline_writes_cleaned_script(tmp_path: Path) -> None:
    cfg = _setup_cfg(tmp_path)

    with (
        patch(
            "yt_shorts_factory.pipeline.edge_tts_module.synthesize",
            side_effect=_fake_synthesize,
        ),
        patch(
            "yt_shorts_factory.pipeline.whisper_module.transcribe_words",
            return_value=[Word("Hi", 0.0, 0.5)],
        ),
        patch(
            "yt_shorts_factory.pipeline.composer_module.compose",
            side_effect=_fake_compose,
        ),
    ):
        generate(cfg, story=_story())

    script_files = list(cfg.work_dir.rglob("script.txt"))
    assert script_files
    text = script_files[0].read_text(encoding="utf-8")
    # Abbreviation in the title should have been expanded.
    assert "Am I the asshole" in text
