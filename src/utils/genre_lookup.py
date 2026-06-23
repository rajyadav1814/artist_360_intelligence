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
    logger.info(f"Starting genre lookup batch for {len(titles)} titles...")
    for title in titles:
        info = _get_genre_for_title(title)
        if info:
            results[title] = info
    logger.info(f"Finished genre lookup. Found info for {len(results)} out of {len(titles)} titles.")
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
        logger.info(f"Found genre via Last.fm for '{artist_title}'")
        return result

    # Fall back to TheAudioDB
    result = _get_genre_from_audiodb(artist, track)
    if result and (result.get("genre") or result.get("label")):
        logger.info(f"Found genre/label via TheAudioDB for '{artist_title}'")
        return result
        
    logger.debug(f"No genre or label found for '{artist_title}'")
    return result


def _extract_tags_from_lastfm(tags_list, artist):
    if not tags_list:
        return None
    artist_lower = artist.lower()
    genre_tags = []
    
    # sometimes tags_list is a dict if there's only one tag
    if isinstance(tags_list, dict):
        tags_list = [tags_list]
        
    for tag in tags_list:
        tag_name = tag.get("name", "").strip()
        if not tag_name:
            continue
        tag_lower = tag_name.lower()
        if tag_lower == artist_lower or tag_lower in _SKIP_TAGS:
            continue
        genre_tags.append(tag_name.title())
        if len(genre_tags) >= 3:
            break
    return ", ".join(genre_tags) if genre_tags else None


def _get_genre_from_lastfm(artist: str, item_name: str) -> Optional[Dict[str, str]]:
    """
    Fetch genre tags from Last.fm API. Tries track.getInfo first, then album.getInfo.
    Returns dict with 'genre' (comma-separated top tags) and 'label' (None, Last.fm doesn't provide labels).
    """
    # 1. Try track.getInfo
    params_track = {
        "method": "track.getInfo",
        "api_key": LASTFM_API_KEY,
        "artist": artist,
        "track": item_name,
        "format": "json",
    }
    
    try:
        response = requests.get(LASTFM_BASE_URL, params=params_track, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "error" not in data:
                track_data = data.get("track", {})
                toptags = track_data.get("toptags", {}).get("tag", [])
                
                genre_str = _extract_tags_from_lastfm(toptags, artist)
                if genre_str:
                    return {"genre": genre_str, "label": None}
    except Exception as e:
        logger.debug(f"Last.fm track lookup failed for '{artist} - {item_name}': {e}")

    # 2. Try album.getInfo
    params_album = {
        "method": "album.getInfo",
        "api_key": LASTFM_API_KEY,
        "artist": artist,
        "album": item_name,
        "format": "json",
    }
    try:
        response = requests.get(LASTFM_BASE_URL, params=params_album, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "error" not in data:
                album_data = data.get("album", {})
                toptags = album_data.get("tags", {}).get("tag", [])
                
                genre_str = _extract_tags_from_lastfm(toptags, artist)
                if genre_str:
                    return {"genre": genre_str, "label": None}
    except Exception as e:
        logger.debug(f"Last.fm album lookup failed for '{artist} - {item_name}': {e}")

    return None


def _get_genre_from_audiodb(artist: str, item_name: str) -> Optional[Dict[str, str]]:
    """
    Fallback: fetch genre from TheAudioDB API.
    Tries searchtrack.php first, then searchalbum.php.
    Also retrieves the album label if available.
    """
    # 1. Try track search
    url_track = f"https://www.theaudiodb.com/api/v1/json/123/searchtrack.php?s={quote(artist)}&t={quote(item_name)}"
    try:
        response = requests.get(url_track, timeout=10)
        if response.status_code == 200:
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
        logger.debug(f"AudioDB track lookup failed for '{artist} - {item_name}': {e}")

    # 2. Try album search
    url_album = f"https://www.theaudiodb.com/api/v1/json/123/searchalbum.php?s={quote(artist)}&a={quote(item_name)}"
    try:
        response = requests.get(url_album, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and data.get("album") and len(data["album"]) > 0:
                album_info = data["album"][0]
                genre = album_info.get("strGenre")
                style = album_info.get("strStyle")
                label_str = album_info.get("strLabel")

                result = []
                if genre and genre.strip():
                    result.append(genre.strip())
                if style and style.strip() and style.strip() not in result:
                    result.append(style.strip())

                genre_str = ", ".join(result) if result else None
                
                if genre_str or label_str:
                    return {"genre": genre_str, "label": label_str}
    except Exception as e:
        logger.debug(f"AudioDB album lookup failed for '{artist} - {item_name}': {e}")

    return None
