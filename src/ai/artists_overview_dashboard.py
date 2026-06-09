from __future__ import annotations

import math
from html import escape
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src.database.connection import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_DAYS = 30


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
        WITH sp_bounds AS (SELECT MAX(date) AS max_d FROM spotify_daily WHERE country = 'global'),
        it_bounds AS (SELECT MAX(date) AS max_d FROM itunes_daily WHERE country = 'ww'),
        raw_rows AS (
            SELECT d.artist_title, d.rank, d.days, d.streams::numeric AS metric
            FROM spotify_daily d, sp_bounds b
            WHERE d.country = 'global'
              AND d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
            UNION ALL
            SELECT d.artist_title, d.rank, d.days, d.points::numeric AS metric
            FROM itunes_daily d, it_bounds b
            WHERE d.country = 'ww'
              AND d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
        ),
        parsed AS (
            SELECT
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
            SELECT title, SUM(metric) AS metric, MIN(rank) AS best_rank
            FROM parsed
            GROUP BY title
            ORDER BY metric DESC
            LIMIT 10
        ),
        kpis AS (
            SELECT
                SUM(metric) AS metric,
                COUNT(DISTINCT title) FILTER (WHERE rank <= 10) AS popular_songs,
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
            row_count
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
            NULL::bigint AS row_count
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
            row_count
        FROM kpis
    """
    rows = _run_query(query, (days, days))
    if not rows:
        return pd.DataFrame(), pd.DataFrame(), {"max_days": 0, "popular_songs": 0, "row_count": 0}
    df = pd.DataFrame(rows)
    for col in ["metric", "chart_count", "entries", "best_rank", "max_days", "row_count"]:
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
        .rename(columns={"label": "title"})[["title", "metric"]]
        .sort_values("metric", ascending=False)
        .reset_index(drop=True)
    )
    kpi_row = df[df["row_type"] == "kpi"].head(1)
    kpis = {
        "max_days": float(kpi_row["max_days"].iloc[0]) if not kpi_row.empty else 0,
        "popular_songs": float(kpi_row["chart_count"].iloc[0]) if not kpi_row.empty else 0,
        "row_count": float(kpi_row["row_count"].iloc[0]) if not kpi_row.empty else 0,
    }
    return artist_stats, top_tracks, kpis


@st.cache_data(ttl=300, show_spinner=False)
def _load_album_dashboard(days: int = WINDOW_DAYS) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    query = """
        WITH bounds AS (
            SELECT MAX(date) AS max_d FROM itunes_artist_album WHERE country = 'ww'
        ),
        parsed AS (
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
            WHERE d.country = 'ww'
              AND d.date > (b.max_d - %s::int)
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
            SELECT album, SUM(metric) AS metric, MIN(rank) AS best_rank
            FROM parsed
            GROUP BY album
            ORDER BY metric DESC
            LIMIT 10
        ),
        kpis AS (
            SELECT SUM(metric) AS metric, COUNT(*) AS entries, MAX(days) AS max_days, COUNT(*) AS row_count
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
            row_count
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
            NULL::bigint AS row_count
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
            row_count
        FROM kpis
    """
    rows = _run_query(query, (days,))
    if not rows:
        return pd.DataFrame(), pd.DataFrame(), {"row_count": 0, "max_days": 0}
    df = pd.DataFrame(rows)
    for col in ["metric", "chart_count", "entries", "best_rank", "max_days", "row_count"]:
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
        .rename(columns={"label": "album"})[["album", "metric"]]
        .sort_values("metric", ascending=False)
        .reset_index(drop=True)
    )
    kpi_row = df[df["row_type"] == "kpi"].head(1)
    kpis = {
        "row_count": float(kpi_row["row_count"].iloc[0]) if not kpi_row.empty else 0,
        "max_days": float(kpi_row["max_days"].iloc[0]) if not kpi_row.empty else 0,
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


def render_artists_overview() -> None:
    latest_artists = _load_artist_rank_history(WINDOW_DAYS)
    spotify_df = _load_spotify_artist_latest()
    details_df = _load_artist_details_latest()
    track_artist_stats, top_tracks, track_kpis = _load_track_dashboard(WINDOW_DAYS)
    album_artist_stats, top_albums, album_kpis = _load_album_dashboard(WINDOW_DAYS)

    if latest_artists.empty and details_df.empty and top_tracks.empty and top_albums.empty:
        st.info("No artist overview data is available yet.")
        return

    latest_date = latest_artists["scrape_date"].max() if not latest_artists.empty else None
    filtered = _build_artist_table(latest_artists, spotify_df, details_df, track_artist_stats, album_artist_stats)

    artist_total = float(latest_artists["name"].nunique()) if not latest_artists.empty else 0
    song_total = float(details_df["songs_count"].sum()) if "songs_count" in details_df else 0
    album_total = float(details_df["albums_count"].sum()) if "albums_count" in details_df else 0
    chart_days = float(track_kpis.get("max_days", 0))
    popular_songs = float(track_kpis.get("popular_songs", 0))
    latest_label = str(latest_date) if latest_date else "No snapshot date"
    track_rows_label = f"{_fmt_n(track_kpis.get('row_count', 0))} chart rows"
    album_rows_label = f"{_fmt_n(album_kpis.get('row_count', 0))} album chart rows"
    details_label = f"{_fmt_n(len(details_df))} artist detail rows"

    def kpi_html(title: str, value: str, icon: str, subtitle: str) -> str:
        return (
            "<div class='kpi'>"
            f"<div class='kpi-icon'>{icon}</div>"
            "<div class='kpi-copy'>"
            f"<div class='kpi-title'>{escape(title)}</div>"
            f"<div class='kpi-value'>{escape(value)}</div>"
            f"<div class='kpi-sub'>{escape(subtitle)}</div>"
            "</div></div>"
        )

    def bars_html(df: pd.DataFrame, label_col: str, value_col: str, title: str, desc: str, limit: int = 7) -> str:
        if df.empty:
            return f"<section class='panel'><div class='panel-head'><div><h3>{escape(title)}</h3><p>{escape(desc)}</p></div></div><div class='empty'>No rows available.</div></section>"
        df = df.head(limit).reset_index(drop=True)
        max_value = float(df[value_col].max()) or 1.0
        rows = []
        for idx, row in df.iterrows():
            label = str(row[label_col] or "Unknown")
            value = float(row[value_col] or 0)
            width = max(4, min(100, value / max_value * 100))
            rows.append(
                "<div class='bar-row'>"
                f"<span class='bar-index'>{idx + 1}</span>"
                f"<span class='bar-label' title='{escape(label)}'>{escape(_short_label(label, 20))}</span>"
                "<span class='bar-track'>"
                f"<span class='bar-fill' style='width:{width:.1f}%'></span>"
                f"<b>{escape(_fmt_n(value))}</b></span></div>"
            )
        return (
            "<section class='panel'>"
            f"<div class='panel-head'><div><h3>{escape(title)}</h3><p>{escape(desc)}</p></div><span class='toggle'><b>Top</b><i>All</i></span></div>"
            f"<div class='bars'>{''.join(rows)}</div></section>"
        )

    def donut_html(df: pd.DataFrame) -> str:
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
            f"<div class='donut' style='background:conic-gradient({', '.join(segments)})'><span>{escape(_fmt_n(total))}</span></div>"
            f"<div class='legend'>{''.join(legend)}</div></section>"
        )

    def treemap_html(df: pd.DataFrame) -> str:
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

    def radar_html(df: pd.DataFrame) -> str:
        source_cols = [("iTunes", "itunes_points"), ("Spotify", "spotify_points"), ("Apple Music", "apple_music_points"), ("Shazam", "shazam_points"), ("YouTube", "youtube_points"), ("Other", "other_points")]
        labels, values = [], []
        for label, col in source_cols:
            if col in df.columns:
                labels.append(label)
                values.append(float(df[col].fillna(0).sum()))
        if not any(values):
            return "<section class='panel'><div class='panel-head'><div><h3>Source Performance</h3><p>Platform contribution mix from artist ranking points.</p></div></div><div class='empty'>No source point rows available.</div></section>"
        max_value = max(values) or 1.0
        cx, cy, radius = 180, 96, 72
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
        rings = "".join(f"<circle cx='{cx}' cy='{cy}' r='{r}'></circle>" for r in [24, 48, 72])
        return "<section class='panel chart-panel'><div class='panel-head'><div><h3>Source Performance</h3><p>Platform contribution mix from artist ranking points.</p></div></div><svg class='radar' viewBox='0 0 360 192'><g class='radar-grid'>" + rings + "".join(axes) + "</g><polygon points='" + " ".join(points) + "'></polygon>" + "".join(label_nodes) + "</svg></section>"

    def word_cloud_html(df: pd.DataFrame) -> str:
        cloud_df = df[["name", "total_points"]].fillna({"total_points": 0}).sort_values("total_points", ascending=False).head(36) if not df.empty else pd.DataFrame()
        words = []
        for pos, (_, row) in enumerate(cloud_df.iterrows()):
            if pos < 4:
                klass = "tier-xl"
            elif pos < 10:
                klass = "tier-lg"
            elif pos < 20:
                klass = "tier-md"
            else:
                klass = "tier-sm"
            color_class = f"tone-{pos % 5}"
            words.append(
                f"<span class='artist-word {klass} {color_class}' title='Rank {pos + 1} · {_fmt_n(row.get('total_points'))} points'>"
                f"{escape(str(row['name']))}"
                "</span>"
            )
        graph_df = cloud_df.head(18).reset_index(drop=True)
        graph_svg = ""
        if not graph_df.empty:
            width, height, pad_x, pad_y = 980, 132, 28, 18
            values = [float(v or 0) for v in graph_df["total_points"].tolist()]
            max_value = max(values) or 1.0
            min_value = min(values) if len(values) > 1 else 0.0
            span = max(max_value - min_value, 1.0)
            points = []
            bars = []
            for idx, value in enumerate(values):
                x = pad_x + (idx / max(len(values) - 1, 1)) * (width - pad_x * 2)
                y = height - pad_y - ((value - min_value) / span) * (height - pad_y * 2)
                points.append((x, y))
                bar_h = max(4, (height - pad_y - y))
                tone = idx % 5
                bars.append(
                    f"<rect class='perf-bar tone-fill-{tone}' x='{x - 11:.1f}' y='{height - pad_y - bar_h:.1f}' width='22' height='{bar_h:.1f}' rx='6'></rect>"
                )
            point_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            area_str = f"{pad_x},{height-pad_y} {point_str} {width-pad_x},{height-pad_y}"
            dots = "".join(f"<circle class='perf-dot tone-fill-{idx % 5}' cx='{x:.1f}' cy='{y:.1f}' r='5.5'></circle>" for idx, (x, y) in enumerate(points))
            grid = "".join(
                f"<line class='perf-grid' x1='{pad_x}' y1='{gy}' x2='{width-pad_x}' y2='{gy}'></line>"
                for gy in [30, 58, 86, 114]
            )
            first_name = escape(_short_label(str(graph_df.iloc[0]["name"]), 18))
            last_name = escape(_short_label(str(graph_df.iloc[-1]["name"]), 18))
            graph_svg = (
                "<svg class='perf-graph' viewBox='0 0 980 132' role='img' aria-label='Top artist total points trend'>"
                + grid
                + f"<line class='perf-axis' x1='{pad_x}' y1='{height-pad_y}' x2='{width-pad_x}' y2='{height-pad_y}'></line>"
                + "".join(bars)
                + f"<polygon class='perf-area' points='{area_str}'></polygon>"
                + f"<polyline class='perf-line' points='{point_str}'></polyline>"
                + dots
                + f"<text class='perf-title' x='{pad_x}' y='16'>Top score {_fmt_n(max_value)}</text>"
                + f"<text class='perf-name' x='{pad_x}' y='130'>{first_name}</text>"
                + f"<text class='perf-name' x='{width-pad_x}' y='130' text-anchor='end'>{last_name}</text>"
                + "</svg>"
            )
        return (
            "<section class='panel word-panel'>"
            "<div class='panel-head'><div><h3>Artist Performance</h3><p>Ranked artist strength by total points, with the top 18 plotted below.</p></div><span class='top-chip'>Top 36 by total points</span></div>"
            f"<div class='word-cloud'>{''.join(words)}</div>{graph_svg}</section>"
        )

    top_artists = filtered[["name", "total_points"]].fillna({"total_points": 0}).sort_values("total_points", ascending=False).head(10) if not filtered.empty else pd.DataFrame()
    theme = "dark" if st.session_state.get("dark_mode", True) else "light"
    html = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui;background:transparent}.dash{min-height:1060px;padding:18px;color:var(--text);background:var(--bg)}
.dash.dark{--bg:linear-gradient(135deg,#0d1117 0%,#111827 42%,#17152a 72%,#261d3d 100%);--panel:#161b26;--panel2:#1f2633;--panel3:#283041;--text:#f8fafc;--muted:#cdd6e4;--soft:#94a3b8;--border:rgba(148,163,184,.15);--track:rgba(148,163,184,.13);--shadow:0 18px 42px rgba(0,0,0,.24);--rose:#fb7185;--blue:#60a5fa;--green:#34d399;--purple:#c4b5fd;--amber:#fcd34d}
.dash.light{--bg:linear-gradient(135deg,#f5f6fa 0%,#ffffff 58%,#f8f9fb 100%);--panel:#fff;--panel2:#f8f9fb;--panel3:#eef1f7;--text:#1a1a1a;--muted:#4a5568;--soft:#8a8fa3;--border:rgba(148,163,184,.22);--track:rgba(15,23,42,.08);--shadow:0 14px 30px rgba(15,23,42,.08);--rose:#fb7185;--blue:#60a5fa;--green:#34d399;--purple:#a78bfa;--amber:#f59e0b}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:18px;margin-bottom:16px}.kpi{min-height:124px;border-radius:16px;background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);padding:18px 16px;display:flex;align-items:center;gap:16px;box-shadow:var(--shadow);position:relative;overflow:hidden}.kpi:before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:var(--accent)}.kpi-icon{width:44px;height:44px;border-radius:14px;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2));font-size:24px;display:flex;align-items:center;justify-content:center;flex:0 0 auto}.kpi:nth-child(1){--accent:var(--rose);--accent2:#f43f5e}.kpi:nth-child(2){--accent:var(--blue);--accent2:#2563eb}.kpi:nth-child(3){--accent:var(--green);--accent2:#10b981}.kpi:nth-child(4){--accent:var(--purple);--accent2:#8b5cf6}.kpi:nth-child(5){--accent:var(--amber);--accent2:#f97316}.kpi-title{color:var(--soft);font-size:12px;text-transform:uppercase;letter-spacing:.06em;font-weight:800;margin-bottom:10px;white-space:nowrap}.kpi-value{font-size:30px;font-weight:900;line-height:1;color:var(--text);font-variant-numeric:tabular-nums}.kpi-sub{color:var(--muted);margin-top:8px;font-size:11px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:14px}.panel{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);border-radius:16px;padding:12px;min-height:276px;overflow:hidden;box-shadow:var(--shadow)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:10px;gap:10px}.panel h3{margin:0;color:var(--text);font-size:16px;font-weight:800}.panel p{margin:5px 0 0;color:var(--muted);font-size:11px;font-weight:650;line-height:1.25}.toggle{display:inline-flex;border:1px solid var(--border);border-radius:3px;overflow:hidden;font-size:10px;flex:0 0 auto}.toggle b,.toggle i{padding:4px 7px;font-style:normal}.toggle b{background:var(--rose);color:#fff}.toggle i{background:var(--panel3);color:var(--muted)}
.bars{display:flex;flex-direction:column;gap:9px}.bar-row{display:grid;grid-template-columns:16px minmax(82px,30%) 1fr;gap:8px;align-items:center}.bar-index,.bar-label{font-size:11px}.bar-index{color:var(--soft)}.bar-label{color:var(--text);font-weight:750;overflow:hidden;text-overflow:ellipsis}.bar-track{height:18px;background:var(--track);border-radius:4px;position:relative}.bar-fill{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--rose),var(--blue));border:1px solid rgba(251,113,133,.32)}.bar-track b{position:absolute;right:5px;top:50%;transform:translateY(-50%);font-size:10px;color:var(--text)}
.radar{width:100%;height:220px}.radar text{fill:var(--soft);font-size:10px}.radar-grid circle,.radar-grid line{fill:none;stroke:var(--border)}.radar polygon{fill:rgba(196,181,253,.18);stroke:var(--purple);stroke-width:2}
.donut{width:132px;height:132px;border-radius:50%;margin:8px auto 12px;display:grid;place-items:center;position:relative}.donut:after{content:"";position:absolute;width:72px;height:72px;border-radius:50%;background:var(--panel)}.donut span{position:relative;z-index:1;color:var(--text);font-weight:900}.legend{display:grid;gap:6px}.legend-row{display:grid;grid-template-columns:12px 1fr auto;gap:7px;align-items:center;color:var(--muted);font-size:11px}.legend-row span{width:10px;height:10px;border-radius:50%}.legend-row b{color:var(--text);font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.legend-row i{font-style:normal}
.treemap{height:224px;display:flex;flex-wrap:wrap;gap:2px}.tile{min-width:72px;min-height:52px;padding:7px;color:#fff;display:flex;flex-direction:column;justify-content:space-between;font-size:11px;font-weight:800;text-shadow:0 1px 2px rgba(0,0,0,.28)}.tile b{font-size:13px}.top-chip{font-size:11px;color:var(--muted);background:var(--panel3);border:1px solid var(--border);padding:3px 7px;border-radius:4px}.word-panel{min-height:312px;padding:14px 14px 18px}.word-panel .panel-head{margin-bottom:12px}.word-cloud{min-height:88px;max-height:100px;overflow:hidden;line-height:1.12;display:flex;align-content:flex-start;align-items:baseline;flex-wrap:wrap;gap:8px 14px}.artist-word{display:inline-flex;align-items:baseline;font-weight:900;letter-spacing:.01em;white-space:nowrap;text-shadow:0 8px 20px rgba(0,0,0,.18)}.tier-xl{font-size:30px;line-height:1}.tier-lg{font-size:20px;line-height:1}.tier-md{font-size:14px;line-height:1}.tier-sm{font-size:11px;line-height:1;opacity:.86}.tone-0{color:var(--rose)}.tone-1{color:var(--blue)}.tone-2{color:var(--green)}.tone-3{color:var(--purple)}.tone-4{color:var(--amber)}.perf-graph{width:100%;height:132px;margin-top:14px;display:block;border-radius:12px;background:linear-gradient(180deg,rgba(96,165,250,.10),rgba(251,113,133,.05))}.perf-grid{stroke:var(--border);stroke-width:1;stroke-dasharray:4 5}.perf-axis{stroke:var(--soft);stroke-width:1.5}.perf-area{fill:rgba(96,165,250,.24)}.perf-line{fill:none;stroke:var(--rose);stroke-width:5;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 8px rgba(251,113,133,.42))}.perf-bar{opacity:.72}.perf-dot{stroke:var(--panel);stroke-width:3;filter:drop-shadow(0 0 5px rgba(255,255,255,.22))}.perf-graph text{fill:var(--soft);font-size:11px;font-weight:900}.perf-title{fill:var(--text)!important;font-size:13px!important}.perf-name{font-size:10px!important}.tone-fill-0{fill:var(--rose)}.tone-fill-1{fill:var(--blue)}.tone-fill-2{fill:var(--green)}.tone-fill-3{fill:var(--purple)}.tone-fill-4{fill:var(--amber)}
.empty{color:var(--muted);font-size:12px;padding:24px 4px}
@media(max-width:1050px){.kpis{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}@media(max-width:640px){.kpis{grid-template-columns:1fr}.dash{padding:10px}.kpi{min-height:100px}}
</style></head><body>
""" + f"<main class='dash {theme}'>" + "<div class='kpis'>" + kpi_html("Artists", _fmt_n(artist_total), "&#127908;", f"Latest rank snapshot: {latest_label}") + kpi_html("Songs", _fmt_n(song_total), "&#9835;", details_label) + kpi_html("Albums", _fmt_n(album_total), "&#9673;", album_rows_label) + kpi_html("Chart Days", _fmt_n(chart_days), "&#9719;", f"Max track streak in last {WINDOW_DAYS} days") + kpi_html("Popular Songs", _fmt_n(popular_songs), "&#9679;", f"Top 10 ranked tracks · {track_rows_label}") + "</div><div class='grid'>" + bars_html(top_artists, "name", "total_points", "Top Artist", "Highest scoring artists in the latest ranking snapshot.", 10) + bars_html(top_tracks, "title", "metric", "Top Track", "Tracks with the strongest combined chart metric.", 10) + bars_html(top_albums, "album", "metric", "Top Album", "Albums with the strongest album chart metric.", 10) + "</div><div class='grid'>" + donut_html(filtered) + treemap_html(top_albums) + radar_html(filtered) + "</div>" + word_cloud_html(filtered) + "</main></body></html>"
    st_components.html(html, height=1120, scrolling=False)
