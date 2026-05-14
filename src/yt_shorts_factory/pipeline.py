"""End-to-end pipeline orchestrator.

Stages:
  1. Pull stories from Reddit (multi-subreddit + fresh-sort aware).
  2. Filter out previously rendered posts via the dedup SQLite db.
  3. Pick a story.
  4. Apply niche profile if any (overrides voice/SFX/music defaults).
  5. Build a retention hook + clean the body.
  6. Auto-detect narrator gender, swap to a gender-matched TTS voice.
  7. Synthesize voiceover (Kokoro by default; auto-falls-back to Edge).
  8. Transcribe voiceover (faster-whisper) -> word timings.
     Word timings are rescaled by 1/speedup so SFX and subtitles stay
     aligned after the composer applies atempo (only matters when
     ``audio_speedup != 1.0``).
  9. Place SFX based on punctuation and scene markers in the text.
 10. Optionally pick a background music track from the niche-mood folder.
 11. Generate .ass subtitles (absolute \\pos for deterministic centering).
 12. Pick a gameplay clip (prunes stale low-res segments, avoids back-to-back
     repeats).
 13. Optionally pick an ASMR / cooking / soap-carving overlay for the
     bottom half of the split-screen.
 14. Compose the final mp4 with ffmpeg (lanczos scale + sfx + music + ducking).
 15. Mark the post as rendered in the dedup db so we don't recycle it.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from yt_shorts_factory.assets import asmr as asmr_module
from yt_shorts_factory.assets import gameplay as gameplay_module
from yt_shorts_factory.assets import music as music_module
from yt_shorts_factory.assets import sfx as sfx_module
from yt_shorts_factory.assets.sfx import SfxClip
from yt_shorts_factory.config import PipelineConfig, TtsConfig
from yt_shorts_factory.niche import profiles as niche_profiles
from yt_shorts_factory.render import composer as composer_module
from yt_shorts_factory.render import subtitles as subtitles_module
from yt_shorts_factory.script import cleaner as cleaner_module
from yt_shorts_factory.script import gender as gender_module
from yt_shorts_factory.script import hook as hook_module
from yt_shorts_factory.sources import dedup as dedup_module
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
    asmr_path: Path | None = None
    niche_name: str | None = None
    detected_gender: gender_module.Gender = "unknown"


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


def _pick_gendered_voice(
    cleaned_text: str,
    tts: TtsConfig,
    kokoro_cfg: object,
    *,
    rotation_seed: int,
    user_overrides: set[str],
) -> tuple[str, Literal["male", "female", "unknown"]]:
    """Resolve the per-story narrator voice.

    Honors ``--voice`` overrides, falls back to the niche/profile voice when
    no gender signal is detectable.
    """
    if "voice" in user_overrides or not tts.auto_gender:
        return tts.voice, "unknown"

    if tts.backend == "kokoro":
        male = list(getattr(kokoro_cfg, "male_voices", []))
        female = list(getattr(kokoro_cfg, "female_voices", []))
        fallback = getattr(kokoro_cfg, "voice", "am_michael")
    else:
        male = list(tts.male_voices)
        female = list(tts.female_voices)
        fallback = tts.voice

    voice, detected = gender_module.pick_voice(
        cleaned_text,
        male_voices=male,
        female_voices=female,
        fallback=fallback,
        rotation_seed=rotation_seed,
    )
    return voice, detected


def _maybe_fallback_to_edge(cfg: PipelineConfig) -> None:
    """If Kokoro is requested but its model files aren't on disk, fall back."""
    if cfg.tts.backend != "kokoro" or not cfg.tts.fallback_to_edge:
        return
    model_path = cfg.kokoro.model_dir / cfg.kokoro.model_file
    voices_path = cfg.kokoro.model_dir / cfg.kokoro.voices_file
    if model_path.exists() and voices_path.exists():
        return
    log.warning(
        "Kokoro model files missing at %s; falling back to Edge TTS. "
        "Run `yt-shorts-factory download-tts-models` to enable Kokoro (~310 MB).",
        cfg.kokoro.model_dir,
    )
    cfg.tts.backend = "edge"


def _pick_story(cfg: PipelineConfig) -> reddit_source.RedditStory:
    """Pull stories from Reddit, filter through dedup, return the best fresh one."""
    target = cfg.reddit.subreddit or ",".join(cfg.reddit.subreddits[:3]) or "AmItheAsshole"
    log.info("Fetching stories from r/%s (sort=%s, fresh=%s)",
             target, cfg.reddit.sort, cfg.reddit.include_fresh)
    stories = reddit_source.fetch_stories(cfg.reddit)
    if cfg.dedup.enabled:
        before = len(stories)
        unprocessed = dedup_module.filter_unprocessed([s.id for s in stories], cfg.dedup)
        stories = [s for s in stories if s.id in unprocessed]
        log.info("Dedup: %d/%d posts are unprocessed", len(stories), before)
    chosen = reddit_source.pick_best(stories)
    if chosen is None:
        raise RuntimeError(
            f"No suitable stories found in r/{target} with current filters "
            f"(min={cfg.reddit.min_chars}, max={cfg.reddit.max_chars}, "
            f"dedup_skipped={cfg.dedup.enabled})."
        )
    return chosen


