"""Test helpers shared across modules."""

from __future__ import annotations


def make_pr(number: int, author: str = "alice", **overrides) -> dict:
    """Build a normalized PR dict like GitHubClient._normalize returns."""
    pr = {
        "number": number,
        "title": f"PR {number}",
        "author": author,
        "state": "open",
        "merged": False,
        "draft": False,
        "url": f"https://github.com/o/r/pull/{number}",
        "body": "body text",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }
    pr.update(overrides)
    return pr
