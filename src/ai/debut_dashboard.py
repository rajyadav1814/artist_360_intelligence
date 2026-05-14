"""
Debut Intelligence Dashboard
Chromadata · Commercial Signal Intelligence

Tracks all new chart entries for the current week vs prior week across:
  - Spotify Daily (global + regional)
  - iTunes Daily (WW + US)
  - Track Rankings (cross-platform composite)
  - Trending Monthly (new artists entering the trending chart)

Matches the Sony Latin Pulse dark UI design language with full
debut intelligence: entry strength, rank distribution, multi-track
debutants, Spotify debuts, new-to-trending artists, debut vs
incumbent comparison, and an acquisition spotlight card.
"""

import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from src.database.connection import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
#  SHARED DARK THEME  (inject once from the parent app OR here)
# ─────────────────────────────────────────────────────────────
DEBUT_CSS = """
<style>
/* ── base overrides ── */
.block-container { padding-top: 1.5rem !important; }
hr { margin: 1rem 0 !important; border-color: var(--border) !important; opacity: 0.3; }

/* ── tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    gap: 8px;
    border-bottom: 1px solid var(--border) !important;
    background: transparent;
}
[data-testid="stTabs"] [role="tab"] {
    background: var(--surface2) !important;
    color: var(--text2) !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px 10px 0 0 !important;
    padding: 10px 20px !important;
    transition: all 0.3s ease;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: var(--text) !important;
    background: linear-gradient(135deg, rgba(79,142,247,.2), rgba(124,92,252,.2)) !important;
    border-color: var(--accent) !important;
}

/* ── metrics ── */
[data-testid="stMetric"] {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    padding: 0.85rem 1.15rem !important;
    border-radius: 14px !important;
}
[data-testid="stMetricLabel"] p {
    font-size: 0.8rem !important;
    color: var(--text2) !important;
    font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    font-weight: 900 !important;
}

/* ── unified cards ── */
.insight-card, .spotlight-card, .mini-stat-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
    box-shadow: 0 12px 24px rgba(0,0,0,.15);
}
.insight-icon { font-size: 1.6rem; margin-bottom: 0.5rem; }
.insight-title {
    font-size: 0.75rem;
    color: var(--text2);
    font-weight: 700;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}
.insight-val {
    font-size: 1.4rem;
    font-weight: 800;
    color: var(--text);
    margin-bottom: 0.35rem;
}
.insight-desc { font-size: 0.9rem; color: var(--text2); line-height: 1.5; }

/* ── tables & rows ── */
.rank-row {
    display: grid;
    align-items: center;
    gap: 12px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
}
.rank-row:hover { background: rgba(79,142,247,0.1); }

/* ── spotlight enhancement ── */
.sp-name { font-size: 1.8rem; font-weight: 900; line-height: 1.2; margin-bottom: 0.5rem; }
.sp-artist { font-size: 1rem; color: var(--text2); margin-bottom: 1rem; }
.sp-stat { padding: 0.6rem 0.85rem; border-radius: 10px; }
.sp-val { font-size: 1.25rem; font-weight: 800; }

/* ── scroll area ── */
.scroll-area {
    max-height: 380px;
    overflow-y: auto;
    padding-right: 8px;
}
.scroll-area::-webkit-scrollbar { width: 4px; }
.scroll-area::-webkit-scrollbar-track { background: transparent; }
.scroll-area::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }

/* ── badges ── */
.badge-new { background: rgba(79,142,247,.2); color: #c3daff; border: 1px solid rgba(79,142,247,.4); padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 800; }
.badge-hot { background: rgba(34,211,160,.2); color: #a5f3d9; border: 1px solid rgba(34,211,160,.4); padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 800; }
</style>
"""


