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
/* ── design tokens (scoped) ── */
:root {
    --db-bg:    #0d1117;
    --db-bg2:   #161b26;
    --db-bg3:   #1f2633;
    --db-bg4:   #283041;
    --db-line:  rgba(148,163,184,.15);
    --db-t1:    #ffffff;
    --db-t2:    #cdd6e4;
    --db-t3:    #8b95ad;
    --db-blue:  #60a5fa;
    --db-green: #34d399;
    --db-red:   #fb7185;
    --db-purple:#c4b5fd;
    --db-amber: #fcd34d;
    --db-teal:  #5eead4;
    --db-pink:  #f9a8d4;
    /* legacy aliases used elsewhere in this file */
    --surface2: var(--db-bg2);
    --border:   var(--db-line);
    --text:     var(--db-t1);
    --text2:    var(--db-t2);
    --accent:   var(--db-blue);
    --accent2:  var(--db-purple);
    --accent3:  var(--db-green);
}

/* ── base ── */
.block-container { padding-top: 1.25rem !important; }
hr { margin: 1.25rem 0 !important; border: none !important; border-top: 1px solid var(--db-line) !important; opacity: 1; }

/* ── tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    gap: 10px;
    border-bottom: 1px solid var(--db-line) !important;
    background: transparent;
}
[data-testid="stTabs"] [role="tab"] {
    background: var(--db-bg2) !important;
    color: var(--db-t2) !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: .04em !important;
    border: 1px solid var(--db-line) !important;
    border-radius: 12px 12px 0 0 !important;
    padding: 11px 22px !important;
    transition: all 0.25s ease;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: var(--db-t1) !important;
    background: linear-gradient(135deg, rgba(96,165,250,.22), rgba(196,181,253,.22)) !important;
    border-color: rgba(96,165,250,.55) !important;
}

/* ── hero header ── */
.db-hero {
    position: relative;
    background: linear-gradient(135deg, #1a2238 0%, #1f1a3a 50%, #261d3d 100%);
    border: 1px solid rgba(148,163,184,.18);
    border-radius: 20px;
    padding: 26px 30px;
    margin-bottom: 1.6rem;
    margin-top: 1.5rem;
    box-shadow: 0 24px 60px rgba(0,0,0,.35);
    overflow: hidden;
}
.db-hero::after {
    content: "";
    position: absolute; right: -120px; top: -120px;
    width: 320px; height: 320px;
    background: radial-gradient(circle, rgba(196,181,253,.18), transparent 60%);
    pointer-events: none;
}
.db-hero-eyebrow {
    display: inline-flex; align-items: center; gap: 10px;
    font-size: 12px; font-weight: 800; letter-spacing: .18em;
    text-transform: uppercase; color: var(--db-t3);
    margin-bottom: 14px;
}
.db-hero-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--db-green);
    box-shadow: 0 0 0 4px rgba(52,211,153,.18), 0 0 14px rgba(52,211,153,.55);
    animation: db-pulse 2s ease-in-out infinite;
}
@keyframes db-pulse {
    0%,100% { box-shadow: 0 0 0 4px rgba(52,211,153,.18), 0 0 14px rgba(52,211,153,.55); }
    50%     { box-shadow: 0 0 0 8px rgba(52,211,153,.05), 0 0 22px rgba(52,211,153,.85); }
}
.db-hero-title {
    font-size: 2.4rem; font-weight: 900; letter-spacing: -.02em;
    color: var(--db-t1); margin-bottom: 8px; line-height: 1.1;
}
.db-hero-sub {
    font-size: 0.95rem; color: var(--db-t2); font-weight: 500;
    letter-spacing: .02em;
}
.db-hero-sub b { color: var(--db-t1); font-weight: 700; }

