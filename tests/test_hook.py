from __future__ import annotations

from yt_shorts_factory.config import HookConfig
from yt_shorts_factory.script.hook import (
    assemble_narration,
    build_hook,
)


def test_build_hook_drops_aita_prefix() -> None:
    hook = build_hook(
        "AITA for telling my MIL she's not invited?",
        "It was a Tuesday and everything was fine.",
        HookConfig(style="verdict"),
    )
    assert "aita" not in hook.lower()
    assert "mother-in-law" in hook.lower() or "mil" in hook.lower() or "telling" in hook.lower()


def test_build_hook_question_style_keeps_question_mark() -> None:
    hook = build_hook(
        "Would you forgive your dad after 10 years?",
        "He left when I was 8.",
        HookConfig(style="question"),
    )
    assert hook.endswith("?")


def test_build_hook_cliffhanger_uses_body_first_sentence() -> None:
    body = "Three days later, everything fell apart. I thought I was prepared."
    hook = build_hook("Some title", body, HookConfig(style="cliffhanger", max_words=14))
    assert "Three days later" in hook


def test_build_hook_none_style_passes_through_title() -> None:
    hook = build_hook("Original Title", "body", HookConfig(style="none"))
    assert hook == "Original Title"


def test_build_hook_auto_picks_drama_for_aita() -> None:
    """``style='auto'`` should produce non-empty output without crashing."""
    hook = build_hook(
        "AITA for laughing at my brother?",
        "Body text here.",
        HookConfig(style="auto"),
    )
    assert hook
    assert "aita" not in hook.lower()


def test_assemble_narration_drops_original_title_by_default() -> None:
    text = assemble_narration(
        "AITA for breathing?",
        "I exist. That's the whole story.",
        HookConfig(),
    )
    # Hook line comes first, original title shouldn't appear since
    # drop_original_title=True by default.
    assert "AITA for breathing" not in text
    assert "I exist" in text


def test_assemble_narration_keeps_title_when_requested() -> None:
    text = assemble_narration(
        "Some Title",
        "Body.",
        HookConfig(style="none", drop_original_title=False),
    )
    assert "Some Title" in text
    assert "Body" in text
