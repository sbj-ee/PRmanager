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

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        resp = self.session.get(f"{API_ROOT}{path}", params=params, timeout=30)
        if resp.status_code == 401:
            raise GitHubError("Unauthorized (401). Check your GitHub token.")
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise GitHubError("GitHub API rate limit exceeded.")
        if resp.status_code == 404:
            raise GitHubError(f"Not found (404): {path}")
        if not resp.ok:
            raise GitHubError(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
        return resp

    def current_user(self) -> str:
        """Return the login of the authenticated user."""
        resp = self._get("/user")
        login = resp.json().get("login")
        if not login:
            raise GitHubError("could not determine the authenticated user.")
        return login

    def fetch_pulls(self, owner: str, repo: str, state: str = "all") -> list[dict]:
        """Fetch all PRs for a repo (paginated), normalized to our schema."""
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
            for pr in batch:
                pulls.append(self._normalize(pr))
            if len(batch) < 100:
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
        }