# ─────────────────────────────────────────────────────────────
#  PLOTLY DARK LAYOUT
# ─────────────────────────────────────────────────────────────
_DARK = dict(
    paper_bgcolor="rgba(18,24,42,1)",
    plot_bgcolor="rgba(18,24,42,1)",
    font=dict(color="#eef2ff", family="Inter, Helvetica Neue, sans-serif", size=11),
    margin=dict(l=0, r=0, t=32, b=0),
    xaxis=dict(
        gridcolor="rgba(151,163,197,.12)",
        showline=False,
        tickcolor="#333",
        tickfont=dict(color="#97a3c5", size=10),
        title=None,
    ),
    yaxis=dict(
        gridcolor="rgba(151,163,197,.12)",
        showline=False,
        tickcolor="#333",
        tickfont=dict(color="#97a3c5", size=10),
        title=None,
    ),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        borderwidth=0,
        font=dict(color="#97a3c5", size=10),
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
    ),
    hoverlabel=dict(
        bgcolor="rgba(9,17,39,.96)",
        bordercolor="rgba(79,142,247,.45)",
        font=dict(color="#eef2ff", size=11),
    ),
)


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def fmt(n) -> str:
    """Format a number as K / M / B string."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    n = float(n)
    if abs(n) >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}B"
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"{n/1_000:.0f}K"
    return f"{int(n)}"


def _plotly(fig: go.Figure, height: int = 280) -> None:
    fig.update_layout(height=height, **_DARK)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _sec(left: str, right: str = "") -> None:
    badge = f'<span class="sec-badge">{right}</span>' if right else ""
    st.markdown(
        f'<div class="sec-hdr"><span class="sec-title">{left}</span>{badge}</div>',
        unsafe_allow_html=True,
    )


def _get_conn_cursor():
    conn = get_connection()
    return conn, conn.cursor()


def _df_from_cursor(cur) -> pd.DataFrame:
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def _latest_date(table: str = "spotify_daily") -> "datetime.date | None":
    try:
        conn, cur = _get_conn_cursor()
        with cur:
            cur.execute(f"SELECT MAX(date) AS d FROM {table}")
            row = cur.fetchone()
            if row:
                val = row[0] if isinstance(row, (list, tuple)) else row.get("d")
                return pd.to_datetime(val).date() if val else None
    except Exception as e:
        logger.error(f"_latest_date({table}): {e}")
    return None


# ─────────────────────────────────────────────────────────────
#  DATABASE QUERIES
# ─────────────────────────────────────────────────────────────

def get_debut_tracks(days_back: int = 7) -> pd.DataFrame:
    """
    Tracks that appear in the CURRENT week's chart but NOT in the
    PRIOR week.  Returns rank, score, artist_title, label, platform.
    Works across the unified spotify_daily table (region = 'global').
    Falls back gracefully if no prior-week data exists.
    """
    try:
        conn, cur = _get_conn_cursor()
        with cur:
            ld = _latest_date("spotify_daily")
            if not ld:
                return pd.DataFrame()

            current_start = ld - timedelta(days=days_back - 1)
            prior_start   = ld - timedelta(days=(days_back * 2) - 1)
            prior_end     = ld - timedelta(days=days_back)

            cur.execute(
                """
                WITH current_week AS (
                    SELECT
                        artist_title,
                        MAX(label)         AS label,
                        MIN(rank)          AS best_rank,
                        SUM(streams)       AS total_streams,
                        COUNT(DISTINCT date) AS days_charted,
                        MAX(date)          AS last_seen
                    FROM spotify_daily
                    WHERE date BETWEEN %s AND %s
                      AND streams > 0
                      AND country = 'global'
                    GROUP BY artist_title
                ),
                prior_week AS (
                    SELECT DISTINCT artist_title
                    FROM spotify_daily
                    WHERE date BETWEEN %s AND %s
                      AND streams > 0
                      AND country = 'global'
                )
                SELECT
                    cw.artist_title,
                    cw.label,
                    cw.best_rank      AS rank,
                    cw.total_streams,
                    cw.days_charted,
                    cw.last_seen
                FROM current_week cw
                LEFT JOIN prior_week pw
                       ON cw.artist_title = pw.artist_title
                WHERE pw.artist_title IS NULL
                ORDER BY cw.best_rank ASC
                """,
                (current_start, ld, prior_start, prior_end),
            )
            df = _df_from_cursor(cur)

        for c in ["rank", "total_streams", "days_charted"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        return df
    except Exception as e:
        logger.error(f"get_debut_tracks: {e}")
        return pd.DataFrame()


def get_itunes_debuts(days_back: int = 7) -> pd.DataFrame:
    """
    New entries in the iTunes WW chart (region = 'ww') this week
    that were absent from the prior week.
    """
    try:
        conn, cur = _get_conn_cursor()
        with cur:
            ld = _latest_date("itunes_daily")
            if not ld:
                return pd.DataFrame()

            current_start = ld - timedelta(days=days_back - 1)
            prior_start   = ld - timedelta(days=(days_back * 2) - 1)
            prior_end     = ld - timedelta(days=days_back)

            cur.execute(
                """
                WITH current_wk AS (
                    SELECT
                        artist_title,
                        MAX(label)   AS label,
                        MIN(rank)    AS best_rank,
                        SUM(points)  AS total_score,
                        MAX(peak)    AS peak_position,
                        MAX(date)    AS last_seen
                    FROM itunes_daily
                    WHERE date BETWEEN %s AND %s
                      AND country = 'ww'
                      AND points  > 0
                    GROUP BY artist_title
                ),
                prior_wk AS (
                    SELECT DISTINCT artist_title
                    FROM itunes_daily
                    WHERE date BETWEEN %s AND %s
                      AND country = 'ww'
                )
                SELECT cw.*
                FROM current_wk cw
                LEFT JOIN prior_wk pw
                       ON cw.artist_title = pw.artist_title
                WHERE pw.artist_title IS NULL
                ORDER BY cw.best_rank ASC
                """,
                (current_start, ld, prior_start, prior_end),
            )
            df = _df_from_cursor(cur)

        for c in ["best_rank", "total_score", "peak_position"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        # Split "Artist - Track" format into separate columns if present
        if not df.empty and "artist_title" in df.columns:
            split = df["artist_title"].str.split(" - ", n=1, expand=True)
            df["artist"] = split[0].str.strip()
            df["title"]  = split[1].str.strip() if 1 in split.columns else df["artist_title"]

        return df
    except Exception as e:
        logger.error(f"get_itunes_debuts: {e}")
        return pd.DataFrame()


def get_debut_kpis(debut_df: pd.DataFrame, all_df: pd.DataFrame) -> dict:
    """
    Derive key KPI values from debut and full-chart DataFrames.
    Returns a dict of pre-formatted strings and raw numbers.
    """
    if debut_df.empty:
        return {}

    total        = len(debut_df)
    best_rank    = int(debut_df["rank"].min()) if "rank" in debut_df.columns else 0
    avg_rank     = int(debut_df["rank"].mean()) if "rank" in debut_df.columns else 0
    avg_score    = int(debut_df["total_streams"].mean()) if "total_streams" in debut_df.columns else 0
    median_score = int(debut_df["total_streams"].median()) if "total_streams" in debut_df.columns else 0

    best_track = (
        debut_df.loc[debut_df["rank"].idxmin(), "artist_title"]
        if "artist_title" in debut_df.columns
        else "—"
    )

    dropouts = len(all_df) - len(debut_df) if not all_df.empty else 0
    churn    = round(total / max(len(all_df), 1) * 100, 1) if not all_df.empty else 0.0

    incumbent_avg = (
        all_df[~all_df["artist_title"].isin(debut_df["artist_title"])]["total_streams"].mean()
        if "artist_title" in all_df.columns and not all_df.empty
        else 0
    )
    strength_ratio = round(avg_score / max(incumbent_avg, 1), 2)

    best_debut_score = (
        int(debut_df.loc[debut_df["rank"].idxmin(), "total_streams"])
        if "total_streams" in debut_df.columns
        else 0
    )
    vs_avg_ratio = round(best_debut_score / max(avg_score, 1), 1)

    return {
        "total":           total,
        "best_rank":       best_rank,
        "best_track":      best_track,
        "avg_rank":        avg_rank,
        "avg_score":       avg_score,
        "median_score":    median_score,
        "churn_pct":       churn,
        "incumbent_avg":   int(incumbent_avg),
        "strength_ratio":  strength_ratio,
        "best_debut_score":best_debut_score,
        "vs_avg_ratio":    vs_avg_ratio,
    }


def get_multi_track_debutants(debut_df: pd.DataFrame) -> pd.DataFrame:
    """Artists with 2+ debut tracks this week."""
    if debut_df.empty or "artist_title" not in debut_df.columns:
        return pd.DataFrame()

    multi = (
        debut_df.groupby("artist_title")
        .agg(
            track_count=("artist_title", "count"),
            combined_score=("total_streams", "sum"),
            best_rank=("rank", "min"),
        )
        .reset_index()
        .query("track_count >= 2")
        .sort_values("track_count", ascending=False)
    )
    return multi


def get_new_trending_artists(days_back: int = 30) -> pd.DataFrame:
    """
    Artists that appear in trending_monthly for the current month
    but were absent from the prior month.
    """
    try:
        conn, cur = _get_conn_cursor()
        with cur:
            cur.execute(
                """
                WITH current_m AS (
                    SELECT
                        a.name          AS artist_name,
                        SUM(t.total_points) AS total_score,
                        MIN(t.rank)     AS best_rank,
                        COUNT(DISTINCT t.top_country) AS countries
                    FROM trending_artists_monthly t
                    JOIN artists a ON a.id = t.artist_id
                    WHERE t.month = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
                    GROUP BY a.name
                ),
                prior_m AS (
                    SELECT DISTINCT a.name AS artist_name
                    FROM trending_artists_monthly t
                    JOIN artists a ON a.id = t.artist_id
                    WHERE t.month = TO_CHAR(CURRENT_DATE - INTERVAL '1 month', 'YYYY-MM')
                )
                SELECT cm.*
                FROM current_m cm
                LEFT JOIN prior_m pm ON cm.artist_name = pm.artist_name
                WHERE pm.artist_name IS NULL
                ORDER BY cm.total_score DESC
                LIMIT 15
                """,
            )
            df = _df_from_cursor(cur)

        for c in ["total_score", "best_rank", "countries"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        return df
    except Exception as e:
        logger.error(f"get_new_trending_artists: {e}")
        return pd.DataFrame()


def get_itunes_artist_new_entries(limit: int = 10) -> pd.DataFrame:
    """
    Fetch the latest 'NEW' entries from itunes_artist_rankings.
    """
    try:
        conn, cur = _get_conn_cursor()
        with cur:
            cur.execute(
                """
                SELECT 
                    a.name AS artist_name, 
                    iar.rank, 
                    iar.rank_change, 
                    iar.total_points, 
                    iar.scrape_date
                FROM itunes_artist_rankings iar
                JOIN artists a ON a.id = iar.artist_id
                WHERE iar.rank_change = 'NEW'
                  AND iar.scrape_date >= NOW() - INTERVAL '7 days'
                ORDER BY iar.scrape_date DESC, iar.rank ASC
                LIMIT %s
                """,
                (limit,),
            )
            df = _df_from_cursor(cur)
        
        if not df.empty:
            df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
            df["total_points"] = pd.to_numeric(df["total_points"], errors="coerce")
            # Avoid duplicate entries for the same artist on the same date (handle multiple scrapes)
            if "scrape_date" in df.columns:
                df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
                df = df.drop_duplicates(subset=["artist_name", "scrape_date"])
            
        return df
    except Exception as e:
        logger.error(f"get_itunes_artist_new_entries: {e}")
        return pd.DataFrame()


def get_debut_rank_buckets(debut_df: pd.DataFrame) -> pd.DataFrame:
    """Count debuts in each 25-rank bucket."""
    if debut_df.empty or "rank" not in debut_df.columns:
        return pd.DataFrame()

    buckets = []
    for start in range(1, 201, 25):
        end   = start + 24
        count = int(((debut_df["rank"] >= start) & (debut_df["rank"] <= end)).sum())
        buckets.append({"bucket": f"{start}–{end}", "count": count, "start": start})

    return pd.DataFrame(buckets)


def get_debut_vs_incumbent(debut_df: pd.DataFrame, all_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compare average streams/score between debuts and incumbents
    for each 50-rank tier.
    """
    if debut_df.empty or all_df.empty:
        return pd.DataFrame()

    tiers = []
    for start, end in [(1, 50), (51, 100), (101, 150), (151, 200)]:
        label     = f"{start}–{end}"
        deb_avg   = int(
            debut_df[(debut_df["rank"] >= start) & (debut_df["rank"] <= end)]["total_streams"].mean()
            if "total_streams" in debut_df.columns else 0
        ) or 0
        incumb    = all_df[~all_df["artist_title"].isin(debut_df["artist_title"])]
        inc_avg   = int(
            incumb[(incumb["rank"] >= start) & (incumb["rank"] <= end)]["total_streams"].mean()
            if "total_streams" in incumb.columns else 0
        ) or 0
        tiers.append({"tier": label, "Debuts": deb_avg, "Incumbents": inc_avg})

    return pd.DataFrame(tiers)


