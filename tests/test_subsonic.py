import asyncio
import importlib
import sys
from pathlib import Path


def import_subsonic_with_env(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
    monkeypatch.setenv("DISCORD_TEST_GUILD", "123")
    monkeypatch.setenv("DISCORD_OWNER_ID", "456")
    monkeypatch.setenv("APP_ID", "789")
    monkeypatch.setenv("SUBSONIC_SERVER", "https://subsonic.example")
    monkeypatch.setenv("SUBSONIC_USER", "user")
    monkeypatch.setenv("SUBSONIC_PASSWORD", "pass")

    sys.modules.pop("util.env", None)
    sys.modules.pop("util", None)
    sys.modules.pop("subsonic", None)
    return importlib.import_module("subsonic")


def test_token_auth_params_are_deterministic(monkeypatch, tmp_path):
    subsonic = import_subsonic_with_env(monkeypatch, tmp_path)
    monkeypatch.setattr(subsonic.secrets, "token_hex", lambda length: "salt-value")

    params = subsonic._get_auth_params()

    assert params["u"] == "user"
    assert params["s"] == "salt-value"
    assert params["t"] == "bda06896546fe111b31b0542f59b97f4"
    assert "p" not in params


def test_password_auth_params_include_legacy_prefix(monkeypatch, tmp_path):
    subsonic = import_subsonic_with_env(monkeypatch, tmp_path)
    monkeypatch.setattr(subsonic.env, "SUBSONIC_AUTH_MODE", "plaintext")

    params = subsonic._get_auth_params()

    assert params["p"] == "pass"
    assert "s" not in params
    assert "t" not in params


def test_json_request_helper_adds_auth_and_checks_errors(monkeypatch, tmp_path):
    subsonic = import_subsonic_with_env(monkeypatch, tmp_path)
    captured = {}

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        async def json(self):
            return {"subsonic-response": {"status": "ok"}}

    class Session:
        async def get(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return Response()

    async def fake_get_session():
        return Session()

    monkeypatch.setattr(subsonic, "get_session", fake_get_session)
    monkeypatch.setattr(subsonic.secrets, "token_hex", lambda length: "salt-value")

    result = asyncio.run(subsonic._get_json("ping.view", {"extra": "value"}, timeout=12))

    assert result["subsonic-response"]["status"] == "ok"
    assert captured["url"] == "https://subsonic.example/rest/ping.view"
    assert captured["kwargs"]["timeout"] == 12
    assert captured["kwargs"]["params"]["extra"] == "value"
    assert captured["kwargs"]["params"]["u"] == "user"


def test_json_request_helper_raises_api_error_with_code_alias(monkeypatch, tmp_path):
    subsonic = import_subsonic_with_env(monkeypatch, tmp_path)

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        async def json(self):
            return {"subsonic-response": {"status": "failed", "error": {"code": 70}}}

    class Session:
        async def get(self, url, **kwargs):
            return Response()

    async def fake_get_session():
        return Session()

    monkeypatch.setattr(subsonic, "get_session", fake_get_session)

    try:
        asyncio.run(subsonic._get_json("missing.view"))
    except subsonic.APIError as error:
        assert error.errorcode == 70
        assert error.code == 70
        assert error.message == "The requested data was not found."
    else:
        raise AssertionError("Expected APIError")


def test_json_request_helper_rejects_malformed_subsonic_response(monkeypatch, tmp_path):
    subsonic = import_subsonic_with_env(monkeypatch, tmp_path)

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        async def json(self):
            return {"unexpected": "payload"}

    class Session:
        async def get(self, url, **kwargs):
            return Response()

    async def fake_get_session():
        return Session()

    monkeypatch.setattr(subsonic, "get_session", fake_get_session)

    try:
        asyncio.run(subsonic._get_json("broken.view"))
    except subsonic.APIError as error:
        assert error.code == 0
        assert "Malformed Subsonic response" in error.message
    else:
        raise AssertionError("Expected APIError")


def test_collection_parsers_tolerate_missing_optional_lists(monkeypatch, tmp_path):
    subsonic = import_subsonic_with_env(monkeypatch, tmp_path)

    album = subsonic.Album({"id": "album-1", "name": "Empty Album"})
    playlist = subsonic.Playlist({"id": "playlist-1", "name": "Empty Playlist"})
    artist = subsonic.Artist({"id": "artist-1", "name": "Empty Artist"})

    assert album.songs == []
    assert playlist.songs == []
    assert artist.albums == []
