from prm import db

from helpers import make_pr


def test_add_and_list_repos():
    with db.connect() as conn:
        rid = db.add_repo(conn, "octocat", "Hello-World")
        # idempotent: same full_name returns same id
        assert db.add_repo(conn, "octocat", "Hello-World") == rid
        rows = db.list_repos(conn)
    assert len(rows) == 1
    assert rows[0]["full_name"] == "octocat/Hello-World"
    assert rows[0]["pr_count"] == 0


def test_remove_repo_cascades_pulls():
    with db.connect() as conn:
        rid = db.add_repo(conn, "o", "r")
        db.upsert_pull(conn, rid, make_pr(1))
        assert db.remove_repo(conn, "o/r") is True
        assert db.find_pull(conn, 1) == []
        # removing again reports nothing deleted
        assert db.remove_repo(conn, "o/r") is False


def test_upsert_updates_remote_fields_but_preserves_local():
    with db.connect() as conn:
        rid = db.add_repo(conn, "o", "r")
        db.upsert_pull(conn, rid, make_pr(7, title="old"))
        pr = db.find_pull(conn, 7)[0]
        # set local-only state
        db.set_review_status(conn, pr["id"], "approved")
        db.add_tag(conn, pr["id"], "urgent")
        db.add_note(conn, pr["id"], "a note")

        # re-sync with changed remote fields
        db.upsert_pull(conn, rid, make_pr(7, title="new title", state="closed"))
        pr2 = db.find_pull(conn, 7)[0]

    assert pr2["title"] == "new title"
    assert pr2["state"] == "closed"
    # local fields survived the upsert
    assert pr2["review_status"] == "approved"


def test_query_pulls_filters():
    with db.connect() as conn:
        r1 = db.add_repo(conn, "o", "one")
        r2 = db.add_repo(conn, "o", "two")
        db.upsert_pull(conn, r1, make_pr(1, author="alice", state="open"))
        db.upsert_pull(conn, r1, make_pr(2, author="bob", state="closed"))
        db.upsert_pull(conn, r2, make_pr(3, author="alice", draft=True, state="closed"))
        bob = db.find_pull(conn, 2)[0]
        db.add_tag(conn, bob["id"], "wip")

        assert len(db.query_pulls(conn, {})) == 3
        assert len(db.query_pulls(conn, {"repo": "o/one"})) == 2
        assert len(db.query_pulls(conn, {"state": "open"})) == 1
        assert len(db.query_pulls(conn, {"author": "alice"})) == 2
        # substring + case-insensitive
        assert len(db.query_pulls(conn, {"author": "ALIC"})) == 2
        assert len(db.query_pulls(conn, {"author": "bo"})) == 1
        # exact match is stricter
        assert len(db.query_pulls(conn, {"author_exact": "alice"})) == 2
        assert len(db.query_pulls(conn, {"author_exact": "alic"})) == 0
        assert len(db.query_pulls(conn, {"tag": "wip"})) == 1
        assert len(db.query_pulls(conn, {"draft": False})) == 2


def test_query_pulls_order():
    with db.connect() as conn:
        rid = db.add_repo(conn, "o", "r")
        db.upsert_pull(conn, rid, make_pr(1, created_at="2026-03-01T00:00:00Z"))
        db.upsert_pull(conn, rid, make_pr(2, created_at="2026-01-01T00:00:00Z"))
        db.upsert_pull(conn, rid, make_pr(3, created_at="2026-02-01T00:00:00Z"))
        oldest_first = db.query_pulls(conn, {}, order="created-asc")
    assert [r["number"] for r in oldest_first] == [2, 3, 1]


def test_query_pulls_label_and_assignee():
    with db.connect() as conn:
        rid = db.add_repo(conn, "o", "r")
        db.upsert_pull(conn, rid, make_pr(1, labels="bug,go", assignees="alice"))
        db.upsert_pull(conn, rid, make_pr(2, labels="golang", assignees="bob"))
        db.upsert_pull(conn, rid, make_pr(3))

        # exact-token membership: "go" must not match "golang"
        assert [r["number"] for r in db.query_pulls(conn, {"labels": ["go"]})] == [1]
        assert [r["number"] for r in db.query_pulls(conn, {"labels": ["golang"]})] == [2]
        # case-insensitive
        assert len(db.query_pulls(conn, {"labels": ["GO"]})) == 1
        # multiple labels are ANDed
        assert [r["number"] for r in db.query_pulls(conn, {"labels": ["bug", "go"]})] == [1]
        assert db.query_pulls(conn, {"labels": ["bug", "docs"]}) == []
        # assignee membership
        assert [r["number"] for r in db.query_pulls(conn, {"assignee": "alice"})] == [1]
        assert len(db.query_pulls(conn, {"assignee": "ALICE"})) == 1


def test_notes_and_tags():
    with db.connect() as conn:
        rid = db.add_repo(conn, "o", "r")
        db.upsert_pull(conn, rid, make_pr(1))
        pid = db.find_pull(conn, 1)[0]["id"]

        db.add_note(conn, pid, "first")
        db.add_note(conn, pid, "second")
        assert [n["body"] for n in db.list_notes(conn, pid)] == ["first", "second"]

        db.add_tag(conn, pid, "x")
        db.add_tag(conn, pid, "x")  # dedup
        db.add_tag(conn, pid, "y")
        assert db.list_tags(conn, pid) == ["x", "y"]
        assert db.remove_tag(conn, pid, "x") is True
        assert db.remove_tag(conn, pid, "missing") is False
        assert db.list_tags(conn, pid) == ["y"]


def test_find_pull_scopes_by_repo():
    with db.connect() as conn:
        r1 = db.add_repo(conn, "o", "one")
        r2 = db.add_repo(conn, "o", "two")
        db.upsert_pull(conn, r1, make_pr(5))
        db.upsert_pull(conn, r2, make_pr(5))
        assert len(db.find_pull(conn, 5)) == 2
        assert len(db.find_pull(conn, 5, "o/one")) == 1
