import os
import logging
from typing import Optional, List, Dict, Any
import requests
from urllib.parse import quote

logger = logging.getLogger(__name__)

LASTFM_API_KEY = "c1c2e375e5f7aa0ec509a5cddb53b303"
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"

# Tags to skip (artist names, decades, etc. that aren't real genres)
_SKIP_TAGS = {"seen live", "favorites", "favourite", "love", "sexy"}


def get_genres_batch(titles: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Look up genres and labels for a list of artist_title strings.
    Uses Last.fm (audioscrobbler) API as primary source, falls back to TheAudioDB.
    API: https://ws.audioscrobbler.com/2.0/?method=track.getInfo&api_key=...&artist=...&track=...&format=json
    """
    results = {}
    for title in titles:
        info = _get_genre_for_title(title)
        if info:
            results[title] = info
    return results


def _get_genre_for_title(artist_title: str) -> Optional[Dict[str, str]]:
    """Look up genre for a single 'Artist - Track' string."""
    # Titles are usually in the format "Artist - Track"
    parts = artist_title.split(" - ", 1)
    if len(parts) != 2:
        return None

    artist, track = parts[0].strip(), parts[1].strip()

    # Try Last.fm first
    result = _get_genre_from_lastfm(artist, track)
    if result and result.get("genre"):
        return result

    # Fall back to TheAudioDB
    return _get_genre_from_audiodb(artist, track)


def _get_genre_from_lastfm(artist: str, track: str) -> Optional[Dict[str, str]]:
    """
    Fetch genre tags from Last.fm track.getInfo API.
    Returns dict with 'genre' (comma-separated top tags) and 'label' (None, Last.fm doesn't provide labels).
    """
    params = {
        "method": "track.getInfo",
        "api_key": LASTFM_API_KEY,
        "artist": artist,
        "track": track,
        "format": "json",
    }
    try:
        response = requests.get(LASTFM_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            logger.debug(f"Last.fm API error for '{artist} - {track}': {data.get('message')}")
            return None

        track_data = data.get("track", {})
        toptags = track_data.get("toptags", {}).get("tag", [])

        if not toptags:
            return None

        # Filter out non-genre tags (artist names, decades, etc.)
        artist_lower = artist.lower()
        genre_tags = []
        for tag in toptags:
            tag_name = tag.get("name", "").strip()
            if not tag_name:
                continue
            tag_lower = tag_name.lower()
            # Skip if tag is the artist name or a known non-genre tag
            if tag_lower == artist_lower or tag_lower in _SKIP_TAGS:
                continue
            genre_tags.append(tag_name.title())
            if len(genre_tags) >= 3:  # Keep top 3 genre tags
                break

        genre_str = ", ".join(genre_tags) if genre_tags else None

        if genre_str:
            return {"genre": genre_str, "label": None}

    except Exception as e:
        logger.debug(f"Last.fm lookup failed for '{artist} - {track}': {e}")

    return None


def _get_genre_from_audiodb(artist: str, track: str) -> Optional[Dict[str, str]]:
    """
    Fallback: fetch genre from TheAudioDB API.
    Also retrieves the album label if available.
    """
    url = f"https://www.theaudiodb.com/api/v1/json/123/searchtrack.php?s={quote(artist)}&t={quote(track)}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and data.get("track") and len(data["track"]) > 0:
            track_info = data["track"][0]
            genre = track_info.get("strGenre")
            style = track_info.get("strStyle")
            idAlbum = track_info.get("idAlbum")

            result = []
            if genre and genre.strip():
                result.append(genre.strip())
            if style and style.strip() and style.strip() not in result:
                result.append(style.strip())

            genre_str = ", ".join(result) if result else None
            label_str = None

            if idAlbum:
                try:
                    album_url = f"https://www.theaudiodb.com/api/v1/json/123/album.php?m={idAlbum}"
                    album_resp = requests.get(album_url, timeout=10)
                    if album_resp.status_code == 200:
                        album_data = album_resp.json()
                        if album_data and album_data.get("album") and len(album_data["album"]) > 0:
                            label_str = album_data["album"][0].get("strLabel")
                except Exception as e:
                    logger.debug(f"Failed to fetch label for album {idAlbum}: {e}")

            if genre_str or label_str:
                return {"genre": genre_str, "label": label_str}
    except Exception as e:
        logger.debug(f"AudioDB lookup failed for '{artist} - {track}': {e}")

    return None
