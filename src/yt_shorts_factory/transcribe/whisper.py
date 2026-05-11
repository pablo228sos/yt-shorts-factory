"""faster-whisper wrapper that returns word-level timings.

We re-transcribe the TTS audio (rather than re-using the input text)
because the audio's word boundaries are what need to drive the subtitle
animation. Whisper is more than accurate enough for clean synthetic speech.

The first call is slow because the model needs to download; subsequent
calls reuse the cached model and run in roughly real-time on CPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yt_shorts_factory.config import WhisperConfig

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class Word:
    """A single transcribed word with timing in seconds."""

    text: str
    start: float
    end: float


def _load_model(cfg: WhisperConfig) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(
        cfg.model_size,
        device=cfg.device,
        compute_type=cfg.compute_type,
    )


def transcribe_words(audio_path: Path, cfg: WhisperConfig) -> list[Word]:
    """Return per-word timings for `audio_path`."""
    model = _load_model(cfg)
    segments, _info = model.transcribe(
        str(audio_path),
        language=cfg.language,
        word_timestamps=True,
        vad_filter=True,
    )
    words: list[Word] = []
    for segment in segments:
        if not segment.words:
            continue
        for w in segment.words:
            text = (w.word or "").strip()
            if not text:
                continue
            words.append(Word(text=text, start=float(w.start), end=float(w.end)))
    return words
