"""Configuration and credential resolution for prmanager."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _xdg(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var)
    return Path(raw) if raw else default


HOME = Path.home()
DATA_DIR = _xdg("XDG_DATA_HOME", HOME / ".local" / "share") / "prmanager"
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", HOME / ".config") / "prmanager"
CONFIG_FILE = CONFIG_DIR / "config.json"


def db_path() -> Path:
    """Location of the SQLite database. Overridable with PRM_DB."""
    override = os.environ.get("PRM_DB")
    if override:
        return Path(override)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "prm.db"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    # Token may live here; keep it private.
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def set_token(token: str) -> None:
    cfg = load_config()
    cfg["token"] = token
    save_config(cfg)


def resolve_token() -> str | None:
    """Find a GitHub token: env vars, config file, then the gh CLI."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val.strip()

    token = load_config().get("token")
    if token:
        return str(token).strip()

    try:
        out = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    return None
