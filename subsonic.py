"""For interfacing with the Subsonic API"""

import asyncio
import hashlib
import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

import aiohttp

from util import env

logger = logging.getLogger(__name__)


def _get_auth_params() -> dict:
    """
    Generate authentication parameters based on SUBSONIC_AUTH_MODE.

    Supports two authentication modes:
    - plaintext: Uses the configured password directly.
    - token: Uses MD5(password + salt) for enhanced security (available since Subsonic API v1.13.0; this client requests v1.15.0).

    Returns:
        dict: Authentication parameters including username, version, client name,
              format, and either password (plaintext mode) or token+salt (token mode)
    """
    auth_mode = env.SUBSONIC_AUTH_MODE
    if auth_mode not in ("plaintext", "token"):
        raise ValueError(f"SUBSONIC_AUTH_MODE must be 'plaintext' or 'token', got: {auth_mode!r}")

    auth_params = {"u": env.SUBSONIC_USER, "c": "discodrome", "f": "json", "v": "1.15.0"}

    if auth_mode == "token":
        # Use token-based authentication with salt
        # Generate a new salt for each request for security
        salt = secrets.token_hex(16)
        # Note: MD5 is used here because it's required by the Subsonic API specification,
        # despite being cryptographically weak. This is a protocol requirement.
        token = hashlib.md5((env.SUBSONIC_PASSWORD + salt).encode()).hexdigest()
        auth_params["t"] = token
        auth_params["s"] = salt
    else:
        # Use plaintext authentication (default)
        auth_params["p"] = env.SUBSONIC_PASSWORD

    return auth_params


globalsession = None


async def get_session() -> aiohttp.ClientSession:
    """Get an aiohttp session"""
    global globalsession
    if globalsession is None:
        globalsession = aiohttp.ClientSession()
    return globalsession


async def close_session() -> None:
    """Close the aiohttp session"""
    global globalsession
    if globalsession is not None:
        await globalsession.close()
        await asyncio.sleep(0.25)
        globalsession = None


class APIError(Exception):
    """Exception raised for errors in the Subsonic API"""

    def __init__(self, errorcode: int, message: str) -> None:
        self.errorcode = errorcode
        self.code = errorcode
        self.message = message
        super().__init__(self.message)


class Song:
    """Object representing a song returned from the Subsonic API"""

    def __init__(self, json_object: dict) -> None:
        #! Other properties exist in the initial json response but are currently unused by Discodrome and thus aren't supported here
        self._id: str = json_object.get("id", "")
        self._title: str = json_object.get("title", "Unknown Track")
        self._album: str = json_object.get("album", "Unknown Album")
        self._artist: str = json_object.get("artist", "Unknown Artist")
        self._cover_id: str = json_object.get("coverArt", "")
        self._duration: int = json_object.get("duration", 0)

    @property
    def song_id(self) -> str:
        """The song's id"""
        return self._id

    @property
    def title(self) -> str:
        """The song's title"""
        return self._title

    @property
    def album(self) -> str:
        """The album containing the song"""
        return self._album

    @property
    def artist(self) -> str:
        """The song's artist"""
        return self._artist

    @property
    def cover_id(self) -> str:
        """The id of the cover art used by the song"""
        return self._cover_id

    @property
    def duration(self) -> int:
        """The total duration of the song"""
        return self._duration

    @property
    def duration_printable(self) -> str:
        """The total duration of the song as a human readable string in the format `mm:ss`"""
        return f"{(self._duration // 60):02d}:{(self._duration % 60):02d}"


class AlbumMeta:
    """Object representing an album returned from subsonic API"""

    def __init__(self, json_object: dict) -> None:
        self._id: str = json_object.get("id", "")
        self._name: str = json_object.get("name", "Unknown Album")
        self._artist: str = json_object.get("artist", "Unknown Artist")
        self._cover_id: str = json_object.get("coverArt", "")
        self._song_count: int = json_object.get("songCount", 0)
        self._duration: int = json_object.get("duration", 0)
        self._year: int = json_object.get("year", 0)

    @property
    def id(self) -> str:
        """The album's id"""
        return self._id

    @property
    def name(self) -> str:
        """The album's name"""
        return self._name

    @property
    def artist(self) -> str:
        """The album's artist"""
        return self._artist

    @property
    def cover_id(self) -> str:
        """The id of the cover art used by the album"""
        return self._cover_id

    @property
    def song_count(self) -> int:
        """The number of songs in the album"""
        return self._song_count

    @property
    def duration(self) -> int:
        """The total duration of the album"""
        return self._duration

    @property
    def duration_printable(self) -> str:
        """The total duration of the album as a human readable string in the format `mm:ss`"""
        return f"{(self._duration // 60):02d}:{(self._duration % 60):02d}"

    @property
    def year(self) -> int:
        """The year the album was released"""
        return self._year


