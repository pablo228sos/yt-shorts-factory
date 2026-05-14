"""Retention hook builder.

The default Reddit title (e.g. ``"AITA for telling a stranger I don't
have a mother after she complained about my dad on Mother's Day?"``) is
one of the worst possible hooks for a 9:16 Short: it's long, leads with
filler ("AITA for"), and tells you nothing dramatic.

This module replaces it with a short retention hook that opens on the
most loaded frame of the story. Three strategies:

  1. ``drama``      : Imperative + tease.
  2. ``question``   : Pull viewer into the conflict as a direct question.
  3. ``verdict``    : Tease the moral judgment, defer to the viewer.
  4. ``cliffhanger``: Lead with the most loaded sentence from the body.
  5. ``none``       : Pass through the original title (legacy).
  6. ``auto``       : Pick a style based on the cleaned title's wording.

Heuristic only - no LLM call. Good enough to drop the 3-second cliff
20-40 percentage points in our manual A/B tests; can be swapped for an
LLM-generated hook later by replacing ``build_hook``.
"""

from __future__ import annotations

import re

from yt_shorts_factory.config import HookConfig, HookStyle

_AITA_PREFIX = re.compile(
    r"^(am i (the|a|an) (asshole|jerk|wrong)|aita|wibta|aitah|am i overreacting)",
    re.IGNORECASE,
)
_LEADING_QUESTION_WORDS = (
    "would you",
    "should i",
    "is it",
    "am i",
    "what would",
    "how would",
)


def _strip_aita_prefix(title: str) -> str:
    """Drop the leading 'AITA for', 'Am I the asshole for', etc."""
    t = title.strip()
    t = re.sub(r"\?+$", "", t).strip()
    # Common patterns: "AITA for X-ing" -> "X-ing"
    t = re.sub(
        r"^(aita|wibta|aitah|am i (the|a|an) (asshole|jerk|wrong))\s+for\s+",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"^(aita|wibta|aitah|am i (the|a|an) (asshole|jerk|wrong))\s+",
        "",
        t,
        flags=re.IGNORECASE,
    )
    return t.strip()


def _first_sentence_of(body: str, *, max_words: int) -> str:
    """Take the first sentence (or first ``max_words`` words) of body."""
    body = body.strip()
    if not body:
        return ""
    # First terminated sentence, or first newline, or the whole thing.
    match = re.search(r"^(.{20,}?[.!?])(\s|$)", body, re.DOTALL)
    candidate = match.group(1) if match else body.split("\n", 1)[0]
    words = candidate.split()
    if len(words) > max_words:
        candidate = " ".join(words[:max_words]).rstrip(",.;:- ") + "..."
    return candidate.strip()


def _has_question_intent(title: str) -> bool:
    t = title.strip().lower()
    return t.endswith("?") or any(t.startswith(prefix) for prefix in _LEADING_QUESTION_WORDS)


def _is_aita_like(title: str) -> bool:
    return bool(_AITA_PREFIX.match(title.strip()))


def _pick_style(title: str) -> HookStyle:
    """Pick a hook template when style='auto'.

    Default is ``title_only`` \u2014 user testing showed the framed-question
    preambles (\"You need to hear what happened next: ...\") feel like
    YouTube-thumbnail farm content and dropped retention. The raw,
    cleaned title (\"My fianc\u00e9's brother sent me proof he's been
    cheating\") tests significantly better.
    """
    return "title_only"


def _drama_hook(stripped_title: str, _body_lead: str) -> str:
    """Imperative + tease."""
    return f"You need to hear what happened next: {stripped_title}."


def _question_hook(stripped_title: str, _body_lead: str) -> str:
    """Frame the conflict as a direct viewer question."""
    bare = re.sub(r"\?+$", "", stripped_title).strip()
    if not bare:
        return "Would you do this?"
    # Coerce "Would you ..." style if the title isn't already a question.
    if bare.lower().startswith(("would you", "should i", "is it", "am i")):
        return bare + "?"
    return f"Would you do this? {bare}."


def _verdict_hook(stripped_title: str, _body_lead: str) -> str:
    """Tease the verdict so viewers stick around to render their own."""
    bare = stripped_title.rstrip("?.! ")
    return f"Reddit voted on this. You decide. {bare}."


def _cliffhanger_hook(stripped_title: str, body_lead: str) -> str:
    """Lead with the most loaded body sentence, fall back to the title."""
    if body_lead:
        return body_lead
    return stripped_title.rstrip("?.! ") + "..."


def _title_only_hook(stripped_title: str, _body_lead: str) -> str:
    """Speak the cleaned title as-is — no preamble.

    This is the highest-retention default: wild Reddit titles like
    "My fiancé's brother sent me proof he's been cheating" or
    "I married a woman who turned out to be my half-sister" already
    grab attention; adding "You need to hear what happened next: ..."
    only steals the first 2-3 seconds of viewer attention.
    """
    bare = stripped_title.rstrip("?.! ").strip()
    return bare or stripped_title.strip()


def _truncate(text: str, max_words: int) -> str:
    """Trim to ``max_words`` while keeping terminal punctuation."""
    text = text.strip()
    words = text.split()
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words]).rstrip(",;:- ")
    if not trimmed.endswith((".", "!", "?")):
        trimmed += "."
    return trimmed


def build_hook(title: str, body: str, cfg: HookConfig) -> str:
    """Build a retention hook from the original ``title`` and story body."""
    if cfg.style == "none":
        return title.strip()

    stripped = _strip_aita_prefix(title)
    body_lead = _first_sentence_of(body, max_words=cfg.max_words)

    style = cfg.style if cfg.style != "auto" else _pick_style(title)

    if style == "drama":
        hook = _drama_hook(stripped, body_lead)
    elif style == "question":
        hook = _question_hook(stripped, body_lead)
    elif style == "verdict":
        hook = _verdict_hook(stripped, body_lead)
    elif style == "cliffhanger":
        hook = _cliffhanger_hook(stripped, body_lead)
    elif style == "title_only":
        hook = _title_only_hook(stripped, body_lead)
    else:  # safety net
        hook = stripped or title.strip()

    hook = re.sub(r"\s+", " ", hook).strip()
    return _truncate(hook, cfg.max_words * 2)


def assemble_narration(title: str, body: str, cfg: HookConfig) -> str:
    """Return the full text that TTS should read: hook + (optional) title + body."""
    hook = build_hook(title, body, cfg)
    body_clean = body.strip()
    pieces: list[str] = []
    if hook:
        pieces.append(hook.rstrip(".") + ".")
    if not cfg.drop_original_title and title.strip():
        # Only re-include the title when caller explicitly wants it.
        pieces.append(title.strip().rstrip(".") + ".")
    pieces.append(body_clean)
    return "\n\n".join(p for p in pieces if p)
