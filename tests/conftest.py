"""Shared fixtures. Every test runs against a temp DB and temp config,
with the network and the `gh` CLI fallback neutralized by default."""

from __future__ import annotations

import pytest

from prm import config, db


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    # Database lives in a temp file via PRM_DB.
    monkeypatch.setenv("PRM_DB", str(tmp_path / "prm.db"))

    # Config redirected to a temp file.
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_dir / "config.json")

    # No ambient tokens, and the gh fallback is inert unless a test opts in.
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def _no_gh(*_a, **_k):
        raise FileNotFoundError("gh not available in tests")

    monkeypatch.setattr(config.subprocess, "run", _no_gh)

    db.init_db()
    yield
