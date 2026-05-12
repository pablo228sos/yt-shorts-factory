"""Sound-effect synthesis and placement.

We don't ship any sound files in the repo — they're generated on demand
by ffmpeg from sine waves and filtered noise. Licensing-clean (math) and
zero external downloads.

  - ``vine_boom.mp3``: ~50 Hz damped sine, the classic "dramatic moment"
    booming bass drop.
  - ``ding.mp3``     : Bright 1.5 kHz double-tap, like a notification chime.
  - ``whoosh.mp3``   : Filtered noise burst, scene-transition wind.
  - ``suspense.mp3`` : 220 Hz sine swell with tremolo, used for build-ups.

``synthesize_default_sfx`` is idempotent: if a file already exists it
won't be regenerated. ``place_sfx`` picks where in the narration to fire
each effect.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from yt_shorts_factory.config import SfxConfig
from yt_shorts_factory.transcribe.whisper import Word

log = logging.getLogger(__name__)


_SCENE_MARKERS: tuple[str, ...] = (
    "edit:",
    "update:",
    "verdict:",
    "tldr",
    "tl;dr",
    "so anyway",
    "fast forward",
    "the next day",
    "a week later",
    "and then",
)


@dataclass(frozen=True)
class SfxClip:
    """A single SFX placement: which file, at which timestamp, at which gain."""

    path: Path
    start_s: float
    gain_db: float


def _ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is required to synthesize SFX. Install ffmpeg and rerun."
        )


def _run_ffmpeg(filter_expr: str, out_path: Path) -> None:
    """Render an ffmpeg lavfi filter graph straight to mp3."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        filter_expr,
        "-ac",
        "1",
        "-ar",
        "44100",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def _synth_vine_boom(out_path: Path) -> None:
    # Classic "vine boom": 50 Hz sine with exponential decay over ~1.2 s.
    expr = (
        "aevalsrc=expr='sin(2*PI*50*t)*exp(-3.0*t)':d=1.2:s=44100,"
        "volume=2.5"
    )
    _run_ffmpeg(expr, out_path)


def _synth_ding(out_path: Path) -> None:
    # Two short 1.5 kHz pings with a tiny gap. Bright "notification" feel.
    expr = (
        "aevalsrc=expr='sin(2*PI*1500*t)*exp(-8*t) + "
        "0.5*sin(2*PI*1500*(t-0.18))*exp(-8*(t-0.18))*lt(t\\,0.4)':d=0.5:s=44100"
    )
    _run_ffmpeg(expr, out_path)


def _synth_whoosh(out_path: Path) -> None:
    # Filtered white noise sweep — wind-by transition.
    expr = "anoisesrc=color=white:duration=0.6:amplitude=0.4,highpass=f=400,lowpass=f=2500"
    _run_ffmpeg(expr, out_path)


def _synth_suspense(out_path: Path) -> None:
    # 220 Hz drone + 4 Hz tremolo, 2 s — under nosleep cliffhangers.
    expr = "sine=frequency=220:duration=2.0,tremolo=f=4:d=0.6"
    _run_ffmpeg(expr, out_path)


_SYNTHESIZERS = {
    "vine_boom.mp3": _synth_vine_boom,
    "ding.mp3": _synth_ding,
    "whoosh.mp3": _synth_whoosh,
    "suspense.mp3": _synth_suspense,
}


def synthesize_default_sfx(cfg: SfxConfig, *, force: bool = False) -> list[Path]:
    """Generate the default SFX library into ``cfg.sfx_dir``.

    Returns the list of paths that exist after the call. Safe to call on
    every run — already-present files are skipped unless ``force=True``.
    """
    _ensure_ffmpeg()
    cfg.sfx_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, synth in _SYNTHESIZERS.items():
        path = cfg.sfx_dir / name
        if path.exists() and path.stat().st_size > 0 and not force:
            paths.append(path)
            continue
        log.info("Synthesizing SFX: %s", name)
        synth(path)
        paths.append(path)
    return paths


def _spans_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return not (a[1] <= b[0] or b[1] <= a[0])


def place_sfx(
    words: list[Word],
    full_text: str,
    cfg: SfxConfig,
) -> list[SfxClip]:
    """Decide where to fire SFX based on the transcribed timing and the script.

    Heuristics:
      - End of a question (``?``) within the first half of the video → vine boom.
      - First word of a scene-marker phrase (``edit:``, ``the next day``) → ding.
      - Every ~15 s of narration → whoosh (used as a pacing transition cue).
    """
    if not cfg.enabled or not words:
        return []

    clips: list[SfxClip] = []
    text_lc = (full_text or "").lower()

    vine_boom = cfg.sfx_dir / "vine_boom.mp3"
    ding = cfg.sfx_dir / "ding.mp3"
    whoosh = cfg.sfx_dir / "whoosh.mp3"

    # Vine booms on question marks (limit total to keep things tasteful).
    booms_so_far = 0
    for w in words:
        if w.text.rstrip(",").endswith(("?", "?!", "!?", "!!")):
            if booms_so_far >= 3:
                break
            # Only place when vine_boom.mp3 exists on disk.
            if vine_boom.exists():
                clips.append(
                    SfxClip(path=vine_boom, start_s=w.end + 0.05, gain_db=cfg.vine_boom_db)
                )
                booms_so_far += 1

    # Dings on scene markers. Find each marker's start word.
    if ding.exists() and text_lc:
        for marker in _SCENE_MARKERS:
            idx = text_lc.find(marker)
            if idx < 0:
                continue
            # Roughly map the character offset to a word index by counting
            # whitespace runs. Cheap approximation but good enough for SFX.
            word_idx = max(0, min(len(words) - 1, len(full_text[:idx].split())))
            target = words[word_idx]
            clips.append(
                SfxClip(
                    path=ding,
                    start_s=max(0.0, target.start - 0.05),
                    gain_db=cfg.ding_db,
                )
            )

    # Whooshes as periodic pacing cues, but never two SFX overlapping.
    if whoosh.exists() and words[-1].end > 25.0:
        total = words[-1].end
        next_at = 15.0
        while next_at < total - 5.0:
            # Snap to the nearest word boundary.
            nearest = min(words, key=lambda w: abs(w.start - next_at))
            clips.append(
                SfxClip(path=whoosh, start_s=nearest.start, gain_db=cfg.whoosh_db)
            )
            next_at += 18.0

    # Enforce max count and no-overlap.
    clips.sort(key=lambda c: c.start_s)
    deduped: list[SfxClip] = []
    occupied: list[tuple[float, float]] = []
    for clip in clips:
        if len(deduped) >= cfg.max_sfx_per_video:
            break
        span = (clip.start_s, clip.start_s + 1.5)
        if any(_spans_overlap(span, o) for o in occupied):
            continue
        if span[0] < cfg.min_gap_seconds or span[0] > words[-1].end - cfg.min_gap_seconds:
            continue
        deduped.append(clip)
        occupied.append(span)
    return deduped
