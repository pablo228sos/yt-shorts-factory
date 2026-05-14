"""Heuristic narrator-gender detection.

We pick a male or female TTS voice based on first-person markers in the
cleaned story text. No model, no API call — just regex patterns that have
held up well on Reddit-story corpora.

Returns one of ``"male"``, ``"female"``, or ``"unknown"``. ``"unknown"``
lets the caller keep whatever default voice was already configured.

The signals we look for (highest-confidence first):

- Explicit ``(25M)`` / ``(F32)`` / ``25M`` / ``F32`` Reddit shorthand.
- First-person identity statements: ``I'm a 24F``, ``I'm a 30-year-old man``,
  ``as a guy``, ``as a woman``.
- Relationship markers: ``my wife``, ``my husband``, ``my girlfriend``,
  ``my boyfriend`` (only weighted when no explicit identity signal exists).

We resolve conflicts by tallying signals with weights and picking the
side with the higher score; ties go to ``"unknown"``.
"""

from __future__ import annotations

import re
from typing import Literal

Gender = Literal["male", "female", "unknown"]


# (regex, weight, gender)
_PATTERNS: list[tuple[re.Pattern[str], int, Gender]] = [
    # Reddit shorthand inside parens. Already partially expanded by the
    # cleaner but the raw forms still appear in some posts.
    (re.compile(r"\bI[' ]?m\s+\(?(\d{2})\s*M\)?\b", re.IGNORECASE), 4, "male"),
    (re.compile(r"\bI[' ]?m\s+\(?(\d{2})\s*F\)?\b", re.IGNORECASE), 4, "female"),
    (re.compile(r"\b\(\s*M\s*\d{2}\s*\)", re.IGNORECASE), 4, "male"),
    (re.compile(r"\b\(\s*F\s*\d{2}\s*\)", re.IGNORECASE), 4, "female"),
    (re.compile(r"\b\(\s*\d{2}\s*M\s*\)", re.IGNORECASE), 4, "male"),
    (re.compile(r"\b\(\s*\d{2}\s*F\s*\)", re.IGNORECASE), 4, "female"),

    # Post-cleaner expansion (cleaner.py turns (25F) into "a 25-year-old female,").
    (re.compile(r"\bI[' ]?m\s+a\s+\d{1,2}-year-old\s+male\b", re.IGNORECASE), 5, "male"),
    (re.compile(r"\bI[' ]?m\s+a\s+\d{1,2}-year-old\s+female\b", re.IGNORECASE), 5, "female"),
    (re.compile(r"\ba\s+\d{1,2}-year-old\s+male\b", re.IGNORECASE), 3, "male"),
    (re.compile(r"\ba\s+\d{1,2}-year-old\s+female\b", re.IGNORECASE), 3, "female"),

    # Direct identity statements.
    (re.compile(r"\bI[' ]?m\s+a\s+(?:guy|man|dude|father|dad)\b", re.IGNORECASE), 4, "male"),
    (re.compile(r"\bI[' ]?m\s+a\s+(?:woman|girl|mom|mother|wife)\b", re.IGNORECASE), 4, "female"),
    (re.compile(r"\bas\s+a\s+(?:guy|man|father|dad)\b", re.IGNORECASE), 3, "male"),
    (re.compile(r"\bas\s+a\s+(?:woman|girl|mom|mother|wife)\b", re.IGNORECASE), 3, "female"),

    # Relationship markers (lower weight, only narrator's perspective).
    (re.compile(r"\bmy\s+(?:wife|girlfriend|gf)\b", re.IGNORECASE), 2, "male"),
    (re.compile(r"\bmy\s+(?:husband|boyfriend|bf)\b", re.IGNORECASE), 2, "female"),
    (re.compile(r"\bmy\s+(?:dear\s+wife|DW)\b"), 2, "male"),
    (re.compile(r"\bmy\s+(?:dear\s+husband|DH)\b"), 2, "female"),
]


def detect_gender(text: str) -> Gender:
    """Score gender signals in ``text``; return ``male`` / ``female`` / ``unknown``."""
    if not text:
        return "unknown"
    scores: dict[Gender, int] = {"male": 0, "female": 0, "unknown": 0}
    for pattern, weight, gender in _PATTERNS:
        for _ in pattern.finditer(text):
            scores[gender] += weight
    if scores["male"] == 0 and scores["female"] == 0:
        return "unknown"
    if scores["male"] == scores["female"]:
        return "unknown"
    return "male" if scores["male"] > scores["female"] else "female"


def pick_voice(
    text: str,
    *,
    male_voices: list[str],
    female_voices: list[str],
    fallback: str,
    rotation_seed: int = 0,
) -> tuple[str, Gender]:
    """Return ``(voice_name, detected_gender)``.

    ``rotation_seed`` is used to cycle through ``male_voices`` / ``female_voices``
    deterministically so back-to-back batch outputs don't always pick the
    first voice in the list.
    """
    gender = detect_gender(text)
    pool: list[str]
    if gender == "male":
        pool = list(male_voices) or [fallback]
    elif gender == "female":
        pool = list(female_voices) or [fallback]
    else:
        return fallback, "unknown"
    return pool[rotation_seed % len(pool)], gender
