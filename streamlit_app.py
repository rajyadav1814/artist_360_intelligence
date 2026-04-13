from __future__ import annotations

from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as st_components

from src.database.connection import get_connection
from src.scrapers.artist_details_scraper import LATIN_AMERICAN_COUNTRIES
from skeleton import render_dashboard_skeleton


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
BOT_SRC = "https://copilotstudio.microsoft.com/environments/4b079cee-b5d6-e253-856d-c427359af206/bots/cr917_agentT1zDET/webchat?__version__=2"
LOAD_TIMEOUT_MS = 20000


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
        .block-container {
            width: min(100%, 1680px);
            max-width: 1680px;
            padding-top: 1rem;
            padding-right: clamp(0.85rem, 1.8vw, 1.6rem);
            padding-left: clamp(0.85rem, 1.8vw, 1.6rem);
            padding-bottom: 2rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: clamp(0.75rem, 1.4vw, 1.1rem);
            align-items: stretch;
        }
        div[data-testid="column"] > div {
            width: 100%;
            height: 100%;
        }
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
            padding:clamp(0.9rem, 1.2vw, 1.1rem); box-shadow:0 12px 32px rgba(0,0,0,.22);
            margin-bottom:1rem; transition: all 0.3s ease;
            animation: fadeIn 0.7s ease-out; min-height: 100%;
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
            min-height:clamp(108px, 12vw, 132px); position:relative; overflow:hidden; height: 100%;
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
        .stTabs {
            width: 100%;
            border-bottom: none !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            display: grid !important;
            grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr));
            grid-auto-flow: row;
            gap: 10px;
            width: 100%;
            background: transparent;
            border-bottom: none !important;
            overflow: visible;
            align-items: stretch;
        }
        .stTabs [data-baseweb="tab-border"] {
            display: none !important;
        }
        .stTabs [data-baseweb="tab-highlight"] {
            display: none !important;
        }
        .stTabs > div > div {
            border-bottom: none !important;
            gap: 10px;
            width: 100%;
        }
        .stTabs [data-baseweb="tab"] {
            width: 100%;
            min-width: 0 !important;
            justify-content: center;
            background: var(--surface2);
            border-radius: 10px;
            color: var(--text2);
            border: 1px solid var(--border);
            padding: 0.5rem 0.65rem !important;
            min-height: 44px;
            height: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            transition: all 0.3s ease;
            border-bottom: 1px solid var(--border) !important;
        }
        .stTabs [data-baseweb="tab"] p {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: .86rem;
        }
        .stTabs [data-baseweb="tab-panel"] {
            width: 100%;
            padding-top: 0.85rem;
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
        .stPlotlyChart, div[data-testid="stDataFrame"], div[data-testid="stTable"] {
            width: 100% !important;
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

        @media (max-width: 1200px) {
            .block-container {
                max-width: 100%;
            }
            .page-title {
                font-size: 1.8rem;
            }
            .kpi-value {
                font-size: 1.75rem;
            }
            .stTabs [data-baseweb="tab-list"] {
                grid-template-columns: repeat(auto-fit, minmax(min(150px, 100%), 1fr));
            }
        }

        @media (max-width: 992px) {
            .block-container {
                padding-right: 0.9rem;
                padding-left: 0.9rem;
            }
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
            }
            div[data-testid="column"] {
                min-width: calc(50% - 0.55rem) !important;
                flex: 1 1 calc(50% - 0.55rem) !important;
            }
        }

        @media (max-width: 768px) {
            div[data-testid="column"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
            .page-title {
                font-size: 1.55rem;
            }
            .page-meta {
                font-size: 0.88rem;
            }
            .dashboard-card {
                padding: 0.9rem;
                border-radius: 14px;
            }
            .kpi-card {
                min-height: auto;
            }
            .kpi-value {
                font-size: 1.55rem;
            }
            .stTabs [data-baseweb="tab"] {
                min-height: 40px;
                padding: 0.4rem 0.45rem !important;
            }
            .stTabs [data-baseweb="tab"] p {
                font-size: 0.8rem;
            }
            .run-item {
                grid-template-columns: 1fr;
                gap: 0.35rem;
            }
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

        /* Global footer */
        .app-footer {
            margin-top: 2.5rem;
            padding: 1rem 0 0.25rem;
            border-top: 1px solid rgba(41,52,85,.7);
            text-align: center;
            color: var(--text2);
            font-size: 0.86rem;
            line-height: 1.7;
        }
        .app-footer a {
            color: #b7d4ff;
            text-decoration: none;
        }
        .app-footer a:hover {
            color: #ffffff;
            text-decoration: underline;
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
        height=max(280, int(height)),
        autosize=True,
        margin=dict(l=0, r=0, t=56, b=0, pad=0),
        paper_bgcolor="rgba(18,24,42,1)",
        plot_bgcolor="rgba(18,24,42,1)",
        font=dict(color="#e8eaf6"),
        legend_title_text="",
        title=dict(x=0.03, xanchor="left", font=dict(size=16, color="#eef2ff")),
        hoverlabel=dict(
            bgcolor="rgba(9,17,39,.96)",
            bordercolor="rgba(79,142,247,.45)",
            font=dict(color="#eef2ff"),
        ),
    )
    fig.update_xaxes(
        gridcolor="rgba(151,163,197,.12)",
        zerolinecolor="rgba(151,163,197,.12)",
        tickfont=dict(size=11),
        title_font=dict(size=12),
    )
    fig.update_yaxes(
        gridcolor="rgba(151,163,197,.12)",
        zerolinecolor="rgba(151,163,197,.12)",
        tickfont=dict(size=11),
        title_font=dict(size=12),
    )


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


def render_footer() -> None:
    st.markdown(
        """
        <div class="app-footer">
            <div><a href="mailto:info@chromadata.com">info@chromadata.com</a></div>
            <div>© 2026 - Chromadata. All rights reserved.</div>
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
    table_df["monthly_listeners"] = table_df["monthly_listeners"].apply(fmt_short)
    table_df["peak_listeners"] = table_df["peak_listeners"].apply(fmt_short)
    table_df.columns = [
        "Rank",
        "Artist",
        "Top Song",
        "Top Country",
        "Monthly Listeners",
        "Peak Listeners",
        "Trend",
    ]
    return table_df


def set_leaderboard_view(view_name: str) -> None:
    st.session_state.leaderboard_view = view_name
    st.session_state.comparison_mode = False


def toggle_comparison_mode() -> None:
    is_enabled = not st.session_state.get("comparison_mode", False)
    st.session_state.comparison_mode = is_enabled
    if is_enabled:
        st.session_state.leaderboard_view = "compare"
    elif st.session_state.get("leaderboard_view") == "compare":
        st.session_state.leaderboard_view = "📋 Table"


def render_leaderboard(leaderboard: pd.DataFrame, runs: pd.DataFrame, max_rows: int) -> None:
    if leaderboard.empty:
        st.warning("No leaderboard data available yet. Run the scraper first.")
        return

    render_kpis(leaderboard, runs)

    st.markdown("<br>", unsafe_allow_html=True)

    # Keep all five controls in one row: Table, Analysis, Spotlight, Compare, Download
    csv = leaderboard.head(max_rows).to_csv(index=False)
    selected_view = st.session_state.get("leaderboard_view", "📋 Table")
    btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns(5, gap="small")
    with btn_col1:
        st.button(
            "📋 Table",
            use_container_width=True,
            type="primary" if selected_view == "📋 Table" else "secondary",
            key="view_table_btn",
            on_click=set_leaderboard_view,
            args=("📋 Table",),
        )
    with btn_col2:
        st.button(
            "📈 Analysis",
            use_container_width=True,
            type="primary" if selected_view == "📈 Analysis" else "secondary",
            key="view_analysis_btn",
            on_click=set_leaderboard_view,
            args=("📈 Analysis",),
        )
    with btn_col3:
        st.button(
            "🎯 Spotlight",
            use_container_width=True,
            type="primary" if selected_view == "🎯 Spotlight" else "secondary",
            key="view_spotlight_btn",
            on_click=set_leaderboard_view,
            args=("🎯 Spotlight",),
        )
    with btn_col4:
        st.button(
            "📊 Compare",
            use_container_width=True,
            type="primary" if st.session_state.get("comparison_mode", False) else "secondary",
            key="compare_btn",
            on_click=toggle_comparison_mode,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Comparison Mode
    if st.session_state.comparison_mode:
        st.markdown("### 🔄 Artist Comparison Mode")
        st.info("Select 2-5 artists to compare their metrics side by side")

        available_artists = leaderboard["name"].dropna().tolist()[:20]  # Limit to top 20 for performance
        selected_for_comparison = st.multiselect(
            "Select artists to compare",
            available_artists,
            default=available_artists[:2] if len(available_artists) >= 2 else available_artists,
            max_selections=5,
            key="comparison_artists"
        )

        if len(selected_for_comparison) >= 2:
            comparison_data = leaderboard[leaderboard["name"].isin(selected_for_comparison)].copy()
            comparison_data = comparison_data.sort_values("rank")
            comparison_data["monthly_label"] = comparison_data["monthly_listeners"].apply(fmt_short)

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
            comp_col1, comp_col2 = st.columns(2, gap="large")

            with comp_col1:
                # Monthly listeners comparison
                fig_comp_listeners = px.bar(
                    comparison_data,
                    x="name",
                    y="monthly_listeners",
                    text="monthly_label",
                    title="Monthly Listeners Comparison",
                    labels={'monthly_listeners': 'Monthly Listeners', 'name': 'Artist'},
                    color_discrete_sequence=CHART_COLORS
                )
                fig_comp_listeners.update_traces(
                    marker_color=CHART_COLORS[0],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="<b>%{x}</b><br>Monthly listeners: %{y:,.0f}<extra></extra>",
                )
                fig_comp_listeners.update_layout(
                    showlegend=False,
                    xaxis_title="",
                    yaxis_title="Monthly listeners",
                    margin=dict(l=8, r=8, t=64, b=8),
                )
                fig_comp_listeners.update_yaxes(tickformat="~s")
                style_figure(fig_comp_listeners, 300)
                st.plotly_chart(fig_comp_listeners, use_container_width=True, config=PLOTLY_CONFIG)

            with comp_col2:
                # LATAM reach comparison
                fig_comp_reach = px.bar(
                    comparison_data,
                    x="name",
                    y="countries_count",
                    text="countries_count",
                    title="LATAM Country Reach",
                    labels={'countries_count': 'Countries', 'name': 'Artist'},
                    color_discrete_sequence=CHART_COLORS
                )
                fig_comp_reach.update_traces(
                    marker_color=CHART_COLORS[1],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="<b>%{x}</b><br>LATAM countries: %{y}<extra></extra>",
                )
                fig_comp_reach.update_layout(
                    showlegend=False,
                    xaxis_title="",
                    yaxis_title="Countries",
                    margin=dict(l=8, r=8, t=64, b=8),
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

    if st.session_state.comparison_mode:
        return

    if selected_view == "📋 Table":
        left, right = st.columns([1.8, 1.4])

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
                    "Rank": st.column_config.NumberColumn(width="small", format="%d"),
                    "Artist": st.column_config.TextColumn(width="small"),
                    "Top Song": st.column_config.TextColumn(width="small"),
                    "Top Country": st.column_config.TextColumn(width="small"),
                    "Monthly Listeners": st.column_config.TextColumn(width="small"),  # Changed to TextColumn
                    "Peak Listeners": st.column_config.TextColumn(width="small"),     # Changed to TextColumn
                    "Trend": st.column_config.TextColumn(width="small"),
                },
            )

        with right:
            top_streams = leaderboard.dropna(subset=["monthly_listeners"]).nlargest(8, "monthly_listeners").copy()
            if not top_streams.empty:
                top_streams = top_streams.sort_values("monthly_listeners", ascending=True)
                top_streams["listener_label"] = top_streams["monthly_listeners"].apply(fmt_short)
                avg_listeners = top_streams["monthly_listeners"].mean()

                fig_bar = px.bar(
                    top_streams,
                    x="monthly_listeners",
                    y="name",
                    orientation="h",
                    text="listener_label",
                    color="monthly_listeners",
                    custom_data=["display_country", "rank"],
                    labels={"monthly_listeners": "Monthly listeners", "name": ""},
                    color_continuous_scale=["#1d4ed8", "#7c3aed", "#22d3a0"],
                )
                fig_bar.update_traces(
                    textposition="outside",
                    cliponaxis=False,
                    marker_line_color="rgba(255,255,255,.18)",
                    marker_line_width=1.1,
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Monthly listeners: %{x:,.0f}<br>"
                        "Top LATAM market: %{customdata[0]}<br>"
                        "Current rank: #%{customdata[1]}<extra></extra>"
                    ),
                )
                fig_bar.add_vline(
                    x=avg_listeners,
                    line_dash="dash",
                    line_color="rgba(245,166,35,.9)",
                    annotation_text=f"Avg {fmt_short(avg_listeners)}",
                    annotation_position="top left",
                )
                fig_bar.update_layout(
                    title="Top Artists by Monthly Listeners",
                    coloraxis_showscale=False,
                    xaxis_title="Monthly listeners",
                    xaxis_tickformat="~s",
                    yaxis_title="",
                )
                style_figure(fig_bar, 360)
                st.plotly_chart(fig_bar, use_container_width=True, config=PLOTLY_CONFIG)

                country_mix = (
                    leaderboard.loc[leaderboard["display_country"].ne("—"), "display_country"]
                    .value_counts()
                    .head(6)
                    .reset_index()
                )
                if not country_mix.empty:
                    country_mix.columns = ["country", "artists"]
                    fig_country = px.pie(
                        country_mix,
                        names="country",
                        values="artists",
                        hole=0.58,
                        color="country",
                        color_discrete_sequence=CHART_COLORS,
                    )
                    fig_country.update_traces(
                        textposition="inside",
                        textinfo="percent+label",
                        hovertemplate="<b>%{label}</b><br>Artists: %{value}<extra></extra>",
                    )
                    fig_country.update_layout(
                        title="LATAM Presence by Top Country",
                        showlegend=False,
                        annotations=[
                            dict(
                                text="Market<br>mix",
                                x=0.5,
                                y=0.5,
                                showarrow=False,
                                font=dict(size=13, color="#cbd5f5"),
                            )
                        ],
                    )
                    style_figure(fig_country, 290)
                    st.plotly_chart(fig_country, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.info("No monthly listener data is available for the current leaderboard selection.")

    elif selected_view == "📈 Analysis":
        st.markdown(
            "<div class='section-sub'>Explore cleaner views of leaderboard concentration and market reach.</div>",
            unsafe_allow_html=True,
        )

        control_col1, control_col2 = st.columns([1.3, 1.3])
        with control_col1:
            relationship_view = st.selectbox(
                "Relationship View",
                ["Density Heatmap", "Bubble Scatter"],
                index=0,
                key="analysis_relationship_view",
            )
        with control_col2:
            top_n = int(
                st.slider(
                    "Artists to include (default: all)",
                    min_value=1,
                    max_value=max(1, len(leaderboard)),
                    value=max(1, len(leaderboard)),
                    step=1,
                    key="analysis_top_n",
                )
            )

        analysis_df = leaderboard.dropna(subset=["rank"]).sort_values("rank").head(max(1, top_n)).copy()
        analysis_df["rank"] = pd.to_numeric(analysis_df["rank"], errors="coerce")
        analysis_df["monthly_listeners"] = pd.to_numeric(analysis_df["monthly_listeners"], errors="coerce")
        analysis_df["countries_count"] = pd.to_numeric(analysis_df["countries_count"], errors="coerce")

        col_a, col_b = st.columns(2)

        with col_a:
            bins = [0, 5, 10, 20, 50, 100]
            labels = ["Top 5", "6-10", "11-20", "21-50", "51-100"]
            analysis_df["rank_bucket"] = pd.cut(
                analysis_df["rank"],
                bins=bins,
                labels=labels,
                include_lowest=True,
                right=True,
            )
            rank_dist = (
                analysis_df["rank_bucket"]
                .value_counts()
                .reindex(labels, fill_value=0)
                .rename_axis("Rank Range")
                .reset_index(name="Artists")
            )

            total_artists = int(rank_dist["Artists"].sum())
            rank_dist["Share"] = (rank_dist["Artists"] / total_artists * 100).round(1) if total_artists else 0
            rank_dist = rank_dist.sort_values("Artists", ascending=True)

            tier_colors = {
                "Top 5": "#22d3a0",
                "6-10": "#4f8ef7",
                "11-20": "#7c5cfc",
                "21-50": "#f5a623",
                "51-100": "#e84545",
            }

            fig_dist = go.Figure(
                data=[
                    go.Bar(
                        x=rank_dist["Artists"],
                        y=rank_dist["Rank Range"],
                        orientation="h",
                        marker=dict(
                            color=rank_dist["Rank Range"].map(tier_colors),
                            line=dict(color="rgba(255,255,255,.18)", width=1),
                        ),
                        text=[f"{c} ({p:.1f}%)" for c, p in zip(rank_dist["Artists"], rank_dist["Share"])],
                        textposition="outside",
                        cliponaxis=False,
                        customdata=rank_dist[["Share"]].to_numpy(),
                        hovertemplate="<b>%{y}</b><br>Artists: %{x}<br>Share: %{customdata[0]:.1f}%<extra></extra>",
                    )
                ]
            )

            if total_artists > 0:
                expected_per_tier = total_artists / max(1, len(labels))
                fig_dist.add_vline(
                    x=expected_per_tier,
                    line_dash="dot",
                    line_color="rgba(151,163,197,.85)",
                    annotation_text="even split",
                    annotation_position="top right",
                )

            fig_dist.update_layout(
                title="Rank Tier Distribution",
                showlegend=False,
                xaxis_title="Artists",
                yaxis_title="",
                margin=dict(l=8, r=12, t=64, b=8),
            )
            fig_dist.update_xaxes(dtick=1, rangemode="tozero")
            style_figure(fig_dist, 360)
            st.plotly_chart(fig_dist, use_container_width=True, config=PLOTLY_CONFIG)

            if total_artists > 0:
                dominant_tier = rank_dist.loc[rank_dist["Artists"].idxmax()]
                dominant_tier_name = str(dominant_tier["Rank Range"])
                top_10_count = int(
                    rank_dist.loc[rank_dist["Rank Range"].isin(["Top 5", "6-10"]), "Artists"].sum()
                )
                top_10_share = (top_10_count / total_artists * 100) if total_artists else 0

                dominant_tier_artists = (
                    analysis_df.loc[analysis_df["rank_bucket"].astype(str) == dominant_tier_name, "name"]
                    .dropna()
                    .astype(str)
                    .sort_values()
                    .tolist()
                )
                top_10_artists = (
                    analysis_df.loc[analysis_df["rank_bucket"].astype(str).isin(["Top 5", "6-10"]), ["rank", "name"]]
                    .dropna(subset=["name", "rank"])
                    .sort_values("rank")
                )

                dominant_preview = ", ".join(dominant_tier_artists[:6])
                if len(dominant_tier_artists) > 6:
                    dominant_preview += f" (+{len(dominant_tier_artists) - 6} more)"

                top_10_names = ", ".join(top_10_artists["name"].astype(str).tolist())
                st.markdown(
                    (
                        "<div class='small-note'>"
                        f"Summary: Most artists are in <b>{escape(dominant_tier_name)}</b> "
                        f"({int(dominant_tier['Artists'])} artists, {float(dominant_tier['Share']):.1f}%). "
                        f"Artists in this tier: <b>{escape(dominant_preview) if dominant_preview else 'N/A'}</b>. "
                        f"Overall, <b>{top_10_count}</b> artists ({top_10_share:.1f}%) are in the top 10 tiers: "
                        f"<b>{escape(top_10_names) if top_10_names else 'N/A'}</b>."
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

        with col_b:
            scatter_data = analysis_df.dropna(subset=["monthly_listeners", "countries_count"])
            if scatter_data.empty:
                st.info("Not enough listener and country coverage data to render analysis charts.")
            elif relationship_view == "Density Heatmap":
                heatmap_df = scatter_data.copy()
                heatmap_df["countries_count"] = heatmap_df["countries_count"].round().astype(int)

                quantiles = min(5, int(heatmap_df["monthly_listeners"].nunique()))
                if quantiles >= 2:
                    heatmap_df["listener_band"] = pd.qcut(
                        heatmap_df["monthly_listeners"],
                        q=quantiles,
                        duplicates="drop",
                    )
                    band_categories = list(heatmap_df["listener_band"].cat.categories)
                    band_labels = {
                        band: f"{fmt_short(band.left)}-{fmt_short(band.right)}"
                        for band in band_categories
                    }
                    ordered_band_labels = [band_labels[band] for band in band_categories[::-1]]
                    heatmap_df["listener_band_label"] = (
                        heatmap_df["listener_band"]
                        .map(band_labels)
                        .astype(pd.CategoricalDtype(categories=ordered_band_labels, ordered=True))
                    )
                else:
                    single_label = f"{fmt_short(heatmap_df['monthly_listeners'].min())}-{fmt_short(heatmap_df['monthly_listeners'].max())}"
                    heatmap_df["listener_band_label"] = single_label

                heatmap_matrix = heatmap_df.pivot_table(
                    index="listener_band_label",
                    columns="countries_count",
                    values="rank",
                    aggfunc="mean",
                    observed=False,
                ).sort_index()

                fig_heatmap = go.Figure(
                    data=[
                        go.Heatmap(
                            x=heatmap_matrix.columns.astype(str).tolist(),
                            y=heatmap_matrix.index.astype(str).tolist(),
                            z=heatmap_matrix.values,
                            colorscale=[
                                [0.0, "#f8d7c5"],
                                [0.2, "#f4b8a0"],
                                [0.4, "#ef8e71"],
                                [0.6, "#e45d4a"],
                                [0.8, "#c92f31"],
                                [1.0, "#8f0f22"],
                            ],
                            colorbar=dict(title="Avg Rank"),
                            xgap=1,
                            ygap=1,
                            hovertemplate="LATAM Countries: %{x}<br>Listener Band: %{y}<br>Avg Rank: %{z:.1f}<extra></extra>",
                        )
                    ]
                )
                fig_heatmap.update_layout(
                    title="Reach vs. Monthly Listeners (Rank Heatmap)",
                    xaxis_title="LATAM Countries",
                    yaxis_title="Monthly Listener Band",
                )
                fig_heatmap.update_xaxes(side="top")
                style_figure(fig_heatmap, 360)
                st.plotly_chart(fig_heatmap, use_container_width=True, config=PLOTLY_CONFIG)

                if not heatmap_matrix.empty:
                    best_zone = heatmap_matrix.stack(future_stack=True).dropna()
                    if not best_zone.empty:
                        best_idx = best_zone.idxmin()
                        best_avg_rank = float(best_zone.min())
                        zone_listener_band = str(best_idx[0])
                        zone_countries = int(best_idx[1])
                        zone_artists = (
                            heatmap_df.loc[
                                (heatmap_df["listener_band_label"].astype(str) == zone_listener_band)
                                & (heatmap_df["countries_count"] == zone_countries),
                                "name",
                            ]
                            .dropna()
                            .astype(str)
                            .sort_values()
                            .tolist()
                        )
                        zone_artist_preview = ", ".join(zone_artists[:6])
                        if len(zone_artists) > 6:
                            zone_artist_preview += f" (+{len(zone_artists) - 6} more)"
                        st.markdown(
                            (
                                "<div class='small-note'>"
                                f"Summary: The strongest zone is <b>{escape(zone_listener_band)}</b> listeners with "
                                f"<b>{zone_countries}</b> LATAM countries, where the average rank is about "
                                f"<b>#{best_avg_rank:.1f}</b> (lower is better). "
                                f"Artists in this zone: <b>{escape(zone_artist_preview) if zone_artist_preview else 'N/A'}</b>."
                                "</div>"
                            ),
                            unsafe_allow_html=True,
                        )
            else:
                fig_scatter = px.scatter(
                    scatter_data,
                    x="countries_count",
                    y="monthly_listeners",
                    size="monthly_listeners",
                    color="rank",
                    hover_name="name",
                    title="Reach vs. Monthly Listeners (Artist View)",
                    labels={"countries_count": "LATAM Countries", "monthly_listeners": "Monthly Listeners", "rank": "Rank"},
                    color_continuous_scale=["#22d3a0", "#f5a623", "#e84545"],
                    size_max=26,
                )
                fig_scatter.update_traces(
                    marker=dict(line=dict(color="rgba(255,255,255,.22)", width=1)),
                    hovertemplate="<b>%{hovertext}</b><br>Countries: %{x}<br>Listeners: %{y:,.0f}<br>Rank: %{marker.color:.0f}<extra></extra>",
                )
                fig_scatter.update_yaxes(tickformat="~s")
                style_figure(fig_scatter, 360)
                st.plotly_chart(fig_scatter, use_container_width=True, config=PLOTLY_CONFIG)

                reach_corr = scatter_data["countries_count"].corr(scatter_data["monthly_listeners"])
                median_reach = float(scatter_data["countries_count"].median()) if not scatter_data.empty else 0
                max_reach = int(scatter_data["countries_count"].max()) if not scatter_data.empty else 0
                if pd.notna(reach_corr):
                    corr_text = "positive" if reach_corr > 0 else "negative" if reach_corr < 0 else "flat"
                    st.markdown(
                        (
                            "<div class='small-note'>"
                            f"Summary: This view shows a <b>{corr_text}</b> relationship between LATAM reach and monthly listeners "
                            f"(correlation {reach_corr:.2f}). Median reach is <b>{median_reach:.0f}</b> countries, "
                            f"with a maximum of <b>{max_reach}</b>."
                            "</div>"
                        ),
                        unsafe_allow_html=True,
                    )

    else:
        st.markdown("### 🎯 Artist Detail Spotlight")
        artists = leaderboard["name"].dropna().tolist()

        selected_artist = st.selectbox("🔍 Choose an artist", artists, index=0)

        if selected_artist:
            row = leaderboard.loc[leaderboard["name"] == selected_artist].iloc[0]

            # Single frame containing all artist details, including counts
            with st.expander("📋 View Artist Details", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🎵 Songs", int(row.get("songs_count") or 0))
                c2.metric("💿 Albums", int(row.get("albums_count") or 0))
                c3.metric("🌎 LATAM Countries", int(row.get("countries_count") or 0))
                c4.metric("👥 Monthly Listeners", fmt_short(row.get("monthly_listeners") or 0))

                songs_items = [item.strip() for item in str(row.get("top_songs") or "").split("\n") if item.strip()]
                albums_items = [item.strip() for item in str(row.get("top_albums") or "").split("\n") if item.strip()]
                countries_items = [item.strip() for item in str(row.get("top_countries") or "").split("\n") if item.strip()]

                profile_title = str(row.get("page_title") or "").strip()
                profile_snapshot = str(row.get("snapshot_text") or "").strip()
                rank_value = int(row.get("rank")) if pd.notna(row.get("rank")) else 0

                def safe_text(value: object) -> str:
                    if value is None or pd.isna(value):
                        return "—"
                    text = str(value).strip()
                    return text if text else "—"

                if profile_title:
                    st.markdown(f"#### 🪪 {escape(profile_title)}")
                if profile_snapshot:
                    st.caption(profile_snapshot)

                meta_left, meta_right = st.columns(2)
                with meta_left:
                    st.markdown(f"**📈 Current Rank:** #{rank_value}")
                    st.markdown(f"**🌍 Top Country:** {safe_text(row.get('display_country'))}")
                with meta_right:
                    st.markdown(f"**⭐ Total Points:** {fmt_short(row.get('total_points') or 0)}")
                    st.markdown(f"**📊 Peak Listeners:** {fmt_short(row.get('peak_listeners') or 0)}")

                left_list, mid_list, right_list = st.columns(3)
                with left_list:
                    st.markdown("#### 🎵 Top Songs")
                    if songs_items:
                        st.markdown("\n".join(f"{idx}. {item}" for idx, item in enumerate(songs_items, start=1)))
                    else:
                        st.caption("No songs available.")

                with mid_list:
                    st.markdown("#### 💿 Top Albums")
                    if albums_items:
                        st.markdown("\n".join(f"{idx}. {item}" for idx, item in enumerate(albums_items, start=1)))
                    else:
                        st.caption("No albums available.")

                with right_list:
                    st.markdown("#### 🗺️ Top Countries")
                    if countries_items:
                        st.markdown("\n".join(f"{idx}. {item}" for idx, item in enumerate(countries_items, start=1)))
                    else:
                        st.caption("No countries available.")

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
        best_df_plot = best_df.copy()
        max_best_position = int(best_df_plot["best_position"].max())
        best_df_plot["position_score"] = max_best_position + 1 - best_df_plot["best_position"]
        best_df_plot = best_df_plot.sort_values("best_position", ascending=True)

        bar_colors = [CHART_COLORS[idx % len(CHART_COLORS)] for idx in range(len(best_df_plot))]
        fig_best = go.Figure(
            data=[
                go.Bar(
                    x=best_df_plot["position_score"],
                    y=best_df_plot["artist"],
                    orientation="h",
                    marker=dict(color=bar_colors, line=dict(width=0)),
                    text=[f"#{int(v)}" for v in best_df_plot["best_position"]],
                    textposition="outside",
                    cliponaxis=False,
                    customdata=best_df_plot[["best_position"]].to_numpy(),
                    hovertemplate="<b>%{y}</b><br>Score: %{x:.0f}<br>Best position: #%{customdata[0]}<extra></extra>",
                )
            ]
        )
        style_figure(fig_best, max(380, 34 * len(best_df) + 80))
        fig_best.update_layout(
            title=dict(text="🏆 Best Recent Positions", x=0.03, xanchor="left", font=dict(size=18)),
            showlegend=False,
            yaxis_title="",
            margin=dict(l=70, r=20, t=70, b=40),
            bargap=0.35,
        )
        fig_best.update_xaxes(dtick=1, showgrid=False, range=[0, max_best_position + 1.3])
        fig_best.update_yaxes(
            autorange="reversed",
            categoryorder="array",
            categoryarray=best_df_plot["artist"].tolist(),
            ticklabelstandoff=18,
        )
        st.plotly_chart(fig_best, use_container_width=True, config=PLOTLY_CONFIG)
    
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
        trends_df.columns = ["Rank", "Artist", "Monthly Listeners", "Peak Listeners", "Top LATAM Country", "LATAM Countries"]
        st.dataframe(
            trends_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Monthly Listeners": st.column_config.TextColumn(width="small"),
                "Peak Listeners": st.column_config.TextColumn(width="small"),
                "Rank": st.column_config.NumberColumn(format="%d"),
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
    tab1, tab2, tab3 = st.tabs(["📊 Overview", "📜 History", "🔍 Analytics"])
    
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


def render_chatbot_widget() -> None:
        st_components.html(
                f"""
                <script>
                (function() {{
                    const BOT_SRC = {BOT_SRC!r};
                    const LOAD_TIMEOUT_MS = {LOAD_TIMEOUT_MS};
                    const IFRAME_TOP_CROP_PX = 88;
                    const ROOT_ID = "a360-chatbot-root";
                    const STYLE_ID = "a360-chatbot-style";

                    const doc = window.parent.document;

                    if (!doc.getElementById(STYLE_ID)) {{
                        const style = doc.createElement("style");
                        style.id = STYLE_ID;
                        style.textContent = `
                            .a360-chatbot-toggle {{
                                position: fixed;
                                right: 24px;
                                bottom: 24px;
                                width: 62px;
                                height: 62px;
                                border: none;
                                border-radius: 999px;
                                cursor: pointer;
                                z-index: 10010;
                                color: #ffffff;
                                font-size: 30px;
                                line-height: 1;
                                background: linear-gradient(135deg, #4f8ef7 0%, #7c5cfc 60%, #22d3a0 100%);
                                box-shadow: 0 14px 36px rgba(79, 142, 247, 0.35);
                            }}
                            .a360-chatbot-toggle:hover {{
                                transform: translateY(-2px);
                            }}
                            .a360-chatbot-container {{
                                position: fixed;
                                width: min(400px, calc(100vw - 48px));
                                height: min(650px, calc(100vh - 120px));
                                min-height: 460px;
                                border-radius: 16px;
                                overflow: hidden;
                                border: 1px solid #293455;
                                background: #11182c;
                                box-shadow: 0 30px 65px rgba(0, 0, 0, 0.45);
                                z-index: 10011;
                            }}
                            .a360-chatbot-mobile {{
                                left: 16px !important;
                                right: 16px !important;
                                top: 80px !important;
                                bottom: 16px !important;
                                width: auto !important;
                                height: auto !important;
                                min-height: 0;
                            }}
                            .a360-chatbot-header {{
                                height: 58px;
                                padding: 0 12px;
                                display: flex;
                                align-items: center;
                                justify-content: space-between;
                                background: linear-gradient(135deg, #4f8ef7 0%, #7c5cfc 60%, #22d3a0 100%);
                                color: #ffffff;
                                cursor: grab;
                                user-select: none;
                                font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;
                                position: relative;
                                z-index: 2;
                            }}
                            .a360-chatbot-title {{
                                display: flex;
                                align-items: center;
                                gap: 10px;
                                font-weight: 700;
                                font-size: 14px;
                            }}
                            .a360-chatbot-actions {{
                                display: flex;
                                gap: 8px;
                            }}
                            .a360-chatbot-btn {{
                                width: 32px;
                                height: 32px;
                                border-radius: 999px;
                                border: 1px solid rgba(255, 255, 255, 0.35);
                                background: rgba(0, 0, 0, 0.12);
                                color: #fff;
                                font-size: 16px;
                                cursor: pointer;
                            }}
                            .a360-chatbot-window {{
                                position: relative;
                                height: calc(100% - 58px);
                                background: #0a1123;
                                overflow: hidden;
                                z-index: 1;
                            }}
                            .a360-chatbot-iframe {{
                                position: relative;
                                top: 0;
                                width: 100%;
                                height: 100%;
                                border: none;
                                opacity: 0;
                                transition: opacity 0.3s ease;
                            }}
                            .a360-chatbot-overlay {{
                                position: absolute;
                                inset: 0;
                                display: flex;
                                flex-direction: column;
                                align-items: center;
                                justify-content: center;
                                text-align: center;
                                color: #dce6ff;
                                padding: 24px;
                                font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;
                            }}
                            .a360-chatbot-spinner {{
                                width: 36px;
                                height: 36px;
                                border-radius: 999px;
                                border: 3px solid rgba(255,255,255,0.18);
                                border-top-color: #7da9ff;
                                animation: a360spin 0.9s linear infinite;
                                margin-bottom: 12px;
                            }}
                            .a360-chatbot-error-btn {{
                                margin-top: 12px;
                                border: 1px solid #4f8ef7;
                                color: #e8f0ff;
                                background: rgba(79,142,247,0.15);
                                border-radius: 8px;
                                padding: 8px 12px;
                                cursor: pointer;
                            }}
                            @keyframes a360spin {{
                                from {{ transform: rotate(0deg); }}
                                to {{ transform: rotate(360deg); }}
                            }}
                        `;
                        doc.head.appendChild(style);
                    }}

                    let root = doc.getElementById(ROOT_ID);
                    if (!root) {{
                        root = doc.createElement("div");
                        root.id = ROOT_ID;
                        doc.body.appendChild(root);
                    }}

                    root.innerHTML = "";

                    const margin = 24;
                    const containerWidth = Math.min(400, window.parent.innerWidth - margin * 2);
                    const containerHeight = Math.min(650, window.parent.innerHeight - 140);
                    const state = {{
                        open: false,
                        iframeKey: 0,
                        status: "idle",
                        isDragging: false,
                        dragStartX: 0,
                        dragStartY: 0,
                        x: Math.max(margin, window.parent.innerWidth - containerWidth - margin),
                        y: Math.max(margin, window.parent.innerHeight - containerHeight - margin),
                        timer: null,
                    }};

                    const isMobile = () => window.parent.matchMedia("(max-width: 480px)").matches;

                    const clearTimer = () => {{
                        if (state.timer) {{
                            clearTimeout(state.timer);
                            state.timer = null;
                        }}
                    }};

                    const startBotLoad = () => {{
                        state.status = "loading";
                        clearTimer();
                        state.timer = setTimeout(() => {{
                            state.status = "error";
                            render();
                        }}, LOAD_TIMEOUT_MS);
                    }};

                    const createIframe = () => {{
                        const iframe = doc.createElement("iframe");
                        iframe.className = "a360-chatbot-iframe";
                        iframe.style.top = `-${{IFRAME_TOP_CROP_PX}}px`;
                        iframe.style.height = `calc(100% + ${{IFRAME_TOP_CROP_PX}}px)`;
                        iframe.title = "AI Artist Assistant";
                        iframe.allow = "microphone; camera";
                        iframe.src = BOT_SRC + "&iframeKey=" + state.iframeKey;
                        iframe.onload = () => {{
                            clearTimer();
                            state.status = "ready";
                            iframe.style.opacity = "1";
                            const overlay = root.querySelector(".a360-chatbot-overlay");
                            if (overlay) overlay.style.display = "none";
                        }};
                        return iframe;
                    }};

                    const openChat = () => {{
                        state.open = true;
                        startBotLoad();
                        render();
                    }};

                    const closeChat = () => {{
                        clearTimer();
                        state.open = false;
                        state.status = "idle";
                        state.isDragging = false;
                        render();
                    }};

                    const retryChat = () => {{
                        state.iframeKey += 1;
                        startBotLoad();
                        render();
                    }};

                    const onMouseMove = (e) => {{
                        if (!state.isDragging || !state.open || isMobile()) return;
                        const container = root.querySelector(".a360-chatbot-container");
                        if (!container) return;
                        const maxX = window.parent.innerWidth - (container.offsetWidth || 450);
                        const maxY = window.parent.innerHeight - (container.offsetHeight || 520);
                        state.x = Math.max(0, Math.min(e.clientX - state.dragStartX, maxX));
                        state.y = Math.max(0, Math.min(e.clientY - state.dragStartY, maxY));
                        container.style.left = state.x + "px";
                        container.style.top = state.y + "px";
                    }};

                    const onMouseUp = () => {{
                        state.isDragging = false;
                        doc.body.style.userSelect = "";
                        doc.body.style.cursor = "";
                    }};

                    const buildOverlay = () => {{
                        const overlay = doc.createElement("div");
                        overlay.className = "a360-chatbot-overlay";

                        if (state.status === "error") {{
                            overlay.innerHTML = `
                                <div style="font-size: 30px; margin-bottom: 8px;">⚠️</div>
                                <div>Unable to connect to the AI Assistant. The service may be temporarily unavailable or the session has expired.</div>
                                <button class="a360-chatbot-error-btn">Try Again</button>
                            `;
                            overlay.querySelector("button").addEventListener("click", retryChat);
                            return overlay;
                        }}

                        overlay.innerHTML = `
                            <div class="a360-chatbot-spinner"></div>
                            <div>Loading AI Assistant...</div>
                        `;
                        return overlay;
                    }};

                    const render = () => {{
                        root.innerHTML = "";

                        if (!state.open) {{
                            const toggle = doc.createElement("button");
                            toggle.className = "a360-chatbot-toggle";
                            toggle.setAttribute("aria-label", "Open Artist Bot");
                            toggle.setAttribute("title", "Chat with our AI assistant");
                            toggle.textContent = "🤖";
                            toggle.addEventListener("click", openChat);
                            root.appendChild(toggle);
                            return;
                        }}

                        const container = doc.createElement("div");
                        container.className = "a360-chatbot-container";

                        if (isMobile()) {{
                            container.classList.add("a360-chatbot-mobile");
                        }} else {{
                            container.style.left = state.x + "px";
                            container.style.top = state.y + "px";
                        }}

                        const header = doc.createElement("div");
                        header.className = "a360-chatbot-header";

                        header.innerHTML = `
                            <div class="a360-chatbot-title"><span style="font-size: 20px;">🤖</span><span>AI Artist Assistant</span></div>
                            <div class="a360-chatbot-actions">
                                <button class="a360-chatbot-btn" aria-label="Reload chat" title="Reload chat">↺</button>
                                <button class="a360-chatbot-btn" aria-label="Close chat" title="Close chat">✕</button>
                            </div>
                        `;

                        const buttons = header.querySelectorAll("button");
                        buttons[0].addEventListener("click", retryChat);
                        buttons[1].addEventListener("click", closeChat);

                        header.addEventListener("mousedown", (e) => {{
                            if (isMobile()) return;
                            state.isDragging = true;
                            const rect = container.getBoundingClientRect();
                            state.dragStartX = e.clientX - rect.left;
                            state.dragStartY = e.clientY - rect.top;
                            doc.body.style.userSelect = "none";
                            doc.body.style.cursor = "grabbing";
                            e.preventDefault();
                        }});

                        const win = doc.createElement("div");
                        win.className = "a360-chatbot-window";
                        const iframe = createIframe();
                        win.appendChild(iframe);

                        if (state.status === "loading" || state.status === "error") {{
                            win.appendChild(buildOverlay());
                        }}

                        container.appendChild(header);
                        container.appendChild(win);
                        root.appendChild(container);
                    }};

                    doc.removeEventListener("mousemove", onMouseMove);
                    doc.removeEventListener("mouseup", onMouseUp);
                    doc.addEventListener("mousemove", onMouseMove);
                    doc.addEventListener("mouseup", onMouseUp);

                    window.parent.addEventListener("resize", () => {{
                        if (!state.open) return;
                        render();
                    }});

                    render();
                }})();
                </script>
                """,
                height=0,
                width=0,
        )
        


apply_theme()

_skeleton_slot = st.empty()
with _skeleton_slot.container():
    render_dashboard_skeleton()

try:
    data = load_dashboard_data()
except Exception as exc:  # pragma: no cover
    _skeleton_slot.empty()
    st.error(f"❌ Failed to load dashboard data: {exc}")
    st.stop()

_skeleton_slot.empty()

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
    st.Page(
        show_leaderboard_page,
        title="Leaderboard",
        icon=":material/trending_up:",
        url_path="leaderboard",
        default=True,
    ),
    st.Page(
        show_chart_tracker_page,
        title="Chart Tracker",
        icon=":material/desktop_windows:",
        url_path="chart-tracker",
    ),
    st.Page(
        show_stream_trends_page,
        title="Stream Trends",
        icon=":material/show_chart:",
        url_path="stream-trends",
    ),
    st.Page(
        show_ops_monitor_page,
        title="Ops Monitor",
        icon=":material/tune:",
        url_path="ops-monitor",
    ),
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
        artist_options = ["All artists"] + sorted(leaderboard["name"].dropna().unique().tolist())
        selected_artist = st.selectbox("🎤 Artist search", artist_options, index=0)
        latam_only = st.toggle("🌎 Latin America", value=True)
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
    if selected_artist != "All artists":
        filtered = filtered[filtered["name"] == selected_artist]
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
render_footer()
render_chatbot_widget()

# Auto-refresh functionality
if st.session_state.auto_refresh:
    import time
    time.sleep(30)
    st.rerun()
