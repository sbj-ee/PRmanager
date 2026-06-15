"""Thin GitHub REST API client for fetching pull requests."""

from __future__ import annotations

import requests

API_ROOT = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token: str | None):
        self.session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "prmanager",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.session.headers.update(headers)

    def _check(self, resp: requests.Response) -> requests.Response:
        if resp.status_code == 401:
            raise GitHubError("Unauthorized (401). Check your GitHub token.")
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise GitHubError("GitHub API rate limit exceeded.")
        if resp.status_code == 403:
            raise GitHubError(
                "Forbidden (403). Your token may lack the required scope "
                "(pull-request write / 'repo')."
            )
        if resp.status_code == 404:
            raise GitHubError(f"Not found (404): {resp.request.path_url}")
        if resp.status_code == 422:
            raise GitHubError(f"Unprocessable (422): {resp.text[:300]}")
        if not resp.ok:
            raise GitHubError(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
        return resp

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        return self._check(
            self.session.get(f"{API_ROOT}{path}", params=params, timeout=30)
        )

    def _post(self, path: str, payload: dict) -> requests.Response:
        return self._check(
            self.session.post(f"{API_ROOT}{path}", json=payload, timeout=30)
        )

    def submit_review(
        self, owner: str, repo: str, number: int, event: str, body: str = ""
    ) -> dict:
        """Submit a review on a PR. event is one of GitHub's review events:
        APPROVE, REQUEST_CHANGES, COMMENT."""
        payload: dict = {"event": event}
        if body:
            payload["body"] = body
        resp = self._post(
            f"/repos/{owner}/{repo}/pulls/{number}/reviews", payload
        )
        return resp.json()

    def current_user(self) -> str:
        """Return the login of the authenticated user."""
        resp = self._get("/user")
        login = resp.json().get("login")
        if not login:
            raise GitHubError("could not determine the authenticated user.")
        return login

    def fetch_pulls(
        self, owner: str, repo: str, state: str = "all", since: str | None = None
    ) -> list[dict]:
        """Fetch PRs for a repo (paginated), normalized to our schema.

        PRs are returned newest-updated first. When ``since`` (an ISO-8601
        ``updated_at`` watermark) is given, pagination stops as soon as a PR
        older than it is seen, so only new/changed PRs are returned. The
        boundary timestamp is included to avoid missing ties (upserts are
        idempotent).
        """
        pulls: list[dict] = []
        page = 1
        while True:
            resp = self._get(
                f"/repos/{owner}/{repo}/pulls",
                params={
                    "state": state,
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "direction": "desc",
                },
            )
            batch = resp.json()
            if not batch:
                break
            stop = False
            for pr in batch:
                norm = self._normalize(pr)
                # ISO-8601 UTC ("...Z") strings compare correctly lexically.
                if since and norm["updated_at"] and norm["updated_at"] < since:
                    stop = True
                    break
                pulls.append(norm)
            if stop or len(batch) < 100:
                break
            page += 1
        return pulls

    @staticmethod
    def _normalize(pr: dict) -> dict:
        return {
            "number": pr["number"],
            "title": pr.get("title"),
            "author": (pr.get("user") or {}).get("login"),
            "state": pr.get("state"),
            "merged": bool(pr.get("merged_at")),
            "draft": bool(pr.get("draft")),
            "url": pr.get("html_url"),
            "body": pr.get("body") or "",
            "created_at": pr.get("created_at"),
            "updated_at": pr.get("updated_at"),
            "head_sha": (pr.get("head") or {}).get("sha"),
            "labels": ",".join(
                lbl["name"] for lbl in (pr.get("labels") or []) if lbl.get("name")
            ),
            "assignees": ",".join(
                a["login"] for a in (pr.get("assignees") or []) if a.get("login")
            ),
        }

    # Check conclusions that count as a hard failure.
    _FAIL_CONCLUSIONS = frozenset(
        {"failure", "timed_out", "cancelled", "action_required",
         "stale", "startup_failure"}
    )
    # Conclusions that don't affect the rollup either way.
    _IGNORED_CONCLUSIONS = frozenset({"neutral", "skipped"})

    def checks_status(self, owner: str, repo: str, sha: str) -> str:
        """Aggregate CI state for a commit into one of:
        'success', 'failure', 'pending', or 'none' (no checks configured).

        Combines legacy commit statuses (external CI) and check runs
        (e.g. GitHub Actions)."""
        states: list[str] = []

        combined = self._get(f"/repos/{owner}/{repo}/commits/{sha}/status").json()
        if combined.get("total_count", 0) > 0 and combined.get("state"):
            states.append(combined["state"])  # success / failure / pending

        runs = (
            self._get(f"/repos/{owner}/{repo}/commits/{sha}/check-runs")
            .json()
            .get("check_runs", [])
        )
        for run in runs:
            if run.get("status") != "completed":
                states.append("pending")
                continue
            conclusion = run.get("conclusion")
            if conclusion in self._IGNORED_CONCLUSIONS:
                continue
            if conclusion in self._FAIL_CONCLUSIONS:
                states.append("failure")
            elif conclusion == "success":
                states.append("success")
            else:
                states.append("pending")

        if not states:
            return "none"
        if "failure" in states:
            return "failure"
        if "pending" in states:
            return "pending"
        return "success"
