import unicodedata

from bs4 import BeautifulSoup
from typing import List
from datetime import datetime
from config.settings import SPOTIFY_ARTISTS_URL, SPOTIFY_LISTENERS_URL, SPOTIFY_LISTENERS2_URL
from src.utils.http_client import fetch_page
from src.utils.logger import get_logger
from src.database.models import SpotifyArtist

logger = get_logger(__name__)

# Additional Latin artists to always include alongside the top 300
EXTRA_ARTISTS = [
    "Alejandro Sanz",
    "Beéle",
    "C. Tangana",
    "CA7RIEL & Paco Amoroso",
    "Caetano Veloso",
    "Camila",
    "Carlos Santana",
    "Carlos Vives",
    "Charly García",
    "Chayanne",
    "Christina Aguilera",
    "DARUMAS",
    "DENNIS",
    "Djavan",
    "Emilia",
    "Filipe Ret",
    "Fito Páez",
    "Grupo Menos É Mais",
    "Gusttavo Lima",
    "Ha*Ash",
    "Jorge Drexler",
    "Kany García",
    "Kapo",
    "Kenia OS",
    "Luan Santana",
    "Luck Ra",
    "Luísa Sonza",
    "Marisa Monte",
    "Mon Laferte",
    "Natalia Lafourcade",
    "Nathy Peluso",
    "Nicki Nicole",
    "Prince Royce",
    "Rauw Alejandro",
    "Reik",
    "Residente",
    "Ricky Martin",
    "Roberto Carlos",
    "Romeo Santos",
    "Rosalía",
    "Shakira",
    "Thalía",
    "Tiago Iorc",
    "TINI",
    "Trueno",
    "Vicente Fernández",
]

# Mapping of how kworb.net spells a name -> our canonical name.
# Used when the page drops accents or uses a different variant entirely.
ARTIST_ALIASES = {
    "thalia": "Thalía",
    "santana": "Carlos Santana",
    "fito paez": "Fito Páez",
    "nathy peluso": "Nathy Peluso",
}


def _fix_encoding(text: str) -> str:
    """
    Repair double-encoded UTF-8 (mojibake).

    kworb.net sometimes serves names like 'ROSALÃ\x8dA' instead of 'ROSALÍA'
    because the original UTF-8 bytes were re-interpreted as Latin-1 and
    encoded to UTF-8 a second time.  This reverses that process.
    """
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _normalize_name(name: str) -> str:
    """Normalize a name for comparison: fix encoding, NFC-normalize, lowercase."""
    return unicodedata.normalize("NFC", _fix_encoding(name)).lower()


_EXTRA_ARTISTS_LOWER = {_normalize_name(name) for name in EXTRA_ARTISTS}


def _safe_int(value: str) -> int | None:
    try:
        return int(value.strip().replace(",", "").replace(".", ""))
    except (ValueError, AttributeError):
        return None


def _parse_row(row) -> SpotifyArtist | None:
    """Parse a single table row into a SpotifyArtist, or None if invalid."""
    cells = row.find_all("td")
    if len(cells) < 3:
        return None

    texts = [c.get_text(strip=True) for c in cells]
    raw_name = texts[1]
    if not raw_name:
        return None

    # Repair mojibake so names are stored cleanly in the DB
    artist_name = _fix_encoding(raw_name)
    artist_name = unicodedata.normalize("NFC", artist_name)

    monthly = _safe_int(texts[2]) if len(texts) > 2 else None
    peak = _safe_int(texts[5]) if len(texts) > 5 else None

    return SpotifyArtist(
        artist_name=artist_name,
        monthly_listeners=monthly,
        peak_listeners=peak,
        peak_date=None,
    )


def scrape_spotify_artists() -> List[SpotifyArtist]:
    """
    Scrape Spotify artist listener stats from kworb.net/spotify/listeners.html.

    Returns the top 300 artists by monthly listeners.
    """
    html = fetch_page(SPOTIFY_LISTENERS_URL)
    if not html:
        logger.error("Failed to fetch Spotify listeners page")
        return []

    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table")
    if not table:
        logger.error("No table found on Spotify listeners page")
        return []

    artists: List[SpotifyArtist] = []
    for row in table.find_all("tr"):
        if len(artists) >= 300:
            break
        artist = _parse_row(row)
        if artist is not None:
            artists.append(artist)

    logger.info(f"Scraped {len(artists)} Spotify artists")
    return artists


def _search_page_for_extras(
    url: str,
    still_needed: set,
    alias_lookup: dict,
) -> List[SpotifyArtist]:
    """
    Fetch a single kworb listeners page and return any EXTRA_ARTISTS found.

    Mutates *still_needed* in place — matched names are removed.
    """
    html = fetch_page(url)
    if not html:
        logger.error(f"Failed to fetch {url}")
        return []

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        logger.error(f"No table found on {url}")
        return []

    found: List[SpotifyArtist] = []

    for row in table.find_all("tr"):
        if not still_needed:
            break
        artist = _parse_row(row)
        if artist is None:
            continue

        norm = _normalize_name(artist.artist_name)

        # Direct match
        if norm in still_needed:
            found.append(artist)
            still_needed.discard(norm)
            continue

        # Alias match (e.g. "Thalia" on page -> "Thalía" in our list)
        canonical = alias_lookup.get(norm)
        if canonical and _normalize_name(canonical) in still_needed:
            artist.artist_name = canonical  # store the canonical name
            found.append(artist)
            still_needed.discard(_normalize_name(canonical))

    return found


def scrape_extra_spotify_artists() -> List[SpotifyArtist]:
    """
    Search kworb.net listeners pages for the 46 EXTRA_ARTISTS and return
    their Spotify listener data.

    First searches listeners.html, then falls back to listeners2.html
    for any artists not found on the first page.

    Handles mojibake (double-encoded UTF-8) and name aliases so that
    artists like ROSALÍA, Thalía, Vicente Fernández etc. are matched
    even when the page encodes them differently.

    Artists not found on either page are logged as warnings.
    """
    alias_lookup = {_normalize_name(k): v for k, v in ARTIST_ALIASES.items()}
    still_needed = set(_EXTRA_ARTISTS_LOWER)
    found: List[SpotifyArtist] = []

    # --- Page 1: listeners.html ---
    page1 = _search_page_for_extras(SPOTIFY_LISTENERS_URL, still_needed, alias_lookup)
    found.extend(page1)
    logger.info(f"listeners.html: found {len(page1)}, still need {len(still_needed)}")

    # --- Page 2: listeners2.html (fallback for remaining) ---
    if still_needed:
        page2 = _search_page_for_extras(SPOTIFY_LISTENERS2_URL, still_needed, alias_lookup)
        found.extend(page2)
        logger.info(f"listeners2.html: found {len(page2)}, still need {len(still_needed)}")

    if still_needed:
        logger.warning(
            f"{len(still_needed)} extra artist(s) not found on either page: "
            f"{', '.join(sorted(still_needed))}"
        )

    logger.info(f"Scraped {len(found)}/{len(EXTRA_ARTISTS)} extra Latin artists")
    return found
