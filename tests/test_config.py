import types

from prm import config


def test_set_and_resolve_token_from_config():
    config.set_token("cfg-token")
    assert config.resolve_token() == "cfg-token"


def test_env_token_takes_precedence(monkeypatch):
    config.set_token("cfg-token")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    assert config.resolve_token() == "env-token"


def test_resolve_token_falls_back_to_gh(monkeypatch):
    # no env, no config -> use gh CLI
    def fake_run(*_a, **_k):
        return types.SimpleNamespace(returncode=0, stdout="gh-token\n")

    monkeypatch.setattr(config.subprocess, "run", fake_run)
    assert config.resolve_token() == "gh-token"


def test_resolve_token_none_when_unavailable():
    # autouse fixture disables gh and clears env; no config written
    assert config.resolve_token() is None


def test_login_cache_roundtrip():
    assert config.cached_login() is None
    config.set_login("sbj-ee")
    assert config.cached_login() == "sbj-ee"


def test_load_config_survives_corrupt_file():
    config.CONFIG_FILE.write_text("{not json")
    assert config.load_config() == {}
