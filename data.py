''' Data used throughout the application '''

import copy
import json
import logging
import os
import pickle

from typing import Any

from models import AudioBalanceMode, AutoplayMode
from subsonic import Song
from player import Player

logger = logging.getLogger(__name__)

GUILD_PROPERTIES_FILE = "guild_properties.json"
LEGACY_GUILD_PROPERTIES_FILE = "guild_properties.pickle"

class GuildData():
    ''' Class that holds all Discodrome data specific to a guild (not saved to disk) '''
    def __init__(self, guild_id: int) -> None:
        self._data = {
            "player": None,
        }
        self.player = Player(guild_properties(guild_id))
        if self.player.queue is None:
            self.player.queue = []

    @property
    def player(self) -> Player:
        '''The guild's player.'''
        return self._data["player"]
    
    @player.setter
    def player(self, value: Player) -> None:
        self._data["player"] = value

_guild_data_instances: dict[int, GuildData] = {} # Dictionary to store temporary data for each guild instance

def guild_data(guild_id: int) -> GuildData:
    ''' Returns the temporary data for the chosen guild '''

    # Return property if guild exists
    if guild_id in _guild_data_instances:
        return _guild_data_instances[guild_id]

    # Create & store new data object if guild does not already exist
    data = GuildData(guild_id)

    # Load queue from disk if it exists
    properties = guild_properties(guild_id)
    if properties.queue is not None:
        data.player.queue = properties.queue

    _guild_data_instances[guild_id] = data
    return _guild_data_instances[guild_id]


_default_properties: dict[str, Any] = {
    "queue": None,
    "autoplay-mode": AutoplayMode.NONE,
    "audio-balance-mode": AudioBalanceMode.DYNAMIC,
}

def _properties_with_defaults(properties: dict[str, Any]) -> dict[str, Any]:
    ''' Return a per-guild properties dict with any missing defaults added. '''
    updated_properties = copy.copy(_default_properties)
    updated_properties.update(properties)
    return updated_properties

def _enum_from_value(enum_class: type[AutoplayMode] | type[AudioBalanceMode], value: Any, default: Any) -> Any:
    ''' Parse a persisted enum value from name, value, or enum instance. '''
    if isinstance(value, enum_class):
        return value

    if isinstance(value, str):
        normalized_value = value.replace("-", "_").upper()
        if normalized_value in enum_class.__members__:
            return enum_class[normalized_value]

        for enum_value in enum_class:
            if value.lower() == str(enum_value.value).lower():
                return enum_value

    try:
        return enum_class(value)
    except (TypeError, ValueError):
        return default

def _song_to_dict(song: Song) -> dict[str, Any]:
    ''' Serialize a song for JSON persistence. '''
    return {
        "id": song.song_id,
        "title": song.title,
        "album": song.album,
        "artist": song.artist,
        "coverArt": song.cover_id,
        "duration": song.duration,
    }

def _song_from_dict(song_data: dict[str, Any]) -> Song:
    ''' Deserialize a song from JSON persistence. '''
    return Song({
        "id": song_data.get("id", ""),
        "title": song_data.get("title", "Unknown Track"),
        "album": song_data.get("album", "Unknown Album"),
        "artist": song_data.get("artist", "Unknown Artist"),
        "coverArt": song_data.get("coverArt", ""),
        "duration": song_data.get("duration", 0),
    })

class _LegacyGuildPropertiesUnpickler(pickle.Unpickler):
    ''' Restricted unpickler for one-time migration from the old local state file. '''

    _allowed_classes = {
        ("data", "GuildProperties"),
        ("data", "AutoplayMode"),
        ("data", "AudioBalanceMode"),
        ("models", "AutoplayMode"),
        ("models", "AudioBalanceMode"),
        ("subsonic", "Song"),
    }

    def find_class(self, module: str, name: str) -> Any:
        if (module, name) in self._allowed_classes:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Unsupported class in legacy guild properties: {module}.{name}")

