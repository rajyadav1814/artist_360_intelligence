from bs4 import BeautifulSoup
from typing import List
from datetime import datetime
from config.settings import SPOTIFY_ARTISTS_URL, SPOTIFY_LISTENERS_URL
from src.utils.http_client import fetch_page
from src.utils.logger import get_logger
from src.database.models import SpotifyArtist

logger = get_logger(__name__)


def _safe_int(value: str) -> int | None:
    try:
        return int(value.strip().replace(",", "").replace(".", ""))
    except (ValueError, AttributeError):
        return None


def scrape_spotify_artists() -> List[SpotifyArtist]:
    """
    Scrape Spotify artist listener stats from kworb.net/spotify/artists.html
    Columns: Artist | Monthly Listeners | Peak Listeners | Peak Date
    """
    html = fetch_page(SPOTIFY_ARTISTS_URL)
    if not html:
        logger.error("Failed to fetch Spotify artists page")
        return []

    soup = BeautifulSoup(html, "lxml")
    artists: List[SpotifyArtist] = []

    table = soup.find("table")
    if not table:
        logger.error("No table found on Spotify artists page")
        return []

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        texts = [c.get_text(strip=True) for c in cells]
        artist_name = texts[0]
        if not artist_name:
            continue

        monthly = _safe_int(texts[1]) if len(texts) > 1 else None
        peak = _safe_int(texts[2]) if len(texts) > 2 else None

        peak_date = None
        if len(texts) > 3 and texts[3]:
            try:
                peak_date = datetime.strptime(texts[3], "%Y-%m-%d").date()
            except ValueError:
                pass

        artists.append(
            SpotifyArtist(
                artist_name=artist_name,
                monthly_listeners=monthly,
                peak_listeners=peak,
                peak_date=peak_date,
            )
        )

    logger.info(f"Scraped {len(artists)} Spotify artists")
    return artists