class Album(AlbumMeta):
    """Object representing an album returned from subsonic API"""

    def __init__(self, json_object: dict) -> None:
        super().__init__(json_object)
        self._songs: list[Song] = []
        for song in json_object.get("song", []):
            self._songs.append(Song(song))

    @property
    def songs(self) -> list[Song]:
        """The songs in the album"""
        return self._songs


class ArtistMeta:
    """Object representing an artist returned from subsonic API"""

    def __init__(self, json_object: dict) -> None:
        self._id: str = json_object.get("id", "")
        self._name: str = json_object.get("name", "Unknown Artist")
        self._cover_id: str = json_object.get("coverArt", "")
        self._album_count: int = json_object.get("albumCount", 0)

    @property
    def artist_id(self) -> str:
        """The artist's id"""
        return self._id

    @property
    def name(self) -> str:
        """The artist's name"""
        return self._name

    @property
    def cover_id(self) -> str:
        """The id of the cover art used by the artist"""
        return self._cover_id

    @property
    def album_count(self) -> int:
        """The number of albums by the artist"""
        return self._album_count


class Artist(ArtistMeta):
    """Object representing an artist returned from subsonic API"""

    def __init__(self, json_object: dict) -> None:
        super().__init__(json_object)
        self._albums: list[Album] = []
        for album in json_object.get("album", []):
            self._albums.append(Album(album))

    @property
    def albums(self) -> list[Album]:
        """The albums by the artist"""
        return self._albums


class PlaylistMeta:
    """Object representing a playlist returned from subsonic API"""

    def __init__(self, json_object: dict) -> None:
        self._id: str = json_object.get("id", "")
        self._name: str = json_object.get("name", "Unknown Album")
        self._cover_id: str = json_object.get("coverArt", "")
        self._song_count: int = json_object.get("songCount", 0)
        self._duration: int = json_object.get("duration", 0)
        self._songs: list[Song] = []
        for song in json_object.get("entry", []):
            self._songs.append(Song(song))

    @property
    def playlist_id(self) -> str:
        """The playlist's id"""
        return self._id

    @property
    def name(self) -> str:
        """The playlist's name"""
        return self._name

    @property
    def cover_id(self) -> str:
        """The id of the cover art used by the playlist"""
        return self._cover_id

    @property
    def song_count(self) -> int:
        """The number of songs in the playlist"""
        return self._song_count

    @property
    def duration(self) -> int:
        """The total duration of the playlist"""
        return self._duration

    @property
    def duration_printable(self) -> str:
        """The total duration of the playlist as a human readable string in the format `hh:mm:ss`"""
        return str(timedelta(seconds=self._duration))


class Playlist(PlaylistMeta):
    """Object representing a playlist returned from subsonic API"""

    def __init__(self, json_object: dict) -> None:
        super().__init__(json_object)
        self._songs: list[Song] = []
        for song in json_object.get("entry", []):
            self._songs.append(Song(song))

        # If playlist has no cover art, try to use the first song's cover art
        if not self._cover_id and self._songs:
            self._cover_id = self._songs[0].cover_id

    @property
    def songs(self) -> list[Song]:
        """The songs in the playlist"""
        return self._songs


