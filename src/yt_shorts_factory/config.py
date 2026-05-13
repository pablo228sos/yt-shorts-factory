"""Runtime configuration for the pipeline.

All knobs that an operator might want to tweak live here. Values can be
overridden per-run via CLI flags or by passing a `PipelineConfig` directly
when invoking the pipeline programmatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# Curated list of high-engagement story subreddits used as the default
# rotation pool. Mix of moral conflict, horror, betrayal, and dark
# confession content where 5-15 fresh posts/day clear the length filter.
_DEFAULT_SUBREDDITS: list[str] = [
    "AmItheAsshole",
    "AITAH",
    "AmIOverreacting",
    "EntitledParents",
    "MaliciousCompliance",
    "ProRevenge",
    "JustNoMIL",
    "raisedbynarcissists",
    "relationship_advice",
    "survivinginfidelity",
    "nosleep",
    "shortscarystories",
    "TwoSentenceHorror",
    "LetsNotMeet",
    "confession",
    "offmychest",
    "TrueOffMyChest",
    "BestofRedditorUpdates",
]

# Story-listing endpoints we treat as "fresh". For a given subreddit we
# pull a few of these and merge results, so the pool always contains
# something posted in the last 24h.
SortType = Literal["top", "hot", "new", "rising"]


class RedditConfig(BaseModel):
    """How we pull stories from Reddit.

    ``subreddits`` is the round-robin rotation pool used by ``batch`` and
    by the default ``generate-cmd`` when the operator doesn't pin one
    specific subreddit via ``subreddit``. When ``subreddit`` is set it
    takes priority — same field the original MVP used.
    """

    subreddit: str | None = None
    subreddits: list[str] = Field(default_factory=lambda: list(_DEFAULT_SUBREDDITS))
    time_filter: str = "day"  # day | week | month | year | all
    sort: SortType = "top"   # "top"/"hot"/"new"/"rising"
    # When True, we additionally pull "new" alongside ``sort`` and merge,
    # so the pool always contains posts published in the last few hours.
    include_fresh: bool = True
    limit: int = 25
    min_chars: int = 600
    max_chars: int = 3500
    skip_nsfw: bool = True
    skip_stickied: bool = True
    user_agent: str = "yt-shorts-factory/0.1 (+https://github.com/pablo228sos/yt-shorts-factory)"


TtsBackend = Literal["edge", "kokoro"]


class TtsConfig(BaseModel):
    """Voice synthesis settings.

    Two backends are supported:
      - ``kokoro`` (default): Local Kokoro-82M ONNX model. Currently the
        top-rated open-weight TTS model on TTS Arena, runs on CPU, no API
        key, no network. ~310 MB one-time model download via the
        ``download-tts-models`` CLI command. ``voice`` here is the Edge
        name; the Kokoro voice is resolved separately via ``kokoro.voice``
        (or auto-picked per-story).
      - ``edge``: Microsoft Edge TTS — free, online streaming, very
        natural neural voices. Used as the automatic fallback when Kokoro
        model files aren't on disk yet.

    ``audio_speedup`` runs after synthesis via ffmpeg ``atempo``. Defaults
    to ``1.0`` (no speed change) — the user-facing goal is *clarity +
    intonation*, not artificial speedup.
    """

    backend: TtsBackend = "kokoro"
    # Edge fallback voice. Christopher = deep adult-male narrator, the
    # closest Edge analogue to Kokoro's ``am_michael``.
    voice: str = "en-US-ChristopherNeural"
    # Edge-preferred voices the pipeline picks from when narrator gender
    # is auto-detected. Order matters: first usable voice wins.
    male_voices: list[str] = Field(
        default_factory=lambda: [
            "en-US-ChristopherNeural",
            "en-US-AndrewMultilingualNeural",
            "en-US-BrianNeural",
            "en-US-GuyNeural",
        ]
    )
    female_voices: list[str] = Field(
        default_factory=lambda: [
            "en-US-AriaNeural",
            "en-US-AvaMultilingualNeural",
            "en-US-EmmaMultilingualNeural",
            "en-US-JennyNeural",
        ]
    )
    # Rotate through male/female voice candidates between videos so back-to-back
    # uploads don't sound identical (Edge ``backend`` only — Kokoro picks one
    # voice per gender).
    rotate_voices: bool = True
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    audio_speedup: float = 1.0
    # When True the pipeline runs gender heuristics on the story text and
    # swaps in a male/female voice automatically; user --voice overrides win.
    auto_gender: bool = True
    # When Kokoro is requested but the model files aren't downloaded yet,
    # fall back to Edge instead of erroring out.
    fallback_to_edge: bool = True


class KokoroConfig(BaseModel):
    """Kokoro-ONNX backend settings (only used when ``TtsConfig.backend='kokoro'``)."""

    model_dir: Path = Path("cache/tts/kokoro")
    model_file: str = "kokoro-v1.0.onnx"
    voices_file: str = "voices-v1.0.bin"
    # Fallback voice (used when auto_gender returns ``unknown``).
    voice: str = "am_michael"
    # Top-rated Kokoro narrator voices per gender. The pipeline picks one
    # per-story based on text heuristics.
    male_voices: list[str] = Field(
        default_factory=lambda: ["am_michael", "am_adam", "am_eric"]
    )
    female_voices: list[str] = Field(
        default_factory=lambda: ["af_heart", "af_bella", "af_nicole", "af_sarah"]
    )
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
    "ytsearch1:gta v stunts no copyright 1 hour 1080p",
    "ytsearch1:trackmania gameplay no copyright 1 hour 1080p",
]

# Satisfying / ASMR sources used in the bottom half of the split-screen
# layout. Same yt-dlp pipeline as gameplay, separate cache subfolder.
_DEFAULT_ASMR_SOURCES: list[str] = [
    "ytsearch1:satisfying soap cutting asmr no copyright 1 hour",
    "ytsearch1:asmr cooking aesthetic no copyright 1 hour",
    "ytsearch1:satisfying kinetic sand cutting no copyright 1 hour",
    "ytsearch1:soap carving satisfying compilation 1 hour no copyright",
    "ytsearch1:satisfying glass cutting asmr 1 hour no copyright",
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
    # Drop cached segments that don't match ``preferred_height`` so the
    # composer never reuses an old 720p slice after a 1080p upgrade.
    prune_low_res_segments: bool = True
    # When True, the segment picker avoids re-using the most recently
    # rendered segment back-to-back so consecutive batch videos look
    # visually different. The chooser falls back to repeats only when one
    # segment is the only available option.
    avoid_recent_repeats: bool = True
    # When YouTube rate-limits anonymous access (common on cloud IPs), pass a
    # browser name here ("firefox", "chrome", "edge") and yt-dlp will reuse
    # that browser's cookies. Residential IPs usually don't need this.
    cookies_from_browser: str | None = None


class AsmrConfig(BaseModel):
    """Bottom-half satisfying/ASMR overlay.

    When ``enabled=True`` the composer renders a split-screen 9:16: the
    top half is the regular gameplay B-roll (1080x960) and the bottom
    half is a muted ASMR / cooking / soap-carving clip (1080x960). The
    audio track is muted because the narrator + music already occupy the
    audio bus; ASMR plays as a purely visual element.

    ``sources`` follows the same yt-dlp resolution as gameplay; clips are
    cached in ``cache_dir`` and reused / rotated across batches.
    """

    enabled: bool = True
    cache_dir: Path = Path("cache/asmr")
    sources: list[str] = Field(default_factory=lambda: list(_DEFAULT_ASMR_SOURCES))
    local_files: list[Path] = Field(default_factory=list)
    segment_seconds: float = 90.0
    max_disk_mb: int = 4096
    preferred_height: int = 1080
    # Bottom-half height in the split-screen layout. The gameplay fills
    # the rest (RenderConfig.height - asmr_height).
    asmr_height: int = 960
    # When True, ASMR sources rotate across consecutive batch outputs.
    avoid_recent_repeats: bool = True
    cookies_from_browser: str | None = None


class DedupConfig(BaseModel):
    """Persistent dedup of already-rendered Reddit posts.

    ``db_path`` is a SQLite file the pipeline updates after every
    successful render: ``(post_id, subreddit, title, rendered_at)``.
    Subsequent runs skip any post whose id is already present, so a
    long-running ``batch`` doesn't recycle the same stories.
    """

    enabled: bool = True
    db_path: Path = Path("cache/processed.sqlite")


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
    asmr: AsmrConfig = Field(default_factory=AsmrConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    sfx: SfxConfig = Field(default_factory=SfxConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    # If set, applies a named niche profile (drama/comedy/horror/relationship/...)
    # that tweaks defaults across voice/SFX/music/hook style. ``"auto"`` picks
    # a profile from the subreddit; ``None`` disables niche overlays entirely.
    niche: str | None = "auto"
    output_dir: Path = Path("out")
    work_dir: Path = Path("cache/work")
