"""Glue together gameplay B-roll, narration audio, and burned-in subtitles
into a single 1080x1920 mp4 using ffmpeg.

Filter graph overview:
  [0:v] crop+scale to 1080x1920, trim to narration length -> [bg]
  [bg]  burn .ass subtitles                                -> [v]
  [0:a] lower gameplay volume by `duck_music_db`           -> [bgm]
  [1:a] voiceover (left as-is)                             -> [vo]
  [bgm][vo] amix -> [a]
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from yt_shorts_factory.config import RenderConfig


def _ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def _ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not installed or not on PATH.")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe is not installed or not on PATH.")


def _escape_subtitles_path(p: Path) -> str:
    """ffmpeg's subtitles filter parses its argument as a filter expression,
    so we need to escape backslashes, colons, and single quotes."""
    s = str(p)
    s = s.replace("\\", "\\\\")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    return s


def compose(
    *,
    gameplay_path: Path,
    voice_path: Path,
    subtitles_path: Path,
    output_path: Path,
    cfg: RenderConfig,
) -> Path:
    """Render the final Short. Returns `output_path` on success."""
    _ensure_ffmpeg()
    if not gameplay_path.exists():
        raise FileNotFoundError(gameplay_path)
    if not voice_path.exists():
        raise FileNotFoundError(voice_path)
    if not subtitles_path.exists():
        raise FileNotFoundError(subtitles_path)

    duration = _ffprobe_duration(voice_path) + cfg.intro_padding_s + cfg.outro_padding_s
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subs_arg = _escape_subtitles_path(subtitles_path)
    # Center-crop horizontally to a 9:16 frame then scale to target size.
    # `force_original_aspect_ratio=increase` ensures we always cover.
    vf = (
        f"[0:v]scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=increase,"
        f"crop={cfg.width}:{cfg.height},setsar=1,fps={cfg.fps}[bg];"
        f"[bg]subtitles='{subs_arg}'[v];"
        f"[0:a]volume={cfg.duck_music_db}dB[bgm];"
        f"[1:a]apad=pad_dur={cfg.outro_padding_s}[vo];"
        f"[bgm][vo]amix=inputs=2:duration=longest:dropout_transition=0[a]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(gameplay_path),
        "-itsoffset",
        str(cfg.intro_padding_s),
        "-i",
        str(voice_path),
        "-filter_complex",
        vf,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-b:v",
        cfg.video_bitrate,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        cfg.audio_bitrate,
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return output_path
