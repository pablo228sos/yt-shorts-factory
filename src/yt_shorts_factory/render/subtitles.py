r"""Generate Advanced SubStation Alpha (.ass) subtitles with TikTok-style
"pop word" animation.

Approach: group consecutive words into small chunks (default 1-3 words),
emit one ASS Dialogue line per chunk. The chunk appears from the start of
its first word to the end of its last word, large-font, centered around
``style.vertical_position``, white text + black outline. The current
word inside the chunk is highlighted in yellow.

We also support ALL CAPS rendering and a font-fallback list. libass picks
the first font it can find on the system, so listing ``Bebas Neue, Impact,
Arial Black`` gracefully degrades on a fresh Windows install (Impact ships
with Windows) while still using Bebas Neue when present.

This avoids needing libass karaoke `\k` tags and works reliably with
ffmpeg's `subtitles` filter on any system.
"""

from __future__ import annotations

from pathlib import Path

from yt_shorts_factory.config import RenderConfig, SubtitleStyle
from yt_shorts_factory.transcribe.whisper import Word


def _format_time(t: float) -> str:
    """ASS time format: H:MM:SS.cs (centiseconds)."""
    if t < 0:
        t = 0.0
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = t % 60
    return f"{hours}:{minutes:02d}:{seconds:05.2f}"


def _chunk_words(words: list[Word], max_per_chunk: int) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        current.append(word)
        ends_sentence = word.text.endswith((".", "!", "?", ","))
        if len(current) >= max_per_chunk or ends_sentence:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _format_font_for_ass(style: SubtitleStyle) -> str:
    """libass accepts a comma-separated list of preferred fonts."""
    fonts = [style.font, *style.font_fallback]
    # Dedupe while preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for f in fonts:
        if f and f not in seen:
            seen.add(f)
            uniq.append(f)
    return ",".join(uniq)


def _build_header(style: SubtitleStyle, render: RenderConfig) -> str:
    margin_v = int(render.height * (1.0 - style.vertical_position))
    bold = -1 if style.bold else 0
    fontname = _format_font_for_ass(style)
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {render.width}\n"
        f"PlayResY: {render.height}\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 2\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Pop,{fontname},{style.font_size},{style.primary_color},"
        f"{style.primary_color},{style.outline_color},&H00000000,"
        f"{bold},0,0,0,100,100,0,0,1,{style.outline_width},{style.shadow},"
        f"5,40,40,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )


def _transform_text(text: str, style: SubtitleStyle) -> str:
    if style.uppercase:
        return text.upper()
    return text


def _render_chunk_text(chunk: list[Word], highlight_idx: int, style: SubtitleStyle) -> str:
    parts: list[str] = []
    for i, word in enumerate(chunk):
        token = _transform_text(word.text, style)
        if i == highlight_idx:
            # Active word: yellow color + slight scale pop ("\fscx115\fscy115").
            parts.append(
                rf"{{\c{style.highlight_color}\fscx115\fscy115}}"
                rf"{token}"
                rf"{{\c{style.primary_color}\fscx100\fscy100}}"
            )
        else:
            parts.append(token)
    return " ".join(parts)


def build_ass(
    words: list[Word],
    style: SubtitleStyle,
    render: RenderConfig,
) -> str:
    """Build the full .ass file contents for the given word-level timings."""
    chunks = _chunk_words(words, max_per_chunk=style.max_words_per_chunk)
    lines = [_build_header(style, render)]

    for chunk in chunks:
        if not chunk:
            continue
        chunk_start = chunk[0].start
        chunk_end = chunk[-1].end
        for idx, word in enumerate(chunk):
            seg_start = word.start if idx > 0 else chunk_start
            seg_end = word.end if idx < len(chunk) - 1 else chunk_end
            if seg_end <= seg_start:
                seg_end = seg_start + 0.05
            text = _render_chunk_text(chunk, highlight_idx=idx, style=style)
            line = (
                f"Dialogue: 0,{_format_time(seg_start)},{_format_time(seg_end)},"
                f"Pop,,0,0,0,,{text}"
            )
            lines.append(line)
    return "\n".join(lines) + "\n"


def write_ass(
    words: list[Word],
    out_path: Path,
    style: SubtitleStyle,
    render: RenderConfig,
) -> Path:
    """Write the .ass subtitle file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = build_ass(words, style, render)
    out_path.write_text(content, encoding="utf-8")
    return out_path
