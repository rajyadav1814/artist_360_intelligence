from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config.settings import ITUNES_ARTISTS_URL
from src.database.models import ItunesRanking
from src.utils.http_client import fetch_page
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _safe_int(value: str) -> int | None:
    """Convert string to int, return None on failure."""
    try:
        return int(value.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return None


def build_profile_url(href: Optional[str]) -> Optional[str]:
    """Build a valid absolute kworb artist URL from a relative href."""
    if not href:
        return None
    return urljoin(ITUNES_ARTISTS_URL, href)


def scrape_itunes_global_artists() -> List[ItunesRanking]:
    """
    Scrape the Global Digital Artist Ranking from kworb.net/itunes/
    Columns: rank | change | artist | total | itunes | spotify |
             apple_music | shazam | youtube | other | top_country | countries
    """
    html = fetch_page(ITUNES_ARTISTS_URL)
    if not html:
        logger.error("Failed to fetch iTunes artist page")
        return []

    soup = BeautifulSoup(html, "lxml")
    rankings: List[ItunesRanking] = []

    table = soup.find("table")
    if not table:
        logger.error("No table found on iTunes artists page")
        return []

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        texts = [c.get_text(strip=True) for c in cells]
        try:
            rank = _safe_int(texts[0])
            if rank is None:
                continue

            rank_change = texts[1] if texts[1] else "="

            artist_cell = cells[2]
            artist_name = artist_cell.get_text(strip=True)
            anchor = artist_cell.find("a")
            profile_url = build_profile_url(anchor.get("href") if anchor else None)

            ranking = ItunesRanking(
                artist_name=artist_name,
                rank=rank,
                rank_change=rank_change,
                total_points=_safe_int(texts[3]),
                itunes_points=_safe_int(texts[4]),
                spotify_points=_safe_int(texts[5]),
                apple_music_points=_safe_int(texts[6]),
                shazam_points=_safe_int(texts[7]),
                youtube_points=_safe_int(texts[8]),
                other_points=_safe_int(texts[9]) if len(texts) > 9 else None,
                top_country=texts[10] if len(texts) > 10 else None,
                num_countries=_safe_int(texts[11]) if len(texts) > 11 else None,
                profile_url=profile_url,
            )
            rankings.append(ranking)

        except (IndexError, KeyError) as exc:
            logger.debug(f"Skipping malformed row: {exc}")
            continue

    logger.info(f"Scraped {len(rankings)} artist rankings from iTunes page")
    return rankings