def get_all_chart_tracks(days_back: int = 7) -> pd.DataFrame:
    """Full chart for the current week (for KPI comparison baseline)."""
    try:
        conn, cur = _get_conn_cursor()
        with cur:
            ld = _latest_date("spotify_daily")
            if not ld:
                return pd.DataFrame()

            current_start = ld - timedelta(days=days_back - 1)
            cur.execute(
                """
                SELECT
                    artist_title,
                    MAX(label)         AS label,
                    MIN(rank)          AS rank,
                    SUM(streams)       AS total_streams,
                    COUNT(DISTINCT date) AS days_charted
                FROM spotify_daily
                WHERE date BETWEEN %s AND %s
                  AND streams > 0
                  AND country = 'global'
                GROUP BY artist_title
                ORDER BY rank ASC
                """,
                (current_start, ld),
            )
            df = _df_from_cursor(cur)

        for c in ["rank", "total_streams", "days_charted"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        return df
    except Exception as e:
        logger.error(f"get_all_chart_tracks: {e}")
        return pd.DataFrame()


def get_acquisition_spotlight(debut_df: pd.DataFrame) -> dict:
    """
    Pick the most promising debut as an acquisition signal:
    highest-ranking new entry with strong stream growth signal.
    Returns a dict of display fields.
    """
    if debut_df.empty:
        return {}

    # Score = inverse rank (lower is better) weighted by streams
    df = debut_df.copy()
    df["acq_score"] = (
        (1 / df["rank"].clip(lower=1)) * 1000
        + df["total_streams"] / df["total_streams"].max()
    )
    candidate = df.sort_values("acq_score", ascending=False).iloc[0]

    return {
        "artist_title":  candidate.get("artist_title", "—"),
        "label":         candidate.get("label", "Independent"),
        "rank":          int(candidate.get("rank", 0)),
        "total_streams": int(candidate.get("total_streams", 0)),
        "days_charted":  int(candidate.get("days_charted", 1)),
    }


# ─────────────────────────────────────────────────────────────
#  RENDER HELPERS
# ─────────────────────────────────────────────────────────────

def _kpi_metric_row(items: list) -> None:
    """
    items = list of (label, value, delta, delta_color)
    delta_color = 'normal' | 'inverse' | 'off'
    """
    cols = st.columns(len(items))
    for col, (lbl, val, delta, dc) in zip(cols, items):
        with col:
            st.metric(label=lbl, value=val, delta=delta, delta_color=dc)


def _debut_table_html(df: pd.DataFrame, score_col: str = "total_streams", max_rows: int = 34) -> str:
    """
    Render an HTML debut table with rank, title/artist, score bar,
    badge (HOT / MULTI / NEW), and score value.
    """
    if df.empty:
        return "<p style='color:var(--text2);font-size:12px'>No debut data available.</p>"

    max_score = df[score_col].max() if score_col in df.columns else 1

    header = """
    <div style="display:grid;grid-template-columns:80px 1.8fr 1.2fr 1fr 100px 80px;
                gap:12px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:4px;">
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Rank</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Track Title</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Artist</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Label</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:right">Score</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:right">Signal</span>
    </div>"""

    rows_html = ""
    for _, row in df.head(max_rows).iterrows():
        rank         = int(row.get("rank", 0))
        artist_title = str(row.get("artist_title", ""))
        parts        = artist_title.split(" - ", 1)
        artist       = parts[0].strip()
        title        = parts[1].strip() if len(parts) > 1 else artist_title
        label        = str(row.get("label", "")).strip()
        label_display = label if label and label.lower() != "nan" else "—"
        score        = row.get(score_col, 0) or 0
        pct          = round(float(score) / max(float(max_score), 1) * 100)

        if score >= max_score * 0.6:
            bar_color, badge = "#22c55e", '<span class="badge-hot" style="font-size:9px">TOP DEBUT</span>'
        elif score >= max_score * 0.3:
            bar_color, badge = "#a78bfa", '<span class="badge-multi" style="font-size:9px">RISING</span>'
        else:
            bar_color, badge = "#555", '<span class="badge-new" style="font-size:9px">NEW ENTRY</span>'

        rows_html += f"""
        <div class="rank-row"
             style="grid-template-columns:80px 1.8fr 1.2fr 1fr 100px 80px; padding: 12px 10px;">
          <span style="font-size:15px;font-weight:700;color:var(--text)">
            #{rank}
          </span>
          <div>
            <div style="font-size:15px;font-weight:700;color:var(--text);
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:6px">{title}</div>
            <div class="sbar-bg" style="height:5px">
              <div class="sbar-fg" style="width:{pct}%;background:{bar_color}"></div>
            </div>
          </div>
          <div style="font-size:13px;color:var(--text2);white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis">{artist}</div>
          <div style="font-size:12px;color:var(--accent2);white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis">{label_display}</div>
          <span style="font-size:15px;font-weight:700;color:var(--text);text-align:right">{fmt(score)}</span>
          <span style="text-align:right">{badge}</span>
        </div>"""

    return header + rows_html


def _itunes_debut_table_html(df: pd.DataFrame, max_rows: int = 15) -> str:
    """Render iTunes WW debut table."""
    if df.empty:
        return "<p style='color:var(--text2);font-size:12px'>No iTunes debut data available.</p>"

    header = """
    <div style="display:grid;grid-template-columns:80px 1.8fr 1.5fr 1fr 100px 80px;
                gap:12px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:4px;">
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Rank</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Track Title</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Artist</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Label</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:right">Points</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:right">Peak</span>
    </div>"""

    rows_html = ""
    for _, row in df.head(max_rows).iterrows():
        rank  = int(row.get("best_rank", 0))
        title = str(row.get("title", row.get("track_name", "—")))
        artist= str(row.get("artist", "—"))
        label = str(row.get("label", "")).strip()
        label_display = label if label and label.lower() != "nan" else "—"
        score = row.get("total_score", 0) or 0
        peak  = int(row.get("peak_position", 0)) if not pd.isna(row.get("peak_position", np.nan)) else 0

        is_old_catalog = peak > 100
        peak_color     = "#fbbf24" if is_old_catalog else "var(--text2)"

        rows_html += f"""
        <div class="rank-row"
             style="grid-template-columns:80px 1.8fr 1.5fr 1fr 100px 80px; padding: 12px 10px;">
          <span style="font-size:15px;font-weight:700;color:var(--text)">
            #{rank}
          </span>
          <div style="font-size:15px;font-weight:700;color:var(--text);
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{title}</div>
          <div style="font-size:13px;color:var(--text2);white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis">{artist}</div>
          <div style="font-size:12px;color:var(--accent2);white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis">{label_display}</div>
          <span style="font-size:15px;font-weight:700;color:var(--text);text-align:right">{fmt(score)}</span>
          <span style="font-size:13px;color:{peak_color};text-align:right;font-weight:600">pk#{peak}</span>
        </div>"""

    return header + rows_html


def _multi_track_html(multi_df: pd.DataFrame, debut_df: pd.DataFrame) -> str:
    """HTML table listing multi-track debutants with their individual scores."""
    if multi_df.empty:
        return "<p style='color:var(--text2);font-size:12px'>No multi-track debutants.</p>"

    header = """
    <div style="display:grid;grid-template-columns:2fr 100px 140px 2fr;
                gap:12px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:4px;">
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Artist</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Tracks</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:right">Combined Score</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;padding-left:15px">Breakdown (Rank & Score)</span>
    </div>"""

    rows_html = ""
    for _, row in multi_df.iterrows():
        artist      = str(row["artist_title"])
        track_count = int(row["track_count"])
        combined    = int(row["combined_score"])

        # individual track scores
        indiv = (
            debut_df[debut_df["artist_title"] == artist]
            .sort_values("rank")[["rank", "total_streams"]]
        )
        scores_txt = " &nbsp;·&nbsp; ".join(
            f'<span style="color:var(--text2)">#{int(r["rank"])}</span> <span style="color:var(--accent)">{fmt(r["total_streams"])}</span>' 
            for _, r in indiv.iterrows()
        )

        rows_html += f"""
        <div class="rank-row"
             style="grid-template-columns:2fr 100px 140px 2fr; padding: 14px 10px;">
          <span style="font-size:15px;font-weight:700;color:var(--text)">{artist}</span>
          <div style="text-align:center">
            <span class="badge-multi" style="font-size:10px; padding:4px 10px">{track_count} TRACKS</span>
          </div>
          <span style="font-size:15px;font-weight:700;color:var(--accent2);text-align:right">{fmt(combined)}</span>
          <div style="font-size:13px;padding-left:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
            {scores_txt}
          </div>
        </div>"""

    return header + rows_html


def _new_trending_html(df: pd.DataFrame) -> str:
    """Compact ranked list of new-to-trending artists."""
    if df.empty:
        return "<p style='color:var(--text2);font-size:12px'>No new trending artists data.</p>"

    max_score = df["total_score"].max()
    palette   = ["#a78bfa","#60a5fa","#2dd4bf","#fbbf24","#f472b6",
                 "#34d399","#fb923c","#e879f9","#94a3b8","#f87171"]
    html = ""
    for i, row in df.iterrows():
        name    = str(row["artist_name"])
        score   = row.get("total_score", 0) or 0
        ctries  = int(row.get("countries", 0))
        pct     = round(float(score) / max(float(max_score), 1) * 100)
        color   = palette[i % len(palette)]
        html += f"""
        <div style="display:flex;align-items:center;gap:8px;
                    padding:5px 0;border-bottom:1px solid var(--border)">
          <span style="font-size:10px;color:var(--text2);min-width:16px">{i+1}</span>
          <div style="flex:1">
            <div style="font-size:12px;color:var(--text)">{name}</div>
            <div class="sbar-bg">
              <div class="sbar-fg" style="width:{pct}%;background:{color}"></div>
            </div>
          </div>
          <span style="font-size:10px;color:var(--text2)">{ctries} countries</span>
          <span style="font-size:11px;font-weight:600;color:{color}">{fmt(score)}</span>
        </div>"""
    return html


def _itunes_artist_new_entries_table_html(df: pd.DataFrame) -> str:
    """Render a table for the latest iTunes artist new entries."""
    if df.empty:
        return "<p style='color:var(--text2);font-size:12px'>No recent NEW entries found in iTunes artist rankings.</p>"

    header = """
    <div style="display:grid;grid-template-columns:80px 1.5fr 1fr 120px 120px;
                gap:12px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:4px;">
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Rank</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Artist</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700">Change</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:right">Points</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:right">Date</span>
    </div>"""

    rows_html = ""
    for _, row in df.iterrows():
        rank = int(row.get("rank", 0))
        artist = str(row.get("artist_name", "—"))
        change = str(row.get("rank_change", "—"))
        points = row.get("total_points", 0) or 0
        date = row.get("scrape_date")
        date_str = date.strftime("%b %d") if date else "—"

        rows_html += f"""
        <div class="rank-row"
             style="grid-template-columns:80px 1.5fr 1fr 120px 120px; padding: 10px 10px;">
          <span style="font-size:15px;font-weight:700;color:var(--text)">#{rank}</span>
          <div style="font-size:15px;font-weight:700;color:var(--text);
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{artist}</div>
          <div><span class="badge-new">{change}</span></div>
          <span style="font-size:15px;font-weight:700;color:var(--text);text-align:right">{fmt(points)}</span>
          <span style="font-size:13px;color:var(--text2);text-align:right">{date_str}</span>
        </div>"""

    return header + rows_html


# ─────────────────────────────────────────────────────────────
#  CHARTS
# ─────────────────────────────────────────────────────────────

def _chart_rank_bucket(bucket_df: pd.DataFrame) -> None:
    """Bar chart: debut count per rank bucket."""
    if bucket_df.empty:
        st.info("No bucket data.")
        return

    colors = [
        "#22c55e" if row["start"] <= 50 else
        "#60a5fa" if row["start"] <= 100 else
        "#a78bfa" if row["start"] <= 150 else
        "#555"
        for _, row in bucket_df.iterrows()
    ]

    fig = go.Figure(go.Bar(
        x=bucket_df["bucket"],
        y=bucket_df["count"],
        marker_color=colors,
        marker_line_width=0,
    ))
    fig.update_layout(
        xaxis=dict(tickfont=dict(color="#555", size=10)),
        yaxis=dict(tickfont=dict(color="#555", size=10), dtick=2),
    )
    _plotly(fig, height=180)


def _chart_score_distribution(debut_df: pd.DataFrame, score_col: str = "total_streams") -> None:
    """Line chart: score curve by debut rank."""
    if debut_df.empty or score_col not in debut_df.columns:
        st.info("No score data.")
        return

    df = debut_df.sort_values("rank")
    fig = go.Figure(go.Scatter(
        x=df["rank"],
        y=df[score_col],
        mode="lines+markers",
        line=dict(color="#60a5fa", width=1.5),
        marker=dict(color="#60a5fa", size=4),
        fill="tozeroy",
        fillcolor="rgba(96,165,250,0.08)",
        hovertemplate="Rank #%{x}<br>Score: %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(title="Rank", tickfont=dict(color="#555", size=10)),
        yaxis=dict(tickfont=dict(color="#555", size=10), tickformat=","),
    )
    _plotly(fig, height=160)




# ─────────────────────────────────────────────────────────────
#  MAIN RENDER
# ─────────────────────────────────────────────────────────────

def render_debut_tab() -> None:
    """
    Main entry point for the Debut Intelligence Dashboard tab.
    """
    # Inject CSS
    st.markdown(DEBUT_CSS, unsafe_allow_html=True)

    # ── Load data ──────────────────────────────────────────
    debut_df   = get_debut_tracks()
    all_df     = get_all_chart_tracks()
    itunes_df  = get_itunes_debuts()
    trending_df= get_new_trending_artists()
    itunes_artist_new_df = get_itunes_artist_new_entries(10)

    kpis       = get_debut_kpis(debut_df, all_df)
    multi_df   = get_multi_track_debutants(debut_df)
    bucket_df  = get_debut_rank_buckets(debut_df)
    spotlight  = get_acquisition_spotlight(debut_df)

    monday     = datetime.now() - timedelta(days=datetime.now().weekday())
    week_num   = monday.strftime("%W")

    # ── Page header ────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:var(--surface2);border-bottom:1px solid var(--border);
                    padding:14px 20px 10px;margin-bottom:1.5rem;border-radius:18px;box-shadow:0 18px 36px rgba(0,0,0,.12);">
          <div style="font-size:0.8rem;color:var(--text2);letter-spacing:0.1em;
                      text-transform:uppercase;margin-bottom:0.5rem;
                      display:flex;align-items:center;gap:8px">
            <span style="width:8px;height:8px;border-radius:50%;
                         background:var(--accent3);display:inline-block;box-shadow:0 0 10px var(--accent3)"></span>
         &nbsp;·&nbsp; Debut Intelligence
          </div>
          <div style="font-size:2.2rem;font-weight:800;letter-spacing:-0.03em;color:var(--text);
                      margin-bottom:0.25rem">Chart Debuts Report</div>
          <div style="font-size:1rem;color:var(--text2);letter-spacing:0.02em;
                      text-transform:uppercase">
            Spotify Global + iTunes WW &nbsp;·&nbsp;
            New entries vs prior week &nbsp;·&nbsp; May 2026
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPI metric bar ─────────────────────────────────────
    _kpi_metric_row([
        ("New entries",      str(kpis.get("total", 0)),
         f"{kpis.get('churn_pct', 0):.1f}% of chart this week", "off"),
        ("Best debut rank",  f"#{kpis.get('best_rank', 0)}",
         kpis.get("best_track", "—")[:30], "off"),
        ("Avg debut rank",   f"#{kpis.get('avg_rank', 0)}",
         "vs incumbent avg rank", "off"),
        ("Avg debut score",  fmt(kpis.get("avg_score", 0)),
         f"median {fmt(kpis.get('median_score', 0))}", "off"),
        ("Strength vs field",f"{kpis.get('strength_ratio', 0):.2f}×",
         "debut / incumbent score ratio", "off"),
    ])

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Insight cards ──────────────────────────────────────
    best_track   = kpis.get("best_track", "—")
    best_rank    = kpis.get("best_rank", 0)
    multi_artist = multi_df.iloc[0]["artist_title"] if not multi_df.empty else "—"
    multi_count  = int(multi_df.iloc[0]["track_count"]) if not multi_df.empty else 0
    sp_count     = len(itunes_df) if not itunes_df.empty else 0

    st.markdown(
        f"""
        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:1.25rem; margin-bottom:1.5rem;">
          <div class="insight-card">
            <div class="insight-icon">⚡</div>
            <div class="insight-title">Strongest debut</div>
            <div class="insight-val">{best_track[:28]} at #{best_rank}</div>
            <div class="insight-desc">
              Entry score {fmt(kpis.get("best_debut_score",0))} —
              Highest new entry of the week.
            </div>
          </div>
          <div class="insight-card">
            <div class="insight-icon">🎵</div>
            <div class="insight-title">Multi-track debutant</div>
            <div class="insight-val">{multi_artist} — {multi_count} entries</div>
            <div class="insight-desc">
              {multi_artist} placed {multi_count} tracks simultaneously this week,
              the largest single-artist debut footprint in the chart.
            </div>
          </div>
          <div class="insight-card">
            <div class="insight-icon">🌐</div>
            <div class="insight-title">iTunes WW debuts</div>
            <div class="insight-val">{sp_count} new tracks</div>
            <div class="insight-desc">
              {sp_count} tracks entered the iTunes WW chart this week.
              Catalogue re-entries flagged by historical peak rank.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Row 0: Latest iTunes Artist New Entries ─────────
    if not itunes_artist_new_df.empty:
        _sec("Top 10 Latest New Entry - Last Week", "iTunes Artist Ranking")
        iar_new_html = _itunes_artist_new_entries_table_html(itunes_artist_new_df)
        st.markdown(
            f'<div style="max-height:400px;overflow-y:auto;padding-right:10px;margin-bottom:2rem;border:1px solid var(--border);border-radius:12px;background:var(--surface2)">{iar_new_html}</div>',
            unsafe_allow_html=True,
        )

    # ── Row 1: Full-width Debut Table ─────────
    _sec(
        f"All {kpis.get('total', 0)} debuts — ranked by entry strength",
        "Spotify Global",
    )
    debut_html = _debut_table_html(debut_df, score_col="total_streams")
    st.markdown(
        f'<div style="max-height:500px;overflow-y:auto;padding-right:10px;margin-bottom:2rem;">{debut_html}</div>',
        unsafe_allow_html=True,
    )

    # ── Row 2: Charts ───────────────
    # chart_col1, chart_col2 = st.columns([1, 1], gap="medium")
    # with chart_col1:
    #     _sec("Debuts by rank bucket")
    #     _chart_rank_bucket(bucket_df)

    # with chart_col2:
    #     _sec("Entry score curve")
    #     _chart_score_distribution(debut_df, score_col="total_streams")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Row 3: Full-width iTunes Table ─────────
    _sec("iTunes WW new entries", f"{len(itunes_df)} debuts · Latest date")
    itunes_html = _itunes_debut_table_html(itunes_df, max_rows=15)
    st.markdown(
        f'<div style="max-height:450px;overflow-y:auto;padding-right:10px;margin-bottom:2rem;">{itunes_html}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Row 4: Spotlight & Signal (Side-by-side) ───────────────
    col_c, col_d = st.columns([1, 1], gap="medium")
    with col_c:
        # Strongest Debut (Spotlight)
        if spotlight:
            ratio = round(spotlight.get("total_streams", 0) / max(kpis.get("avg_score", 1), 1), 1)
            st.markdown(
                f"""
                <div class="spotlight-card" style="padding:0.75rem 1rem; margin-bottom:0.5rem; height:150px; display:flex; flex-direction:column; justify-content:center;">
                  <div class="sp-rank">
                    <span class="badge-hot" style="font-size:9px">STRONGEST DEBUT</span>
                  </div>
                  <div style="font-size:1.3rem; font-weight:900; color:var(--text); margin-bottom:2px">
                    {spotlight.get("artist_title","—")}
                  </div>
                  <div style="font-size:0.85rem; color:var(--text2); margin-bottom:8px">
                    {spotlight.get("label","Independent")} &nbsp;·&nbsp; #{spotlight.get("rank",0)} entry
                  </div>
                  <div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.5rem;">
                    <div class="sp-stat" style="padding:4px 0">
                      <div class="sp-lbl" style="font-size:10px">Entry score</div>
                      <div class="sp-val" style="color:var(--accent3); font-size:1.1rem">{fmt(spotlight.get("total_streams",0))}</div>
                    </div>
                    <div class="sp-stat" style="padding:4px 0">
                      <div class="sp-lbl" style="font-size:10px">vs debut avg</div>
                      <div class="sp-val" style="color:#fbbf24; font-size:1.1rem">{ratio}×</div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_d:
        # Acquisition signal card
        if spotlight:
            st.markdown(
                f"""
                <div class="mini-stat-card" style="border-left:3px solid var(--accent3); padding:0.75rem 1rem; margin-bottom:0.5rem; height:150px; display:flex; flex-direction:column; justify-content:center;">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                    <div class="mini-lbl" style="font-size:10px">Acquisition signal</div>
                    <span class="badge-hot" style="font-size:8px">A&R PRIORITY</span>
                  </div>
                  <div style="font-size:1.1rem;font-weight:800;color:var(--text);margin-bottom:2px">
                    {spotlight.get("artist_title","—")}
                  </div>
                  <div style="font-size:0.85rem;color:var(--text2);margin-bottom:8px">
                    Recommend prioritized follow-up on retention and territory growth.
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Row 5: Multi-track debutants ──────────────
    _sec("Multi-track debutants this week", f"{len(multi_df)} artists")
    multi_html = _multi_track_html(multi_df, debut_df)
    st.markdown(f'<div class="scroll-area" style="max-height:400px; margin-bottom:2rem;">{multi_html}</div>', unsafe_allow_html=True)



# ─────────────────────────────────────────────────────────────
#  STANDALONE ENTRY POINT
# ─────────────────────────────────────────────────────────────

def render_debut_dashboard() -> None:
    """
    Standalone page wrapper — use this if this file is the
    top-level page rather than a tab inside a parent app.
    """
    st.set_page_config(
        page_title="Debut Intelligence · Chromadata",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    render_debut_tab()


__all__ = ["render_debut_tab", "render_debut_dashboard"]