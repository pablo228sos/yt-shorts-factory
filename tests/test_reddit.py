from __future__ import annotations

from typing import Any

import httpx
import pytest

from yt_shorts_factory.config import RedditConfig
from yt_shorts_factory.sources.reddit import fetch_stories, pick_best


def _post(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "abc",
        "subreddit": "AmItheAsshole",
        "title": "AITA for using mocks?",
        "author": "tester",
        "selftext": "a" * 800,
        "permalink": "/r/AmItheAsshole/comments/abc/test/",
        "score": 1234,
        "num_comments": 50,
        "stickied": False,
        "over_18": False,
    }
    base.update(overrides)
    return base


def _payload(*posts: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"children": [{"data": p} for p in posts]}}


def _make_client(payload: dict[str, Any]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def test_fetch_stories_filters_short_posts() -> None:
    cfg = RedditConfig(min_chars=500, max_chars=2000)
    payload = _payload(
        _post(id="1", selftext="too short"),
        _post(id="2", selftext="a" * 1000),
    )
    with _make_client(payload) as client:
        stories = fetch_stories(cfg, client=client)
    assert [s.id for s in stories] == ["2"]


def test_fetch_stories_filters_nsfw_and_stickied() -> None:
    cfg = RedditConfig(min_chars=500, max_chars=2000)
    payload = _payload(
        _post(id="ok", selftext="a" * 800),
        _post(id="nsfw", selftext="a" * 800, over_18=True),
        _post(id="stick", selftext="a" * 800, stickied=True),
    )
    with _make_client(payload) as client:
        stories = fetch_stories(cfg, client=client)
    assert [s.id for s in stories] == ["ok"]


def test_pick_best_returns_highest_score() -> None:
    cfg = RedditConfig(min_chars=500, max_chars=2000)
    payload = _payload(
        _post(id="lo", selftext="a" * 800, score=10),
        _post(id="hi", selftext="a" * 800, score=999),
        _post(id="mid", selftext="a" * 800, score=200),
    )
    with _make_client(payload) as client:
        stories = fetch_stories(cfg, client=client)
    best = pick_best(stories)
    assert best is not None
    assert best.id == "hi"


def test_pick_best_returns_none_for_empty() -> None:
    assert pick_best([]) is None


def test_fetch_stories_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "rate limited"})

    cfg = RedditConfig()
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        fetch_stories(cfg, client=client)
