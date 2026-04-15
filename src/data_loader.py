import pandas as pd
import streamlit as st
from src.database.connection import get_connection
from src.scrapers.artist_details_scraper import LATIN_AMERICAN_COUNTRIES
from src.ui.utils import TRACKER_TOP_ARTISTS

def query_to_df(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = [dict(row) for row in cur.fetchall()]
        return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def load_dashboard_data() -> dict[str, pd.DataFrame]:
    queries = {
        "itunes": """
            WITH latest_run AS (
                SELECT MAX(scraped_at) AS ts FROM itunes_artist_rankings
            )
            SELECT a.name, a.profile_url, r.rank, r.rank_change, r.total_points,
                   r.itunes_points, r.spotify_points, r.apple_music_points,
                   r.shazam_points, r.youtube_points, r.other_points,
                   r.top_country, r.num_countries, r.scrape_date, r.scraped_at
            FROM itunes_artist_rankings r
            JOIN artists a ON a.id = r.artist_id
            JOIN latest_run lr ON r.scraped_at = lr.ts
            ORDER BY r.rank ASC
        """,
        "spotify": """
            WITH latest_run AS (
                SELECT MAX(scraped_at) AS ts FROM spotify_artists
            )
            SELECT a.name, s.monthly_listeners, s.peak_listeners, s.peak_date,
                   s.scrape_date, s.scraped_at
            FROM spotify_artists s
            JOIN artists a ON a.id = s.artist_id
            JOIN latest_run lr ON s.scraped_at = lr.ts
            ORDER BY s.monthly_listeners DESC NULLS LAST
        """,
        "details": """
            SELECT DISTINCT ON (a.name)
                   a.name, ad.page_title, ad.snapshot_text, ad.songs_count,
                   ad.albums_count, ad.countries_count, ad.top_songs,
                   ad.top_albums, ad.top_countries, ad.scrape_date, ad.scraped_at
            FROM artist_details ad
            JOIN artists a ON a.id = ad.artist_id
            ORDER BY a.name, ad.scraped_at DESC
        """,
        "runs": """
            SELECT source, status, rows_upserted, started_at, finished_at
            FROM scrape_runs
            ORDER BY finished_at DESC NULLS LAST, started_at DESC
            LIMIT 100
        """,
        "history": f"""
            WITH latest_run AS (
                SELECT MAX(scraped_at) AS ts FROM itunes_artist_rankings
            ),
            top_artists AS (
                SELECT artist_id
                FROM itunes_artist_rankings r
                JOIN latest_run lr ON r.scraped_at = lr.ts
                WHERE r.rank <= {TRACKER_TOP_ARTISTS}
            )
            SELECT a.name, r.rank, r.scraped_at
            FROM itunes_artist_rankings r
            JOIN artists a ON a.id = r.artist_id
            WHERE r.artist_id IN (SELECT artist_id FROM top_artists)
            ORDER BY r.scraped_at ASC, r.rank ASC
        """,
        "longevity": """
            SELECT 
                a.name,
                COUNT(*) as times_on_chart,
                COUNT(DISTINCT DATE_TRUNC('week', r.scrape_date)) as weeks_on_chart,
                COUNT(*) FILTER (WHERE r.rank = 1) as times_at_top,
                MAX(r.scrape_date) FILTER (WHERE r.rank = 1) as last_day_at_top,
                MAX(r.num_countries) as max_countries,
                MIN(r.rank) as best_rank
            FROM itunes_artist_rankings r
            JOIN artists a ON a.id = r.artist_id
            GROUP BY a.name
        """,
        "top_history": """
            SELECT r.scrape_date, a.name as artist
            FROM itunes_artist_rankings r
            JOIN artists a ON a.id = r.artist_id
            WHERE r.rank = 1
            ORDER BY r.scrape_date DESC
        """
    }

    conn = get_connection()
    try:
        frames = {name: query_to_df(conn, sql) for name, sql in queries.items()}
    finally:
        conn.close()

    if not frames["runs"].empty:
        frames["runs"]["finished_at"] = pd.to_datetime(frames["runs"]["finished_at"], errors="coerce")
        frames["runs"]["started_at"] = pd.to_datetime(frames["runs"]["started_at"], errors="coerce")
    if not frames["history"].empty:
        frames["history"]["scraped_at"] = pd.to_datetime(frames["history"]["scraped_at"], errors="coerce")
    if not frames["top_history"].empty:
        frames["top_history"]["scrape_date"] = pd.to_datetime(frames["top_history"]["scrape_date"], errors="coerce")
    if not frames["longevity"].empty:
        frames["longevity"]["last_day_at_top"] = pd.to_datetime(frames["longevity"]["last_day_at_top"], errors="coerce")

    leaderboard = frames["itunes"].merge(
        frames["spotify"][["name", "monthly_listeners", "peak_listeners"]],
        on="name",
        how="left",
    ).merge(
        frames["details"][["name", "songs_count", "albums_count", "countries_count", "top_songs", "top_albums", "top_countries"]],
        on="name",
        how="left",
    ).merge(
        frames["longevity"][["name", "times_on_chart", "weeks_on_chart", "times_at_top", "last_day_at_top", "max_countries", "best_rank"]],
        on="name",
        how="left"
    )

    for col in [
        "monthly_listeners",
        "peak_listeners",
        "total_points",
        "countries_count",
        "itunes_points",
        "spotify_points",
        "apple_music_points",
        "shazam_points",
        "youtube_points",
        "other_points",
    ]:
        if col in leaderboard.columns:
            leaderboard[col] = pd.to_numeric(leaderboard[col], errors="coerce")

    leaderboard["top_song"] = leaderboard["top_songs"].fillna("").apply(
        lambda value: value.split("\n")[0].strip() if str(value).strip() else "—"
    )

    def filter_latam_countries(countries_blob: str) -> list[str]:
        return [
            item.strip()
            for item in str(countries_blob or "").split("\n")
            if item.strip() in LATIN_AMERICAN_COUNTRIES
        ]

    leaderboard["latam_countries"] = leaderboard["top_countries"].apply(filter_latam_countries)
    leaderboard["top_countries"] = leaderboard["latam_countries"].apply(lambda items: "\n".join(items))
    leaderboard["countries_count"] = leaderboard["latam_countries"].apply(len)

    def pick_display_country(row: pd.Series) -> str:
        top_country = str(row.get("top_country") or "").strip()
        if top_country in LATIN_AMERICAN_COUNTRIES:
            return top_country
        latam_list = row.get("latam_countries") or []
        return latam_list[0] if latam_list else ""

    leaderboard["display_country"] = leaderboard.apply(pick_display_country, axis=1)
    leaderboard["latam_signal"] = leaderboard["display_country"].ne("")
    leaderboard["display_country"] = leaderboard["display_country"].replace("", "—")
    
    return {
        "leaderboard": leaderboard,
        "runs": frames["runs"],
        "history": frames["history"],
        "top_history": frames["top_history"]
    }
