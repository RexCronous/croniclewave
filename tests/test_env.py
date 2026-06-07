import importlib
import sys

import pytest

ENV_KEYS = [
    "DISCORD_BOT_TOKEN",
    "DISCORD_TEST_GUILD",
    "DISCORD_OWNER_ID",
    "APP_ID",
    "SUBSONIC_SERVER",
    "SUBSONIC_USER",
    "SUBSONIC_PASSWORD",
    "SUBSONIC_AUTH_MODE",
    "BOT_STATUS",
    "BOT_PREFIX",
    "BOT_SEARCH_SUGGESTION_COUNT",
]


def reload_env(monkeypatch):
    sys.modules.pop("util.env", None)
    return importlib.import_module("util.env")


def clear_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def set_required_env(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("DISCORD_OWNER_ID", "123")
    monkeypatch.setenv("APP_ID", "456")
    monkeypatch.setenv("SUBSONIC_SERVER", "https://music.example")
    monkeypatch.setenv("SUBSONIC_USER", "ren")
    monkeypatch.setenv("SUBSONIC_PASSWORD", "subsonic-password")


def test_missing_required_environment_values_raise_clear_error(monkeypatch):
    clear_env(monkeypatch)

    with pytest.raises(RuntimeError) as exc_info:
        reload_env(monkeypatch)

    message = str(exc_info.value)
    assert "Missing required environment variables" in message
    assert "DISCORD_BOT_TOKEN" in message
    assert "SUBSONIC_PASSWORD" in message


def test_environment_loader_uses_defaults_and_parses_ints(monkeypatch):
    clear_env(monkeypatch)
    set_required_env(monkeypatch)

    env = reload_env(monkeypatch)

    assert env.DISCORD_OWNER_ID == 123
    assert env.APP_ID == 456
    assert env.DISCORD_TEST_GUILD is None
    assert env.SUBSONIC_AUTH_MODE == "token"
    assert env.BOT_PREFIX is None
    assert env.BOT_SEARCH_SUGGESTION_COUNT == 5


def test_invalid_integer_environment_value_names_variable(monkeypatch):
    clear_env(monkeypatch)
    set_required_env(monkeypatch)
    monkeypatch.setenv("APP_ID", "not-an-int")

    with pytest.raises(RuntimeError) as exc_info:
        reload_env(monkeypatch)

    assert "APP_ID must be an integer" in str(exc_info.value)


def test_invalid_subsonic_auth_mode_names_allowed_values(monkeypatch):
    clear_env(monkeypatch)
    set_required_env(monkeypatch)
    monkeypatch.setenv("SUBSONIC_AUTH_MODE", "digest")

    with pytest.raises(RuntimeError) as exc_info:
        reload_env(monkeypatch)

    message = str(exc_info.value)
    assert "SUBSONIC_AUTH_MODE must be one of" in message
    assert "plaintext" in message
    assert "token" in message


def test_search_suggestion_count_must_be_positive(monkeypatch):
    clear_env(monkeypatch)
    set_required_env(monkeypatch)
    monkeypatch.setenv("BOT_SEARCH_SUGGESTION_COUNT", "0")

    with pytest.raises(RuntimeError) as exc_info:
        reload_env(monkeypatch)

    assert "BOT_SEARCH_SUGGESTION_COUNT must be at least 1" in str(exc_info.value)
