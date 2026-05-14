"""End-to-end pipeline test with all heavy I/O mocked.

We don't actually call Edge TTS, Whisper, ffmpeg, or download anything —
instead we verify that ``pipeline.generate`` orchestrates the stages in
the right order and writes the cleaned script + subtitles to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from yt_shorts_factory.config import GameplayConfig, PipelineConfig, SfxConfig
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


def _fake_synthesize(text: str, out_path: Path, _cfg: Any, _kokoro_cfg: Any) -> Path:
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
        # Disable SFX so the test doesn't try to invoke ffmpeg.
        sfx=SfxConfig(enabled=False, sfx_dir=tmp_path / "sfx"),
    )


def test_pipeline_orchestrates_all_stages(tmp_path: Path) -> None:
    cfg = _setup_cfg(tmp_path)
    fake_words = [Word("Hello", 0.0, 0.4), Word("world.", 0.4, 0.9)]

    with (
        patch(
            "yt_shorts_factory.pipeline.tts_synthesize",
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
            "yt_shorts_factory.pipeline.tts_synthesize",
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
    # The hook strips the original "AITA for ..." prefix from the title;
    # the cleaner still expands abbreviations that appear elsewhere.
    assert "testing this" in text.lower()


def test_pipeline_applies_niche_profile_from_subreddit(tmp_path: Path) -> None:
    """Auto-resolved niche profile must hit the result.niche_name field."""
    cfg = _setup_cfg(tmp_path)
    # cfg.niche defaults to "auto" → story.subreddit "AmItheAsshole" → drama.

    with (
        patch(
            "yt_shorts_factory.pipeline.tts_synthesize",
            side_effect=_fake_synthesize,
        ),
        patch(
            "yt_shorts_factory.pipeline.whisper_module.transcribe_words",
            return_value=[Word("Hello", 0.0, 0.4)],
        ),
        patch(
            "yt_shorts_factory.pipeline.composer_module.compose",
            side_effect=_fake_compose,
        ),
    ):
        result = generate(cfg, story=_story())

    assert result.niche_name == "drama"


def test_pipeline_word_timings_rescaled_for_speedup(tmp_path: Path) -> None:
    """When speedup>1 the words written into the .ass file should be compressed."""
    cfg = _setup_cfg(tmp_path)
    # Disable niche overlay so it doesn't overwrite our explicit speedup.
    cfg.niche = None
    cfg.tts.audio_speedup = 2.0  # double speed -> halve all timings

    words = [Word("Hello", 0.0, 1.0), Word("world.", 1.0, 2.0)]
    with (
        patch(
            "yt_shorts_factory.pipeline.tts_synthesize",
            side_effect=_fake_synthesize,
        ),
        patch(
            "yt_shorts_factory.pipeline.whisper_module.transcribe_words",
            return_value=words,
        ),
        patch(
            "yt_shorts_factory.pipeline.composer_module.compose",
            side_effect=_fake_compose,
        ),
    ):
        result = generate(cfg, story=_story())

    # End of the second word in the .ass file should be at 0:00:01.00,
    # not 0:00:02.00 (because we halved everything for 2x speedup).
    subs_text = result.subtitles_path.read_text(encoding="utf-8")
    assert "0:00:02.00" not in subs_text
    assert "0:00:01.00" in subs_text