class GuildProperties():
    ''' Class that holds all Discodrome properties specific to a guild (saved to disk) '''
    def __init__(self) -> None:
        self._properties = copy.copy(_default_properties)

    def ensure_defaults(self) -> None:
        ''' Add missing defaults and break shared default dict references. '''
        self._properties = _properties_with_defaults(self._properties)

    @property
    def autoplay_mode(self) -> AutoplayMode:
        '''The autoplay mode in use by this guild'''
        return self._properties["autoplay-mode"]

    @autoplay_mode.setter
    def autoplay_mode(self, value: AutoplayMode) -> None:
        self._properties["autoplay-mode"] = value

    @property
    def audio_balance_mode(self) -> AudioBalanceMode:
        '''The audio balancing mode in use by this guild'''
        return self._properties.get("audio-balance-mode", AudioBalanceMode.DYNAMIC)

    @audio_balance_mode.setter
    def audio_balance_mode(self, value: AudioBalanceMode) -> None:
        self._properties["audio-balance-mode"] = value

    @property
    def queue(self) -> list[Song]:
        return self._properties["queue"]

    @queue.setter
    def queue(self, value: list[Song]) -> None:
        self._properties["queue"] = value

    def to_dict(self) -> dict[str, Any]:
        ''' Serialize guild properties for JSON persistence. '''
        queue = self.queue
        return {
            "queue": None if queue is None else [_song_to_dict(song) for song in queue],
            "autoplay-mode": self.autoplay_mode.name.lower(),
            "audio-balance-mode": self.audio_balance_mode.name.lower(),
        }

    @classmethod
    def from_dict(cls, properties_data: dict[str, Any]) -> "GuildProperties":
        ''' Deserialize guild properties from JSON persistence. '''
        properties = cls()
        properties.autoplay_mode = _enum_from_value(
            AutoplayMode,
            properties_data.get("autoplay-mode"),
            AutoplayMode.NONE
        )
        properties.audio_balance_mode = _enum_from_value(
            AudioBalanceMode,
            properties_data.get("audio-balance-mode"),
            AudioBalanceMode.DYNAMIC
        )

        queue_data = properties_data.get("queue")
        if isinstance(queue_data, list):
            properties.queue = [
                _song_from_dict(song_data)
                for song_data in queue_data
                if isinstance(song_data, dict)
            ]
        else:
            properties.queue = None

        properties.ensure_defaults()
        return properties


_guild_property_instances: dict[int, GuildProperties] = {} # Dictionary to store properties for each guild instance

def guild_properties(guild_id: int) -> GuildProperties:
    ''' Returns the properties for the chosen guild '''

    # Return property if guild exists
    if guild_id in _guild_property_instances:
        _guild_property_instances[guild_id].ensure_defaults()
        return _guild_property_instances[guild_id]

    # Create & store new properties object if guild does not already exist
    properties = GuildProperties()
    _guild_property_instances[guild_id] = properties
    return _guild_property_instances[guild_id]

def save_guild_properties_to_disk() -> None:
    ''' Saves guild properties to disk. '''

    # Copy the queues from each guild data into each guild property
    for guild_id, properties in _guild_property_instances.items():
        if guild_id in _guild_data_instances:
            properties.queue = _guild_data_instances[guild_id].player.queue

    guild_properties_data = {
        str(guild_id): properties.to_dict()
        for guild_id, properties in _guild_property_instances.items()
    }
    saved_data = {"guilds": guild_properties_data}
    temp_file = f"{GUILD_PROPERTIES_FILE}.tmp"

    try:
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(saved_data, file, indent=2)
        os.replace(temp_file, GUILD_PROPERTIES_FILE)
        logger.info("Guild properties saved successfully.")
    except (OSError, TypeError) as err:
        logger.error("Failed to save guild properties to disk.", exc_info=err)

def load_guild_properties_from_disk() -> None:
    ''' Loads guild properties that have been saved to disk. '''

    if not os.path.exists(GUILD_PROPERTIES_FILE):
        if os.path.exists(LEGACY_GUILD_PROPERTIES_FILE):
            _load_legacy_guild_properties_from_disk()
            save_guild_properties_to_disk()
            return

        logger.info("Unable to load guild properties from disk. File was not found.")
        return

    try:
        with open(GUILD_PROPERTIES_FILE, "r", encoding="utf-8") as file:
            saved_data = json.load(file)
    except (json.JSONDecodeError, OSError) as err:
        logger.error("Failed to load guild properties from disk.", exc_info=err)
        return

    guilds_data = saved_data.get("guilds", saved_data)
    if not isinstance(guilds_data, dict):
        logger.error("Failed to load guild properties from disk. Expected a JSON object.")
        return

    for guild_id, properties_data in guilds_data.items():
        if not isinstance(properties_data, dict):
            logger.warning("Skipping guild properties for guild %s. Expected a JSON object.", guild_id)
            continue

        try:
            _guild_property_instances[int(guild_id)] = GuildProperties.from_dict(properties_data)
        except ValueError:
            logger.warning("Skipping guild properties for invalid guild ID %s.", guild_id)

    logger.info("Guild properties loaded successfully.")

def _load_legacy_guild_properties_from_disk() -> None:
    ''' Loads and migrates guild properties from the old pickle file. '''

    try:
        with open(LEGACY_GUILD_PROPERTIES_FILE, "rb") as file:
            legacy_properties = _LegacyGuildPropertiesUnpickler(file).load()
    except (pickle.UnpicklingError, OSError, AttributeError, EOFError) as err:
        logger.error("Failed to load legacy guild properties from disk.", exc_info=err)
        return

    if not isinstance(legacy_properties, dict):
        logger.error("Failed to load legacy guild properties from disk. Expected a dictionary.")
        return

    for guild_id, properties in legacy_properties.items():
        if not isinstance(guild_id, int) or not isinstance(properties, GuildProperties):
            logger.warning("Skipping invalid legacy guild properties entry for guild %s.", guild_id)
            continue

        properties.ensure_defaults()
        _guild_property_instances[guild_id] = properties

    logger.info("Legacy guild properties loaded and migrated successfully.")
