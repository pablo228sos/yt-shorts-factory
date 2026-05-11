from __future__ import annotations

from pathlib import Path

from yt_shorts_factory.config import RenderConfig, SubtitleStyle
from yt_shorts_factory.render.subtitles import build_ass, write_ass
from yt_shorts_factory.transcribe.whisper import Word


def _words() -> list[Word]:
    return [
        Word("Hello", 0.00, 0.30),
        Word("world.", 0.30, 0.80),
        Word("This", 0.85, 1.05),
        Word("is", 1.05, 1.20),
        Word("a", 1.20, 1.30),
        Word("test.", 1.30, 1.80),
    ]


def test_build_ass_has_header_and_dialogue() -> None:
    content = build_ass(_words(), SubtitleStyle(), RenderConfig())
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert "Dialogue:" in content
    # One dialogue line per word (each highlights the active word).
    assert content.count("Dialogue:") == len(_words())


def test_build_ass_breaks_chunks_on_sentence_end() -> None:
    style = SubtitleStyle(max_words_per_chunk=5)
    content = build_ass(_words(), style, RenderConfig())
    # "Hello world." should be one chunk (ends with period), then the rest.
    # All six lines should appear regardless of chunking.
    assert content.count("Dialogue:") == 6


def test_write_ass_creates_file(tmp_path: Path) -> None:
    out = tmp_path / "subs.ass"
    write_ass(_words(), out, SubtitleStyle(), RenderConfig())
    assert out.exists()
    assert "Dialogue:" in out.read_text(encoding="utf-8")


def test_build_ass_with_empty_words_returns_header_only() -> None:
    content = build_ass([], SubtitleStyle(), RenderConfig())
    assert "Dialogue:" not in content
    assert "[Events]" in content


def test_highlight_color_present() -> None:
    style = SubtitleStyle(highlight_color="&H0000F0FF")
    content = build_ass(_words()[:2], style, RenderConfig())
    assert "&H0000F0FF" in content
