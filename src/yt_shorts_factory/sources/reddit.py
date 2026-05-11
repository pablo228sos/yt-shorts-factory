"""Reddit story source.

We use the unauthenticated public JSON endpoint
(`https://www.reddit.com/r/<sub>/top.json`) because it requires no OAuth
credentials for read-only access. This is sufficient for an MVP and avoids
forcing users to register a Reddit app.

The fetcher returns `RedditStory` objects already filtered for length,
NSFW, and stickied posts so downstream stages can be dumb.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

import httpx

from yt_shorts_factory.config import RedditConfig


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

    @property
    def full_text(self) -> str:
        """The text that will be fed into TTS."""
        return f"{self.title}\n\n{self.body}".strip()


_REDDIT_BASE = "https://www.reddit.com"


def _build_url(cfg: RedditConfig) -> str:
    return f"{_REDDIT_BASE}/r/{cfg.subreddit}/top.json"


def _params(cfg: RedditConfig) -> dict[str, str | int]:
    return {"t": cfg.time_filter, "limit": cfg.limit, "raw_json": 1}


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
    )


def fetch_stories(
    cfg: RedditConfig,
    *,
    client: httpx.Client | None = None,
) -> list[RedditStory]:
    """Fetch and filter the latest top stories for `cfg.subreddit`."""
    headers = {"User-Agent": cfg.user_agent}
    owns_client = client is None
    if client is None:
        client = httpx.Client(headers=headers, timeout=20.0, follow_redirects=True)
    try:
        resp = client.get(_build_url(cfg), params=_params(cfg), headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if owns_client:
            client.close()

    children = payload.get("data", {}).get("children", [])
    stories: list[RedditStory] = []
    for child in children:
        post = child.get("data") or {}
        if not _passes_filters(post, cfg):
            continue
        stories.append(_to_story(post))
    return stories


def pick_best(stories: list[RedditStory]) -> RedditStory | None:
    """Pick the highest-scoring story from a filtered list."""
    if not stories:
        return None
    return max(stories, key=lambda s: (s.score, s.num_comments))
