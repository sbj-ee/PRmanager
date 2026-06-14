"""SQLite persistence layer for prmanager."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from prm.config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner      TEXT NOT NULL,
    name       TEXT NOT NULL,
    full_name  TEXT NOT NULL UNIQUE,
    added_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pulls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id       INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    number        INTEGER NOT NULL,
    title         TEXT,
    author        TEXT,
    state         TEXT,             -- open / closed
    merged        INTEGER DEFAULT 0,
    draft         INTEGER DEFAULT 0,
    url           TEXT,
    body          TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    -- local-only fields:
    review_status TEXT DEFAULT 'pending',  -- pending/approved/changes/commented
    synced_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (repo_id, number)
);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pull_id    INTEGER NOT NULL REFERENCES pulls(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tags (
    pull_id INTEGER NOT NULL REFERENCES pulls(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    PRIMARY KEY (pull_id, tag)
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# ----- repos -----

def add_repo(conn: sqlite3.Connection, owner: str, name: str) -> int:
    full = f"{owner}/{name}"
    conn.execute(
        "INSERT OR IGNORE INTO repos (owner, name, full_name) VALUES (?, ?, ?)",
        (owner, name, full),
    )
    row = conn.execute("SELECT id FROM repos WHERE full_name = ?", (full,)).fetchone()
    return int(row["id"])


def remove_repo(conn: sqlite3.Connection, full_name: str) -> bool:
    cur = conn.execute("DELETE FROM repos WHERE full_name = ?", (full_name,))
    return cur.rowcount > 0


def list_repos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.*, COUNT(p.id) AS pr_count
        FROM repos r LEFT JOIN pulls p ON p.repo_id = r.id
        GROUP BY r.id ORDER BY r.full_name
        """
    ).fetchall()


def get_repo(conn: sqlite3.Connection, full_name: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM repos WHERE full_name = ?", (full_name,)
    ).fetchone()


# ----- pulls -----

def upsert_pull(conn: sqlite3.Connection, repo_id: int, pr: dict) -> None:
    """Insert or update a PR, preserving local-only fields on update."""
    conn.execute(
        """
        INSERT INTO pulls
            (repo_id, number, title, author, state, merged, draft, url, body,
             created_at, updated_at, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT (repo_id, number) DO UPDATE SET
            title = excluded.title,
            author = excluded.author,
            state = excluded.state,
            merged = excluded.merged,
            draft = excluded.draft,
            url = excluded.url,
            body = excluded.body,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at,
            synced_at = datetime('now')
        """,
        (
            repo_id,
            pr["number"],
            pr["title"],
            pr["author"],
            pr["state"],
            int(pr["merged"]),
            int(pr["draft"]),
            pr["url"],
            pr["body"],
            pr["created_at"],
            pr["updated_at"],
        ),
    )


def find_pull(
    conn: sqlite3.Connection, number: int, repo_full: Optional[str] = None
) -> list[sqlite3.Row]:
    if repo_full:
        return conn.execute(
            """
            SELECT p.*, r.full_name AS repo FROM pulls p
            JOIN repos r ON r.id = p.repo_id
            WHERE p.number = ? AND r.full_name = ?
            """,
            (number, repo_full),
        ).fetchall()
    return conn.execute(
        """
        SELECT p.*, r.full_name AS repo FROM pulls p
        JOIN repos r ON r.id = p.repo_id
        WHERE p.number = ?
        """,
        (number,),
    ).fetchall()


def query_pulls(conn: sqlite3.Connection, filters: dict) -> list[sqlite3.Row]:
    where = []
    params: list = []

    if filters.get("repo"):
        where.append("r.full_name = ?")
        params.append(filters["repo"])
    if filters.get("state"):
        where.append("p.state = ?")
        params.append(filters["state"])
    if filters.get("author"):
        where.append("p.author = ?")
        params.append(filters["author"])
    if filters.get("review_status"):
        where.append("p.review_status = ?")
        params.append(filters["review_status"])
    if filters.get("draft") is not None:
        where.append("p.draft = ?")
        params.append(int(filters["draft"]))
    if filters.get("tag"):
        where.append(
            "p.id IN (SELECT pull_id FROM tags WHERE tag = ?)"
        )
        params.append(filters["tag"])

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT p.*, r.full_name AS repo,
               (SELECT group_concat(tag, ',') FROM tags WHERE pull_id = p.id) AS tags,
               (SELECT COUNT(*) FROM notes WHERE pull_id = p.id) AS note_count
        FROM pulls p JOIN repos r ON r.id = p.repo_id
        {clause}
        ORDER BY p.updated_at DESC
    """
    return conn.execute(sql, params).fetchall()


def set_review_status(conn: sqlite3.Connection, pull_id: int, status: str) -> None:
    conn.execute(
        "UPDATE pulls SET review_status = ? WHERE id = ?", (status, pull_id)
    )


# ----- notes & tags -----

def add_note(conn: sqlite3.Connection, pull_id: int, body: str) -> None:
    conn.execute("INSERT INTO notes (pull_id, body) VALUES (?, ?)", (pull_id, body))


def list_notes(conn: sqlite3.Connection, pull_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM notes WHERE pull_id = ? ORDER BY created_at", (pull_id,)
    ).fetchall()


def add_tag(conn: sqlite3.Connection, pull_id: int, tag: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO tags (pull_id, tag) VALUES (?, ?)", (pull_id, tag)
    )


def remove_tag(conn: sqlite3.Connection, pull_id: int, tag: str) -> bool:
    cur = conn.execute(
        "DELETE FROM tags WHERE pull_id = ? AND tag = ?", (pull_id, tag)
    )
    return cur.rowcount > 0


def list_tags(conn: sqlite3.Connection, pull_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT tag FROM tags WHERE pull_id = ? ORDER BY tag", (pull_id,)
    ).fetchall()
    return [r["tag"] for r in rows]
