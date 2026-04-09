from typing import List

from src.database.connection import get_connection
from src.database.models import ArtistDetail, ItunesRanking, SpotifyArtist, TrendingArtist
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _upsert_artist(cur, name: str, profile_url: str = None) -> int:
    """Insert artist if not exists, return its id."""
    cur.execute(
        """
        INSERT INTO artists (name, profile_url, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (name) DO UPDATE SET
            profile_url = COALESCE(EXCLUDED.profile_url, artists.profile_url),
            updated_at = NOW()
        RETURNING id
        """,
        (name, profile_url),
    )
    return cur.fetchone()["id"]


def save_itunes_rankings(rankings: List[ItunesRanking]) -> int:
    """Bulk-save iTunes global artist rankings. Returns row count."""
    conn = get_connection()
    saved = 0
    try:
        with conn:
            with conn.cursor() as cur:
                for r in rankings:
                    artist_id = _upsert_artist(cur, r.artist_name, r.profile_url)
                    cur.execute(
                        """
                        INSERT INTO itunes_artist_rankings
                            (artist_id, rank, rank_change, total_points,
                             itunes_points, spotify_points, apple_music_points,
                             shazam_points, youtube_points, other_points,
                             top_country, num_countries, scrape_date)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            artist_id, r.rank, r.rank_change, r.total_points,
                            r.itunes_points, r.spotify_points, r.apple_music_points,
                            r.shazam_points, r.youtube_points, r.other_points,
                            r.top_country, r.num_countries, r.scrape_date,
                        ),
                    )
                    saved += 1
    finally:
        conn.close()
    logger.info(f"Saved {saved} iTunes rankings to DB")
    return saved


def save_spotify_artists(artists: List[SpotifyArtist]) -> int:
    """Bulk-save Spotify artist listener data. Returns row count."""
    conn = get_connection()
    saved = 0
    try:
        with conn:
            with conn.cursor() as cur:
                for a in artists:
                    artist_id = _upsert_artist(cur, a.artist_name)
                    cur.execute(
                        """
                        INSERT INTO spotify_artists
                            (artist_id, monthly_listeners, peak_listeners,
                             peak_date, scrape_date)
                        VALUES (%s,%s,%s,%s,%s)
                        """,
                        (
                            artist_id, a.monthly_listeners, a.peak_listeners,
                            a.peak_date, a.scrape_date,
                        ),
                    )
                    saved += 1
    finally:
        conn.close()
    logger.info(f"Saved {saved} Spotify artists to DB")
    return saved


def save_trending_artists(trending: List[TrendingArtist]) -> int:
    """Upsert trending artist data for a given month. Returns row count."""
    conn = get_connection()
    saved = 0
    try:
        with conn:
            with conn.cursor() as cur:
                for t in trending:
                    artist_id = _upsert_artist(cur, t.artist_name)
                    cur.execute(
                        """
                        INSERT INTO trending_artists_monthly
                            (artist_id, source, rank, rank_change,
                             total_points, top_country, month)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (artist_id, source, month)
                        DO UPDATE SET
                            rank         = EXCLUDED.rank,
                            rank_change  = EXCLUDED.rank_change,
                            total_points = EXCLUDED.total_points,
                            top_country  = EXCLUDED.top_country,
                            scraped_at   = NOW()
                        """,
                        (
                            artist_id, t.source, t.rank, t.rank_change,
                            t.total_points, t.top_country, t.month,
                        ),
                    )
                    saved += 1
    finally:
        conn.close()
    logger.info(f"Saved {saved} trending artist records to DB")
    return saved


def save_artist_details(details: List[ArtistDetail]) -> int:
    """Upsert artist detail snapshots. Returns row count."""
    conn = get_connection()
    saved = 0
    try:
        with conn:
            with conn.cursor() as cur:
                for detail in details:
                    artist_id = _upsert_artist(cur, detail.artist_name, detail.profile_url)
                    cur.execute(
                        """
                        INSERT INTO artist_details
                            (artist_id, page_title, snapshot_text, songs_count,
                             albums_count, countries_count, top_songs, top_albums,
                             top_countries, scrape_date)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (artist_id, scrape_date)
                        DO UPDATE SET
                            page_title     = EXCLUDED.page_title,
                            snapshot_text  = EXCLUDED.snapshot_text,
                            songs_count    = EXCLUDED.songs_count,
                            albums_count   = EXCLUDED.albums_count,
                            countries_count= EXCLUDED.countries_count,
                            top_songs      = EXCLUDED.top_songs,
                            top_albums     = EXCLUDED.top_albums,
                            top_countries  = EXCLUDED.top_countries,
                            scraped_at     = NOW()
                        """,
                        (
                            artist_id,
                            detail.page_title,
                            detail.snapshot_text,
                            detail.songs_count,
                            detail.albums_count,
                            detail.countries_count,
                            detail.top_songs,
                            detail.top_albums,
                            detail.top_countries,
                            detail.scrape_date,
                        ),
                    )
                    saved += 1
    finally:
        conn.close()
    logger.info(f"Saved {saved} artist detail snapshots to DB")
    return saved


def log_scrape_run(source: str, status: str, rows: int = 0, error: str = None) -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scrape_runs (source, status, rows_upserted, error_msg, finished_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (source, status, rows, error),
                )
    finally:
        conn.close()
