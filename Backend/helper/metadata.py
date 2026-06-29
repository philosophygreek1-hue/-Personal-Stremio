"""
Simplified metadata for personal files addon.
No TMDB/IMDb — files are organized into user-defined folders.
Each file becomes an entry with a unique ID based on channel+msg_id.
"""
import asyncio
import hashlib
import re
from datetime import datetime
from Backend.config import Telegram
from Backend.logger import LOGGER
from Backend.helper.encrypt import encode_string


def extract_default_id(url: str) -> str | None:
    """Keep for compatibility — used by edited-message handler."""
    if not url:
        return None
    # Check for a "folder:<name>" tag in caption
    folder_match = re.search(r'folder:([^\s]+)', url, re.IGNORECASE)
    if folder_match:
        return folder_match.group(1)
    return None


def get_readable_file_size(size_bytes: int) -> str:
    if not size_bytes:
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def make_personal_id(channel: int, msg_id: int) -> str:
    """Create a unique Stremio-safe ID for a personal file."""
    raw = f"personal:{channel}:{msg_id}"
    return "ps" + hashlib.md5(raw.encode()).hexdigest()[:16]


async def metadata(
    filename: str,
    channel: int,
    msg_id: int,
    override_id: str = None
) -> dict | None:
    """
    Build metadata for a personal file. No external API calls.
    
    - folder: extracted from override_id (caption tag "folder:MyFolder")
               or from Telegram.DEFAULT_FOLDER env var, or "General"
    - title: the raw filename (cleaned)
    - quality: guessed from filename if present, else "File"
    """
    try:
        # Determine folder
        folder = None
        if override_id:
            folder = override_id.strip()
        if not folder:
            folder = getattr(Telegram, "DEFAULT_FOLDER", None) or "General"

        # Guess quality/resolution from filename
        quality = "File"
        res_match = re.search(r'\b(2160p|4K|1080p|720p|480p|360p)\b', filename, re.IGNORECASE)
        if res_match:
            quality = res_match.group(1).upper()

        # Encode stream reference
        data = {"chat_id": channel, "msg_id": msg_id}
        encoded_string = await encode_string(data)

        # Generate unique personal ID for this file
        personal_id = make_personal_id(channel, msg_id)

        return {
            "personal_id": personal_id,
            "imdb_id": personal_id,   # used as Stremio meta ID
            "tmdb_id": None,
            "title": filename,
            "folder": folder,
            "year": datetime.utcnow().year,
            "rate": 0,
            "description": f"📁 {folder}",
            "poster": "",
            "backdrop": "",
            "logo": "",
            "cast": [],
            "runtime": "",
            "genres": [folder],       # folder name used as genre for filtering
            "media_type": "personal", # custom type
            "quality": quality,
            "encoded_string": encoded_string,
        }
    except Exception as e:
        LOGGER.error(f"Personal metadata error for {filename}: {e}")
        return None


# Stubs kept for compatibility with any imports in the codebase
async def search_movie_candidates(query, year=None, limit=8):
    return []

async def search_tv_candidates(query, limit=8):
    return []

async def fetch_selected_movie_metadata(selected_id):
    return None

async def fetch_selected_tv_metadata(selected_id):
    return None
