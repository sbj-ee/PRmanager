import types

import pytest

from prm.github import GitHubClient, GitHubError


class FakeResp:
    def __init__(self, status=200, json_data=None, text=""):
        self.status_code = status
        self._json = json_data if json_data is not None else {}
        self.text = text
        self.ok = 200 <= status < 300
        self.request = types.SimpleNamespace(path_url="/x")

    def json(self):
        return self._json


def _raw_pr(number):
    return {
        "number": number,
        "title": f"PR {number}",
        "user": {"login": "alice"},
        "state": "open",
        "merged_at": None,
        "draft": False,
        "html_url": f"https://github.com/o/r/pull/{number}",
        "body": "hello",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }


def test_normalize_maps_fields():
    norm = GitHubClient._normalize(_raw_pr(3))
    assert norm["number"] == 3
    assert norm["author"] == "alice"
    assert norm["merged"] is False
    assert norm["url"].endswith("/pull/3")


def test_normalize_merged_and_missing_body():
    raw = _raw_pr(4)
    raw["merged_at"] = "2026-02-01T00:00:00Z"
    raw["body"] = None
    norm = GitHubClient._normalize(raw)
    assert norm["merged"] is True
    assert norm["body"] == ""


def test_fetch_pulls_paginates(monkeypatch):
    client = GitHubClient("tok")
    pages = {
        1: [_raw_pr(n) for n in range(100)],   # full page -> fetch next
        2: [_raw_pr(200)],                       # partial -> stop
    }

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            return FakeResp(json_data=pages.get(params["page"], []))

    client.session = FakeSession()
    pulls = client.fetch_pulls("o", "r")
    assert len(pulls) == 101
    assert pulls[-1]["number"] == 200


def test_fetch_pulls_since_stops_at_watermark():
    client = GitHubClient("tok")
    # newest-first; watermark is between the 2nd and 3rd PR
    def pr(n, ts):
        p = _raw_pr(n)
        p["updated_at"] = ts
        return p

    page1 = [
        pr(3, "2026-03-03T00:00:00Z"),
        pr(2, "2026-03-02T00:00:00Z"),
        pr(1, "2026-03-01T00:00:00Z"),  # older than since -> stop here
    ]

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            return FakeResp(json_data=page1 if params["page"] == 1 else [])

    client.session = FakeSession()
    pulls = client.fetch_pulls("o", "r", since="2026-03-02T00:00:00Z")
    nums = [p["number"] for p in pulls]
    assert nums == [3, 2]  # PR 1 excluded; boundary (2) included


def test_submit_review_builds_payload(monkeypatch):
    client = GitHubClient("tok")
    captured = {}

    class FakeSession:
        def post(self, url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResp(json_data={"html_url": "https://github.com/o/r/pull/9#r1"})

    client.session = FakeSession()
    out = client.submit_review("o", "r", 9, "APPROVE", "lgtm")
    assert captured["url"].endswith("/repos/o/r/pulls/9/reviews")
    assert captured["json"] == {"event": "APPROVE", "body": "lgtm"}
    assert out["html_url"].endswith("#r1")


def test_submit_review_omits_empty_body():
    client = GitHubClient("tok")
    captured = {}

    class FakeSession:
        def post(self, url, json=None, timeout=None):
            captured["json"] = json
            return FakeResp(json_data={})

    client.session = FakeSession()
    client.submit_review("o", "r", 1, "APPROVE", "")
    assert captured["json"] == {"event": "APPROVE"}


@pytest.mark.parametrize(
    "status,needle",
    [
        (401, "Unauthorized"),
        (403, "Forbidden"),
        (404, "Not found"),
        (422, "Unprocessable"),
        (500, "500"),
    ],
)
def test_check_error_mapping(status, needle):
    client = GitHubClient("tok")
    with pytest.raises(GitHubError) as exc:
        client._check(FakeResp(status=status, text="boom"))
    assert needle in str(exc.value)


def test_rate_limit_message():
    client = GitHubClient("tok")
    with pytest.raises(GitHubError) as exc:
        client._check(FakeResp(status=403, text="API rate limit exceeded"))
    assert "rate limit" in str(exc.value).lower()


def _checks_client(status_json, checkruns_json):
    client = GitHubClient("tok")

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            if url.endswith("/status"):
                return FakeResp(json_data=status_json)
            if url.endswith("/check-runs"):
                return FakeResp(json_data=checkruns_json)
            return FakeResp(json_data={})

    client.session = FakeSession()
    return client


def _run(status, conclusion="success"):
    return {"status": status, "conclusion": conclusion}


@pytest.mark.parametrize(
    "status_json,runs,expected",
    [
        ({"total_count": 0, "state": "pending"}, [], "none"),
        ({"total_count": 0}, [_run("completed", "success")], "success"),
        ({"total_count": 0}, [_run("completed", "success"),
                              _run("completed", "failure")], "failure"),
        ({"total_count": 0}, [_run("in_progress", None)], "pending"),
        ({"total_count": 2, "state": "failure"}, [], "failure"),
        ({"total_count": 1, "state": "success"},
         [_run("completed", "success")], "success"),
        # neutral/skipped don't count
        ({"total_count": 0}, [_run("completed", "skipped"),
                              _run("completed", "neutral")], "none"),
        ({"total_count": 0}, [_run("completed", "timed_out")], "failure"),
    ],
)
def test_checks_status_rollup(status_json, runs, expected):
    client = _checks_client(status_json, {"check_runs": runs})
    assert client.checks_status("o", "r", "sha") == expected


def test_normalize_extracts_head_sha():
    raw = _raw_pr(1)
    raw["head"] = {"sha": "abc123"}
    assert GitHubClient._normalize(raw)["head_sha"] == "abc123"


def test_current_user():
    client = GitHubClient("tok")

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            return FakeResp(json_data={"login": "sbj-ee"})

    client.session = FakeSession()
    assert client.current_user() == "sbj-ee"
