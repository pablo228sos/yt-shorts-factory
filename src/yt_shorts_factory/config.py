"""Runtime configuration for the pipeline.

All knobs that an operator might want to tweak live here. Values can be
overridden per-run via CLI flags or by passing a `PipelineConfig` directly
when invoking the pipeline programmatically.
"""

from __future__ import annotations

from pathlib import Path

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


class TtsConfig(BaseModel):
    """Microsoft Edge TTS settings (no API key required)."""

    voice: str = "en-US-GuyNeural"
    rate: str = "+8%"
    pitch: str = "+0Hz"
    volume: str = "+0%"


class WhisperConfig(BaseModel):
    """Local faster-whisper transcription for word-level subtitle timing."""

    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "en"


class SubtitleStyle(BaseModel):
    """TikTok-style "one word at a time" caption styling."""

    font: str = "Arial"
    font_size: int = 90
    primary_color: str = "&H00FFFFFF"  # white
    highlight_color: str = "&H0000F0FF"  # warm yellow
    outline_color: str = "&H00000000"  # black
    outline_width: int = 6
    shadow: int = 2
    max_words_per_chunk: int = 3
    vertical_position: float = 0.55  # 0.0 = top, 1.0 = bottom


class GameplayConfig(BaseModel):
    """Background B-roll (Minecraft Parkour / Subway Surfers style)."""

    cache_dir: Path = Path("cache/gameplay")
    sources: list[str] = Field(default_factory=list)
    local_files: list[Path] = Field(default_factory=list)


class RenderConfig(BaseModel):
    """Output video parameters."""

    width: int = 1080
    height: int = 1920
    fps: int = 30
    video_bitrate: str = "4M"
    audio_bitrate: str = "192k"
    duck_music_db: float = -25.0  # how much to duck gameplay audio
    intro_padding_s: float = 0.15
    outro_padding_s: float = 0.4


class PipelineConfig(BaseModel):
    """Top-level config bundle passed through the pipeline."""

    reddit: RedditConfig = Field(default_factory=RedditConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)
    subtitles: SubtitleStyle = Field(default_factory=SubtitleStyle)
    gameplay: GameplayConfig = Field(default_factory=GameplayConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    output_dir: Path = Path("out")
    work_dir: Path = Path("cache/work")
