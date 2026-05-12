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


def test_every_profile_has_a_voice_and_mood() -> None:
    for profile in NICHE_PROFILES.values():
        assert profile.voice
        assert profile.music_mood in {"drama", "horror", "comedy", "lofi"}
