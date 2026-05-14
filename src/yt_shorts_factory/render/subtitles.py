r"""Generate Advanced SubStation Alpha (.ass) subtitles with TikTok-style
"pop word" animation.

Approach: group consecutive words into small chunks (default 1-3 words),
emit one ASS Dialogue line per chunk. The chunk appears from the start of
its first word to the end of its last word, large-font, centered around
``style.vertical_position``, white text + black outline. The current
word inside the chunk is highlighted in yellow.

We also support ALL CAPS rendering. The Style's ``Fontname`` field is a
*single* name (commas are field separators in .ass and would corrupt the
Style line, e.g. shifting ``Outline`` and ``Shadow`` into the wrong
slots and producing the giant black blob users saw around captions).
When the requested font is missing libass substitutes via the system
font stack (DirectWrite on Windows, fontconfig on Linux/macOS).

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
    """Return a single font name safe for a .ass Style ``Fontname`` field.

    .ass Style fields are comma-separated, so commas inside ``Fontname``
    silently shift every later field (Bold, Italic, BorderStyle, Outline,
    Shadow, Alignment...) by N positions. That is what previously made
    captions render with a giant black halo: ``Outline`` and ``Shadow``
    ended up at 100 instead of the intended thin values. We therefore
    pick a single primary font here and trust libass + the host font
    subsystem to substitute when the font is missing.
    """
    primary = style.font.strip()
    if "," in primary:
        primary = primary.split(",", 1)[0].strip()
    return primary or "Arial Black"


def _build_header(style: SubtitleStyle, render: RenderConfig) -> str:
    """Emit the .ass header.

    Subtitles are positioned in each event via an explicit ``\\pos(x,y)``
    tag (see ``build_ass``), not via Alignment + MarginV \u2014 different libass
    builds disagree on whether MarginV measures from the top or the bottom
    when Alignment=5 (middle-center), which is what made the prior version
    drop captions into the bottom corner on some installs. Using absolute
    coordinates is deterministic across every supported libass.
    """
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
        f"5,40,40,0,1\n"
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
    r"""Build the full .ass file contents for the given word-level timings.

    Each Dialogue line is prefixed with an absolute ``\pos(x,y)`` tag so
    the caption is anchored at the same on-screen coordinates regardless
    of how the local libass build interprets Alignment+MarginV. ``y`` is
    computed from ``style.vertical_position`` (0.0 = top, 1.0 = bottom of
    frame).
    """
    chunks = _chunk_words(words, max_per_chunk=style.max_words_per_chunk)
    lines = [_build_header(style, render)]

    pos_x = render.width // 2
    pos_y = int(render.height * style.vertical_position)
    pos_tag = rf"{{\an5\pos({pos_x},{pos_y})}}"

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
                f"Pop,,0,0,0,,{pos_tag}{text}"
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
