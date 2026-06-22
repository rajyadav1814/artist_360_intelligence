import requests
import streamlit as st
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

@st.cache_data(ttl=86400) # Cache for 24 hours
def get_artist_info_from_audiodb(artist_name: str) -> dict:
    """
    Fetch the artist info (image and genre) from TheAudioDB API.
    Returns a dict with 'image' and 'genre'.
    """
    result = {"image": None, "genre": None}
    if not artist_name or artist_name == "All artists":
        return result
        
    try:
        # API endpoint for searching artist
        # Note: Using public API key '2' as per TheAudioDB documentation for testing/small projects
        url = f"https://www.theaudiodb.com/api/v1/json/2/search.php?s={artist_name.replace(' ', '%20')}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data and "artists" in data and data["artists"]:
                artist_info = data["artists"][0]
                result["image"] = artist_info.get("strArtistThumb")
                result["genre"] = artist_info.get("strGenre") or artist_info.get("strStyle")
    except Exception as e:
        logger.error(f"Error fetching info for {artist_name}: {e}")
        
    return result

@st.cache_data(ttl=86400) # Cache for 24 hours
def get_artist_image_url(artist_name: str) -> Optional[str]:
    """
    Fetch the artist image URL from TheAudioDB API.
    Returns None if not found.
    """
    info = get_artist_info_from_audiodb(artist_name)
    return info.get("image")

def get_fallback_avatar_url(artist_name: str) -> str:
    """
    Generate a professional looking fallback avatar using ui-avatars.com.
    """
    cleaned_name = str(artist_name).replace(' ', '+')
    return f"https://ui-avatars.com/api/?name={cleaned_name}&background=linear-gradient(135deg,4f8ef7,7c5cfc)&color=fff&size=512&font-size=0.35&bold=true&rounded=true"
