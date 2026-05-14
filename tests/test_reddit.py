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


def _single_sub_cfg(**kw: Any) -> RedditConfig:
    """Pin a single subreddit + disable fresh-mode for unit-test determinism."""
    defaults: dict[str, Any] = dict(
        subreddit="AmItheAsshole",
        include_fresh=False,
        min_chars=500,
        max_chars=2000,
    )
    defaults.update(kw)
    return RedditConfig(**defaults)


def test_fetch_stories_filters_short_posts() -> None:
    cfg = _single_sub_cfg()
    payload = _payload(
        _post(id="1", selftext="too short"),
        _post(id="2", selftext="a" * 1000),
    )
    with _make_client(payload) as client:
        stories = fetch_stories(cfg, client=client)
    assert [s.id for s in stories] == ["2"]


def test_fetch_stories_filters_nsfw_and_stickied() -> None:
    cfg = _single_sub_cfg()
    payload = _payload(
        _post(id="ok", selftext="a" * 800),
        _post(id="nsfw", selftext="a" * 800, over_18=True),
        _post(id="stick", selftext="a" * 800, stickied=True),
    )
    with _make_client(payload) as client:
        stories = fetch_stories(cfg, client=client)
    assert [s.id for s in stories] == ["ok"]


def test_pick_best_returns_highest_score() -> None:
    cfg = _single_sub_cfg()
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


def test_pick_best_prefers_shock_titles_over_higher_score() -> None:
    """Wild premise titles (cheating, paternity, family-relation drama)
    should outrank a mildly higher-scoring boring AITA post."""
    cfg = _single_sub_cfg()
    payload = _payload(
        _post(
            id="boring",
            title="AITA for using too many semicolons in my code?",
            selftext="It was a normal day. " + ("filler " * 200),
            score=5000,
        ),
        _post(
            id="wild",
            title="My fianc\u00e9's brother sent me proof he's been cheating with my sister",
            selftext="I found out yesterday. " + ("filler " * 200),
            score=3000,
        ),
    )
    with _make_client(payload) as client:
        stories = fetch_stories(cfg, client=client)
    best = pick_best(stories)
    assert best is not None
    assert best.id == "wild"


def test_fetch_stories_raises_on_http_error_for_single_sub() -> None:
    """Single-subreddit calls preserve the original 'raise on HTTP error' semantics."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "rate limited"})

    cfg = _single_sub_cfg()
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        fetch_stories(cfg, client=client)


def test_fetch_stories_multi_sub_degrades_gracefully_on_error() -> None:
    """Multi-subreddit calls log + skip failed subs instead of erroring out."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "AmItheAsshole" in str(request.url):
            return httpx.Response(503, json={"error": "rate limited"})
        return httpx.Response(200, json=_payload(_post(id="ok", selftext="a" * 800)))

    cfg = RedditConfig(
        subreddits=["AmItheAsshole", "nosleep"],
        include_fresh=False,
        min_chars=500,
        max_chars=2000,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        stories = fetch_stories(cfg, client=client)
    assert [s.id for s in stories] == ["ok"]
    assert any("AmItheAsshole" in c for c in calls)
    assert any("nosleep" in c for c in calls)


def test_fetch_stories_include_fresh_pulls_top_and_new() -> None:
    """With include_fresh=True we hit both /top.json and /new.json."""
    sorts_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        # URL ends with /<sort>.json; pull out the sort.
        sort = str(request.url).split("/")[-1].split(".")[0]
        sorts_seen.append(sort)
        return httpx.Response(200, json=_payload(_post(id=f"id_{sort}", selftext="a" * 800)))

    cfg = RedditConfig(
        subreddit="AmItheAsshole",
        sort="top",
        include_fresh=True,
        min_chars=500,
        max_chars=2000,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        stories = fetch_stories(cfg, client=client)
    assert "top" in sorts_seen
    assert "new" in sorts_seen
    assert {s.id for s in stories} == {"id_top", "id_new"}
