import discord
from discord.ext import commands
from utils.chat import chat_with_ollama
from utils.pick_replik import pick_random
from pala_replik import leave_replik
from utils.spoti import search_spotify_track, search_user_playlist, get_playlist_tracks, extract_playlist_id
import yt_dlp
import asyncio
import random
from utils.config import Discord as DiscordConfig, Audio as AudioConfig, Queue as QueueConfig

# Global queue for playlist playback
music_queue = []
current_track_index = 0

print(f"Opus loaded: {discord.opus.is_loaded()}")
# Try to manually load Opus
if not discord.opus.is_loaded():
    discord.opus.load_opus(DiscordConfig.OPUS_LIBRARY_PATH)

# Create bot instance
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=DiscordConfig.COMMAND_PREFIX, intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.event
async def on_voice_state_update(member, before, after):
    """Greet users when they join a voice channel (where the bot is present)"""
    # Ignore bot's own voice state changes
    if member.bot:
        return

    # Check if user joined a voice channel (wasn't in one before, now is)
    if before.channel is None and after.channel is not None:
        # Check if bot is in the same voice channel
        if bot.voice_clients:
            for voice_client in bot.voice_clients:
                if voice_client.channel == after.channel:
                    # User joined the same channel as the bot
                    # Find a text channel to send the greeting
                    text_channel = None

                    # Try to find the channel where bot was last commanded from
                    # Or just use the first text channel the bot can see in this guild
                    for channel in member.guild.text_channels:
                        if channel.permissions_for(member.guild.me).send_messages:
                            text_channel = channel
                            break

                    if text_channel:
                        greetings = [
                            f"Hoş geldin {member.display_name}, babayiğit!",
                            f"Mekandayız {member.display_name}! Ne var ne yok?",
                            f"{member.display_name} geldi. Hayırlı nöbetler babayiğit!",
                            f"Selam {member.display_name}. İş var mı?",
                            f"{member.display_name}, aramıza hoş geldin dayı!",
                        ]
                        await text_channel.send(random.choice(greetings))

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Process commands first
    await bot.process_commands(message)

    # Check if bot is mentioned
    if bot.user and bot.user.mentioned_in(message) and not message.mention_everyone:
        # Remove the bot mention from the message content
        message_content = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
        author_name = message.author.name

        prompt = f"""
        Kullanici: {author_name}, Mesaj: {message_content}\n:
        Faruk:"""
        chat_response = await chat_with_ollama(prompt)

        await message.reply(f"{chat_response}")

@bot.command(name='join', help='Joins the voice channel you are in.')
async def join(ctx):
    """Join the voice channel of the user who invoked the command."""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Geldim babayigit! Mekandayiz, yani {channel.name}")
    else:
        await ctx.send("You need to be in a voice channel first!")

@bot.command(name='leave', help='Leaves the voice channel.')
async def leave(ctx):
    """Leave the voice channel."""
    global music_queue, current_track_index

    if ctx.voice_client:
        # Clear the queue when leaving
        music_queue = []
        current_track_index = 0

        await ctx.voice_client.disconnect()
        await ctx.send(pick_random(leave_replik))
    else:
        await ctx.send("Bos bos konusma, ben hicbir yerde degilim!")

@bot.command(name='play_local', help='Plays a local audio file.')
async def play_local(ctx, audio_file: str = ""):
    """Play a local audio file"""
    voice_client = ctx.voice_client

    # If bot is not connected to a voice channel, join the user's channel
    if not voice_client or not voice_client.is_connected():
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            voice_client = await channel.connect()
            await ctx.send(f"Geldim babayigit! Mekandayiz, yani {channel.name}")
        else:
            await ctx.send("Bidi bidi yapma kral. Kalibinin adami ol, once bir sesli kanala gir!")
            return

    source = discord.FFmpegPCMAudio(f'{AudioConfig.LOCAL_FILES_DIRECTORY}{audio_file}.mp3')
    voice_client.play(source)

