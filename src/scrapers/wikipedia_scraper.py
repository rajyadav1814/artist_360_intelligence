import requests
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

WIKIPEDIA_API_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"

WIKIPEDIA_API_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def fetch_wikipedia_summary(artist_name: str) -> Optional[dict]:
    """
    Fetch Wikipedia summary for an artist using the REST API.
    Returns dict with title, extract, thumbnail, and content_urls or None if not found.
    """
    if not artist_name:
        return None

    # Clean artist name for Wikipedia search
    search_name = artist_name.strip().replace("&", "and").replace(" feat. ", " ")
    url = f"{WIKIPEDIA_API_URL}{search_name.replace(' ', '_')}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "Artist-360-Intelligence/1.0 (https://github.com/artist-360)",
    }

    try:
        response = requests.get(url, timeout=10, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return {
                "title": data.get("title"),
                "extract": data.get("extract"),
                "thumbnail": data.get("thumbnail", {}).get("source") if data.get("thumbnail") else None,
                "content_url": data.get("content_urls", {}).get("desktop", {}).get("page"),
                "description": data.get("description"),
            }
        elif response.status_code == 404:
            logger.info(f"No Wikipedia page found for: {artist_name}")
            return None
        else:
            logger.warning(f"Wikipedia API returned {response.status_code} for {artist_name}")
            return None
    except requests.RequestException as exc:
        logger.warning(f"Failed to fetch Wikipedia for {artist_name}: {exc}")
        return None


def search_wikipedia(artist_name: str) -> Optional[dict]:
    """
    Search Wikipedia for an artist when direct lookup fails.
    Returns dict with basic info or None if no match.
    """
    if not artist_name:
        return None

    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": artist_name,
        "srlimit": 1,
        "srprop": "snippet|thumbnail",
    }

    headers = {
        "Accept": "application/json",
        "User-Agent": "Artist-360-Intelligence/1.0 (https://github.com/artist-360)",
    }

    try:
        response = requests.get(WIKIPEDIA_SEARCH_URL, params=params, timeout=10, headers=headers)
        if response.status_code == 200:
            data = response.json()
            results = data.get("query", {}).get("search", [])
            if results:
                result = results[0]
                return {
                    "title": result.get("title"),
                    "extract": result.get("snippet"),
                    "thumbnail": result.get("thumbnail", {}).get("source") if result.get("thumbnail") else None,
                    "content_url": f"https://en.wikipedia.org/wiki/{result.get('title', '').replace(' ', '_')}" if result.get("title") else None,
                    "description": None,
                }
        return None
    except requests.RequestException as exc:
        logger.warning(f"Wikipedia search failed for {artist_name}: {exc}")
        return None


def get_wikipedia_info(artist_name: str) -> Optional[dict]:
    """
    Get Wikipedia info for an artist, trying direct summary first then search.
    """
    wiki_data = fetch_wikipedia_summary(artist_name)
    if wiki_data:
        return wiki_data

    # Fallback to search if direct lookup fails
    return search_wikipedia(artist_name)