import os
import logging
from typing import Optional, List, Dict, Any
import requests
from urllib.parse import quote

logger = logging.getLogger(__name__)

def get_genres_batch(titles: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Look up genres and labels for a list of artist_title strings using TheAudioDB API.
    API: https://www.theaudiodb.com/api/v1/json/123/searchtrack.php?s={artist}&t={track}
    """
    results = {}
    for title in titles:
        info = _get_genre_for_title(title)
        if info:
            results[title] = info
    return results

def _get_genre_for_title(artist_title: str) -> Optional[Dict[str, str]]:
    # Titles are usually in the format "Artist - Track"
    parts = artist_title.split(" - ", 1)
    if len(parts) != 2:
        return None
    
    artist, track = parts[0].strip(), parts[1].strip()
    
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
        logger.debug(f"Failed to fetch genre for {artist_title}: {e}")
        
    return None
