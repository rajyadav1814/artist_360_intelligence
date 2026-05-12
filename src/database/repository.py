from typing import List, Dict

from psycopg2.extras import execute_values
from src.database.connection import get_connection
from src.database.models import ArtistDetail, ItunesRanking, SpotifyArtist, TrendingArtist, SpotifyDaily, ItunesDaily, TrackRanking
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


def _batch_upsert_artists(cur, artist_data: List[tuple]) -> Dict[str, int]:
    """Batch upsert artists and return a mapping of name -> artist_id.
    
    Args:
        artist_data: List of (name, profile_url) tuples
    
    Returns:
        Dict mapping artist name to artist_id
    """
    if not artist_data:
        return {}
    
    # Use execute_values for efficient batch insert
    query = """
        INSERT INTO artists (name, profile_url, updated_at)
        VALUES %s
        ON CONFLICT (name) DO UPDATE SET
            profile_url = COALESCE(EXCLUDED.profile_url, artists.profile_url),
            updated_at = NOW()
        RETURNING name, id
    """
    
    result = execute_values(
        cur, query, artist_data,
        template="(%s, %s, NOW())",
        fetch=True
    )
    
    # Create mapping of artist name to ID
    return {row["name"]: row["id"] for row in result}


def save_itunes_rankings(rankings: List[ItunesRanking]) -> int:
    """Bulk-save iTunes global artist rankings using batch processing. Returns row count."""
    if not rankings:
        return 0
    
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Step 1: Batch upsert all artists
                artist_data = [(r.artist_name, r.profile_url) for r in rankings]
                artist_map = _batch_upsert_artists(cur, artist_data)
                
                # Step 2: Batch insert iTunes rankings
                rankings_data = [
                    (
                        artist_map[r.artist_name],
                        r.rank,
                        r.rank_change,
                        r.total_points,
                        r.itunes_points,
                        r.spotify_points,
                        r.apple_music_points,
                        r.shazam_points,
                        r.youtube_points,
                        r.other_points,
                        r.top_country,
                        r.num_countries,
                        r.scrape_date
                    )
                    for r in rankings
                    if r.artist_name in artist_map
                ]
                
                execute_values(
                    cur,
                    """
                    INSERT INTO itunes_artist_rankings
                        (artist_id, rank, rank_change, total_points,
                         itunes_points, spotify_points, apple_music_points,
                         shazam_points, youtube_points, other_points,
                         top_country, num_countries, scrape_date)
                    VALUES %s
                    """,
                    rankings_data
                )
                
                saved = len(rankings_data)
    finally:
        conn.close()
    
    logger.info(f"Saved {saved} iTunes rankings to DB")
    return saved


def save_spotify_artists(artists: List[SpotifyArtist]) -> int:
    """Bulk-save Spotify artist listener data using batch processing. Returns row count."""
    if not artists:
        return 0
    
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Step 1: Batch upsert all artists
                artist_data = [(a.artist_name, None) for a in artists]
                artist_map = _batch_upsert_artists(cur, artist_data)
                
                # Step 2: Batch insert Spotify data
                spotify_data = [
                    (
                        artist_map[a.artist_name],
                        a.monthly_listeners,
                        a.peak_listeners,
                        a.peak_date,
                        a.scrape_date
                    )
                    for a in artists
                    if a.artist_name in artist_map
                ]
                
                execute_values(
                    cur,
                    """
                    INSERT INTO spotify_artists
                        (artist_id, monthly_listeners, peak_listeners, peak_date, scrape_date)
                    VALUES %s
                    """,
                    spotify_data
                )
                
                saved = len(spotify_data)
    finally:
        conn.close()
    
    logger.info(f"Saved {saved} Spotify artists to DB")
    return saved


def save_trending_artists(trending: List[TrendingArtist]) -> int:
    """Upsert trending artist data for a given month using batch processing. Returns row count."""
    if not trending:
        return 0
    
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Step 1: Batch upsert all artists
                artist_data = [(t.artist_name, None) for t in trending]
                artist_map = _batch_upsert_artists(cur, artist_data)
                
                # Step 2: Batch upsert trending data
                trending_data = [
                    (
                        artist_map[t.artist_name],
                        t.source,
                        t.rank,
                        t.rank_change,
                        t.total_points,
                        t.top_country,
                        t.month
                    )
                    for t in trending
                    if t.artist_name in artist_map
                ]
                
                execute_values(
                    cur,
                    """
                    INSERT INTO trending_artists_monthly
                        (artist_id, source, rank, rank_change,
                         total_points, top_country, month)
                    VALUES %s
                    ON CONFLICT (artist_id, source, month)
                    DO UPDATE SET
                        rank         = EXCLUDED.rank,
                        rank_change  = EXCLUDED.rank_change,
                        total_points = EXCLUDED.total_points,
                        top_country  = EXCLUDED.top_country,
                        scraped_at   = NOW()
                    """,
                    trending_data
                )
                
                saved = len(trending_data)
    finally:
        conn.close()
    
    logger.info(f"Saved {saved} trending artist records to DB")
    return saved


