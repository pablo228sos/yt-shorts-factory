"""Niche profiles — per-content-type defaults across the pipeline.

A niche profile is a small bundle of overrides that customize:

  - which Edge TTS voice fits the mood (energetic male for AITA, slow
    spooky for nosleep, upbeat female for TIFU);
  - which background-music sub-folder to draw from (``drama``/``horror``/
    ``comedy``/``lofi``);
  - which SFX flavor to emphasize (booms for AITA, suspense risers for
    nosleep, comedy pops for TIFU);
  - which hook-rewriting template to apply;
  - whether to crank audio speedup or keep it relaxed.

Profiles are looked up first by exact subreddit name (case-insensitive),
then by category (drama/comedy/horror/relationship/everyday), and finally
fall back to a generic profile. ``apply_profile`` mutates a
``PipelineConfig`` in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from yt_shorts_factory.config import HookStyle, PipelineConfig


@dataclass(frozen=True)
class NicheProfile:
    """All overrides a single niche applies to the base config."""

    name: str
    voice: str
    music_mood: str  # "drama" | "horror" | "comedy" | "lofi"
    hook_style: HookStyle
    audio_speedup: float = 1.18
    sfx_intensity: float = 1.0  # multiplier on SFX dB / count
    description: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


# Catalogue of niche profiles. Adding a new niche = add an entry here.
NICHE_PROFILES: dict[str, NicheProfile] = {
    "drama": NicheProfile(
        name="drama",
        voice="en-US-GuyNeural",
        music_mood="drama",
        hook_style="drama",
        audio_speedup=1.20,
        sfx_intensity=1.0,
        description="High-stakes interpersonal conflict (AITA, MaliciousCompliance).",
        aliases=(
            "amitheasshole",
            "aita",
            "aitah",
            "maliciouscompliance",
            "entitledparents",
            "amioverreacting",
            "prorevenge",
        ),
    ),
    "relationship": NicheProfile(
        name="relationship",
        voice="en-US-AriaNeural",
        music_mood="drama",
        hook_style="cliffhanger",
        audio_speedup=1.15,
        sfx_intensity=0.8,
        description="Relationship advice and breakups (relationship_advice, BORU).",
        aliases=(
            "relationship_advice",
            "relationships",
            "bestofredditorupdates",
            "boru",
            "datingadvice",
            "deadbedrooms",
        ),
    ),
    "comedy": NicheProfile(
        name="comedy",
        voice="en-US-JennyNeural",
        music_mood="comedy",
        hook_style="question",
        audio_speedup=1.22,
        sfx_intensity=1.1,
        description="Light, embarrassing, funny (TIFU, confession, talesfromretail).",
        aliases=(
            "tifu",
            "confession",
            "confessions",
            "talesfromretail",
            "talesfromtechsupport",
            "pettyrevenge",
        ),
    ),
    "horror": NicheProfile(
        name="horror",
        voice="en-US-ChristopherNeural",
        music_mood="horror",
        hook_style="cliffhanger",
        audio_speedup=1.05,  # slower = creepier
        sfx_intensity=0.9,
        description="Spooky/paranormal (nosleep, Glitch_in_the_Matrix, paranormal).",
        aliases=(
            "nosleep",
            "letsnotmeet",
            "glitch_in_the_matrix",
            "glitchinthematrix",
            "paranormal",
            "thetruthishere",
        ),
    ),
    "everyday": NicheProfile(
        name="everyday",
        voice="en-US-GuyNeural",
        music_mood="lofi",
        hook_style="auto",
        audio_speedup=1.18,
        sfx_intensity=0.9,
        description="Catch-all for general subs.",
        aliases=(
            "askreddit",
            "showerthoughts",
            "todayilearned",
            "explainlikeimfive",
            "unpopularopinion",
        ),
    ),
}


_ALIAS_INDEX: dict[str, NicheProfile] = {}
for profile in NICHE_PROFILES.values():
    for alias in profile.aliases:
        _ALIAS_INDEX[alias.lower()] = profile
    _ALIAS_INDEX[profile.name.lower()] = profile


def resolve_profile(name: str | None) -> NicheProfile | None:
    """Look up a profile by niche name, subreddit name, or alias.

    Returns ``None`` when no match — caller should keep base config.
    """
    if not name:
        return None
    key = name.strip().lower().removeprefix("r/").lstrip("/")
    if not key:
        return None
    return _ALIAS_INDEX.get(key)


def apply_profile(
    cfg: PipelineConfig,
    profile: NicheProfile,
    *,
    overrides: set[str] | None = None,
) -> PipelineConfig:
    """Overlay ``profile`` onto ``cfg`` in place, returning ``cfg``.

    ``overrides`` lists field names the caller has explicitly set and that
    the profile must NOT overwrite. Supported keys:

      - ``voice``         -> ``cfg.tts.voice``
      - ``audio_speedup`` -> ``cfg.tts.audio_speedup``
      - ``hook_style``    -> ``cfg.hook.style``
      - ``sfx_intensity`` -> ``cfg.sfx.{vine_boom,ding,whoosh}_db``
    """
    overrides = overrides or set()
    if "voice" not in overrides:
        cfg.tts.voice = profile.voice
    if "audio_speedup" not in overrides:
        cfg.tts.audio_speedup = profile.audio_speedup
    if "hook_style" not in overrides:
        cfg.hook.style = profile.hook_style
    if "sfx_intensity" not in overrides:
        cfg.sfx.vine_boom_db = -4.0 / max(0.1, profile.sfx_intensity)
        cfg.sfx.ding_db = -8.0 / max(0.1, profile.sfx_intensity)
        cfg.sfx.whoosh_db = -12.0 / max(0.1, profile.sfx_intensity)
    return cfg


def music_subdir_for_profile(cfg: PipelineConfig, profile: NicheProfile) -> str:
    """Pick the music-subdir for ``profile`` using the config map."""
    return cfg.music.niche_subdir_map.get(profile.music_mood, profile.music_mood)
