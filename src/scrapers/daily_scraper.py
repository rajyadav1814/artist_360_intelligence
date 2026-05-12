import io
from datetime import date
from typing import List, Optional

import pandas as pd
from bs4 import BeautifulSoup

from config.settings import ITUNES_DAILY_URL, SPOTIFY_DAILY_URL
from src.database.models import ItunesDaily, SpotifyDaily
from src.utils.http_client import fetch_page
from src.utils.logger import get_logger
from src.utils.label_lookup import get_label

logger = get_logger(__name__)


def _safe_int(value) -> int:
    if pd.isna(value):
        return 0
    try:
        clean_val = str(value).replace(",", "").replace("+", "").strip()
        if not clean_val or clean_val == "—" or clean_val == "--":
            return 0
        return int(float(clean_val))
    except (ValueError, TypeError):
        return 0


def _safe_peak(value) -> int:
    if pd.isna(value):
        return 0
    try:
        val_str = str(value).strip()
        if not val_str or val_str == "—" or val_str == "--":
            return 0
        # Kworb peaks can be "1(x5)", take the part before "("
        clean_val = val_str.split("(")[0].replace(",", "").strip()
        return int(float(clean_val))
    except (ValueError, TypeError, IndexError):
        return 0


def _get_column(row: pd.Series, possible_names: List[str]) -> Optional[str]:
    for name in possible_names:
        if name in row.index:
            return str(row[name]).strip()
    return None


def scrape_spotify_daily(country: str = "global") -> List[SpotifyDaily]:
    """Scrape Spotify daily chart for a specific country."""
    from src.utils.label_lookup import get_labels_batch_optimized
    url = SPOTIFY_DAILY_URL.format(country=country)
    logger.info(f"Scraping Spotify {country} Daily from {url}...")
    
    html = fetch_page(url)
    if not html:
        return []

    try:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if not table:
            return []

        df = pd.read_html(io.StringIO(str(table)))[0]
        today = date.today()
        
        # Pre-extract titles for batch label lookup
        titles = []
        rows_to_process = []
        for _, row in df.iterrows():
            artist_title = _get_column(row, ["Artist and Title", "Artist - Title", "Video"])
            if artist_title:
                titles.append(artist_title)
                rows_to_process.append(row)
        
        # Batch lookup labels
        labels_map = get_labels_batch_optimized(titles)
        
        results = []
        for i, row in enumerate(rows_to_process):
            try:
                rank_raw = _get_column(row, ["Pos"])
                if not rank_raw or not rank_raw.isdigit():
                    continue
                rank = int(rank_raw)
                
                artist_title = titles[i]
                results.append(
                    SpotifyDaily(
                        date=today,
                        country=country,
                        rank=rank,
                        artist_title=artist_title,
                        days=_safe_int(row.get("Days", 0)),
                        peak=_safe_peak(row.get("Pk", 0)),
                        streams=_safe_int(row.get("Streams", 0)),
                        streams_change=_safe_int(row.get("Streams+", 0)),
                        total_streams=_safe_int(row.get("Total", 0)),
                        label=labels_map.get(artist_title)
                    )
                )
            except Exception:
                continue

        logger.info(f"Scraped {len(results)} rows for Spotify {country}")
        return results
    except Exception as e:
        logger.error(f"Failed to parse Spotify {country}: {e}")
        return []


def scrape_spotify_weekly(country: str = "global") -> List[SpotifyDaily]:
    """Scrape Spotify weekly chart for a specific country."""
    from src.utils.label_lookup import get_labels_batch_optimized
    url = f"https://kworb.net/spotify/country/{country}_weekly.html"
    logger.info(f"Scraping Spotify {country} Weekly from {url}...")
    
    html = fetch_page(url)
    if not html:
        return []

    try:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if not table:
            return []

        df = pd.read_html(io.StringIO(str(table)))[0]
        today = date.today()
        
        # Pre-extract titles
        titles = []
        rows_to_process = []
        for _, row in df.iterrows():
            artist_title = _get_column(row, ["Artist and Title", "Artist - Title", "Video"])
            if artist_title:
                titles.append(artist_title)
                rows_to_process.append(row)

        # Batch lookup labels
        labels_map = get_labels_batch_optimized(titles)
        
        results = []
        for i, row in enumerate(rows_to_process):
            try:
                rank_raw = _get_column(row, ["Pos"])
                if not rank_raw or not rank_raw.isdigit():
                    continue
                rank = int(rank_raw)

                artist_title = titles[i]
                results.append(
                    SpotifyDaily(
                        date=today,
                        country=f"{country}_weekly",
                        rank=rank,
                        artist_title=artist_title,
                        days=_safe_int(row.get("Days", 0)),
                        peak=_safe_peak(row.get("Pk", 0)),
                        streams=_safe_int(row.get("Streams", 0)),
                        streams_change=_safe_int(row.get("Streams+", 0)),
                        total_streams=_safe_int(row.get("Total", 0)),
                        label=labels_map.get(artist_title)
                    )
                )
            except Exception:
                continue

        logger.info(f"Scraped {len(results)} rows for Spotify {country} Weekly")
        return results
    except Exception as e:
        logger.error(f"Failed to parse Spotify {country} Weekly: {e}")
        return []


