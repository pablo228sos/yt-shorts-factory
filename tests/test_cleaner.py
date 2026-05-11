from __future__ import annotations

from yt_shorts_factory.script.cleaner import clean_story, make_hook


def test_clean_story_expands_abbreviations() -> None:
    out = clean_story("AITA for telling my SO that NTA was wrong?")
    assert "Am I the asshole" in out
    assert "significant other" in out
    assert "Not the asshole" in out


def test_clean_story_does_not_expand_lowercase_homographs() -> None:
    """`so`, `op`, `info` are real words; only ALL-CAPS should expand."""
    out = clean_story("So I told my brother, it was for his info.")
    assert "significant other" not in out
    assert "Need more info" not in out
    assert "So" in out


def test_clean_story_strips_urls_and_markdown() -> None:
    raw = "Check [this](https://example.com) out. Source: https://example.com/page"
    out = clean_story(raw)
    assert "https://" not in out
    assert "this" in out


def test_clean_story_expands_age_gender() -> None:
    out = clean_story("I (25F) told my brother (30M) he was wrong.")
    assert "25-year-old female" in out
    assert "30-year-old male" in out


def test_clean_story_drops_edit_blocks() -> None:
    raw = "Main story body that is long enough.\n\nEdit: thanks for the gold!\n\nTL;DR: yes"
    out = clean_story(raw)
    assert "Main story body" in out
    assert "gold" not in out.lower()
    assert "tl;dr" not in out.lower()


def test_clean_story_censors_profanity() -> None:
    out = clean_story("That was a shit decision.")
    assert "shit" not in out
    assert "s**t" in out


def test_clean_story_empty_string() -> None:
    assert clean_story("") == ""


def test_make_hook_for_aita() -> None:
    assert make_hook("AITA for ignoring my MIL?").lower().startswith("wait")


def test_make_hook_generic() -> None:
    assert make_hook("Some random title").lower().startswith("you won't")
