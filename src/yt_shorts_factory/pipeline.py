"""End-to-end pipeline orchestrator.

Stages:
  1. Pull stories from Reddit.
  2. Pick a story.
  3. Clean its text.
  4. Synthesize voiceover (Edge TTS).
  5. Transcribe voiceover (faster-whisper) -> word timings.
  6. Generate .ass subtitles.
  7. Pick a gameplay clip.
  8. Compose the final mp4 with ffmpeg.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path

from yt_shorts_factory.assets import gameplay as gameplay_module
from yt_shorts_factory.config import PipelineConfig
from yt_shorts_factory.render import composer as composer_module
from yt_shorts_factory.render import subtitles as subtitles_module
from yt_shorts_factory.script import cleaner as cleaner_module
from yt_shorts_factory.sources import reddit as reddit_source
from yt_shorts_factory.transcribe import whisper as whisper_module
from yt_shorts_factory.tts import edge as edge_tts_module

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


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:60] or "story"


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

    slug = _slugify(story.title)
    work_subdir = cfg.work_dir / f"{story.id}_{slug}"
    work_subdir.mkdir(parents=True, exist_ok=True)

    log.info("Selected story: %s (score=%d)", story.title, story.score)
    cleaned = cleaner_module.clean_story(story.full_text)
    (work_subdir / "script.txt").write_text(cleaned, encoding="utf-8")

    voice_path = work_subdir / "voice.mp3"
    log.info("Synthesizing voiceover -> %s", voice_path)
    edge_tts_module.synthesize(cleaned, voice_path, cfg.tts)

    log.info("Transcribing voiceover for word timings")
    words = whisper_module.transcribe_words(voice_path, cfg.whisper)
    if not words:
        raise RuntimeError("Whisper returned no words; cannot build subtitles.")

    subs_path = work_subdir / "subs.ass"
    subtitles_module.write_ass(words, subs_path, cfg.subtitles, cfg.render)

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
    )

    return GenerationResult(
        story=story,
        cleaned_text=cleaned,
        voice_path=voice_path,
        subtitles_path=subs_path,
        gameplay_path=gameplay_path,
        output_path=output_path,
    )
