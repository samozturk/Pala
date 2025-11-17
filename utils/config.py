"""
Configuration loader for the Discord bot.
Loads settings from .env and config.json files.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# Get the project root directory (parent of utils/)
PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / '.env'
CONFIG_PATH = PROJECT_ROOT / 'config.json'

# Load .env file
load_dotenv(ENV_PATH)

# Load config.json
try:
    with open(CONFIG_PATH, 'r') as f:
        _config = json.load(f)
except FileNotFoundError:
    raise FileNotFoundError(
        f"config.json not found at {CONFIG_PATH}. "
        "Please create it using config.json.example as a template."
    )
except json.JSONDecodeError as e:
    raise ValueError(f"Invalid JSON in config.json: {e}")


def get_env(key: str, required: bool = True, default: str = None) -> str:
    """
    Get an environment variable from .env file.

    Args:
        key: The environment variable name
        required: If True, raises error if not found
        default: Default value if not found (only used if required=False)

    Returns:
        The environment variable value

    Raises:
        ValueError: If required variable is not found
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(
            f"Required environment variable '{key}' not found in .env file. "
            f"Please check {ENV_PATH} and .env.example for reference."
        )
    return value


def get_config(path: str, required: bool = True, default=None):
    """
    Get a configuration value from config.json using dot notation.

    Args:
        path: Dot-separated path to the config value (e.g., 'discord.command_prefix')
        required: If True, raises error if not found
        default: Default value if not found (only used if required=False)

    Returns:
        The configuration value

    Raises:
        ValueError: If required config value is not found
    """
    keys = path.split('.')
    value = _config

    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        if required:
            raise ValueError(
                f"Required config value '{path}' not found in config.json. "
                f"Please check {CONFIG_PATH} and config.json.example for reference."
            )
        return default


# Discord Configuration
class Discord:
    BOT_TOKEN = get_env('DISCORD_BOT_TOKEN')
    COMMAND_PREFIX = get_config('discord.command_prefix')
    OPUS_LIBRARY_PATH = get_config('discord.opus_library_path')


# Spotify Configuration
class Spotify:
    CLIENT_ID = get_env('SPOTIFY_CLIENT_ID')
    CLIENT_SECRET = get_env('SPOTIFY_CLIENT_SECRET')
    REDIRECT_URI = get_env('SPOTIFY_REDIRECT_URI')
    SCOPES = get_config('spotify.scopes')
    DEVICE_NAME = get_config('spotify.device_name')
    CACHE_DIRECTORY = get_config('spotify.cache_directory')


# Ollama Configuration
class Ollama:
    API_URL = get_config('ollama.api_url')
    MODEL = get_config('ollama.model')
    TIMEOUT = get_config('ollama.timeout', required=False, default=60.0)


# Audio Configuration
class Audio:
    LOCAL_FILES_DIRECTORY = get_config('audio.local_files_directory')


# Queue Configuration
class Queue:
    MAX_SIZE = get_config('queue.max_size', required=False, default=100)


# Lavalink Configuration
class Lavalink:
    PASSWORD = get_env('LAVALINK_PASSWORD', required=False, default='youshallnotpass')
    HOST = get_config('lavalink.host')
    PORT = get_config('lavalink.port')


# Export for easy access
__all__ = ['Discord', 'Spotify', 'Ollama', 'Audio', 'Queue', 'Lavalink', 'get_env', 'get_config']