def generate(
    cfg: PipelineConfig,
    *,
    story: reddit_source.RedditStory | None = None,
    rng: random.Random | None = None,
    user_overrides: set[str] | None = None,
) -> GenerationResult:
    """Run the full pipeline. Returns paths to all produced artifacts."""
    rng = rng or random.Random()
    user_overrides = user_overrides or set()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.work_dir.mkdir(parents=True, exist_ok=True)

    if story is None:
        story = _pick_story(cfg)

    # Resolve & apply niche profile if requested.
    niche_name: str | None = None
    profile = None
    if cfg.niche == "auto":
        profile = niche_profiles.resolve_profile(story.subreddit)
    elif cfg.niche:
        profile = niche_profiles.resolve_profile(cfg.niche)
    if profile is not None:
        niche_profiles.apply_profile(cfg, profile, overrides=user_overrides)
        niche_name = profile.name
        log.info(
            "Applied niche profile: %s (voice=%s, mood=%s), respecting user overrides: %s",
            profile.name,
            cfg.tts.voice,
            profile.music_mood,
            sorted(user_overrides) if user_overrides else "(none)",
        )

    slug = _slugify(story.title)
    work_subdir = cfg.work_dir / f"{story.id}_{slug}"
    work_subdir.mkdir(parents=True, exist_ok=True)

    log.info("Selected story: %s (score=%d)", story.title, story.score)

    # Build the hook + cleaned narration text.
    raw_text = hook_module.assemble_narration(story.title, story.body, cfg.hook)
    cleaned = cleaner_module.clean_story(raw_text)
    (work_subdir / "script.txt").write_text(cleaned, encoding="utf-8")

    # Pick a Kokoro/Edge fallback if Kokoro isn't installed.
    _maybe_fallback_to_edge(cfg)

    # Auto-pick male/female voice based on the cleaned narration.
    voice_name, detected_gender = _pick_gendered_voice(
        cleaned,
        cfg.tts,
        cfg.kokoro,
        rotation_seed=hash(story.id) & 0xFFFF,
        user_overrides=user_overrides,
    )
    if cfg.tts.backend == "kokoro":
        cfg.kokoro.voice = voice_name
    else:
        cfg.tts.voice = voice_name
    log.info(
        "Voice: %s (backend=%s, detected_gender=%s)",
        voice_name,
        cfg.tts.backend,
        detected_gender,
    )

    # Synthesize voiceover.
    voice_path = work_subdir / "voice.mp3"
    log.info("Synthesizing voiceover -> %s", voice_path)
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

    # Optional picture-in-picture ASMR / cooking overlay.
    asmr_path: Path | None = None
    asmr_pip: composer_module.PipLayout | None = None
    if cfg.asmr.enabled:
        asmr_path = asmr_module.pick_clip(cfg.asmr, rng=rng)
        if asmr_path is not None:
            asmr_pip = composer_module.PipLayout(
                width=cfg.asmr.pip_width,
                height=cfg.asmr.pip_height,
                y=cfg.asmr.pip_y,
                x=cfg.asmr.pip_x,
            )
            log.info(
                "ASMR overlay: %s (PiP %dx%d @ y=%d)",
                asmr_path.name,
                asmr_pip.width,
                asmr_pip.height,
                asmr_pip.y,
            )
        else:
            log.warning(
                "ASMR overlay enabled but no clip available — rendering "
                "without PiP. Run `yt-shorts-factory download-gameplay "
                "--kind asmr` while online to populate the ASMR cache."
            )

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
        asmr_path=asmr_path,
        asmr_pip=asmr_pip,
    )

    # Record the post in the dedup db so future batches skip it.
    dedup_module.mark_rendered(story.id, story.subreddit, story.title, cfg.dedup)

    return GenerationResult(
        story=story,
        cleaned_text=cleaned,
        voice_path=voice_path,
        subtitles_path=subs_path,
        gameplay_path=gameplay_path,
        output_path=output_path,
        sfx_clips=tuple(sfx_clips),
        music_path=music_path,
        asmr_path=asmr_path,
        niche_name=niche_name,
        detected_gender=detected_gender,
    )
