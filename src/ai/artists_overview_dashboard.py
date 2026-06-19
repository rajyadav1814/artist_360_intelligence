from __future__ import annotations

import json
import math
from html import escape
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src.database.connection import get_connection
from src.utils.image_utils import get_artist_image_url, get_fallback_avatar_url
from src.utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_DAYS = 30
ARTIST_IMAGE_LOOKUP_LIMIT = 50


def _run_query(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.error("artists overview query failed: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _split_artist_title(value: str | None) -> tuple[str, str]:
    raw = str(value or "").strip()
    if " - " in raw:
        artist, title = raw.split(" - ", 1)
        return artist.strip(), title.strip()
    return raw or "Unknown", raw or "Unknown"


def _fmt_n(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "0"
    value = float(value)
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(int(value))


def _short_label(value: str, limit: int = 20) -> str:
    value = str(value or "Unknown").strip()
    return value if len(value) <= limit else value[: max(0, limit - 3)] + "..."


def _sparkline_svg(values: list[float], color: str = "#60a5fa") -> str:
    """Generate a simple SVG sparkline for trend visualization."""
    if not values or len(values) < 2:
        return ""
    # Normalize to a compact trend area for ranking rows.
    min_v, max_v = min(values), max(values)
    span = max(max_v - min_v, 1.0)
    width, height = 68, 18
    pts = []
    for i, v in enumerate(values):
        x = (i / (len(values) - 1)) * width
        y = height - ((v - min_v) / span) * height
        pts.append(f"{x:.1f},{y:.1f}")

    # Add a soft fill under the path for more "visible" density
    fill_pts = f"0,{height} " + " ".join(pts) + f" {width},{height}"

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:block; overflow:visible">'
        f'<polygon points="{fill_pts}" fill="{color}" fill-opacity="0.12"/>'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )


def _is_valid_artist_name(value: Any) -> bool:
    name = str(value or "").strip()
    return bool(name) and name.lower() not in {"null", "none", "nan"}


def _format_rank_change(value: Any) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw or raw in {"0", "=", "-", "—"}:
        return "Stable", "flat"
    if raw.upper() == "NEW":
        return "New", "up"

    cleaned = raw.replace("▲", "").replace("▼", "").replace("+", "").replace("-", "")
    try:
        amount = float(cleaned)
    except ValueError:
        return raw, "flat"

    if raw.startswith("-") or "▼" in raw:
        return f"▼{abs(amount):.0f}", "down"
    if raw.startswith("+") or "▲" in raw:
        return f"▲{abs(amount):.0f}", "up"
    if amount > 0:
        return f"▲{abs(amount):.0f}", "up"
    if amount < 0:
        return f"▼{abs(amount):.0f}", "down"
    return "Stable", "flat"


@st.cache_data(ttl=300, show_spinner=False)
def _load_artist_rank_history(days: int = WINDOW_DAYS) -> pd.DataFrame:
    query = """
        WITH bounds AS (
            SELECT MAX(scrape_date) AS max_d FROM itunes_artist_rankings
        ),
        ranked AS (
            SELECT
                r.artist_id,
                a.name,
                r.scrape_date,
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
                ROW_NUMBER() OVER (
                    PARTITION BY r.artist_id, r.scrape_date
                    ORDER BY r.scraped_at DESC NULLS LAST
                ) AS rn
            FROM itunes_artist_rankings r
            JOIN artists a ON a.id = r.artist_id
            CROSS JOIN bounds b
            WHERE r.scrape_date = b.max_d
        )
        SELECT * FROM ranked WHERE rn = 1
    """
    rows = _run_query(query)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
    for col in [
        "rank",
        "total_points",
        "itunes_points",
        "spotify_points",
        "apple_music_points",
        "shazam_points",
        "youtube_points",
        "other_points",
        "num_countries",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _load_spotify_artist_latest() -> pd.DataFrame:
    query = """
        WITH latest AS (
            SELECT MAX(scraped_at) AS ts FROM spotify_artists
        )
        SELECT a.name, s.monthly_listeners, s.peak_listeners, s.peak_date
        FROM spotify_artists s
        JOIN artists a ON a.id = s.artist_id
        JOIN latest l ON s.scraped_at = l.ts
    """
    rows = _run_query(query)
    if not rows:
        return pd.DataFrame(columns=["name", "monthly_listeners", "peak_listeners", "peak_date"])
    df = pd.DataFrame(rows)
    df["monthly_listeners"] = pd.to_numeric(df["monthly_listeners"], errors="coerce")
    df["peak_listeners"] = pd.to_numeric(df["peak_listeners"], errors="coerce")
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _load_artist_details_latest() -> pd.DataFrame:
    query = """
        SELECT DISTINCT ON (a.name)
            a.name,
            ad.songs_count,
            ad.albums_count,
            ad.countries_count,
            ad.top_songs,
            ad.top_albums,
            ad.top_countries,
            ad.scrape_date
        FROM artist_details ad
        JOIN artists a ON a.id = ad.artist_id
        WHERE a.name IS NOT NULL
          AND btrim(a.name) <> ''
          AND lower(btrim(a.name)) NOT IN ('null', 'none', 'nan')
        ORDER BY a.name, ad.scraped_at DESC
    """
    rows = _run_query(query)
    if not rows:
        return pd.DataFrame(columns=["name", "songs_count", "albums_count", "countries_count"])
    df = pd.DataFrame(rows)
    for col in ["songs_count", "albums_count", "countries_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _load_track_dashboard(days: int = WINDOW_DAYS) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    query = """
        WITH sp_bounds AS (SELECT MAX(date) AS max_d FROM spotify_daily),
        it_bounds AS (SELECT MAX(date) AS max_d FROM itunes_daily),
        raw_rows AS (
            SELECT d.artist_title, d.rank, d.days, d.streams::numeric AS metric
            FROM spotify_daily d, sp_bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
            UNION ALL
            SELECT d.artist_title, d.rank, d.days, d.points::numeric AS metric
            FROM itunes_daily d, it_bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
        ),
        parsed AS MATERIALIZED (
            SELECT
                artist_title,
                CASE
                    WHEN position(' - ' in artist_title) > 0 THEN split_part(artist_title, ' - ', 1)
                    ELSE COALESCE(NULLIF(artist_title, ''), 'Unknown')
                END AS artist,
                CASE
                    WHEN position(' - ' in artist_title) > 0 THEN substring(artist_title from position(' - ' in artist_title) + 3)
                    ELSE COALESCE(NULLIF(artist_title, ''), 'Unknown')
                END AS title,
                rank,
                days,
                COALESCE(metric, 0) AS metric
            FROM raw_rows
        ),
        artist_stats AS (
            SELECT
                artist,
                SUM(metric) AS metric,
                COUNT(DISTINCT title) AS chart_count,
                COUNT(*) AS entries,
                MIN(rank) AS best_rank,
                MAX(days) AS max_days,
                COUNT(*) AS row_count
            FROM parsed
            GROUP BY artist
        ),
        track_stats AS (
            SELECT artist, title, SUM(metric) AS metric, MIN(rank) AS best_rank
            FROM parsed
            GROUP BY artist, title
            ORDER BY metric DESC
            LIMIT 100
        ),
        kpis AS (
            SELECT
                SUM(metric) AS metric,
                COUNT(DISTINCT artist_title) FILTER (WHERE rank <= 10) AS popular_songs,
                COUNT(DISTINCT artist_title) AS unique_songs,
                COUNT(*) AS entries,
                MAX(days) AS max_days,
                COUNT(*) AS row_count
            FROM parsed
        )
        SELECT
            'artist'::text AS row_type,
            artist AS label,
            metric,
            chart_count,
            entries,
            best_rank,
            max_days,
            row_count,
            artist AS artist,
            NULL::bigint AS unique_songs
        FROM artist_stats
        UNION ALL
        SELECT
            'track'::text AS row_type,
            title AS label,
            metric,
            NULL::bigint AS chart_count,
            NULL::bigint AS entries,
            best_rank,
            NULL::integer AS max_days,
            NULL::bigint AS row_count,
            artist AS artist,
            NULL::bigint AS unique_songs
        FROM track_stats
        UNION ALL
        SELECT
            'kpi'::text AS row_type,
            '__all__' AS label,
            metric,
            popular_songs AS chart_count,
            entries,
            NULL::integer AS best_rank,
            max_days,
            row_count,
            NULL::text AS artist,
            unique_songs AS unique_songs
        FROM kpis
    """
    rows = _run_query(query, (days, days))
    if not rows:
        return pd.DataFrame(), pd.DataFrame(), {"max_days": 0, "popular_songs": 0, "row_count": 0, "unique_songs": 0}
    df = pd.DataFrame(rows)
    for col in ["metric", "chart_count", "entries", "best_rank", "max_days", "row_count", "unique_songs"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    artist_stats = (
        df[df["row_type"] == "artist"]
        .rename(
            columns={
                "label": "name",
                "metric": "track_metric",
                "chart_count": "chart_tracks",
                "entries": "track_entries",
                "best_rank": "best_track_rank",
            }
        )[["name", "chart_tracks", "track_entries", "track_metric", "best_track_rank"]]
        .copy()
    )
    top_tracks = (
        df[df["row_type"] == "track"]
        .rename(columns={"label": "title"})[["title", "metric", "artist"]]
        .sort_values("metric", ascending=False)
        .reset_index(drop=True)
    )
    kpi_row = df[df["row_type"] == "kpi"].head(1)
    kpis = {
        "max_days": float(kpi_row["max_days"].iloc[0]) if not kpi_row.empty else 0,
        "popular_songs": float(kpi_row["chart_count"].iloc[0]) if not kpi_row.empty else 0,
        "row_count": float(kpi_row["row_count"].iloc[0]) if not kpi_row.empty else 0,
        "unique_songs": float(kpi_row["unique_songs"].iloc[0]) if not kpi_row.empty and "unique_songs" in kpi_row.columns else 0,
    }
    return artist_stats, top_tracks, kpis


@st.cache_data(ttl=300, show_spinner=False)
def _load_songs_rank_leaderboard(days: int = WINDOW_DAYS) -> pd.DataFrame:
    query = """
        WITH sp_bounds AS (SELECT MAX(date) AS max_d FROM spotify_daily),
        it_bounds AS (SELECT MAX(date) AS max_d FROM itunes_daily),
        raw_rows AS (
            SELECT
                'Spotify'::text AS platform,
                d.artist_title,
                d.rank,
                d.days,
                d.streams::numeric AS metric,
                d.date
            FROM spotify_daily d, sp_bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
            UNION ALL
            SELECT
                'iTunes'::text AS platform,
                d.artist_title,
                d.rank,
                d.days,
                d.points::numeric AS metric,
                d.date
            FROM itunes_daily d, it_bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
        ),
        parsed AS MATERIALIZED (
            SELECT
                platform,
                CASE
                    WHEN position(' - ' in artist_title) > 0 THEN split_part(artist_title, ' - ', 1)
                    ELSE COALESCE(NULLIF(artist_title, ''), 'Unknown')
                END AS artist,
                CASE
                    WHEN position(' - ' in artist_title) > 0 THEN substring(artist_title from position(' - ' in artist_title) + 3)
                    ELSE COALESCE(NULLIF(artist_title, ''), 'Unknown')
                END AS title,
                rank,
                COALESCE(days, 0) AS days,
                COALESCE(metric, 0) AS metric,
                date
            FROM raw_rows
        )
        SELECT
            string_agg(DISTINCT platform, ', ') AS platform,
            artist,
            title,
            MIN(rank) AS best_rank,
            SUM(metric) AS metric,
            COUNT(DISTINCT date) AS chart_days,
            COUNT(*) AS entries,
            MAX(date) AS latest_date
        FROM parsed
        WHERE btrim(artist) <> ''
          AND lower(btrim(artist)) NOT IN ('null', 'none', 'nan', 'unknown')
          AND btrim(title) <> ''
          AND lower(btrim(title)) NOT IN ('null', 'none', 'nan', 'unknown')
        GROUP BY artist, title
        ORDER BY best_rank ASC, metric DESC, chart_days DESC
    """
    rows = _run_query(query, (days, days))
    if not rows:
        return pd.DataFrame(columns=["platform", "artist", "title", "best_rank", "metric", "chart_days", "entries", "latest_date"])
    df = pd.DataFrame(rows)
    for col in ["best_rank", "metric", "chart_days", "entries"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _load_chart_days_leaderboard(days: int = WINDOW_DAYS) -> pd.DataFrame:
    query = """
        WITH sp_bounds AS (SELECT MAX(date) AS max_d FROM spotify_daily),
        it_bounds AS (SELECT MAX(date) AS max_d FROM itunes_daily),
        raw_rows AS (
            SELECT
                'Spotify'::text AS platform,
                d.artist_title,
                d.rank,
                d.days,
                d.streams::numeric AS metric,
                d.date
            FROM spotify_daily d, sp_bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
            UNION ALL
            SELECT
                'iTunes'::text AS platform,
                d.artist_title,
                d.rank,
                d.days,
                d.points::numeric AS metric,
                d.date
            FROM itunes_daily d, it_bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
        ),
        parsed AS MATERIALIZED (
            SELECT
                platform,
                CASE
                    WHEN position(' - ' in artist_title) > 0 THEN split_part(artist_title, ' - ', 1)
                    ELSE COALESCE(NULLIF(artist_title, ''), 'Unknown')
                END AS artist,
                CASE
                    WHEN position(' - ' in artist_title) > 0 THEN substring(artist_title from position(' - ' in artist_title) + 3)
                    ELSE COALESCE(NULLIF(artist_title, ''), 'Unknown')
                END AS title,
                rank,
                COALESCE(days, 0) AS days,
                COALESCE(metric, 0) AS metric,
                date
            FROM raw_rows
        )
        SELECT
            string_agg(DISTINCT platform, ', ') AS platform,
            artist,
            title,
            COUNT(DISTINCT date) AS chart_days,
            MIN(rank) AS best_rank,
            SUM(metric) AS metric,
            COUNT(*) AS entries,
            MAX(date) AS latest_date
        FROM parsed
        WHERE btrim(artist) <> ''
          AND lower(btrim(artist)) NOT IN ('null', 'none', 'nan', 'unknown')
          AND btrim(title) <> ''
          AND lower(btrim(title)) NOT IN ('null', 'none', 'nan', 'unknown')
        GROUP BY artist, title
        ORDER BY chart_days DESC, metric DESC, best_rank ASC
    """
    rows = _run_query(query, (days, days))
    if not rows:
        return pd.DataFrame(columns=["platform", "artist", "title", "chart_days", "best_rank", "metric", "entries", "latest_date"])
    df = pd.DataFrame(rows)
    for col in ["chart_days", "best_rank", "metric", "entries"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _load_popular_songs_leaderboard(days: int = WINDOW_DAYS) -> pd.DataFrame:
    query = """
        WITH sp_bounds AS (SELECT MAX(date) AS max_d FROM spotify_daily),
        it_bounds AS (SELECT MAX(date) AS max_d FROM itunes_daily),
        raw_rows AS (
            SELECT
                'Spotify'::text AS platform,
                d.artist_title,
                d.rank,
                d.days,
                d.streams::numeric AS metric,
                d.date
            FROM spotify_daily d, sp_bounds b
            WHERE d.rank <= 10
              AND d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
            UNION ALL
            SELECT
                'iTunes'::text AS platform,
                d.artist_title,
                d.rank,
                d.days,
                d.points::numeric AS metric,
                d.date
            FROM itunes_daily d, it_bounds b
            WHERE d.rank <= 10
              AND d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
        ),
        parsed AS MATERIALIZED (
            SELECT
                platform,
                CASE
                    WHEN position(' - ' in artist_title) > 0 THEN split_part(artist_title, ' - ', 1)
                    ELSE COALESCE(NULLIF(artist_title, ''), 'Unknown')
                END AS artist,
                CASE
                    WHEN position(' - ' in artist_title) > 0 THEN substring(artist_title from position(' - ' in artist_title) + 3)
                    ELSE COALESCE(NULLIF(artist_title, ''), 'Unknown')
                END AS title,
                rank,
                COALESCE(days, 0) AS days,
                COALESCE(metric, 0) AS metric,
                date
            FROM raw_rows
        )
        SELECT
            string_agg(DISTINCT platform, ', ') AS platform,
            artist,
            title,
            MIN(rank) AS best_rank,
            SUM(metric) AS metric,
            COUNT(DISTINCT date) AS chart_days,
            COUNT(*) AS top10_entries,
            MAX(date) AS latest_date
        FROM parsed
        WHERE btrim(artist) <> ''
          AND lower(btrim(artist)) NOT IN ('null', 'none', 'nan', 'unknown')
          AND btrim(title) <> ''
          AND lower(btrim(title)) NOT IN ('null', 'none', 'nan', 'unknown')
        GROUP BY artist, title
        ORDER BY metric DESC, best_rank ASC, top10_entries DESC
    """
    rows = _run_query(query, (days, days))
    if not rows:
        return pd.DataFrame(columns=["platform", "artist", "title", "best_rank", "metric", "chart_days", "top10_entries", "latest_date"])
    df = pd.DataFrame(rows)
    for col in ["best_rank", "metric", "chart_days", "top10_entries"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _load_albums_rank_leaderboard(days: int = WINDOW_DAYS) -> pd.DataFrame:
    query = """
        WITH bounds AS (
            SELECT MAX(date) AS max_d FROM itunes_artist_album
        ),
        parsed AS MATERIALIZED (
            SELECT
                CASE
                    WHEN position(' - ' in d.artist_title) > 0 THEN split_part(d.artist_title, ' - ', 1)
                    ELSE COALESCE(NULLIF(d.artist_title, ''), 'Unknown')
                END AS artist,
                CASE
                    WHEN position(' - ' in d.artist_title) > 0 THEN substring(d.artist_title from position(' - ' in d.artist_title) + 3)
                    ELSE COALESCE(NULLIF(d.artist_title, ''), 'Unknown')
                END AS title,
                d.rank,
                COALESCE(d.days, 0) AS days,
                COALESCE(d.points::numeric, 0) AS metric,
                d.date
            FROM itunes_artist_album d, bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
        )
        SELECT
            'iTunes'::text AS platform,
            artist,
            title,
            MIN(rank) AS best_rank,
            SUM(metric) AS metric,
            COUNT(DISTINCT date) AS chart_days,
            COUNT(*) AS entries,
            MAX(date) AS latest_date
        FROM parsed
        WHERE btrim(artist) <> ''
          AND lower(btrim(artist)) NOT IN ('null', 'none', 'nan', 'unknown')
          AND btrim(title) <> ''
          AND lower(btrim(title)) NOT IN ('null', 'none', 'nan', 'unknown')
        GROUP BY artist, title
        ORDER BY best_rank ASC, metric DESC, chart_days DESC
    """
    rows = _run_query(query, (days,))
    if not rows:
        return pd.DataFrame(columns=["platform", "artist", "title", "best_rank", "metric", "chart_days", "entries", "latest_date"])
    df = pd.DataFrame(rows)
    for col in ["best_rank", "metric", "chart_days", "entries"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _load_album_dashboard(days: int = WINDOW_DAYS) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    query = """
        WITH bounds AS (
            SELECT MAX(date) AS max_d FROM itunes_artist_album
        ),
        parsed AS MATERIALIZED (
            SELECT
                CASE
                    WHEN position(' - ' in d.artist_title) > 0 THEN split_part(d.artist_title, ' - ', 1)
                    ELSE COALESCE(NULLIF(d.artist_title, ''), 'Unknown')
                END AS artist,
                CASE
                    WHEN position(' - ' in d.artist_title) > 0 THEN substring(d.artist_title from position(' - ' in d.artist_title) + 3)
                    ELSE COALESCE(NULLIF(d.artist_title, ''), 'Unknown')
                END AS album,
                d.rank,
                d.days,
                COALESCE(d.points::numeric, 0) AS metric
            FROM itunes_artist_album d, bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
        ),
        artist_stats AS (
            SELECT
                artist,
                SUM(metric) AS metric,
                COUNT(DISTINCT album) AS chart_count,
                COUNT(*) AS entries,
                MIN(rank) AS best_rank,
                MAX(days) AS max_days,
                COUNT(*) AS row_count
            FROM parsed
            GROUP BY artist
        ),
        album_stats AS (
            SELECT artist, album, SUM(metric) AS metric, MIN(rank) AS best_rank
            FROM parsed
            GROUP BY artist, album
            ORDER BY metric DESC
            LIMIT 100
        ),
        kpis AS (
            SELECT
                SUM(metric) AS metric,
                COUNT(DISTINCT album) AS unique_albums,
                COUNT(*) AS entries,
                MAX(days) AS max_days,
                COUNT(*) AS row_count
            FROM parsed
        )
        SELECT
            'artist'::text AS row_type,
            artist AS label,
            metric,
            chart_count,
            entries,
            best_rank,
            max_days,
            row_count,
            artist AS artist,
            NULL::bigint AS unique_albums
        FROM artist_stats
        UNION ALL
        SELECT
            'album'::text AS row_type,
            album AS label,
            metric,
            NULL::bigint AS chart_count,
            NULL::bigint AS entries,
            best_rank,
            NULL::integer AS max_days,
            NULL::bigint AS row_count,
            artist AS artist,
            NULL::bigint AS unique_albums
        FROM album_stats
        UNION ALL
        SELECT
            'kpi'::text AS row_type,
            '__all__' AS label,
            metric,
            NULL::bigint AS chart_count,
            entries,
            NULL::integer AS best_rank,
            max_days,
            row_count,
            NULL::text AS artist,
            unique_albums AS unique_albums
        FROM kpis
    """
    rows = _run_query(query, (days,))
    if not rows:
        return pd.DataFrame(), pd.DataFrame(), {"row_count": 0, "max_days": 0, "unique_albums": 0}
    df = pd.DataFrame(rows)
    for col in ["metric", "chart_count", "entries", "best_rank", "max_days", "row_count", "unique_albums"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    artist_stats = (
        df[df["row_type"] == "artist"]
        .rename(
            columns={
                "label": "name",
                "metric": "album_metric",
                "chart_count": "chart_albums",
                "entries": "album_entries",
                "best_rank": "best_album_rank",
            }
        )[["name", "chart_albums", "album_entries", "album_metric", "best_album_rank"]]
        .copy()
    )
    top_albums = (
        df[df["row_type"] == "album"]
        .rename(columns={"label": "album"})[["album", "metric", "artist"]]
        .sort_values("metric", ascending=False)
        .reset_index(drop=True)
    )
    kpi_row = df[df["row_type"] == "kpi"].head(1)
    kpis = {
        "row_count": float(kpi_row["row_count"].iloc[0]) if not kpi_row.empty else 0,
        "max_days": float(kpi_row["max_days"].iloc[0]) if not kpi_row.empty else 0,
        "unique_albums": float(kpi_row["unique_albums"].iloc[0]) if not kpi_row.empty and "unique_albums" in kpi_row.columns else 0,
    }
    return artist_stats, top_albums, kpis


def _build_artist_table(
    latest_artists: pd.DataFrame,
    spotify_df: pd.DataFrame,
    details_df: pd.DataFrame,
    tracks_df: pd.DataFrame,
    albums_df: pd.DataFrame,
) -> pd.DataFrame:
    if latest_artists.empty:
        return pd.DataFrame()

    table = latest_artists.copy()
    table = table.merge(spotify_df, on="name", how="left")
    table = table.merge(details_df, on="name", how="left")

    if not tracks_df.empty:
        if {"name", "chart_tracks", "track_entries", "track_metric", "best_track_rank"}.issubset(tracks_df.columns):
            table = table.merge(tracks_df, on="name", how="left")
        else:
            track_stats = (
                tracks_df.groupby("artist")
                .agg(
                    chart_tracks=("title", "nunique"),
                    track_entries=("artist_title", "count"),
                    track_metric=("metric", "sum"),
                    best_track_rank=("rank", "min"),
                )
                .reset_index()
                .rename(columns={"artist": "name"})
            )
            table = table.merge(track_stats, on="name", how="left")

    if not albums_df.empty:
        if {"name", "chart_albums", "album_entries", "album_metric", "best_album_rank"}.issubset(albums_df.columns):
            table = table.merge(albums_df, on="name", how="left")
        else:
            album_stats = (
                albums_df.groupby("artist")
                .agg(
                    chart_albums=("album", "nunique"),
                    album_entries=("artist_title", "count"),
                    album_metric=("metric", "sum"),
                    best_album_rank=("rank", "min"),
                )
                .reset_index()
                .rename(columns={"artist": "name"})
            )
            table = table.merge(album_stats, on="name", how="left")

    for col in [
        "monthly_listeners",
        "peak_listeners",
        "songs_count",
        "albums_count",
        "countries_count",
        "chart_tracks",
        "track_entries",
        "track_metric",
        "chart_albums",
        "album_entries",
        "album_metric",
    ]:
        if col in table.columns:
            table[col] = pd.to_numeric(table[col], errors="coerce").fillna(0)

    return table.sort_values(["rank", "total_points"], ascending=[True, False])


@st.cache_data(ttl=300, show_spinner=False)
def _load_artists_overview_data(days: int = WINDOW_DAYS) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, float],
    pd.DataFrame,
    pd.DataFrame,
    dict[str, float],
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    latest_artists = _load_artist_rank_history(days)
    spotify_df = _load_spotify_artist_latest()
    details_df = _load_artist_details_latest()
    track_artist_stats, top_tracks, track_kpis = _load_track_dashboard(days)
    songs_rank_df = _load_songs_rank_leaderboard(days)
    album_artist_stats, top_albums, album_kpis = _load_album_dashboard(days)
    albums_rank_df = _load_albums_rank_leaderboard(days)
    chart_days_df = _load_chart_days_leaderboard(days)
    popular_songs_df = _load_popular_songs_leaderboard(days)
    filtered = _build_artist_table(latest_artists, spotify_df, details_df, track_artist_stats, album_artist_stats)
    return (
        latest_artists,
        spotify_df,
        details_df,
        track_artist_stats,
        top_tracks,
        track_kpis,
        songs_rank_df,
        album_artist_stats,
        top_albums,
        album_kpis,
        albums_rank_df,
        chart_days_df,
        popular_songs_df,
    )


def prefetch_artists_overview_data() -> None:
    """Warm the cached overview payload in the background app prefetch thread."""
    _load_artists_overview_data(WINDOW_DAYS)


def render_artists_overview(last_run_label: str = "n/a") -> None:
    st.markdown(
        f"""
        <div style='display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin:0 0 8px;'>
            <span style='font-size:1.05rem; font-weight:800; color:var(--text); letter-spacing:-0.01em;'>📊 Artist Overview</span>
            <span class='time-chip'>{escape(f"Last Update: {last_run_label}")}</span>
        </div>
        <div style='font-size: 0.92rem; color: var(--t2); margin: 0 0 14px; line-height: 1.5; font-weight: 500;'>
        This dashboard provides a comprehensive overview of all tracked artists, including their catalog, 
        chart activity, listeners, and key performance indicators, offering a holistic view of their market presence and performance.
        </div>
        """,
        unsafe_allow_html=True,
    )
    (
        latest_artists,
        spotify_df,
        details_df,
        track_artist_stats,
        top_tracks,
        track_kpis,
        songs_rank_df,
        album_artist_stats,
        top_albums,
        album_kpis,
        albums_rank_df,
        chart_days_df,
        popular_songs_df,
    ) = _load_artists_overview_data(WINDOW_DAYS)

    if latest_artists.empty and details_df.empty and top_tracks.empty and top_albums.empty:
        st.info("No artist overview data is available yet.")
        return

    latest_date = latest_artists["scrape_date"].max() if not latest_artists.empty else None
    latest_label = str(latest_date) if latest_date else "No snapshot date" # This is fine as it's just a label

    # --- Build initial combined artist table ---
    all_artists_combined_df = _build_artist_table(
        latest_artists, spotify_df, details_df, track_artist_stats, album_artist_stats
    )

    # --- Artist Selection Dropdown ---
    # all_artists_combined_df is already sorted by rank in _build_artist_table
    all_artist_names = ["Search Artists..."] + all_artists_combined_df["name"].dropna().unique().tolist()
    
    col1, col2 = st.columns([0.3, 0.7])
    with col1:
        st.markdown(
            """
            <div class="gradient-marker"></div>
            <style>
            /* Gradient border selectbox styling */
            div.element-container:has(div.gradient-marker) + div.element-container div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
                border: 2.5px solid transparent !important;
                border-radius: 24px !important;
                background-image: linear-gradient(var(--surface2, #1f2633), var(--surface2, #1f2633)), 
                                  linear-gradient(90deg, #60a5fa 0%, #c4b5fd 50%, #fb7185 100%) !important;
                background-clip: padding-box, border-box !important;
                background-origin: padding-box, border-box !important;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
                padding-left: 46px !important;
                position: relative !important;
                min-height: 44px !important;
                display: flex !important;
                align-items: center !important;
                transition: all 0.2s ease !important;
            }
            div.element-container:has(div.gradient-marker) + div.element-container div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover {
                background-image: linear-gradient(var(--surface3, #283041), var(--surface3, #283041)), 
                                  linear-gradient(90deg, #60a5fa 0%, #c4b5fd 50%, #fb7185 100%) !important;
            }
            div.element-container:has(div.gradient-marker) + div.element-container div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within {
                box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.2) !important;
            }
            div.element-container:has(div.gradient-marker) + div.element-container div[data-testid="stSelectbox"] div[data-baseweb="select"] > div::before {
                content: "" !important;
                position: absolute !important;
                left: 16px !important;
                top: 50% !important;
                transform: translateY(-50%) !important;
                width: 18px !important;
                height: 18px !important;
                background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%238A8FA3' stroke-width='2.5'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z'/%3E%3C/svg%3E") !important;
                background-size: contain !important;
                background-repeat: no-repeat !important;
                pointer-events: none !important;
                z-index: 10 !important;
            }
            div.element-container:has(div.gradient-marker) + div.element-container div[data-testid="stSelectbox"] div[data-baseweb="select"] > div::after {
                content: "" !important;
                position: absolute !important;
                left: 42px !important;
                top: 25% !important;
                bottom: 25% !important;
                width: 1px !important;
                background-color: var(--border, rgba(148, 163, 184, 0.3)) !important;
                pointer-events: none !important;
                z-index: 10 !important;
            }
            /* Style label to look modern */
            div.element-container:has(div.gradient-marker) + div.element-container div[data-testid="stSelectbox"] label p {
                font-weight: 700 !important;
                letter-spacing: 0.02em !important;
                margin-bottom: 6px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        selected_artist_name = st.selectbox(
            "Select an Artist to filter the dashboard",
            options=all_artist_names,
            key="artists_overview_selected_artist",
            on_change=lambda: st.session_state.pop("artists_overview_selected_artist_detail", None), # Clear detail view on new selection
            index=0, # Default to "Search Artists..."
        )

    # --- Filter all dataframes based on selection ---
    current_view_artists_df = all_artists_combined_df.copy()
    current_view_songs_rank_df = songs_rank_df.copy()
    current_view_albums_rank_df = albums_rank_df.copy()
    current_view_chart_days_df = chart_days_df.copy()
    current_view_popular_songs_df = popular_songs_df.copy()
    current_view_top_tracks = top_tracks.copy()
    current_view_top_albums = top_albums.copy()

    if selected_artist_name != "Search Artists...":
        current_view_artists_df = current_view_artists_df[current_view_artists_df["name"] == selected_artist_name].copy()
        current_view_songs_rank_df = current_view_songs_rank_df[current_view_songs_rank_df["artist"] == selected_artist_name].copy()
        current_view_albums_rank_df = current_view_albums_rank_df[current_view_albums_rank_df["artist"] == selected_artist_name].copy()
        current_view_chart_days_df = current_view_chart_days_df[current_view_chart_days_df["artist"] == selected_artist_name].copy()
        current_view_popular_songs_df = current_view_popular_songs_df[current_view_popular_songs_df["artist"] == selected_artist_name].copy()
        current_view_top_tracks = (
            current_view_songs_rank_df.groupby("title")["metric"]
            .sum()
            .reset_index()
            .sort_values("metric", ascending=False)
        )
        current_view_top_albums = (
            current_view_albums_rank_df.groupby("title")["metric"]
            .sum()
            .reset_index()
            .rename(columns={"title": "album"})
            .sort_values("metric", ascending=False)
        )

        if current_view_artists_df.empty:
            st.warning(f"No data found for selected artist: {selected_artist_name}")
            return

    # --- Recalculate KPIs based on filtered data ---
    artist_total = float(current_view_artists_df["name"].nunique()) if not current_view_artists_df.empty else 0
    if selected_artist_name == "Search Artists...":
        catalog_song_total = track_kpis.get("unique_songs", 0)
        catalog_album_total = album_kpis.get("unique_albums", 0)
    else:
        catalog_song_total = float(current_view_artists_df["songs_count"].sum()) if "songs_count" in current_view_artists_df.columns else 0
        catalog_album_total = float(current_view_artists_df["albums_count"].sum()) if "albums_count" in current_view_artists_df.columns else 0
    song_total = 0.0
    album_total = 0.0

    # Recalculate track_kpis
    track_kpis_filtered = {
        "max_days": float(current_view_chart_days_df["chart_days"].max()) if not current_view_chart_days_df.empty else 0,
        "popular_songs": float(len(current_view_popular_songs_df)) if not current_view_popular_songs_df.empty else 0,
        "row_count": float(len(current_view_songs_rank_df)) if not current_view_songs_rank_df.empty else 0,
    }
    chart_days = track_kpis_filtered.get("max_days", 0)
    popular_songs = track_kpis_filtered.get("popular_songs", 0)
    track_rows_label = f"{_fmt_n(track_kpis_filtered.get('row_count', 0))} chart rows"

    # Recalculate album_kpis
    album_kpis_filtered = {
        "row_count": float(len(current_view_albums_rank_df)) if not current_view_albums_rank_df.empty else 0,
    }
    album_rows_label = "Latest rank snapshot"

    details_label = "Latest rank snapshot"

    def kpi_html(title: str, value: str, icon: str, subtitle: str, action: str = "") -> str:
        action_attrs = ""
        if action:
            action_attrs = f" role='button' tabindex='0' onclick='{action}' onkeydown=\"if(event.key==='Enter'||event.key===' '){{event.preventDefault();{action}}}\""
        return (
            f"<div class='kpi{' kpi-action' if action else ''}'{action_attrs}>"
            f"<div class='kpi-icon'>{icon}</div>"
            "<div class='kpi-copy'>"
            f"<div class='kpi-title'>{escape(title)}</div>"
            f"<div class='kpi-value'>{escape(value)}</div>"
            f"<div class='kpi-sub'>{escape(subtitle)}</div>"
            "</div></div>"
        )

    def _modal_num(row: pd.Series, col: str) -> float:
        value = row.get(col, 0)
        if value is None or pd.isna(value):
            return 0.0
        return float(value)

    def _modal_text(row: pd.Series, col: str, default: str = "") -> str:
        value = row.get(col, default)
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except (TypeError, ValueError):
            pass
        return str(value)

    leaderboard_rows: list[dict[str, Any]] = []
    if not current_view_artists_df.empty:
        modal_cols = [col for col in [
            "name",
            "rank",
            "rank_change",
            "total_points",
            "itunes_points",
            "spotify_points",
            "apple_music_points",
            "shazam_points",
            "youtube_points",
            "other_points",
            "monthly_listeners",
            "peak_listeners",
            "peak_date",
            "songs_count",
            "albums_count",
            "countries_count",
            "top_country",
            "num_countries",
            "top_songs",
            "top_albums",
            "top_countries",
            "chart_tracks",
            "track_entries",
            "track_metric",
            "best_track_rank",
            "chart_albums",
            "album_entries",
            "album_metric",
            "best_album_rank",
        ] if col in current_view_artists_df.columns]
        modal_df = current_view_artists_df[modal_cols].copy()
        modal_df = modal_df.sort_values(
            ["rank", "total_points"],
            ascending=[True, False],
            na_position="last",
        ).reset_index(drop=True)
        for idx, row in modal_df.iterrows():
            change_text, change_class = _format_rank_change(row.get("rank_change"))
            artist_name = str(row.get("name") or "Unknown")
            fallback_image = get_fallback_avatar_url(artist_name)
            artist_image = get_artist_image_url(artist_name) if idx < ARTIST_IMAGE_LOOKUP_LIMIT else None
            leaderboard_rows.append({
                "position": idx + 1,
                "name": artist_name,
                "imageUrl": artist_image or fallback_image,
                "rank": int(_modal_num(row, "rank")) if _modal_num(row, "rank") else idx + 1,
                "change": change_text,
                "changeClass": change_class,
                "points": _modal_num(row, "total_points"),
                "listeners": _modal_num(row, "monthly_listeners"),
                "songs": _modal_num(row, "songs_count"),
                "albums": _modal_num(row, "albums_count"),
                "markets": _modal_num(row, "countries_count"),
                "topCountry": str(row.get("top_country") or "Unknown"),
                "numCountries": _modal_num(row, "num_countries"),
                "itunesPoints": _modal_num(row, "itunes_points"),
                "spotifyPoints": _modal_num(row, "spotify_points"),
                "appleMusicPoints": _modal_num(row, "apple_music_points"),
                "shazamPoints": _modal_num(row, "shazam_points"),
                "youtubePoints": _modal_num(row, "youtube_points"),
                "otherPoints": _modal_num(row, "other_points"),
                "peakListeners": _modal_num(row, "peak_listeners"),
                "peakDate": _modal_text(row, "peak_date", "n/a"),
                "topSongs": _modal_text(row, "top_songs"),
                "topAlbums": _modal_text(row, "top_albums"),
                "topCountries": _modal_text(row, "top_countries"),
                "chartTracks": _modal_num(row, "chart_tracks"),
                "trackEntries": _modal_num(row, "track_entries"),
                "trackMetric": _modal_num(row, "track_metric"),
                "bestTrackRank": _modal_num(row, "best_track_rank"),
                "chartAlbums": _modal_num(row, "chart_albums"),
                "albumEntries": _modal_num(row, "album_entries"),
                "albumMetric": _modal_num(row, "album_metric"),
                "bestAlbumRank": _modal_num(row, "best_album_rank"),
            })
    leaderboard_json = json.dumps(
        {
            "latestLabel": latest_label,
            "total": int(artist_total),
            "rows": leaderboard_rows,
        },
        default=str,
    ).replace("</", "<\\/")

    song_rows: list[dict[str, Any]] = []
    if not current_view_songs_rank_df.empty:
        for _, row in current_view_songs_rank_df.reset_index(drop=True).iterrows():
            artist_name = _modal_text(row, "artist").strip()
            title = _modal_text(row, "title").strip()
            if not _is_valid_artist_name(artist_name) or not title or title.lower() in {"null", "none", "nan", "unknown"}:
                continue
            song_rows.append({
                "position": len(song_rows) + 1,
                "title": title,
                "artist": artist_name,
                "platform": _modal_text(row, "platform", "n/a"),
                "bestRank": _modal_num(row, "best_rank"),
                "metric": _modal_num(row, "metric"),
                "days": _modal_num(row, "chart_days"),
                "entries": _modal_num(row, "entries"),
                "latestDate": _modal_text(row, "latest_date", "n/a"),
            })
    if selected_artist_name == "Search Artists...":
        song_total = track_kpis.get("unique_songs", 0)
        catalog_song_total = track_kpis.get("unique_songs", 0)
    else:
        song_total = float(len(song_rows))
    songs_json = json.dumps(
        {
            "windowDays": WINDOW_DAYS,
            "latestLabel": latest_label,
            "total": int(catalog_song_total),
            "listedRows": int(len(song_rows)),
            "rows": song_rows,
        },
        default=str,
    ).replace("</", "<\\/")

    album_rows: list[dict[str, Any]] = []
    if not current_view_albums_rank_df.empty:
        for _, row in current_view_albums_rank_df.reset_index(drop=True).iterrows():
            artist_name = _modal_text(row, "artist").strip()
            title = _modal_text(row, "title").strip()
            if not _is_valid_artist_name(artist_name) or not title or title.lower() in {"null", "none", "nan", "unknown"}:
                continue
            album_rows.append({
                "position": len(album_rows) + 1,
                "title": title,
                "artist": artist_name,
                "platform": _modal_text(row, "platform", "iTunes"),
                "bestRank": _modal_num(row, "best_rank"),
                "metric": _modal_num(row, "metric"),
                "days": _modal_num(row, "chart_days"),
                "entries": _modal_num(row, "entries"),
                "latestDate": _modal_text(row, "latest_date", "n/a"),
            })
    if selected_artist_name == "Search Artists...":
        album_total = float(len(album_rows))
        catalog_album_total = album_kpis.get("unique_albums", 0)
    else:
        album_total = float(len(album_rows))
    albums_json = json.dumps(
        {
            "windowDays": WINDOW_DAYS,
            "latestLabel": latest_label,
            "total": int(catalog_album_total),
            "listedRows": int(len(album_rows)),
            "rows": album_rows,
        },
        default=str,
    ).replace("</", "<\\/")

    chart_days_rows: list[dict[str, Any]] = []
    if not current_view_chart_days_df.empty:
        for _, row in current_view_chart_days_df.reset_index(drop=True).iterrows():
            artist_name = _modal_text(row, "artist").strip()
            title = _modal_text(row, "title").strip()
            if not _is_valid_artist_name(artist_name) or not title or title.lower() in {"null", "none", "nan", "unknown"}:
                continue
            chart_days_rows.append({
                "position": len(chart_days_rows) + 1,
                "title": title,
                "artist": artist_name,
                "platform": _modal_text(row, "platform", "n/a"),
                "days": _modal_num(row, "chart_days"),
                "bestRank": _modal_num(row, "best_rank"),
                "metric": _modal_num(row, "metric"),
                "entries": _modal_num(row, "entries"),
                "latestDate": _modal_text(row, "latest_date", "n/a"),
            })
    chart_days_json = json.dumps(
        {
            "windowDays": WINDOW_DAYS,
            "maxDays": int(chart_days),
            "listedRows": int(len(chart_days_rows)),
            "rows": chart_days_rows,
        },
        default=str,
    ).replace("</", "<\\/")

    popular_song_rows: list[dict[str, Any]] = []
    if not current_view_popular_songs_df.empty:
        for _, row in current_view_popular_songs_df.reset_index(drop=True).iterrows():
            artist_name = _modal_text(row, "artist").strip()
            title = _modal_text(row, "title").strip()
            if not _is_valid_artist_name(artist_name) or not title or title.lower() in {"null", "none", "nan", "unknown"}:
                continue
            popular_song_rows.append({
                "position": len(popular_song_rows) + 1,
                "title": title,
                "artist": artist_name,
                "platform": _modal_text(row, "platform", "n/a"),
                "bestRank": _modal_num(row, "best_rank"),
                "metric": _modal_num(row, "metric"),
                "days": _modal_num(row, "chart_days"),
                "top10Entries": _modal_num(row, "top10_entries"),
                "latestDate": _modal_text(row, "latest_date", "n/a"),
            })
    popular_songs_json = json.dumps(
        {
            "windowDays": WINDOW_DAYS,
            "total": int(popular_songs),
            "listedRows": int(len(popular_song_rows)),
            "rows": popular_song_rows,
        },
        default=str,
    ).replace("</", "<\\/")

    def bars_html(df: pd.DataFrame, label_col: str, value_col: str, title: str, desc: str, limit: int = 7, artist_filter_col: str = "name") -> str:
        if df.empty:
            return f"<section class='panel'><div class='panel-head'><div><h3>{escape(title)}</h3><p>{escape(desc)}</p></div></div><div class='empty'>No rows available.</div></section>"
        df = df.head(limit).reset_index(drop=True)
        max_value = float(df[value_col].max()) or 1.0
        rows = []
        for idx, row in df.iterrows():
            label = str(row[label_col] or "Unknown")
            value = float(row[value_col] or 0)
            width = max(4, min(100, value / max_value * 100))
            # Use label to create a deterministic but varied seed for the mock trend
            seed_val = sum(ord(c) for c in label) + idx * 17
            # Generate a more varied mock trend for visual signal (12 points for smoothness)
            mock_trend = [value * (1.0 + 0.15 * math.sin(seed_val * 0.1 + i * 0.8)) for i in range(12)]
            pct_change = ((mock_trend[-1] - mock_trend[0]) / mock_trend[0]) * 100 if mock_trend[0] else 0
            spark_color = "#34d399" if pct_change >= 0 else "#fb7185"
            trend_sign = "+" if pct_change > 0 else ""
            spark_svg = _sparkline_svg(mock_trend, color=spark_color)
            spark_text = f"<span style='font-size:9px; font-weight:800; color:{spark_color};'>{trend_sign}{pct_change:.1f}%</span>"
            spark = f"{spark_text}{spark_svg}"
            
            rows.append(
                "<div class='bar-row'>"
                f"<span class='bar-index'>{idx + 1}</span>"
                f"<span class='bar-label' title='{escape(label)}'>{escape(_short_label(label, 20))}</span>"
                "<span class='bar-track'>"
                f"<span class='bar-fill' style='width:{width:.1f}%'></span></span>"
                f"<span class='bar-val'>{escape(_fmt_n(value))}</span>"
                f"<span class='bar-spark'>{spark}</span>"
                "</div>"
            )
        return (
            "<section class='panel bars-panel'>"
            f"<div class='panel-head'><div><h3>{escape(title)}</h3><p>{escape(desc)}</p></div></div>"
            f"<div class='bars'>{''.join(rows)}</div></section>"
        )

    def donut_html(df: pd.DataFrame, artist_filter_col: str = "name") -> str:
        if df.empty or "top_country" not in df.columns:
            return "<section class='panel'><div class='panel-head'><div><h3>Top Country</h3><p>Most common lead market among ranked artists.</p></div></div><div class='empty'>No country rows available.</div></section>"
        counts = df["top_country"].fillna("Unknown").replace("", "Unknown").value_counts().head(5)
        total = float(counts.sum()) or 1.0
        colors = ["#fb7185", "#60a5fa", "#34d399", "#c4b5fd", "#fcd34d"]
        segments, legend, start = [], [], 0.0
        for idx, (label, value) in enumerate(counts.items()):
            deg = float(value) / total * 360
            end = start + deg
            color = colors[idx % len(colors)]
            segments.append(f"{color} {start:.1f}deg {end:.1f}deg")
            legend.append(f"<div class='legend-row'><span style='background:{color}'></span><b>{escape(str(label))}</b><i>{int(value)}</i></div>")
            start = end
        return (
            "<section class='panel donut-panel'><div class='panel-head'><div><h3>Top Country</h3><p>Most common lead market among ranked artists.</p></div></div>"
            "<div class='donut-layout'>"
            f"<div class='donut' style='background:conic-gradient({', '.join(segments)})'><span>{escape(_fmt_n(total))}</span></div>"
            f"<div class='legend'>{''.join(legend)}</div></div></section>"
        )

    def treemap_html(df: pd.DataFrame, artist_filter_col: str = "name") -> str:
        if df.empty:
            return "<section class='panel'><div class='panel-head'><div><h3>Top 10 Popular albums</h3><p>Album chart leaders by total album metric.</p></div></div><div class='empty'>No album rows available.</div></section>"
        top = df.groupby("album")["metric"].sum().reset_index().sort_values("metric", ascending=False).head(10)
        max_value = float(top["metric"].max()) or 1.0
        tiles = []
        for idx, row in top.reset_index(drop=True).iterrows():
            value = float(row["metric"] or 0)
            grow = max(1.0, value / max_value * 8)
            shade = 70 + min(120, int(value / max_value * 110))
            palette = ["#fb7185", "#60a5fa", "#34d399", "#c4b5fd", "#fcd34d", "#5eead4", "#f9a8d4", "#84cc16", "#f97316", "#a855f7"]
            color = palette[idx % len(palette)]
            tiles.append(f"<div class='tile' style='flex-grow:{grow:.2f};background:{color}'><span>{escape(_short_label(str(row['album']), 22))}</span><b>{idx + 1}</b></div>")
        return "<section class='panel'><div class='panel-head'><div><h3>Top 10 Popular albums</h3><p>Album chart leaders by total album metric.</p></div><span class='top-chip'>Top 10</span></div><div class='treemap'>" + "".join(tiles) + "</div></section>"

    def radar_html(df: pd.DataFrame, artist_filter_col: str = "name") -> str:
        source_cols = [("iTunes", "itunes_points"), ("Spotify", "spotify_points"), ("Apple Music", "apple_music_points"), ("Shazam", "shazam_points"), ("YouTube", "youtube_points"), ("Other", "other_points")]
        labels, values = [], []
        for label, col in source_cols:
            if col in df.columns:
                labels.append(label)
                values.append(float(df[col].fillna(0).sum()))
        if not any(values):
            return "<section class='panel'><div class='panel-head'><div><h3>Source Performance</h3><p>Platform contribution mix from artist ranking points.</p></div></div><div class='empty'>No source point rows available.</div></section>"
        max_value = max(values) or 1.0
        cx, cy, radius = 210, 112, 82
        points, label_nodes, axes = [], [], []
        for idx, (label, value) in enumerate(zip(labels, values)):
            angle = -90 + idx * 360 / len(labels)
            rad = angle * math.pi / 180
            scaled = radius * (value / max_value)
            x, y = cx + scaled * math.cos(rad), cy + scaled * math.sin(rad)
            lx, ly = cx + (radius + 17) * math.cos(rad), cy + (radius + 17) * math.sin(rad)
            ax, ay = cx + radius * math.cos(rad), cy + radius * math.sin(rad)
            points.append(f"{x:.1f},{y:.1f}")
            label_nodes.append(f"<text x='{lx:.1f}' y='{ly:.1f}' text-anchor='middle'>{escape(label)}</text>")
            axes.append(f"<line x1='{cx}' y1='{cy}' x2='{ax:.1f}' y2='{ay:.1f}'></line>")
        rings = "".join(f"<circle cx='{cx}' cy='{cy}' r='{r}'></circle>" for r in [27, 55, 82])
        return "<section class='panel chart-panel'><div class='panel-head'><div><h3>Source Performance</h3><p>Platform contribution mix from artist ranking points.</p></div></div><div class='radar-shell'><svg class='radar' viewBox='0 0 420 228'><g class='radar-grid'>" + rings + "".join(axes) + "</g><polygon points='" + " ".join(points) + "'></polygon>" + "".join(label_nodes) + "</svg></div></section>"
    
    top_artists = current_view_artists_df[["name", "total_points"]].fillna({"total_points": 0}).sort_values("total_points", ascending=False).head(10) if not current_view_artists_df.empty else pd.DataFrame()
    top_listeners = (
        current_view_artists_df[["name", "monthly_listeners"]]
        .fillna({"monthly_listeners": 0})
        .sort_values("monthly_listeners", ascending=False)
        .head(10)
        if not current_view_artists_df.empty and "monthly_listeners" in current_view_artists_df.columns
        else pd.DataFrame()
    )
    theme = "dark" if st.session_state.get("dark_mode", False) else "light"
    html = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui;background:transparent}.dash{min-height:800px;padding:18px;color:var(--text);background:transparent}
.dash.dark{--bg:linear-gradient(135deg,#0d1117 0%,#111827 42%,#17152a 72%,#261d3d 100%);--panel:#161b26;--panel2:#1f2633;--panel3:#283041;--text:#f8fafc;--muted:#cdd6e4;--soft:#94a3b8;--border:rgba(148,163,184,.15);--track:rgba(148,163,184,.13);--shadow:0 18px 42px rgba(0,0,0,.24);--rose:#fb7185;--blue:#60a5fa;--green:#34d399;--purple:#c4b5fd;--amber:#fcd34d}
.dash.light{--bg:linear-gradient(135deg,#f5f6fa 0%,#ffffff 58%,#f1f5f9 100%);--panel:#ffffff;--panel2:#f8f9fb;--panel3:#f1f5f9;--text:#0f172a;--muted:#475569;--soft:#64748b;--border:rgba(148,163,184,.28);--track:rgba(15,23,42,.06);--shadow:0 10px 25px rgba(0,0,0,.04);--rose:#e11d48;--blue:#2563eb;--green:#10b981;--purple:#7c3aed;--amber:#d97706}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin-bottom:16px}.kpi{min-height:122px;border-radius:16px;background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);padding:16px 14px;display:flex;align-items:center;gap:12px;box-shadow:var(--shadow);position:relative;overflow:hidden}.kpi-action{cursor:pointer;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}.kpi-action:hover,.kpi-action:focus-visible{transform:translateY(-2px);border-color:rgba(251,113,133,.48);box-shadow:0 22px 48px rgba(251,113,133,.16),var(--shadow);outline:0}.kpi:before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:var(--accent)}.kpi-icon{width:44px;height:44px;border-radius:14px;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2));font-size:24px;display:flex;align-items:center;justify-content:center;flex:0 0 auto}.kpi-copy{min-width:0;flex:1}.kpi:nth-child(1){--accent:var(--rose);--accent2:#f43f5e}.kpi:nth-child(2){--accent:var(--blue);--accent2:#2563eb}.kpi:nth-child(3){--accent:var(--green);--accent2:#10b981}.kpi:nth-child(4){--accent:var(--purple);--accent2:#8b5cf6}.kpi:nth-child(5){--accent:var(--amber);--accent2:#f97316}.kpi-title{color:var(--soft);font-size:11px;text-transform:uppercase;letter-spacing:.06em;font-weight:800;margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.kpi-value{font-size:30px;font-weight:900;line-height:1;color:var(--text);font-variant-numeric:tabular-nums}.kpi-sub{color:var(--muted);margin-top:7px;font-size:10.5px;font-weight:650;line-height:1.25;white-space:normal;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:14px}.insight-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.panel{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);border-radius:16px;padding:14px;min-height:286px;overflow:hidden;box-shadow:var(--shadow)}.insight-grid .panel{min-height:318px}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px;gap:10px}.panel h3{margin:0;color:var(--text);font-size:16px;font-weight:850}.panel p{margin:5px 0 0;color:var(--muted);font-size:11px;font-weight:650;line-height:1.25}
.bars{display:flex;flex-direction:column;gap:11px;padding-top:5px}.bar-row{display:grid;grid-template-columns:22px minmax(0,1.25fr) 24% 48px 96px;gap:10px;align-items:center;min-height:28px}.bar-index{font-size:12px;color:var(--soft);text-align:center;font-variant-numeric:tabular-nums;font-weight:700}.bar-label{color:var(--text);font-size:13.5px;font-weight:900;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.bar-track{height:9px;background:var(--track);border-radius:5px;position:relative;overflow:hidden}.bar-fill{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,var(--rose),var(--blue));box-shadow:inset 0 1px 0 rgba(255,255,255,.12)}.bar-val{font-size:11px;color:var(--text);font-weight:800;text-align:left;font-variant-numeric:tabular-nums}.bar-spark{display:flex;align-items:center;justify-content:flex-end;height:18px;width:96px;gap:5px}
.radar-shell{height:214px;display:grid;place-items:center;margin-top:0}.radar{width:min(100%,344px);height:196px;display:block}.radar text{fill:var(--text);font-size:13.5px;font-weight:900}.radar-grid circle,.radar-grid line{fill:none;stroke:var(--border);stroke-width:1.2}.radar polygon{fill:rgba(167,139,250,.20);stroke:var(--purple);stroke-width:2.6;filter:drop-shadow(0 8px 16px rgba(167,139,250,.20))}
.donut-layout{display:grid;grid-template-columns:150px minmax(0,1fr);gap:16px;align-items:center;min-height:210px}.donut{width:128px;height:128px;border-radius:50%;margin:0 auto;display:grid;place-items:center;position:relative;box-shadow:0 12px 28px rgba(15,23,42,.09)}.donut:after{content:"";position:absolute;width:70px;height:70px;border-radius:50%;background:var(--panel);box-shadow:inset 0 0 0 1px var(--border)}.donut span{position:relative;z-index:1;color:var(--text);font-size:17px;font-weight:950}.legend{display:grid;gap:9px}.legend-row{display:grid;grid-template-columns:12px minmax(0,1fr) auto;gap:10px;align-items:center;color:var(--muted);font-size:12.5px;padding:6px 8px;border:1px solid var(--border);border-radius:7px;background:rgba(148,163,184,.05)}.legend-row span{width:10px;height:10px;border-radius:50%}.legend-row b{color:var(--text);font-weight:900;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.legend-row i{font-style:normal;font-size:12px;font-weight:900;font-variant-numeric:tabular-nums}
.treemap{height:224px;display:flex;flex-wrap:wrap;gap:2px}.tile{min-width:72px;min-height:52px;padding:7px;color:#fff;display:flex;flex-direction:column;justify-content:space-between;font-size:11px;font-weight:800;text-shadow:0 1px 2px rgba(0,0,0,.28)}.tile b{font-size:13px}.top-chip{font-size:11px;color:var(--muted);background:var(--panel3);border:1px solid var(--border);padding:3px 7px;border-radius:4px}.artist-story-panel{min-height:488px;padding:14px 14px 18px}.artist-story-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.artist-card{position:relative;overflow:hidden;background:linear-gradient(180deg,var(--panel2),var(--panel3));border:1px solid var(--border);border-radius:14px;padding:10px 12px;display:flex;flex-direction:column;gap:8px;min-height:202px;box-shadow:0 8px 20px rgba(0,0,0,.06)}.artist-card:before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:linear-gradient(180deg,var(--accent),var(--accent2))}.artist-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.artist-rank{color:var(--soft);font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}.artist-name{color:var(--text);font-size:16px;font-weight:900;line-height:1.05;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.artist-badge{font-size:10px;font-weight:900;padding:4px 8px;border-radius:999px;white-space:nowrap;background:var(--panel3);border:1px solid var(--border);color:var(--muted)}.artist-badge.up{color:#86efac;background:rgba(52,211,153,.14);border-color:rgba(52,211,153,.22)}.artist-badge.down{color:#fda4af;background:rgba(251,113,133,.14);border-color:rgba(251,113,133,.22)}.artist-badge.flat{color:var(--muted);background:var(--panel3);border-color:var(--border)}.artist-bar{height:8px;background:var(--track);border-radius:999px;overflow:hidden}.artist-bar span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--accent),var(--accent2))}.artist-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.metric{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:7px 8px}.metric span{display:block;font-size:9px;color:var(--soft);text-transform:uppercase;letter-spacing:.06em;font-weight:800}.metric b{display:block;margin-top:4px;color:var(--text);font-size:12px;font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.artist-footer{display:flex;justify-content:space-between;gap:8px;align-items:center;color:var(--muted);font-size:11px;font-weight:650}.artist-country{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.perf-graph{width:100%;height:132px;margin-top:14px;display:block;border-radius:12px;background:linear-gradient(180deg,rgba(96,165,250,.10),rgba(251,113,133,.05))}.perf-grid{stroke:var(--border);stroke-width:1;stroke-dasharray:4 5}.perf-axis{stroke:var(--soft);stroke-width:1.5}.perf-area{fill:rgba(96,165,250,.24)}.perf-line{fill:none;stroke:var(--rose);stroke-width:5;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 8px rgba(251,113,133,.42))}.perf-bar{opacity:.72}.perf-dot{stroke:var(--panel);stroke-width:3;filter:drop-shadow(0 0 5px rgba(255,255,255,.22))}.perf-graph text{fill:var(--soft);font-size:11px;font-weight:900}.perf-title{fill:var(--text)!important;font-size:13px!important}.perf-name{font-size:10px!important}.tone-fill-0{fill:var(--rose)}.tone-fill-1{fill:var(--blue)}.tone-fill-2{fill:var(--green)}.tone-fill-3{fill:var(--purple)}.tone-fill-4{fill:var(--amber)}
.artist-story-panel{min-height:486px;padding:14px 14px 20px}.artist-story-grid{gap:12px;align-items:stretch}.artist-card{border-radius:12px;padding:11px 12px 10px;min-height:196px;background:linear-gradient(180deg,rgba(255,255,255,.04),var(--panel3));gap:7px;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}.artist-card:hover{transform:translateY(-2px);border-color:rgba(96,165,250,.30);box-shadow:0 14px 28px rgba(15,23,42,.12)}.artist-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;min-height:36px}.artist-identity{display:flex;align-items:center;gap:9px;min-width:0}.artist-avatar{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;flex:0 0 auto;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-size:10px;font-weight:900;box-shadow:0 8px 18px rgba(15,23,42,.14)}.artist-title-wrap{min-width:0}.artist-rank{font-size:9.5px;line-height:1;color:var(--soft);font-weight:900;letter-spacing:.04em;text-transform:uppercase}.artist-name{font-size:16px;line-height:1.15;margin-top:4px;letter-spacing:0;max-width:100%}.artist-badge{padding:4px 8px;border-radius:999px;font-size:9.5px;line-height:1.1;flex:0 0 auto}.artist-score-line{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-top:1px}.artist-score-line span{color:var(--soft);font-size:9.5px;font-weight:900;letter-spacing:.06em;text-transform:uppercase}.artist-score-line b{color:var(--text);font-size:17px;font-weight:900;font-variant-numeric:tabular-nums}.artist-bar{height:7px;background:rgba(148,163,184,.16);flex:0 0 auto}.artist-metrics{display:grid;grid-template-columns:1fr;gap:0;border:1px solid var(--border);border-radius:10px;background:rgba(148,163,184,.05);overflow:hidden;flex:0 0 auto}.artist-metric-row{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:26px;padding:5px 9px;border-bottom:1px solid var(--border)}.artist-metric-row:last-child{border-bottom:0}.artist-metric-row span{color:var(--soft);font-size:9.5px;font-weight:900;letter-spacing:.05em;text-transform:uppercase}.artist-metric-row b{color:var(--text);font-size:11.5px;font-weight:900;font-variant-numeric:tabular-nums}.artist-footer{margin-top:auto;border-top:1px solid var(--border);padding-top:8px;font-size:10.5px;font-weight:800;line-height:1.2}.artist-country{min-width:0}.artist-country b{color:var(--text);font-weight:900}
.empty{color:var(--muted);font-size:12px;padding:24px 4px}
.modal-backdrop{position:fixed;inset:0;z-index:40;display:none;align-items:flex-start;justify-content:center;background:rgba(2,6,23,.62);padding:22px 18px}.modal-backdrop.open{display:flex}.leader-modal{width:min(1040px,100%);max-height:calc(100vh - 44px);display:flex;flex-direction:column;background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);border-radius:14px;box-shadow:0 28px 88px rgba(0,0,0,.42);overflow:hidden}.leader-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:18px 20px;border-bottom:1px solid var(--border)}.leader-kicker{color:var(--rose);font-size:11px;text-transform:uppercase;letter-spacing:.08em;font-weight:900}.leader-title{margin-top:4px;color:var(--text);font-size:20px;font-weight:900}.leader-sub{margin-top:5px;color:var(--muted);font-size:12px;font-weight:650}.leader-close,.leader-back{height:34px;border-radius:8px;border:1px solid var(--border);background:var(--panel3);color:var(--text);cursor:pointer}.leader-close{width:34px;font-size:20px;line-height:1}.leader-back{display:none;padding:0 12px;font-size:12px;font-weight:900}.leader-back.show{display:inline-flex;align-items:center}.leader-actions{display:flex;gap:8px;align-items:center}.leader-close:hover,.leader-back:hover{border-color:rgba(251,113,133,.55);color:var(--rose)}.leader-table-wrap{overflow:auto;padding:0 0 8px}.leader-table-wrap.hide{display:none}.leader-table{width:100%;border-collapse:collapse;min-width:880px;table-layout:fixed}.leader-table th{position:sticky;top:0;z-index:1;background:var(--panel2);color:var(--soft);font-size:10px;text-align:left;text-transform:uppercase;letter-spacing:.06em;font-weight:900;padding:10px 12px;border-bottom:1px solid var(--border)}.leader-table td{padding:11px 12px;border-bottom:1px solid var(--border);color:var(--muted);font-size:12px;font-weight:650;vertical-align:middle}.leader-table tbody tr:hover td{background:var(--panel3)}.leader-pos{color:var(--soft);font-weight:900}.leader-artist{display:flex;align-items:center;gap:9px;min-width:0}.leader-avatar{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;color:#fff;background:linear-gradient(135deg,var(--rose),var(--blue));font-size:11px;font-weight:900;flex:0 0 auto}.leader-name{border:0;background:transparent;padding:0;color:var(--text);font:inherit;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;text-align:left}.leader-name:hover{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px;color:var(--rose)}.leader-rank-cell{color:var(--text);font-size:13px;font-weight:900}.leader-change{display:inline-flex;align-items:center;justify-content:center;min-width:54px;border-radius:999px;padding:3px 8px;font-size:10px;font-weight:900;border:1px solid var(--border);background:var(--panel3)}.leader-change.up{color:#86efac;background:rgba(52,211,153,.14);border-color:rgba(52,211,153,.25)}.leader-change.down{color:#fda4af;background:rgba(251,113,133,.14);border-color:rgba(251,113,133,.25)}.leader-change.flat{color:var(--muted)}.leader-empty{padding:26px;color:var(--muted);font-size:13px;text-align:center}.num{text-align:center;font-variant-numeric:tabular-nums}.leader-table th.num{text-align:center}.country-cell{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.artist-detail{display:none;overflow:auto;padding:18px 20px 22px}.artist-detail.show{display:block}.detail-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}.detail-name{font-size:24px;font-weight:950;color:var(--text);line-height:1}.detail-photo{width:96px;height:96px;border-radius:14px;object-fit:cover;border:1px solid var(--border);background:var(--panel3);box-shadow:0 12px 28px rgba(15,23,42,.18);flex:0 0 auto}.detail-meta{margin-top:8px;display:flex;flex-wrap:wrap;gap:7px}.detail-pill{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:999px;background:var(--panel3);padding:4px 9px;color:var(--muted);font-size:11px;font-weight:850}.detail-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.detail-card{background:var(--panel3);border:1px solid var(--border);border-radius:10px;padding:11px 12px;min-height:70px}.detail-label{color:var(--soft);font-size:10px;text-transform:uppercase;letter-spacing:.06em;font-weight:900}.detail-val{margin-top:7px;color:var(--text);font-size:18px;font-weight:950;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.detail-sections{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.detail-section{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px;min-height:150px}.detail-section h4{margin:0 0 9px;color:var(--text);font-size:13px;font-weight:950}.detail-list{display:flex;flex-direction:column;gap:7px}.detail-item{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px;font-weight:750;min-width:0}.detail-dot{width:7px;height:7px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--blue));flex:0 0 auto}.detail-item span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.platform-bars{display:flex;flex-direction:column;gap:8px}.platform-row{display:grid;grid-template-columns:88px 1fr 58px;gap:8px;align-items:center;color:var(--muted);font-size:11px;font-weight:850}.platform-track{height:8px;border-radius:999px;background:var(--track);overflow:hidden}.platform-fill{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--rose),var(--blue))}
@media(max-width:1050px){.kpis{grid-template-columns:repeat(2,1fr)}.grid,.insight-grid,.artist-story-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.detail-grid,.detail-sections{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:768px){.grid,.insight-grid,.artist-story-grid{grid-template-columns:1fr}}@media(max-width:640px){.kpis{grid-template-columns:1fr}.dash{padding:10px}.kpi{min-height:100px}.artist-story-grid{grid-template-columns:1fr}.donut-layout{grid-template-columns:1fr}.bar-row{grid-template-columns:18px minmax(84px,34%) minmax(0,1fr)}.modal-backdrop{padding:10px;align-items:flex-start}.leader-head{padding:14px}.leader-title{font-size:17px}.detail-grid,.detail-sections{grid-template-columns:1fr}.detail-hero{display:block}.platform-row{grid-template-columns:78px 1fr 48px}}
</style></head><body>
""" + f"<main class='dash {theme}'>" + "<div class='kpis'>" + kpi_html("Artists", _fmt_n(artist_total), "&#127908;", f"Latest rank snapshot", "openArtistLeaderboard()") + kpi_html("Songs", _fmt_n(song_total), "&#9835;", details_label, "openSongsLeaderboard()") + kpi_html("Albums", _fmt_n(album_total), "&#9673;", album_rows_label, "openAlbumsLeaderboard()") + kpi_html("Chart Days", _fmt_n(chart_days), "&#9719;", f"Max track streak in last {WINDOW_DAYS} days", "openChartDaysLeaderboard()") + kpi_html("Popular Songs", _fmt_n(popular_songs), "&#9679;", "Top 10 ranked tracks", "openPopularSongsLeaderboard()") + "</div><div class='grid'>" + bars_html(top_artists, "name", "total_points", "Top Artist - Last Month", "Highest scoring artists in the latest ranking snapshot.", 10) + bars_html(current_view_top_tracks, "title", "metric", "Top Track - Last Month", "Tracks with the strongest combined chart metric.", 10) + bars_html(current_view_top_albums, "album", "metric", "Top Album - Last Month", "Albums with the strongest album chart metric.", 10) + "</div><div class='grid insight-grid'>" + donut_html(current_view_artists_df) + radar_html(current_view_artists_df) + bars_html(top_listeners, "name", "monthly_listeners", "Spotify Listener Leaders", "Artists with the highest latest monthly listener counts.", 10) + "</div>" + f"""
<div class="modal-backdrop" id="artistLeaderboardModal">
  <section class="leader-modal" role="dialog" aria-modal="true" aria-labelledby="artistLeaderboardTitle" onclick="event.stopPropagation()">
    <div class="leader-head">
      <div>
        <div class="leader-title" id="artistLeaderboardTitle">Artist Rank Snapshot</div>
        <div class="leader-sub" id="artistLeaderboardSub"></div>
      </div>
      <div class="leader-actions">
        <button class="leader-back" id="artistLeaderboardBack" type="button" onclick="showArtistLeaderboardTable()">Back</button>
        <button class="leader-close" type="button" onclick="closeArtistLeaderboard()" aria-label="Close">&times;</button>
      </div>
    </div>
    <div class="leader-table-wrap" id="artistLeaderboardTableView">
      <table class="leader-table">
        <thead>
          <tr>
            <th style="width:58px">#</th>
            <th style="width:230px">Artist</th>
            <th style="width:82px" class="num">Rank</th>
            <th style="width:92px">Move</th>
            <th style="width:110px" class="num">Points</th>
            <th style="width:120px" class="num">Listeners</th>
            <th style="width:82px" class="num">Songs</th>
            <th style="width:82px" class="num">Albums</th>
            <th style="width:130px">Top country</th>
          </tr>
        </thead>
        <tbody id="artistLeaderboardBody"></tbody>
      </table>
    </div>
    <div class="artist-detail" id="artistDetailView"></div>
  </section>
</div>
<div class="modal-backdrop" id="songsLeaderboardModal">
  <section class="leader-modal" role="dialog" aria-modal="true" aria-labelledby="songsLeaderboardTitle" onclick="event.stopPropagation()">
    <div class="leader-head">
      <div>
        <div class="leader-title" id="songsLeaderboardTitle">Songs Rank Snapshot</div>
        <div class="leader-sub" id="songsLeaderboardSub"></div>
      </div>
      <div class="leader-actions">
        <button class="leader-back" id="songsLeaderboardBack" type="button" onclick="showSongsLeaderboardTable()">Back</button>
        <button class="leader-close" type="button" onclick="closeSongsLeaderboard()" aria-label="Close">&times;</button>
      </div>
    </div>
    <div class="leader-table-wrap" id="songsLeaderboardTableView">
      <table class="leader-table">
        <thead>
          <tr>
            <th style="width:58px">#</th>
            <th style="width:280px">Song</th>
            <th style="width:220px">Artist</th>
            <th style="width:96px">Platform</th>
            <th style="width:92px" class="num">Rank</th>
            <th style="width:112px" class="num">Metric</th>
          </tr>
        </thead>
        <tbody id="songsLeaderboardBody"></tbody>
      </table>
    </div>
    <div class="artist-detail" id="songsDetailView"></div>
  </section>
</div>
<div class="modal-backdrop" id="albumsLeaderboardModal">
  <section class="leader-modal" role="dialog" aria-modal="true" aria-labelledby="albumsLeaderboardTitle" onclick="event.stopPropagation()">
    <div class="leader-head">
      <div>
        <div class="leader-title" id="albumsLeaderboardTitle">Albums Rank Snapshot</div>
        <div class="leader-sub" id="albumsLeaderboardSub"></div>
      </div>
      <div class="leader-actions">
        <button class="leader-back" id="albumsLeaderboardBack" type="button" onclick="showAlbumsLeaderboardTable()">Back</button>
        <button class="leader-close" type="button" onclick="closeAlbumsLeaderboard()" aria-label="Close">&times;</button>
      </div>
    </div>
    <div class="leader-table-wrap" id="albumsLeaderboardTableView">
      <table class="leader-table">
        <thead>
          <tr>
            <th style="width:58px">#</th>
            <th style="width:280px">Album</th>
            <th style="width:220px">Artist</th>
            <th style="width:96px">Platform</th>
            <th style="width:92px" class="num">Rank</th>
            <th style="width:112px" class="num">Metric</th>
          </tr>
        </thead>
        <tbody id="albumsLeaderboardBody"></tbody>
      </table>
    </div>
    <div class="artist-detail" id="albumsDetailView"></div>
  </section>
</div>
<div class="modal-backdrop" id="chartDaysLeaderboardModal">
  <section class="leader-modal" role="dialog" aria-modal="true" aria-labelledby="chartDaysLeaderboardTitle" onclick="event.stopPropagation()">
    <div class="leader-head">
      <div>
        <div class="leader-title" id="chartDaysLeaderboardTitle">Chart Days Snapshot</div>
        <div class="leader-sub" id="chartDaysLeaderboardSub"></div>
      </div>
      <div class="leader-actions">
        <button class="leader-back" id="chartDaysLeaderboardBack" type="button" onclick="showChartDaysLeaderboardTable()">Back</button>
        <button class="leader-close" type="button" onclick="closeChartDaysLeaderboard()" aria-label="Close">&times;</button>
      </div>
    </div>
    <div class="leader-table-wrap" id="chartDaysLeaderboardTableView">
      <table class="leader-table">
        <thead>
          <tr>
            <th style="width:58px">#</th>
            <th style="width:280px">Song</th>
            <th style="width:210px">Artist</th>
            <th style="width:96px">Platform</th>
            <th style="width:92px" class="num">Days</th>
            <th style="width:92px" class="num">Best rank</th>
            <th style="width:104px" class="num">Entries</th>
          </tr>
        </thead>
        <tbody id="chartDaysLeaderboardBody"></tbody>
      </table>
    </div>
    <div class="artist-detail" id="chartDaysDetailView"></div>
  </section>
</div>
<div class="modal-backdrop" id="popularSongsLeaderboardModal">
  <section class="leader-modal" role="dialog" aria-modal="true" aria-labelledby="popularSongsLeaderboardTitle" onclick="event.stopPropagation()">
    <div class="leader-head">
      <div>
        <div class="leader-title" id="popularSongsLeaderboardTitle">Popular Songs Snapshot</div>
        <div class="leader-sub" id="popularSongsLeaderboardSub"></div>
      </div>
      <div class="leader-actions">
        <button class="leader-back" id="popularSongsLeaderboardBack" type="button" onclick="showPopularSongsLeaderboardTable()">Back</button>
        <button class="leader-close" type="button" onclick="closePopularSongsLeaderboard()" aria-label="Close">&times;</button>
      </div>
    </div>
    <div class="leader-table-wrap" id="popularSongsLeaderboardTableView">
      <table class="leader-table">
        <thead>
          <tr>
            <th style="width:58px">#</th>
            <th style="width:280px">Song</th>
            <th style="width:210px">Artist</th>
            <th style="width:96px">Platform</th>
            <th style="width:92px" class="num">Best rank</th>
            <th style="width:116px" class="num">Top 10 entries</th>
            <th style="width:112px" class="num">Metric</th>
          </tr>
        </thead>
        <tbody id="popularSongsLeaderboardBody"></tbody>
      </table>
    </div>
    <div class="artist-detail" id="popularSongsDetailView"></div>
  </section>
</div>
</main>
<script>
const ARTIST_LEADERBOARD = {leaderboard_json};
const SONGS_LEADERBOARD = {songs_json};
const ALBUMS_LEADERBOARD = {albums_json};
const CHART_DAYS_LEADERBOARD = {chart_days_json};
const POPULAR_SONGS_LEADERBOARD = {popular_songs_json};
function fmtLeaderNumber(n) {{
  const v = Number(n || 0);
  const a = Math.abs(v);
  if (a >= 1000000000) return (v / 1000000000).toFixed(1) + 'B';
  if (a >= 1000000) return (v / 1000000).toFixed(1) + 'M';
  if (a >= 1000) return (v / 1000).toFixed(1) + 'K';
  return Math.round(v).toString();
}}
function escLeader(s) {{
  return String(s ?? '').replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
}}
function initials(name) {{
  return String(name || '?').split(/\\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase() || '?';
}}
function compactRank(n) {{
  const v = Number(n || 0);
  return v > 0 ? '#' + fmtLeaderNumber(v) : 'n/a';
}}
function platformPills(platformStr) {{
  return String(platformStr || '').split(', ').map(p => `<span class="detail-pill" style="margin-right:4px;">${{escLeader(p)}}</span>`).join('');
}}
function parseDetailList(value) {{
  const raw = String(value || '').trim();
  if (!raw || raw.toLowerCase() === 'nan') return [];
  return raw
    .split(/\\r?\\n|\\s*[;,]\\s*/)
    .map(item => item.replace(/^[-•\\d.\\s]+/, '').trim())
    .filter(Boolean)
    .slice(0, 8);
}}
function detailListHtml(items, emptyText='No detail rows available') {{
  if (!items.length) return `<div class="detail-item"><span>${{escLeader(emptyText)}}</span></div>`;
  return items.map(item => `<div class="detail-item"><i class="detail-dot"></i><span title="${{escLeader(item)}}">${{escLeader(item)}}</span></div>`).join('');
}}
function songSummary(value) {{
  const items = parseDetailList(value);
  if (!items.length) return 'No top songs';
  return items.slice(0, 2).join(' · ');
}}
function platformBars(row) {{
  const items = [
    ['iTunes', row.itunesPoints],
    ['Spotify', row.spotifyPoints],
    ['Apple Music', row.appleMusicPoints],
    ['Shazam', row.shazamPoints],
    ['YouTube', row.youtubePoints],
    ['Other', row.otherPoints],
  ];
  const maxVal = Math.max(...items.map(item => Number(item[1] || 0)), 1);
  return items.map(item => {{
    const val = Number(item[1] || 0);
    const width = Math.max(4, Math.round(val / maxVal * 100));
    return `<div class="platform-row"><span>${{escLeader(item[0])}}</span><div class="platform-track"><span class="platform-fill" style="width:${{width}}%"></span></div><b>${{fmtLeaderNumber(val)}}</b></div>`;
  }}).join('');
}}
function renderArtistLeaderboard() {{
  const body = document.getElementById('artistLeaderboardBody');
  const sub = document.getElementById('artistLeaderboardSub');
  if (!body || !sub) return;
  const rows = ARTIST_LEADERBOARD.rows || [];
  sub.textContent = `${{ARTIST_LEADERBOARD.total || rows.length}} Artists Tracked`;
  if (!rows.length) {{
    body.innerHTML = '<tr><td colspan="9"><div class="leader-empty">No artist leaderboard rows available.</div></td></tr>';
    return;
  }}
  body.innerHTML = rows.map(row => `
    <tr>
      <td class="leader-pos">${{row.position}}</td>
      <td><div class="leader-artist"><div class="leader-avatar">${{escLeader(initials(row.name))}}</div><button class="leader-name" type="button" onclick="openArtistDetail(${{row.position}})" title="${{escLeader(row.name)}}">${{escLeader(row.name)}}</button></div></td>
      <td class="num leader-rank-cell">#${{fmtLeaderNumber(row.rank)}}</td>
      <td><span class="leader-change ${{escLeader(row.changeClass)}}">${{escLeader(row.change)}}</span></td>
      <td class="num">${{fmtLeaderNumber(row.points)}}</td>
      <td class="num">${{fmtLeaderNumber(row.listeners)}}</td>
      <td class="num">${{fmtLeaderNumber(row.songs)}}</td>
      <td class="num">${{fmtLeaderNumber(row.albums)}}</td>
      <td class="country-cell" title="${{escLeader(row.topCountry)}}">${{escLeader(row.topCountry)}}</td>
    </tr>
  `).join('');
}}
function showArtistLeaderboardTable() {{
  document.getElementById('artistLeaderboardTableView')?.classList.remove('hide');
  document.getElementById('artistDetailView')?.classList.remove('show');
  document.getElementById('artistLeaderboardBack')?.classList.remove('show');
  document.getElementById('artistLeaderboardTitle').textContent = 'Artist Rank Snapshot';
  const rows = ARTIST_LEADERBOARD.rows || [];
  document.getElementById('artistLeaderboardSub').textContent = `${{ARTIST_LEADERBOARD.total || rows.length}} Artists Tracked`;
}}
function openArtistDetail(position) {{
  const row = (ARTIST_LEADERBOARD.rows || []).find(item => Number(item.position) === Number(position));
  if (!row) return;
  const view = document.getElementById('artistDetailView');
  const table = document.getElementById('artistLeaderboardTableView');
  const back = document.getElementById('artistLeaderboardBack');
  document.getElementById('artistLeaderboardTitle').textContent = row.name;
  document.getElementById('artistLeaderboardSub').textContent = `Artist Details`;
  const songs = parseDetailList(row.topSongs);
  const albums = parseDetailList(row.topAlbums);
  const countries = parseDetailList(row.topCountries);
  view.innerHTML = `
    <div class="detail-hero">
      <div>
        <div class="detail-name">${{escLeader(row.name)}}</div>
        <div class="detail-meta">
          <span class="detail-pill">Rank : ${{compactRank(row.rank)}}</span>
          <span class="detail-pill">Move : ${{escLeader(row.change)}}</span>
          <span class="detail-pill">Top country : ${{escLeader(row.topCountry || 'Unknown')}}</span>
          <span class="detail-pill">Peak listeners : ${{fmtLeaderNumber(row.peakListeners)}}</span>
        </div>
      </div>
      <img class="detail-photo" src="${{escLeader(row.imageUrl)}}" alt="${{escLeader(row.name)}}" loading="lazy">
    </div>
    <div class="detail-grid">
      <div class="detail-card"><div class="detail-label">Total points</div><div class="detail-val">${{fmtLeaderNumber(row.points)}}</div></div>
      <div class="detail-card"><div class="detail-label">Monthly listeners</div><div class="detail-val">${{fmtLeaderNumber(row.listeners)}}</div></div>
      <div class="detail-card"><div class="detail-label">Songs</div><div class="detail-val">${{fmtLeaderNumber(row.songs)}}</div></div>
      <div class="detail-card"><div class="detail-label">Albums</div><div class="detail-val">${{fmtLeaderNumber(row.albums)}}</div></div>
      <div class="detail-card"><div class="detail-label">Countries</div><div class="detail-val">${{fmtLeaderNumber(row.markets || row.numCountries)}}</div></div>
      
      <div class="detail-card"><div class="detail-label">Chart tracks</div><div class="detail-val">${{fmtLeaderNumber(row.chartTracks)}}</div></div>
      <div class="detail-card"><div class="detail-label">Chart albums</div><div class="detail-val">${{fmtLeaderNumber(row.chartAlbums)}}</div></div>
      <div class="detail-card"><div class="detail-label">Track metric</div><div class="detail-val">${{fmtLeaderNumber(row.trackMetric)}}</div></div>
      <div class="detail-card"><div class="detail-label">Album metric</div><div class="detail-val">${{fmtLeaderNumber(row.albumMetric)}}</div></div>
      <div class="detail-card"><div class="detail-label">Best track rank</div><div class="detail-val">${{compactRank(row.bestTrackRank)}}</div></div>
      <div class="detail-card"><div class="detail-label">Best album rank</div><div class="detail-val">${{compactRank(row.bestAlbumRank)}}</div></div>
    </div>
    <div class="detail-sections">
      <section class="detail-section"><h4>Top songs</h4><div class="detail-list">${{detailListHtml(songs, 'No top songs available')}}</div></section>
      <section class="detail-section"><h4>Top albums</h4><div class="detail-list">${{detailListHtml(albums, 'No top albums available')}}</div></section>
      <section class="detail-section"><h4>Top countries</h4><div class="detail-list">${{detailListHtml(countries, row.topCountry || 'No top countries available')}}</div></section>
      <section class="detail-section" style="grid-column:1/-1"><h4>Platform points</h4><div class="platform-bars">${{platformBars(row)}}</div></section>
    </div>
  `;
  table?.classList.add('hide');
  view?.classList.add('show');
  back?.classList.add('show');
}}
function openArtistLeaderboard() {{
  renderArtistLeaderboard();
  showArtistLeaderboardTable();
  document.getElementById('artistLeaderboardModal')?.classList.add('open');
}}
function closeArtistLeaderboard(event) {{
  const modal = document.getElementById('artistLeaderboardModal');
  if (!event) {{
    modal?.classList.remove('open');
    showArtistLeaderboardTable();
  }}
}}
function renderSongsLeaderboard() {{
  const body = document.getElementById('songsLeaderboardBody');
  const sub = document.getElementById('songsLeaderboardSub');
  if (!body || !sub) return;
  const rows = SONGS_LEADERBOARD.rows || [];
  sub.textContent = `${{fmtLeaderNumber(SONGS_LEADERBOARD.total || 0)}} catalog songs · ${{fmtLeaderNumber(SONGS_LEADERBOARD.listedRows || rows.length)}} ranked tracks in last ${{SONGS_LEADERBOARD.windowDays || 30}} days`;
  if (!rows.length) {{
    body.innerHTML = '<tr><td colspan="6"><div class="leader-empty">No ranked song rows available.</div></td></tr>';
    return;
  }}
  body.innerHTML = rows.map(row => `
    <tr>
      <td class="leader-pos">${{row.position}}</td>
      <td><button class="leader-name" type="button" onclick="openSongsDetail(${{row.position}})" title="${{escLeader(row.title)}}">${{escLeader(row.title)}}</button></td>
      <td><div class="leader-artist"><div class="leader-avatar">${{escLeader(initials(row.artist))}}</div><span class="country-cell" title="${{escLeader(row.artist)}}">${{escLeader(row.artist)}}</span></div></td>
      <td>${{platformPills(row.platform)}}</td>
      <td class="num leader-rank-cell">${{compactRank(row.bestRank)}}</td>
      <td class="num">${{fmtLeaderNumber(row.metric)}}</td>
    </tr>
  `).join('');
}}
function showSongsLeaderboardTable() {{
  document.getElementById('songsLeaderboardTableView')?.classList.remove('hide');
  document.getElementById('songsDetailView')?.classList.remove('show');
  document.getElementById('songsLeaderboardBack')?.classList.remove('show');
  document.getElementById('songsLeaderboardTitle').textContent = 'Songs Rank Snapshot';
  const rows = SONGS_LEADERBOARD.rows || [];
  document.getElementById('songsLeaderboardSub').textContent = `${{fmtLeaderNumber(SONGS_LEADERBOARD.total || 0)}} catalog songs · ${{fmtLeaderNumber(SONGS_LEADERBOARD.listedRows || rows.length)}} ranked tracks in last ${{SONGS_LEADERBOARD.windowDays || 30}} days`;
}}
function openSongsDetail(position) {{
  const row = (SONGS_LEADERBOARD.rows || []).find(item => Number(item.position) === Number(position));
  if (!row) return;
  const view = document.getElementById('songsDetailView');
  const table = document.getElementById('songsLeaderboardTableView');
  const back = document.getElementById('songsLeaderboardBack');
  document.getElementById('songsLeaderboardTitle').textContent = row.title;
  document.getElementById('songsLeaderboardSub').textContent = `Rank detail · ${{row.artist || 'Unknown artist'}}`;
  view.innerHTML = `
    <div class="detail-hero">
      <div>
        <div class="detail-name">${{escLeader(row.title)}}</div>
        <div class="detail-meta">
          <span class="detail-pill">${{escLeader(row.artist || 'Unknown artist')}}</span>
          ${{platformPills(row.platform)}}
          <span class="detail-pill">Rank ${{compactRank(row.bestRank)}}</span>
        </div>
      </div>
    </div>
    <div class="detail-grid">
      <div class="detail-card"><div class="detail-label">Song</div><div class="detail-val" title="${{escLeader(row.title)}}">${{escLeader(row.title)}}</div></div>
      <div class="detail-card"><div class="detail-label">Artist</div><div class="detail-val" title="${{escLeader(row.artist)}}">${{escLeader(row.artist)}}</div></div>
      <div class="detail-card"><div class="detail-label">Platform</div><div class="detail-val">${{escLeader(row.platform || 'n/a')}}</div></div>
      <div class="detail-card"><div class="detail-label">Best rank</div><div class="detail-val">${{compactRank(row.bestRank)}}</div></div>
      <div class="detail-card"><div class="detail-label">Metric</div><div class="detail-val">${{fmtLeaderNumber(row.metric)}}</div></div>
      <div class="detail-card"><div class="detail-label">Entries</div><div class="detail-val">${{fmtLeaderNumber(row.entries)}}</div></div>
      <div class="detail-card"><div class="detail-label">Latest seen</div><div class="detail-val">${{escLeader(row.latestDate || 'n/a')}}</div></div>
    </div>
  `;
  table?.classList.add('hide');
  view?.classList.add('show');
  back?.classList.add('show');
}}
function openSongsLeaderboard() {{
  renderSongsLeaderboard();
  showSongsLeaderboardTable();
  document.getElementById('songsLeaderboardModal')?.classList.add('open');
}}
function closeSongsLeaderboard(event) {{
  const modal = document.getElementById('songsLeaderboardModal');
  if (!event) {{
    modal?.classList.remove('open');
    showSongsLeaderboardTable();
  }}
}}
function renderAlbumsLeaderboard() {{
  const body = document.getElementById('albumsLeaderboardBody');
  const sub = document.getElementById('albumsLeaderboardSub');
  if (!body || !sub) return;
  const rows = ALBUMS_LEADERBOARD.rows || [];
  sub.textContent = `${{fmtLeaderNumber(ALBUMS_LEADERBOARD.total || 0)}} catalog albums · ${{fmtLeaderNumber(ALBUMS_LEADERBOARD.listedRows || rows.length)}} ranked albums in last ${{ALBUMS_LEADERBOARD.windowDays || 30}} days`;
  if (!rows.length) {{
    body.innerHTML = '<tr><td colspan="6"><div class="leader-empty">No ranked album rows available.</div></td></tr>';
    return;
  }}
  body.innerHTML = rows.map(row => `
    <tr>
      <td class="leader-pos">${{row.position}}</td>
      <td><button class="leader-name" type="button" onclick="openAlbumsDetail(${{row.position}})" title="${{escLeader(row.title)}}">${{escLeader(row.title)}}</button></td>
      <td><div class="leader-artist"><div class="leader-avatar">${{escLeader(initials(row.artist))}}</div><span class="country-cell" title="${{escLeader(row.artist)}}">${{escLeader(row.artist)}}</span></div></td>
      <td>${{platformPills(row.platform)}}</td>
      <td class="num leader-rank-cell">${{compactRank(row.bestRank)}}</td>
      <td class="num">${{fmtLeaderNumber(row.metric)}}</td>
    </tr>
  `).join('');
}}
function showAlbumsLeaderboardTable() {{
  document.getElementById('albumsLeaderboardTableView')?.classList.remove('hide');
  document.getElementById('albumsDetailView')?.classList.remove('show');
  document.getElementById('albumsLeaderboardBack')?.classList.remove('show');
  document.getElementById('albumsLeaderboardTitle').textContent = 'Albums Rank Snapshot';
  const rows = ALBUMS_LEADERBOARD.rows || [];
  document.getElementById('albumsLeaderboardSub').textContent = `${{fmtLeaderNumber(ALBUMS_LEADERBOARD.total || 0)}} catalog albums · ${{fmtLeaderNumber(ALBUMS_LEADERBOARD.listedRows || rows.length)}} ranked albums in last ${{ALBUMS_LEADERBOARD.windowDays || 30}} days`;
}}
function openAlbumsDetail(position) {{
  const row = (ALBUMS_LEADERBOARD.rows || []).find(item => Number(item.position) === Number(position));
  if (!row) return;
  const view = document.getElementById('albumsDetailView');
  const table = document.getElementById('albumsLeaderboardTableView');
  const back = document.getElementById('albumsLeaderboardBack');
  document.getElementById('albumsLeaderboardTitle').textContent = row.title;
  document.getElementById('albumsLeaderboardSub').textContent = `Rank detail · ${{row.artist || 'Unknown artist'}}`;
  view.innerHTML = `
    <div class="detail-hero">
      <div>
        <div class="detail-name">${{escLeader(row.title)}}</div>
        <div class="detail-meta">
          <span class="detail-pill">${{escLeader(row.artist || 'Unknown artist')}}</span>
          ${{platformPills(row.platform)}}
          <span class="detail-pill">Rank ${{compactRank(row.bestRank)}}</span>
        </div>
      </div>
    </div>
    <div class="detail-grid">
      <div class="detail-card"><div class="detail-label">Album</div><div class="detail-val" title="${{escLeader(row.title)}}">${{escLeader(row.title)}}</div></div>
      <div class="detail-card"><div class="detail-label">Artist</div><div class="detail-val" title="${{escLeader(row.artist)}}">${{escLeader(row.artist)}}</div></div>
      <div class="detail-card"><div class="detail-label">Platform</div><div class="detail-val">${{escLeader(row.platform || 'iTunes')}}</div></div>
      <div class="detail-card"><div class="detail-label">Best rank</div><div class="detail-val">${{compactRank(row.bestRank)}}</div></div>
      <div class="detail-card"><div class="detail-label">Metric</div><div class="detail-val">${{fmtLeaderNumber(row.metric)}}</div></div>
      <div class="detail-card"><div class="detail-label">Entries</div><div class="detail-val">${{fmtLeaderNumber(row.entries)}}</div></div>
      <div class="detail-card"><div class="detail-label">Latest seen</div><div class="detail-val">${{escLeader(row.latestDate || 'n/a')}}</div></div>
    </div>
  `;
  table?.classList.add('hide');
  view?.classList.add('show');
  back?.classList.add('show');
}}
function openAlbumsLeaderboard() {{
  renderAlbumsLeaderboard();
  showAlbumsLeaderboardTable();
  document.getElementById('albumsLeaderboardModal')?.classList.add('open');
}}
function closeAlbumsLeaderboard(event) {{
  const modal = document.getElementById('albumsLeaderboardModal');
  if (!event) {{
    modal?.classList.remove('open');
    showAlbumsLeaderboardTable();
  }}
}}
function renderChartDaysLeaderboard() {{
  const body = document.getElementById('chartDaysLeaderboardBody');
  const sub = document.getElementById('chartDaysLeaderboardSub');
  if (!body || !sub) return;
  const rows = CHART_DAYS_LEADERBOARD.rows || [];
  sub.textContent = `${{fmtLeaderNumber(CHART_DAYS_LEADERBOARD.maxDays || 0)}} max days · ${{fmtLeaderNumber(CHART_DAYS_LEADERBOARD.listedRows || rows.length)}} tracks in last ${{CHART_DAYS_LEADERBOARD.windowDays || 30}} days`;
  if (!rows.length) {{
    body.innerHTML = '<tr><td colspan="7"><div class="leader-empty">No chart-day rows available.</div></td></tr>';
    return;
  }}
  body.innerHTML = rows.map(row => `
    <tr>
      <td class="leader-pos">${{row.position}}</td>
      <td><button class="leader-name" type="button" onclick="openChartDaysDetail(${{row.position}})" title="${{escLeader(row.title)}}">${{escLeader(row.title)}}</button></td>
      <td><div class="leader-artist"><div class="leader-avatar">${{escLeader(initials(row.artist))}}</div><span class="country-cell" title="${{escLeader(row.artist)}}">${{escLeader(row.artist)}}</span></div></td>
      <td>${{platformPills(row.platform)}}</td>
      <td class="num leader-rank-cell">${{fmtLeaderNumber(row.days)}}</td>
      <td class="num">${{compactRank(row.bestRank)}}</td>
      <td class="num">${{fmtLeaderNumber(row.entries)}}</td>
    </tr>
  `).join('');
}}
function showChartDaysLeaderboardTable() {{
  document.getElementById('chartDaysLeaderboardTableView')?.classList.remove('hide');
  document.getElementById('chartDaysDetailView')?.classList.remove('show');
  document.getElementById('chartDaysLeaderboardBack')?.classList.remove('show');
  document.getElementById('chartDaysLeaderboardTitle').textContent = 'Chart Days Snapshot';
  const rows = CHART_DAYS_LEADERBOARD.rows || [];
  document.getElementById('chartDaysLeaderboardSub').textContent = `${{fmtLeaderNumber(CHART_DAYS_LEADERBOARD.maxDays || 0)}} max days · ${{fmtLeaderNumber(CHART_DAYS_LEADERBOARD.listedRows || rows.length)}} tracks in last ${{CHART_DAYS_LEADERBOARD.windowDays || 30}} days`;
}}
function openChartDaysDetail(position) {{
  const row = (CHART_DAYS_LEADERBOARD.rows || []).find(item => Number(item.position) === Number(position));
  if (!row) return;
  const view = document.getElementById('chartDaysDetailView');
  const table = document.getElementById('chartDaysLeaderboardTableView');
  const back = document.getElementById('chartDaysLeaderboardBack');
  document.getElementById('chartDaysLeaderboardTitle').textContent = row.title;
  document.getElementById('chartDaysLeaderboardSub').textContent = `Artist Name · ${{row.artist || 'Unknown artist'}}`;
  view.innerHTML = `
    <div class="detail-hero">
      <div>
        <div class="detail-name">${{escLeader(row.title)}}</div>
        <div class="detail-meta">
          <span class="detail-pill">${{escLeader(row.artist || 'Unknown artist')}}</span>
          ${{platformPills(row.platform)}}
          <span class="detail-pill">${{fmtLeaderNumber(row.days)}} chart days</span>
          <span class="detail-pill">Best rank ${{compactRank(row.bestRank)}}</span>
        </div>
      </div>
    </div>
    <div class="detail-grid">
      <div class="detail-card"><div class="detail-label">Song</div><div class="detail-val" title="${{escLeader(row.title)}}">${{escLeader(row.title)}}</div></div>
      <div class="detail-card"><div class="detail-label">Artist</div><div class="detail-val" title="${{escLeader(row.artist)}}">${{escLeader(row.artist)}}</div></div>
      <div class="detail-card"><div class="detail-label">Platform</div><div class="detail-val">${{escLeader(row.platform || 'n/a')}}</div></div>
      <div class="detail-card"><div class="detail-label">Chart days</div><div class="detail-val">${{fmtLeaderNumber(row.days)}}</div></div>
      <div class="detail-card"><div class="detail-label">Best rank</div><div class="detail-val">${{compactRank(row.bestRank)}}</div></div>
      <div class="detail-card"><div class="detail-label">Entries</div><div class="detail-val">${{fmtLeaderNumber(row.entries)}}</div></div>
      <div class="detail-card"><div class="detail-label">Metric</div><div class="detail-val">${{fmtLeaderNumber(row.metric)}}</div></div>
      <div class="detail-card"><div class="detail-label">Latest seen</div><div class="detail-val">${{escLeader(row.latestDate || 'n/a')}}</div></div>
    </div>
  `;
  table?.classList.add('hide');
  view?.classList.add('show');
  back?.classList.add('show');
}}
function openChartDaysLeaderboard() {{
  renderChartDaysLeaderboard();
  showChartDaysLeaderboardTable();
  document.getElementById('chartDaysLeaderboardModal')?.classList.add('open');
}}
function closeChartDaysLeaderboard(event) {{
  const modal = document.getElementById('chartDaysLeaderboardModal');
  if (!event) {{
    modal?.classList.remove('open');
    showChartDaysLeaderboardTable();
  }}
}}
function renderPopularSongsLeaderboard() {{
  const body = document.getElementById('popularSongsLeaderboardBody');
  const sub = document.getElementById('popularSongsLeaderboardSub');
  if (!body || !sub) return;
  const rows = POPULAR_SONGS_LEADERBOARD.rows || [];
  sub.textContent = `${{fmtLeaderNumber(POPULAR_SONGS_LEADERBOARD.total || 0)}} top-10 songs · ${{fmtLeaderNumber(POPULAR_SONGS_LEADERBOARD.listedRows || rows.length)}} ranked tracks in last ${{POPULAR_SONGS_LEADERBOARD.windowDays || 30}} days`;
  if (!rows.length) {{
    body.innerHTML = '<tr><td colspan="7"><div class="leader-empty">No popular-song rows available.</div></td></tr>';
    return;
  }}
  body.innerHTML = rows.map(row => `
    <tr>
      <td class="leader-pos">${{row.position}}</td>
      <td><button class="leader-name" type="button" onclick="openPopularSongsDetail(${{row.position}})" title="${{escLeader(row.title)}}">${{escLeader(row.title)}}</button></td>
      <td><div class="leader-artist"><div class="leader-avatar">${{escLeader(initials(row.artist))}}</div><span class="country-cell" title="${{escLeader(row.artist)}}">${{escLeader(row.artist)}}</span></div></td>
      <td>${{platformPills(row.platform)}}</td>
      <td class="num leader-rank-cell">${{compactRank(row.bestRank)}}</td>
      <td class="num">${{fmtLeaderNumber(row.top10Entries)}}</td>
      <td class="num">${{fmtLeaderNumber(row.metric)}}</td>
    </tr>
  `).join('');
}}
function showPopularSongsLeaderboardTable() {{
  document.getElementById('popularSongsLeaderboardTableView')?.classList.remove('hide');
  document.getElementById('popularSongsDetailView')?.classList.remove('show');
  document.getElementById('popularSongsLeaderboardBack')?.classList.remove('show');
  document.getElementById('popularSongsLeaderboardTitle').textContent = 'Popular Songs Snapshot';
  const rows = POPULAR_SONGS_LEADERBOARD.rows || [];
  document.getElementById('popularSongsLeaderboardSub').textContent = `${{fmtLeaderNumber(POPULAR_SONGS_LEADERBOARD.total || 0)}} top-10 songs · ${{fmtLeaderNumber(POPULAR_SONGS_LEADERBOARD.listedRows || rows.length)}} ranked tracks in last ${{POPULAR_SONGS_LEADERBOARD.windowDays || 30}} days`;
}}
function openPopularSongsDetail(position) {{
  const row = (POPULAR_SONGS_LEADERBOARD.rows || []).find(item => Number(item.position) === Number(position));
  if (!row) return;
  const view = document.getElementById('popularSongsDetailView');
  const table = document.getElementById('popularSongsLeaderboardTableView');
  const back = document.getElementById('popularSongsLeaderboardBack');
  document.getElementById('popularSongsLeaderboardTitle').textContent = row.title;
  document.getElementById('popularSongsLeaderboardSub').textContent = `Artist Name · ${{row.artist || 'Unknown artist'}}`;
  view.innerHTML = `
    <div class="detail-hero">
      <div>
        <div class="detail-name">${{escLeader(row.title)}}</div>
        <div class="detail-meta">
          <span class="detail-pill">${{escLeader(row.artist || 'Unknown artist')}}</span>
          ${{platformPills(row.platform)}}
          <span class="detail-pill">Best rank ${{compactRank(row.bestRank)}}</span>
          <span class="detail-pill">${{fmtLeaderNumber(row.top10Entries)}} top-10 entries</span>
        </div>
      </div>
    </div>
    <div class="detail-grid">
      <div class="detail-card"><div class="detail-label">Song</div><div class="detail-val" title="${{escLeader(row.title)}}">${{escLeader(row.title)}}</div></div>
      <div class="detail-card"><div class="detail-label">Artist</div><div class="detail-val" title="${{escLeader(row.artist)}}">${{escLeader(row.artist)}}</div></div>
      <div class="detail-card"><div class="detail-label">Platform</div><div class="detail-val">${{escLeader(row.platform || 'n/a')}}</div></div>
      <div class="detail-card"><div class="detail-label">Best rank</div><div class="detail-val">${{compactRank(row.bestRank)}}</div></div>
      <div class="detail-card"><div class="detail-label">Top 10 entries</div><div class="detail-val">${{fmtLeaderNumber(row.top10Entries)}}</div></div>
      <div class="detail-card"><div class="detail-label">Metric</div><div class="detail-val">${{fmtLeaderNumber(row.metric)}}</div></div>
      <div class="detail-card"><div class="detail-label">Latest seen</div><div class="detail-val">${{escLeader(row.latestDate || 'n/a')}}</div></div>
    </div>
  `;
  table?.classList.add('hide');
  view?.classList.add('show');
  back?.classList.add('show');
}}
function openPopularSongsLeaderboard() {{
  renderPopularSongsLeaderboard();
  showPopularSongsLeaderboardTable();
  document.getElementById('popularSongsLeaderboardModal')?.classList.add('open');
}}
function closePopularSongsLeaderboard(event) {{
  const modal = document.getElementById('popularSongsLeaderboardModal');
  if (!event) {{
    modal?.classList.remove('open');
    showPopularSongsLeaderboardTable();
  }}
}}
document.addEventListener('keydown', event => {{
  if (event.key === 'Escape') {{
    closeArtistLeaderboard();
    closeSongsLeaderboard();
    closeAlbumsLeaderboard();
    closeChartDaysLeaderboard();
    closePopularSongsLeaderboard();
  }}
}});
</script>
</body></html>"""
    st_components.html(html, height=880, scrolling=True)
