import asyncio
import importlib
import sys
from pathlib import Path


class FakeGuildProperties:
    def __init__(self):
        self.queue = []
        self.autoplay_mode = None
        self.audio_balance_mode = None


def import_player_with_env(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("DISCORD_OWNER_ID", "123")
    monkeypatch.setenv("APP_ID", "456")
    monkeypatch.setenv("SUBSONIC_SERVER", "https://music.example")
    monkeypatch.setenv("SUBSONIC_USER", "ren")
    monkeypatch.setenv("SUBSONIC_PASSWORD", "subsonic-password")
    for module in ["util.env", "subsonic", "player"]:
        sys.modules.pop(module, None)
    return importlib.import_module("player")


def test_player_queue_mutation_helpers_persist(monkeypatch, tmp_path):
    player_module = import_player_with_env(monkeypatch, tmp_path)
    guild_properties = FakeGuildProperties()
    player = player_module.Player(guild_properties)
    saves = []

    monkeypatch.setattr(player_module, "save_guild_properties", lambda: saves.append(list(guild_properties.queue)))

    async def exercise_queue():
        await player.enqueue("first")
        await player.enqueue("next", position="front")
        await player.move_queued_song(1, 0)
        removed = await player.remove_queued_song(1)
        await player.clear_queue()
        return removed

    removed = asyncio.run(exercise_queue())

    assert removed == "next"
    assert player.queue == []
    assert guild_properties.queue == []
    assert saves == [["first"], ["next", "first"], ["first", "next"], ["first"], []]


def test_persisted_queue_is_snapshot_not_live_list(monkeypatch, tmp_path):
    player_module = import_player_with_env(monkeypatch, tmp_path)
    guild_properties = FakeGuildProperties()
    player = player_module.Player(guild_properties)

    monkeypatch.setattr(player_module, "save_guild_properties", lambda: None)

    asyncio.run(player.enqueue("persisted"))
    player.queue.append("unsaved-live-mutation")

    assert guild_properties.queue == ["persisted"]
    assert guild_properties.queue is not player.queue
