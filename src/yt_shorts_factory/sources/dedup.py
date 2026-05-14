"""Persistent dedup of already-rendered Reddit posts.

A tiny SQLite table that maps ``post_id -> rendered_at``. The pipeline
calls ``mark_rendered`` after every successful generation, and
``fetch_stories`` filters out anything already in the table.

This keeps a long-running ``batch --count 50`` from cycling through the
same five hot AITA posts that always sit at the top of /day.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from yt_shorts_factory.config import DedupConfig

log = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_posts (
    post_id    TEXT PRIMARY KEY,
    subreddit  TEXT NOT NULL,
    title      TEXT NOT NULL,
    rendered_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_processed_subreddit
    ON processed_posts(subreddit);
"""


@contextmanager
def _connect(cfg: DedupConfig) -> Iterator[sqlite3.Connection]:
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cfg.db_path))
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        yield conn
    finally:
        conn.close()


def is_processed(post_id: str, cfg: DedupConfig) -> bool:
    """True when ``post_id`` has already been rendered."""
    if not cfg.enabled:
        return False
    with _connect(cfg) as conn:
        cur = conn.execute(
            "SELECT 1 FROM processed_posts WHERE post_id = ? LIMIT 1",
            (post_id,),
        )
        return cur.fetchone() is not None


def filter_unprocessed(
    post_ids: Iterable[str], cfg: DedupConfig
) -> set[str]:
    """Return the subset of ``post_ids`` that have NOT been rendered yet."""
    if not cfg.enabled:
        return set(post_ids)
    ids = list(post_ids)
    if not ids:
        return set()
    with _connect(cfg) as conn:
        placeholders = ",".join("?" * len(ids))
        cur = conn.execute(
            f"SELECT post_id FROM processed_posts WHERE post_id IN ({placeholders})",
            ids,
        )
        already = {row[0] for row in cur.fetchall()}
    return set(ids) - already


def mark_rendered(
    post_id: str, subreddit: str, title: str, cfg: DedupConfig
) -> None:
    """Insert ``post_id`` into the processed table (no-op on conflict)."""
    if not cfg.enabled:
        return
    with _connect(cfg) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_posts(post_id, subreddit, title) "
            "VALUES (?, ?, ?)",
            (post_id, subreddit, title),
        )
        conn.commit()


def count_processed(cfg: DedupConfig) -> int:
    """Number of distinct posts the pipeline has ever rendered."""
    if not cfg.enabled:
        return 0
    if not Path(cfg.db_path).exists():
        return 0
    with _connect(cfg) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM processed_posts")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def reset(cfg: DedupConfig) -> None:
    """Drop the dedup database (for tests / manual reset)."""
    if cfg.db_path.exists():
        cfg.db_path.unlink()
