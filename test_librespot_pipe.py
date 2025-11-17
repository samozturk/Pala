#!/usr/bin/env python3
"""
Test script to verify librespot pipe backend works correctly
"""
import subprocess
import time
from utils.spoti import search_spotify_track, get_device_id, sp
from utils.config import Spotify as SpotifyConfig
from pathlib import Path

print("Testing librespot pipe backend...")

# Get cache directory
cache_dir = Path(SpotifyConfig.CACHE_DIRECTORY) if SpotifyConfig.CACHE_DIRECTORY else Path('.librespot-cache')
cache_dir = cache_dir.resolve()

# Start librespot with pipe backend
librespot_cmd = [
    'librespot',
    '--name', 'TestPipe',
    '--backend', 'pipe',
    '--format', 'S16',
    '--device', '-',
    '--enable-oauth',
    '--system-cache', str(cache_dir),
]

print("Starting librespot...")
librespot_process = subprocess.Popen(
    librespot_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

print("Waiting for device to register (5 seconds)...")
time.sleep(5)

# Check if device appeared
device_id = get_device_id('TestPipe')
if device_id:
    print(f"✅ Device found: {device_id}")
else:
    print("❌ Device not found!")
    librespot_process.terminate()
    exit(1)

# Search for a track
print("\nSearching for track...")
track = search_spotify_track("Imagine Dragons Believer")
if not track:
    print("❌ Track not found!")
    librespot_process.terminate()
    exit(1)

print(f"✅ Found: {track['name']} by {track['artist']}")

# Start playback
print(f"\nStarting playback on device {device_id}...")
sp.start_playback(device_id=device_id, uris=[track['uri']])

print("Playback started. Checking if audio is coming through pipe...")
time.sleep(2)

# Read a bit of data from stdout to see if audio is flowing
try:
    data = librespot_process.stdout.read(4096)
    if data and len(data) > 0:
        print(f"✅ Audio data flowing! Read {len(data)} bytes")
    else:
        print("❌ No audio data in pipe!")
except Exception as e:
    print(f"❌ Error reading from pipe: {e}")

# Check playback state
playback = sp.current_playback()
if playback and playback['is_playing']:
    progress = playback['progress_ms'] / 1000
    print(f"✅ Spotify shows playing at {progress:.1f}s")
else:
    print("❌ Spotify shows not playing")

# Cleanup
print("\nStopping...")
librespot_process.terminate()
librespot_process.wait()
print("Done!")