/* ── KPI tiles ── */
.db-kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin-top: 1.5rem;
    margin-bottom: 1.5rem;
}
.db-kpi {
    position: relative;
    background: var(--db-bg2);
    border: 1px solid var(--db-line);
    border-radius: 16px;
    padding: 18px 18px 16px 22px;
    box-shadow: 0 12px 24px rgba(0,0,0,.18);
    overflow: hidden;
    transition: transform .2s ease, border-color .2s ease;
}
.db-kpi:hover { transform: translateY(-2px); border-color: rgba(148,163,184,.3); }
.db-kpi::before {
    content: ""; position: absolute; left: 0; top: 14%; bottom: 14%; width: 4px;
    border-radius: 0 4px 4px 0;
    background: var(--db-blue);
}
.db-kpi.k-blue::before   { background: var(--db-blue); }
.db-kpi.k-green::before  { background: var(--db-green); }
.db-kpi.k-purple::before { background: var(--db-purple); }
.db-kpi.k-amber::before  { background: var(--db-amber); }
.db-kpi.k-pink::before   { background: var(--db-pink); }
.db-kpi-lbl {
    font-size: 11px; font-weight: 800; letter-spacing: .12em;
    text-transform: uppercase; color: var(--db-t3);
    margin-bottom: 10px;
}
.db-kpi-val {
    font-size: 26px; font-weight: 900; color: var(--db-t1);
    line-height: 1.1; margin-bottom: 6px; letter-spacing: -.01em;
}
.db-kpi.k-blue   .db-kpi-val { color: var(--db-blue); }
.db-kpi.k-green  .db-kpi-val { color: var(--db-green); }
.db-kpi.k-purple .db-kpi-val { color: var(--db-purple); }
.db-kpi.k-amber  .db-kpi-val { color: var(--db-amber); }
.db-kpi.k-pink   .db-kpi-val { color: var(--db-pink); }
.db-kpi-sub {
    font-size: 12px; color: var(--db-t2); font-weight: 500;
    line-height: 1.35;
}

/* ── insight cards ── */
.insight-card, .spotlight-card, .mini-stat-card {
    position: relative;
    background:
      radial-gradient(circle at 88% -10%, rgba(96,165,250,.18) 0%, transparent 48%),
      linear-gradient(180deg, #171e2d 0%, #151b28 100%);
    border: 1px solid rgba(148,163,184,.22);
    border-radius: 18px;
    padding: 1.1rem 1.25rem 1.2rem;
    margin-bottom: 1rem;
    min-height: 204px;
    box-shadow: 0 16px 32px rgba(0,0,0,.24);
    overflow: hidden;
    transition: transform .24s ease, box-shadow .24s ease, border-color .24s ease;
}
.insight-card::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
    height: 3px;
    background: linear-gradient(90deg, var(--db-blue), rgba(196,181,253,.85));
}
.insight-card:hover {
    transform: translateY(-3px);
    border-color: rgba(96,165,250,.52);
    box-shadow: 0 24px 44px rgba(0,0,0,.36);
}
.insight-icon {
    width: 2.2rem;
    height: 2.2rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    font-size: 1.15rem;
    margin-bottom: 0.72rem;
    background: rgba(96,165,250,.14);
    border: 1px solid rgba(96,165,250,.26);
}
.insight-title {
    font-size: 11px;
    color: #9eabc4;
    font-weight: 800;
    letter-spacing: .12em;
    text-transform: uppercase;
    margin-bottom: 0.48rem;
}
.insight-val {
    font-size: clamp(1.12rem, 1.05vw + .78rem, 1.9rem);
    font-weight: 800;
    color: var(--db-t1);
    margin-bottom: 0.55rem;
    line-height: 1.28;
    letter-spacing: -.01em;
}
.insight-desc {
    font-size: 0.91rem;
    color: #c7d1e4;
    line-height: 1.58;
}

/* ── section headers ── */
.sec-hdr {
    display: flex; align-items: center; justify-content: space-between;
    margin: 0 0 14px 2px;
}
.sec-title {
    font-size: 1.1rem; font-weight: 800;
    color: var(--db-t1); letter-spacing: -.005em;
}
.sec-badge {
    font-size: 11px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: var(--db-t2);
    background: var(--db-bg3); border: 1px solid var(--db-line);
    padding: 5px 12px; border-radius: 999px;
}

/* ── table container ── */
.db-tbl-wrap {
    background: var(--db-bg2);
    border: 1px solid var(--db-line);
    border-radius: 16px;
    padding: 4px 10px;
    margin-bottom: 1.6rem;
    box-shadow: 0 14px 30px rgba(0,0,0,.18);
    overflow: hidden;
}

