"""Clean and normalize Reddit-story text so TTS doesn't trip over it.

Goals:
- Strip markdown, urls, edit blocks, signatures.
- Expand subreddit jargon (AITA, NTA, YTA, ...) so TTS reads them as words.
- Replace numeric ages like "I (25F)" with "I'm a 25-year-old female".
- Censor common slurs that would get YouTube to demonetize the video.
"""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://\S+")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_EDIT_RE = re.compile(
    r"(?im)^(?:edit\s*\d*|update\s*\d*|tl;dr|tldr|eta)\s*[:\-].*?(?=\n\n|\Z)",
    re.DOTALL,
)
_MULTISPACE_RE = re.compile(r"[ \t]+")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")
_AGE_GENDER_RE = re.compile(r"\((\d{1,2})\s*([MmFf])\)")
_GENDER_AGE_RE = re.compile(r"\(([MmFf])\s*(\d{1,2})\)")

# Subreddit-jargon that TTS will otherwise read as letters.
# Case-sensitive: only matches when the user typed it in ALL CAPS, so we
# don't expand ordinary words like "so", "op", "info".
_ABBREVIATIONS_CS: dict[str, str] = {
    "AITA": "Am I the asshole",
    "WIBTA": "Would I be the asshole",
    "NTA": "Not the asshole.",
    "YTA": "You're the asshole.",
    "ESH": "Everyone sucks here.",
    "NAH": "No assholes here.",
    "INFO": "Need more info.",
    "OP": "the original poster",
    "SO": "significant other",
    "MIL": "mother-in-law",
    "FIL": "father-in-law",
    "SIL": "sister-in-law",
    "BIL": "brother-in-law",
    "DH": "dear husband",
    "DW": "dear wife",
    "BF": "boyfriend",
    "GF": "girlfriend",
    "LO": "little one",
    "DD": "daughter",
    "DS": "son",
}

# Case-insensitive: lowercase-typed shorthand that's safe to expand anywhere.
_ABBREVIATIONS_CI: dict[str, str] = {
    "tbh": "to be honest",
    "imo": "in my opinion",
    "imho": "in my honest opinion",
    "fyi": "for your information",
    "irl": "in real life",
    "ngl": "not gonna lie",
}

# Words that trigger YouTube demonetization. Censor with asterisks so TTS
# either skips them or reads them as benign sounds.
_BAD_WORDS = {
    "fuck",
    "fucking",
    "fucked",
    "shit",
    "bitch",
    "asshole",
    "cunt",
    "dick",
}


_ABBR_CS_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _ABBREVIATIONS_CS) + r")\b",
)
_ABBR_CI_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _ABBREVIATIONS_CI) + r")\b",
    re.IGNORECASE,
)


def _expand_abbreviations(text: str) -> str:
    text = _ABBR_CS_RE.sub(lambda m: _ABBREVIATIONS_CS[m.group(0)], text)
    text = _ABBR_CI_RE.sub(lambda m: _ABBREVIATIONS_CI[m.group(0).lower()], text)
    return text


def _expand_age_gender(text: str) -> str:
    def repl_ag(match: re.Match[str]) -> str:
        age, gender = match.group(1), match.group(2).upper()
        word = "female" if gender == "F" else "male"
        return f", a {age}-year-old {word},"

    def repl_ga(match: re.Match[str]) -> str:
        gender, age = match.group(1).upper(), match.group(2)
        word = "female" if gender == "F" else "male"
        return f", a {age}-year-old {word},"

    text = _AGE_GENDER_RE.sub(repl_ag, text)
    text = _GENDER_AGE_RE.sub(repl_ga, text)
    return text


def _censor_profanity(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        word = match.group(0)
        if len(word) <= 2:
            return word
        return word[0] + "*" * (len(word) - 2) + word[-1]

    pattern = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in _BAD_WORDS) + r")\b",
        re.IGNORECASE,
    )
    return pattern.sub(repl, text)


def clean_story(text: str, *, censor: bool = True) -> str:
    """Return a TTS-friendly version of `text`."""
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n")
    cleaned = _MD_LINK_RE.sub(r"\1", cleaned)
    cleaned = _URL_RE.sub("", cleaned)
    cleaned = _EDIT_RE.sub("", cleaned)
    cleaned = _expand_age_gender(cleaned)
    if censor:
        # Censor before expanding abbreviations so the "asshole" inside
        # expansions like "Am I the asshole" survives unmolested.
        cleaned = _censor_profanity(cleaned)
    cleaned = _expand_abbreviations(cleaned)
    cleaned = _MULTISPACE_RE.sub(" ", cleaned)
    cleaned = _MULTINEWLINE_RE.sub("\n\n", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r",{2,}", ",", cleaned)
    return cleaned.strip()


def make_hook(title: str) -> str:
    """A first-line hook that boosts retention in the first 3 seconds."""
    title = title.strip().rstrip(".?!")
    if not title:
        return ""
    if title.lower().startswith(("aita", "wibta")):
        return "Wait until you hear this one."
    return "You won't believe what happened."
