import asyncio
import os
import time
import typing
import random
import json

import wavelink

import discord
import wavelink
from wavelink.ext import spotify
from discord.ext import commands

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from tinydb import TinyDB, Query

LAVALINK_PASS = os.getenv("LAVALINK_PASS")
LAVALINK_PORT = os.getenv("LAVALINK_PORT")
LAVALINK_ADDRESS = os.getenv("LAVALINK_ADDRESS")
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

client_credentials_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        self.db = TinyDB('cogs/db/history.json')
        bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self) -> None:
        await self.bot.wait_until_ready()

        await wavelink.NodePool.create_node(
            bot=self.bot,
            host=LAVALINK_ADDRESS,
            port=LAVALINK_PORT,
            password=LAVALINK_PASS,
            spotify_client=spotify.SpotifyClient(
                client_id=os.getenv("spotifyClientId"),
                client_secret=os.getenv("spotifyClientSecret"),
            ),
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild.voice_client:
            return
        
        if member.guild == member.guild.voice_client.guild:
            if len(member.guild.voice_client.channel.members) == 1:
                await member.guild.voice_client.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        print(f"Node {node.identifier} is ready.")

    @commands.Cog.listener()
    async def on_wavelink_track_end(
        self, player: wavelink.Player, track: wavelink.Track, reason):
        try:
            ctx = player.ctx
        except AttributeError as e:
            ctx.send(f"An error occured: {e}")
        

        vc = ctx.voice_client

        if vc.loop:
            return await vc.play(track)
        try:
            next_song = vc.queue.get()
        except wavelink.errors.QueueEmpty as e:
            return
        await vc.play(next_song)
        mbed = discord.Embed(
            title=f"▶️ | Now playing {next_song}...",
            description=f"**[{next_song.title}]({next_song.uri})**",
            colour=discord.Colour.yellow(),
        )
        await ctx.send(embed=mbed)

    @commands.command(
        name="connect",
        description="Connects to VC",
        aliases=["join", "con"],
        usage="connect",
        help="Will connect to the voice channel you are in. If you are not in a voice channel, you can specify one.",
    )
    async def connect(self, ctx, *, channel: typing.Optional[discord.VoiceChannel]):
        if channel is None:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                return await ctx.send(
                    "No voice channel to connect to. Please either provide one or join one."
                )

        self.node = wavelink.NodePool.get_node()
        self.player = self.node.get_player(ctx.guild)

        if self.player is not None and self.player.is_connected():
            await self.player.move_to(ctx.author.voice.channel)

        await channel.connect(cls=wavelink.Player)

        mbed = discord.Embed(
            title=f"🔗 | Connected to {channel.name}.",
            colour=discord.Colour.yellow(),
        )

        await ctx.send(embed=mbed)

    @commands.command(
        name="similarsongs",
        description="Similar Songs",
        aliases=["similar"],
        usage="similarsongs <number of songs> <song name> (<artist>)",
        help="Gives a list of similar songs to the one you specify.",
    )
    async def similarsongs(self, ctx, number: int):
        vc: wavelink.Player = ctx.voice_client
        info = vc.source.info
        song_name = info["title"]
        results = sp.search(q=song_name, limit=1)
        song_id = results['tracks']['items'][0]['id']
        
        recommendations = sp.recommendations(seed_tracks=[song_id], limit=number)
        
        trackz = []

        for track in recommendations['tracks']:
            name = (track['name'] + ' ' + track['artists'][0]['name'])
            trackz.append(name)
        
        for track in trackz:
            ytsong = await wavelink.YouTubeTrack.search(query=track, return_first=True)

            ctx.voice_client.queue.put(ytsong)
        
        embed = discord.Embed(
            title=f"🔗 | Added {number} similar songs to the queue.",
            colour=discord.Colour.yellow(),
        )

        track_names = []

        for track in recommendations['tracks']:
            name = (track['name'] + ' - ' + track['artists'][0]['name'])
            track_names.append(name)
        
        for track in track_names:
            embed.add_field(name=track, value='', inline=False)

        await ctx.send(embed=embed)

    @commands.command(
        name="genre",
        description="Genre",
        aliases=["gen"],
        usage="genre <genre> <number of songs>",
        help="Gives a list of songs from the genre you specify.",
    )
    async def genre(self, ctx, genre: str, number: int):
        # if number is missing, default to 5
        if number == None:
            number = 5
        
        genres = sp.recommendation_genre_seeds().get('genres')
        if not ctx.voice_client:
            await self.connect(ctx, channel=ctx.author.voice.channel)
        vc: wavelink.Player = ctx.voice_client
        ctx: commands.Context = ctx

        if genre not in genres or genre == None:
            mbed = discord.Embed(
                title=f"🔗 | Genre not found. Please choose from the following:",
                colour=discord.Colour.yellow(),
                description=genres
            )
            return await ctx.send(embed=mbed)



        channel = ctx.author.voice.channel
        if not ctx.author.voice or not channel:
            return await ctx.send("You are not connected to any voice channel!")

        if not ctx.voice_client:
            await self.connect(ctx, channel=channel)

        vc: wavelink.Player = ctx.voice_client
            
        results = sp.recommendations(seed_genres=[genre], limit=number)
        trackz = []
    
        for idx, track in enumerate(results['tracks']):
            print(f"{idx+1}. {track['name']} - {track['artists'][0]['name']}")
            trackz.append(track['name'] + ' ' + track['artists'][0]['name'])
        
        first_track_played = False
        for track in trackz:
            ytsong = await wavelink.YouTubeTrack.search(query=track, return_first=True)
            
            if not first_track_played and not vc.is_playing():
                await vc.play(ytsong)
                first_track_played = True
            else:
                await vc.queue.put_wait(ytsong)
        
        embed = discord.Embed(
            title=f"🔗 | Added {number} songs to the queue.",
            colour=discord.Colour.yellow(),
        )
        for idx, track in enumerate(trackz):
            embed.add_field(name=f"{idx+1}. {track}", value="")

        await ctx.send(embed=embed)
    
        if not ctx.voice_client.is_playing():
            await self.play(vc.queue.get())


    @commands.command(
        name="clear",
        description="Clears the queue",
        aliases=["clr", "cl"],
        usage="clear",
        help="Clears the queue.",
    )
    async def clear(self, ctx):
        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.send("I am not currently connected to voice!")

        vc.queue.clear()

        await ctx.send("The queue has been cleared.")

    @commands.command(
        name="nowplaying",
        aliases=["np", "playing"],
        description="Now Playing",
        usage="nowplaying",
        help="Shows the song that is currently playing. It will show the title, duration, current position, author, source, and URL.",
    )
    async def nowplaying(self, ctx):
        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.send("I am not currently connected to voice!")
        try:
            duration = vc.source.info["length"]
            info = vc.source.info
            cur_pos = vc.position
        except AttributeError:
            return await ctx.send("I am not currently playing anything!")

        duration = time.strftime("%M:%S", time.gmtime(duration))
        cur_pos = time.strftime("%M:%S", time.gmtime(cur_pos))
        embed = discord.Embed(title="Now Playing", color=discord.Colour.yellow())
        embed.add_field(name=info["title"], value=" ", inline=False)
        embed.add_field(name="Uploader", value=info["author"], inline=True)
        embed.add_field(name="Time", value=f"{cur_pos}/{duration}", inline=True)
        embed.add_field(name="Source", value=info["sourceName"].upper(), inline=True)
        embed.add_field(
            name="URL", value=f'[{info["title"]}]({info["uri"]})', inline=False
        )
        embed.set_footer(text="Harmony")

        await ctx.send(embed=embed)

    @commands.command()
    async def radio(self, ctx):
        vc: wavelink.Player = ctx.voice_client

        if getattr(vc, "radio_mode", False):
            setattr(vc, "radio_mode", False)
            await ctx.send("Radio mode turned off.")
        else:
            setattr(vc, "radio_mode", True)
            await ctx.send("Radio mode turned on.")

    @commands.command(
        name="play",
        description="Play Song",
        aliases=["p"],
        usage="play <song name/URL>",
        help="Play a song with the given search query or URL. If the bot is already playing a song, it will add the song to the queue.",
    )
    async def play(self, ctx, *, track: wavelink.YouTubeTrack):
        async with ctx.typing():

            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.send("You are not connected to any voice channel!")

            if not ctx.voice_client:
                await self.connect(ctx, channel=ctx.author.voice.channel)
            vc: wavelink.Player = ctx.voice_client

            if not vc.is_playing():
                await vc.play(track)
                mbed = discord.Embed(
                    title=f"🎶 | Now playing {track}",
                    description=f"Requested by {ctx.author.mention}", 
                    colour=discord.Colour.yellow(),
                )
                await ctx.send(embed=mbed)
            else:
                await vc.queue.put_wait(track)
                mbed = discord.Embed(
                    title=f"🎶 | Added {track} to the queue...",
                    description=f"Requested by {ctx.author.mention}",
                    colour=discord.Colour.yellow(),
                )
        
                await ctx.send(embed=mbed)

            vc.ctx = ctx
            setattr(vc, "loop", False)

            data = {
                "song_name": track.title,
                "song_url": track.uri,
                "requestor": ctx.author.name,
                "time": f"{time.strftime('%H:%M:%S', time.localtime())}|{time.strftime('%m/%d/%Y', time.localtime())}",
            }
            self.db.insert(data)

            if getattr(vc, "radio_mode", False) and vc.queue.is_empty:
                song_id = sp.search(q=track.title, limit=1)['tracks']['items'][0]['id']
                recommendations = sp.recommendations(seed_tracks=[song_id], limit=1)
                similar_song = recommendations['tracks'][0]['name'] + ' ' + recommendations['tracks'][0]['artists'][0]['name']
                similar_track = await wavelink.YouTubeTrack.search(query=similar_song, return_first=True)
                await vc.queue.put(similar_track)


    @commands.command(
        name="skip",
        description="Skip",
        aliases=["sk"],
        usage="skip",
        help="Skip the current song. If the bot is playing a song, it will skip to the next song in the queue. If the queue is empty, it will stop playing.",
    )
    async def skip(self, ctx):

        vc = ctx.voice_client

        if vc.is_connected():
            if vc.is_playing():
                await vc.stop()
                mbed = discord.Embed(
                    title=" ⏭️ | Skipped current music",
                    colour=discord.Colour.yellow(),
                )
            else:
                mbed = discord.Embed(
                    title="Not playing any music right now. Fuark.",
                    colour=discord.Colour.yellow(),
                )
        else:
            mbed = discord.Embed(
                title="Not connected to any voice channels right now. Fuark.",
                colour=discord.Colour.yellow(),
            )

        await ctx.send(embed=mbed)

    @commands.command(
        name="pause",
        description="Pause",
        aliases=["pa"],
        usage="pause",
        help="Pause the current song. If the bot is playing a song, it will pause the song. If the bot is already paused, it will resume the song.",
    )
    async def pause(self, ctx):
        if self.player is None:
            return await ctx.send("ID4 is not connected to any voice channels. Fuark.")

        if not self.player.is_paused():
            if self.player.is_playing():
                await self.player.pause()
                mbed = discord.Embed(
                    title="⏸️ | Playback paused",
                    colour=discord.Colour.yellow(),
                )
            else:
                mbed = discord.Embed(
                    title="Not playing any music right now. Fuark.",
                    colour=discord.Colour.yellow(),
                )

        return await ctx.send(embed=mbed)

    @commands.command(
        name="resume",
        description="Resume",
        aliases=["continue"],
        usage="resume",
        help="Resume the current song. If the bot is playing a song, it will resume the song.",
    )
    async def resume(self, ctx):
        if self.player is None:
            return await ctx.send("ID4 is not connected to any voice channels. Fuark.")

        if not self.player.is_paused():
            await self.player.resume()
            mbed = discord.Embed(
                title=" ▶️ | Playback resumed",
                colour=discord.Colour.yellow(),
            )
        else:
            mbed = discord.Embed(
                title="Playback not paused. Fuark.",
                colour=discord.Colour.yellow(),
            )

        return await ctx.send(embed=mbed)

    @commands.command(
        name="seek",
        description="Seek forward a given number of seconds",
        usage="seek <seconds>",
        help="Skip forward a given number of seconds in the current track.",
    )
    async def seek(self, ctx, seconds: int):
        if not ctx.voice_client:
            await ctx.send("I am not currently playing any music.")
            return

        vc = ctx.voice_client
        current_time = vc.position
        new_time = current_time + (seconds * 1000)
        await vc.seek(new_time)
        await ctx.send(f"Seeked forward {seconds} seconds.")

    @commands.command(
        name="queue",
        description="Music Queue",
        aliases=["q"],
        usage="queue",
        help="Get the music queue. If the bot is playing a song, it will show the queue. If the queue is empty, it will show the current song.",
    )
    async def queue(self, ctx) -> None:
        vc: wavelink.Player = ctx.voice_client


        if not vc or not vc.is_connected():
            return await ctx.send("I am not currently connected to voice!")
        
        player: wavelink.Player = ctx.voice_client

        if not player.queue:
            return await ctx.send("There are no songs in the queue.")
        
        embed = discord.Embed(
            title="Music Queue",
            description=f"{len(player.queue)} songs in queue",
            colour=discord.Colour.yellow(),
        )
        for track in player.queue:
            embed.add_field(
                name=f"{track.title} - {track.info['author']}",
                value=f"{track.info['uri']}",
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(
        name="disconnect",
        description="Disconnect",
        aliases=["dc", "leave"],
        usage="disconnect",
        help="Disconnect the bot from the voice channel. If the bot is playing a song, it will disconnect from the voice channel.",
    )
    async def disconnect(self, ctx) -> None:
        vc: wavelink.Player = ctx.voice_client

        try:
            await vc.disconnect()
        except Exception as e:
            print(e)
        mbed = discord.Embed(
            title="🔌 | Disconnected from voice channel",
            colour=discord.Colour.yellow(),
        )

        await ctx.send(embed=mbed, delete_after=10)

    @commands.command(
        name="history",
        description="History",
        aliases=["h"],
        usage="history",
        help="Get the history of the last 10 songs.",
    )
    async def history(self, ctx) -> None:
        with open("cogs\\db\\history.json", "r") as read_file:
            data = json.load(read_file)
        embed = discord.Embed(
            title="History",
            description=f"Last {len(data)} songs played",
            colour=discord.Colour.yellow(),
        )
        for track in data:
            embed.add_field(
                name=f"{track['title']} - {track['author']}",
                value=f"{track['uri']}",
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(
        name="volume",
        description="Adjust Voume",
        aliases=["vol"],
        usage="volume <volume>",
        help="Change the volume of the player. If no volume is specified, it will return the current volume. The volume can be set from 0 to 150."""
    )
    async def volume(self, ctx, *, volume: int):
        vc: wavelink.Player = ctx.voice_client

        if volume is None:
            return await ctx.send(f"🔊 | Current volume: {vc.volume}")

        if 0 < volume < 150:
            await vc.set_volume(volume)
            await ctx.send(f"🔊 | Volume set to {volume}")
        else:
            await ctx.send("Volume must be between 0 and 150")

    @commands.group(invoke_without_command=True)
    async def playlist(self, ctx):
        await ctx.send_help(ctx.command)

    @playlist.command(name="save")
    async def playlist_save(self, ctx, playlist_name, *, song: wavelink.YouTubeTrack):
        self.db.insert({'user_id': ctx.author.id, 'playlist_name': playlist_name, 'song_name': song.title, 'song_url': song.uri})
        await ctx.send(f"Song '{song.title}' added to playlist '{playlist_name}'.")

    @playlist.command(name="list")
    async def playlist_list(self, ctx):
        User = Query()
        playlists = self.db.search(User.user_id == ctx.author.id)
        playlist_names = set([playlist['playlist_name'] for playlist in playlists])
        await ctx.send(f"Your playlists: {', '.join(playlist_names)}")

    @playlist.command(name="view")
    async def playlist_view(self, ctx, playlist_name):
        User = Query()
        playlists = self.db.search((User.user_id == ctx.author.id) & (User.playlist_name == playlist_name))
        if not playlists:
            await ctx.send("You do not have a playlist with that name.")
        else:
            songs = [playlist['song_name'] for playlist in playlists]
            await ctx.send(f"Songs in playlist '{playlist_name}': {', '.join(songs)}")


async def setup(bot):
    await bot.add_cog(Music(bot))