@bot.command()
async def play(ctx, *, song_name):
    """Play a song from Spotify (finds it on YouTube and streams)"""
    # Check if user is in a voice channel
    if not ctx.author.voice:
        await ctx.send("Bidi bidi yapma kral. Önce bir sesli kanala gir!")
        return

    # Search for the track on Spotify to get proper metadata
    await ctx.send(f"Spotify'da '{song_name}' arıyorum...")
    track_info = search_spotify_track(song_name)

    if not track_info:
        await ctx.send(f"'{song_name}' bulunamadı babayiğit. Başka bir şey dene.")
        return

    await ctx.send(f"Buldum: {track_info['name']} - {track_info['artist']}")

    # Connect to voice channel if not already connected
    if not ctx.voice_client:
        voice_client = await ctx.author.voice.channel.connect()
        await ctx.send(f"Geldim babayigit! Mekandayiz, yani {ctx.author.voice.channel.name}")
    else:
        voice_client = ctx.voice_client

    # Stop any currently playing audio
    if voice_client.is_playing():
        voice_client.stop()

    try:
        # Search YouTube for the track (Spotify metadata → YouTube search)
        await ctx.send("YouTube'da buluyorum, biraz bekle...")
        youtube_query = f"{track_info['name']} {track_info['artist']}"

        # yt-dlp options for streaming
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch',
            'source_address': '0.0.0.0',  # Bind to ipv4 since ipv6 addresses cause issues sometimes
        }

        # Run yt-dlp in executor to avoid blocking
        loop = asyncio.get_event_loop()

        def get_youtube_url():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore
                info = ydl.extract_info(f"ytsearch:{youtube_query}", download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url', '')

        url = await loop.run_in_executor(None, get_youtube_url)

        # Create FFmpeg audio source from YouTube stream
        audio_source = discord.FFmpegPCMAudio(
            url,  # type: ignore
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options='-vn'
        )
        source = discord.PCMVolumeTransformer(audio_source, volume=1.0)

        # Play the audio
        voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)
        await ctx.send(f"🎵 Çalıyor: {track_info['name']} - {track_info['artist']}")

    except Exception as e:
        await ctx.send(f"Bir sorun oldu babayiğit: {str(e)}")

@bot.command(name='stop', help='Stops the currently playing audio.')
async def stop(ctx):
    """Stop playing audio in the voice channel."""
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        # Clean up Spotify process if it exists
        if hasattr(voice_client, '_spotify_process'):
            voice_client._spotify_process.terminate()
            delattr(voice_client, '_spotify_process')
        await ctx.send("Durdurdum sesi!")
    elif voice_client:
        await ctx.send("Zaten bir sey calmiyor ki!")
    else:
        await ctx.send("Sesli kanalda degilim ki!")

