"""Edge-TTS based narration generator.

Microsoft's Edge browser exposes a free streaming TTS endpoint with very
natural-sounding neural voices. `edge-tts` is a thin Python wrapper around
that endpoint. No API key required.

We intentionally do NOT use SSML beyond simple rate/pitch/volume because
the public endpoint is occasionally picky about prosody tags.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from yt_shorts_factory.config import TtsConfig


async def _synthesize_async(text: str, out_path: Path, cfg: TtsConfig) -> None:
    communicator = edge_tts.Communicate(
        text=text,
        voice=cfg.voice,
        rate=cfg.rate,
        pitch=cfg.pitch,
        volume=cfg.volume,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    await communicator.save(str(out_path))


def synthesize(text: str, out_path: Path, cfg: TtsConfig) -> Path:
    """Render `text` to an mp3 file at `out_path` using Edge TTS."""
    if not text.strip():
        raise ValueError("Cannot synthesize empty text.")
    asyncio.run(_synthesize_async(text, out_path, cfg))
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"TTS produced no output at {out_path}")
    return out_path


async def list_voices(language_prefix: str = "en-US") -> list[str]:
    """Return short names of available voices (debug helper)."""
    voices = await edge_tts.list_voices()
    return [v["ShortName"] for v in voices if v["ShortName"].startswith(language_prefix)]
