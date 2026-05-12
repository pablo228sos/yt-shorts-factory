"""TTS dispatcher: pick the right backend based on ``TtsConfig.backend``."""

from __future__ import annotations

from pathlib import Path

from yt_shorts_factory.config import KokoroConfig, TtsConfig


def synthesize(text: str, out_path: Path, cfg: TtsConfig, kokoro_cfg: KokoroConfig) -> Path:
    """Render ``text`` to an audio file at ``out_path`` using the configured backend."""
    if cfg.backend == "edge":
        from yt_shorts_factory.tts import edge

        return edge.synthesize(text, out_path, cfg)
    if cfg.backend == "kokoro":
        from yt_shorts_factory.tts import kokoro

        return kokoro.synthesize(text, out_path, kokoro_cfg)
    raise ValueError(f"Unknown TTS backend: {cfg.backend!r}")
