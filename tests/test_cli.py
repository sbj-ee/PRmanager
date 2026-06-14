from typer.testing import CliRunner

from prm import cli, config, db
from prm.cli import app

from helpers import make_pr

runner = CliRunner()


def run(*args, **kwargs):
    return runner.invoke(app, list(args), **kwargs)


def text(res):
    """Combined stdout+stderr; error output uses a separate stderr console."""
    try:
        err = res.stderr or ""
    except ValueError:
        err = ""
    return (res.stdout or "") + err


def seed(repo="o/r", numbers=(1,), **pr_kwargs):
    owner, name = repo.split("/")
    with db.connect() as conn:
        rid = db.add_repo(conn, owner, name)
        for n in numbers:
            db.upsert_pull(conn, rid, make_pr(n, **pr_kwargs))


def test_track_and_repos():
    assert run("track", "octocat/Hello-World").exit_code == 0
    res = run("repos")
    assert res.exit_code == 0
    assert "octocat/Hello-World" in res.stdout


def test_track_rejects_bad_repo():
    res = run("track", "not-a-repo")
    assert res.exit_code == 1
    assert "owner/name" in text(res)


def test_list_filters_and_note_marker():
    seed(numbers=(1, 2), author="alice")
    with db.connect() as conn:
        pid = db.find_pull(conn, 1)[0]["id"]
        db.add_note(conn, pid, "hi")
    res = run("list", "--author", "alice")
    assert res.exit_code == 0
    assert "PR 1" in res.stdout and "PR 2" in res.stdout
    # note marker emoji rendered for the PR that has a note
    assert "📝" in res.stdout


def test_note_tag_review_flow():
    seed()
    assert run("note", "1", "look here").exit_code == 0
    assert run("tag", "1", "urgent").exit_code == 0
    assert run("review", "1", "approved").exit_code == 0

    res = run("show", "1")
    assert "look here" in res.stdout
    assert "urgent" in res.stdout
    assert "approved" in res.stdout


def test_renders_markup_like_content_without_crashing():
    # PR fields are untrusted: brackets must not be parsed as Rich markup.
    seed(numbers=(1,), author="dependabot[bot]",
         title="bump [golang.org/x/crypto] from 1 to 2",
         body="Bumps [pkg](url) from [a] to [b].")
    with db.connect() as conn:
        pid = db.find_pull(conn, 1)[0]["id"]
        db.add_note(conn, pid, "see [section] of docs")

    res_list = run("list")
    assert res_list.exit_code == 0
    assert "golang.org/x/crypto" in res_list.stdout

    res_show = run("show", "1")
    assert res_show.exit_code == 0
    assert "dependabot[bot]" in res_show.stdout
    assert "[section]" in res_show.stdout


def test_review_rejects_bad_status():
    seed()
    res = run("review", "1", "bogus")
    assert res.exit_code == 1


def test_show_missing_pr():
    res = run("show", "999")
    assert res.exit_code == 1
    assert "no PR #999" in text(res)


def test_ambiguous_pr_requires_repo():
    seed(repo="o/one", numbers=(5,))
    seed(repo="o/two", numbers=(5,))
    res = run("show", "5")
    assert res.exit_code == 1
    assert "multiple repos" in text(res)
    # disambiguation works
    assert run("show", "5", "--repo", "o/one").exit_code == 0


def test_tag_remove():
    seed()
    run("tag", "1", "x")
    assert run("tag", "1", "x", "--remove").exit_code == 0
    res = run("tag", "1", "missing", "--remove")
    assert res.exit_code == 1


def test_sync_pulls_from_github(monkeypatch):
    class FakeClient:
        def __init__(self, token):
            pass

        def fetch_pulls(self, owner, name, state="all", since=None):
            return [make_pr(10), make_pr(11)]

    monkeypatch.setattr(cli, "GitHubClient", FakeClient)
    monkeypatch.setattr(config, "resolve_token", lambda: "tok")

    res = run("sync", "octocat/Hello-World")
    assert res.exit_code == 0
    assert "Synced 2 PRs" in res.stdout
    with db.connect() as conn:
        assert len(db.find_pull(conn, 10)) == 1


