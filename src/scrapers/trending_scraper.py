"""
Trending Artists for Last Month
--------------------------------
Uses the Global Digital Artist Ranking (iTunes/kworb composite) as the source.
"Last month" means we snapshot today's top-300 and tag them with the previous
calendar month (YYYY-MM), representing the artists trending over that period.
"""
from datetime import datetime, date
from typing import List

from src.scrapers.itunes_scraper import scrape_itunes_global_artists
from src.database.models import TrendingArtist
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_last_month_label() -> str:
    """Return the previous month label in 'YYYY-MM' format."""
    last_month = date.today().replace(day=1) - __import__("datetime").timedelta(days=1)
    return last_month.strftime("%Y-%m")


def scrape_trending_artists_last_month() -> List[TrendingArtist]:
    """
    Scrape the top-300 Global Artist Rankings and store them tagged as
    the previous month's trending artists.
    """
    month_label = get_last_month_label()
    logger.info(f"Scraping trending artists for month: {month_label}")

    raw_rankings = scrape_itunes_global_artists()
    if not raw_rankings:
        logger.error("No rankings data retrieved for trending artists")
        return []

    trending: List[TrendingArtist] = []
    for r in raw_rankings:
        trending.append(
            TrendingArtist(
                artist_name=r.artist_name,
                source="itunes_global",
                rank=r.rank,
                rank_change=r.rank_change,
                total_points=r.total_points,
                top_country=r.top_country,
                month=month_label,
            )
        )

    logger.info(f"Built {len(trending)} trending artist records for {month_label}")
    return trending
