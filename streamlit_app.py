from __future__ import annotations

from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.database.connection import get_connection
from src.scrapers.artist_details_scraper import LATIN_AMERICAN_COUNTRIES


st.set_page_config(
    page_title="Artist 360 Intelligence",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state for interactivity
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False
if "comparison_mode" not in st.session_state:
    st.session_state.comparison_mode = False
if "selected_artists" not in st.session_state:
    st.session_state.selected_artists = []
if "show_advanced" not in st.session_state:
    st.session_state.show_advanced = False

PAGE_META = {
    "Leaderboard": (
        "Artist 360 Leaderboard",
        "Top Latin artists ranked by iTunes performance, Spotify reach, and global footprint",
    ),
    "Chart Tracker": (
        "Chart Tracker",
        "Historical rank trajectories for top artists, revealing trends and momentum",
    ),
    "Stream Trends": (
        "Stream Trends",
        "Insights into streaming performance, growth patterns, and listener demographics",
    ),
    "Ops Monitor": (
        "Ops Monitor",
        "Operational dashboard showing recent data collection runs, their status, and performance metrics",
    ),
}

CHART_COLORS = ["#4f8ef7", "#22d3a0", "#f5a623", "#7c5cfc", "#e84545", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#a855f7"]
PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}
TRACKER_TOP_ARTISTS = 10
LATAM_COUNTRIES = sorted(LATIN_AMERICAN_COUNTRIES)


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg:#070b16; --surface:#12182a; --surface2:#1a2238; --surface3:#202947;
            --border:#293455; --accent:#4f8ef7; --accent2:#7c5cfc; --accent3:#22d3a0;
            --warn:#f5a623; --danger:#e84545; --text:#eef2ff; --text2:#97a3c5;
        }
        
        /* Smooth animations */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        @keyframes shimmer {
            0% { background-position: -1000px 0; }
            100% { background-position: 1000px 0; }
        }
        
        .stApp { 
            background:linear-gradient(180deg,#060a15 0%,#091127 100%); 
            color:var(--text);
            animation: fadeIn 0.6s ease-out;
        }
        [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, header { background:transparent !important; }
        [data-testid="stDecoration"] { display:none; }
        .block-container { padding-top:1rem; padding-bottom:2rem; max-width:1400px; }
        [data-testid="stSidebar"] {
            background:var(--surface); border-right:1px solid var(--border);
            animation: slideIn 0.4s ease-out;
        }
        [data-testid="stSidebarHeader"] {
            position: relative;
            min-height: 74px;
            padding: 1rem 3rem .9rem 1rem;
            border-bottom: 1px solid rgba(41,52,85,.7);
        }
        [data-testid="stSidebarHeader"]::before {
            content:"🎵";
            position:absolute; left:1rem; top:1rem;
            width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
            font-size:1.15rem; font-weight:900; color:#fff;
            background:linear-gradient(135deg, #4f8ef7 0%, #7c5cfc 55%, #22d3a0 100%);
            box-shadow:0 10px 24px rgba(79,142,247,.28);
        }
        [data-testid="stSidebarHeader"]::after {
            content:"Artist 360 Intelligence";
            position:absolute; left:4.25rem; top:1.35rem;
            right:3.25rem; color:var(--text); font-size:1.15rem; font-weight:800;
            letter-spacing:.2px; line-height:1.15;
        }
        [data-testid="stSidebarNav"] { padding-top:.6rem; }
        h1, h2, h3, h4, p, label, div, span { color:var(--text); }
        .brand-row { display:none; }
        .brand-logo {
            width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
            font-size:1.15rem; font-weight:900; color:#fff;
            background:linear-gradient(135deg, #4f8ef7 0%, #7c5cfc 55%, #22d3a0 100%);
            box-shadow:0 10px 24px rgba(79,142,247,.28);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .brand-logo:hover {
            transform: rotate(5deg) scale(1.1);
            box-shadow:0 15px 35px rgba(79,142,247,.4);
        }
        .sidebar-logo { font-size:1.2rem; font-weight:800; letter-spacing:.2px; line-height:1.15; }
        .sidebar-sub { color:var(--text2); font-size:.8rem; margin-top:.18rem; }
        .sidebar-badge {
            display:inline-block; margin-top:.45rem; padding:3px 8px; border-radius:999px;
            background:rgba(124,92,252,.18); color:#ddd6fe; font-size:.75rem; font-weight:700;
        }
        div[data-testid="stRadio"] > label { font-size:.82rem; font-weight:700; color:var(--text2) !important; }
        div[data-testid="stRadio"] [role="radiogroup"] label {
            background:transparent; border:1px solid transparent; border-radius:10px;
            padding:.35rem .45rem; margin:.1rem 0; transition:all .3s cubic-bezier(0.4, 0, 0.2, 1);
            cursor: pointer;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label:hover {
            background:rgba(79,142,247,.12); border-color:rgba(79,142,247,.25);
            transform: translateX(4px);
        }
        div[data-testid="stRadio"] [role="radiogroup"] label[data-checked="true"] {
            background:rgba(79,142,247,.18); border-color:rgba(79,142,247,.4);
        }
        div[data-testid="stRadio"] [role="radiogroup"] label > div:first-child {
            display:none !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label p {
            margin-left:0 !important; font-weight:600;
        }
        .page-title { font-size:2rem; font-weight:800; letter-spacing:-.03em; margin-bottom:.25rem; }
        .page-meta { color:var(--text2); font-size:.95rem; margin-bottom:1rem; }
        .dashboard-card {
            background:rgba(18,24,42,.96); border:1px solid var(--border); border-radius:16px;
            padding:1rem 1rem .9rem 1rem; box-shadow:0 12px 32px rgba(0,0,0,.22);
            margin-bottom:1rem; transition: all 0.3s ease;
            animation: fadeIn 0.7s ease-out;
        }
        .dashboard-card:hover {
            box-shadow:0 18px 42px rgba(0,0,0,.35);
            border-color: rgba(79,142,247,.3);
        }
        .section-title { 
            font-size:1rem; font-weight:700; margin-bottom:.2rem;
            display: flex; align-items: center; gap: 0.5rem;
        }
        .section-sub { color:var(--text2); font-size:.82rem; margin-bottom:.9rem; }
        
        /* Interactive buttons */
        .action-btn {
            display: inline-flex; align-items: center; gap: 0.5rem;
            padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.85rem;
            font-weight: 600; cursor: pointer; transition: all 0.3s ease;
            border: 1px solid var(--border); background: var(--surface2);
            color: var(--text); text-decoration: none;
        }
        .action-btn:hover {
            background: rgba(79,142,247,.15);
            border-color: var(--accent);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(79,142,247,.2);
        }
        .action-btn-primary {
            background: linear-gradient(135deg, #4f8ef7, #7c5cfc);
            border-color: transparent;
        }
        .action-btn-primary:hover {
            background: linear-gradient(135deg, #6fa3f9, #9175fd);
            box-shadow: 0 6px 20px rgba(79,142,247,.4);
        }
        .kpi-card {
            background:linear-gradient(180deg, rgba(19,26,45,1) 0%, rgba(16,21,37,1) 100%);
            border:1px solid var(--border); border-radius:14px; padding:1rem 1rem .9rem 1rem;
            min-height:110px; position:relative; overflow:hidden;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            animation: fadeIn 0.6s ease-out;
        }
        .kpi-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 28px rgba(79,142,247,.2);
            border-color: rgba(79,142,247,.4);
        }
        .kpi-card::before {
            content:''; position:absolute; top:0; left:0; right:0; height:3px;
            background:linear-gradient(90deg,var(--accent),var(--accent2));
            transition: height 0.3s ease;
        }
        .kpi-card:hover::before {
            height: 4px;
        }
        .kpi-green::before { background:linear-gradient(90deg,var(--accent3),#16a34a); }
        .kpi-amber::before { background:linear-gradient(90deg,var(--warn),#f97316); }
        .kpi-red::before { background:linear-gradient(90deg,var(--danger),#be123c); }
        .kpi-label { 
            color:var(--text2); font-size:.76rem; text-transform:uppercase; 
            letter-spacing:.08em; margin-bottom: 0.5rem;
        }
        .kpi-value { 
            font-size:2rem; font-weight:800; margin-top:.35rem;
            background: linear-gradient(135deg, #eef2ff 0%, #97a3c5 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .kpi-delta { color:var(--text2); font-size:.78rem; margin-top:.2rem; }
        
        /* Progress bars */
        .progress-bar {
            width: 100%; height: 6px; background: rgba(151,163,197,.15);
            border-radius: 999px; overflow: hidden; margin-top: 0.5rem;
        }
        .progress-fill {
            height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent3));
            border-radius: 999px; transition: width 1.5s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .table-wrap { overflow-x:auto; }
        table.leader-table { width:100%; border-collapse:collapse; font-size:.92rem; }
        .leader-table thead th {
            text-align:left; padding:.7rem .75rem; color:var(--text2); font-size:.73rem;
            letter-spacing:.06em; text-transform:uppercase; border-bottom:1px solid var(--border);
        }
        .leader-table tbody td {
            padding:.72rem .75rem; border-bottom:1px solid rgba(41,52,85,.72); vertical-align:middle;
        }
        .leader-table tbody tr:hover { 
            background:rgba(79,142,247,.10); 
            transform: scale(1.01);
            box-shadow: 0 4px 12px rgba(79,142,247,.15);
        }
        .leader-table tbody tr {
            transition: all 0.2s ease;
        }
        .pos-cell { color:#dbe4ff; font-weight:800; width:44px; }
        .artist-cell { font-weight:700; }
        .muted { color:var(--text2); }
        .num-cell { text-align:right; font-variant-numeric:tabular-nums; }
        .country-pill {
            display:inline-block; padding:2px 8px; border-radius:999px; background:rgba(34,211,160,.12);
            color:#8ff0cf; font-size:.75rem; font-weight:700;
        }
        .badge { 
            display:inline-block; padding:3px 8px; border-radius:999px; 
            font-size:.72rem; font-weight:800; transition: all 0.2s ease;
            cursor: default;
        }
        .badge:hover {
            transform: scale(1.1);
        }
        .badge-up { background:rgba(34,211,160,.14); color:#8ff0cf; }
        .badge-up:hover { background:rgba(34,211,160,.25); }
        .badge-dn { background:rgba(232,69,69,.14); color:#ff9c9c; }
        .badge-dn:hover { background:rgba(232,69,69,.25); }
        .badge-same { background:rgba(151,163,197,.14); color:#c4d0f3; }
        .badge-new { 
            background:rgba(79,142,247,.16); color:#b7d4ff;
            animation: pulse 2s infinite;
        }
        
        /* Tooltip styles */
        .tooltip {
            position: relative;
            display: inline-block;
        }
        .tooltip .tooltiptext {
            visibility: hidden;
            background-color: rgba(18,24,42,0.98);
            color: var(--text);
            text-align: center;
            border-radius: 8px;
            padding: 8px 12px;
            position: absolute;
            z-index: 1000;
            bottom: 125%;
            left: 50%;
            margin-left: -60px;
            opacity: 0;
            transition: opacity 0.3s;
            border: 1px solid var(--border);
            box-shadow: 0 8px 20px rgba(0,0,0,.4);
            font-size: 0.8rem;
        }
        .tooltip:hover .tooltiptext {
            visibility: visible;
            opacity: 1;
        }
        textarea, input, [data-baseweb="select"] > div {
            background:var(--surface2) !important; color:var(--text) !important; border-color:var(--border) !important;
        }
        div[data-testid="stMetric"] {
            background:transparent; border:none; padding:0; box-shadow:none;
        }
        div[data-testid="stMetric"] label { color:var(--text2) !important; }
        .status-good { color:#22c55e; font-weight:700; }
        .small-note { color:var(--text2); font-size:.82rem; }
        .run-log { display:flex; flex-direction:column; gap:.55rem; }
        .run-item {
            display:grid; grid-template-columns: 1.35fr 1fr .5fr .55fr; gap:.6rem;
            align-items:center; padding:.7rem .85rem; background:rgba(17,24,39,.55);
            border:1px solid rgba(41,52,85,.7); border-radius:10px; font-size:.84rem;
        }
        .run-date { color:var(--text); font-weight:600; }
        .run-source, .run-rows { color:var(--text2); }
        .run-dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:8px; }
        .dot-ok { background:#22c55e; }
        .dot-partial { background:#f5a623; }
        .dot-fail { background:#e84545; }
        .status-pill { 
            display:inline-block; padding:2px 8px; border-radius:999px; 
            font-size:.72rem; font-weight:700; transition: all 0.2s ease;
        }
        .pill-ok { background:rgba(34,197,94,.14); color:#8ff0cf; }
        .pill-ok:hover { background:rgba(34,197,94,.25); }
        .pill-partial { background:rgba(245,166,35,.14); color:#ffd089; }
        .pill-fail { background:rgba(232,69,69,.14); color:#ff9c9c; }
        
        /* Live indicator */
        .live-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 4px 10px;
            background: rgba(34,211,160,.12);
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 700;
            color: #8ff0cf;
        }
        .live-dot {
            width: 6px;
            height: 6px;
            background: #22d3a0;
            border-radius: 50%;
            animation: pulse 2s ease-in-out infinite;
        }
        
        /* Loading skeleton */
        .skeleton {
            background: linear-gradient(90deg, rgba(151,163,197,.1) 25%, rgba(151,163,197,.2) 50%, rgba(151,163,197,.1) 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
            border-radius: 8px;
        }
        
        /* Expandable section */
        .expandable {
            overflow: hidden;
            transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        /* Comparison mode highlight */
        .comparison-highlight {
            border: 2px solid var(--accent);
            background: rgba(79,142,247,.08);
            animation: pulse 1.5s ease-in-out 3;
        }
        
        /* Interactive tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background: transparent;
            border-bottom: none !important;
        }
        .stTabs [data-baseweb="tab-border"] {
            display: none !important;
        }
        .stTabs [data-baseweb="tab-highlight"] {
            display: none !important;
        }
        .stTabs {
            border-bottom: none !important;
        }
        .stTabs > div > div {
            border-bottom: none !important;
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            background: var(--surface2);
            border-radius: 10px;
            color: var(--text2);
            border: 1px solid var(--border);
            padding: 0.5rem 1.2rem;
            transition: all 0.3s ease;
            border-bottom: 1px solid var(--border) !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background: rgba(79,142,247,.12);
            border-color: rgba(79,142,247,.3);
            transform: translateY(-2px);
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(79,142,247,.2), rgba(124,92,252,.2));
            border-color: var(--accent);
            color: var(--text);
            border-bottom: 1px solid var(--accent) !important;
        }
        
        /* Buttons enhancement */
        .stButton button {
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-radius: 10px;
        }
        .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(79,142,247,.3);
        }
        
        /* Loading spinner */
        .stSpinner > div {
            border-color: var(--accent) transparent transparent transparent;
        }
        
        /* Toast notifications */
        .stToast {
            background: rgba(18,24,42,0.98) !important;
            border: 1px solid var(--accent) !important;
            border-radius: 12px !important;
        }
        
        /* Metric cards enhancement */
        [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 800 !important;
        }
        [data-testid="stMetricDelta"] {
            font-size: 0.85rem !important;
        }
        
        /* Expander animation */
        .streamlit-expanderHeader {
            transition: all 0.3s ease;
            border-radius: 8px;
        }
        .streamlit-expanderHeader:hover {
            background: rgba(79,142,247,.08);
        }
        
        /* Download button styling */
        .stDownloadButton button {
            background: linear-gradient(135deg, #22d3a0, #16a34a) !important;
            color: white !important;
            border: none !important;
        }
        .stDownloadButton button:hover {
            background: linear-gradient(135deg, #2ee4b0, #1fb556) !important;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(34,211,160,.4) !important;
        }
        
        /* Selectbox hover */
        [data-baseweb="select"]:hover {
            border-color: var(--accent) !important;
        }
        
        /* Text input focus */
        input:focus, textarea:focus {
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 1px var(--accent) !important;
        }
        
        /* Slider styling */
        .stSlider [role="slider"] {
            background: linear-gradient(135deg, #4f8ef7, #7c5cfc) !important;
        }
        
        /* Toggle switch */
        [data-testid="stCheckbox"] input[type="checkbox"]:checked + div {
            background: linear-gradient(135deg, #4f8ef7, #7c5cfc) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def fmt_short(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"


def trend_badge_html(value: str | None) -> str:
    token = str(value or "=").strip().upper()
    if token == "NEW":
        return '<span class="badge badge-new">NEW</span>'
    if token.startswith("+"):
        return f'<span class="badge badge-up">▲ {escape(token)}</span>'
    if token.startswith("-"):
        return f'<span class="badge badge-dn">▼ {escape(token[1:])}</span>'
    return '<span class="badge badge-same">—</span>'


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

    leaderboard = frames["itunes"].merge(
        frames["spotify"][["name", "monthly_listeners", "peak_listeners"]],
        on="name",
        how="left",
    ).merge(
        frames["details"][["name", "songs_count", "albums_count", "countries_count", "top_songs", "top_albums", "top_countries"]],
        on="name",
        how="left",
    )

    for col in ["monthly_listeners", "peak_listeners", "total_points", "countries_count"]:
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
    frames["leaderboard"] = leaderboard.sort_values("rank")
    return frames


def latest_source_rows(runs: pd.DataFrame) -> pd.DataFrame:
    if runs.empty:
        return runs
    ranked = runs.sort_values("finished_at", ascending=False)
    return ranked.drop_duplicates(subset=["source"], keep="first")


def style_figure(fig, height: int) -> None:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor="rgba(18,24,42,1)",
        plot_bgcolor="rgba(18,24,42,1)",
        font=dict(color="#e8eaf6"),
        legend_title_text="",
    )
    fig.update_xaxes(gridcolor="rgba(151,163,197,.12)", zerolinecolor="rgba(151,163,197,.12)")
    fig.update_yaxes(gridcolor="rgba(151,163,197,.12)", zerolinecolor="rgba(151,163,197,.12)")


def render_header(title: str, meta: str, last_run_label: str) -> None:
    st.markdown(
        f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
            <div>
                <div class='page-title' style='animation: slideIn 0.5s ease-out;'>{escape(title)}</div>
                <div class='page-meta'>{escape(meta)}</div>
            </div>
            <div class="live-indicator">
                <span class="live-dot"></span>
                LIVE
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(leaderboard: pd.DataFrame, runs: pd.DataFrame) -> None:
    success_rate = (runs["status"].eq("success").mean() * 100) if not runs.empty else 0
    total_monthly = leaderboard["monthly_listeners"].fillna(0).sum()
    latam_artists = int(leaderboard["latam_signal"].sum()) if "latam_signal" in leaderboard else 0
    new_entries = int(leaderboard["rank_change"].fillna("").eq("NEW").sum())
    tracked_jobs = int(runs["source"].nunique()) if not runs.empty else 0

    # Calculate progress percentages
    max_listeners = 100_000_000  # Adjust based on your data
    listener_progress = min(100, (total_monthly / max_listeners * 100))
    artist_progress = min(100, (latam_artists / len(leaderboard) * 100)) if len(leaderboard) > 0 else 0

    cards = [
        ("Total Monthly Listeners", fmt_short(total_monthly), "Live Spotify monthly listener sum", "", listener_progress),
        ("Artists with LATAM Signals", str(latam_artists), "Currently visible in the regional cut", "kpi-green", artist_progress),
        ("New Chart Entries", str(new_entries), "Fresh NEW movements in the latest run", "kpi-amber", 0),
        ("Jobs Tracked", str(tracked_jobs), f"Pipeline success rate {success_rate:.0f}%", "kpi-red", success_rate),
    ]
    cols = st.columns(4)
    for col, (label, value, delta, klass, progress) in zip(cols, cards):
        progress_html = f'<div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>' if progress > 0 else ''
        col.markdown(
            f"""
            <div class="kpi-card {klass}">
                <div class="kpi-label">{escape(label)}</div>
                <div class="kpi-value">{escape(value)}</div>
                <div class="kpi-delta">{escape(delta)}</div>
                {progress_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


def prepare_leaderboard_table(leaderboard: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    table_df = leaderboard.head(max_rows)[
        [
            "rank",
            "name",
            "top_song",
            "display_country",
            "monthly_listeners",
            "peak_listeners",
            "rank_change",
        ]
    ].copy()
    table_df["rank_change"] = table_df["rank_change"].fillna("=").replace("", "=")
    table_df.columns = [
        "#",
        "Artist",
        "Top Song",
        "Top Country",
        "Monthly Listeners",
        "Peak Listeners",
        "Trend",
    ]
    return table_df


def render_leaderboard(leaderboard: pd.DataFrame, runs: pd.DataFrame, max_rows: int) -> None:
    if leaderboard.empty:
        st.warning("No leaderboard data available yet. Run the scraper first.")
        return

    render_kpis(leaderboard, runs)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Add action buttons row - left aligned
    btn_col1, btn_col2, btn_col3, spacer = st.columns([1, 1, 1, 6])
    with btn_col1:
        if st.button("📊 Compare", use_container_width=True, key="compare_btn"):
            st.session_state.comparison_mode = not st.session_state.comparison_mode
    with btn_col2:
        csv = leaderboard.head(max_rows).to_csv(index=False)
        st.download_button(
            label="⬇️ Download",
            data=csv,
            file_name="artist_leaderboard.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_csv_btn"
        )
    with btn_col3:
        if st.button("🔄 " + ("ON" if st.session_state.auto_refresh else "OFF"), 
                     use_container_width=True, 
                     type="primary" if st.session_state.auto_refresh else "secondary",
                     key="auto_refresh_btn"):
            st.session_state.auto_refresh = not st.session_state.auto_refresh
            st.rerun()
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Comparison Mode
    if st.session_state.comparison_mode:
        st.markdown("### 🔄 Artist Comparison Mode")
        st.info("Select 2-4 artists to compare their metrics side by side")
        
        available_artists = leaderboard["name"].dropna().tolist()[:20]  # Limit to top 20 for performance
        selected_for_comparison = st.multiselect(
            "Select artists to compare",
            available_artists,
            default=available_artists[:2] if len(available_artists) >= 2 else available_artists,
            max_selections=4,
            key="comparison_artists"
        )
        
        if len(selected_for_comparison) >= 2:
            comparison_data = leaderboard[leaderboard["name"].isin(selected_for_comparison)].copy()
            
            # Comparison metrics
            comp_cols = st.columns(len(selected_for_comparison))
            for idx, (col, artist_name) in enumerate(zip(comp_cols, selected_for_comparison)):
                artist_data = comparison_data[comparison_data["name"] == artist_name].iloc[0]
                with col:
                    st.markdown(f"#### {artist_name}")
                    st.metric("Rank", f"#{int(artist_data['rank'])}")
                    st.metric("Monthly Listeners", fmt_short(artist_data.get('monthly_listeners', 0)))
                    songs_count = artist_data.get('songs_count', 0)
                    st.metric("Songs", int(songs_count) if pd.notna(songs_count) else 0)
                    countries_count = artist_data.get('countries_count', 0)
                    st.metric("LATAM Countries", int(countries_count) if pd.notna(countries_count) else 0)
            
            # Visual comparison
            st.markdown("#### 📊 Visual Comparison")
            comp_col1, comp_col2 = st.columns(2)
            
            with comp_col1:
                # Monthly listeners comparison
                fig_comp_listeners = px.bar(
                    comparison_data,
                    x="name",
                    y="monthly_listeners",
                    color="name",
                    title="Monthly Listeners Comparison",
                    labels={'monthly_listeners': 'Monthly Listeners', 'name': 'Artist'},
                    color_discrete_sequence=CHART_COLORS
                )
                style_figure(fig_comp_listeners, 300)
                st.plotly_chart(fig_comp_listeners, use_container_width=True, config=PLOTLY_CONFIG)
            
            with comp_col2:
                # LATAM reach comparison
                fig_comp_reach = px.bar(
                    comparison_data,
                    x="name",
                    y="countries_count",
                    color="name",
                    title="LATAM Country Reach",
                    labels={'countries_count': 'Countries', 'name': 'Artist'},
                    color_discrete_sequence=CHART_COLORS
                )
                style_figure(fig_comp_reach, 300)
                st.plotly_chart(fig_comp_reach, use_container_width=True, config=PLOTLY_CONFIG)
            
            # Detailed comparison table
            with st.expander("📋 View Detailed Comparison Table"):
                comp_table = comparison_data[[
                    'name', 'rank', 'monthly_listeners', 'peak_listeners', 
                    'songs_count', 'albums_count', 'countries_count', 'top_song'
                ]].copy()
                comp_table.columns = [
                    'Artist', 'Rank', 'Monthly Listeners', 'Peak Listeners',
                    'Songs', 'Albums', 'LATAM Countries', 'Top Song'
                ]
                st.dataframe(comp_table, use_container_width=True, hide_index=True)
        else:
            st.warning("Please select at least 2 artists to compare")
    
    # Use tabs for different views
    tab1, tab2, tab3 = st.tabs(["📋 Data Table", "📈 Visual Analysis", "🎯 Artist Spotlight"])
    
    with tab1:
        left, right = st.columns([2.2, 1.0])

        with left:
            st.markdown(
                "<div class='dashboard-card'><div class='section-title'>🏆 Global Chart Positions</div><div class='section-sub'>Latest leaderboard filtered to Latin American relevance</div></div>",
                unsafe_allow_html=True,
            )
            table_df = prepare_leaderboard_table(leaderboard, max_rows)
            st.dataframe(
                table_df,
                use_container_width=True,
                hide_index=True,
                height=min(35 + max_rows * 35, 620),
                column_config={
                    "#": st.column_config.NumberColumn(width="small", format="%d"),
                    "Artist": st.column_config.TextColumn(width="medium"),
                    "Top Song": st.column_config.TextColumn(width="medium"),
                    "Top Country": st.column_config.TextColumn(width="small"),
                    "Monthly Listeners": st.column_config.NumberColumn(format="%,d"),
                    "Peak Listeners": st.column_config.NumberColumn(format="%,d"),
                    "Trend": st.column_config.TextColumn(width="small"),
                },
            )

        with right:
            top_streams = leaderboard.dropna(subset=["monthly_listeners"]).nlargest(10, "monthly_listeners")
            if not top_streams.empty:
                fig_bar = px.bar(
                    top_streams.sort_values("monthly_listeners"),
                    x="monthly_listeners",
                    y="name",
                    orientation="h",
                    color="monthly_listeners",
                    color_continuous_scale=["#4f8ef7", "#22d3a0"],
                )
                fig_bar.update_layout(title="Top Artists by Monthly Listeners", coloraxis_showscale=False)
                style_figure(fig_bar, 360)
                st.plotly_chart(fig_bar, use_container_width=True, config=PLOTLY_CONFIG)
    
    with tab2:
        col_a, col_b = st.columns(2)
        
        with col_a:
            # Rank distribution
            rank_dist = leaderboard.groupby(pd.cut(leaderboard['rank'], bins=[0, 5, 10, 20, 50, 100]), observed=False).size()
            fig_dist = px.bar(
                x=rank_dist.index.astype(str),
                y=rank_dist.values,
                labels={'x': 'Rank Range', 'y': 'Number of Artists'},
                title="Artist Distribution by Rank Range",
                color=rank_dist.values,
                color_continuous_scale=["#7c5cfc", "#4f8ef7", "#22d3a0"]
            )
            style_figure(fig_dist, 350)
            st.plotly_chart(fig_dist, use_container_width=True, config=PLOTLY_CONFIG)
        
        with col_b:
            # Listener vs Country reach
            scatter_data = leaderboard.dropna(subset=["monthly_listeners", "countries_count"]).head(30)
            if not scatter_data.empty:
                fig_scatter = px.scatter(
                    scatter_data,
                    x="countries_count",
                    y="monthly_listeners",
                    size="monthly_listeners",
                    color="rank",
                    hover_name="name",
                    title="Country Reach vs. Monthly Listeners",
                    labels={'countries_count': 'LATAM Countries', 'monthly_listeners': 'Monthly Listeners'},
                    color_continuous_scale=["#22d3a0", "#f5a623", "#e84545"]
                )
                style_figure(fig_scatter, 350)
                st.plotly_chart(fig_scatter, use_container_width=True, config=PLOTLY_CONFIG)
    
    with tab3:
        st.markdown("### 🎯 Artist Detail Spotlight")
        artists = leaderboard["name"].dropna().tolist()
        
        col_search, col_select = st.columns([1, 2])
        with col_search:
            search_artist = st.text_input("🔍 Quick search", placeholder="Type artist name...")
        with col_select:
            if search_artist:
                filtered_artists = [a for a in artists if search_artist.lower() in a.lower()]
                selected_artist = st.selectbox("Choose an artist", filtered_artists if filtered_artists else artists, index=0)
            else:
                selected_artist = st.selectbox("Choose an artist", artists, index=0)
        
        if selected_artist:
            row = leaderboard.loc[leaderboard["name"] == selected_artist].iloc[0]
            
            # Artist metrics with icons
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🎵 Songs", int(row.get("songs_count") or 0))
            c2.metric("💿 Albums", int(row.get("albums_count") or 0))
            c3.metric("🌎 LATAM Countries", int(row.get("countries_count") or 0))
            c4.metric("👥 Monthly Listeners", fmt_short(row.get("monthly_listeners") or 0))
            
            # Expandable details
            with st.expander("📋 View Top Songs", expanded=True):
                songs_text = row.get("top_songs") or "—"
                st.text_area("Top Songs", songs_text, height=180, label_visibility="collapsed")
            
            with st.expander("🗺️ View Top Countries", expanded=True):
                countries_text = row.get("top_countries") or "—"
                st.text_area("Top Countries", countries_text, height=180, label_visibility="collapsed")


def resample_tracker_pattern(pattern: list[int], days: int) -> list[int]:
    if not pattern:
        return [1] * max(days, 1)
    if days <= 1:
        return [int(pattern[-1])]
    if len(pattern) == days:
        return [int(value) for value in pattern]

    resampled: list[int] = []
    last_index = len(pattern) - 1
    for step in range(days):
        scaled_index = (step / (days - 1)) * last_index
        lower = int(scaled_index)
        upper = min(lower + 1, last_index)
        blend = scaled_index - lower
        interpolated = pattern[lower] + (pattern[upper] - pattern[lower]) * blend
        resampled.append(int(round(interpolated)))
    return resampled


def build_tracker_demo_data(leaderboard: pd.DataFrame, days: int = 14) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "rank" in leaderboard.columns and leaderboard["rank"].notna().any():
        top = leaderboard.dropna(subset=["rank"]).sort_values("rank").head(TRACKER_TOP_ARTISTS).copy()
    else:
        top = leaderboard.dropna(subset=["monthly_listeners"]).nlargest(TRACKER_TOP_ARTISTS, "monthly_listeners").copy()

    if top.empty:
        top = leaderboard.head(TRACKER_TOP_ARTISTS).copy()

    top = top.reset_index(drop=True)
    date_range = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days)
    date_labels = date_range.strftime("%b %-d").tolist()
    base_patterns = [
        [3, 2, 2, 1, 1, 2, 3, 2, 1, 1, 2, 1, 1, 1],
        [5, 4, 3, 3, 2, 2, 1, 2, 3, 2, 2, 3, 2, 2],
        [8, 7, 6, 5, 4, 3, 4, 3, 3, 4, 3, 3, 3, 3],
        [10, 9, 8, 7, 6, 5, 6, 5, 4, 5, 4, 4, 4, 4],
        [15, 12, 10, 9, 8, 7, 8, 7, 6, 5, 5, 5, 5, 5],
    ]

    max_rank = int(top["rank"].max()) if "rank" in top.columns and top["rank"].notna().any() else TRACKER_TOP_ARTISTS + 8
    max_rank = max(TRACKER_TOP_ARTISTS + 2, max_rank)

    records = []
    best_rows = []
    for idx, row in top.iterrows():
        pattern = resample_tracker_pattern(base_patterns[idx % len(base_patterns)], days)
        current_rank = int(row["rank"]) if pd.notna(row.get("rank")) else idx + 1
        current_rank = max(1, min(max_rank, current_rank))
        shift = current_rank - pattern[-1]
        series = [max(1, min(max_rank, point + shift)) for point in pattern]

        for day_label, plot_date, pos in zip(date_labels, date_range, series):
            records.append({"day": day_label, "date": plot_date, "artist": row["name"], "position": pos})

        best_rows.append({
            "artist": row["name"],
            "best_position": min(series),
        })

    return pd.DataFrame(records), pd.DataFrame(best_rows).sort_values("best_position")


def render_chart_tracker(history: pd.DataFrame, leaderboard: pd.DataFrame) -> None:
    if history.empty and leaderboard.empty:
        st.warning("Not enough ranking data available yet.")
        return

    unique_runs = int(history["scraped_at"].nunique()) if not history.empty else 0
    
    # Add interactive controls
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(
            f"<div class='dashboard-card'><div class='section-title'>📈 Chart Tracker</div><div class='section-sub'>Clean position movement for the current top {TRACKER_TOP_ARTISTS} artists in the latest snapshot</div></div>",
            unsafe_allow_html=True,
        )
    with col2:
        time_range = st.selectbox("📅 Time Range", ["7 days", "14 days", "30 days"], index=1)
    with col3:
        view_mode = st.selectbox("👁️ View Mode", ["Line Chart", "Area Chart"], index=0)

    time_window_days = int(time_range.split()[0])
    using_demo = unique_runs < 3
    if using_demo:
        st.info("📊 Full ranking history is still building. Using latest snapshot with smoothed trajectory interpolation.", icon="ℹ️")
        line_df, best_df = build_tracker_demo_data(leaderboard, days=time_window_days)
    else:
        history = history.copy()
        history["scraped_at"] = pd.to_datetime(history["scraped_at"], errors="coerce")
        history = history.dropna(subset=["scraped_at", "rank", "name"]).sort_values(["scraped_at", "rank"])

        if not history.empty:
            latest_scraped_at = history["scraped_at"].max().normalize()
            window_start = latest_scraped_at - pd.Timedelta(days=time_window_days - 1)
            history = history[history["scraped_at"] >= window_start]

        if history.empty:
            st.info("📊 Limited long-range history is available. Showing an interpolated top-artist trend instead.", icon="ℹ️")
            line_df, best_df = build_tracker_demo_data(leaderboard, days=time_window_days)
            using_demo = True
        else:
            history["day"] = history["scraped_at"].dt.strftime("%b %-d")
            line_df = history.rename(columns={"name": "artist", "rank": "position", "scraped_at": "date"})[
                ["day", "date", "artist", "position"]
            ]
            best_df = (
                history.groupby("name", as_index=False)["rank"]
                .min()
                .rename(columns={"name": "artist", "rank": "best_position"})
                .sort_values("best_position")
                .head(TRACKER_TOP_ARTISTS)
            )

    if using_demo and "rank" in leaderboard.columns and leaderboard["rank"].notna().any():
        artists_tracked = leaderboard.dropna(subset=["rank"]).sort_values("rank")["name"].head(TRACKER_TOP_ARTISTS).tolist()
    else:
        artists_tracked = (
            line_df.sort_values(["position", "artist"])["artist"].drop_duplicates().tolist()[:TRACKER_TOP_ARTISTS]
        )

    line_df = line_df[line_df["artist"].isin(artists_tracked)]
    best_df = best_df[best_df["artist"].isin(artists_tracked)].sort_values("best_position", ascending=False)

    max_position = int(line_df["position"].max()) if not line_df.empty else TRACKER_TOP_ARTISTS
    max_position = max(TRACKER_TOP_ARTISTS + 2, max_position)
    tick_step = 1 if max_position <= 15 else 2 if max_position <= 30 else 5

    fig_line = go.Figure()
    for idx, artist in enumerate(artists_tracked):
        sub = line_df[line_df["artist"] == artist]

        if view_mode == "Area Chart":
            fig_line.add_trace(
                go.Scatter(
                    x=sub["date"],
                    y=sub["position"],
                    mode="lines",
                    name=artist,
                    fill="tonexty" if idx > 0 else "tozeroy",
                    line=dict(color=CHART_COLORS[idx % len(CHART_COLORS)], width=2),
                    hovertemplate="<b>%{fullData.name}</b><br>%{x|%b %d}: Position #%{y}<extra></extra>",
                )
            )
        else:
            fig_line.add_trace(
                go.Scatter(
                    x=sub["date"],
                    y=sub["position"],
                    mode="lines+markers",
                    name=artist,
                    line=dict(color=CHART_COLORS[idx % len(CHART_COLORS)], width=3, shape="spline"),
                    marker=dict(size=7),
                    hovertemplate="<b>%{fullData.name}</b><br>%{x|%b %d}: Position #%{y}<extra></extra>",
                )
            )

    title_text = f"🎯 Top {TRACKER_TOP_ARTISTS} Artist Position Trend ({time_range})"
    fig_line.update_layout(
        title=dict(text=title_text, x=0, xanchor="left", font=dict(size=18), y=0.98, yanchor="top"),
        xaxis_title="",
        yaxis_title="Chart position",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
        ),
        hovermode="x unified",
        margin=dict(l=50, r=20, t=80, b=90),
    )
    fig_line.update_yaxes(
        autorange="reversed",
        range=[max_position + 0.5, 0.5],
        tickmode="array",
        tickvals=list(range(1, max_position + 1, tick_step)),
    )
    fig_line.update_xaxes(showgrid=False, tickformat="%b %d", dtick=86400000 * max(1, time_window_days // 10))
    style_figure(fig_line, 520)
    st.plotly_chart(fig_line, use_container_width=True, config=PLOTLY_CONFIG)

    if not best_df.empty:
        fig_best = px.bar(
            best_df,
            x="best_position",
            y="artist",
            orientation="h",
            color="artist",
            color_discrete_sequence=CHART_COLORS,
        )
        fig_best.update_traces(
            text=[f"#{int(v)}" for v in best_df["best_position"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Best position: #%{x}<extra></extra>",
        )
        fig_best.update_layout(
            title=dict(text="🏆 Best Recent Positions", x=0.03, xanchor="left", font=dict(size=18)),
            showlegend=False,
            xaxis_title="Lower is better",
            yaxis_title="",
            margin=dict(l=40, r=20, t=70, b=40),
        )
        fig_best.update_xaxes(autorange="reversed", dtick=1, showgrid=False)
        style_figure(fig_best, max(380, 34 * len(best_df) + 80))
        st.plotly_chart(fig_best, use_container_width=True, config=PLOTLY_CONFIG)
        st.download_button(
            "⬇️ Download Best Recent Positions",
            data=best_df.sort_values("best_position").to_csv(index=False).encode("utf-8"),
            file_name="best_recent_positions.csv",
            mime="text/csv",
            key="download_best_recent_positions",
        )
    
    # Additional insights
    with st.expander("📊 Detailed Movement Analysis", expanded=False):
        movement_data = []
        for artist in artists_tracked:
            artist_data = line_df[line_df["artist"] == artist]
            if len(artist_data) >= 2:
                first_pos = artist_data.iloc[0]["position"]
                last_pos = artist_data.iloc[-1]["position"]
                change = first_pos - last_pos
                movement_data.append({
                    "Artist": artist,
                    "Starting Position": int(first_pos),
                    "Current Position": int(last_pos),
                    "Change": f"+{int(change)}" if change > 0 else str(int(change)),
                    "Trend": "📈 Rising" if change > 0 else "📉 Falling" if change < 0 else "➡️ Stable"
                })
        
        if movement_data:
            movement_df = pd.DataFrame(movement_data)
            st.dataframe(movement_df, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download Detailed Movement Analysis",
                data=movement_df.to_csv(index=False).encode("utf-8"),
                file_name="detailed_movement_analysis.csv",
                mime="text/csv",
                key="download_detailed_movement_analysis",
            )



def render_stream_trends(leaderboard: pd.DataFrame) -> None:
    if leaderboard.empty:
        st.warning("No streaming data available yet.")
        return

    top_spotify = leaderboard.dropna(subset=["monthly_listeners"]).nlargest(12, "monthly_listeners")
    if top_spotify.empty:
        st.info("Spotify listener data has not been scraped yet.")
        return

    # Interactive metric selector
    st.markdown("### 🎵 Streaming Analytics")
    metric_choice = st.radio(
        "Select metric to visualize",
        ["Listener Momentum", "LATAM Reach", "Peak Performance"],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    
    if metric_choice == "Listener Momentum":
        with c1:
            fig = go.Figure()
            fig.add_bar(
                name="Monthly Listeners", 
                x=top_spotify["name"], 
                y=top_spotify["monthly_listeners"], 
                marker_color="#1ED760",
                hovertemplate="<b>%{x}</b><br>Monthly: %{y:,}<extra></extra>"
            )
            fig.add_bar(
                name="Peak Listeners", 
                x=top_spotify["name"], 
                y=top_spotify["peak_listeners"].fillna(0), 
                marker_color="#4f8ef7",
                hovertemplate="<b>%{x}</b><br>Peak: %{y:,}<extra></extra>"
            )
            fig.update_layout(
                title="🎧 Spotify Listener Momentum", 
                barmode="group", 
                xaxis_title="Artist", 
                yaxis_title="Listeners"
            )
            fig.update_xaxes(tickangle=-45)
            style_figure(fig, 420)
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

        with c2:
            # Growth potential
            top_spotify_copy = top_spotify.copy()
            top_spotify_copy["growth_potential"] = (
                (top_spotify_copy["peak_listeners"].fillna(0) - top_spotify_copy["monthly_listeners"]) / 
                top_spotify_copy["monthly_listeners"] * 100
            ).fillna(0)
            growth_data = top_spotify_copy.nlargest(10, "growth_potential")
            
            fig_growth = px.bar(
                growth_data.sort_values("growth_potential"),
                x="growth_potential",
                y="name",
                orientation="h",
                color="growth_potential",
                color_continuous_scale=["#f5a623", "#22d3a0"],
                title="📊 Growth Potential %"
            )
            fig_growth.update_layout(coloraxis_showscale=False)
            style_figure(fig_growth, 420)
            st.plotly_chart(fig_growth, use_container_width=True, config=PLOTLY_CONFIG)
    
    elif metric_choice == "LATAM Reach":
        with c1:
            latam_presence = leaderboard[leaderboard["countries_count"] > 0].nlargest(10, "countries_count")
            if not latam_presence.empty:
                fig_latam = px.bar(
                    latam_presence.sort_values("countries_count"),
                    x="countries_count",
                    y="name",
                    orientation="h",
                    color="countries_count",
                    color_continuous_scale=["#7c5cfc", "#22d3a0"],
                    title="🌎 Latin American Country Reach"
                )
                fig_latam.update_layout(coloraxis_showscale=False)
                style_figure(fig_latam, 420)
                st.plotly_chart(fig_latam, use_container_width=True, config=PLOTLY_CONFIG)
        
        with c2:
            # Map-style visualization
            if not latam_presence.empty:
                fig_bubble = px.scatter(
                    latam_presence,
                    x="countries_count",
                    y="monthly_listeners",
                    size="monthly_listeners",
                    color="rank",
                    hover_name="name",
                    title="🗺️ Geographic Spread vs Popularity",
                    labels={'countries_count': 'LATAM Countries', 'monthly_listeners': 'Monthly Listeners'},
                    color_continuous_scale=["#22d3a0", "#f5a623", "#e84545"]
                )
                style_figure(fig_bubble, 420)
                st.plotly_chart(fig_bubble, use_container_width=True, config=PLOTLY_CONFIG)
    
    else:  # Peak Performance
        with c1:
            peak_data = top_spotify[top_spotify["peak_listeners"].notna()].nlargest(10, "peak_listeners")
            if not peak_data.empty:
                fig_peak = px.bar(
                    peak_data.sort_values("peak_listeners"),
                    x="peak_listeners",
                    y="name",
                    orientation="h",
                    color="peak_listeners",
                    color_continuous_scale=["#4f8ef7", "#7c5cfc"],
                    title="🚀 Peak Listener Performance"
                )
                fig_peak.update_layout(coloraxis_showscale=False)
                style_figure(fig_peak, 420)
                st.plotly_chart(fig_peak, use_container_width=True, config=PLOTLY_CONFIG)
        
        with c2:
            # Peak vs current
            comparison_data = top_spotify[top_spotify["peak_listeners"].notna()].head(10)
            fig_compare = go.Figure()
            fig_compare.add_trace(go.Scatter(
                x=comparison_data["monthly_listeners"],
                y=comparison_data["peak_listeners"],
                mode='markers+text',
                marker=dict(
                    size=15,
                    color=comparison_data.index,
                    colorscale='Viridis',
                    showscale=False
                ),
                text=comparison_data["name"].str[:15],
                textposition="top center",
                hovertemplate="<b>%{text}</b><br>Current: %{x:,}<br>Peak: %{y:,}<extra></extra>"
            ))
            # Add diagonal line
            max_val = max(comparison_data["monthly_listeners"].max(), comparison_data["peak_listeners"].max())
            fig_compare.add_trace(go.Scatter(
                x=[0, max_val],
                y=[0, max_val],
                mode='lines',
                line=dict(dash='dash', color='gray'),
                showlegend=False,
                hoverinfo='skip'
            ))
            fig_compare.update_layout(
                title="🎯 Current vs Peak Performance",
                xaxis_title="Monthly Listeners",
                yaxis_title="Peak Listeners"
            )
            style_figure(fig_compare, 420)
            st.plotly_chart(fig_compare, use_container_width=True, config=PLOTLY_CONFIG)

    # Data table with enhanced view
    with st.expander("📋 View Detailed Streaming Data", expanded=False):
        trends_df = top_spotify[["rank", "name", "monthly_listeners", "peak_listeners", "display_country", "countries_count"]].copy()
        trends_df.columns = ["iTunes Rank", "Artist", "Monthly Listeners", "Peak Listeners", "Top LATAM Country", "LATAM Countries"]
        st.dataframe(
            trends_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Monthly Listeners": st.column_config.NumberColumn(format="%,d"),
                "Peak Listeners": st.column_config.NumberColumn(format="%,d"),
                "iTunes Rank": st.column_config.NumberColumn(format="#%d"),
            },
        )


def render_ops_monitor(runs: pd.DataFrame) -> None:
    if runs.empty:
        st.warning("⚠️ No scrape run logs available yet. Start the pipeline to see metrics.")
        return

    runs = runs.copy()
    runs["status"] = runs["status"].fillna("unknown")
    runs["success_flag"] = runs["status"].eq("success").astype(int)
    runs["duration_sec"] = (runs["finished_at"] - runs["started_at"]).dt.total_seconds()

    total_runs = len(runs)
    success_pct = runs["success_flag"].mean() * 100
    latest_rows = int(runs["rows_upserted"].fillna(0).iloc[0]) if total_runs else 0
    avg_duration = runs["duration_sec"].dropna().mean()
    
    # Health indicator
    if success_pct >= 95:
        health_status = "🟢 Excellent"
        health_color = "#22d3a0"
    elif success_pct >= 80:
        health_status = "🟡 Good"
        health_color = "#f5a623"
    else:
        health_status = "🔴 Needs Attention"
        health_color = "#e84545"
    
    st.markdown(f"### ⚙️ Pipeline Health: <span style='color:{health_color}'>{health_status}</span>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Animated KPI cards
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📋 Total Runs", total_runs, delta=f"+{runs['source'].nunique()} sources")
    k2.metric("✅ Success Rate", f"{success_pct:.1f}%", delta=f"{success_pct - 80:.1f}%" if success_pct > 80 else f"{success_pct - 80:.1f}%")
    k3.metric("📊 Latest Batch", f"{latest_rows:,}", delta="Rows processed")
    k4.metric("⏱️ Avg Duration", f"{avg_duration:.0f}s" if pd.notna(avg_duration) else "—", delta="Per run")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Performance Overview", "📜 Run History", "🔍 Detailed Analytics"])
    
    with tab1:
        rate_df = (
            runs.groupby("source", as_index=False)
            .agg(success_pct=("success_flag", "mean"), total_rows=("rows_upserted", "sum"))
            .sort_values(["success_pct", "total_rows"], ascending=[False, False])
        )
        rate_df["success_pct"] = rate_df["success_pct"] * 100

        c1, c2 = st.columns([1.1, 1.1])
        with c1:
            colors = ["#22d3a0" if val >= 95 else "#f5a623" if val >= 80 else "#e84545" for val in rate_df["success_pct"]]
            fig_rate = go.Figure(
                data=[
                    go.Bar(
                        x=rate_df["source"],
                        y=rate_df["success_pct"],
                        marker_color=colors,
                        text=[f"{v:.0f}%" for v in rate_df["success_pct"]],
                        textposition="outside",
                        hovertemplate="<b>%{x}</b><br>Success: %{y:.1f}%<extra></extra>"
                    )
                ]
            )
            fig_rate.update_layout(
                title="🎯 Pipeline Success Rate by Job",
                xaxis_title="",
                yaxis_title="Success %",
                yaxis_range=[0, 105],
            )
            style_figure(fig_rate, 320)
            st.plotly_chart(fig_rate, use_container_width=True, config=PLOTLY_CONFIG)

        with c2:
            recent = runs[["finished_at", "source", "rows_upserted", "status"]].head(7).copy()
            recent["finished_label"] = recent["finished_at"].dt.strftime("%Y-%m-%d %H:%M").fillna("in progress")
            html = ['<div class="dashboard-card"><div class="section-title">🔔 Recent Scrape Runs</div><div class="section-sub">Last 7 pipeline events</div><div class="run-log">']
            for _, row in recent.iterrows():
                status = str(row["status"]).lower()
                dot_class = "dot-ok" if status == "success" else "dot-partial" if status == "partial" else "dot-fail"
                pill_class = "pill-ok" if status == "success" else "pill-partial" if status == "partial" else "pill-fail"
                html.append(
                    f'<div class="run-item">'
                    f'<div class="run-date"><span class="run-dot {dot_class}"></span>{escape(str(row["finished_label"]))}</div>'
                    f'<div class="run-source">{escape(str(row["source"]))}</div>'
                    f'<div class="run-rows">{int(row["rows_upserted"] or 0):,}</div>'
                    f'<div><span class="status-pill {pill_class}">{escape(status)}</span></div>'
                    f'</div>'
                )
            html.append('</div></div>')
            st.markdown(''.join(html), unsafe_allow_html=True)
    
    with tab2:
        rows_df = runs.dropna(subset=["finished_at"]).sort_values("finished_at").tail(20).copy()
        if not rows_df.empty:
            rows_df["Run Label"] = rows_df["finished_at"].dt.strftime("%b %d %H:%M")
            fig_rows = go.Figure()
            for idx, source in enumerate(rows_df["source"].drop_duplicates().tolist()):
                sub = rows_df[rows_df["source"] == source]
                fig_rows.add_trace(
                    go.Scatter(
                        x=sub["Run Label"],
                        y=sub["rows_upserted"],
                        mode="lines+markers",
                        name=source,
                        line=dict(color=CHART_COLORS[idx % len(CHART_COLORS)], width=2.5),
                        marker=dict(size=7),
                        hovertemplate="%{x}<br>%{fullData.name}: %{y:,} rows<extra></extra>",
                    )
                )
            fig_rows.update_layout(
                title="📈 Records Ingested per Run",
                xaxis_title="Run",
                yaxis_title="Rows upserted (log scale)",
            )
            fig_rows.update_yaxes(type="log")
            fig_rows.update_xaxes(tickangle=-20)
            style_figure(fig_rows, 400)
            st.plotly_chart(fig_rows, use_container_width=True, config=PLOTLY_CONFIG)
            st.caption("💡 Log scale is used so very large and very small jobs stay visible together.")
    
    with tab3:
        # Detailed run statistics
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.markdown("#### 📊 Run Duration Analysis")
            duration_df = runs.dropna(subset=["duration_sec"]).copy()
            if not duration_df.empty:
                fig_duration = px.box(
                    duration_df,
                    x="source",
                    y="duration_sec",
                    color="source",
                    title="Run Duration Distribution by Source",
                    labels={'duration_sec': 'Duration (seconds)', 'source': 'Data Source'},
                    color_discrete_sequence=CHART_COLORS
                )
                style_figure(fig_duration, 350)
                st.plotly_chart(fig_duration, use_container_width=True, config=PLOTLY_CONFIG)
        
        with col_right:
            st.markdown("#### 📋 Status Breakdown")
            status_counts = runs["status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            fig_status = px.pie(
                status_counts,
                names="Status",
                values="Count",
                title="Overall Status Distribution",
                color_discrete_sequence=["#22d3a0", "#f5a623", "#e84545"]
            )
            style_figure(fig_status, 350)
            st.plotly_chart(fig_status, use_container_width=True, config=PLOTLY_CONFIG)
        


apply_theme()

try:
    data = load_dashboard_data()
except Exception as exc:  # pragma: no cover
    st.error(f"❌ Failed to load dashboard data: {exc}")
    st.stop()

leaderboard = data["leaderboard"]
runs = data["runs"]
history = data["history"]

last_run_label = "n/a"
if not runs.empty and runs["finished_at"].notna().any():
    last_run_label = runs["finished_at"].dropna().max().strftime("%Y-%m-%d %H:%M")


def show_leaderboard_page() -> None:
    page_title, page_meta = PAGE_META["Leaderboard"]
    render_header(page_title, page_meta, last_run_label)
    render_leaderboard(filtered, runs, max_rows=max_rows)


def show_chart_tracker_page() -> None:
    page_title, page_meta = PAGE_META["Chart Tracker"]
    render_header(page_title, page_meta, last_run_label)
    render_chart_tracker(history, filtered)


def show_stream_trends_page() -> None:
    page_title, page_meta = PAGE_META["Stream Trends"]
    render_header(page_title, page_meta, last_run_label)
    render_stream_trends(filtered)


def show_ops_monitor_page() -> None:
    page_title, page_meta = PAGE_META["Ops Monitor"]
    render_header(page_title, page_meta, last_run_label)
    render_ops_monitor(runs)


app_pages = [
    st.Page(show_leaderboard_page, title="Leaderboard", url_path="leaderboard", default=True),
    st.Page(show_chart_tracker_page, title="Chart Tracker", url_path="chart-tracker"),
    st.Page(show_stream_trends_page, title="Stream Trends", url_path="stream-trends"),
    st.Page(show_ops_monitor_page, title="Ops Monitor", url_path="ops-monitor"),
]

with st.sidebar:
    st.markdown(
        """
        <div class='brand-row'>
            <div class='brand-logo'>🎵</div>
            <div>
                <div class='sidebar-logo'>Artist 360 Intelligence</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Proper sidebar routing for all dashboard views
    current_page = st.navigation(app_pages, position="sidebar", expanded=True)
    
    # Collapsible advanced settings
    with st.expander("🔍 Search & Filter", expanded=True):
        search = st.text_input("🎤 Artist search", placeholder="e.g. BTS, Drake...")
        latam_only = st.toggle("🌎 Latin America only", value=True)
        default_countries = sorted([c for c in leaderboard["display_country"].unique().tolist() if c != "—"])
        selected_countries = st.multiselect(
            "📍 Countries",
            default_countries or LATAM_COUNTRIES,
            default=default_countries or LATAM_COUNTRIES[:6],
        )

    
    with st.expander("🎛️ Display Options", expanded=True):
        max_rows = st.slider("📊 Table rows", min_value=10, max_value=50, value=15, step=5)
    
    # Apply filters to create filtered dataframe
    filtered = leaderboard.copy()
    if latam_only:
        filtered = filtered[filtered["latam_signal"]]
    if selected_countries:
        filtered = filtered[filtered["display_country"].isin(selected_countries)]
    if search.strip():
        filtered = filtered[filtered["name"].str.contains(search.strip(), case=False, na=False)]
    filtered = filtered.sort_values("rank")
    
    # Action buttons
    st.markdown("### 🔄 Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    # Auto-refresh toggle
    auto_refresh_sidebar = st.toggle("⏱️ Auto-refresh (30s)", value=st.session_state.auto_refresh)
    if auto_refresh_sidebar != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_refresh_sidebar
    
    # Status indicator
    status_color = "status-good" if len(runs) > 0 else "muted"
    st.markdown(f"<span class='{status_color}'>● Pipeline: {'Healthy' if len(runs) > 0 else 'Unknown'}</span>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Last run: {last_run_label}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Updated: {pd.Timestamp.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
    

current_page.run()

# Auto-refresh functionality
if st.session_state.auto_refresh:
    import time
    time.sleep(30)
    st.rerun()