def scrape_spotify_totals(country: str = "global") -> List[SpotifyDaily]:
    """Scrape Spotify daily chart totals (all-time stats for the day's tracks)."""
    from src.utils.label_lookup import get_labels_batch_optimized
    url = f"https://kworb.net/spotify/country/{country}_daily_totals.html"
    logger.info(f"Scraping Spotify {country} Totals from {url}...")
    
    html = fetch_page(url)
    if not html:
        return []

    try:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if not table:
            return []

        df = pd.read_html(io.StringIO(str(table)))[0]
        today = date.today()
        
        # Pre-extract titles
        titles = []
        rows_to_process = []
        for _, row in df.iterrows():
            artist_title = _get_column(row, ["Artist and Title", "Artist - Title", "Track"])
            if artist_title:
                titles.append(artist_title)
                rows_to_process.append(row)

        # Batch lookup labels
        labels_map = get_labels_batch_optimized(titles)
        
        results = []
        for i, row in enumerate(rows_to_process):
            try:
                rank_raw = _get_column(row, ["Pos"])
                # In totals table, rank might be different or missing, use index if needed
                rank = int(rank_raw) if rank_raw and rank_raw.isdigit() else 0

                artist_title = titles[i]
                results.append(
                    SpotifyDaily(
                        date=today,
                        country=f"{country}_totals",
                        rank=rank,
                        artist_title=artist_title,
                        days=_safe_int(row.get("Days", 0)),
                        peak=_safe_peak(row.get("Pk", 0)),
                        streams=_safe_int(row.get("Streams", 0)),
                        streams_change=_safe_int(row.get("Streams+", 0)),
                        total_streams=_safe_int(row.get("Total", 0)),
                        label=labels_map.get(artist_title)
                    )
                )
            except Exception:
                continue

        logger.info(f"Scraped {len(results)} rows for Spotify {country} Totals")
        return results
    except Exception as e:
        logger.error(f"Failed to parse Spotify {country} Totals: {e}")
        return []


def scrape_itunes_daily(country: str = "us") -> List[ItunesDaily]:
    """Scrape iTunes daily chart for a specific country."""
    from src.utils.label_lookup import get_labels_batch_optimized
    if country == "ww":
        url = "https://kworb.net/ww/"
    else:
        url = ITUNES_DAILY_URL.format(country=country)
        
    logger.info(f"Scraping iTunes {country} Daily from {url}...")
    html = fetch_page(url)
    if not html:
        return []

    try:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if not table:
            return []

        df = pd.read_html(io.StringIO(str(table)))[0]
        today = date.today()
        
        # Pre-extract titles
        titles = []
        rows_to_process = []
        for _, row in df.iterrows():
            artist_title = _get_column(row, ["Artist and Title", "Artist - Title"])
            if artist_title:
                titles.append(artist_title)
                rows_to_process.append(row)

        # Batch lookup labels
        labels_map = get_labels_batch_optimized(titles)
        
        results = []
        for i, row in enumerate(rows_to_process):
            try:
                rank_raw = _get_column(row, ["Pos"])
                if not rank_raw or not rank_raw.isdigit():
                    continue
                rank = int(rank_raw)

                artist_title = titles[i]
                results.append(
                    ItunesDaily(
                        date=today,
                        country=country,
                        rank=rank,
                        artist_title=artist_title,
                        days=_safe_int(row.get("Days", 0)),
                        peak=_safe_peak(row.get("Pk", 0)),
                        points=_safe_int(row.get("Pts", 0)),
                        points_change=_safe_int(row.get("Pts+", row.get("P+", 0))),
                        total_points=_safe_int(row.get("TPts", 0)),
                        label=labels_map.get(artist_title)
                    )
                )
            except Exception as e:
                continue

        logger.info(f"Scraped {len(results)} rows for iTunes {country}")
        return results
    except Exception as e:
        logger.error(f"Failed to parse iTunes {country}: {e}")
        return []