def save_artist_details(details: List[ArtistDetail]) -> int:
    """Upsert artist detail snapshots using batch processing. Returns row count."""
    if not details:
        return 0
    
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Step 1: Batch upsert all artists
                artist_data = [(d.artist_name, d.profile_url) for d in details]
                artist_map = _batch_upsert_artists(cur, artist_data)
                
                # Step 2: Batch upsert artist details
                details_data = [
                    (
                        artist_map[d.artist_name],
                        d.page_title,
                        d.snapshot_text,
                        d.songs_count,
                        d.albums_count,
                        d.countries_count,
                        d.top_songs,
                        d.top_albums,
                        d.top_countries,
                        d.scrape_date
                    )
                    for d in details
                    if d.artist_name in artist_map
                ]
                
                execute_values(
                    cur,
                    """
                    INSERT INTO artist_details
                        (artist_id, page_title, snapshot_text, songs_count,
                         albums_count, countries_count, top_songs, top_albums,
                         top_countries, scrape_date)
                    VALUES %s
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
                    details_data
                )
                
                saved = len(details_data)
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


def save_spotify_daily(data: List[SpotifyDaily]) -> int:
    """Bulk-save Spotify daily chart data."""
    if not data:
        return 0
    
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                rows = [
                    (
                        d.date, d.country, d.rank, d.artist_title,
                        d.days, d.peak, d.streams, d.streams_change, d.total_streams, d.label
                    )
                    for d in data
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO spotify_daily
                        (date, country, rank, artist_title, days, peak, streams, streams_change, total_streams, label)
                    VALUES %s
                    ON CONFLICT (date, country, rank, artist_title) DO UPDATE SET
                        days = EXCLUDED.days,
                        peak = EXCLUDED.peak,
                        streams = EXCLUDED.streams,
                        streams_change = EXCLUDED.streams_change,
                        total_streams = EXCLUDED.total_streams,
                        label = EXCLUDED.label
                    """,
                    rows
                )
                return len(rows)
    finally:
        conn.close()


def save_itunes_daily(data: List[ItunesDaily]) -> int:
    """Bulk-save iTunes daily chart data."""
    if not data:
        return 0
    
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                rows = [
                    (
                        d.date, d.country, d.rank, d.artist_title,
                        d.days, d.peak, d.points, d.points_change, d.total_points, d.label
                    )
                    for d in data
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO itunes_daily
                        (date, country, rank, artist_title, days, peak, points, points_change, total_points, label)
                    VALUES %s
                    ON CONFLICT (date, country, rank, artist_title) DO UPDATE SET
                        days = EXCLUDED.days,
                        peak = EXCLUDED.peak,
                        points = EXCLUDED.points,
                        points_change = EXCLUDED.points_change,
                        total_points = EXCLUDED.total_points,
                        label = EXCLUDED.label
                    """,
                    rows
                )
                return len(rows)
    finally:
        conn.close()


def save_track_rankings(data: List[TrackRanking]) -> int:
    """Bulk-save track rankings."""
    if not data:
        return 0
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            rows = [
                (
                    r.track_id,
                    r.rank,
                    r.streams,
                    r.week_number,
                    r.fiscal_year,
                    r.chart_date,
                    r.scrape_date,
                )
                for r in data
            ]
            execute_values(
                cur,
                """
                INSERT INTO track_rankings (track_id, rank, streams, week_number, fiscal_year, chart_date, scrape_date)
                VALUES %s
                ON CONFLICT (track_id, chart_date) DO UPDATE SET
                    rank = EXCLUDED.rank,
                    streams = EXCLUDED.streams,
                    week_number = EXCLUDED.week_number,
                    fiscal_year = EXCLUDED.fiscal_year,
                    scrape_date = EXCLUDED.scrape_date
                """,
                rows
            )
            conn.commit()
            return len(rows)
    finally:
        conn.close()


def save_track_rankings_from_raw(raw_data) -> int:
    """Save track rankings from raw scraper data (artist_name, title, rank, streams)."""
    if not raw_data:
        return 0
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            inserted = 0
            for item in raw_data:
                # Upsert artist
                cur.execute(
                    """
                    INSERT INTO artists (name, updated_at)
                    VALUES (%s, NOW())
                    ON CONFLICT (name) DO UPDATE SET updated_at = NOW()
                    RETURNING id
                    """,
                    (item.artist_name,),
                )
                artist_id = cur.fetchone()["id"]
                
                # Upsert track
                cur.execute(
                    """
                    INSERT INTO tracks (artist_id, title)
                    VALUES (%s, %s)
                    ON CONFLICT (artist_id, title) DO NOTHING
                    RETURNING id
                    """,
                    (artist_id, item.title),
                )
                row = cur.fetchone()
                if row:
                    track_id = row["id"]
                else:
                    cur.execute(
                        "SELECT id FROM tracks WHERE artist_id = %s AND title = %s",
                        (artist_id, item.title),
                    )
                    track_id = cur.fetchone()["id"]
                
                # Insert track ranking
                cur.execute(
                    """
                    INSERT INTO track_rankings (track_id, rank, streams, week_number, fiscal_year, chart_date, scrape_date)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE)
                    ON CONFLICT (track_id, chart_date) DO UPDATE SET
                        rank = EXCLUDED.rank,
                        streams = EXCLUDED.streams,
                        week_number = EXCLUDED.week_number,
                        fiscal_year = EXCLUDED.fiscal_year
                    """,
                    (track_id, item.rank, item.streams, item.week_number, item.fiscal_year, item.chart_date),
                )
                inserted += 1
            
            conn.commit()
            return inserted
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving track rankings: {e}")
        raise
    finally:
        conn.close()