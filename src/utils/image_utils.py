import requests
import streamlit as st
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


@st.cache_data(ttl=86400)  # Cache for 24 hours
def get_artist_audiodb_info(artist_name: str) -> dict:
    """
    Fetch artist metadata from TheAudioDB API in a single call.
    Returns a dict with 'image' (strArtistThumb) and 'genre' (strGenre).
    Results are cached for 24 hours to avoid redundant API hits.
    """
    result = {"image": None, "genre": None}
    if not artist_name or artist_name == "All artists":
        return result

    try:
        url = f"https://www.theaudiodb.com/api/v1/json/2/search.php?s={artist_name.replace(' ', '%20')}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and "artists" in data and data["artists"]:
                artist_info = data["artists"][0]
                result["image"] = artist_info.get("strArtistThumb")
                result["genre"] = artist_info.get("strGenre")
    except Exception as e:
        logger.error(f"Error fetching AudioDB info for {artist_name}: {e}")

    return result


@st.cache_data(ttl=86400)  # Cache for 24 hours
def get_artist_image_url(artist_name: str) -> Optional[str]:
    """
    Fetch the artist image URL from TheAudioDB API.
    Returns None if not found.
    """
    return get_artist_audiodb_info(artist_name)["image"]


@st.cache_data(ttl=86400)  # Cache for 24 hours
def get_artist_genre(artist_name: str) -> Optional[str]:
    """
    Fetch the artist genre (strGenre) from TheAudioDB API.
    Returns None if not found.
    """
    return get_artist_audiodb_info(artist_name)["genre"]


def get_fallback_avatar_url(artist_name: str) -> str:
    """
    Generate a professional looking fallback avatar using ui-avatars.com.
    """
    cleaned_name = str(artist_name).replace(' ', '+')
    return f"https://ui-avatars.com/api/?name={cleaned_name}&background=linear-gradient(135deg,4f8ef7,7c5cfc)&color=fff&size=512&font-size=0.35&bold=true&rounded=true"
