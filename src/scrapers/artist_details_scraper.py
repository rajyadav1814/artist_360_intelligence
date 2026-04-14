import re
from typing import Iterable, List, Optional

from bs4 import BeautifulSoup

from src.database.models import ArtistDetail
from src.scrapers.itunes_scraper import scrape_itunes_global_artists
from src.utils.http_client import fetch_page
from src.utils.logger import get_logger

logger = get_logger(__name__)

SERVICE_PATTERN = r"(?:Spotify|Apple Music|YouTube|iTunes|Shazam|Deezer|Amazon Music|Tidal)"
SNAPSHOT_PATTERN = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} [A-Z]{2,4}"
LATIN_AMERICAN_COUNTRIES = {
    "Argentina",
    "Bolivia",
    "Brazil",
    "Chile",
    "Colombia",
    "Costa Rica",
    "Cuba",
    "Dominican Republic",
    "Ecuador",
    "El Salvador",
    "Guatemala",
    "Honduras",
    "Mexico",
    "Nicaragua",
    "Panama",
    "Paraguay",
    "Peru",
    "Puerto Rico",
    "Uruguay",
    "Venezuela",
}


def _normalize_label(value: str) -> str:
    return " ".join(value.split()).strip().casefold()


NORMALIZED_LATIN_AMERICAN_COUNTRIES = {
    _normalize_label(country) for country in LATIN_AMERICAN_COUNTRIES
}


def is_latin_american_country(country_name: str) -> bool:
    return _normalize_label(country_name) in NORMALIZED_LATIN_AMERICAN_COUNTRIES


def extract_item_name_from_summary(summary: str) -> str:
    """Extract the song, album, or country label from a kworb summary row."""
    normalized = " ".join(summary.split())
    if not normalized:
        return ""

    if normalized.startswith("Album:"):
        normalized = normalized.removeprefix("Album:").strip()

    match = re.match(rf"^(.*?)\s+{SERVICE_PATTERN}\b", normalized)
    if match:
        return match.group(1).strip(" :-|")

    return normalized.split(":", 1)[0].strip()


def _collect_item_names(tables: Iterable, limit: Optional[int] = None) -> List[str]:
    items: List[str] = []
    seen: set[str] = set()

    for table in tables:
        if table is None:
            continue

        for row in table.find_all("tr"):
            summary = " ".join(row.get_text(" ", strip=True).split())
            if not summary:
                continue

            item_name = extract_item_name_from_summary(summary)
            if not item_name or item_name in seen:
                continue

            seen.add(item_name)
            items.append(item_name)

            if limit is not None and len(items) >= limit:
                return items

    return items


def parse_artist_detail_page(
    html: str,
    fallback_name: str,
    profile_url: str,
) -> ArtistDetail:
    """Parse one kworb artist detail page into a compact summary object."""
    soup = BeautifulSoup(html, "lxml")
    page_title = soup.title.get_text(strip=True) if soup.title else None
    artist_name = fallback_name
    if page_title and " Chart Positions" in page_title:
        artist_name = page_title.split(" Chart Positions", 1)[0].strip() or fallback_name

    full_text = " ".join(soup.get_text(" ", strip=True).split())
    snapshot_match = re.search(SNAPSHOT_PATTERN, full_text)
    snapshot_text = snapshot_match.group(0) if snapshot_match else None

    tables = soup.find_all("table")
    if len(tables) >= 4:
        song_tables = tables[:2]
        album_table = tables[2]
        country_table = tables[3]
    elif len(tables) == 3:
        song_tables = [tables[0]]
        album_table = tables[1]
        country_table = tables[2]
    elif len(tables) == 2:
        song_tables = [tables[0]]
        album_table = tables[1]
        country_table = None
    elif len(tables) == 1:
        song_tables = [tables[0]]
        album_table = None
        country_table = None
    else:
        song_tables = []
        album_table = None
        country_table = None

    song_items = _collect_item_names(song_tables)
    album_items = _collect_item_names([album_table])
    country_items = [
        country
        for country in _collect_item_names([country_table])
        if is_latin_american_country(country)
    ]

    return ArtistDetail(
        artist_name=artist_name,
        profile_url=profile_url,
        page_title=page_title,
        snapshot_text=snapshot_text,
        songs_count=len(song_items),
        albums_count=len(album_items),
        countries_count=len(country_items),
        top_songs="\n".join(song_items[:10]) or None,
        top_albums="\n".join(album_items[:10]) or None,
        top_countries="\n".join(country_items[:10]) or None,
    )


def scrape_artist_details(limit: int | None = None) -> List[ArtistDetail]:
    """
    Scrape compact artist detail summaries from kworb artist profile pages.
    Country snapshots are restricted to Latin American markets only.
    """
    rankings = scrape_itunes_global_artists()
    if not rankings:
        logger.error("No artist rankings available for detail scraping")
        return []

    if limit is not None:
        limit = max(1, limit)
        rankings = rankings[:limit]
    
    details: List[ArtistDetail] = []

    for ranking in rankings:
        if not ranking.profile_url:
            logger.warning(f"Skipping {ranking.artist_name}: missing profile URL")
            continue

        html = fetch_page(ranking.profile_url)
        if not html:
            logger.warning(f"Skipping {ranking.artist_name}: could not fetch profile page")
            continue

        detail = parse_artist_detail_page(
            html=html,
            fallback_name=ranking.artist_name,
            profile_url=ranking.profile_url,
        )
        details.append(detail)
        logger.info(
            "Scraped artist details for %s (%s songs, %s albums, %s Latin American countries)",
            detail.artist_name,
            detail.songs_count,
            detail.albums_count,
            detail.countries_count,
        )

    logger.info(f"Scraped {len(details)} artist detail pages")
    return details
