from datetime import date
from typing import List, Optional
from dataclasses import dataclass

from bs4 import BeautifulSoup

from config.settings import ITUNES_TRACKS_URL
from src.utils.http_client import fetch_page
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TrackRankingRaw:
    """Raw track ranking data before database insertion."""
    artist_name: str
    title: str
    rank: int
    streams: Optional[int] = None
    week_number: int = 1
    fiscal_year: int = 2026
    chart_date: date = None
    
    def __post_init__(self):
        if self.chart_date is None:
            self.chart_date = date.today()


def _safe_int(value: str) -> Optional[int]:
    """Convert string to int, return None on failure."""
    if not value or value.strip() in ("-", "--", "—"):
        return None
    try:
        clean_val = value.replace(",", "").replace("+", "").strip()
        return int(float(clean_val))
    except (ValueError, TypeError):
        return None


def scrape_itunes_tracks() -> List[TrackRankingRaw]:
    """
    Scrape the Worldwide iTunes Song Ranking from kworb.net/ww
    Columns: rank | change | artist - title | weeks | peak | (xN) | points | change | percentage | country counts...
    Returns raw data for processing by save function.
    """
    html = fetch_page(ITUNES_TRACKS_URL)
    if not html:
        logger.error("Failed to fetch iTunes worldwide tracks page")
        return []

    soup = BeautifulSoup(html, "lxml")
    rankings: List[TrackRankingRaw] = []

    table = soup.find("table")
    if not table:
        logger.error("No table found on iTunes worldwide tracks page")
        return []

    rows = table.find_all("tr")
    
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 8:
            continue

        texts = [c.get_text(strip=True) for c in cells]
        try:
            rank = _safe_int(texts[0])
            if rank is None:
                continue
            
            artist_title = texts[2]
            if " - " not in artist_title:
                continue
            artist_name, title = artist_title.split(" - ", 1)
            artist_name = artist_name.strip()
            title = title.strip()
            
            points = _safe_int(texts[6])  # points column
            
            ranking = TrackRankingRaw(
                artist_name=artist_name,
                title=title,
                rank=rank,
                streams=points,
            )
            rankings.append(ranking)

        except (IndexError, KeyError, ValueError) as exc:
            logger.debug(f"Skipping malformed row: {exc}")
            continue
    
    logger.info(f"Scraped {len(rankings)} track rankings from iTunes worldwide tracks page")
    return rankings