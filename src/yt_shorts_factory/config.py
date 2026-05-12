"""Runtime configuration for the pipeline.

All knobs that an operator might want to tweak live here. Values can be
overridden per-run via CLI flags or by passing a `PipelineConfig` directly
when invoking the pipeline programmatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class RedditConfig(BaseModel):
    """How we pull stories from Reddit."""

    subreddit: str = "AmItheAsshole"
    time_filter: str = "day"  # day | week | month | year | all
    limit: int = 25
    min_chars: int = 600
    max_chars: int = 3500
    skip_nsfw: bool = True
    skip_stickied: bool = True
    user_agent: str = "yt-shorts-factory/0.1 (+https://github.com/)"


TtsBackend = Literal["edge", "kokoro"]


class TtsConfig(BaseModel):
    """Voice synthesis settings.

    Two backends are supported:
      - ``edge`` (default): Microsoft Edge TTS, free, online, no API key, fast.
      - ``kokoro``: Local Kokoro-82M ONNX model. Top-tier quality, runs on
        CPU. Opt-in: requires ``pip install kokoro-onnx`` and a one-time
        model download (see ``download-tts-models`` CLI command).

    ``audio_speedup`` is applied after synthesis via ``ffmpeg atempo`` so it
    works identically for both backends. 1.0 = original pace; 1.15-1.25 is
    the typical "brainrot" pace.
    """

    backend: TtsBackend = "edge"
    voice: str = "en-US-GuyNeural"
    rate: str = "+8%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    audio_speedup: float = 1.18


class KokoroConfig(BaseModel):
    """Kokoro-ONNX backend settings (only used when ``TtsConfig.backend='kokoro'``)."""

    model_dir: Path = Path("cache/tts/kokoro")
    model_file: str = "kokoro-v1.0.onnx"
    voices_file: str = "voices-v1.0.bin"
    voice: str = "am_michael"  # narration-friendly male voice
    speed: float = 1.0  # in-model speed; we additionally apply ``audio_speedup`` later
    lang: str = "en-us"
    model_url: str = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.0/kokoro-v1.0.onnx"
    )
    voices_url: str = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.0/voices-v1.0.bin"
    )


class WhisperConfig(BaseModel):
    """Local faster-whisper transcription for word-level subtitle timing."""

    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "en"


class SubtitleStyle(BaseModel):
    """TikTok-style "one word at a time" caption styling.

    Defaults emulate the dominant 2025 viral-Shorts style:
    huge bold sans-serif, centered ~55% from the top, white text +
    yellow highlight on the active word, fat black outline.
    """

    font: str = "Bebas Neue"
    # Fonts the renderer will try if ``font`` isn't installed. ffmpeg's
    # libass falls back automatically when given multiple choices.
    font_fallback: list[str] = Field(
        default_factory=lambda: ["Impact", "Anton", "Oswald", "Arial Black", "Arial"]
    )
    font_size: int = 110
    bold: bool = True
    uppercase: bool = True
    primary_color: str = "&H00FFFFFF"  # white
    highlight_color: str = "&H0000F0FF"  # warm yellow
    outline_color: str = "&H00000000"  # black
    outline_width: int = 6
    shadow: int = 3
    max_words_per_chunk: int = 3
    vertical_position: float = 0.55  # 0.0 = top, 1.0 = bottom


HookStyle = Literal["auto", "drama", "question", "verdict", "cliffhanger", "none"]


class HookConfig(BaseModel):
    """How to rewrite a Reddit post into a retention-friendly opener.

    The hook is prepended to the cleaned story and read first. Topic-aware
    templates are chosen based on the subreddit if ``style='auto'``.
    """

    style: HookStyle = "auto"
    # Hard cap on hook length in words. Long openers eat the first 3 sec.
    max_words: int = 14
    # Whether to also drop the original Reddit title from the narration
    # (the hook already conveys it, and titles read by TTS are usually
    # the worst-performing seconds of the video).
    drop_original_title: bool = True


# Long no-copyright gameplay videos commonly used as Shorts B-roll.
# yt-dlp resolves these on first run; users can override via `sources`.
# Mixing direct video IDs with `ytsearch:` queries gives a fallback when
# any specific upload disappears.
_DEFAULT_GAMEPLAY_SOURCES: list[str] = [
    "https://www.youtube.com/watch?v=intRX7BRA90",  # Minecraft Parkour [Free to Use]
    "https://www.youtube.com/watch?v=u7kdVe8q5zs",  # Subway Surfers Gameplay [No Copyright]
    "ytsearch1:minecraft parkour gameplay no copyright 1 hour 1080p",
    "ytsearch1:subway surfers gameplay no copyright 1 hour 1080p",
]


class GameplayConfig(BaseModel):
    """Background B-roll (Minecraft Parkour / Subway Surfers style).

    The pipeline pulls long no-copyright gameplay videos from `sources` via
    yt-dlp and slices random N-second segments per Short. Operators can
    override `sources` with their own URLs/queries or point `local_files`
    at clips they already have.

    ``preferred_height`` controls the yt-dlp format selector: we now ask
    for 1080p by default so the 9:16 center-crop doesn't have to upscale.
    """

    cache_dir: Path = Path("cache/gameplay")
    sources: list[str] = Field(default_factory=lambda: list(_DEFAULT_GAMEPLAY_SOURCES))
    local_files: list[Path] = Field(default_factory=list)
    segment_seconds: float = 90.0
    min_source_seconds: float = 180.0
    max_disk_mb: int = 8192  # cap on total cached source MB (bumped for 1080p)
    preferred_height: int = 1080
    # When YouTube rate-limits anonymous access (common on cloud IPs), pass a
    # browser name here ("firefox", "chrome", "edge") and yt-dlp will reuse
    # that browser's cookies. Residential IPs usually don't need this.
    cookies_from_browser: str | None = None


class SfxConfig(BaseModel):
    """Sound-effect injection (vine boom / ding / whoosh / suspense).

    SFX are short, procedurally generated by ffmpeg at install time and
    cached in ``sfx_dir``. The pipeline places them based on the story
    text: question marks → vine boom, scene-change markers ("update:",
    "edit:") → ding, every ~10s of narration → optional whoosh.

    Set ``enabled=False`` to suppress all SFX.
    """

    enabled: bool = True
    sfx_dir: Path = Path("cache/sfx")
    vine_boom_db: float = -4.0
    ding_db: float = -8.0
    whoosh_db: float = -12.0
    # Max SFX placed per Short to avoid sonic mush.
    max_sfx_per_video: int = 8
    # Seconds of silence required around an SFX to play it (don't talk over).
    min_gap_seconds: float = 0.25


class MusicConfig(BaseModel):
    """Background music bed.

    Music is opt-in: the user drops royalty-free tracks (lofi for AITA,
    drama pads for nosleep, comedy ukelele for TIFU, etc.) into
    ``music_dir`` organized by niche. The pipeline picks a random track,
    loops/trims it to fit, mixes it under the voice with a dB drop, and
    relies on the voice ducking compressor for cleanliness.

    If ``music_dir`` is empty or missing, no music is added.
    """

    enabled: bool = True
    music_dir: Path = Path("cache/music")
    base_volume_db: float = -22.0
    duck_under_voice_db: float = -10.0
    # Sub-directories of ``music_dir`` that the pipeline searches per niche.
    # Falls back to the top-level dir if no niche match.
    niche_subdir_map: dict[str, str] = Field(
        default_factory=lambda: {
            "drama": "drama",
            "horror": "horror",
            "comedy": "comedy",
            "lofi": "lofi",
        }
    )


class RenderConfig(BaseModel):
    """Output video parameters."""

    width: int = 1080
    height: int = 1920
    fps: int = 30
    video_bitrate: str = "5M"
    audio_bitrate: str = "192k"
    # ffmpeg ``scale=...:flags=`` argument. lanczos = sharp, slowest.
    scale_flags: str = "lanczos"
    duck_music_db: float = -25.0  # how much to duck the gameplay's own audio
    intro_padding_s: float = 0.15
    outro_padding_s: float = 0.4
    # Aggressive bitrate/quality knob: lower = better quality, default 22.
    crf: int = 22
    preset: str = "veryfast"


class PipelineConfig(BaseModel):
    """Top-level config bundle passed through the pipeline."""

    reddit: RedditConfig = Field(default_factory=RedditConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    kokoro: KokoroConfig = Field(default_factory=KokoroConfig)
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)
    subtitles: SubtitleStyle = Field(default_factory=SubtitleStyle)
    hook: HookConfig = Field(default_factory=HookConfig)
    gameplay: GameplayConfig = Field(default_factory=GameplayConfig)
    sfx: SfxConfig = Field(default_factory=SfxConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    # If set, applies a named niche profile (drama/comedy/horror/relationship/...)
    # that tweaks defaults across voice/SFX/music/hook style. ``"auto"`` picks
    # a profile from the subreddit; ``None`` disables niche overlays entirely.
    niche: str | None = "auto"
    output_dir: Path = Path("out")
    work_dir: Path = Path("cache/work")