class ApiResponse:
    """Object representing a generic response from the Subsonic API"""

    def __init__(self, response: dict):
        self._raw_response = response
        self._status = response["subsonic-response"]["status"]
        self._error_code = (
            response["subsonic-response"]["error"]["code"] if "error" in response["subsonic-response"] else None
        )
        self._error_message = (
            response["subsonic-response"]["error"]["message"] if "error" in response["subsonic-response"] else None
        )

    @property
    def raw_response(self) -> dict:
        """The raw response from the Subsonic API"""
        return self._raw_response

    @property
    def status(self) -> str:
        """The status of the API response. Either "ok" or "failed" """
        return self._status

    def succeeded(self) -> bool:
        """Returns true if the API response indicates a successful request"""
        return self._status == "ok"

    @property
    def error_code(self) -> dict:
        """The error code returned by the API, if any."""
        return self._error_code

    @property
    def error_message(self) -> dict:
        """The error message returned by the API, if any."""
        return self._error_message


class SearchResults(ApiResponse):
    """Object representing search results returned from the Subsonic API"""

    def __init__(self, response: dict) -> None:
        super().__init__(response)
        search_results = response["subsonic-response"].get("searchResult3", {})
        self._songs: list[Song] = []
        self._albums: list[AlbumMeta] = []
        self._artists: list[ArtistMeta] = []
        if "song" in search_results:
            for song in search_results["song"]:
                self._songs.append(Song(song))
        if "album" in search_results:
            for album in search_results["album"]:
                self._albums.append(AlbumMeta(album))
        if "artist" in search_results:
            for artist in search_results["artist"]:
                self._artists.append(ArtistMeta(artist))

    @property
    def songs(self) -> list[Song]:
        """The songs returned by the search query"""
        return self._songs

    @property
    def albums(self) -> list[AlbumMeta]:
        """The albums returned by the search query"""
        return self._albums

    @property
    def artists(self) -> list[ArtistMeta]:
        """The artists returned by the search query"""
        return self._artists


async def ping_api() -> bool:
    """Send a ping request to the subsonic API"""

    ping_data = await _get_json("ping.view", check_errors=False)
    if await check_subsonic_error(ping_data):
        return False
    logger.debug("Ping Response: %s", ping_data)

    return True


async def check_subsonic_error(response: dict[str, Any]) -> bool:
    """Checks and logs error codes returned by the subsonic API. Returns true if an error is present"""

    logging.debug("Checking for subsonic error...")
    if isinstance(response, aiohttp.ClientResponse):
        try:
            response = await response.json()
        except Exception:
            return False

    subsonic_response = response.get("subsonic-response") if isinstance(response, dict) else None
    if not isinstance(subsonic_response, dict):
        raise APIError(0, "Malformed Subsonic response: missing subsonic-response envelope.")

    if subsonic_response.get("status") == "ok":
        logging.debug("No error found.")
        return False

    err_code = subsonic_response.get("error", {}).get("code", 0)
    match err_code:
        case 0:
            err_msg = "Generic Error."
            raise APIError(err_code, err_msg)
        case 10:
            err_msg = "Required Parameter Missing."
            raise APIError(err_code, err_msg)
        case 20:
            err_msg = "Incompatible Subsonic REST protocol version. Client must upgrade."
            raise APIError(err_code, err_msg)
        case 30:
            err_msg = "Incompatible Subsonic REST protocol version. Server must upgrade."
            raise APIError(err_code, err_msg)
        case 40:
            err_msg = "Wrong username or password."
            raise APIError(err_code, err_msg)
        case 41:
            err_msg = "Token authentication not supported for LDAP users."
            raise APIError(err_code, err_msg)
        case 50:
            err_msg = "User is not authorized for the given operation."
            raise APIError(err_code, err_msg)
        case 60:
            err_msg = "The trial period for the Subsonic server is over."
            raise APIError(err_code, err_msg)
        case 70:
            err_msg = "The requested data was not found."
            raise APIError(err_code, err_msg)
        case _:
            err_msg = "Unknown Error Code."
            raise APIError(err_code, err_msg)

    logger.warning("Subsonic API request responded with error code %s: %s", err_code, err_msg)
    return True


async def _get_json(
    endpoint: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: int | None = None,
    check_errors: bool = True,
) -> dict[str, Any]:
    """Send an authenticated Subsonic JSON GET request."""
    request_params = _get_auth_params()
    if params is not None:
        request_params.update(params)

    session = await get_session()
    url = f"{env.SUBSONIC_SERVER}/rest/{endpoint}"
    request_kwargs: dict[str, Any] = {"params": request_params}
    if timeout is not None:
        request_kwargs["timeout"] = timeout

    async with await session.get(url, **request_kwargs) as response:
        response.raise_for_status()
        data = await response.json()

    if check_errors:
        await check_subsonic_error(data)

    return data


