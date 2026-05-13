"""Glue together gameplay B-roll, narration audio, SFX, optional music,
and burned-in subtitles into a single 1080x1920 mp4 using ffmpeg.

Filter graph overview (worst case, music + SFX):
  [0:v] scale=W:H:lanczos, crop, fps -> [bg] -> subtitles -> [v]
  [1:a] atempo=speedup, apad                 -> [vo_raw] -> asplit -> [vo][sc]
  [2:a] aloop, atrim, volume                 -> [m_raw]
  [m_raw][sc] sidechaincompress              -> [music]
  [3:a] adelay,volume                        -> [sfx0]
  [4:a] adelay,volume                        -> [sfx1]
  [0:a] volume=duck_music_db                 -> [bgm]
  [vo][music][sfx0..n][bgm] amix=normalize=0 -> [a]

If music or SFX are absent the corresponding legs are simply dropped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from yt_shorts_factory.assets.sfx import SfxClip
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


def _clamp_atempo(speedup: float) -> list[float]:
    """ffmpeg's atempo filter accepts 0.5..2.0 per instance; chain them
    for ratios outside that range."""
    if speedup <= 0:
        return [1.0]
    ratios: list[float] = []
    remaining = speedup
    while remaining > 2.0:
        ratios.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        ratios.append(0.5)
        remaining /= 0.5
    ratios.append(remaining)
    return ratios


def _build_filter_graph(
    *,
    cfg: RenderConfig,
    subs_arg: str,
    speedup: float,
    duration_s: float,
    voice_idx: int,
    music_idx: int | None,
    sfx_clips: list[tuple[int, SfxClip]],
    intro_padding_s: float,
    music_base_db: float,
    music_sidechain: bool,
    asmr_idx: int | None = None,
    asmr_height: int = 0,
) -> str:
    """Assemble the -filter_complex string.

    When ``asmr_idx`` is set the video is rendered as a vertical
    split-screen: the top ``cfg.height - asmr_height`` pixels show the
    gameplay B-roll and the bottom ``asmr_height`` pixels show the muted
    ASMR clip. Subtitles are burned over the combined frame.
    """
    scale_flags = cfg.scale_flags
    if asmr_idx is not None and asmr_height > 0:
        top_h = cfg.height - asmr_height
        vf_parts = [
            f"[0:v]scale={cfg.width}:{top_h}:"
            f"force_original_aspect_ratio=increase:flags={scale_flags},"
            f"crop={cfg.width}:{top_h},setsar=1,fps={cfg.fps}[top]",
            f"[{asmr_idx}:v]scale={cfg.width}:{asmr_height}:"
            f"force_original_aspect_ratio=increase:flags={scale_flags},"
            f"crop={cfg.width}:{asmr_height},setsar=1,fps={cfg.fps}[bot]",
            "[top][bot]vstack=inputs=2[bg]",
            f"[bg]subtitles='{subs_arg}'[v]",
        ]
    else:
        vf_parts = [
            f"[0:v]scale={cfg.width}:{cfg.height}:"
            f"force_original_aspect_ratio=increase:flags={scale_flags},"
            f"crop={cfg.width}:{cfg.height},setsar=1,fps={cfg.fps}[bg]",
            f"[bg]subtitles='{subs_arg}'[v]",
        ]

    audio_parts: list[str] = []

    # Voice leg with atempo chain + outro pad. Only split into a sidechain
    # copy when music ducking is actually going to consume it; ffmpeg errors
    # out on any named output pad that's never connected downstream.
    atempo_chain = ",".join(f"atempo={r}" for r in _clamp_atempo(speedup))
    audio_parts.append(
        f"[{voice_idx}:a]{atempo_chain},apad=pad_dur={cfg.outro_padding_s}[vo_raw]"
    )
    needs_sidechain = music_idx is not None and music_sidechain
    if needs_sidechain:
        audio_parts.append("[vo_raw]asplit=2[vo][vo_sc]")
    else:
        audio_parts.append("[vo_raw]anull[vo]")

    mix_labels: list[str] = ["[vo]"]

    # SFX legs.
    for i, (input_idx, clip) in enumerate(sfx_clips):
        # adelay wants ms; pad both channels (we forced mono on synth, but
        # apply :all=1 to be safe in case the input is stereo).
        delay_ms = max(0, int((clip.start_s + intro_padding_s) * 1000))
        audio_parts.append(
            f"[{input_idx}:a]adelay={delay_ms}:all=1,volume={clip.gain_db}dB[sfx{i}]"
        )
        mix_labels.append(f"[sfx{i}]")

    # Music leg with optional sidechain ducking.
    if music_idx is not None:
        audio_parts.append(
            f"[{music_idx}:a]aloop=loop=-1:size=2147483647,"
            f"atrim=duration={duration_s:.3f},"
            f"volume={music_base_db}dB[m_raw]"
        )
        if needs_sidechain:
            audio_parts.append(
                "[m_raw][vo_sc]sidechaincompress="
                "threshold=0.05:ratio=10:attack=20:release=300:level_sc=1[music]"
            )
        else:
            audio_parts.append("[m_raw]anull[music]")
        mix_labels.append("[music]")

    # Gameplay's own audio always ducked low.
    audio_parts.append(f"[0:a]volume={cfg.duck_music_db}dB[bgm]")
    mix_labels.append("[bgm]")

    audio_parts.append(
        f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:"
        f"duration=longest:dropout_transition=0:normalize=0[a]"
    )

    return ";".join(vf_parts + audio_parts)


def compose(
    *,
    gameplay_path: Path,
    voice_path: Path,
    subtitles_path: Path,
    output_path: Path,
    cfg: RenderConfig,
    speedup: float = 1.0,
    sfx_clips: list[SfxClip] | None = None,
    music_path: Path | None = None,
    music_base_db: float = -22.0,
    music_sidechain: bool = True,
    asmr_path: Path | None = None,
    asmr_height: int = 0,
) -> Path:
    """Render the final Short. Returns ``output_path`` on success.

    When ``asmr_path`` is provided the video is rendered as a vertical
    split-screen (top: gameplay, bottom: muted ASMR).
    """
    _ensure_ffmpeg()
    if not gameplay_path.exists():
        raise FileNotFoundError(gameplay_path)
    if not voice_path.exists():
        raise FileNotFoundError(voice_path)
    if not subtitles_path.exists():
        raise FileNotFoundError(subtitles_path)

    raw_voice_duration = _ffprobe_duration(voice_path)
    voice_duration = raw_voice_duration / max(0.1, speedup)
    duration = voice_duration + cfg.intro_padding_s + cfg.outro_padding_s
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subs_arg = _escape_subtitles_path(subtitles_path)

    # Build ffmpeg input args + assign indices.
    inputs: list[str] = ["-stream_loop", "-1", "-i", str(gameplay_path)]
    voice_idx = 1
    inputs += ["-itsoffset", str(cfg.intro_padding_s), "-i", str(voice_path)]

    sfx_clips = sfx_clips or []
    music_idx: int | None = None
    asmr_idx: int | None = None
    next_idx = 2

    # Music goes first (lower SFX indices keep filter strings short) but
    # order in inputs doesn't matter for correctness — only the index does.
    if music_path is not None and music_path.exists():
        inputs += ["-stream_loop", "-1", "-i", str(music_path)]
        music_idx = next_idx
        next_idx += 1

    if asmr_path is not None and asmr_path.exists() and asmr_height > 0:
        # ``-an`` here would apply to the *entire* compose call; instead
        # we just ignore the ASMR audio stream by never mapping it into
        # the audio graph. -stream_loop lets it cover long narrations.
        inputs += ["-stream_loop", "-1", "-i", str(asmr_path)]
        asmr_idx = next_idx
        next_idx += 1

    indexed_sfx: list[tuple[int, SfxClip]] = []
    for clip in sfx_clips:
        if not clip.path.exists():
            continue
        inputs += ["-i", str(clip.path)]
        indexed_sfx.append((next_idx, clip))
        next_idx += 1

    filter_graph = _build_filter_graph(
        cfg=cfg,
        subs_arg=subs_arg,
        speedup=speedup,
        duration_s=duration,
        voice_idx=voice_idx,
        music_idx=music_idx,
        sfx_clips=indexed_sfx,
        intro_padding_s=cfg.intro_padding_s,
        music_base_db=music_base_db,
        music_sidechain=music_sidechain,
        asmr_idx=asmr_idx,
        asmr_height=asmr_height if asmr_idx is not None else 0,
    )

    cmd: list[str] = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_graph]
    cmd += [
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        cfg.preset,
        "-crf",
        str(cfg.crf),
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
