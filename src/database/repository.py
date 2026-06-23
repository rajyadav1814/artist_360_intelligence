from typing import List, Dict

from psycopg2 import errors
from psycopg2.extras import execute_values
from src.database.connection import get_connection
from src.database.models import ArtistDetail, ItunesRanking, SpotifyArtist, TrendingArtist, SpotifyDaily, ItunesDaily, ItunesArtistAlbum
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


def _repair_serial_sequence(cur, table_name: str) -> None:
    """
    Repair a SERIAL/IDENTITY sequence if it has fallen behind MAX(id).

    This is safe to call repeatedly and is a no-op when the table has no
    sequence or when the sequence is already ahead of the data.
    """
    cur.execute("SELECT pg_get_serial_sequence(%s, 'id') AS seq_name", (table_name,))
    row = cur.fetchone()
    seq_name = row["seq_name"] if row else None
    if not seq_name:
        return

    cur.execute(
        f"""
        SELECT setval(
            %s,
            COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1,
            false
        )
        """,
        (seq_name,),
    )


def _repair_serial_sequences(cur, table_names: List[str]) -> None:
    for table_name in table_names:
        _repair_serial_sequence(cur, table_name)


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
                _repair_serial_sequences(cur, ["artists", "itunes_artist_rankings"])

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
                _repair_serial_sequences(cur, ["artists", "spotify_artists"])

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
                _repair_serial_sequences(cur, ["artists", "trending_artists_monthly"])

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
                _repair_serial_sequences(cur, ["artists", "artist_details"])

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
    insert_sql = """
        INSERT INTO scrape_runs (source, status, rows_upserted, error_msg, finished_at)
        VALUES (%s, %s, %s, %s, NOW())
    """
    conn = get_connection()
    try:
        try:
            with conn:
                with conn.cursor() as cur:
                    _repair_serial_sequence(cur, "scrape_runs")
                    cur.execute(insert_sql, (source, status, rows, error))
        except errors.UniqueViolation as exc:
            if getattr(exc.diag, "constraint_name", None) != "scrape_runs_pkey":
                raise

            # If the database was restored or rows were inserted manually, the
            # SERIAL sequence can fall behind MAX(id). Repair it once and retry.
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT setval(
                            pg_get_serial_sequence('scrape_runs', 'id'),
                            COALESCE((SELECT MAX(id) FROM scrape_runs), 0) + 1,
                            false
                        )
                        """
                    )
                    cur.execute(insert_sql, (source, status, rows, error))
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
                _repair_serial_sequence(cur, "spotify_daily")

                rows = [
                    (
                        d.date, d.country, d.rank, d.artist_title,
                        d.days, d.peak, d.streams, d.streams_change, d.total_streams, d.label, d.rank_change, d.genere
                    )
                    for d in data
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO spotify_daily
                        (date, country, rank, artist_title, days, peak, streams, streams_change, total_streams, label, rank_change, genere)
                    VALUES %s
                    ON CONFLICT (date, country, rank, artist_title)
                    DO UPDATE SET
                        days            = EXCLUDED.days,
                        peak            = EXCLUDED.peak,
                        streams         = EXCLUDED.streams,
                        streams_change  = EXCLUDED.streams_change,
                        total_streams   = EXCLUDED.total_streams,
                        label           = COALESCE(EXCLUDED.label, spotify_daily.label),
                        rank_change     = EXCLUDED.rank_change,
                        genere          = COALESCE(EXCLUDED.genere, spotify_daily.genere),
                        scraped_at      = NOW()
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
                _repair_serial_sequence(cur, "itunes_daily")

                rows = [
                    (
                        d.date, d.country, d.rank, d.artist_title,
                        d.days, d.peak, d.points, d.points_change, d.total_points, d.label, d.rank_change, d.genere
                    )
                    for d in data
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO itunes_daily
                        (date, country, rank, artist_title, days, peak, points, points_change, total_points, label, rank_change, genere)
                    VALUES %s
                    ON CONFLICT (date, country, rank, artist_title)
                    DO UPDATE SET
                        days            = EXCLUDED.days,
                        peak            = EXCLUDED.peak,
                        points          = EXCLUDED.points,
                        points_change   = EXCLUDED.points_change,
                        total_points    = EXCLUDED.total_points,
                        label           = COALESCE(EXCLUDED.label, itunes_daily.label),
                        rank_change     = EXCLUDED.rank_change,
                        genere          = COALESCE(EXCLUDED.genere, itunes_daily.genere),
                        scraped_at      = NOW()
                    """,
                    rows
                )
                return len(rows)
    finally:
        conn.close()


def save_itunes_artist_album(data: List[ItunesArtistAlbum]) -> int:
    """Bulk-save iTunes artist album daily chart data."""
    if not data:
        return 0
    
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                _repair_serial_sequence(cur, "itunes_artist_album")

                rows = [
                    (
                        d.date, d.country, d.rank, d.artist_title,
                        d.days, d.peak, d.points, d.points_change, d.total_points, d.label, d.rank_change, d.genere
                    )
                    for d in data
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO itunes_artist_album
                        (date, country, rank, artist_title, days, peak, points, points_change, total_points, label, rank_change, genere)
                    VALUES %s
                    ON CONFLICT (date, country, rank, artist_title)
                    DO UPDATE SET
                        days            = EXCLUDED.days,
                        peak            = EXCLUDED.peak,
                        points          = EXCLUDED.points,
                        points_change   = EXCLUDED.points_change,
                        total_points    = EXCLUDED.total_points,
                        label           = COALESCE(EXCLUDED.label, itunes_artist_album.label),
                        rank_change     = EXCLUDED.rank_change,
                        genere          = COALESCE(EXCLUDED.genere, itunes_artist_album.genere),
                        scraped_at      = NOW()
                    """,
                    rows
                )
                return len(rows)
    finally:
        conn.close()
