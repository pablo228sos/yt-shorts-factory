from __future__ import annotations

from yt_shorts_factory.config import PipelineConfig
from yt_shorts_factory.niche.profiles import (
    NICHE_PROFILES,
    apply_profile,
    resolve_profile,
)


def test_resolve_profile_by_subreddit_alias() -> None:
    p = resolve_profile("AmItheAsshole")
    assert p is not None
    assert p.name == "drama"


def test_resolve_profile_case_insensitive() -> None:
    p = resolve_profile("NOSLEEP")
    assert p is not None
    assert p.name == "horror"


def test_resolve_profile_strips_r_prefix() -> None:
    p = resolve_profile("r/tifu")
    assert p is not None
    assert p.name == "comedy"


def test_resolve_profile_does_not_strip_leading_r_from_subreddit() -> None:
    """``lstrip('r/')`` used to strip any leading 'r' or '/' character —
    breaking ``relationship_advice`` -> ``elationship_advice``. Must only
    strip the literal ``r/`` prefix."""
    p = resolve_profile("relationship_advice")
    assert p is not None
    assert p.name == "relationship"

    p2 = resolve_profile("relationships")
    assert p2 is not None
    assert p2.name == "relationship"


def test_resolve_profile_returns_none_for_unknown() -> None:
    assert resolve_profile("not-a-real-sub") is None
    assert resolve_profile(None) is None
    assert resolve_profile("") is None


def test_apply_profile_mutates_config() -> None:
    cfg = PipelineConfig()
    profile = NICHE_PROFILES["horror"]
    apply_profile(cfg, profile)
    assert cfg.tts.voice == profile.voice
    assert cfg.tts.audio_speedup == profile.audio_speedup
    assert cfg.hook.style == profile.hook_style


def test_apply_profile_returns_same_cfg() -> None:
    cfg = PipelineConfig()
    out = apply_profile(cfg, NICHE_PROFILES["comedy"])
    assert out is cfg


def test_apply_profile_respects_voice_override() -> None:
    cfg = PipelineConfig()
    cfg.tts.voice = "en-US-AriaNeural"
    apply_profile(cfg, NICHE_PROFILES["drama"], overrides={"voice"})
    # Drama profile's default voice would be en-US-GuyNeural; the override
    # must keep our explicit choice.
    assert cfg.tts.voice == "en-US-AriaNeural"
    # But other fields (speedup, hook style) should still come from profile.
    assert cfg.tts.audio_speedup == NICHE_PROFILES["drama"].audio_speedup
    assert cfg.hook.style == NICHE_PROFILES["drama"].hook_style


def test_apply_profile_respects_speedup_override() -> None:
    cfg = PipelineConfig()
    cfg.tts.audio_speedup = 1.0
    apply_profile(cfg, NICHE_PROFILES["comedy"], overrides={"audio_speedup"})
    assert cfg.tts.audio_speedup == 1.0
    # And voice should still be the comedy profile's voice.
    assert cfg.tts.voice == NICHE_PROFILES["comedy"].voice


def test_apply_profile_respects_multiple_overrides() -> None:
    cfg = PipelineConfig()
    cfg.tts.voice = "en-GB-RyanNeural"
    cfg.tts.audio_speedup = 1.5
    apply_profile(
        cfg,
        NICHE_PROFILES["horror"],
        overrides={"voice", "audio_speedup"},
    )
    assert cfg.tts.voice == "en-GB-RyanNeural"
    assert cfg.tts.audio_speedup == 1.5


def test_pettyrevenge_resolves_to_comedy_not_typo() -> None:
    """Regression: ``petyrevenge`` (typo) used to live in drama's aliases,
    so the correct ``pettyrevenge`` resolved to comedy via fallback. Now
    only ``pettyrevenge`` exists, and it must resolve cleanly."""
    p = resolve_profile("pettyrevenge")
    assert p is not None
    assert p.name == "comedy"
    # And the typo should not silently match anything.
    assert resolve_profile("petyrevenge") is None


def test_every_profile_has_a_voice_and_mood() -> None:
    for profile in NICHE_PROFILES.values():
        assert profile.voice
        assert profile.music_mood in {"drama", "horror", "comedy", "lofi"}
