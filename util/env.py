import os
from typing import Final

from dotenv import load_dotenv

load_dotenv(os.path.relpath("data.env"))

_REQUIRED_VARIABLES = (
    "DISCORD_BOT_TOKEN",
    "DISCORD_OWNER_ID",
    "APP_ID",
    "SUBSONIC_SERVER",
    "SUBSONIC_USER",
    "SUBSONIC_PASSWORD",
)


def _optional_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _required_str(name: str) -> str:
    value = _optional_str(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variables: {name}")
    return value


def _optional_int(name: str, default: int | None = None) -> int | None:
    value = _optional_str(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {value!r}") from exc


def _required_int(name: str) -> int:
    value = _optional_int(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variables: {name}")
    return value


def _optional_choice(name: str, choices: tuple[str, ...], default: str) -> str:
    value = _optional_str(name, default) or default
    if value not in choices:
        formatted = ", ".join(choices)
        raise RuntimeError(f"{name} must be one of: {formatted}; got {value!r}")
    return value


def _optional_int_at_least(name: str, minimum: int, default: int) -> int:
    value = _optional_int(name, default)
    if value is None:
        return default
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}, got {value}")
    return value


def _validate_required_variables() -> None:
    missing = [name for name in _REQUIRED_VARIABLES if _optional_str(name) is None]
    if missing:
        formatted = "\n".join(f"- {name}" for name in missing)
        raise RuntimeError(f"Missing required environment variables:\n{formatted}")


_validate_required_variables()

DISCORD_BOT_TOKEN: Final[str] = _required_str("DISCORD_BOT_TOKEN")
DISCORD_TEST_GUILD: Final[int | None] = _optional_int("DISCORD_TEST_GUILD")
DISCORD_OWNER_ID: Final[int] = _required_int("DISCORD_OWNER_ID")
APP_ID: Final[int] = _required_int("APP_ID")

SUBSONIC_SERVER: Final[str] = _required_str("SUBSONIC_SERVER").rstrip("/")
SUBSONIC_USER: Final[str] = _required_str("SUBSONIC_USER")
SUBSONIC_PASSWORD: Final[str] = _required_str("SUBSONIC_PASSWORD")
SUBSONIC_AUTH_MODE: Final[str] = _optional_choice("SUBSONIC_AUTH_MODE", ("plaintext", "token"), "token")

BOT_STATUS: Final[str | None] = _optional_str("BOT_STATUS")
BOT_PREFIX: Final[str | None] = _optional_str("BOT_PREFIX")
BOT_SEARCH_SUGGESTION_COUNT: Final[int] = _optional_int_at_least("BOT_SEARCH_SUGGESTION_COUNT", 1, 5)