async def search(
    query: str,
    *,
    artist_count: int = 00,
    artist_offset: int = 0,
    album_count: int = 0,
    album_offset: int = 0,
    song_count: int = 1,
    song_offset: int = 0,
) -> SearchResults:
    """Send a search request to the subsonic API"""

    # Sanitize special characters in the user's query
    # parsed_query = urlParse.quote(query, safe='')

    search_params = {
        "query": query,  # todo: fix parsed query
        "artistCount": str(artist_count),
        "artistOffset": str(artist_offset),
        "albumCount": str(album_count),
        "albumOffset": str(album_offset),
        "songCount": str(song_count),
        "songOffset": str(song_offset),
    }

    search_data = await _get_json("search3.view", search_params, check_errors=False)
    logger.debug("Search Response: %s", search_data)

    results = SearchResults(search_data)

    return results


async def get_user_playlists() -> list[int]:
    """Retrive metadata of all playlists the Subsonic user is authorised to play"""

    query_data = await _get_json("getPlaylists.view", check_errors=False)
    if await check_subsonic_error(query_data):
        return None
    logger.debug("Playlists query response: %s", query_data)

    if "playlist" not in query_data["subsonic-response"]["playlists"]:
        query_data["subsonic-response"]["playlists"]["playlist"] = []

    return query_data["subsonic-response"]["playlists"]["playlist"]


async def get_playlist(id: str) -> Playlist:
    """Retrive the contents of a specific playlist"""

    playlist_params = {"id": id}

    playlist = await _get_json("getPlaylist.view", playlist_params, check_errors=False)
    if await check_subsonic_error(playlist):
        return None
    logger.debug("Playlist query response: %s", playlist)

    try:
        playlist = Playlist(playlist["subsonic-response"]["playlist"])
    except Exception as e:
        logger.error("Failed to parse playlist data: %s", e)
        return None

    return playlist


async def get_artist_id(query: str) -> str:
    """Send a search request to the subsonic API to return the id of an artist"""

    search_params = {
        "query": query,
        "artistCount": "1",
        "albumCount": "0",
        "albumOffset": "0",
        "songCount": "0",
        "songOffset": "0",
    }

    search_data = await _get_json("search3.view", search_params, check_errors=False)
    if await check_subsonic_error(search_data):
        return None
    artistid = search_data["subsonic-response"]["searchResult3"]["artist"][0]["id"]
    logger.debug("Artist ID: %s", artistid)

    return artistid


async def get_artist_discography(query: str) -> Album:
    """Send a search request to the subsonic API to return all albums by an artist"""

    artistid = await get_artist_id(query)

    artist_params = {"id": artistid}

    search_data = await _get_json("getArtist.view", artist_params, check_errors=False)
    if await check_subsonic_error(search_data):
        return None
    logger.debug("Search Response: %s", search_data)
    albums = search_data["subsonic-response"]["artist"].get("album", [])

    album_list: list[Album] = []

    for albuminfo in albums:
        album_data = await _get_json("getAlbum.view", {"id": albuminfo["id"]}, check_errors=False)
        if await check_subsonic_error(album_data):
            return None
        logger.debug("Search Response: %s", album_data)
        album_list.append(Album(album_data["subsonic-response"]["album"]))

    return album_list


async def get_album_art_file(cover_id: str, size: int = 300) -> str:
    """Request album art from the subsonic API"""
    # Return placeholder if cover_id is empty or None
    if not cover_id:
        return "resources/cover_not_found.jpg"

    target_path = f"cache/{cover_id}.jpg"

    # Check if the cover art is already cached (TODO: Check for last-modified date?)
    if os.path.exists(target_path):
        return target_path

    cover_params = {"id": cover_id, "size": str(size)}

    params = _get_auth_params() | cover_params

    session = await get_session()
    async with await session.get(f"{env.SUBSONIC_SERVER}/rest/getCoverArt", params=params) as response:
        logging.debug("Response: %s", response.content)
        if await check_subsonic_error(response) or response.status != 200:
            return "resources/cover_not_found.jpg"

        file = Path(target_path)
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_bytes(await response.read())

    return target_path


