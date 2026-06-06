''' A player object that handles playback and data for its respective guild '''

from __future__ import annotations

import asyncio
import discord

import logging
from typing import Any

from models import AudioBalanceMode, AutoplayMode
from subsonic import Song, APIError, get_random_songs, get_similar_songs, stream, get_album_art_file

logger = logging.getLogger(__name__)

def build_audio_filter(mode: AudioBalanceMode) -> str | None:
    ''' Build an FFmpeg audio filter chain for the selected balance mode. '''

    match mode:
        case AudioBalanceMode.OFF:
            return None
        case AudioBalanceMode.REPLAYGAIN:
            return "volume=replaygain=track:replaygain_noclip=1"
        case AudioBalanceMode.DYNAMIC:
            return ",".join([
                "volume=replaygain=track:replaygain_noclip=1",
                "dynaudnorm=f=250:g=15:p=0.95:m=10",
                "alimiter=limit=0.95",
            ])

    return None

class Player():
    ''' Class that represents an audio player '''
    def __init__(self, guild_properties: Any) -> None:
        self._data = {
            "current-song": None,
            "current-position": 0,
            "queue": [],
            "channel": None,
        }
        self._guild_properties = guild_properties
        self._player_loop = None
        self._stopped = False

    @property
    def current_song(self) -> Song:
        '''The current song'''
        return self._data["current-song"]

    @current_song.setter
    def current_song(self, song: Song) -> None:
        self._data["current-song"] = song

    @property
    def current_position(self) -> int:
        ''' The current position for the current song, in seconds. '''
        return self._data["current-position"]

    @current_position.setter
    def current_position(self, position: int) -> None:
        ''' Set the current position for the current song, in seconds. '''
        self._data["current-position"] = position

    @property
    def queue(self) -> list[Song]:
        ''' The current audio queue. '''
        return self._data["queue"]

    @queue.setter
    def queue(self, value: list) -> None:
        self._data["queue"] = value

    @property
    def player_loop(self) -> asyncio.AbstractEventLoop:
        ''' The player loop '''
        return self._player_loop
    
    @player_loop.setter
    def player_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._player_loop = loop

    @property
    def channel(self) -> discord.TextChannel:
        ''' The text channel to send player notifications to '''
        return self._data["channel"]

    @channel.setter
    def channel(self, channel: discord.TextChannel) -> None:
        self._data["channel"] = channel

    @property
    def guild_properties(self) -> Any:
        ''' The guild's saved player properties. '''
        return self._guild_properties

    async def _send(self, title: str, description: str = None, thumbnail: str = None) -> None:
        ''' Sends a notification embed to the player's channel '''
        if self.channel is None:
            logger.warning("Cannot send player notification: no channel set")
            return
        embed = discord.Embed(color=discord.Color(0x50C470), title=title, description=description)
        file = discord.utils.MISSING
        if thumbnail is not None:
            try:
                file = discord.File(thumbnail, filename="image.png")
                embed.set_thumbnail(url="attachment://image.png")
            except Exception as e:
                logger.error(f"Failed to attach thumbnail: {e}")
        await self.channel.send(file=file, embed=embed)





    async def stream_track(self, song: Song, voice_client: discord.VoiceClient) -> None:
        ''' Streams a track from the Subsonic server to a connected voice channel, and updates guild data accordingly '''

        # Make sure the voice client is available and connected
        if voice_client is None:
            await self._send("Error", "Not currently connected to a voice channel.")
            return

        # Check if the voice client is still connected
        if not voice_client.is_connected():
            logger.error("Voice client is not connected")
            await self._send("Error", "Voice connection was lost. Please try again.")
            return

        # Make sure the bot isn't already playing music
        if voice_client.is_playing():
            await self._send("Error", "Already playing.")
            return

        # Get the stream from the Subsonic server, using the provided song's ID
        ffmpeg_options = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"}
        audio_filter = build_audio_filter(self.guild_properties.audio_balance_mode)
        if audio_filter is not None:
            ffmpeg_options["options"] = f"-filter:a {audio_filter}"
        try:
            stream_url = await stream(song.song_id)
            if not stream_url:
                logger.error("Failed to get stream URL")
                await self._send("Error", "Failed to get audio stream. Please try again.")
                return

            audio_src = discord.FFmpegOpusAudio(stream_url, **ffmpeg_options)
        except APIError as err:
            logger.error(f"API Error streaming song, Code {err.errorcode}: {err.message}")
            await self._send("Error", f"API error while streaming song: {err.message}")
            return
        except Exception as e:
            logger.error(f"Unexpected error getting audio stream: {e}")
            await self._send("Error", "An error occurred while preparing the audio. Please try again.")
            return

        # Begin playing the song
        loop = asyncio.get_running_loop()
        self.player_loop = loop

        # Handle playback finished
        async def playback_finished(error):
            if error:
                logger.error(f"An error occurred while playing the audio: {error}")
                return

            if self._stopped:
                logger.debug("Playback stopped intentionally, not advancing queue.")
                self._stopped = False
                return

            logger.debug("Playback finished.")
            try:
                # Only proceed if voice client is still connected
                if voice_client and voice_client.is_connected():
                    await self.play_audio_queue(voice_client)
                else:
                    logger.warning("Voice client disconnected, cannot continue queue playback")
            except Exception as e:
                logger.error(f"Failed to schedule play_audio_queue: {e}")

        # Try to play the audio with retry logic
        max_attempts = 3
        attempt = 0

        while attempt < max_attempts:
            try:
                # Check again if voice client is still connected before playing
                if not voice_client.is_connected():
                    logger.error("Voice client disconnected before playing")
                    await self._send("Error", "Voice connection was lost. Please try again.")
                    return

                voice_client.play(audio_src, after=lambda e: loop.create_task(playback_finished(e)))
                logger.info(f"Started playing: {song.title} by {song.artist}")
                return  # Success, exit the function
            except discord.ClientException as e:
                logger.error(f"Discord client exception while playing audio (attempt {attempt+1}): {e}")
                attempt += 1
                if attempt >= max_attempts:
                    await self._send("Error", "Failed to play audio after multiple attempts. Please try again.")
                    return
                await asyncio.sleep(1)  # Wait before retrying
            except Exception as err:
                logger.error(f"An error occurred while playing the audio: {err}")
                await self._send("Error", "An error occurred while playing the audio. Please try again.")
                return


    async def handle_autoplay(self, prev_song_id: str=None) -> bool:
        ''' Handles populating the queue when autoplay is enabled '''

        autoplay_mode = self.guild_properties.autoplay_mode
        logger.debug("Handling autoplay...")
        logger.debug(f"Autoplay mode: {autoplay_mode}")
        logger.debug(f"Queue: {self.queue}")
        # If queue is notempty or autoplay is disabled, don't handle autoplay
        if self.queue != [] or autoplay_mode is AutoplayMode.NONE:
            return False

        # If there was no previous song provided, we default back to selecting a random song
        if prev_song_id is None:
            autoplay_mode = AutoplayMode.RANDOM
            logging.info("No previous song ID provided. Defaulting to random.")

        songs = []

        try:
            match autoplay_mode:
                case AutoplayMode.RANDOM:
                    songs = await get_random_songs(size=1)
                case AutoplayMode.SIMILAR:
                    logger.debug(f"Prev song ID: {prev_song_id}")
                    songs = await get_similar_songs(song_id=prev_song_id, count=1)

        except APIError as err:
            logging.error(f"API Error fetching song for autoplay, Code {err.errorcode}: {err.message}")
        
        logger.debug(f"Autoplay song: {songs}")

        # If there's no match, throw an error
        if len(songs) == 0:
            await self._send("Error", "Failed to obtain a song for autoplay.")
            return False
        
        self.queue.append(songs[0])
        return True


    async def play_audio_queue(self, voice_client: discord.VoiceClient) -> None:
        ''' Plays the audio queue '''

        # Check if the bot is connected to a voice channel; it's the caller's responsibility to open a voice channel
        if voice_client is None:
            await self._send("Error", "Not currently connected to a voice channel.")
            return

        # Check if the bot is already playing something
        if voice_client.is_playing():
            return

        # Check if the queue contains songs
        if self.queue != []:
            # Pop the first item from the queue and stream the track
            song = self.queue.pop(0)
            self.current_song = song
            cover_art = await get_album_art_file(song.cover_id)
            desc = f"**{song.title}** - *{song.artist}*\n{song.album} ({song.duration_printable})"
            await self._send("Now Playing:", desc, cover_art)
            await self.stream_track(song, voice_client)
        else:
            logger.debug("Queue is empty.")
            logger.debug("Current song: %s", self.current_song)
            if self.current_song is not None:
                prev_song_id = self.current_song.song_id
                self.current_song = None
            else:
                prev_song_id = None
            # Handle autoplay if queue is empty
            if await self.handle_autoplay(prev_song_id=prev_song_id):
                await self.play_audio_queue(voice_client)
                return
            # If the queue is empty, playback has ended; we should let the user know
            await self._send("Playback ended")


    def stop(self, voice_client: discord.VoiceClient) -> None:
        ''' Stops playback without advancing the queue '''
        self._stopped = True
        self.current_song = None
        voice_client.stop()

    async def skip_track(self, voice_client: discord.VoiceClient) -> None:
        ''' Skips the current track and plays the next one in the queue '''

        # Check if the bot is connected to a voice channel; it's the caller's responsibility to open a voice channel
        if voice_client is None:
            await self._send("Error", "Not currently connected to a voice channel.")
            return
        logger.debug("Skipping track...")
        # Check if the bot is already playing something
        if voice_client.is_playing():
            voice_client.stop()
            await self._send("Skipped track")
        else:
            await self._send("Error", "No track is playing.")
