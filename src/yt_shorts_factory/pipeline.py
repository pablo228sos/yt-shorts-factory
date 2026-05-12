"""End-to-end pipeline orchestrator.

Stages:
  1. Pull stories from Reddit.
  2. Pick a story.
  3. Apply niche profile if any (overrides voice/SFX/music defaults).
  4. Build a retention hook + clean the body.
  5. Synthesize voiceover (Edge TTS or Kokoro, dispatched by ``tts.backend``).
  6. Transcribe voiceover (faster-whisper) -> word timings.
     Word timings are rescaled by 1/speedup so SFX and subtitles stay
     aligned after the composer applies atempo.
  7. Place SFX based on punctuation and scene markers in the text.
  8. Optionally pick a background music track from the niche-mood folder.
  9. Generate .ass subtitles.
 10. Pick a gameplay clip.
 11. Compose the final mp4 with ffmpeg (lanczos scale + sfx + music + ducking).
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path

from yt_shorts_factory.assets import gameplay as gameplay_module
from yt_shorts_factory.assets import music as music_module
from yt_shorts_factory.assets import sfx as sfx_module
from yt_shorts_factory.assets.sfx import SfxClip
from yt_shorts_factory.config import PipelineConfig
from yt_shorts_factory.niche import profiles as niche_profiles
from yt_shorts_factory.render import composer as composer_module
from yt_shorts_factory.render import subtitles as subtitles_module
from yt_shorts_factory.script import cleaner as cleaner_module
from yt_shorts_factory.script import hook as hook_module
from yt_shorts_factory.sources import reddit as reddit_source
from yt_shorts_factory.transcribe import whisper as whisper_module
from yt_shorts_factory.tts import synthesize as tts_synthesize

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationResult:
    """Everything the pipeline produced for a single run."""

    story: reddit_source.RedditStory
    cleaned_text: str
    voice_path: Path
    subtitles_path: Path
    gameplay_path: Path
    output_path: Path
    sfx_clips: tuple[SfxClip, ...] = ()
    music_path: Path | None = None
    niche_name: str | None = None


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:60] or "story"


def _rescale_words(
    words: list[whisper_module.Word], speedup: float
) -> list[whisper_module.Word]:
    """Compress whisper-detected timings to match ffmpeg's atempo speedup."""
    if speedup == 1.0 or speedup <= 0:
        return words
    inv = 1.0 / speedup
    return [
        whisper_module.Word(text=w.text, start=w.start * inv, end=w.end * inv)
        for w in words
    ]


def generate(
    cfg: PipelineConfig,
    *,
    story: reddit_source.RedditStory | None = None,
    rng: random.Random | None = None,
) -> GenerationResult:
    """Run the full pipeline. Returns paths to all produced artifacts."""
    rng = rng or random.Random()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.work_dir.mkdir(parents=True, exist_ok=True)

    if story is None:
        log.info("Fetching stories from r/%s", cfg.reddit.subreddit)
        stories = reddit_source.fetch_stories(cfg.reddit)
        chosen = reddit_source.pick_best(stories)
        if chosen is None:
            raise RuntimeError(
                f"No suitable stories found in r/{cfg.reddit.subreddit} with "
                f"current filters (min={cfg.reddit.min_chars}, "
                f"max={cfg.reddit.max_chars})."
            )
        story = chosen

    # Resolve & apply niche profile if requested.
    niche_name: str | None = None
    profile = None
    if cfg.niche == "auto":
        profile = niche_profiles.resolve_profile(story.subreddit)
    elif cfg.niche:
        profile = niche_profiles.resolve_profile(cfg.niche)
    if profile is not None:
        niche_profiles.apply_profile(cfg, profile)
        niche_name = profile.name
        log.info("Applied niche profile: %s (voice=%s, mood=%s)",
                 profile.name, profile.voice, profile.music_mood)

    slug = _slugify(story.title)
    work_subdir = cfg.work_dir / f"{story.id}_{slug}"
    work_subdir.mkdir(parents=True, exist_ok=True)

    log.info("Selected story: %s (score=%d)", story.title, story.score)

    # Build the hook + cleaned narration text.
    raw_text = hook_module.assemble_narration(story.title, story.body, cfg.hook)
    cleaned = cleaner_module.clean_story(raw_text)
    (work_subdir / "script.txt").write_text(cleaned, encoding="utf-8")

    # Synthesize voiceover.
    voice_path = work_subdir / "voice.mp3"
    log.info("Synthesizing voiceover (%s) -> %s", cfg.tts.backend, voice_path)
    tts_synthesize(cleaned, voice_path, cfg.tts, cfg.kokoro)

    # Transcribe for word-level subtitle timing.
    log.info("Transcribing voiceover for word timings")
    words = whisper_module.transcribe_words(voice_path, cfg.whisper)
    if not words:
        raise RuntimeError("Whisper returned no words; cannot build subtitles.")

    # Rescale to match the speedup applied during composition.
    scaled_words = _rescale_words(words, cfg.tts.audio_speedup)

    subs_path = work_subdir / "subs.ass"
    subtitles_module.write_ass(scaled_words, subs_path, cfg.subtitles, cfg.render)

    # Pick SFX placements & music bed.
    sfx_clips: list[SfxClip] = []
    if cfg.sfx.enabled:
        # Ensure SFX library exists; quietly fall back to empty if ffmpeg
        # synthesis isn't available (composer would still work without SFX).
        try:
            sfx_module.synthesize_default_sfx(cfg.sfx)
        except Exception as exc:
            log.warning("SFX synthesis failed: %s. Continuing without SFX.", exc)
        sfx_clips = sfx_module.place_sfx(scaled_words, cleaned, cfg.sfx)
        log.info("Placed %d SFX cues", len(sfx_clips))

    music_subdir = None
    if profile is not None:
        music_subdir = niche_profiles.music_subdir_for_profile(cfg, profile)
    music_path: Path | None = None
    if cfg.music.enabled:
        music_path = music_module.pick_music(cfg.music, music_subdir, rng=rng)
        if music_path is not None:
            log.info("Background music: %s", music_path.name)

    log.info("Picking gameplay clip")
    gameplay_path = gameplay_module.pick_clip(cfg.gameplay, rng=rng)

    output_path = cfg.output_dir / f"{story.id}_{slug}.mp4"
    log.info("Composing final video -> %s", output_path)
    composer_module.compose(
        gameplay_path=gameplay_path,
        voice_path=voice_path,
        subtitles_path=subs_path,
        output_path=output_path,
        cfg=cfg.render,
        speedup=cfg.tts.audio_speedup,
        sfx_clips=sfx_clips,
        music_path=music_path,
        music_base_db=cfg.music.base_volume_db,
        music_sidechain=True,
    )

    return GenerationResult(
        story=story,
        cleaned_text=cleaned,
        voice_path=voice_path,
        subtitles_path=subs_path,
        gameplay_path=gameplay_path,
        output_path=output_path,
        sfx_clips=tuple(sfx_clips),
        music_path=music_path,
        niche_name=niche_name,
    )
