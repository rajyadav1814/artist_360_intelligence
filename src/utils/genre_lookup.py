import os
import logging
from typing import Optional, List, Dict
import requests
from urllib.parse import quote

logger = logging.getLogger(__name__)

def get_genres_batch(titles: List[str]) -> Dict[str, str]:
    """
    Look up genres for a list of artist_title strings using TheAudioDB API.
    API: https://www.theaudiodb.com/api/v1/json/123/searchtrack.php?s={artist}&t={track}
    """
    results = {}
    for title in titles:
        genre = _get_genre_for_title(title)
        if genre:
            results[title] = genre
    return results

def _get_genre_for_title(artist_title: str) -> Optional[str]:
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
            genre = data["track"][0].get("strGenre")
            if genre and genre.strip():
                return genre.strip()
    except Exception as e:
        logger.debug(f"Failed to fetch genre for {artist_title}: {e}")
        
    return None
