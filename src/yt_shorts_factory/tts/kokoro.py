"""Kokoro-ONNX TTS backend.

Kokoro is a state-of-the-art open-source TTS model that runs locally
without an API key. We import it lazily so the package stays usable for
users on Edge TTS who don't want the ~300 MB model download.

Usage:
    pip install kokoro-onnx soundfile
    yt-shorts-factory download-tts-models   # one-time, downloads model + voices
    yt-shorts-factory generate-cmd --tts kokoro ...
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import urllib.request
from pathlib import Path

from yt_shorts_factory.config import KokoroConfig

log = logging.getLogger(__name__)


class KokoroNotInstalled(RuntimeError):
    """Raised when the optional Kokoro backend is requested but not available."""


def _check_dependencies() -> None:
    """Import-check; raises ``KokoroNotInstalled`` with a friendly message."""
    try:
        import kokoro_onnx  # noqa: F401
        import soundfile  # noqa: F401
    except ImportError as exc:
        raise KokoroNotInstalled(
            "Kokoro backend requested but not installed. "
            "Run: pip install kokoro-onnx soundfile"
        ) from exc


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    log.info("Downloading %s -> %s", url, dest)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    tmp.replace(dest)
    return dest


def download_models(cfg: KokoroConfig) -> tuple[Path, Path]:
    """Download the Kokoro ONNX model + voicepack if not already present.

    Returns ``(model_path, voices_path)``.
    """
    cfg.model_dir.mkdir(parents=True, exist_ok=True)
    model_path = cfg.model_dir / cfg.model_file
    voices_path = cfg.model_dir / cfg.voices_file
    _download(cfg.model_url, model_path)
    _download(cfg.voices_url, voices_path)
    return model_path, voices_path


def synthesize(text: str, out_path: Path, cfg: KokoroConfig) -> Path:
    """Render ``text`` to a wav file via Kokoro-ONNX.

    We write a wav (not mp3) here because soundfile writes wav natively.
    The composer normalizes the input through ffmpeg's atempo chain anyway
    so the container doesn't matter downstream.
    """
    _check_dependencies()
    # Lazy imports to keep the module importable without kokoro-onnx.
    import soundfile as sf
    from kokoro_onnx import Kokoro

    if not text.strip():
        raise ValueError("Cannot synthesize empty text.")

    model_path = cfg.model_dir / cfg.model_file
    voices_path = cfg.model_dir / cfg.voices_file
    if not model_path.exists() or not voices_path.exists():
        raise KokoroNotInstalled(
            f"Kokoro model files missing. Run: yt-shorts-factory download-tts-models "
            f"(or place {cfg.model_file} and {cfg.voices_file} in {cfg.model_dir})"
        )

    kokoro = Kokoro(str(model_path), str(voices_path))
    samples, sample_rate = kokoro.create(
        text,
        voice=cfg.voice,
        speed=cfg.speed,
        lang=cfg.lang,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write as wav; downstream ffmpeg handles any container.
    wav_path = out_path.with_suffix(".wav")
    sf.write(str(wav_path), samples, sample_rate)
    # If caller asked for .mp3, transcode for compatibility with the
    # composer's existing pipeline expectations.
    if out_path.suffix.lower() != ".wav":
        _transcode_to_mp3(wav_path, out_path)
        wav_path.unlink(missing_ok=True)
        return out_path
    return wav_path


def _transcode_to_mp3(src: Path, dst: Path) -> None:
    """Convert wav -> mp3 with ffmpeg (no quality loss for our purposes)."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg required to transcode Kokoro output to mp3.")
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(dst),
    ]
    subprocess.run(cmd, check=True)