/* ── tables & rows ── */
.rank-row {
    display: grid;
    align-items: center;
    gap: 14px;
    padding: 12px 10px;
    border-bottom: 1px solid var(--db-line);
    transition: background .15s ease;
}
.rank-row:last-child { border-bottom: none; }
.rank-row:hover { background: rgba(96,165,250,.06); }
.rank-pill {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 44px; padding: 6px 10px;
    background: var(--db-bg4); color: var(--db-t1);
    font-size: 14px; font-weight: 800;
    border-radius: 10px; letter-spacing: -.01em;
}
.rank-pill.top { background: linear-gradient(135deg, #34d399, #10b981); color: #0d1117; }
.rank-pill.mid { background: linear-gradient(135deg, #c4b5fd, #a78bfa); color: #0d1117; }
.sbar-bg { width: 100%; height: 6px; background: rgba(148,163,184,.12); border-radius: 4px; overflow: hidden; }
.sbar-fg { height: 100%; border-radius: 4px; }

/* ── spotlight enhancement ── */
.sp-name { font-size: 1.6rem; font-weight: 900; line-height: 1.2; margin-bottom: 0.5rem; color: var(--db-t1); }
.sp-artist { font-size: 0.95rem; color: var(--db-t2); margin-bottom: 1rem; }
.sp-stat { padding: 0.65rem 0.9rem; border-radius: 12px; background: var(--db-bg3); border: 1px solid var(--db-line); }
.sp-lbl { font-size: 11px; color: var(--db-t3); font-weight: 700; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 4px; }
.sp-val { font-size: 1.3rem; font-weight: 800; color: var(--db-t1); }

/* ── scroll area ── */
.scroll-area {
    max-height: 420px; overflow-y: auto; padding-right: 8px;
}
.scroll-area::-webkit-scrollbar,
.db-tbl-wrap::-webkit-scrollbar { width: 6px; }
.scroll-area::-webkit-scrollbar-track,
.db-tbl-wrap::-webkit-scrollbar-track { background: transparent; }
.scroll-area::-webkit-scrollbar-thumb,
.db-tbl-wrap::-webkit-scrollbar-thumb { background: var(--db-bg4); border-radius: 10px; }

/* ── badges ── */
.badge-new {
    background: rgba(96,165,250,.16); color: #bfdbfe;
    border: 1px solid rgba(96,165,250,.45);
    padding: 4px 10px; border-radius: 999px;
    font-size: 10px; font-weight: 800; letter-spacing: .08em;
}
.badge-hot {
    background: rgba(52,211,153,.16); color: #a7f3d0;
    border: 1px solid rgba(52,211,153,.45);
    padding: 4px 10px; border-radius: 999px;
    font-size: 10px; font-weight: 800; letter-spacing: .08em;
}
.badge-multi {
    background: rgba(196,181,253,.16); color: #ddd6fe;
    border: 1px solid rgba(196,181,253,.45);
    padding: 4px 10px; border-radius: 999px;
    font-size: 10px; font-weight: 800; letter-spacing: .08em;
}
.badge-rising {
    background: rgba(252,211,77,.16); color: #fde68a;
    border: 1px solid rgba(252,211,77,.45);
    padding: 4px 10px; border-radius: 999px;
    font-size: 10px; font-weight: 800; letter-spacing: .08em;
}
.col-hdr {
    font-size: 10.5px; color: var(--db-t3);
    text-transform: uppercase; letter-spacing: .14em;
    font-weight: 800;
}
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

@st.cache_data(ttl=300, show_spinner=False)
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
                        label,
                        MIN(rank)          AS best_rank,
                        SUM(streams)       AS total_streams,
                        COUNT(DISTINCT date) AS days_charted,
                        MAX(date)          AS last_seen
                    FROM spotify_daily
                    WHERE date BETWEEN %s AND %s
                      AND streams > 0
                      AND country = 'global'
                    GROUP BY artist_title, label
                ),
                prior_week AS (
                    SELECT DISTINCT artist_title, label
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
                      AND cw.label        = pw.label
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


@st.cache_data(ttl=300, show_spinner=False)
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
                        label,
                        MIN(rank)    AS best_rank,
                        SUM(points)  AS total_score,
                        MAX(peak)    AS peak_position,
                        MAX(date)    AS last_seen
                    FROM itunes_daily
                    WHERE date BETWEEN %s AND %s
                      AND country = 'ww'
                      AND points  > 0
                    GROUP BY artist_title, label
                ),
                prior_wk AS (
                    SELECT DISTINCT artist_title, label
                    FROM itunes_daily
                    WHERE date BETWEEN %s AND %s
                      AND country = 'ww'
                )
                SELECT cw.*
                FROM current_wk cw
                LEFT JOIN prior_wk pw
                       ON cw.artist_title = pw.artist_title
                      AND COALESCE(cw.label,'') = COALESCE(pw.label,'')
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

    if "artist_title" in debut_df.columns:
        total = debut_df["artist_title"].astype(str).apply(lambda x: x.split(" - ")[0].strip()).nunique()
        all_artists_count = all_df["artist_title"].astype(str).apply(lambda x: x.split(" - ")[0].strip()).nunique() if not all_df.empty else 1
    else:
        total = len(debut_df)
        all_artists_count = len(all_df) if not all_df.empty else 1

    best_rank    = int(debut_df["rank"].min()) if "rank" in debut_df.columns else 0
    avg_rank     = int(debut_df["rank"].mean()) if "rank" in debut_df.columns else 0
    avg_score    = int(debut_df["total_streams"].mean()) if "total_streams" in debut_df.columns else 0
    median_score = int(debut_df["total_streams"].median()) if "total_streams" in debut_df.columns else 0

    best_track = (
        debut_df.loc[debut_df["rank"].idxmin(), "artist_title"]
        if "artist_title" in debut_df.columns
        else "—"
    )

    churn    = round(total / max(all_artists_count, 1) * 100, 1) if not all_df.empty else 0.0

    incumbent_avg = (
        all_df[~all_df["artist_title"].isin(debut_df["artist_title"])]["total_streams"].mean()
        if "artist_title" in all_df.columns and not all_df.empty
        else 0
    )
    if pd.isna(incumbent_avg):
        incumbent_avg = 0
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


@st.cache_data(ttl=300, show_spinner=False)
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


@st.cache_data(ttl=300, show_spinner=False)
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


@st.cache_data(ttl=300, show_spinner=False)
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
                    label,
                    MIN(rank)          AS rank,
                    SUM(streams)       AS total_streams,
                    COUNT(DISTINCT date) AS days_charted
                FROM spotify_daily
                WHERE date BETWEEN %s AND %s
                  AND streams > 0
                  AND country = 'global'
                GROUP BY artist_title, label
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
    <div style="display:grid;grid-template-columns:80px 1.8fr 1.2fr 1fr 100px 110px;
                gap:12px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:4px;">
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Rank</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Track Title</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Artist</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Label</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Score</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Signal</span>
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
            bar_color, badge = "#34d399", '<span class="badge-hot">TOP DEBUT</span>'
        elif score >= max_score * 0.3:
            bar_color, badge = "#c4b5fd", '<span class="badge-rising">RISING</span>'
        else:
            bar_color, badge = "#60a5fa", '<span class="badge-new">NEW ENTRY</span>'

        pill_class = "top" if rank <= 25 else ("mid" if rank <= 100 else "")
        rows_html += f"""
        <div class="rank-row"
             style="grid-template-columns:80px 1.8fr 1.2fr 1fr 100px 110px;">
          <span class="rank-pill {pill_class}" style="justify-self:center">{rank}</span>
          <div>
            <div style="font-size:15px;font-weight:700;color:var(--db-t1);
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:6px;text-align:center">{title}</div>
            <div class="sbar-bg" style="margin: 0 auto; max-width: 90%;">
              <div class="sbar-fg" style="width:{pct}%;background:{bar_color}"></div>
            </div>
          </div>
          <div style="font-size:13px;color:var(--db-t2);white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis;text-align:center">{artist}</div>
          <div style="font-size:12px;color:var(--db-purple);font-weight:600;white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis;text-align:center">{label_display}</div>
          <span style="font-size:15px;font-weight:800;color:var(--db-t1);text-align:center">{fmt(score)}</span>
          <div style="display:flex;justify-content:center">{badge}</div>
        </div>"""

    return header + rows_html


def _itunes_debut_table_html(df: pd.DataFrame, max_rows: int = 15) -> str:
    """Render iTunes WW debut table."""
    if df.empty:
        return "<p style='color:var(--text2);font-size:12px'>No iTunes debut data available.</p>"

    header = """
    <div style="display:grid;grid-template-columns:80px 1.8fr 1.5fr 1fr 100px 80px;
                gap:12px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:4px;">
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Rank</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Track Title</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Artist</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Label</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Points</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Peak</span>
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
        peak_color     = "#fcd34d" if is_old_catalog else "var(--db-t2)"

        pill_class = "top" if rank <= 25 else ("mid" if rank <= 100 else "")
        rows_html += f"""
        <div class="rank-row"
             style="grid-template-columns:80px 1.8fr 1.5fr 1fr 100px 80px;">
          <span class="rank-pill {pill_class}" style="justify-self:center">{rank}</span>
          <div style="font-size:15px;font-weight:700;color:var(--db-t1);
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center">{title}</div>
          <div style="font-size:13px;color:var(--db-t2);white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis;text-align:center">{artist}</div>
          <div style="font-size:12px;color:var(--db-purple);font-weight:600;white-space:nowrap;
                      overflow:hidden;text-overflow:ellipsis;text-align:center">{label_display}</div>
          <span style="font-size:15px;font-weight:800;color:var(--db-t1);text-align:center">{fmt(score)}</span>
          <span style="font-size:13px;color:{peak_color};text-align:center;font-weight:700">pk#{peak}</span>
        </div>"""

    return header + rows_html


def _multi_track_html(multi_df: pd.DataFrame, debut_df: pd.DataFrame) -> str:
    """HTML table listing multi-track debutants with their individual scores."""
    if multi_df.empty:
        return "<p style='color:var(--text2);font-size:12px'>No multi-track debutants.</p>"

    header = """
    <div style="display:grid;grid-template-columns:2fr 110px 140px 2fr;
                gap:12px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:4px;">
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Artist</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Tracks</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Combined Score</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Breakdown (Rank & Score)</span>
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
            f'<span style="color:var(--db-t3);font-weight:700">#{int(r["rank"])}</span> <span style="color:var(--db-blue);font-weight:700">{fmt(r["total_streams"])}</span>'
            for _, r in indiv.iterrows()
        )

        rows_html += f"""
        <div class="rank-row"
             style="grid-template-columns:2fr 110px 140px 2fr;">
          <span style="font-size:15px;font-weight:800;color:var(--db-t1);text-align:center">{artist}</span>
          <div style="text-align:center">
            <span class="badge-multi">{track_count} TRACKS</span>
          </div>
          <span style="font-size:15px;font-weight:800;color:var(--db-purple);text-align:center">{fmt(combined)}</span>
          <div style="font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center">
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
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Rank</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Artist</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Change</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Points</span>
      <span style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;font-weight:700;text-align:center">Date</span>
    </div>"""

    rows_html = ""
    for _, row in df.iterrows():
        rank = int(row.get("rank", 0))
        artist = str(row.get("artist_name", "—"))
        change = str(row.get("rank_change", "—"))
        points = row.get("total_points", 0) or 0
        date = row.get("scrape_date")
        date_str = date.strftime("%b %d") if date else "—"

        pill_class = "top" if rank <= 25 else ("mid" if rank <= 100 else "")
        rows_html += f"""
        <div class="rank-row"
             style="grid-template-columns:80px 1.5fr 1fr 120px 120px;">
          <span class="rank-pill {pill_class}" style="justify-self:center">{rank}</span>
          <div style="font-size:15px;font-weight:700;color:var(--db-t1);
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center">{artist}</div>
          <div style="display:flex;justify-content:center"><span class="badge-new">{change}</span></div>
          <span style="font-size:15px;font-weight:800;color:var(--db-t1);text-align:center">{fmt(points)}</span>
          <span style="font-size:13px;color:var(--db-t2);text-align:center;font-weight:600">{date_str}</span>
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

def render_debut_tab(filtered_leaderboard: pd.DataFrame | None = None) -> None:
    """
    Main entry point for the Debut Intelligence Dashboard tab.
    If filtered_leaderboard is provided, debut data is filtered to only
    include artists present in the filtered leaderboard.
    """
    # Inject CSS
    st.markdown(DEBUT_CSS, unsafe_allow_html=True)

    # ── Load data ──────────────────────────────────────────
    debut_df   = get_debut_tracks()
    all_df     = get_all_chart_tracks()
    itunes_df  = get_itunes_debuts()
    trending_df= get_new_trending_artists()
    itunes_artist_new_df = get_itunes_artist_new_entries(10)

    # ── Apply country filter from sidebar ──────────────────
    if filtered_leaderboard is not None and not filtered_leaderboard.empty:
        allowed_artists = set(filtered_leaderboard["name"].dropna().str.lower().unique())

        def _artist_match(artist_title: str, allowed: set) -> bool:
            """Check if artist name from 'Artist - Track' format is in allowed set."""
            name = str(artist_title).split(" - ", 1)[0].strip().lower()
            return name in allowed

        if not debut_df.empty and "artist_title" in debut_df.columns:
            debut_df = debut_df[debut_df["artist_title"].apply(lambda x: _artist_match(x, allowed_artists))]

        if not all_df.empty and "artist_title" in all_df.columns:
            all_df = all_df[all_df["artist_title"].apply(lambda x: _artist_match(x, allowed_artists))]

        if not itunes_df.empty and "artist_title" in itunes_df.columns:
            itunes_df = itunes_df[itunes_df["artist_title"].apply(lambda x: _artist_match(x, allowed_artists))]

        if not itunes_artist_new_df.empty and "artist_name" in itunes_artist_new_df.columns:
            itunes_artist_new_df = itunes_artist_new_df[itunes_artist_new_df["artist_name"].str.lower().isin(allowed_artists)]

        if not trending_df.empty and "artist_name" in trending_df.columns:
            trending_df = trending_df[trending_df["artist_name"].str.lower().isin(allowed_artists)]

    kpis       = get_debut_kpis(debut_df, all_df)
    bucket_df  = get_debut_rank_buckets(debut_df)

    monday     = datetime.now() - timedelta(days=datetime.now().weekday())
    week_num   = monday.strftime("%W")


    # ── KPI tiles ─────────────────────────────────────────
    best_track_short = (kpis.get("best_track", "—") or "—")[:34]
    st.markdown(
        f"""
        <div class="db-kpi-grid">
          <div class="db-kpi k-blue">
            <div class="db-kpi-lbl">New entries</div>
            <div class="db-kpi-val">{kpis.get('total', 0)}</div>
            <div class="db-kpi-sub">{kpis.get('churn_pct', 0):.1f}% of chart this week</div>
          </div>
          <div class="db-kpi k-green">
            <div class="db-kpi-lbl">Best debut rank</div>
            <div class="db-kpi-val">{kpis.get('best_rank', 0)}</div>
            <div class="db-kpi-sub">{best_track_short}</div>
          </div>
          <div class="db-kpi k-purple">
            <div class="db-kpi-lbl">Avg debut rank</div>
            <div class="db-kpi-val">{kpis.get('avg_rank', 0)}</div>
            <div class="db-kpi-sub">across all new entries</div>
          </div>
          <div class="db-kpi k-amber">
            <div class="db-kpi-lbl">Avg debut score</div>
            <div class="db-kpi-val">{fmt(kpis.get('avg_score', 0))}</div>
            <div class="db-kpi-sub">median {fmt(kpis.get('median_score', 0))}</div>
          </div>
          <div class="db-kpi k-pink">
            <div class="db-kpi-lbl">Strength vs field</div>
            <div class="db-kpi-val">{kpis.get('strength_ratio', 0):.2f}×</div>
            <div class="db-kpi-sub">debut / incumbent ratio</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Row 0: Latest iTunes Artist New Entries ─────────
    if not itunes_artist_new_df.empty:
        _sec("Top 5 latest new entries — last week", "iTunes Artist Ranking")
        iar_new_html = _itunes_artist_new_entries_table_html(itunes_artist_new_df)
        st.markdown(
            f'<div class="db-tbl-wrap" style="max-height:420px;overflow-y:auto">{iar_new_html}</div>',
            unsafe_allow_html=True,
        )

    # ── Row 1: Full-width Debut Table ─────────
    _sec(
        f"All {kpis.get('total', 0)} debuts — ranked by entry strength",
        "Spotify Global",
    )
    debut_html = _debut_table_html(debut_df, score_col="total_streams")
    st.markdown(
        f'<div class="db-tbl-wrap" style="max-height:540px;overflow-y:auto">{debut_html}</div>',
        unsafe_allow_html=True,
    )


    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Row 3: Full-width iTunes Table ─────────
    _sec("iTunes WW new entries", f"{len(itunes_df)} debuts · latest date")
    itunes_html = _itunes_debut_table_html(itunes_df, max_rows=15)
    st.markdown(
        f'<div class="db-tbl-wrap" style="max-height:480px;overflow-y:auto">{itunes_html}</div>',
        unsafe_allow_html=True,
    )





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


def prefetch_debut_data() -> None:
    """Warms up the cache for the debut dashboard in the background."""
    try:
        get_debut_tracks()
        get_itunes_debuts()
        get_new_trending_artists()
        get_itunes_artist_new_entries(10)
        get_all_chart_tracks()
    except Exception as e:
        logger.error(f"Error prefetching debut data: {e}")


__all__ = ["render_debut_tab", "render_debut_dashboard", "prefetch_debut_data"]