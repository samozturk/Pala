import spotipy
from spotipy.oauth2 import SpotifyOAuth
import subprocess
from discord import FFmpegPCMAudio
import time
import atexit
import signal

# Handle both direct execution and module import
try:
    from .config import Spotify as SpotifyConfig
except ImportError:
    from config import Spotify as SpotifyConfig

# TODO: Add error handling/logging

# Setup Spotify API client with user authorization (needed for playback control)
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SpotifyConfig.CLIENT_ID,
    client_secret=SpotifyConfig.CLIENT_SECRET,
    redirect_uri=SpotifyConfig.REDIRECT_URI,
    scope=SpotifyConfig.SCOPES,
    open_browser=False
))

def search_spotify_track(query):
    '''Search for a track and return a dictionary with its URI, name, and artist.

    Args:
        query (str): The search query string; typically the track name and artist.

    Returns:
        dict: A dictionary containing the track's URI, name, and artist.
    '''
    results = sp.search(q=query, limit=1, type='track')
    
    if results['tracks']['items']:
        # Get the first track from the search results
        track = results['tracks']['items'][0]
        track_uri = track['uri']
        track_name = track['name']
        artist_name = track['artists'][0]['name']

        return {
            'uri': track_uri,
            'name': track_name,
            'artist': artist_name
        }
    return None

def stop_spotify_device(process):
    """Stop a librespot process gracefully

    Args:
        process: The subprocess.Popen object of the librespot process
    """
    if process:
        print("\nStopping librespot...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Process didn't terminate, killing forcefully...")
            process.kill()
        print("Librespot stopped.")

def create_spotify_device(access_token=None, register_cleanup=True):
    """Start librespot to create a virtual Spotify device

    Args:
        access_token: Optional Spotify access token for authentication
        register_cleanup: If True, automatically registers cleanup handlers for atexit and SIGINT

    Returns:
        subprocess.Popen: The librespot process object
    """
    from pathlib import Path

    # Get absolute path for cache directory
    cache_dir = Path(SpotifyConfig.CACHE_DIRECTORY) if SpotifyConfig.CACHE_DIRECTORY else Path('.librespot-cache')
    cache_dir = cache_dir.resolve()

    cmd = [
        'librespot',
        '--name', SpotifyConfig.DEVICE_NAME,
        '--system-cache', str(cache_dir),
        '--verbose'
    ]

    if access_token:
        # Use access token from spotipy session
        cmd.extend(['--access-token', access_token])
    else:
        # Use interactive OAuth
        cmd.append('--enable-oauth')

    librespot_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if register_cleanup:
        # Register cleanup handler for normal exit
        atexit.register(lambda: stop_spotify_device(librespot_process))

        # Register cleanup handler for Ctrl+C
        def signal_handler(_sig, _frame):
            stop_spotify_device(librespot_process)
            exit(0)

        signal.signal(signal.SIGINT, signal_handler)

    return librespot_process

def get_device_id(device_name=None):
    """Get the device ID for the librespot instance

    Args:
        device_name: Name of the device to find. If None, uses config default.
    """
    if device_name is None:
        device_name = SpotifyConfig.DEVICE_NAME

    devices = sp.devices()
    if devices and 'devices' in devices:
        for device in devices['devices']:
            if device['name'] == device_name:
                return device['id']
    return None

def play_track_on_device(track_uri, device_id=None):
    """Play a track on the specified device (or default device if None)"""
    if device_id is None:
        device_id = get_device_id(SpotifyConfig.DEVICE_NAME)

    if device_id:
        print(f"Starting playback of {track_uri} on device ID {device_id}...")
        sp.start_playback(device_id=device_id, uris=[track_uri])
        return True
    return False