async def play_track_from_queue(ctx, track_info):
    """Helper function to play a single track and handle auto-advance to next in queue.

    Args:
        ctx: Discord command context
        track_info: Dictionary with 'name' and 'artist' keys
    """
    global current_track_index

    voice_client = ctx.voice_client

    # Stop any currently playing audio
    if voice_client and voice_client.is_playing():
        voice_client.stop()

    try:
        # Search YouTube for the track
        youtube_query = f"{track_info['name']} {track_info['artist']}"

        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch',
            'source_address': '0.0.0.0',
        }

        loop = asyncio.get_event_loop()

        def get_youtube_url():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore
                info = ydl.extract_info(f"ytsearch:{youtube_query}", download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url', '')

        url = await loop.run_in_executor(None, get_youtube_url)

        # Create FFmpeg audio source
        audio_source = discord.FFmpegPCMAudio(
            url,  # type: ignore
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options='-vn'
        )
        source = discord.PCMVolumeTransformer(audio_source, volume=1.0)

        # Define callback for when track finishes
        def after_playing(error):
            if error:
                print(f'Player error: {error}')

            # Auto-advance to next track in queue
            global current_track_index
            if current_track_index < len(music_queue) - 1:
                current_track_index += 1
                next_track = music_queue[current_track_index]

                # Schedule the next track to play
                asyncio.run_coroutine_threadsafe(
                    play_track_from_queue(ctx, next_track),
                    bot.loop
                )

        # Play the audio with auto-advance callback
        voice_client.play(source, after=after_playing)

        return True

    except Exception as e:
        print(f"Error playing track: {e}")
        return False

@bot.command()
async def playlist(ctx, *, query):
    """Play a Spotify playlist - searches your playlists first, then accepts public URLs

    Use --shuffle or -s flag to shuffle: !playlist --shuffle workout
    """
    global music_queue, current_track_index

    # Check if user is in a voice channel
    if not ctx.author.voice:
        await ctx.send("Bidi bidi yapma kral. Önce bir sesli kanala gir!")
        return

    # Check for shuffle flag
    shuffle_mode = False
    if '--shuffle' in query or '-s' in query:
        shuffle_mode = True
        query = query.replace('--shuffle', '').replace('-s', '').strip()

    # Try to find in user's playlists first
    await ctx.send(f"'{query}' listeni arıyorum...")
    playlist_info = search_user_playlist(query)

    # If not found, try to extract from URL
    if not playlist_info:
        playlist_id = extract_playlist_id(query)

        if not playlist_id:
            await ctx.send(f"'{query}' adında bir liste bulamadım babayiğit. Tekrar dene.")
            return

        # Get playlist info from URL
        try:
            playlist_data = get_playlist_tracks(playlist_id)
            if not playlist_data:
                await ctx.send("Bu listeyi açamadım. Geçerli bir Spotify linki mi?")
                return

            # Use first track to get playlist info (we already have tracks)
            playlist_info = {
                'id': playlist_id,
                'name': 'Spotify Playlist',
                'track_count': len(playlist_data)
            }
            music_queue = playlist_data
        except Exception as e:
            await ctx.send(f"Liste yüklenirken sorun çıktı: {str(e)}")
            return
    else:
        # Found in user's playlists, fetch the tracks
        await ctx.send(f"Buldum: '{playlist_info['name']}' - {playlist_info['track_count']} şarkı yükleniyor...")
        try:
            music_queue = get_playlist_tracks(playlist_info['id'])
        except Exception as e:
            await ctx.send(f"Liste yüklenirken sorun çıktı: {str(e)}")
            return

    if not music_queue:
        await ctx.send("Liste boş babayiğit!")
        return

    # Check queue size limit
    max_size = QueueConfig.MAX_SIZE
    if max_size and len(music_queue) > max_size:
        await ctx.send(f"Liste çok uzun babayiğit! Maksimum {max_size} şarkı alabiliyorum. İlk {max_size} şarkıyı yüklüyorum...")
        music_queue = music_queue[:max_size]

    # Shuffle if requested
    if shuffle_mode:
        random.shuffle(music_queue)
        await ctx.send("🔀 Listeyi karıştırdım babayiğit!")

    # Reset queue index
    current_track_index = 0

    # Connect to voice channel if not already connected
    if not ctx.voice_client:
        voice_client = await ctx.author.voice.channel.connect()
        await ctx.send(f"Geldim babayiğit! Mekandayız, yani {ctx.author.voice.channel.name}")

    # Start playing the first track
    first_track = music_queue[0]
    shuffle_msg = " (karışık)" if shuffle_mode else ""
    await ctx.send(f"🎵 Liste başlıyor: {playlist_info['name']}{shuffle_msg} ({len(music_queue)} şarkı)")
    await ctx.send(f"İlk şarkı: {first_track['name']} - {first_track['artist']}")

    success = await play_track_from_queue(ctx, first_track)

    if not success:
        await ctx.send("İlk şarkıyı çalarken sorun çıktı babayiğit.")

@bot.command()
async def skip(ctx):
    """Skip to the next track in the playlist queue"""
    global current_track_index

    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_playing():
        await ctx.send("Zaten bir şey çalmıyor ki babayiğit!")
        return

    if not music_queue or current_track_index >= len(music_queue) - 1:
        await ctx.send("Sırada başka şarkı yok. Liste bitti!")
        return

    # Stop current track (this will trigger the auto-advance)
    voice_client.stop()
    await ctx.send("Atladım, sıradaki çalıyor...")

@bot.command()
async def queue(ctx):
    """Show the next tracks in the playlist queue"""
    global current_track_index

    if not music_queue:
        await ctx.send("Liste boş babayiğit!")
        return

    # Show currently playing track
    if current_track_index < len(music_queue):
        current = music_queue[current_track_index]
        message = f"🎵 **Şu an çalıyor:** {current['name']} - {current['artist']}\n\n"
    else:
        message = "**Şu an çalan yok**\n\n"

    # Show next 10 tracks
    remaining = len(music_queue) - current_track_index - 1
    if remaining > 0:
        message += f"**Sırada {remaining} şarkı var:**\n"
        next_tracks = music_queue[current_track_index + 1:current_track_index + 11]

        for i, track in enumerate(next_tracks, 1):
            message += f"{i}. {track['name']} - {track['artist']}\n"

        if remaining > 10:
            message += f"\n...ve {remaining - 10} şarkı daha"
    else:
        message += "**Sırada şarkı yok**"

    await ctx.send(message)

@bot.command()
async def clear(ctx):
    """Clear the playlist queue"""
    global music_queue, current_track_index

    if not music_queue:
        await ctx.send("Liste zaten boş babayiğit!")
        return

    music_queue = []
    current_track_index = 0

    # Stop current playback
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()

    await ctx.send("Listeyi temizledim. Hepsi gitti!")

@bot.command()
async def shuffle(ctx):
    """Shuffle the current playlist queue (keeps currently playing track)"""
    global music_queue, current_track_index

    if not music_queue:
        await ctx.send("Liste boş babayiğit! Önce bir liste yükle.")
        return

    if len(music_queue) <= 1:
        await ctx.send("Karıştıracak bir şey yok ki!")
        return

    # Get the remaining tracks (after current)
    remaining_tracks = music_queue[current_track_index + 1:]

    if not remaining_tracks:
        await ctx.send("Sırada şarkı yok ki babayiğit!")
        return

    # Shuffle the remaining tracks
    random.shuffle(remaining_tracks)

    # Rebuild queue: tracks before current + current + shuffled remaining
    music_queue = music_queue[:current_track_index + 1] + remaining_tracks

    await ctx.send(f"🔀 Sıradaki {len(remaining_tracks)} şarkıyı karıştırdım!")

if __name__ == '__main__':
    bot.run(DiscordConfig.BOT_TOKEN)

    