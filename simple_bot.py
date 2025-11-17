import discord
from discord.ext import commands
from utils.chat import chat_with_ollama
from utils.pick_replik import pick_random
from pala_replik import leave_replik
from utils.spoti import search_spotify_track
import yt_dlp
import asyncio
from utils.config import Discord as DiscordConfig, Audio as AudioConfig

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
    if ctx.voice_client:
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

if __name__ == '__main__':
    bot.run(DiscordConfig.BOT_TOKEN)

    