def create_spotify_audio_source(track_uri):
    """
    Create a Discord audio source that streams Spotify audio via librespot.

    This starts librespot with pipe backend to stream audio directly to Discord.

    Args:
        track_uri: Spotify track URI (e.g., 'spotify:track:xxx')

    Returns:
        tuple: (discord.PCMVolumeTransformer, subprocess.Popen) - Audio source and librespot process

    Note:
        This is a complex implementation that:
        1. Starts librespot with --backend pipe to output raw audio
        2. Uses Spotify API to trigger playback on the virtual device
        3. Captures the audio stream and wraps it for Discord
        4. Returns Discord-compatible audio source and process handle

        IMPORTANT: You must terminate the librespot_process when done!
    """
    from pathlib import Path
    import discord

    # Get absolute path for cache directory
    cache_dir = Path(SpotifyConfig.CACHE_DIRECTORY) if SpotifyConfig.CACHE_DIRECTORY else Path('.librespot-cache')
    cache_dir = cache_dir.resolve()

    # Start librespot with pipe backend
    # This outputs raw PCM audio to stdout instead of speakers
    librespot_cmd = [
        'librespot',
        '--name', f'{SpotifyConfig.DEVICE_NAME}_Stream',
        '--backend', 'pipe',
        '--format', 'S16',  # 16-bit signed PCM
        '--device', '-',     # Output to stdout
        '--enable-oauth',
        '--system-cache', str(cache_dir),
    ]

    # Start librespot process
    librespot_process = subprocess.Popen(
        librespot_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )

    # Give librespot time to initialize and register as a device
    time.sleep(5)

    # Get the device ID for our streaming device
    device_id = get_device_id(f'{SpotifyConfig.DEVICE_NAME}_Stream')

    if not device_id:
        librespot_process.terminate()
        raise RuntimeError("Failed to find librespot streaming device. Make sure it registered with Spotify.")

    # Start playback on the virtual device
    sp.start_playback(device_id=device_id, uris=[track_uri])

    # Give playback a moment to start
    time.sleep(1)

    # Use FFmpegPCMAudio with before_options to read from the pipe
    # This is the cleanest way to pipe librespot output to Discord
    before_options = '-f s16le -ar 44100 -ac 2'

    # Create a wrapper that Discord can use
    # We'll create an FFmpegPCMAudio that reads from stdin
    audio = FFmpegPCMAudio(
        librespot_process.stdout if librespot_process.stdout else '',  # type: ignore
        pipe=True,
        before_options=before_options
    )

    # Wrap in volume transformer for volume control
    source = discord.PCMVolumeTransformer(audio, volume=1.0)

    # Return audio source and librespot process
    # The caller must manage process lifecycle
    return source, librespot_process

if __name__ == "__main__":
    print("Starting librespot with OAuth (you'll need to authenticate once)...")

    # Start librespot - cleanup handlers are registered automatically
    librespot_process = create_spotify_device()

    # Give it time to connect
    print("Waiting for librespot to register (10 seconds)...")
    time.sleep(10)

    # Check if process is still running
    poll_result = librespot_process.poll()
    if poll_result is not None:
        print(f"WARNING: Librespot process exited with code {poll_result}")
    else:
        print("Librespot process is running!")

    print("\nFetching devices...")
    devices = sp.devices()

    if devices and 'devices' in devices:
        print(f"Found {len(devices['devices'])} device(s):")
        for device in devices['devices']:
            print(f"  - {device['name']} (ID: {device['id']}, Active: {device['is_active']})")
    else:
        print("No devices found!")
        print(f"Raw response: {devices}")

    track = search_spotify_track("Imagine Dragons Believer")
    if track:
        print(f"\nFound track: {track['name']} by {track['artist']}")
        print(f"Playing on DiscordBot device...")
        success = play_track_on_device(track['uri'], device_id=get_device_id())

        if success:
            print("\n✅ Playback started successfully!")
            print("🎧 You should hear the music playing now.")
            print("Press Enter to stop and exit...")
            input()
        else:
            print("\n❌ Failed to start playback!")
            print("Make sure the device is active and you have Spotify Premium.")