async def get_random_songs(
    size: int = None, genre: str = None, from_year: int = None, to_year: int = None, music_folder_id: str = None
) -> list[Song]:
    """Request random songs from the subsonic API"""
    logger.debug("Requesting random song...")
    search_params: dict[str, any] = {}

    # Handle Optional params
    if size is not None:
        search_params["size"] = size

    if genre is not None:
        search_params["genre"] = genre

    if from_year is not None:
        search_params["fromYear"] = from_year

    if to_year is not None:
        search_params["toYear"] = to_year

    if music_folder_id is not None:
        search_params["musicFolderId"] = music_folder_id

    search_data = await _get_json("getRandomSongs.view", search_params, check_errors=False)
    if await check_subsonic_error(search_data):
        return []
    logger.debug("Search Response: %s", search_data)

    results: list[Song] = []
    for item in search_data["subsonic-response"]["randomSongs"]["song"]:
        results.append(Song(item))

    return results


async def get_similar_songs(song_id: str, count: int = 1) -> list[Song]:
    """Request similar songs from the subsonic API"""

    logger.debug("Requesting similar song...")
    logger.debug("Song id: %s", song_id)

    if song_id is None:
        return []

    search_params = {"id": song_id, "count": count}

    search_data = await _get_json("getSimilarSongs.view", search_params, check_errors=False)
    logging.debug("Json Response: %s", search_data)
    subsonic_error = await check_subsonic_error(search_data)
    logger.debug("Subsonic error: %s", subsonic_error)
    if subsonic_error:
        logger.debug("Subsonic error. Returning empty list.")
        return []

    results: list[Song] = []

    if search_data["subsonic-response"]["similarSongs"] == {}:
        logging.debug("No similar songs found. Returning empty list.")
        return []

    logger.debug("Similar songs: %s", search_data["subsonic-response"]["similarSongs"]["song"])
    for item in search_data["subsonic-response"]["similarSongs"]["song"]:
        results.append(Song(item))

    logger.debug("Similar songs: %s", results)
    return results


async def stream(stream_id: str):
    """Send a stream request to the subsonic API"""

    stream_params = {
        "id": stream_id
        # TODO: handle other params
    }

    params = _get_auth_params() | stream_params

    session = await get_session()
    async with await session.get(f"{env.SUBSONIC_SERVER}/rest/stream.view", params=params, timeout=20) as response:
        response.raise_for_status()
        if response.content_type == "text/xml":
            logger.error("Failed to stream song: %s", await response.text())
            return None
        return str(response.url)


async def list_albums(
    type: Literal["random", "newest", "frequent", "recent", "starred", "alphabeticalByName", "alphabeticalByArtist"],
    size: int = None,
    offset: int = None,
    from_year: int = None,
    to_year: int = None,
    genre: str = None,
) -> list[AlbumMeta]:
    """Request a list of albums from the subsonic API"""

    logger.debug("Requesting album list...")
    search_params: dict[str, any] = {"type": type}

    # Handle Optional params
    if size is not None:
        search_params["size"] = size

    if offset is not None:
        search_params["offset"] = offset

    if from_year is not None:
        search_params["fromYear"] = from_year

    if to_year is not None:
        search_params["toYear"] = to_year

    if genre is not None:
        search_params["genre"] = genre

    search_data = await _get_json("getAlbumList.view", search_params, check_errors=False)
    if await check_subsonic_error(search_data):
        return []
    logger.debug("Search Response: %s", search_data)

    results: list[AlbumMeta] = []
    for item in search_data["subsonic-response"]["albumList"]["album"]:
        results.append(AlbumMeta(item))

    return results


async def get_album(id: str) -> Album:
    """Request an album from the subsonic API"""

    album_params = {"id": id}

    search_data = await _get_json("getAlbum.view", album_params, check_errors=False)
    if await check_subsonic_error(search_data):
        return None
    logger.debug("Search Response: %s", search_data)

    try:
        album = Album(search_data["subsonic-response"]["album"])
    except Exception as e:
        logger.error("Failed to parse album data: %s", e)
        return None

    return album
