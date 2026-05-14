"""Reddit story source.

We use the unauthenticated public JSON endpoint
(``https://www.reddit.com/r/<sub>/top.json``) because it requires no OAuth
credentials for read-only access. This is sufficient for an MVP and avoids
forcing users to register a Reddit app.

The fetcher returns ``RedditStory`` objects already filtered for length,
NSFW, and stickied posts so downstream stages can be dumb.

Supports multi-subreddit fetching with ``include_fresh=True`` which mixes
``top`` and ``new`` listings so the pool always contains posts from the
last few hours.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from yt_shorts_factory.config import RedditConfig

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedditStory:
    """A single Reddit submission suitable for narration."""

    id: str
    subreddit: str
    title: str
    author: str
    body: str
    permalink: str
    score: int
    num_comments: int
    created_utc: float = 0.0

    @property
    def full_text(self) -> str:
        """The text that will be fed into TTS."""
        return f"{self.title}\n\n{self.body}".strip()


_REDDIT_BASE = "https://www.reddit.com"


def _build_url(subreddit: str, sort: str) -> str:
    return f"{_REDDIT_BASE}/r/{subreddit}/{sort}.json"


def _params(cfg: RedditConfig, sort: str) -> dict[str, str | int]:
    params: dict[str, str | int] = {"limit": cfg.limit, "raw_json": 1}
    # ``top`` accepts ``t`` (time filter); ``new``/``hot``/``rising`` ignore it.
    if sort == "top":
        params["t"] = cfg.time_filter
    return params


def _passes_filters(post: dict[str, Any], cfg: RedditConfig) -> bool:
    if cfg.skip_stickied and post.get("stickied"):
        return False
    if cfg.skip_nsfw and post.get("over_18"):
        return False
    selftext: str = post.get("selftext") or ""
    if not selftext.strip():
        return False
    length = len(selftext)
    return cfg.min_chars <= length <= cfg.max_chars


def _to_story(post: dict[str, Any]) -> RedditStory:
    return RedditStory(
        id=str(post["id"]),
        subreddit=str(post.get("subreddit", "")),
        title=html.unescape(str(post.get("title", "")).strip()),
        author=str(post.get("author", "unknown")),
        body=html.unescape(str(post.get("selftext", "")).strip()),
        permalink=f"{_REDDIT_BASE}{post.get('permalink', '')}",
        score=int(post.get("score", 0)),
        num_comments=int(post.get("num_comments", 0)),
        created_utc=float(post.get("created_utc", 0.0)),
    )


def _resolve_subreddits(cfg: RedditConfig) -> list[str]:
    """Return the subreddit pool: either the pinned single sub or the rotation list."""
    if cfg.subreddit:
        return [cfg.subreddit]
    return list(cfg.subreddits) or ["AmItheAsshole"]


def _resolve_sorts(cfg: RedditConfig) -> list[str]:
    """Sort modes to query. ``include_fresh`` mixes in ``new`` for last-hour posts."""
    sorts: list[str] = [cfg.sort]
    if cfg.include_fresh and "new" not in sorts:
        sorts.append("new")
    return sorts


def _fetch_one(
    subreddit: str,
    sort: str,
    cfg: RedditConfig,
    client: httpx.Client,
) -> list[dict[str, Any]]:
    """Return the raw post dicts for one subreddit/sort combination."""
    headers = {"User-Agent": cfg.user_agent}
    try:
        resp = client.get(
            _build_url(subreddit, sort),
            params=_params(cfg, sort),
            headers=headers,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        # Re-raise so callers / tests still see HTTP errors directly when
        # only one subreddit is requested. The multi-sub path wraps this
        # in ``fetch_stories`` and downgrades to a warning.
        raise
    payload = resp.json()
    children = payload.get("data", {}).get("children", [])
    return [c.get("data") or {} for c in children]


def fetch_stories(
    cfg: RedditConfig,
    *,
    client: httpx.Client | None = None,
) -> list[RedditStory]:
    """Fetch and filter stories across the configured subreddit pool.

    Single-subreddit + single-sort calls preserve the original 0.1 behavior;
    multi-subreddit batches walk the pool round-robin and merge results.
    """
    headers = {"User-Agent": cfg.user_agent}
    owns_client = client is None
    if client is None:
        client = httpx.Client(headers=headers, timeout=20.0, follow_redirects=True)
    try:
        return _fetch_via(cfg, client)
    finally:
        if owns_client:
            client.close()


def _fetch_via(cfg: RedditConfig, client: httpx.Client) -> list[RedditStory]:
    subs = _resolve_subreddits(cfg)
    sorts = _resolve_sorts(cfg)
    is_single = len(subs) == 1 and len(sorts) == 1

    seen_ids: set[str] = set()
    out: list[RedditStory] = []
    for sub in subs:
        for sort in sorts:
            try:
                posts = _fetch_one(sub, sort, cfg, client)
            except httpx.HTTPStatusError as exc:
                if is_single:
                    raise
                log.warning(
                    "Reddit %s/%s returned %s; skipping",
                    sub,
                    sort,
                    exc.response.status_code,
                )
                continue
            except (httpx.HTTPError, ValueError) as exc:
                if is_single:
                    raise
                log.warning("Reddit %s/%s fetch failed: %s", sub, sort, exc)
                continue
            for post in posts:
                pid = str(post.get("id", ""))
                if not pid or pid in seen_ids:
                    continue
                if not _passes_filters(post, cfg):
                    continue
                seen_ids.add(pid)
                out.append(_to_story(post))
    return out


def filter_processed(stories: list[RedditStory], processed_ids: Iterable[str]) -> list[RedditStory]:
    """Drop stories whose id is in ``processed_ids`` (used by dedup)."""
    block = set(processed_ids)
    if not block:
        return list(stories)
    return [s for s in stories if s.id not in block]


_SHOCK_TERMS: tuple[str, ...] = (
    # Infidelity / romantic betrayal
    "cheat", "cheating", "cheated", "affair", "mistress", "infidelit",
    "side chick", "betrayed",
    # Family / blood-relation drama
    "incest", "half-sister", "half sister", "half-brother", "half brother",
    "stepsister", "stepbrother", "stepdad", "stepmom",
    "biological father", "biological mother", "real father", "real mother",
    "secret child", "secret sibling", "adopted", "adoption",
    "paternity", "dna", "dna test", "23andme",
    # Body / pregnancy / hard reveals
    "pregnant", "miscarriage", "abortion", "still birth",
    # Direct relations weaponised
    "my husband", "my wife", "my fianc", "my girlfriend", "my boyfriend",
    "my ex", "my sister", "my brother", "my mother", "my father", "my mom",
    "my dad", "my stepmom", "my stepdad", "my mil", "my fil",
    # Money / will / revenge
    "will", "inheritance", "disinherited",
    # Discovery framing (often signals a twist)
    "found out", "i discovered", "i caught", "turns out",
    "secret", "lied", "lying", "betrayal", "manipulat",
)


def _shock_score(story: RedditStory) -> int:
    """Count how many shock-content keywords occur in the title + body lead.

    Used as a tiebreaker / multiplier in ``pick_best``. Wild titles like
    \"My fianc\u00e9's brother sent me proof he's been cheating\" get a much
    higher rank than generic ones like \"AITA for telling my sister not
    to buy things\".
    """
    haystack = f"{story.title}\n{story.body[:400]}".lower()
    return sum(1 for term in _SHOCK_TERMS if term in haystack)


def pick_best(stories: list[RedditStory]) -> RedditStory | None:
    """Pick the highest-ranked story from a filtered list.

    Ranking key (highest first):
      1. ``shock_score`` \u2014 count of wild/scandalous keyword matches in
         title + body lead. Prefers genuinely viral premises.
      2. ``score``       \u2014 raw Reddit upvotes.
      3. ``num_comments``\u2014 engagement tiebreaker.
      4. ``created_utc`` \u2014 freshness tiebreaker.
    """
    if not stories:
        return None
    return max(
        stories,
        key=lambda s: (_shock_score(s), s.score, s.num_comments, s.created_utc),
    )