def _watermark_recording_client(returns):
    """A fake client that records the `since` it was called with."""
    calls = []

    class FakeClient:
        def __init__(self, token):
            pass

        def fetch_pulls(self, owner, name, state="all", since=None):
            calls.append(since)
            return returns

    return FakeClient, calls


def test_incremental_sync_uses_watermark(monkeypatch):
    monkeypatch.setattr(config, "resolve_token", lambda: "tok")
    Fake, calls = _watermark_recording_client(
        [make_pr(1, updated_at="2026-03-01T00:00:00Z")]
    )
    monkeypatch.setattr(cli, "GitHubClient", Fake)

    assert run("sync", "o/r").exit_code == 0          # first sync: no watermark
    assert run("sync", "o/r").exit_code == 0          # second: passes watermark
    assert calls == [None, "2026-03-01T00:00:00Z"]


def test_full_flag_ignores_watermark(monkeypatch):
    monkeypatch.setattr(config, "resolve_token", lambda: "tok")
    Fake, calls = _watermark_recording_client(
        [make_pr(1, updated_at="2026-03-01T00:00:00Z")]
    )
    monkeypatch.setattr(cli, "GitHubClient", Fake)

    run("sync", "o/r")
    run("sync", "o/r", "--full")
    assert calls == [None, None]


def test_state_change_forces_full_sync(monkeypatch):
    monkeypatch.setattr(config, "resolve_token", lambda: "tok")
    Fake, calls = _watermark_recording_client(
        [make_pr(1, updated_at="2026-03-01T00:00:00Z")]
    )
    monkeypatch.setattr(cli, "GitHubClient", Fake)

    run("sync", "o/r", "--state", "open")
    run("sync", "o/r", "--state", "all")   # different state -> no watermark reuse
    assert calls == [None, None]


def test_list_mine_uses_login(monkeypatch):
    seed(numbers=(1,), author="sbj-ee")
    seed(repo="o/r2", numbers=(2,), author="someoneelse")
    monkeypatch.setattr(config, "cached_login", lambda: "sbj-ee")

    res = run("list", "--mine")
    assert res.exit_code == 0
    assert "PR 1" in res.stdout
    assert "PR 2" not in res.stdout


def test_list_mine_conflicts_with_author():
    seed()
    res = run("list", "--mine", "--author", "alice")
    assert res.exit_code == 1
    assert "not both" in text(res)


def test_submit_requires_body_for_request_changes():
    seed()
    res = run("submit", "1", "request-changes")
    assert res.exit_code == 1
    assert "--body is required" in text(res)


def test_submit_posts_and_updates_local_status(monkeypatch):
    seed()
    captured = {}

    class FakeClient:
        def __init__(self, token):
            pass

        def submit_review(self, owner, name, number, event, body):
            captured.update(
                owner=owner, name=name, number=number, event=event, body=body
            )
            return {"html_url": "https://github.com/o/r/pull/1#r1"}

    monkeypatch.setattr(cli, "GitHubClient", FakeClient)
    monkeypatch.setattr(config, "resolve_token", lambda: "tok")

    res = run("submit", "1", "approve", "--yes")
    assert res.exit_code == 0
    assert captured["event"] == "APPROVE"
    assert "Review posted" in res.stdout
    with db.connect() as conn:
        assert db.find_pull(conn, 1)[0]["review_status"] == "approved"


def test_submit_abort_does_not_post(monkeypatch):
    seed()

    class FakeClient:
        def __init__(self, token):
            raise AssertionError("client should not be constructed on abort")

    monkeypatch.setattr(cli, "GitHubClient", FakeClient)
    monkeypatch.setattr(config, "resolve_token", lambda: "tok")

    res = run("submit", "1", "approve", input="n\n")
    assert res.exit_code == 0
    assert "aborted" in res.stdout
    with db.connect() as conn:
        assert db.find_pull(conn, 1)[0]["review_status"] == "pending"
