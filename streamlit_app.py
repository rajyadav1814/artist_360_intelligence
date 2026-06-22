from __future__ import annotations

import json
from html import escape
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as st_components

from src.ai.custom_chatbot import render_custom_chatbot
from src.ai.label_dashboard import render_pulse_report
from src.ai.debut_dashboard import render_debut_tab, prefetch_debut_data
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx
from src.ai.track_movement_dashboard import render_track_movement
from src.ai.album_movement_dashboard import render_album_movement
from src.ai.artist_spotlight_dashboard import render_debut_artist_chart
from src.ai.artist_movement_dashboard import render_chart_tracker
from src.ai.artists_overview_dashboard import render_artists_overview, prefetch_artists_overview_data
from src.ai.acquisition_dashboard import (
    render_acquisition,
    _load_daily,
    _load_artist_universe,
    _load_spotify_artist_series,
    _load_itunes_artist_series,
    _build_artist_payloads,
    _fmt_n as acq_fmt_n,
    WINDOW_DAYS,
)
from src.ai.redesign_dashboard import render_redesign_dashboard
from src.ai.track_acquisition_dashboard import render_track_acquisition
from src.ai.album_acquisition_dashboard import render_album_acquisition
from src.ai.label_analysis_dashboard import LABEL_NORM
from src.database.connection import get_connection
from src.scrapers.artist_details_scraper import LATIN_AMERICAN_COUNTRIES
from src.utils.image_utils import get_artist_image_url, get_fallback_avatar_url
from src.utils.ui import custom_selectbox, custom_multiselect


st.set_page_config(
    page_title="Artist 360° Intelligence",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide the Streamlit chrome so the live app doesn't show the top-right toolbar.
st.markdown(
    """
    <style>
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        header[data-testid="stHeader"],
        [data-testid="stStatusWidget"],
        [data-testid="stHostedBadge"],
        [data-testid="viewerBadge"],
        [data-testid="stDeployButton"],
        .viewerBadge_container,
        .viewerBadge_link,
        .viewerBadge_text,
        .stDeployButton,
        div[class*="viewerBadge"],
        a[href*="streamlit.io/cloud"],
        a[href*="share.streamlit.io"],
        #MainMenu,
        footer {
            display: none !important;
            visibility: hidden !important;
            pointer-events: none !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize session state for interactivity
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False
if "selected_artists" not in st.session_state:
    st.session_state.selected_artists = []
if "show_advanced" not in st.session_state:
    st.session_state.show_advanced = False
# ── Persistent Theme Management ─────────────────────────────
# 1. Check URL parameters first (e.g. from toggle)
if "theme" in st.query_params:
    st.session_state.dark_mode = st.query_params["theme"] == "dark"
# 2. Check cookies to avoid the redirect flicker on refresh (only if not already set)
elif "dark_mode" not in st.session_state:
    if hasattr(st, "context") and hasattr(st.context, "cookies") and "theme" in st.context.cookies:
        st.session_state.dark_mode = st.context.cookies["theme"] == "dark"
    # 3. Fallback to default
    else:
        st.session_state.dark_mode = False

if "active_artist_profile" not in st.session_state:
    st.session_state.active_artist_profile = None

# Inject JS to sync theme with localStorage AND Cookies
st_components.html(
    f"""
    <script>
        const urlParams = new URLSearchParams(window.parent.location.search);
        const urlTheme = urlParams.get('theme');
        let storedTheme = window.parent.localStorage.getItem('theme');
        
        // If URL has a theme (e.g., from toggle), update local storage first
        if (urlTheme && urlTheme !== storedTheme) {{
            window.parent.localStorage.setItem('theme', urlTheme);
            storedTheme = urlTheme;
        }}

        const currentPythonTheme = "{ 'dark' if st.session_state.dark_mode else 'light' }";
        
        // Always check theme in local storage based on that change Python state if needed
        if (storedTheme && storedTheme !== currentPythonTheme) {{
            urlParams.set('theme', storedTheme);
            window.parent.location.search = urlParams.toString();
        }} else if (storedTheme) {{
            // Keep cookies synced for Python to read on next load
            window.parent.document.cookie = `theme=${{storedTheme}}; path=/; max-age=31536000`;
        }}
    </script>
    """,
    height=0,
    width=0,
)

PAGE_META = {
    "Leaderboard": (
        "🏆 Artist 360° Leaderboard",
        "Top Latin artists ranked by iTunes performance, Spotify reach, and global footprint",
    ),
    "Artists Overview": (
        "🎤 Artists Overview",
        "Catalog, chart activity, listeners, and top artist table from your stored artist data",
    ),
    "Redesign Lab": (
        "🧪 Redesign Lab",
        "Story-first acquisition, fatigue, and roster health prototype inspired by the redesign deck",
    ),
    "Artist Spotlight": (
        "🎤 Artist Spotlight",
        "View and analyze individual artist details and chart performance",
    ),

    # "Stream Trends": (
    #     "🎵 Stream Trends",
    #     "Insights into streaming performance, growth patterns, and listener demographics",
    # ),
    "AI Data Analyst": (
        "🤖 AI Data Analyst",
        "Ask natural-language questions and get content + charts (Powered by Table Details Bot)",
    ),
    "Label Analysis": (
        "🏷️ Label Analysis",
        "Label-level market share, track concentration, and competitive performance across Spotify and iTunes",
    ),
    # "Pulse Report": (
    #     "📊 Pulse Report",
    #     "Track performance by record label, market acquisition, and chart movement",
    # ),
    "Ops Monitor": (
        "⚙️ Ops Monitor",
        "Operational dashboard showing recent data collection runs, their status, and performance metrics",
    ),
    # "Debut Report": (
    #     "🌟 Debut Report",
    #     "Tracks all new chart entries across Spotify and iTunes for the current week",
    # ),
    "Movement": (
        "📊 Movement Dashboard",
        "Daily rank + metric momentum across track and album charts (risers, fallers, trajectories)",
    ),
    "Track Acquisition": (
        "🎯 Track Acquisition",
        "Track-level acquisition intelligence across Spotify Global + iTunes WW",
    ),
    "Acquisition": (
        "💡 Acquisition Recommendation",
        "Composite acquisition signals across Spotify Global + iTunes WW for every charting artist",
    ),
}

CHART_COLORS = ["#fb7185", "#60a5fa", "#34d399", "#c4b5fd", "#fcd34d", "#5eead4", "#f9a8d4", "#84cc16", "#f97316", "#a855f7"]
PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}
TRACKER_TOP_ARTISTS = 10
LATAM_COUNTRIES = sorted(LATIN_AMERICAN_COUNTRIES)
BOT_SRC = "https://copilotstudio.microsoft.com/environments/4b079cee-b5d6-e253-856d-c427359af206/bots/cr917_agentT1zDET/webchat?__version__=2"
LOAD_TIMEOUT_MS = 20000


def render_plotly_html(fig: go.Figure, *, height: int | None = None, dark_mode: bool | None = None) -> None:
    if dark_mode is None:
        dark_mode = st.session_state.get("dark_mode", False)

    chart_height = height or (int(fig.layout.height) if fig.layout.height else 520)
    fig.update_layout(
        template="plotly_dark" if dark_mode else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    chart_html = pio.to_html(
        fig,
        config=PLOTLY_CONFIG,
        full_html=False,
        include_plotlyjs="cdn",
        default_width="100%",
        default_height=f"{chart_height}px",
    )
    bg_color = "rgba(13, 17, 23, 0.95)" if dark_mode else "#FFFFFF"
    border_color = "rgba(108, 92, 231, 0.2)" if dark_mode else "rgba(108, 92, 231, 0.15)"
    shadow_color = "rgba(0, 0, 0, 0.22)" if dark_mode else "rgba(108, 92, 231, 0.05)"

    st_components.html(
        f"""
        <div class="graph-card">
            <div class="plotly-html-chart">{chart_html}</div>
        </div>
        <style>
            body {{ margin: 0; background: transparent; }}
            .graph-card {{
                width: 100%;
                box-sizing: border-box;
                padding: 10px 10px 6px 10px;
                border-radius: 20px;
                border: 1px solid {border_color};
                background: {bg_color};
                box-shadow: 0 4px 12px {shadow_color};
            }}
            .plotly-html-chart {{ width: 100%; }}
            .plotly-html-chart .js-plotly-plot,
            .plotly-html-chart .plot-container,
            .plotly-html-chart .svg-container {{ width: 100% !important; }}
        </style>
        <script>
            // Force a resize event shortly after load to fix Plotly legend squishing bugs
            setTimeout(() => {{
                window.dispatchEvent(new Event('resize'));
            }}, 300);
            setTimeout(() => {{
                window.dispatchEvent(new Event('resize'));
            }}, 1000);
        </script>
        """,
        height=chart_height + 32,
        scrolling=True,
    )


def apply_theme(dark_mode: bool = True) -> None:
    # ── CSS variable sets ───────────────────────────────────────────
    if dark_mode:
        # Dark theme – deep navy (previous style)
        root_vars = """
        :root {
            --bg:#0d1117; --surface:#161b26; --surface2:#1f2633; --surface3:#283041;
            --border:rgba(148,163,184,.35); --accent:#fb7185; --accent2:#60a5fa; --accent3:#34d399;
            --warn:#fcd34d; --danger:#fb7185; --text:#ffffff; --text2:#cdd6e4;
            --primary:#fb7185; --primary-light:#fda4af; --primary-dark:#be123c;
            --cyan:#60a5fa; --pink:#fb7185; --green:#34d399; --orange:#fcd34d;
        }"""
        # Extra dark overrides
        theme_extra = """
        [data-testid="stSidebarHeader"] {
            background: rgba(22,27,39,0.97) !important;
        }
        .dashboard-card {
            background: linear-gradient(180deg, rgba(22,27,39,1), rgba(26,32,53,1)) !important;
        }
        .kpi-card {
            background: linear-gradient(180deg, #161b26, #1f2633) !important;
        }
        .page-header-box {
            background: linear-gradient(135deg, #1a2238 0%, #1f1a3a 50%, #261d3d 100%) !important;
        }
        .leader-table thead th {
            background: rgba(22,27,39,0.97) !important;
        }
        .leader-table tbody tr:nth-child(even) {
            background: rgba(255,255,255,.02) !important;
        }
        .stTabs [data-baseweb="tab"] {
            background: var(--surface2) !important;
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(251,113,133,.22), rgba(196,181,253,.18)) !important;
        }
        .stPlotlyChart {
            background: var(--surface2) !important;
        }
        .tooltip .tooltiptext {
            background-color: rgba(22,27,39,0.99) !important;
            border-color: rgba(108,92,231,.40) !important;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5) !important;
        }
        .tooltip .tooltiptext::after {
            border-color: transparent transparent rgba(22,27,39,0.99) transparent !important;
        }
        .app-footer {
            background: rgba(13,17,23,0.97) !important;
            border-top-color: rgba(41,52,85,.5) !important;
        }
        .kpi-value {
            background: linear-gradient(135deg, #e2e8f0 0%, #a0aec0 100%) !important;
        }
        textarea, input, [data-baseweb="select"] > div {
            background: var(--surface2) !important;
        }
        .run-item {
            background: rgba(26,32,53,0.8) !important;
        }
        /* Selectbox and dropdown styling for dark mode - REMOVED (using custom HTML) */
        """
    else:
        # Light theme – clean white (current style)
        root_vars = """
        :root {
            --bg:#F5F6FA; --surface:#FFFFFF; --surface2:#F8F9FB; --surface3:#EEF1F7;
            --border:#9CA3AF; --accent:#fb7185; --accent2:#60a5fa; --accent3:#34d399;
            --warn:#fcd34d; --danger:#fb7185; --text:#1A1A1A; --text2:#8A8FA3;
            --primary:#fb7185; --primary-light:#fda4af; --primary-dark:#be123c;
            --cyan:#60a5fa; --pink:#fb7185; --green:#34d399; --orange:#fcd34d;
        }"""
        theme_extra = """
        [data-testid="stSidebarHeader"] {
            background: rgba(255,255,255,0.95) !important;
        }
        .dashboard-card {
            background: linear-gradient(180deg, rgba(255,255,255,1), rgba(248,249,251,1)) !important;
        }
        .kpi-card {
            background: linear-gradient(180deg, rgba(255,255,255,1), rgba(248,249,251,1)) !important;
        }
        .page-header-box {
            background: linear-gradient(120deg, rgba(255,255,255,1) 0%, rgba(248,249,251,1) 62%, rgba(240,244,250,1) 100%) !important;
        }
        .leader-table {
            border: 2px solid #fb7185 !important;
            border-radius: 12px !important;
            overflow: hidden !important;
        }
        .leader-table thead th {
            background: linear-gradient(135deg, #E5E7EB 0%, #FFFFFF 100%) !important;
            color: #1A1A1A !important;
            border-bottom: 2px solid rgba(251, 113, 133, 0.25) !important;
            font-weight: 900 !important;
        }
        .leader-table tbody tr {
            border-bottom: 1px solid rgba(251, 113, 133, 0.2) !important;
        }
        .leader-table tbody tr:nth-child(even) {
            background: rgba(251, 113, 133, 0.04) !important;
        }
        .leader-table tbody tr:hover {
            background: rgba(251, 113, 133, 0.12) !important;
        }
        .leader-table tbody td {
            color: #1A1A1A !important;
            font-weight: 500 !important;
        }
        .stTabs [data-baseweb="tab"] {
            background: var(--surface2) !important;
        }
        .tooltip .tooltiptext {
            background-color: rgba(255,255,255,0.99) !important;
        }
        .app-footer {
            background: rgba(255,255,255,0.97) !important;
        }
        .kpi-value {
            background: linear-gradient(135deg, #1A1A1A 0%, #4A4A4A 100%) !important;
        }
        /* Selectbox and dropdown styling for light mode */
        /* Removed - using custom HTML dropdowns instead */

        /* Fix toggle visibility in light mode */
        div[data-baseweb="checkbox"] > div:first-of-type,
        label[data-baseweb="checkbox"] > div:first-of-type {
            background-color: #cbd5e1 !important;
            border: 1px solid #94a3b8 !important;
        }

        div[data-baseweb="checkbox"] input:checked + div,
        label[data-baseweb="checkbox"] input:checked + div {
            background-color: var(--primary) !important;
            border: 1px solid var(--primary) !important;
        }
        """

    st.markdown(
        "<style>" + root_vars + """
        
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
            background: var(--bg); 
            color:var(--text);
            animation: fadeIn 0.6s ease-out;
        }
        body { font-size: 19px; }
        p, div, span, label { font-size: 1rem; }
        [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, header { background:transparent !important; }
        [data-testid="stDecoration"] { display:none; }
        .block-container {
            width: min(100%, 1680px);
            max-width: 1680px;
            padding-top: 3.5rem;
            padding-right: clamp(0.85rem, 1.8vw, 1.6rem);
            padding-left: clamp(0.85rem, 1.8vw, 1.6rem);
            padding-bottom: 6rem;
            margin-top: -6.5rem;
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
            background: var(--surface);
            border-right: 1px solid var(--border);
            transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        [data-testid="stSidebarHeader"] {
            position: sticky;
            top: 0;
            z-index: 100;
            min-height: 74px;
            padding: 1rem 3rem .9rem 1rem;
            border-bottom: 1px solid var(--border);
            background: rgba(255,255,255,0.95) !important;
            backdrop-filter: blur(16px);
        }
        [data-testid="stSidebarHeader"]::before {
            content:"🎵";
            position:absolute; left:1rem; top:1rem;
            width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
            font-size:1.15rem; font-weight:900; color:#fff;
            background:linear-gradient(135deg, #fb7185 0%, #f43f5e 55%, #be123c 100%);
            box-shadow:0 10px 24px rgba(251,113,133,.35);
        }
        [data-testid="stSidebarHeader"]::after {
            content:"Artist 360° Intelligence";
            position:absolute; left:4.25rem; top:1.35rem;
            right:3.25rem; color:var(--text); font-size:1.15rem; font-weight:800;
            letter-spacing:.2px; line-height:1.15;
        }
        [data-testid="stSidebarNav"] { display:none !important; }
        .app-side-nav {
            display:flex;
            flex-direction:column;
            gap:8px;
            padding:.75rem .75rem 1rem;
        }
        .app-side-link {
            display:flex;
            align-items:center;
            gap:12px;
            min-height:44px;
            padding:0 12px;
            border-radius:10px;
            color:var(--text) !important;
            text-decoration:none !important;
            font-weight:750;
            font-size:14px;
            line-height:1;
            transition:background .16s ease,color .16s ease,box-shadow .16s ease;
        }
        .app-side-link:hover {
            background:rgba(251,63,104,.10);
            color:var(--text) !important;
        }
        .app-side-link.is-active {
            background:rgba(251,63,104,.84);
            color:#fff !important;
            box-shadow:0 10px 22px rgba(251,63,104,.28);
        }
        .app-side-icon {
            width:24px;
            height:24px;
            flex:0 0 24px;
            display:grid;
            place-items:center;
            color:currentColor;
        }
        .app-side-icon svg {
            width:21px;
            height:21px;
            display:block;
            stroke:currentColor;
            fill:none;
            stroke-width:2.35;
            stroke-linecap:round;
            stroke-linejoin:round;
        }
        .app-side-label {
            min-width:0;
            overflow:hidden;
            text-overflow:ellipsis;
            white-space:nowrap;
            color:inherit !important;
        }
        [data-testid="stSidebar"].is-mini .app-side-nav {
            align-items:center;
            gap:9px;
            padding:.65rem 0 1rem;
        }
        [data-testid="stSidebar"].is-mini .app-side-link {
            width:40px;
            height:40px;
            min-height:40px;
            padding:0;
            justify-content:center;
            position:relative;
        }
        [data-testid="stSidebar"].is-mini .app-side-label {
            display:none !important;
        }
        [data-testid="stSidebar"].is-mini .app-side-icon {
            width:40px;
            height:40px;
            flex-basis:40px;
        }
        [data-testid="stSidebar"].is-mini .app-side-icon svg {
            width:21px;
            height:21px;
            margin:auto;
        }
        [data-testid="stSidebar"].is-mini .app-side-link[data-tooltip]::after {
            content:attr(data-tooltip);
            position:absolute;
            left:calc(100% + 12px);
            top:50%;
            transform:translateY(-50%) translateX(-4px);
            opacity:0;
            pointer-events:none;
            white-space:nowrap;
            max-width:220px;
            overflow:hidden;
            text-overflow:ellipsis;
            padding:7px 10px;
            border-radius:8px;
            background:var(--surface);
            border:1px solid var(--border);
            color:var(--text) !important;
            font-size:12px;
            font-weight:800;
            box-shadow:0 12px 28px rgba(15,23,42,.18);
            transition:opacity .16s ease,transform .16s ease;
            z-index:999999;
        }
        [data-testid="stSidebar"].is-mini .app-side-link[data-tooltip]::before {
            content:"";
            position:absolute;
            left:calc(100% + 7px);
            top:50%;
            width:9px;
            height:9px;
            transform:translateY(-50%) rotate(45deg);
            opacity:0;
            pointer-events:none;
            background:var(--surface);
            border-left:1px solid var(--border);
            border-bottom:1px solid var(--border);
            transition:opacity .16s ease;
            z-index:999998;
        }
        [data-testid="stSidebar"].is-mini .app-side-link:hover::after,
        [data-testid="stSidebar"].is-mini .app-side-link:hover::before {
            opacity:1;
        }
        [data-testid="stSidebar"].is-mini .app-side-link:hover::after {
            transform:translateY(-50%) translateX(0);
        }
        /* Sidebar nav: align icons and labels on a single baseline */
        [data-testid="stSidebarNav"] ul { padding-left: 0 !important; margin: 0 !important; }
        [data-testid="stSidebarNav"] li { list-style: none !important; margin: 0 !important; padding: 0 !important; }
        [data-testid="stSidebarNav"] a {
            display: flex !important;
            align-items: center !important;
            gap: 14px !important;
            padding: 11px 16px !important;
            border-radius: 12px !important;
            line-height: 1 !important;
            min-height: 46px !important;
            color: var(--text) !important;
            text-decoration: none !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stSidebarNav"] a:hover {
            background: transparent !important;
            color: var(--primary-light) !important;
        }
        [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: rgba(251, 63, 104, 0.82) !important;
            color: #ffffff !important;
            box-shadow: 0 10px 22px rgba(251, 63, 104, 0.28) !important;
        }
        [data-testid="stSidebarNav"] a[data-active="true"] {
            background: rgba(251, 63, 104, 0.82) !important;
            color: #ffffff !important;
            box-shadow: 0 10px 22px rgba(251, 63, 104, 0.28) !important;
        }
        [data-testid="stSidebarNav"] a > span:first-child,
        [data-testid="stSidebarNav"] a [data-testid="stIconMaterial"],
        [data-testid="stSidebarNav"] a .material-symbols-rounded,
        [data-testid="stSidebarNav"] a .material-icons {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 26px !important;
            height: 26px !important;
            font-size: 22px !important;
            line-height: 1 !important;
            flex-shrink: 0 !important;
            margin: 0 !important;
            transform: translateY(0) !important;
            color: inherit !important;
        }
        [data-testid="stSidebarNav"] a span:last-child,
        [data-testid="stSidebarNav"] a p {
            display: inline-flex !important;
            align-items: center !important;
            line-height: 1.2 !important;
            margin: 0 !important;
            padding: 0 !important;
            font-size: 16px !important;
            font-weight: 650 !important;
            color: inherit !important;
        }
        [data-testid="stSidebarNav"] a svg {
            color: inherit !important;
            fill: currentColor !important;
        }
        h1, h2, h3, h4, p, label, div, span { color:var(--text); }
        .brand-row { display:none; }
        .brand-logo {
            width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
            font-size:1.15rem; font-weight:900; color:#fff;
            background:linear-gradient(135deg, #fb7185 0%, #f43f5e 55%, #be123c 100%);
            box-shadow:0 10px 24px rgba(251,113,133,.35);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .brand-logo:hover {
            transform: rotate(5deg) scale(1.1);
            box-shadow:0 15px 35px rgba(251,113,133,.45);
        }
        .sidebar-logo { font-size:1.4rem; font-weight:900; letter-spacing:.2px; line-height:1.15; }
        .sidebar-sub { color:var(--text2); font-size:0.95rem; margin-top:.18rem; }
        .sidebar-badge {
            display:inline-block; margin-top:.45rem; padding:3px 8px; border-radius:999px;
            background:rgba(251,113,133,.22); color:#FDA4AF; font-size:.75rem; font-weight:700;
        }
        div[data-testid="stRadio"] > label { font-size:1.0rem; font-weight:800; color:var(--text2) !important; }
        div[data-testid="stRadio"] [role="radiogroup"] label {
            background:transparent; border:1px solid transparent; border-radius:10px;
            padding:.35rem .45rem; margin:.1rem 0; transition:all .3s cubic-bezier(0.4, 0, 0.2, 1);
            cursor: pointer;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label:hover {
            background:rgba(251,113,133,.12); border-color:rgba(251,113,133,.25);
            transform: translateX(4px);
        }
        div[data-testid="stRadio"] [role="radiogroup"] label[data-checked="true"] {
            background:rgba(251,113,133,.18); border-color:rgba(251,113,133,.4);
        }
        div[data-testid="stRadio"] [role="radiogroup"] label > div:first-child {
            display:none !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label p {
            margin-left:0 !important; font-weight:600;
        }
        .page-title { font-size:2.25rem; font-weight:900; letter-spacing:-.03em; margin-bottom:.25rem; }
        .page-meta { color:var(--text2); font-size:1.1rem; margin-bottom:1rem; }
        .page-header-box {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
            margin-bottom: 1rem;
            padding: 1.15rem 1.25rem;
            border-radius: 16px;
            border: 1px solid rgba(251,113,133,.22);
            background: linear-gradient(135deg, #1a2238 0%, #1f1a3a 50%, #261d3d 100%);
            box-shadow: 0 18px 42px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.03);
            position: relative;
            overflow: hidden;
        }
        .page-header-box::after {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(90deg, rgba(251,113,133,.07), rgba(96,165,250,.06));
            pointer-events: none;
        }
        .page-header-content {
            min-width: 320px;
            position: relative;
            z-index: 1;
        }
        .page-header-badge {
            position: relative;
            z-index: 1;
        }
        
        .dashboard-card:hover {
            box-shadow:0 18px 42px rgba(0,0,0,.35);
            border-color: rgba(251,113,133,.3);
        }
        .section-title {
            font-size:1.15rem; font-weight:800; margin-bottom:.2rem;
            display: flex; align-items: center; gap: 0.5rem;
        }
        .section-sub { color:var(--text2); font-size:0.95rem; margin-bottom:1rem; font-weight:500; }
        .dashboard-card {
            background: linear-gradient(180deg, var(--surface), var(--surface2));
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 1rem 1.15rem;
            transition: all 0.3s ease;
            box-shadow: 0 10px 30px rgba(0,0,0,.15);
            margin-bottom: 1.5rem;
            margin-top: -4.0rem;
        }
        .dashboard-card a {
            color: inherit;
            text-decoration: none;
        }
        .artist-link {
            color: var(--text);
            text-decoration: none;
            font-weight: 700;
        }
        .artist-link:hover {
            color: var(--primary);
            text-decoration: underline;
        }
        .table-wrap { margin-top: 1rem; overflow-x:auto; overflow-y:auto; max-height:620px; }
        .leader-table { width:100%; border-collapse:collapse; font-size:1.1rem; }
        .leader-table thead th {
            text-align:left; padding:.85rem .85rem; color: var(--text); font-size:1.1rem;
            letter-spacing:.06em; text-transform:uppercase; border-bottom:1px solid var(--border);
            font-weight: 900;
        }
        .leader-table tbody td {
            padding:.9rem .85rem; border-bottom:1px solid var(--border); vertical-align:middle;
            color: var(--text);
        }
        .leader-table tbody tr:hover { 
            background:rgba(251,113,133,.12); 
            transform: scale(1.004);
            box-shadow: 0 8px 20px rgba(0,0,0,.1);
        }
        .leader-table tbody tr {
            transition: all 0.18s ease;
        }
        .pos-cell { color:var(--primary); font-weight:800; width:46px; }
        .artist-cell { font-weight:700; }
        .num-cell { text-align:left; font-variant-numeric:tabular-nums; }
        .country-pill {
            display:inline-block; padding:4px 12px; border-radius:999px; background:rgba(34,211,160,.12);
            color: var(--text); font-size:.75rem; font-weight:700;
        }
        .badge { 
            display:inline-block; padding:6px 10px; border-radius:999px; 
            font-size:.72rem; font-weight:800; transition: all 0.2s ease;
            cursor: default;
        }
        .badge:hover {
            transform: scale(1.05);
        }
        .badge-up { background:rgba(34,211,160,.14); color:#8ff0cf; }
        .badge-up:hover { background:rgba(34,211,160,.25); }
        .badge-dn { background:rgba(232,69,69,.14); color:#ff9c9c; }
        .badge-dn:hover { background:rgba(232,69,69,.25); }
        .badge-same { background:rgba(151,163,197,.14); color:#c4d0f3; }
        .badge-new { 
            background:rgba(251,113,133,.18); color:#FDA4AF;
            animation: pulse 2s infinite;
        }
        
        /* Interactive buttons */
        .action-btn {
            display: inline-flex; align-items: center; gap: 0.5rem;
            padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.85rem;
            font-weight: 600; cursor: pointer; transition: all 0.3s ease;
            border: 1px solid var(--border); background: var(--surface2);
            color: var(--text); text-decoration: none;
        }
        .action-btn:hover {
            background: rgba(251,113,133,.15);
            border-color: var(--primary);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(251,113,133,.2);
        }
        .action-btn-primary {
            background: linear-gradient(135deg, #fb7185, #f43f5e);
            border-color: transparent;
        }
        .action-btn-primary:hover {
            background: linear-gradient(135deg, #fda4af, #fb7185);
            box-shadow: 0 6px 20px rgba(251,113,133,.4);
        }
        .kpi-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 24px 20px 18px;
            min-height: 158px;
            width: 100%;
            position: relative; 
            overflow: visible; 
            height: 100%;
            display: flex;
            flex-direction: column;
            margin-top: -2.5rem;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            animation: fadeIn 0.6s ease-out;
            box-shadow: 0 10px 30px rgba(0,0,0,.15);
        }
        .kpi-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 40px rgba(0,0,0,.25);
            border-color: rgba(251,113,133,.3);
            z-index: 1000;
        }
        .kpi-card::before {
            content:''; position:absolute; top:0; left:0; right:0; height:3px;
            border-radius: 20px 20px 0 0;
            background: linear-gradient(90deg, var(--accent), var(--accent2));
            transition: height 0.3s ease;
        }
        .kpi-card:hover::before {
            height: 4px;
        }
        .kpi-green::before { background: linear-gradient(90deg, #34d399, #10b981); }
        .kpi-amber::before { background: linear-gradient(90deg, #fcd34d, #f59e0b); }
        .kpi-red::before { background: linear-gradient(90deg, #fb7185, #e11d48); }
        .kpi-label {
            color:var(--text); font-size:1.0rem; text-transform:uppercase;
            letter-spacing:.08em; margin-bottom: 0.5rem;
            font-weight: 700;
        }
        .kpi-value {
            font-size:2.2rem; font-weight:900; margin-top:.35rem;
            background: linear-gradient(135deg, #1A1A1A 0%, #4A4A4A 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .kpi-delta { color:var(--text2); font-size:0.9rem; margin-top:.2rem; }
        
        /* Progress bars */
        .progress-bar {
            width: 100%; height: 6px; background: rgba(151,163,197,.15);
            border-radius: 999px; overflow: hidden; margin-top: auto;
        }
        .progress-fill {
            height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2));
            border-radius: 999px; transition: width 1.5s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .table-wrap { margin-top: 1rem; overflow-x:auto; overflow-y:auto; max-height:640px; padding-right: 0.25rem; }
        table.leader-table {
            width:100%;
            border-collapse: collapse;
            font-size: 1.05rem;
            border: 2px solid rgba(251, 113, 133, 0.25);
            border-radius: 12px;
            overflow: hidden;
        }
        .leader-table thead th {
            position: sticky;
            top: 0;
            z-index: 3;
            text-align:left;
            padding: .85rem .85rem;
            color: var(--text);
            font-size: 0.95rem;
            letter-spacing: .06em;
            text-transform: uppercase;
            border-bottom: 2px solid rgba(251, 113, 133, 0.22);
            background: linear-gradient(135deg, var(--surface2) 0%, var(--surface) 100%);
            backdrop-filter: blur(8px);
            font-weight: 700;
        }
        .leader-table tbody td {
            padding: .75rem .85rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
            color: var(--text);
            font-weight: 500;
        }
        .leader-table tbody tr {
            transition: all 0.2s ease;
            background: var(--surface);
        }
        .leader-table tbody tr:nth-child(even) {
            background: rgba(251, 113, 133, 0.04);
        }
        .leader-table tbody tr:hover { 
            background: rgba(251, 113, 133, 0.12);
            box-shadow: inset 0 0 12px rgba(0,0,0,0.1);
        }
        .pos-cell {
            color: var(--primary);
            font-weight: 800;
            width: 48px;
            font-size: 1.25rem;
        }
        .artist-cell {
            font-weight: 700;
            color: var(--text);
        }
        .muted {
            color: var(--text2);
            font-weight: 500;
        }
        .num-cell {
            text-align: left;
            font-variant-numeric: tabular-nums;
            color: var(--text);
            font-weight: 600;
        }
        .country-pill {
            display:inline-block; padding:2px 8px; border-radius:999px; background:rgba(52,211,153,.12);
            color: var(--text); font-size:.75rem; font-weight:700;
        }
        .badge { 
            display:inline-block; padding:4px 10px; border-radius:999px; 
            font-size:.72rem; font-weight:800; transition: all 0.2s ease;
            cursor: default;
            color: var(--text);
        }
        .badge:hover {
            transform: scale(1.1);
        }
        .badge-up { background:rgba(52,211,153,.14); color: var(--text); }
        .badge-up:hover { background:rgba(52,211,153,.25); }
        .badge-dn { background:rgba(232,69,69,.14); color: var(--text); }
        .badge-dn:hover { background:rgba(232,69,69,.25); }
        .badge-same { background:rgba(151,163,197,.14); color: var(--text); }
        .badge-new { 
            background:rgba(251,113,133,.18); color: #FDA4AF;
            animation: pulse 2s infinite;
        }
        
        /* Tooltip styles */
        .tooltip {
            position: relative;
            display: inline-block;
        }
        .tooltip .tooltiptext {
            visibility: hidden;
            width: 360px;
            background-color: rgba(13, 17, 23, 0.99);
            backdrop-filter: blur(16px);
            color: #ffffff;
            text-align: left;
            border-radius: 14px;
            padding: 16px 20px;
            position: absolute;
            z-index: 99999;
            top: 100%;
            left: 50%;
            transform: translateX(-50%) translateY(0);
            opacity: 0;
            transition: opacity 0.3s ease, transform 0.3s ease;
            border: 1px solid rgba(251, 113, 133, 0.4);
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            font-size: 0.98rem;
            line-height: 1.6;
            pointer-events: auto;
            max-height: 320px;
            overflow-y: auto;
            overscroll-behavior: contain;
            scrollbar-width: thin;
            scrollbar-color: var(--primary) transparent;
        }
        .tooltip:hover .tooltiptext {
            visibility: visible; 
            opacity: 1; 
            transform: translateX(-50%) translateY(10px);
        }
        .tooltip .tooltiptext::after {
            content: ""; position: absolute; bottom: 100%; left: 50%;
            margin-left: -10px; border-width: 10px; border-style: solid;
            border-color: transparent transparent rgba(13, 17, 23, 0.99) transparent;
        }
        .tooltip .tooltiptext::before {
            content: "";
            position: absolute;
            bottom: 100%;
            left: 0;
            width: 100%;
            height: 25px;
            background: transparent;
        }
        /* Crucial: Prevent Streamlit from clipping the tooltips */
        [data-testid="stHorizontalBlock"], [data-testid="column"], [data-testid="stVerticalBlock"], [data-testid="stVerticalBlockBorderWrapper"] {
            overflow: visible !important;
        }
        
        .tooltip .tooltiptext::-webkit-scrollbar {
            width: 5px;
        }
        .tooltip .tooltiptext::-webkit-scrollbar-track {
            background: transparent;
        }
        .tooltip .tooltiptext::-webkit-scrollbar-thumb {
            background: rgba(251, 113, 133, 0.4);
            border-radius: 10px;
        }
        textarea, input, [data-baseweb="select"] > div, [data-baseweb="select"] span {
            background:var(--surface2) !important; color:var(--text) !important; border-color:var(--border) !important;
        }
        
        /* Selectbox Popover (The dropdown list) */
        div[data-baseweb="popover"] ul {
            background-color: var(--surface) !important;
            border: 1px solid var(--border) !important;
        }
        div[data-baseweb="popover"] li {
            color: var(--text) !important;
            background-color: transparent !important;
        }
        div[data-baseweb="popover"] li:hover {
            background-color: var(--surface2) !important;
        }
        /* Fix for selected value visibility */
        div[data-baseweb="select"] div[child-pv-id] {
            color: var(--text) !important;
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
            align-items:center; padding:.8rem 1rem; background:rgba(17,24,39,.55);
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
            background: #34D399;
            border-radius: 50%;
            animation: pulse 2s ease-in-out infinite;
        }
        
        /* Expandable section */
        .expandable {
            overflow: hidden;
            transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        /* Comparison mode highlight */
        .comparison-highlight {
            border: 2px solid var(--primary);
            background: rgba(251,113,133,.08);
            animation: pulse 1.5s ease-in-out 3;
        }
        
        /* Interactive tabs */
        .stTabs {
            width: 100%;
            border-bottom: none !important;
            margin-top: -2.5rem;
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
            font-weight: 700;
        }
        .stTabs [data-baseweb="tab"] p {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 0.98rem;
        }
        .stTabs [data-baseweb="tab-panel"] {
            width: 100%;
            padding-top: 0.85rem;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background: rgba(251,113,133,.12);
            border-color: rgba(251,113,133,.25);
            transform: translateY(-2px);
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(251,113,133,.22), rgba(196,181,253,.18));
            border-color: var(--primary);
            color: var(--text);
            border-bottom: 1px solid var(--accent) !important;
        }
        .stPlotlyChart, div[data-testid="stDataFrame"], div[data-testid="stTable"] {
            width: 100% !important;
        }
        .stPlotlyChart {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 1rem;
            box-shadow: 0 10px 30px rgba(108,92,231,.08);
            margin-top: 1.25rem;
            margin-bottom: 1.5rem;
        }
        .stPlotlyChart > div {
            background: transparent !important;
        }
        
        /* Buttons enhancement */
        .stButton button {
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-radius: 12px;
            background: rgba(251, 113, 133, 0.12) !important;
            border: 1px solid rgba(251, 113, 133, 0.25) !important;
            color: var(--text) !important;
        }
        .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(251, 113, 133, 0.3);
            background: rgba(251, 113, 133, 0.22) !important;
        }

        /* Selectbox enhancement - dropdown styling - REMOVED (using custom HTML) */
        /* Removed - using custom HTML dropdowns instead */
        
        /* Hide ALL Streamlit running/status indicators */
        [data-testid="stStatusWidget"],
        .stAppStatus,
        [data-testid="stAppStatus"],
        .stSpinner,
        [data-testid="stSpinner"],
        div.element-container:has([data-testid="stSpinner"]) {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
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
                padding: 0.1rem;
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
            color: var(--text) !important;
        }
        .streamlit-expanderHeader:hover {
            background: rgba(251,113,133,0.08);
        }
        .streamlit-expanderHeader p {
            color: var(--text) !important;
        }
        [data-testid="stExpander"] {
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
            background: transparent !important;
        }
        
        /* Toggle labels and sidebar text visibility */
        [data-testid="stWidgetLabel"] p,
        .stMarkdown p,
        .stToggle label,
        [data-testid="stExpander"] p,
        .streamlit-expanderHeader p {
            color: var(--text) !important;
        }
        
        /* Ensure sidebar expander icons/arrows are visible */
        [data-testid="stSidebar"] .streamlit-expanderHeader svg {
            fill: var(--text) !important;
            color: var(--text) !important;
        }
        
        /* Download button styling */
        .stDownloadButton button {
            background: linear-gradient(135deg, #34D399, #10B981) !important;
            color: white !important;
            border: none !important;
            border-radius: 12px !important;
        }
        .stDownloadButton button:hover {
            background: linear-gradient(135deg, #4AE8AD, #22C993) !important;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(52,211,153,.35) !important;
        }
        
        /* Selectbox hover */
        [data-baseweb="select"]:hover {
            border-color: var(--primary) !important;
        }
        
        /* Text input focus */
        input:focus, textarea:focus {
            border-color: var(--primary) !important;
            box-shadow: 0 0 0 1px var(--primary) !important;
        }
        
        /* Slider styling */
        .stSlider [role="slider"] {
            background: linear-gradient(135deg, #fb7185, #fda4af) !important;
        }
        
        /* Toggle switch */
        [data-testid="stCheckbox"] input[type="checkbox"] + div {
            background: rgba(100, 116, 139, 0.25) !important;
            border: 1px solid rgba(148, 163, 184, 0.4) !important;
        }
        [data-testid="stCheckbox"] input[type="checkbox"]:checked + div {
            background: linear-gradient(135deg, #fb7185, #fda4af) !important;
            border-color: #fb7185 !important;
        }

        /* Global footer */
        .app-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 60px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            gap: 5px;
            z-index: 99; /* Below sidebar but above content */
            background: rgba(255, 255, 255, 0.97);
            backdrop-filter: blur(16px);
            border-top: 1px solid rgba(0,0,0,.08);
            text-align: center;
            color: var(--text2);
            font-size: 0.95rem;
            line-height: 1.2;
        }
        .app-footer a {
            color: var(--primary);
            text-decoration: none;
        }
        .app-footer a:hover {
            color: var(--primary-dark);
            text-decoration: underline;
        }
        .time-chip {
            background: var(--surface2);
            color: var(--text2);
            font-size: 0.72rem;
            padding: 4px 10px;
            border-radius: 999px;
            font-weight: 700;
            border: 1px solid var(--border);
            text-transform: none;
            letter-spacing: 0;
            white-space: nowrap;
        }

        /* JS-driven Mini Sidebar Functionality */
        button[data-testid="baseButton-headerNoPadding"],
        button[data-testid="collapsedControl"] {
            display: none !important;
        }
        
        [data-testid="stSidebar"] {
            transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
            overflow: visible !important;
        }
        
        @media (min-width: 769px) {
            [data-testid="stSidebar"].is-mini [data-testid="stSidebarContent"],
            [data-testid="stSidebar"].is-mini [data-testid="stSidebarUserContent"],
            [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] {
                overflow: hidden !important;
            }
        }
        
        [data-testid="stSidebar"].is-mini {
            width: 66px !important;
            min-width: 66px !important;
        }
        
        [data-testid="stSidebar"].is-mini + section[data-testid="stMain"] {
            margin-left: 66px !important;
        }
        
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarHeader"]::after,
        [data-testid="stSidebar"].is-mini .sidebar-logo,
        [data-testid="stSidebar"].is-mini .appearance-title,
        [data-testid="stSidebar"].is-mini .stButton,
        [data-testid="stSidebar"].is-mini [data-testid="stExpander"] {
            display: none !important;
            opacity: 0 !important;
        }
        
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 40px !important;
            height: 40px !important;
            padding: 0 !important;
            margin: 0 auto 8px auto !important;
            border-radius: 10px !important;
            overflow: visible !important;
            position: relative !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"].is-mini [data-testid="stSidebarHeader"]::before {
            left: 50% !important;
            top: 50% !important;
            transform: translate(-50%, -50%) !important;
            margin: 0 !important;
        }
        
        /* Make text invisible without forcing 0x0 dimensions that trigger clip bugs */
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a * {
            color: transparent !important;
            font-size: 0 !important;
            line-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a span.material-symbols-rounded,
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a [data-testid="stIconMaterial"],
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a i {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            position: absolute !important;
            inset: 0 !important;
            transform: none !important;
            width: 100% !important;
            height: 100% !important;
            color: var(--text2) !important;
            font-size: 22px !important;
            line-height: 1 !important;
            text-align: center !important;
            white-space: nowrap !important;
            margin: 0 !important;
            padding: 0 !important;
            z-index: 2 !important;
            opacity: 0.60;
        }

        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a svg {
            display: block !important;
            position: absolute !important;
            left: 50% !important;
            top: 50% !important;
            transform: translate(-50%, -50%) !important;
            width: 22px !important;
            height: 22px !important;
            color: var(--text2) !important;
            margin: 0 !important;
            padding: 0 !important;
            z-index: 2 !important;
            opacity: 0.60;
        }
        

        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[aria-current="page"],
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-active="true"] {
            background: rgba(251, 63, 104, 0.84) !important;
            box-shadow: 0 10px 22px rgba(251, 63, 104, 0.28) !important;
            border: none !important;
            border-radius: 10px !important;
        }

        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-tooltip]::after {
            content: attr(data-tooltip);
            position: absolute;
            left: calc(100% + 12px);
            top: 50%;
            transform: translateY(-50%) translateX(-4px);
            opacity: 0;
            pointer-events: none;
            white-space: nowrap;
            max-width: 220px;
            overflow: hidden;
            text-overflow: ellipsis;
            padding: 7px 10px;
            border-radius: 8px;
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text) !important;
            font-size: 12px;
            font-weight: 800;
            line-height: 1.2;
            box-shadow: 0 12px 28px rgba(15,23,42,.18);
            transition: opacity .16s ease, transform .16s ease;
            z-index: 999999;
        }

        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-tooltip]::before {
            content: "";
            position: absolute;
            left: calc(100% + 7px);
            top: 50%;
            width: 9px;
            height: 9px;
            transform: translateY(-50%) rotate(45deg);
            opacity: 0;
            pointer-events: none;
            background: var(--surface);
            border-left: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
            transition: opacity .16s ease;
            z-index: 999998;
        }

        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-tooltip]:hover::after,
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-tooltip]:hover::before {
            opacity: 1;
        }

        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-tooltip]:hover::after {
            transform: translateY(-50%) translateX(0);
        }
        
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[aria-current="page"] span.material-symbols-rounded,
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[aria-current="page"] [data-testid="stIconMaterial"],
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[aria-current="page"] svg,
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[aria-current="page"] i,
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-active="true"] span.material-symbols-rounded,
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-active="true"] [data-testid="stIconMaterial"],
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-active="true"] svg,
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] a[data-active="true"] i {
            color: #ffffff !important;
            opacity: 1 !important;
            filter: drop-shadow(0 1px 3px rgba(0,0,0,0.2));
        }
        
        [data-testid="stSidebar"].is-mini .status-good,
        [data-testid="stSidebar"].is-mini .muted,
        [data-testid="stSidebar"].is-mini .small-note {
            display: none !important;
        }
        
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarHeader"] {
            padding-left: 0 !important;
            padding-right: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }

        /* Force nav container and list to full width centered column */
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] {
            padding-top: 0.5rem !important;
            width: 100% !important;
        }
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] ul {
            width: 100% !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        [data-testid="stSidebar"].is-mini [data-testid="stSidebarNav"] li {
            width: 100% !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            list-style: none !important;
            padding: 0 !important;
            margin: 0 0 2px 0 !important;
        }

        """ + theme_extra + "</style>",
        unsafe_allow_html=True,
    )
    
    button_bg = "#1f2633" if dark_mode else "#FFFFFF"
    button_border = "rgba(148,163,184,.15)" if dark_mode else "#E9ECF2"
    button_color = "#ffffff" if dark_mode else "#1A1A1A"

    js_code = r"""
        <script>
            setInterval(() => {
                const doc = window.parent.document;
                const sidebar = doc.querySelector('[data-testid="stSidebar"]');
                
                if (sidebar && !doc.getElementById('custom-collapse-btn')) {
                    const btn = doc.createElement('div');
                    btn.id = 'custom-collapse-btn';
                    
                    const isMiniInit = localStorage.getItem('sidebar_mini') === 'true';
                    btn.innerHTML = isMiniInit 
                        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>` 
                        : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>`;
                    
                    btn.style.cssText = `
                        position: absolute; right: -13px; top: 42px; width: 26px; height: 26px; 
                        display: flex; align-items: center; justify-content: center;
                        cursor: pointer; color: __BTN_COLOR__; border-radius: 50%;
                        background: __BTN_BG__; border: 1px solid __BTN_BORDER__;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
                        transition: all 0.2s; z-index: 999999;
                    `;
                    btn.onmouseover = () => { btn.style.transform = 'scale(1.08)'; }
                    btn.onmouseout = () => { btn.style.transform = 'scale(1)'; }
                    
                    btn.onclick = () => {
                        const isMini = sidebar.classList.toggle('is-mini');
                        btn.innerHTML = isMini 
                            ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>` 
                            : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>`;
                        localStorage.setItem('sidebar_mini', isMini);
                        applyMiniNavStyles(sidebar);
                    };
                    
                    if (isMiniInit) {
                        sidebar.classList.add('is-mini');
                    }
                    
                    sidebar.appendChild(btn);
                }

                // Apply styles and tooltips
                if (sidebar) {
                    applyMiniNavStyles(sidebar);
                }
            }, 300);

            function applyMiniNavStyles(sidebar) {
                const navLinks = sidebar.querySelectorAll('.app-side-link, [data-testid="stSidebarNav"] a');
                const currentPath = (window.parent.location.pathname || '/').replace(/\/+$/, '');
                navLinks.forEach(link => {
                    if (link.classList.contains('app-side-link') && !link.dataset.sameTabBound) {
                        link.dataset.sameTabBound = 'true';
                        link.addEventListener('click', event => {
                            event.preventDefault();
                            const nextPath = link.getAttribute('data-path') || new URL(link.href, window.parent.location.href).pathname;
                            const currentSearch = window.parent.location.search || '';
                            const nextUrl = `${nextPath}${currentSearch}`;
                            window.parent.history.pushState({}, '', nextUrl);
                            window.parent.dispatchEvent(new PopStateEvent('popstate'));
                            window.parent.dispatchEvent(new HashChangeEvent('hashchange'));
                            setTimeout(() => {
                                const currentPath = (window.parent.location.pathname || '').replace(/\/+$/, '');
                                const expectedPath = nextPath.replace(/\/+$/, '');
                                if (currentPath !== expectedPath) {
                                    window.parent.location.assign(nextUrl);
                                }
                            }, 80);
                        });
                    }
                    // Add tooltip attribute if missing
                    if (!link.hasAttribute('title')) {
                        const clone = link.cloneNode(true);
                        const icons = clone.querySelectorAll('[data-testid="stIconMaterial"], .material-symbols-rounded, .material-icons, svg');
                        icons.forEach(i => i.remove());
                        const text = clone.textContent.trim();
                        if (text) {
                            link.setAttribute('title', text);
                        }
                    }
                    if (!link.hasAttribute('data-tooltip')) {
                        const text = link.getAttribute('title') || link.textContent.trim();
                        if (text) {
                            link.setAttribute('data-tooltip', text);
                        }
                    }

                    const linkUrl = new URL(link.href || '#', window.parent.location.href);
                    const linkPath = (linkUrl.pathname || '/').replace(/\/+$/, '');
                    const isDefaultOverview = (currentPath === '' || currentPath === '/') && linkPath.endsWith('/artists-overview');
                    const isActive = link.getAttribute('aria-current') === 'page' || linkPath === currentPath || isDefaultOverview;
                    if (isActive) {
                        link.setAttribute('data-active', 'true');
                        link.classList.add('is-active');
                    } else {
                        link.removeAttribute('data-active');
                        link.classList.remove('is-active');
                    }
                    if (sidebar.classList.contains('is-mini')) {
                        if (isActive) {
                            // Red active link
                            link.style.setProperty('background', 'rgba(251,63,104,0.84)', 'important');
                            link.style.setProperty('box-shadow', '0 10px 22px rgba(251,63,104,0.28)', 'important');
                            link.style.setProperty('border', 'none', 'important');
                            link.style.setProperty('border-radius', '10px', 'important');
                            // White icon inside active link
                            const icons = link.querySelectorAll('span, svg, i, [data-testid="stIconMaterial"]');
                            icons.forEach(icon => {
                                icon.style.setProperty('color', '#ffffff', 'important');
                                icon.style.setProperty('opacity', '1', 'important');
                            });
                        } else {
                            // Reset non-active links
                            link.style.removeProperty('background');
                            link.style.removeProperty('box-shadow');
                            link.style.removeProperty('border');
                            link.style.removeProperty('border-radius');
                            const icons = link.querySelectorAll('span, svg, i, [data-testid="stIconMaterial"]');
                            icons.forEach(icon => {
                                icon.style.removeProperty('color');
                                icon.style.removeProperty('opacity');
                            });
                        }
                    } else {
                        // If not mini, remove the hardcoded inline styles so Streamlit's default or global CSS takes over
                        link.style.removeProperty('background');
                        link.style.removeProperty('box-shadow');
                        link.style.removeProperty('border');
                        link.style.removeProperty('border-radius');
                        link.removeAttribute('data-tooltip');
                        const icons = link.querySelectorAll('span, svg, i, [data-testid="stIconMaterial"]');
                        icons.forEach(icon => {
                            icon.style.removeProperty('color');
                            icon.style.removeProperty('opacity');
                        });
                    }
                });
            }
        </script>
        """
    js_code = js_code.replace("__BTN_COLOR__", button_color)
    js_code = js_code.replace("__BTN_BG__", button_bg)
    js_code = js_code.replace("__BTN_BORDER__", button_border)

    st_components.html(
        js_code,
        height=0,
        width=0
    )


def fmt_short(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"





@st.dialog(" ", width="large")
def show_artist_details_dialog(row: pd.Series) -> None:
    """Displays a detailed popup for the selected artist with Spotlight + Acquisition data."""
    artist_name = row["name"]
    real_img_url = get_artist_image_url(row["name"])
    display_img = real_img_url if real_img_url else get_fallback_avatar_url(row["name"])

    # Pre-compute all values
    rank_val = int(row.get("rank")) if pd.notna(row.get("rank")) else 0
    songs_val = int(row.get("songs_count")) if pd.notna(row.get("songs_count")) else 0
    albums_val = int(row.get("albums_count")) if pd.notna(row.get("albums_count")) else 0
    countries_val = int(row.get("countries_count")) if pd.notna(row.get("countries_count")) else 0
    monthly_val = fmt_short(row.get("monthly_listeners")) if pd.notna(row.get("monthly_listeners")) else "—"
    peak_val = fmt_short(row.get("peak_listeners")) if pd.notna(row.get("peak_listeners")) else "—"
    points_val = fmt_short(row.get("total_points")) if pd.notna(row.get("total_points")) else "—"
    trend_change = str(row.get("rank_change") or "=").strip()
    display_country = escape(str(row.get("display_country") or row.get("top_country") or "Global"))

    songs_items = [item.strip() for item in str(row.get("top_songs") or "").split("\n") if item.strip()]
    albums_items = [item.strip() for item in str(row.get("top_albums") or "").split("\n") if item.strip()]
    countries_items = [item.strip() for item in str(row.get("top_countries") or "").split("\n") if item.strip()]

    songs_html = "".join(f"<li>{escape(item)}</li>" for item in songs_items) if songs_items else "<div style='color:#8b95ad;font-size:.88rem;'>No songs available.</div>"
    albums_html = "".join(f"<li>{escape(item)}</li>" for item in albums_items) if albums_items else "<div style='color:#8b95ad;font-size:.88rem;'>No albums available.</div>"
    countries_html = "".join(f"<li>{escape(item)}</li>" for item in countries_items) if countries_items else "<div style='color:#8b95ad;font-size:.88rem;'>No countries available.</div>"

    # Scoped styles for the dialog
    is_dark = st.session_state.get("dark_mode", False)
    
    if is_dark:
        dlg_bg = "linear-gradient(180deg, #0f172a 0%, #020617 100%)"
        dlg_panel_bg = "#1e293b"
        dlg_kpi_bg = "linear-gradient(180deg, #1e293b 0%, #0f172a 100%)"
        dlg_text1, dlg_text2 = "#f8fafc", "#94a3b8"
        dlg_divider = "rgba(255, 255, 255, 0.1)"
        dlg_close_color = "#f8fafc"
        dlg_close_bg = "rgba(248, 250, 252, 0.12)"
        dlg_close_border = "rgba(248, 250, 252, 0.2)"
    else:
        dlg_bg = "linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%)"
        dlg_panel_bg = "#ffffff"
        dlg_kpi_bg = "linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)"
        dlg_text1, dlg_text2 = "#0f172a", "#475569"
        dlg_divider = "rgba(0, 0, 0, 0.08)"
        dlg_close_color = "#0f172a"
        dlg_close_bg = "rgba(15, 23, 42, 0.12)"
        dlg_close_border = "rgba(15, 23, 42, 0.2)"

    dlg_border = "rgba(251, 113, 133, 0.3)" if is_dark else "rgba(251, 113, 133, 0.15)"
    dlg_badge_bg = "rgba(148, 163, 184, 0.1)" if is_dark else "rgba(0, 0, 0, 0.05)"

    st.markdown(f"""
        <style>
        div[role="dialog"] {{
            background: {dlg_bg} !important;
            border: 1px solid {dlg_border} !important;
            box-shadow: 0 25px 60px {"rgba(0, 0, 0, 0.6)" if is_dark else "rgba(0, 0, 0, 0.12)"} !important;
            width: 85vw !important;
            max-width: 1400px !important;
            overflow: hidden !important;
        }}
        /* Remove default header padding/border to fit custom close button */
        [data-testid="stDialogHeader"] {{
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
            height: 0 !important;
        }}
        /* Enhanced close button styling - Perfected for visibility in both modes */
        button[data-testid="stBaseButton-close"],
        button[aria-label="Close"] {{
            color: {dlg_close_color} !important;
            background-color: {dlg_close_bg} !important;
            border: 1px solid {dlg_close_border} !important;
            border-radius: 50% !important;
            width: 36px !important;
            height: 36px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            position: absolute !important;
            top: 12px !important;
            right: 12px !important;
            z-index: 1000 !important;
            opacity: 1 !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
            padding: 0 !important;
            margin: 0 !important;
            line-height: 0 !important;
            cursor: pointer !important;
        }}
        button[data-testid="stBaseButton-close"]:hover,
        button[aria-label="Close"]:hover {{
            background-color: #fb7185 !important;
            color: #ffffff !important;
            border-color: #fb7185 !important;
            transform: scale(1.1) rotate(90deg) !important;
            box-shadow: 0 4px 12px rgba(251, 113, 133, 0.3) !important;
        }}
        button[data-testid="stBaseButton-close"] svg,
        button[aria-label="Close"] svg {{
            fill: currentColor !important;
            width: 20px !important;
            height: 20px !important;
        }}
        .dlg-section {{ margin-bottom: 20px; }}
        .dlg-section-title {{
            font-size: 1.05rem; font-weight: 800; color: {dlg_text1};
            letter-spacing: -.01em; margin-bottom: 14px; padding-bottom: 10px;
            border-bottom: 1px solid {dlg_divider};
            display: flex; align-items: center; gap: 10px;
        }}
        .dlg-section-badge {{
            font-size: .68rem; font-weight: 700; letter-spacing: .1em;
            text-transform: uppercase; color: {dlg_text2};
            background: {dlg_badge_bg}; border: 1px solid {dlg_divider};
            padding: 3px 10px; border-radius: 999px;
        }}
        .dlg-kpi-grid {{
            display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px; margin: 12px 0 16px;
        }}
        .dlg-kpi {{
            background: {dlg_kpi_bg};
            border: 1px solid {dlg_border}; border-radius: 12px;
            padding: 14px; box-shadow: 0 4px 12px rgba(0,0,0,.05);
        }}
        .dlg-kpi-label {{
            color: {dlg_text2}; font-size: .68rem; text-transform: uppercase;
            letter-spacing: .08em; font-weight: 800; margin-bottom: 4px;
            display: flex; align-items: center; gap: 6px;
        }}
        .dlg-kpi-label span {{
            font-size: 1rem;
        }}
        .dlg-kpi-value {{ color: {dlg_text1}; font-size: 1.3rem; font-weight: 900; line-height: 1.1; }}
        .dlg-kpi-note {{ color: {dlg_text2}; font-size: .78rem; margin-top: 3px; }}
        .dlg-panel {{
            background: {dlg_panel_bg}; border: 1px solid {dlg_border};
            border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,.05); margin-bottom: 14px;
        }}
        .dlg-panel-header {{
            padding: 10px 14px; border-bottom: 1px solid {dlg_divider};
            color: {dlg_text1}; font-size: .88rem; font-weight: 800;
            letter-spacing: .04em; text-transform: uppercase;
        }}
        .dlg-panel-body {{ padding: 14px; }}
        .dlg-lists-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
        .dlg-list-title {{ color: {dlg_text1}; font-size: .82rem; font-weight: 800; margin-bottom: 6px; }}
        .dlg-list {{ margin: 0; padding-left: 18px; color: {dlg_text1}; line-height: 1.6; font-size: .85rem; }}
        .dlg-hero {{
            display: grid; grid-template-columns: minmax(100px, 150px) 1fr;
            gap: 16px; align-items: center; margin-bottom: 14px;
        }}
        .dlg-hero img {{
            width: 100%; max-width: 150px; border-radius: 20px;
            box-shadow: 0 16px 36px rgba(0,0,0,0.1); border: 2px solid {dlg_divider};
        }}
        .dlg-hero-name {{ margin: 0 0 4px; color: {dlg_text1}; font-size: 1.8rem; font-weight: 900; letter-spacing: -.01em; }}
        .dlg-hero-badges {{ display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }}
        .dlg-badge {{
            display: inline-block; padding: 4px 12px; border-radius: 8px;
            font-weight: 800; font-size: .8rem; letter-spacing: .04em;
        }}
        .dlg-badge-rank {{ background: rgba(251,113,133,.15); color: #FDA4AF; border: 1px solid rgba(251,113,133,.3); }}
        .dlg-badge-country {{ background: rgba(52,211,153,.15); color: #34d399; border: 1px solid rgba(52,211,153,.3); }}
        .dlg-badge-ml {{ background: {dlg_badge_bg}; color: {dlg_text2}; border: 1px solid {dlg_divider}; }}
        .dlg-acq-signal {{
            display: inline-flex; align-items: center; gap: 6px;
            font-size: .78rem; font-weight: 700; padding: 6px 14px;
            border-radius: 8px; letter-spacing: .04em; text-transform: uppercase;
        }}
        .dlg-sig-buy {{ background: rgba(52,211,153,.18); color: #34d399; border: 1px solid rgba(52,211,153,.4); }}
        .dlg-sig-watch {{ background: rgba(96,165,250,.18); color: #60a5fa; border: 1px solid rgba(96,165,250,.4); }}
        .dlg-sig-caution {{ background: rgba(251,113,133,.18); color: #fb7185; border: 1px solid rgba(251,113,133,.4); }}
        .dlg-sig-row {{
            display: flex; align-items: flex-start; gap: 12px;
            padding: 10px 0; border-bottom: 1px solid {dlg_divider};
        }}
        .dlg-sig-row:last-child {{ border-bottom: none; }}
        .dlg-sig-icon {{ font-size: 18px; flex-shrink: 0; }}
        .dlg-sig-title {{ font-size: .85rem; font-weight: 600; color: {dlg_text1}; margin-bottom: 2px; }}
        .dlg-sig-desc {{ font-size: .78rem; color: {dlg_text2}; line-height: 1.5; }}
        .dlg-trk-row {{
            display: grid; grid-template-columns: 28px 1fr 72px 56px;
            gap: 6px; padding: 8px 0; border-bottom: 1px solid {dlg_divider};
            align-items: center; font-size: .82rem;
        }}
        .dlg-trk-row:last-child {{ border-bottom: none; }}
        .dlg-trk-rank {{ color: {dlg_text2}; text-align: center; font-weight: 600; }}
        .dlg-trk-name {{ color: {dlg_text1}; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .dlg-trk-val {{ color: {dlg_text2}; text-align: right; font-variant-numeric: tabular-nums; }}
        .dlg-summary-table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
        .dlg-summary-table th {{
            text-align: left; color: {dlg_text2}; font-size: .68rem;
            text-transform: uppercase; letter-spacing: .08em;
            padding: .55rem .65rem; border-bottom: 1px solid {dlg_divider};
        }}
        .dlg-summary-table td {{
            padding: .55rem .65rem; border-bottom: 1px solid {dlg_divider}; color: {dlg_text2};
        }}
        @media (max-width: 980px) {{
            .dlg-kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            .dlg-lists-grid {{ grid-template-columns: 1fr; }}
            .dlg-hero {{ grid-template-columns: 1fr; }}
        }}
        </style>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════
    # SECTION 1: ARTIST SPOTLIGHT HERO
    # ════════════════════════════════════════════════════════════════
    st.markdown(f"""
        <div class="dlg-hero">
            <div><img src="{escape(display_img)}" alt="{escape(artist_name)}"></div>
            <div>
                <h2 class="dlg-hero-name">{escape(artist_name)}</h2>
                <div class="dlg-hero-badges">
                    <span class="dlg-badge dlg-badge-rank">🏆 #{rank_val}</span>
                    <span class="dlg-badge dlg-badge-country">🌎 {display_country}</span>
                    <span class="dlg-badge dlg-badge-ml">🎧 {monthly_val} Monthly</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════
    # SECTION 2: SPOTLIGHT KPI GRID
    # ════════════════════════════════════════════════════════════════
    st.markdown(f"""
        <div class="dlg-section">
            <div class="dlg-section-title">📊 Artist Spotlight <span class="dlg-section-badge">Overview</span></div>
            <div style="font-size: 0.82rem; color: {dlg_text2}; margin: 8px 4px 12px; line-height: 1.4; font-weight: 500;">
                Consolidated artist performance metrics tracking chart momentum, catalog depth, and audience reach in real-time.
            </div>
            <div class="dlg-kpi-grid">
                <div class="dlg-kpi">
                    <div class="dlg-kpi-label"><span>🏆</span> Current Rank</div>
                    <div class="dlg-kpi-value">{rank_val}</div>
                    <div class="dlg-kpi-note">Latest chart position</div>
                </div>
                <div class="dlg-kpi">
                    <div class="dlg-kpi-label"><span>🎵</span> Songs</div>
                    <div class="dlg-kpi-value">{songs_val}</div>
                    <div class="dlg-kpi-note">Catalog tracks</div>
                </div>
                <div class="dlg-kpi">
                    <div class="dlg-kpi-label"><span>💽</span> Albums</div>
                    <div class="dlg-kpi-value">{albums_val}</div>
                    <div class="dlg-kpi-note">Catalog albums</div>
                </div>
                <div class="dlg-kpi">
                    <div class="dlg-kpi-label"><span>🌎</span> LATAM Countries</div>
                    <div class="dlg-kpi-value">{countries_val}</div>
                    <div class="dlg-kpi-note">Market presence</div>
                </div>
                <div class="dlg-kpi">
                    <div class="dlg-kpi-label"><span>🎧</span> Monthly Listeners</div>
                    <div class="dlg-kpi-value">{monthly_val}</div>
                    <div class="dlg-kpi-note">Current audience</div>
                </div>
                <div class="dlg-kpi">
                    <div class="dlg-kpi-label"><span>📈</span> Peak Listeners</div>
                    <div class="dlg-kpi-value">{peak_val}</div>
                    <div class="dlg-kpi-note">Historical high</div>
                </div>
                <div class="dlg-kpi">
                    <div class="dlg-kpi-label"><span>⭐</span> Total Points</div>
                    <div class="dlg-kpi-value">{points_val}</div>
                    <div class="dlg-kpi-note">Cross-platform score</div>
                </div>
                <div class="dlg-kpi">
                    <div class="dlg-kpi-label"><span>📊</span> Trend</div>
                    <div class="dlg-kpi-value">{escape(trend_change)}</div>
                    <div class="dlg-kpi-note">Rank momentum</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════
    # SECTION 2.1: RANK TREND CHART (Last 7 Days)
    # ════════════════════════════════════════════════════════════════
    if "artist_trend_days" not in st.session_state:
        st.session_state.artist_trend_days = 7

    tr_title_col, tr_c1, tr_c2, tr_c3, _ = st.columns([2.5, 0.9, 0.9, 0.9, 1.8], vertical_alignment="center")
    with tr_title_col:
        st.markdown(f"<div class='dlg-section-title' style='margin-bottom:0; border-bottom:none; padding-bottom:0;'>📈 Rank Trend</div>", unsafe_allow_html=True)
    with tr_c1:
        if st.button("7 Days", key=f"tr_7_{artist_name}", use_container_width=True, type="primary" if st.session_state.artist_trend_days == 7 else "secondary"):
            st.session_state.artist_trend_days = 7
    with tr_c2:
        if st.button("15 Days", key=f"tr_15_{artist_name}", use_container_width=True, type="primary" if st.session_state.artist_trend_days == 15 else "secondary"):
            st.session_state.artist_trend_days = 15
    with tr_c3:
        if st.button("30 Days", key=f"tr_30_{artist_name}", use_container_width=True, type="primary" if st.session_state.artist_trend_days == 30 else "secondary"):
            st.session_state.artist_trend_days = 30

    st.markdown(f"<div style='border-bottom: 1px solid {dlg_divider}; margin-bottom: 14px; margin-top: -10px;'></div>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:{dlg_text2}; font-size:.85rem; margin-top:5px; margin-bottom:15px;'>Visual tracking of daily rank movement and chart stability over the past {st.session_state.artist_trend_days} days.</p>", unsafe_allow_html=True)

    try:
        # Using history from the global scope populated by load_dashboard_data
        if 'history' in globals() and history is not None and not history.empty:
            artist_hist = history[history["name"] == artist_name].copy()
            if not artist_hist.empty:
                artist_hist["scraped_at"] = pd.to_datetime(artist_hist["scraped_at"])
                latest_date = artist_hist["scraped_at"].max()
                if pd.notna(latest_date):
                    start_date = latest_date - pd.Timedelta(days=st.session_state.artist_trend_days)
                    week_hist = artist_hist[artist_hist["scraped_at"] >= start_date].sort_values("scraped_at")
                    
                    if not week_hist.empty:
                        fig_rh = px.line(
                            week_hist,
                            x="scraped_at",
                            y="rank",
                            markers=True,
                            line_shape="hv",
                            color_discrete_sequence=["#fb7185"]
                        )
                        fig_rh.update_yaxes(autorange="reversed", title="Rank Position")
                        fig_rh.update_xaxes(title="", tickformat="%b %d")
                        style_figure(fig_rh, 300, dark_mode=is_dark)
                        render_plotly_html(fig_rh)
                        st.markdown(f"""
                            <div style="margin: -8px 0 20px; font-size: 0.82rem; color: {dlg_text2}; line-height: 1.5; font-style: italic;">
                                This chart tracks the artist's daily rank velocity. A consistent or rising trajectory (lower numerical rank) indicates sustained consumer demand and strong algorithmic health across major streaming and retail platforms.
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.info("Insufficient rank data for the last 7 days.")
            else:
                st.info("No historical rank data found for this artist.")
    except Exception as e:
        st.warning(f"Rank trend chart unavailable: {e}")

    # ════════════════════════════════════════════════════════════════
    # SECTION 3: TOP TRACKS, ALBUMS & COUNTRIES
    # ════════════════════════════════════════════════════════════════
    st.markdown(f"""
        <div class="dlg-panel">
            <div class="dlg-panel-header">📊 Top Tracks, Albums & Countries</div>
            <div class="dlg-panel-body">
                <div style="font-size: 0.82rem; color: {dlg_text2}; margin: 0 0 14px; line-height: 1.4; font-weight: 500;">
                    Consolidated catalog distribution tracking lead track velocity, project performance, and regional chart footprint.
                </div>
                <div class="dlg-lists-grid">
                    <div>
                        <div class="dlg-list-title">🎵 Top Tracks</div>
                        <div style="font-size: .78rem; color: {dlg_text2}; margin-bottom: 8px;">High-velocity tracks driving the majority of recent stream volume.</div>
                        <ol class="dlg-list">{songs_html}</ol>
                    </div>
                    <div>
                        <div class="dlg-list-title">💿 Top Albums</div>
                        <div style="font-size: .78rem; color: {dlg_text2}; margin-bottom: 8px;">Top-performing projects across global digital storefronts.</div>
                        <ol class="dlg-list">{albums_html}</ol>
                    </div>
                    <div>
                        <div class="dlg-list-title">🌍 Top Countries</div>
                        <div style="font-size: .78rem; color: {dlg_text2}; margin-bottom: 8px;">Markets with the strongest relative chart presence for the artist.</div>
                        <ol class="dlg-list">{countries_html}</ol>
                    </div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════
    # SECTION 7: ACQUISITION INTELLIGENCE
    # ════════════════════════════════════════════════════════════════
    st.markdown(f"""
        <div class="dlg-section-title">🎯 Acquisition Intelligence <span class="dlg-section-badge">Intelligence</span></div>
        <div style="font-size: 0.82rem; color: {dlg_text2}; margin: 8px 4px 12px; line-height: 1.4; font-weight: 500;">
            Advanced commercial signal analysis tracking cross-platform momentum, stream acceleration, and acquisition viability.
        </div>
    """, unsafe_allow_html=True)
    
    acq_loader_slot = st.empty()
    acq_loader_bg = "rgba(17, 26, 46, 0.5)" if is_dark else "rgba(241, 245, 249, 0.5)"
    acq_loader_border = "rgba(148, 163, 184, 0.15)" if is_dark else "rgba(148, 163, 184, 0.3)"
    acq_loader_text = "#cdd6e4" if is_dark else "#475569"

    acq_loader_slot.markdown(f"""
        <style>
        @keyframes acq-spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        .acq-loader-box {{
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            gap: 14px; padding: 40px 20px;
            background: {acq_loader_bg}; border-radius: 12px;
            border: 1px solid {acq_loader_border}; margin: 16px 0;
        }}
        .acq-loader-ring {{
            width: 38px; height: 38px; border-radius: 50%;
            border: 3px solid rgba(251, 113, 133, 0.18);
            border-top-color: #fb7185;
            animation: acq-spin 1s linear infinite;
        }}
        .acq-loader-text {{
            font-size: .88rem; font-weight: 600; color: {acq_loader_text};
        }}
        </style>
        <div class="acq-loader-box">
            <div class="acq-loader-ring"></div>
            <div class="acq-loader-text">Loading profile data...</div>
        </div>
    """, unsafe_allow_html=True)

    try:
        # Use a container to replace the loader once data is ready
        acq_content_slot = st.empty()
        with acq_content_slot.container():
            sp_df = _load_daily("spotify_daily", "global", WINDOW_DAYS)
            it_df = _load_daily("itunes_daily", "ww", WINDOW_DAYS)
            universe_df = _load_artist_universe(WINDOW_DAYS)
            sp_artist_df = _load_spotify_artist_series(WINDOW_DAYS)
            it_artist_df = _load_itunes_artist_series(WINDOW_DAYS)

            date_set = set()
            if not sp_artist_df.empty:
                date_set.update(sp_artist_df["scrape_date"].unique())
            if not it_artist_df.empty:
                date_set.update(it_artist_df["scrape_date"].unique())
            dates = sorted(date_set)

            if dates and not universe_df.empty:
                # Clear the loader once we start processing
                acq_loader_slot.empty()

                all_payloads = _build_artist_payloads(universe_df, sp_artist_df, it_artist_df, sp_df, it_df, dates)
                acq = all_payloads.get(artist_name)

                if acq:
                    sig_text = acq["signal"]
                    sig_cls = "dlg-sig-buy" if "BUY" in sig_text else ("dlg-sig-caution" if "CAUT" in sig_text else "dlg-sig-watch")

                    st.markdown(f"""
                        <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px;flex-wrap:wrap;">
                            <span class="dlg-acq-signal {sig_cls}">{sig_text}</span>
                            <span style="color:{dlg_text2};font-size:.88rem;font-weight:600;">
                                Acquisition Score: <b style="color:{dlg_text1};font-size:1.1rem;">{acq['acqScore']}</b>
                            </span>
                            <span style="color:{dlg_text2};font-size:.88rem;">
                                Label: <b style="color:{dlg_text1};">{escape(acq['label'])}</b>
                            </span>
                            <span style="color:{'#34d399' if acq['momentum'] >= 0 else '#fb7185'};font-size:.88rem;font-weight:700;">
                                {'+' if acq['momentum'] >= 0 else ''}{acq['momentum']}% momentum
                            </span>
                        </div>
                    """, unsafe_allow_html=True)

                    # Acquisition KPIs
                    st.markdown(f"""
                        <div class="dlg-kpi-grid">
                            <div class="dlg-kpi"><div class="dlg-kpi-label"><span>🏆</span> Best Spotify Rank</div><div class="dlg-kpi-value">{acq['bestSpRank']}</div><div class="dlg-kpi-note">{escape(str(acq['bestSpSub']))}</div></div>
                            <div class="dlg-kpi"><div class="dlg-kpi-label"><span>📈</span> Peak Streams</div><div class="dlg-kpi-value">{acq['peakStreams']}</div><div class="dlg-kpi-note">{escape(str(acq['peakStreamsSub']))}</div></div>
                            <div class="dlg-kpi"><div class="dlg-kpi-label"><span>🎤</span> Tracks Charting</div><div class="dlg-kpi-value">{acq['trackCount']}</div><div class="dlg-kpi-note">{escape(str(acq['trackCountSub']))}</div></div>
                            <div class="dlg-kpi"><div class="dlg-kpi-label"><span>🍎</span> Best iTunes WW</div><div class="dlg-kpi-value">{acq['bestItunes']}</div><div class="dlg-kpi-note">{escape(str(acq['itunesSub']))}</div></div>
                        </div>
                    """, unsafe_allow_html=True)

                    # Top Tracks on Spotify Global
                    if acq.get("tracks"):
                        tracks_rows = ""
                        for i, t in enumerate(acq["tracks"]):
                            tracks_rows += f"""<div class="dlg-trk-row">
                                <span class="dlg-trk-rank">{i+1}</span>
                                <span class="dlg-trk-name">{escape(str(t['name']))}</span>
                                <span class="dlg-trk-val">{acq_fmt_n(t['streams'])}</span>
                                <span class="dlg-trk-val">#{t['rank'] if t.get('rank') else '—'}</span>
                            </div>"""
                        st.markdown(f"""
                            <div class="dlg-panel">
                                <div class="dlg-panel-header">🎵 Top Tracks · Spotify Global</div>
                                <div class="dlg-panel-body">
                                    <div style="font-size: 0.82rem; color: {dlg_text2}; margin: 0 0 14px; line-height: 1.4; font-weight: 500;">
                                        Strategic analysis of lead track velocity and total consumption volume across the Spotify Global ecosystem.
                                    </div>
                                    <div class="dlg-trk-row" style="border-bottom:1px solid {dlg_divider};font-size:.7rem;color:{dlg_text2};text-transform:uppercase;letter-spacing:.06em;font-weight:700;">
                                        <span style="text-align:center;">#</span><span>Track</span><span style="text-align:right;">Streams</span><span style="text-align:right;">Best</span>
                                    </div>
                                    {tracks_rows}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

                    # Acquisition Signals
                    if acq.get("signals"):
                        sig_rows = ""
                        for s in acq["signals"]:
                            sig_rows += f"""<div class="dlg-sig-row">
                                <span class="dlg-sig-icon">{s['icon']}</span>
                                <div><div class="dlg-sig-title">{escape(s['title'])}</div><div class="dlg-sig-desc">{escape(s['desc'])}</div></div>
                            </div>"""
                        st.markdown(f"""
                            <div class="dlg-panel">
                                <div class="dlg-panel-header">💡 Why This Artist · Signals</div>
                                <div class="dlg-panel-body">{sig_rows}</div>
                            </div>
                        """, unsafe_allow_html=True)

                    # Quote
                    if acq.get("quote"):
                        st.markdown(f"""
                            <div style="border-left:3px solid rgba(96,165,250,.5);padding:10px 16px;margin:8px 0 16px;
                                background:rgba(96,165,250,.06);border-radius:0 8px 8px 0;
                                font-size:.88rem;color:{dlg_text2};line-height:1.65;font-style:italic;">
                                {escape(acq['quote'])}
                            </div>
                        """, unsafe_allow_html=True)

                else:
                    acq_loader_slot.empty()
                    st.info(f"No acquisition data available for {artist_name} in the current {WINDOW_DAYS}-day window.")
            else:
                acq_loader_slot.empty()
                st.info("No acquisition date range available — data may still be loading.")
    except Exception as exc:
        acq_loader_slot.empty()
        st.warning(f"Could not load acquisition data: {exc}")

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
            WITH bounds AS (
                SELECT MAX(scraped_at) AS ts, MAX(scrape_date) AS max_d
                FROM itunes_artist_rankings
            ),
            top_artists AS (
                SELECT artist_id
                FROM itunes_artist_rankings r
                JOIN bounds b ON r.scraped_at = b.ts
                WHERE r.rank <= 300
            )
            SELECT a.name, r.rank, r.scraped_at
            FROM itunes_artist_rankings r
            JOIN artists a ON a.id = r.artist_id
            CROSS JOIN bounds b
            WHERE r.artist_id IN (SELECT artist_id FROM top_artists)
              AND r.scrape_date >= (b.max_d - 35::int)
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
        """,
        "artist_labels": """
            WITH split_artists AS (
                SELECT TRIM(SPLIT_PART(artist_title, ' - ', 1)) as name, label, date
                FROM spotify_daily
                WHERE label IS NOT NULL AND label != '' AND label != 'Independent'
            ),
            latest_labels AS (
                SELECT name, label,
                       ROW_NUMBER() OVER(PARTITION BY name ORDER BY date DESC) as rn
                FROM split_artists
            )
            SELECT name, label FROM latest_labels WHERE rn = 1
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
        frames["details"][["name", "page_title", "snapshot_text", "songs_count", "albums_count", "countries_count", "top_songs", "top_albums", "top_countries"]],
        on="name",
        how="left",
    ).merge(
        frames["longevity"][["name", "times_on_chart", "weeks_on_chart", "times_at_top", "last_day_at_top", "max_countries", "best_rank"]],
        on="name",
        how="left"
    ).merge(
        frames["artist_labels"][["name", "label"]] if not frames["artist_labels"].empty else pd.DataFrame(columns=["name", "label"]),
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

    leaderboard["top_album"] = leaderboard["top_albums"].fillna("").apply(
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


def style_figure(fig, height: int, dark_mode: bool | None = None) -> None:
    if dark_mode is None:
        dark_mode = st.session_state.get("dark_mode", False)

    text_color = "#cdd6e4" if dark_mode else "#1A1A1A"
    grid_color = "rgba(255,255,255,0.06)" if dark_mode else "rgba(0,0,0,0.06)"
    line_color = "rgba(255,255,255,0.1)" if dark_mode else "rgba(0,0,0,0.1)"
    bg_color = "rgba(22,27,39,0.98)" if dark_mode else "rgba(255,255,255,0.98)"
    
    fig.update_layout(
        template="plotly_dark" if dark_mode else "plotly_white",
        height=max(280, int(height)),
        margin=dict(l=4, r=20, t=56, b=8, pad=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=text_color, family="Inter, ui-sans-serif, system-ui", size=11),
        legend_title_text="",
        title=dict(x=0.03, xanchor="left", font=dict(size=15, color=text_color)),
        hoverlabel=dict(
            bgcolor=bg_color,
            bordercolor=line_color,
            font=dict(color=text_color, size=11),
        ),
    )
    fig.update_xaxes(
        gridcolor=grid_color,
        zerolinecolor=grid_color,
        linecolor=line_color,
        tickcolor=line_color,
        tickfont=dict(size=11),
        title_font=dict(size=12),
    )
    fig.update_yaxes(
        gridcolor=grid_color,
        zerolinecolor=grid_color,
        linecolor=line_color,
        tickcolor=line_color,
        tickfont=dict(size=11),
        title_font=dict(size=12),
    )


def render_header(title: str, meta: str, last_run_label: str) -> None:
    st.markdown(
        f"""
        <section class="page-header-box">
            <div class="page-header-content">
                <div class='page-title' style='animation: slideIn 0.5s ease-out;'>{escape(title)}</div>
                <div class='page-meta'>{escape(meta)} · Last run: {escape(last_run_label)}</div>
            </div>
            <div class="live-indicator page-header-badge">
                <span class="live-dot"></span>
                LIVE
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    st.markdown(
        """
        <div class="app-footer">
            <div><a href="mailto:info@chromadata.ai">info@chromadata.ai</a></div>
            <div>© 2026 - Chromadata. All rights reserved.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(leaderboard: pd.DataFrame, runs: pd.DataFrame) -> None:
    success_rate = (runs["status"].eq("success").mean() * 100) if not runs.empty else 0
    
    try:
        from src.database.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    WITH latest_run AS (
                        SELECT MAX(scraped_at) AS ts FROM spotify_artists
                    ),
                    top_artists AS (
                        SELECT monthly_listeners
                        FROM spotify_artists
                        WHERE scraped_at = (SELECT ts FROM latest_run)
                        ORDER BY monthly_listeners DESC NULLS LAST
                        LIMIT 300
                    )
                    SELECT SUM(monthly_listeners) 
                    FROM top_artists
                """)
                result = cur.fetchone()
                total_monthly = result[0] if result and result[0] else 0
    except Exception:
        total_monthly = leaderboard.nlargest(300, "monthly_listeners")["monthly_listeners"].fillna(0).sum()    
        
    total_artists = len(leaderboard)
    latam_artists = int(leaderboard["latam_signal"].sum()) if "latam_signal" in leaderboard else 0
    avg_listeners = float(leaderboard["monthly_listeners"].mean()) if total_artists > 0 else 0.0
    top_markets = leaderboard["display_country"].replace("—", pd.NA).dropna().unique().tolist()
    unique_markets = len(top_markets)

    new_mask = leaderboard["rank_change"].fillna("").eq("NEW")
    new_entries = int(new_mask.sum())
    
    new_entries_details = ""
    if new_entries > 0:
        new_df = leaderboard[new_mask].sort_values("rank")
        details = []
        for _, row in new_df.iterrows():
            details.append(
                f"<div style='display:flex;justify-content:space-between;gap:1.5rem;padding:4px 0;margin-bottom:4px;'>"
                f"<span>{escape(str(row['name']))}</span>"
                f"<span style='color:var(--accent3);font-weight:700;'>{int(row['rank'])}</span>"
                f"</div>"
            )

        header_html = f"<div style='display:flex;justify-content:space-between;padding:2px 0 8px;margin-bottom:8px;border-bottom:1px solid var(--border);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.04em;color:var(--accent);font-weight:700;'><span>Artist</span><span>Rank</span></div>"
        new_entries_details = (
            "<div style='padding:0.85rem 0 0.35rem;color:var(--text2);font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;'>"
            "New Chart Entries</div>"
            f"{header_html}"
            "<div>" + "".join(details) + "</div>"
        )

    card_cols = st.columns([1, 1, 1, 1], gap='large')
    card_defs = [
        {
            'label': 'Active artists',
            'value': f"{total_artists:,}",
            'style': 'kpi-green',
            'note': f"{unique_markets} LATAM markets"
        },
        {
            'label': 'LATAM signal',
            'value': f"{latam_artists:,}",
            'style': 'kpi-amber',
            'note': f"{fmt_short(avg_listeners)} avg listeners"
        },
        {
            'label': 'New entries',
            'value': str(new_entries),
            'style': 'kpi-red' if new_entries else 'kpi-green',
            'note': 'Fresh chart momentum' if new_entries else 'No new entries'
        },
        {
            'label': 'Pipeline health',
            'value': f"{success_rate:.0f}%",
            'style': 'kpi-green' if success_rate >= 90 else 'kpi-amber',
            'note': f"{len(runs)} recent runs"
        },
    ]

    for col, card in zip(card_cols, card_defs):
        col.markdown(
            f"""
            <div class='kpi-card {card['style']}'>
                <div class='kpi-label'>{escape(card['label'])}</div>
                <div class='kpi-value'>{escape(card['value'])}</div>
                <div class='kpi-delta'>{escape(card['note'])}</div>
                <div class='progress-bar'><div class='progress-fill' style='width:{min(100, (total_monthly / 30_000_000_000 * 100) if card['label'] == 'Active artists' else (success_rate if card['label'] == 'Pipeline health' else 100))}%;'></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if new_entries > 0:
        with st.expander(f"📌 {new_entries} new leaderboard entries", expanded=False):
            st.markdown(new_entries_details, unsafe_allow_html=True)
    else:
        st.info("No new chart entries were added in the latest scrape.")


def prepare_leaderboard_table(leaderboard: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    table_df = leaderboard.head(max_rows)[
        [
            "rank",
            "name",
            "top_song",
            "top_country",
            "monthly_listeners",
            "peak_listeners",
        ]
    ].copy()
    table_df["monthly_listeners"] = table_df["monthly_listeners"].apply(fmt_short)
    table_df["peak_listeners"] = table_df["peak_listeners"].apply(fmt_short)
    table_df.columns = [
        "Rank",
        "Artist",
        "Top Song",
        "Top Country",
        "Monthly Listeners",
        "Peak Listeners",
    ]
    return table_df


def render_leaderboard_table_html(leaderboard: pd.DataFrame, max_rows: int, date_label: str = "n/a") -> None:
    table_df = leaderboard.head(max_rows).copy()
    rows_html = []
    current_theme = "dark" if st.session_state.get("dark_mode", False) else "light"
    for _, row in table_df.iterrows():
        rank = int(row["rank"]) if pd.notna(row["rank"]) else "—"
        rank_change = trend_badge_html(str(row.get("rank_change") or ""))
        artist_name = str(row.get("name") or "—")
        artist_url_name = quote(artist_name)
        artist_html = f"<a href='?artist_name={artist_url_name}&theme={current_theme}' target='_self' class='artist-link' title='Click for full profile'>{escape(artist_name)}</a>"
        top_song = str(row.get("top_song") or "—").strip()
        top_song_label = escape(top_song if len(top_song) <= 40 else top_song[:38] + "…")
        top_song_html = f"<span title=\"{escape(top_song)}\">{top_song_label}</span>"
        top_album = str(row.get("top_album") or "—").strip()
        top_album_label = escape(top_album if len(top_album) <= 40 else top_album[:38] + "…")
        top_album_html = f"<span title=\"{escape(top_album)}\">{top_album_label}</span>"    
        country = str(row.get("top_country") or "—").strip()
        country_html = f"<span class='country-pill'>{escape(country)}</span>" if country and country != "—" else "—"
        monthly = fmt_short(row.get("monthly_listeners"))
        peak = fmt_short(row.get("peak_listeners"))
        points = fmt_short(row.get("total_points"))

        rows_html.append(
            f"<tr>"
            f"<td class='pos-cell'>{rank}</td>"
            f"<td class='artist-cell'>{artist_html}</td>"
            f"<td>{top_song_html}</td>"
            f"<td>{top_album_html}</td>"
            f"<td>{country_html}</td>"
            f"<td class='num-cell'>{monthly}</td>"
            f"<td class='num-cell'>{peak}</td>"
            f"<td class='num-cell'>{points}</td>"
            f"<td>{rank_change}</td>"
            f"</tr>"
        )

    html = f"""
    <div class='dashboard-card'>
        <div class='section-title' style='display: flex; justify-content: space-between; align-items: center;'>
            <span>📊 Leaderboard table</span>
            <span class='time-chip'>{escape(date_label)}</span>
        </div>
        <div class='section-sub'>This is a music artist leaderboard showing the top artists ranked by their Spotify monthly listeners, along with their top song, album, market, peak listeners, iTunes total streams, and rank movement.</div>
        <div class='table-wrap' style='max-height:780px; overflow-x:auto; overflow-y:auto;'>
            <table class='leader-table'>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Artist Name</th>
                        <th>Top song</th>
                        <th>Top Album</th>
                        <th>Top market</th>
                        <th>Spotify Monthly listeners</th>
                        <th>Spotify Peak listeners</th>
                        <th>Itune Total Streams</th>
                        <th>Rank Movement</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows_html)}
                </tbody>
            </table>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_leaderboard(leaderboard: pd.DataFrame, runs: pd.DataFrame, max_rows: int, date_label: str = "n/a") -> None:
    if leaderboard.empty:
        st.warning("No leaderboard data available yet. Run the scraper first.")
        return

    # ── compute KPI values ─────────────────────────────────
    total_artists = len(leaderboard)
    avg_listeners_val = float(leaderboard["monthly_listeners"].mean()) if total_artists else 0.0
    avg_listeners = fmt_short(avg_listeners_val) if total_artists else "—"
    top_markets = [c for c in leaderboard["display_country"].unique().tolist() if c and c != "—"]
    latam_signal = int(leaderboard["latam_signal"].sum()) if "latam_signal" in leaderboard else 0
    new_entries = int(leaderboard["rank_change"].fillna("").eq("NEW").sum()) if "rank_change" in leaderboard else 0
    top_artist_row = leaderboard.sort_values("rank").head(1)
    top_artist_name = str(top_artist_row.iloc[0]["name"]) if not top_artist_row.empty else "—"

    is_dark = st.session_state.get("dark_mode", False)
    
    # Python-level dynamic CSS to ensure no variable inheritance issues
    lb_bg2 = "#161b26" if is_dark else "#FFFFFF"
    lb_bg3 = "#1f2633" if is_dark else "#F8F9FB"
    lb_bg4 = "#283041" if is_dark else "#EEF1F7"
    lb_line = "rgba(148,163,184,.15)" if is_dark else "rgba(148,163,184,.2)"
    lb_t1 = "#ffffff" if is_dark else "#1A1A1A"
    lb_t2 = "#cdd6e4" if is_dark else "#4A5568"
    lb_t3 = "#8b95ad" if is_dark else "#8A8FA3"

    css_template = """
        <style>
        /* ── leaderboard scoped palette ── */
        :root {
            --lb-bg2: __LB_BG2__;
            --lb-bg3: __LB_BG3__;
            --lb-bg4: __LB_BG4__;
            --lb-line: __LB_LINE__;
            --lb-t1: __LB_T1__;
            --lb-t2: __LB_T2__;
            --lb-t3: __LB_T3__;
            --lb-blue:   #60a5fa;
            --lb-green:  #34d399;
            --lb-purple: #c4b5fd;
            --lb-amber:  #fcd34d;
            --lb-pink:   #f9a8d4;
            --lb-red:    #fb7185;
        }
        /* hero */
        .lb-hero {
            position: relative;
            background: linear-gradient(135deg, #1a2238 0%, #1f1a3a 50%, #261d3d 100%);
            border: 1px solid rgba(148,163,184,.18);
            border-radius: 20px;
            padding: 24px 28px;
            margin-bottom: 1.4rem;
            margin-top: 1.0rem;
            box-shadow: 0 24px 60px rgba(0,0,0,.35);
            overflow: hidden;
        }
        .lb-hero::after {
            content: ""; position: absolute; right: -120px; top: -120px;
            width: 320px; height: 320px;
            background: radial-gradient(circle, rgba(96,165,250,.18), transparent 60%);
            pointer-events: none;
        }
        .lb-hero-eyebrow {
            display: inline-flex; align-items: center; gap: 10px;
            font-size: 12px; font-weight: 800; letter-spacing: .18em;
            text-transform: uppercase; color: var(--lb-t3); margin-bottom: 12px;
        }
        .lb-hero-dot {
            width: 10px; height: 10px; border-radius: 50%;
            background: var(--lb-green);
            box-shadow: 0 0 0 4px rgba(52,211,153,.18), 0 0 14px rgba(52,211,153,.55);
            animation: lb-pulse 2s ease-in-out infinite;
        }
        @keyframes lb-pulse {
            0%,100% { box-shadow: 0 0 0 4px rgba(52,211,153,.18), 0 0 14px rgba(52,211,153,.55); }
            50%     { box-shadow: 0 0 0 8px rgba(52,211,153,.05), 0 0 22px rgba(52,211,153,.85); }
        }
        .lb-hero-title { font-size: 2.2rem; font-weight: 900; letter-spacing: -.02em; color: var(--lb-t1); margin-bottom: 6px; line-height: 1.1; }
        .lb-hero-sub { font-size: 0.95rem; color: var(--lb-t2); font-weight: 500; }
        .lb-hero-sub b { color: var(--lb-t1); font-weight: 700; }

        /* KPI tiles */
        .lb-kpi-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 14px;
            margin-bottom: 1.4rem;
        }
        .lb-kpi {
            position: relative;
            background: var(--lb-bg2);
            border: 1px solid var(--lb-line);
            border-radius: 16px;
            padding: 18px 18px 16px 22px;
            box-shadow: 0 12px 24px rgba(0,0,0,.18);
            overflow: hidden;
            transition: transform .2s ease, border-color .2s ease;
        }
        .lb-kpi:hover { transform: translateY(-2px); border-color: rgba(148,163,184,.3); }
        .lb-kpi::before {
            content:""; position:absolute; left:0; top:14%; bottom:14%; width:4px;
            border-radius: 0 4px 4px 0; background: var(--lb-blue);
        }
        .lb-kpi.k-blue::before   { background: var(--lb-blue); }
        .lb-kpi.k-green::before  { background: var(--lb-green); }
        .lb-kpi.k-purple::before { background: var(--lb-purple); }
        .lb-kpi.k-amber::before  { background: var(--lb-amber); }
        .lb-kpi.k-pink::before   { background: var(--lb-pink); }
        .lb-kpi-lbl { font-size: 11px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--lb-t3); margin-bottom: 10px; }
        .lb-kpi-val { font-size: 26px; font-weight: 900; color: var(--lb-t1); line-height: 1.1; margin-bottom: 6px; letter-spacing: -.01em; }
        .lb-kpi.k-blue   .lb-kpi-val { color: var(--lb-blue); }
        .lb-kpi.k-green  .lb-kpi-val { color: var(--lb-green); }
        .lb-kpi.k-purple .lb-kpi-val { color: var(--lb-purple); }
        .lb-kpi.k-amber  .lb-kpi-val { color: var(--lb-amber); }
        .lb-kpi.k-pink   .lb-kpi-val { color: var(--lb-pink); }
        .lb-kpi-sub { font-size: 12px; color: var(--lb-t2); font-weight: 500; line-height: 1.35; }

        /* sectioned cards */
        .lb-section {
            background: var(--lb-bg2);
            border: 1px solid var(--lb-line);
            border-radius: 16px;
            padding: 18px 20px 14px;
            margin-bottom: 1.4rem;
            box-shadow: 0 14px 30px rgba(0,0,0,.18);
        }
        .lb-section-hdr {
            display:flex; align-items:center; justify-content:space-between;
            margin-bottom: 12px;
        }
        .lb-section-title { font-size: 1.05rem; font-weight: 800; color: var(--lb-t1); letter-spacing: -.005em; }
        .lb-section-badge {
            font-size: 11px; font-weight: 700; letter-spacing: .1em;
            text-transform: uppercase; color: var(--lb-t2);
            background: var(--lb-bg3); border: 1px solid var(--lb-line);
            padding: 5px 12px; border-radius: 999px;
        }

        /* Plotly chart wrapper */
        [data-testid="stPlotlyChart"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 0.5rem 0.5rem 0.25rem;
            margin-top: 0 !important;
            margin-bottom: 0.85rem !important;
            box-shadow: 0 14px 30px rgba(0,0,0,.1);
            transition: border-color 0.2s ease, transform 0.2s ease;
        }
        [data-testid="stPlotlyChart"]:hover {
            border-color: rgba(251, 113, 133, 0.35);
            transform: translateY(-2px);
        }
        /* last chart in right column: drop bottom margin so column matches table card */
        [data-testid="column"]:nth-child(2) [data-testid="stPlotlyChart"]:last-of-type {
            margin-bottom: 0 !important;
        }
        /* dashboard-card wrapping the table: trim margins */
        [data-testid="column"]:nth-child(1) .dashboard-card {
            margin-bottom: 0 !important;
        }
        [data-testid="column"]:nth-child(2) > div:first-child { padding-top: 0 !important; margin-top: 0 !important; }
        [data-testid="column"]:nth-child(2) .element-container:first-of-type { margin-top: 0 !important; }
        </style>
        """

    css_code = css_template.replace("__LB_BG2__", lb_bg2).replace("__LB_BG3__", lb_bg3).replace("__LB_BG4__", lb_bg4).replace("__LB_LINE__", lb_line).replace("__LB_T1__", lb_t1).replace("__LB_T2__", lb_t2).replace("__LB_T3__", lb_t3)
    st.markdown(css_code, unsafe_allow_html=True)

    # ── KPI tiles ─────────────────────────────────────────
    # (removed per request)

    render_leaderboard_table_html(leaderboard, max_rows, date_label=date_label)

    chart_col1, chart_col2 = st.columns(2, gap="medium")
    text_color = "#e0e7ff" if is_dark else "#1A1A1A"

    with chart_col1:
        top_ranked = leaderboard.dropna(subset=["rank", "total_points"]).nsmallest(10, "rank").copy()
        if not top_ranked.empty:
            top_ranked = top_ranked.sort_values("rank", ascending=False)
            top_ranked["rank_label"] = "#" + top_ranked["rank"].astype(str)
            top_ranked["points_label"] = top_ranked["total_points"].apply(fmt_short)
            rank_colors = ["#fb7185", "#60a5fa", "#34d399", "#c4b5fd", "#fcd34d",
                           "#5eead4", "#f9a8d4", "#84cc16", "#f97316", "#a855f7"]

            fig_rank = px.bar(
                top_ranked,
                y="name",
                x="total_points",
                orientation="h",
                text="points_label",
                color="rank",
                custom_data=["top_country", "rank", "monthly_listeners"],
                labels={"total_points": "Total Points", "name": ""},
                color_continuous_scale=["#fb7185", "#60a5fa", "#34d399"],
            )
            style_figure(fig_rank, 440, dark_mode=is_dark)
            fig_rank.update_traces(
                textposition="outside",
                cliponaxis=False,
                marker=dict(opacity=0.92, line=dict(width=0.6, color="rgba(255,255,255,.12)") if is_dark else dict(width=0)),
                textfont=dict(color=text_color, size=11),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "<b>Rank:</b> #%{customdata[1]}<br>"
                    "<b>Total Points:</b> %{x:,.0f}<br>"
                    "<b>Monthly listeners:</b> %{customdata[2]:,.0f}<br>"
                    "<b>Top market:</b> %{customdata[0]}<extra></extra>"
                ),
            )
            fig_rank.update_layout(
                title=dict(text="Top by Itunes Streams", font=dict(color=text_color)),
                coloraxis=dict(showscale=False),
                yaxis_title="",
                xaxis_tickformat="~s",
                xaxis_title="Itunes Streams",
                uniformtext_minsize=9,
                uniformtext_mode="hide",
            )
            render_plotly_html(fig_rank)
        else:
            st.info("No ranking data available for the current leaderboard selection.")

    with chart_col2:
        # Monthly Listeners
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
                custom_data=["top_country", "rank"],
                labels={"monthly_listeners": "Monthly listeners", "name": ""},
                color_continuous_scale=["#fda4af", "#fb7185", "#be123c"],
            )
            style_figure(fig_bar, 440, dark_mode=is_dark)
            fig_bar.update_traces(
                textposition="outside",
                cliponaxis=False,
                marker=dict(opacity=0.92, line=dict(width=0.6, color="rgba(255,255,255,.12)") if is_dark else dict(width=0)),
                textfont=dict(color=text_color, size=11),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "<b>Monthly listeners:</b> %{x:,.0f}<br>"
                    "<b>Rank:</b> #%{customdata[1]}<br>"
                    "<b>Market:</b> %{customdata[0]}<extra></extra>"
                ),
            )
            annotation_color = "#fcd34d" if is_dark else "#d97706"
            fig_bar.add_vline(
                x=avg_listeners,
                line_dash="dash",
                line_color="rgba(251,146,60,.85)" if is_dark else "rgba(217,119,6,.6)",
                line_width=2,
                annotation_text=f"Avg {fmt_short(avg_listeners)}",
                annotation_position="top right",
                annotation_font_size=11,
                annotation_font_color=annotation_color,
            )
            fig_bar.update_layout(
                title=dict(text="Top by Spotify Monthly Listeners", font=dict(color=text_color)),
                coloraxis=dict(showscale=False),
                xaxis_title="Spotify Monthly listeners",
                xaxis_tickformat="~s",
                yaxis_title="",
                uniformtext_minsize=11,
                uniformtext_mode="hide",
            )
            render_plotly_html(fig_bar)
        else:
            st.info("No monthly listener data is available for the current leaderboard selection.")



def render_stream_trends(top_spotify: pd.DataFrame, leaderboard: pd.DataFrame, top_history: pd.DataFrame, history: pd.DataFrame = pd.DataFrame()) -> None:
    # Explicitly use global go or re-import to fix UnboundLocalError in some environments
    import plotly.graph_objects as go
    
    if leaderboard.empty:
        st.warning("No streaming data available yet.")
        return

    top_spotify = leaderboard.dropna(subset=["monthly_listeners"]).nlargest(12, "monthly_listeners")
    if top_spotify.empty:
        st.info("Spotify listener data has not been scraped yet.")
        return

    # Interactive metric selector
    st.markdown("### 🎵 Streaming Analytics")
    
    tab1, tab2, tab3 = st.tabs(["🎧 Listener Momentum", "🌍 Market Reach", "🏆 Artist Performance Chart"])
    
    with tab1:
        c1, c2 = st.columns(2)
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
                marker_color="#fb7185",
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
            render_plotly_html(fig)

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
                color_continuous_scale=["#FFB547", "#34D399"],
                title="📊 Growth Potential %"
            )
            fig_growth.update_layout(coloraxis_showscale=False)
            style_figure(fig_growth, 420)
    
    with tab2:
        col_select, col_spacer = st.columns([0.25, 0.75])
        with col_select:
            top_n_market = custom_selectbox(
                "Top artists",
                [10, 50, 100, 200],
                index=1,
                key="market_reach_top_n",
            )

        market_scope = leaderboard.dropna(subset=["rank"]).sort_values("rank").head(top_n_market).copy()
        if market_scope.empty:
            market_scope = leaderboard.head(top_n_market).copy()

        if len(market_scope) < top_n_market:
            st.caption(f"Showing {len(market_scope)} artists because fewer ranked rows are available.")

        point_sources = {
            "itunes_points": "iTunes",
            "spotify_points": "Spotify",
            "apple_music_points": "Apple Music",
            "shazam_points": "Shazam",
            "youtube_points": "YouTube",
            "other_points": "Other",
        }

        source_totals = []
        for col_name, label in point_sources.items():
            total_value = float(market_scope[col_name].fillna(0).sum()) if col_name in market_scope.columns else 0.0
            source_totals.append({"source": label, "points": total_value})

        source_df = pd.DataFrame(source_totals)
        source_df = source_df[source_df["points"] > 0].sort_values("points", ascending=False)

        if source_df.empty:
            st.info("Market reach needs source point breakdown data (itunes_points, spotify_points, apple_music_points, shazam_points, youtube_points, other_points).")
        else:
            total_market_points = float(source_df["points"].sum())
            dominant_row = source_df.iloc[0]
            dominant_share = (float(dominant_row["points"]) / total_market_points * 100) if total_market_points > 0 else 0
            other_points = float(source_df.loc[source_df["source"] == "Other", "points"].sum())
            other_share = (other_points / total_market_points * 100) if total_market_points > 0 else 0

            summary_cards = [
                ("Total charting slots", f"{len(market_scope):,}", f"Top {top_n_market} this week", ""),
                ("Sources represented", f"{len(source_df)}", f"across {len(market_scope):,} slots", ""),
                ("Dominant source", str(dominant_row["source"]), f"{dominant_row['points']:,.0f} pts ({dominant_share:.0f}%)", "kpi-green"),
                ("Other share", f"{other_share:.1f}%", f"{other_points:,.0f} of {total_market_points:,.0f} points", "kpi-amber"),
            ]
            card_cols = st.columns(4)
            for col, (label, value, note, klass) in zip(card_cols, summary_cards):
                col.markdown(
                    f"""
                    <div class="kpi-card {klass}">
                        <div class="kpi-label">{escape(label)}</div>
                        <div class="kpi-value">{escape(value)}</div>
                        <div class="kpi-delta">{escape(note)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                pie_df = source_df.copy()
                pie_df["share"] = pie_df["points"] / total_market_points * 100

                fig_market_share = px.pie(
                    pie_df,
                    names="source",
                    values="points",
                    hole=0.58,
                    color="source",
                    custom_data=["source"],
                    color_discrete_sequence=CHART_COLORS,
                    title=f"Label share of Top {top_n_market} slots",
                )
                fig_market_share.update_traces(
                    sort=False,
                    textposition="inside",
                    textinfo="percent+label",
                    hovertemplate="<b>%{label}</b><br>Points: %{value:,.0f}<br>Share: %{percent}<extra></extra>",
                )
                fig_market_share.update_layout(
                    showlegend=True,
                    legend_title_text="",
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
                style_figure(fig_market_share, 440)
                render_plotly_html(fig_market_share)

            with chart_col2:
                bars_df = source_df.sort_values("points", ascending=True).copy()
                bar_colors = [CHART_COLORS[idx % len(CHART_COLORS)] for idx in range(len(bars_df))]
                
                fig_source_bars = go.Figure(
                    data=[
                        go.Bar(
                            x=bars_df["points"],
                            y=bars_df["source"],
                            orientation="h",
                            marker=dict(color=bar_colors, line=dict(width=0)),
                            text=[f"{int(v):,.0f}" for v in bars_df["points"]],
                            textposition="outside",
                            cliponaxis=False,
                            hovertemplate="<b>%{y}</b><br>Points: %{x:,.0f}<extra></extra>",
                        )
                    ]
                )
                fig_source_bars.update_layout(
                    title=dict(text=f"Points per source - Top {top_n_market}", x=0.03, xanchor="left", font=dict(size=18)),
                    showlegend=False,
                    xaxis_title="",
                    yaxis_title="",
                    margin=dict(l=70, r=20, t=70, b=40),
                    bargap=0.35,
                )
                fig_source_bars.update_xaxes(showgrid=False)
                fig_source_bars.update_yaxes(
                    autorange="reversed",
                    tickfont=dict(size=13, color="#e8eaf6"),
                    ticklabelstandoff=18,
                    showgrid=False,
                )
                style_figure(fig_source_bars, 440)
                render_plotly_html(fig_source_bars)

    with tab3:
        # Control bar for Global Charting
        gl_control1, gl_control2 = st.columns([1, 1])
        with gl_control1:
            top_n_options = [10, 20, 50, 100, 200]
            selected_n = custom_selectbox("🎯 Select Top List", [str(n) for n in top_n_options], index=2, key="gl_chart_top_n_dropdown")
            selected_n = int(selected_n)
        
        with gl_control2:
            time_ranges = {1: "Daily (Last Run)", 7: "7 days", 14: "14 days", 30: "30 days"}
            selected_days_str = custom_selectbox("📅 Time Range", [time_ranges[k] for k in time_ranges.keys()], index=0, key="gl_chart_time_range")
            # Find the key that matches the selected value
            selected_days = [k for k, v in time_ranges.items() if v == selected_days_str][0]

        # Filter and prepare base data
        gl_filtered = leaderboard.dropna(subset=["rank"]).sort_values("rank").head(selected_n)
        
        # Calculate Range-Aware Movement & Peak Logic
        gl_filtered = gl_filtered.copy()
        gl_filtered["current_pos"] = pd.to_numeric(gl_filtered["rank"], errors="coerce")
        gl_filtered["db_change"] = pd.to_numeric(gl_filtered["rank_change"], errors="coerce").fillna(0)
        
        # Ensure history is UTC and normalized
        if not history.empty:
            history["scraped_at"] = pd.to_datetime(history["scraped_at"], utc=True)
            avail_min = history["scraped_at"].min()
            avail_max = history["scraped_at"].max()
            days_avail = (avail_max - avail_min).days
        
        # Calculate Start Position & Range Peak from History
        cutoff_date = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=selected_days)
        
        start_positions = {}
        range_peaks = {}
        
        for name in gl_filtered["name"].unique():
            if selected_days == 0:
                # DAILY MODE: Use the rank_change from DB (pgAdmin style)
                row = gl_filtered[gl_filtered["name"] == name].iloc[0]
                # Start pos = Current pos + Change (since change = Start - Current, wait...)
                # In our logic: range_change = start_pos - current_pos.
                # In DB: rank_change is usually current - previous? 
                # Let's check: if rank goes 10 -> 9, change is +1 (improvement).
                # So Start = 10, Current = 9. Start = Current + Change.
                start_positions[name] = row["current_pos"] + row["db_change"]
                range_peaks[name] = min(row["current_pos"], start_positions[name])
            else:
                # RANGE MODE: Find history records within the window
                artist_hist = history[(history["name"] == name) & (history["scraped_at"] >= cutoff_date)] if not history.empty else pd.DataFrame()
                
                if not artist_hist.empty:
                    # Find the record closest to the START of the window (oldest)
                    sorted_hist = artist_hist.sort_values("scraped_at")
                    start_positions[name] = sorted_hist.iloc[0]["rank"]
                    range_peaks[name] = artist_hist["rank"].min() # Best rank in window
                else:
                    # Fallback to current rank if no history
                    curr = gl_filtered[gl_filtered["name"] == name]["current_pos"].iloc[0]
                    start_positions[name] = curr
                    range_peaks[name] = curr

        gl_filtered["start_pos"] = gl_filtered["name"].map(start_positions).fillna(gl_filtered["current_pos"])
        gl_filtered["range_peak"] = gl_filtered["name"].map(range_peaks).fillna(gl_filtered["current_pos"])
        gl_filtered["range_change"] = gl_filtered["start_pos"] - gl_filtered["current_pos"]
        
        # Format labels and styles
        gl_filtered["movement_label"] = gl_filtered.apply(
            lambda r: f"{int(r['start_pos'])} ➔ {int(r['current_pos'])}" if r['range_change'] != 0 else f"{int(r['current_pos'])} (No change in {selected_days}d)", axis=1
        )

        # Calculate context for tooltips
        peak_dates_map = {}
        for name in gl_filtered["name"].unique():
            art_peaks = top_history[top_history["artist"] == name] if not top_history.empty else pd.DataFrame()
            if not art_peaks.empty:
                dates = art_peaks["scrape_date"].dt.strftime("%d-%m-%Y").tolist()
                peak_dates_map[name] = ", ".join(dates)
            else:
                peak_dates_map[name] = "Never"
        
        gl_filtered["all_peak_dates"] = gl_filtered["name"].map(peak_dates_map)
        
        # Performance Chart - Simplified flow
        st.markdown("<br>", unsafe_allow_html=True)
        # Sort by peak rank for the bar chart
        gl_chart_df = gl_filtered.sort_values("range_peak", ascending=False)
        
        if not gl_chart_df.empty:
            # Score logic: smaller rank number = larger bar
            max_all_time_rank = gl_chart_df["range_peak"].max()
            
            fig_move = go.Figure()
            
            for idx, (_, row) in enumerate(gl_chart_df.iterrows()):
                unique_color = CHART_COLORS[idx % len(CHART_COLORS)]
                pos_score = max_all_time_rank + 1 - row["range_peak"]  # <-- Make sure this is here!
                fig_move.add_trace(go.Bar(
                    name=row["name"],
                    y=[row["name"]],
                    x=[pos_score],
                    orientation="h",
                    marker=dict(color=unique_color, line=dict(width=0)),
                    hovertemplate=(
                        f"<b>{row['name']}</b><br>"
                        f"Peak in {selected_days}d: {int(row['range_peak'])}<br>"
                        f"Starting: {int(row['start_pos'])}<br>"
                        f"Current: {int(row['current_pos'])}<br>"
                        f"Movement: {row['movement_label']}<extra></extra>"
                    ),
                    showlegend=False
                ))
                
                # Label at the end: Show transition Clearly (Pela #X ➔ Have #Y)
                trend_arrow = "↑" if row["range_change"] > 0 else "↓" if row["range_change"] < 0 else "•"
                label_text = f" <b>{int(row['start_pos'])} {trend_arrow} {int(row['current_pos'])}</b>"
                
                fig_move.add_annotation(
                    x=pos_score,
                    y=row["name"],
                    text=label_text,
                    showarrow=False,
                    xanchor="left",
                    font=dict(color="white", size=11),
                    xshift=8
                )

            fig_move.update_layout(
                title=f"🏆 Artist Performance Analysis ({selected_days}D)",
                xaxis=dict(
                    title="Rank Performance Score (Based on Peak in Window)",
                    showgrid=False,
                    zeroline=False,
                    showticklabels=False
                ),
                yaxis=dict(
                    title="",
                    gridcolor="rgba(255,255,255,0.05)"
                ),
                height=min(420, max(320, len(gl_chart_df) * 28)),
                margin=dict(l=180, r=150, t=60, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                bargap=0.35
            )
            render_plotly_html(fig_move)
        
    
    # Detailed Data Table removed as requested




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
        health_color = "#34D399"
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
            colors = ["#34D399" if val >= 95 else "#FFB547" if val >= 80 else "#FF4FCB" for val in rate_df["success_pct"]]
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
            render_plotly_html(fig_rate)

        with c2:
            recent = runs[["finished_at", "source", "rows_upserted", "status"]]
            recent["finished_label"] = recent["finished_at"].dt.strftime("%Y-%m-%d %H:%M").fillna("in progress")
            html = ['<div class="dashboard-card"><div class="section-title">🔔 Recent Scrape Runs</div><div class="run-log">']
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
            render_plotly_html(fig_rows)
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
                render_plotly_html(fig_duration)
        
        with col_right:
            st.markdown("#### 📋 Status Breakdown")
            status_counts = runs["status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            fig_status = px.pie(
                status_counts,
                names="Status",
                values="Count",
                title="Overall Status Distribution",
                color_discrete_sequence=["#34D399", "#FFB547", "#FF4FCB"]
            )
            style_figure(fig_status, 350)
            render_plotly_html(fig_status)


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
                                background: linear-gradient(135deg, #fb7185 0%, #f43f5e 60%, #be123c 100%);
                                box-shadow: 0 14px 36px rgba(251, 113, 133, 0.35);
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
                                background: linear-gradient(135deg, #fb7185 0%, #f43f5e 60%, #be123c 100%);
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
                                border: 1px solid #fb7185;
                                color: #e8f0ff;
                                background: rgba(251,113,133,0.15);
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
        


apply_theme(dark_mode=st.session_state.get("dark_mode", False))

_loader_slot = st.empty()
is_dark = st.session_state.get("dark_mode", False)
l_bg = "#0d1117" if is_dark else "#FFFFFF"
l_title = "#e2e8f0" if is_dark else "#1A1A1A"
l_sub = "#5a7ab5" if is_dark else "#8A8FA3"
l_ring = "rgba(251,113,133,0.15)" if is_dark else "rgba(251,113,133,0.1)"

_loader_slot.markdown(f"""
<style>
@keyframes a360-spin {{
    0%   {{ transform: rotate(0deg); }}
    100% {{ transform: rotate(360deg); }}
}}
@keyframes a360-pulse {{
    0%, 100% {{ opacity: .4; transform: scale(1); }}
    50%        {{ opacity: 1;  transform: scale(1.08); }}
}}
#a360-loader {{
    position: fixed;
    inset: 0;
    background: {l_bg};
    z-index: 99999;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
#a360-loader .a360-ring {{
    width: 64px;
    height: 64px;
    border: 3px solid {l_ring};
    border-top-color: #fb7185;
    border-radius: 50%;
    animation: a360-spin 0.9s linear infinite;
}}
#a360-loader .a360-title {{
    font-size: 1.25rem;
    font-weight: 600;
    color: {l_title};
    letter-spacing: 0.02em;
    animation: a360-pulse 2s ease-in-out infinite;
}}
#a360-loader .a360-sub {{
    font-size: 0.82rem;
    color: {l_sub};
    letter-spacing: 0.04em;
    text-transform: uppercase;
}}
</style>
<div id="a360-loader">
  <div class="a360-ring"></div>
  <div class="a360-title">Artist 360&deg; Intelligence</div>
</div>
""", unsafe_allow_html=True)

try:
    data = load_dashboard_data()
    # Asynchronous prefetch for dashboard data on first load to ensure near-instant load on tab switch without blocking main load
    if "dashboards_prefetched" not in st.session_state:
        st.session_state.dashboards_prefetched = True
        import threading
        from streamlit.runtime.scriptrunner import add_script_run_ctx
        from src.ai.label_analysis_dashboard import prefetch_label_data
        from src.ai.acquisition_dashboard import prefetch_acquisition_data
        
        def run_prefetch():
            try:
                prefetch_debut_data()
                prefetch_artists_overview_data()
                prefetch_label_data()
                prefetch_acquisition_data()
            except Exception as e:
                pass

        prefetch_thread = threading.Thread(target=run_prefetch)
        add_script_run_ctx(prefetch_thread)
        prefetch_thread.start()
except Exception as exc:  # pragma: no cover
    _loader_slot.empty()
    st.error(f"❌ Failed to load dashboard data: {exc}")
    st.stop()

_loader_slot.empty()

leaderboard = data["leaderboard"]
runs = data["runs"]
history = data["history"]
top_history = data.get("top_history", pd.DataFrame())
def clear_active_profile():
    """Callback to reset the active popup state when global filters change."""
    st.session_state.active_artist_profile = None
    if "global_selected_artist" in st.session_state:
        del st.session_state.global_selected_artist
    if "debut_artist_select" in st.session_state:
        del st.session_state.debut_artist_select

last_run_label = "n/a"
if not runs.empty and runs["finished_at"].notna().any():
    last_run_label = runs["finished_at"].dropna().max().strftime("%Y-%m-%d %H:%M")


def show_leaderboard_page() -> None:
    # Check if an artist profile was requested via URL query parameters
    # This allows the dialog to open on the very first run after a click.
    target_name = st.query_params.get("artist_name") or st.session_state.active_artist_profile
    
    if target_name:
        artist_match = leaderboard[leaderboard["name"] == target_name]
        if not artist_match.empty:
            show_artist_details_dialog(artist_match.iloc[0])
            # Clear the trigger state so the dialog doesn't re-open on next interaction
            st.session_state.active_artist_profile = None
            if "artist_name" in st.query_params:
                st.query_params.clear()

    # Use filtered to reflect both country and artist filters in leaderboard and charts
    # Create update label showing only the scraper execution time
    last_update_label = f"Last Update: {last_run_label}"

    render_leaderboard(filtered, runs, max_rows=100, date_label=last_update_label)


def show_compare_page() -> None:
    st.markdown(
        """
        <style>
        .cmp-note {
            margin-top: -20px;
            margin-bottom: 0.9rem;
            padding: 0.75rem 0.9rem;
            border-radius: 12px;
            border: 1px solid rgba(251,113,133,.35);
            background: rgba(251,113,133,.12);
            color: var(--text);
            font-size: 0.9rem;
            font-weight: 600;
        }
        .cmp-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.85rem;
            margin: 0.75rem 0 1rem;
        }
        .cmp-card {
            background: linear-gradient(180deg, var(--surface2) 0%, var(--surface) 100%);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            box-shadow: 0 12px 26px rgba(0,0,0,.08);
        }
        .cmp-artist {
            color: var(--text);
            font-size: 1rem;
            font-weight: 800;
            margin-bottom: 0.6rem;
            letter-spacing: .01em;
        }
        .cmp-metric {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 0.5rem;
            padding: 0.3rem 0;
            border-bottom: 1px solid var(--border);
            font-size: 0.84rem;
        }
        .cmp-metric:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }
        .cmp-metric-label {
            color: var(--text2);
            font-weight: 600;
        }
        .cmp-metric-value {
            color: var(--text);
            font-weight: 800;
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        .cmp-title {
            margin: 0.5rem 0 0.75rem;
            font-size: 1.02rem;
            font-weight: 800;
            color: var(--text);
        }
        .cmp-table-wrap {
            margin-top: 0.65rem;
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow-x: auto;
            background: var(--surface2);
        }
        .cmp-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
        }
        .cmp-table th {
            text-align: left;
            padding: 0.66rem 0.74rem;
            color: var(--text2);
            letter-spacing: .06em;
            text-transform: uppercase;
            font-size: .7rem;
            border-bottom: 1px solid var(--border);
            background: var(--surface);
        }
        .cmp-table td {
            padding: 0.6rem 0.74rem;
            border-bottom: 1px solid var(--border);
            color: var(--text);
            vertical-align: top;
        }
        .cmp-table tr:last-child td {
            border-bottom: none;
        }
        .cmp-warning {
            margin-top: -1.8rem;
            border: 1px solid rgba(245,166,35,.45);
            background: rgba(245,166,35,.14);
            color: var(--text);
            border-radius: 12px;
            padding: 0.72rem 0.88rem;
            font-size: 0.88rem;
            font-weight: 600;
        }
        </style>
        <div class='cmp-note'>Select 2-5 artists to compare their leaderboard metrics.
        <div >Side-by-side performance benchmarking for head-to-head artist analysis. Compare multiple acts across primary metrics including audience scale, catalog depth, and global market penetration.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    available_artists = leaderboard["name"].dropna().tolist()[:20]
    selected_for_comparison = custom_multiselect(
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

        metric_cards: list[str] = []
        for artist_name in selected_for_comparison:
            artist_slice = comparison_data[comparison_data["name"] == artist_name]
            if artist_slice.empty:
                continue
            artist_data = artist_slice.iloc[0]

            rank_value = int(artist_data["rank"]) if pd.notna(artist_data.get("rank")) else "-"
            monthly_value = fmt_short(artist_data.get("monthly_listeners", 0))
            songs_count = artist_data.get("songs_count", 0)
            countries_count = artist_data.get("countries_count", 0)

            metric_cards.append(
                "<div class='cmp-card'>"
                f"<div class='cmp-artist'>{escape(str(artist_name))}</div>"
                "<div class='cmp-metric'><span class='cmp-metric-label'>Rank</span>"
                f"<span class='cmp-metric-value'>{rank_value}</span></div>"
                "<div class='cmp-metric'><span class='cmp-metric-label'>Monthly Listeners</span>"
                f"<span class='cmp-metric-value'>{escape(monthly_value)}</span></div>"
                "<div class='cmp-metric'><span class='cmp-metric-label'>Tracks</span>"
                f"<span class='cmp-metric-value'>{int(songs_count) if pd.notna(songs_count) else 0}</span></div>"
                "<div class='cmp-metric'><span class='cmp-metric-label'>LATAM Countries</span>"
                f"<span class='cmp-metric-value'>{int(countries_count) if pd.notna(countries_count) else 0}</span></div>"
                "</div>"
            )

        st.markdown(f"<div class='cmp-grid'>{''.join(metric_cards)}</div>", unsafe_allow_html=True)

        # ── Head-to-head HTML comparison bars ─────────────────────────────
        VIZ_PALETTE = ["#60a5fa", "#34d399", "#c4b5fd", "#fcd34d", "#fb7185", "#f9a8d4"]
        cmp_metrics = [
            ("🎧 Monthly Listeners", "monthly_listeners"),
            ("🎵 Tracks",             "songs_count"),
            ("💿 Albums",            "albums_count"),
            ("🌎 LATAM Countries",   "countries_count"),
            ("⭐ Total Points",      "total_points"),
        ]

        hth_rows = ""
        for label, col in cmp_metrics:
            vals = []
            for aname in selected_for_comparison:
                sl = comparison_data[comparison_data["name"] == aname]
                v = float(sl.iloc[0][col]) if not sl.empty and pd.notna(sl.iloc[0].get(col)) else 0.0
                vals.append(v)
            max_val = max(vals) if any(v > 0 for v in vals) else 1
            bars_html = ""
            for idx_a, (aname, v) in enumerate(zip(selected_for_comparison, vals)):
                pct = (v / max_val * 100) if max_val > 0 else 0
                color = VIZ_PALETTE[idx_a % len(VIZ_PALETTE)]
                display_v = fmt_short(v) if col not in ("songs_count", "albums_count", "countries_count") else str(int(v))
                is_best = v == max_val and max_val > 0
                crown = " 👑" if is_best else ""
                bars_html += (
                    f"<div style='margin-bottom:6px;'>"
                    f"<div style='display:flex;justify-content:space-between;font-size:.78rem;margin-bottom:3px;'>"
                    f"<span style='color:var(--text);font-weight:600;'>{escape(str(aname))}{crown}</span>"
                    f"<span style='color:{color};font-weight:800;font-variant-numeric:tabular-nums;'>{display_v}</span>"
                    f"</div>"
                    f"<div style='height:10px;border-radius:999px;background:var(--surface3);overflow:hidden;'>"
                    f"<div style='height:100%;width:{pct:.1f}%;border-radius:999px;"
                    f"background:linear-gradient(90deg,{color}cc,{color});transition:width 1s ease;'></div>"
                    f"</div></div>"
                )
            hth_rows += (
                f"<div style='background:var(--surface2);border:1px solid var(--border);"
                f"border-radius:12px;padding:0.75rem 0.9rem;'>"
                f"<div style='font-size:.8rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;"
                f"color:var(--text2);margin-bottom:0.55rem;'>{label}</div>"
                f"{bars_html}</div>"
            )

        st.markdown(
            f"""
            <div style='margin:0.5rem 0 1.25rem;'>
                <div style='font-size:1.05rem;font-weight:800;color:var(--text);
                    letter-spacing:-.01em;margin-bottom:0.75rem;display:flex;
                    align-items:center;gap:0.5rem;'>
                    ⚡ Head-to-Head Breakdown
                    <span style='font-size:.72rem;font-weight:700;letter-spacing:.1em;
                        text-transform:uppercase;color:var(--text2);background:rgba(148,163,184,.1);
                        border:1px solid rgba(148,163,184,.2);padding:3px 10px;border-radius:999px;'>
                        All metrics
                    </span>
                </div>
                <div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:0.75rem;'>
                    {hth_rows}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── 3 Plotly charts: Listeners · Countries · Points ─────────────
        st.markdown(
            "<div style='font-size:1.05rem;font-weight:800;color:var(--text);margin:0.25rem 0 0.85rem;"
            "letter-spacing:-.01em;'>📊 Visual Comparison</div>",
            unsafe_allow_html=True,
        )
        comp_col1, comp_col2, comp_col3 = st.columns(3, gap="medium")

        with comp_col1:
            fig_comp_listeners = go.Figure()
            is_dark = st.session_state.get("dark_mode", False)
            text_color = "#fff" if is_dark else "#1A1A1A"
            for idx_a, aname in enumerate(selected_for_comparison):
                sl = comparison_data[comparison_data["name"] == aname]
                if sl.empty:
                    continue
                v = float(sl.iloc[0].get("monthly_listeners") or 0)
                color = VIZ_PALETTE[idx_a % len(VIZ_PALETTE)]
                fig_comp_listeners.add_trace(go.Bar(
                    name=aname,
                    x=[aname],
                    y=[v],
                    marker=dict(
                        color=color,
                        opacity=0.92,
                        line=dict(width=0),
                    ),
                    text=[fmt_short(v)],
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(color=text_color, size=12, family="Inter, ui-sans-serif"),
                    hovertemplate=f"<b>{escape(str(aname))}</b><br>Monthly listeners: %{{y:,.0f}}<extra></extra>",
                ))
            fig_comp_listeners.update_layout(
                title=dict(text="🎧 Monthly Listeners", font=dict(size=15, color=text_color), x=0.03),
                showlegend=False,
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=8, r=8, t=56, b=8),
                bargap=0.35,
            )
            fig_comp_listeners.update_yaxes(tickformat="~s")
            style_figure(fig_comp_listeners, 310, dark_mode=is_dark)
            render_plotly_html(fig_comp_listeners)

        with comp_col2:
            fig_comp_reach = go.Figure()
            for idx_a, aname in enumerate(selected_for_comparison):
                sl = comparison_data[comparison_data["name"] == aname]
                if sl.empty:
                    continue
                v = int(sl.iloc[0].get("countries_count") or 0)
                color = VIZ_PALETTE[idx_a % len(VIZ_PALETTE)]
                fig_comp_reach.add_trace(go.Bar(
                    name=aname,
                    x=[aname],
                    y=[v],
                    marker=dict(color=color, opacity=0.92, line=dict(width=0)),
                    text=[str(v)],
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(color=text_color, size=12),
                    hovertemplate=f"<b>{escape(str(aname))}</b><br>LATAM countries: %{{y}}<extra></extra>",
                ))
            fig_comp_reach.update_layout(
                title=dict(text="🌎 LATAM Country Reach", font=dict(size=15, color=text_color), x=0.03),
                showlegend=False,
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=8, r=8, t=56, b=8),
                bargap=0.35,
            )
            style_figure(fig_comp_reach, 310, dark_mode=is_dark)
            render_plotly_html(fig_comp_reach)

        with comp_col3:
            fig_comp_points = go.Figure()
            for idx_a, aname in enumerate(selected_for_comparison):
                sl = comparison_data[comparison_data["name"] == aname]
                if sl.empty:
                    continue
                v = float(sl.iloc[0].get("total_points") or 0)
                color = VIZ_PALETTE[idx_a % len(VIZ_PALETTE)]
                fig_comp_points.add_trace(go.Bar(
                    name=aname,
                    x=[aname],
                    y=[v],
                    marker=dict(color=color, opacity=0.92, line=dict(width=0)),
                    text=[fmt_short(v)],
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(color=text_color, size=12),
                    hovertemplate=f"<b>{escape(str(aname))}</b><br>Total points: %{{y:,.0f}}<extra></extra>",
                ))
            fig_comp_points.update_layout(
                title=dict(text="⭐ Total Points", font=dict(size=15, color=text_color), x=0.03),
                showlegend=False,
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=8, r=8, t=56, b=8),
                bargap=0.35,
            )
            fig_comp_points.update_yaxes(tickformat="~s")
            style_figure(fig_comp_points, 310, dark_mode=is_dark)
            render_plotly_html(fig_comp_points)

        with st.expander("📋 View Detailed Comparison Table", expanded=True):
            table_rows: list[str] = []
            for _, row in comparison_data.iterrows():
                rank_val = int(row["rank"]) if pd.notna(row.get("rank")) else "-"
                monthly_val = fmt_short(row.get("monthly_listeners"))
                songs_val = int(row.get("songs_count")) if pd.notna(row.get("songs_count")) else 0
                albums_val = int(row.get("albums_count")) if pd.notna(row.get("albums_count")) else 0
                countries_val = int(row.get("countries_count")) if pd.notna(row.get("countries_count")) else 0
                top_song_val = str(row.get("top_song") or "-")
                table_rows.append(
                    "<tr>"
                    f"<td>{escape(str(row.get('name') or '-'))}</td>"
                    f"<td>{rank_val}</td>"
                    f"<td>{escape(monthly_val)}</td>"
                    f"<td>{songs_val}</td>"
                    f"<td>{albums_val}</td>"
                    f"<td>{countries_val}</td>"
                    f"<td>{escape(top_song_val)}</td>"
                    "</tr>"
                )

            st.markdown(
                "<div class='cmp-table-wrap'>"
                "<table class='cmp-table'>"
                "<thead><tr>"
                "<th>Artist</th><th>Rank</th><th>Monthly Listeners</th>"
                "<th>Tracks</th><th>Albums</th><th>LATAM Countries</th><th>Top Track</th>"
                "</tr></thead>"
                f"<tbody>{''.join(table_rows)}</tbody>"
                "</table>"
                "</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div class='cmp-warning'>Please select at least 2 artists to compare.</div>",
            unsafe_allow_html=True,
        )


def show_chart_tracker_page() -> None:
    # Use global_filtered to show top artists + selected artist spotlight
    render_chart_tracker(history, global_filtered)


def show_stream_trends_page() -> None:
    render_stream_trends(filtered, leaderboard, top_history, history)


def show_debut_artist_page() -> None:
    st.markdown("""
        <style>
        /* Forcefully remove the massive empty space above the Artist Spotlight dashboard */
        .stMainBlockContainer, .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 0rem !important;
        }
        /* Tighten vertical gaps between elements on this page */
        div[data-testid="stVerticalBlock"] {
            gap: 0.5rem !important;
        }
        </style>
    """, unsafe_allow_html=True)
    # Use global_filtered to allow changing artists in the dropdown
    render_debut_artist_chart(global_filtered)


def show_artists_overview_page() -> None:
    st.markdown(
        """
        <style>
        .stMainBlockContainer, .block-container {
            padding-top: 0.1rem !important;
        }
        /* Make overview iframe height responsive to responsive grid wrapping inside the iframe */
                    iframe[title="streamlit.components.v1.html"] {            transition: height 0.2s ease-in-out !important;
        }
        @media (max-width: 1200px) {
                        iframe[title="streamlit.components.v1.html"] {                height: 1100px !important;
            }
        }
        @media (max-width: 1050px) {
                        iframe[title="streamlit.components.v1.html"] {                height: 1800px !important;
            }
        }
        @media (max-width: 768px) {
                        iframe[title="streamlit.components.v1.html"] {                height: 2200px !important;
            }
        }
        @media (max-width: 640px) {
                        iframe[title="streamlit.components.v1.html"] {                height: 2800px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # Pass sidebar-filtered artist names (Latin America, Sony Music, etc.) 
    # for the Artists Overview dashboard which loads its own data from DB
    if len(global_filtered) < len(leaderboard):
        sidebar_filtered_artists = global_filtered["name"].dropna().unique().tolist()
    else:
        sidebar_filtered_artists = None
    render_artists_overview(last_run_label, filtered_artists=sidebar_filtered_artists)


def show_redesign_dashboard_page() -> None:
    st.markdown(
        """
        <style>
        .stMainBlockContainer, .block-container {
            padding-top: 0.1rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    render_redesign_dashboard(filtered, history, last_run_label)


def show_ai_analyst_page() -> None:
    # Previously, this page rendered the custom AI chatbot component via render_custom_chatbot().
    # render_custom_chatbot() provides an interactive chat interface that builds query plans and
    # displays charts/tables based on natural language questions. Below we embed the external Vercel
    # chatbot webview directly, preserving the same UI slot while showcasing the hosted version.
    st.markdown(
        """
        <style>
        /* Disable scrolling on the main Streamlit app for this specific page */
        .stApp, .main {
            overflow: hidden !important;
        }
        .stMainBlockContainer {
            padding-top: 0px !important;
            padding-bottom: 0px !important;
            max-width: 100% !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    is_dark = st.session_state.get("dark_mode", False)
    bot_url = "https://artist360-chatbot.vercel.app/" if is_dark else "https://artist360-chatbot.vercel.app/white"
    st_components.iframe(bot_url, height=1000, scrolling=False)


def show_pulse_report_page() -> None:
    """Wrapper function for Pulse Report page"""
    render_pulse_report()


def show_label_analysis_page() -> None:
    """Wrapper function for Label Analysis page"""
    st.markdown("""
        <style>
        /* Forcefully remove the massive empty space above the Label Analysis iframe */
        .stMainBlockContainer {
            padding-top: 0rem !important;
        }
        </style>
    """, unsafe_allow_html=True)
    from src.ai.label_analysis_dashboard import render_label_analysis
    render_label_analysis()


def show_debut_report_page() -> None:
    """Wrapper function for Debut Report page"""
    _debut_loader = st.empty()
    _debut_loader.markdown("""
<style>
@keyframes _dr_spin {
    0%   { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
@keyframes _dr_pulse {
    0%, 100% { opacity: .4; transform: scale(1); }
    50%        { opacity: 1;  transform: scale(1.08); }
}
#dr-loader {
    position: fixed;
    inset: 0;
    background: #0d1117;
    z-index: 99999;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
#dr-loader .dr-ring {
    width: 64px;
    height: 64px;
    border: 3px solid rgba(108,92,231,0.15);
    border-top-color: #6C5CE7;
    border-radius: 50%;
    animation: _dr_spin 0.9s linear infinite;
}
#dr-loader .dr-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: #e2e8f0;
    letter-spacing: 0.02em;
    animation: _dr_pulse 2s ease-in-out infinite;
}
#dr-loader .dr-sub {
    font-size: 0.82rem;
    color: #5a7ab5;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
</style>
<div id="dr-loader">
  <div class="dr-ring"></div>
  <div class="dr-title">Debuts Report</div>
</div>
""", unsafe_allow_html=True)
    render_debut_tab(filtered)
    _debut_loader.empty()


def show_movement_page() -> None:
    """Wrapper function for Movement page"""
    st.markdown(
        """
        <style>
        div[data-testid="stTabs"] div[role="tablist"] {
            gap: 10px;
        }
        div[data-testid="stTabs"] button[role="tab"] {
            border: 1px solid var(--border) !important;
            border-radius: 10px !important;
            background: var(--surface) !important;
            color: var(--text2) !important;
            font-weight: 700 !important;
            min-height: 44px !important;
            transition: background .15s ease, border-color .15s ease, color .15s ease, box-shadow .15s ease;
        }
        div[data-testid="stTabs"] button[role="tab"]:hover {
            border-color: rgba(251,113,133,.5) !important;
            color: var(--text) !important;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background: rgba(251,113,133,.14) !important;
            border-color: #fb7185 !important;
            color: var(--text) !important;
            box-shadow: inset 0 0 0 1px rgba(251,113,133,.18), 0 6px 16px rgba(251,113,133,.10) !important;
        }
        div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    tab1, tab2, tab3 = st.tabs(["🎤 Artist Movement", "🎵 Track Movement", "💿 Album Movement"])
    
    labels_to_filter = selected_sony_labels if sony_music_only else None
    
    with tab1:
        render_chart_tracker(history, global_filtered)
    with tab2:
        render_track_movement(labels_to_filter)
    with tab3:
        render_album_movement(labels_to_filter)


def show_acquisition_page() -> None:
    """Wrapper function for Acquisition Recommendation page"""
    st.markdown(
        """
        <style>
        div[data-testid="stTabs"] div[role="tablist"] {
            gap: 10px;
        }
        div[data-testid="stTabs"] button[role="tab"] {
            border: 1px solid var(--border) !important;
            border-radius: 10px !important;
            background: var(--surface) !important;
            color: var(--text2) !important;
            font-weight: 700 !important;
            min-height: 44px !important;
            transition: background .15s ease, border-color .15s ease, color .15s ease, box-shadow .15s ease, transform .15s ease;
        }
        div[data-testid="stTabs"] button[role="tab"]:hover {
            border-color: #e31b23 !important;
            color: var(--text) !important;
            transform: translateY(-1px);
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background: linear-gradient(135deg, rgba(255,255,255,.98), rgba(255,232,234,.96)) !important;
            border-color: #e31b23 !important;
            color: #8f0f1c !important;
            box-shadow: inset 0 0 0 1px rgba(227,27,35,.18), 0 6px 16px rgba(227,27,35,.12) !important;
        }
        div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    tab1, tab2, tab3 = st.tabs(["🎵 Track Acquisition", "💿 Album Acquisition", "🎤 Artist Acquisition"])
    
    labels_to_filter = selected_sony_labels if sony_music_only else None
    
    with tab1:
        render_track_acquisition(labels_to_filter)
    with tab2:
        render_album_acquisition(labels_to_filter)
    with tab3:
        render_acquisition(labels_to_filter)


NAV_ITEMS = [
    {
        "page": show_artists_overview_page,
        "title": "Overview",
        "icon": "dashboard",
        "path": "artists-overview",
        "default": True,
    },
    {
        "page": show_redesign_dashboard_page,
        "title": "LATAM Signals",
        "icon": "sparkles",
        "path": "latam-signals",
    },
    {
        "page": show_movement_page,
        "title": "Movement Trends",
        "icon": "trend",
        "path": "movement-trends",
    },
    {
        "page": show_acquisition_page,
        "title": "Acquisition Analysis",
        "icon": "handshake",
        "path": "acquisition-Analysis",
    },
    {
        "page": show_label_analysis_page,
        "title": "Label Analysis",
        "icon": "analytics",
        "path": "label-analysis",
    },
    {
        "page": show_debut_artist_page,
        "title": "Artist Spotlight",
        "icon": "person",
        "path": "artist-spotlight",
    },
    {
        "page": show_compare_page,
        "title": "Compare",
        "icon": "compare",
        "path": "compare",
    },
    {
        "page": show_ai_analyst_page,
        "title": "AI Data Analyst",
        "icon": "bot",
        "path": "ai-data-analyst",
    },
]

app_pages = [
    st.Page(
        item["page"],
        title=item["title"],
        icon=":material/dashboard:",
        url_path=item["path"],
        default=item.get("default", False),
    )
    for item in NAV_ITEMS
]


def _sidebar_icon_svg(icon: str) -> str:
    icons = {
        "dashboard": "<rect x='3' y='3' width='7' height='7' rx='1.5'/><rect x='14' y='3' width='7' height='7' rx='1.5'/><rect x='3' y='14' width='7' height='7' rx='1.5'/><rect x='14' y='14' width='7' height='7' rx='1.5'/>",
        "sparkles": "<path d='M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z'/><path d='M5 15l.9 2.6L8.5 18l-2.6.9L5 21l-.9-2.1L2 18l2.1-.4L5 15z'/><path d='M18 14l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2z'/>",
        "trend": "<path d='M3 17l6-6 4 4 8-8'/><path d='M15 7h6v6'/>",
        "handshake": "<path d='M8.5 12.5l2-2a2.1 2.1 0 0 1 3 0l.8.8'/><path d='M14 11l2.5 2.5a2.1 2.1 0 0 1 0 3l-2 2a2.1 2.1 0 0 1-3 0L8 15'/><path d='M7 13l-2-2 4-4 2 2'/><path d='M17 13l2-2-4-4-2 2'/><path d='M9 16l2 2'/><path d='M11 14l2 2'/>",
        "analytics": "<rect x='4' y='4' width='16' height='16' rx='2'/><path d='M8 16v-4'/><path d='M12 16V8'/><path d='M16 16v-6'/>",
        "person": "<circle cx='12' cy='8' r='3'/><path d='M5 20a7 7 0 0 1 14 0'/>",
        "compare": "<path d='M7 7h13'/><path d='M17 4l3 3-3 3'/><path d='M17 17H4'/><path d='M7 14l-3 3 3 3'/>",
        "bot": "<rect x='5' y='8' width='14' height='11' rx='2'/><path d='M12 8V4'/><path d='M9 13h.01'/><path d='M15 13h.01'/><path d='M9 17h6'/>",
    }
    return f"<svg viewBox='0 0 24 24' aria-hidden='true'>{icons.get(icon, icons['dashboard'])}</svg>"


def _render_custom_sidebar_nav() -> None:
    links = []
    for item in NAV_ITEMS:
        label = escape(item["title"])
        path = "/" + item["path"].strip("/")
        links.append(
            "<a class='app-side-link' "
            f"href='{escape(path)}' target='_self' data-path='{escape(path)}' data-tooltip='{label}'>"
            f"<span class='app-side-icon'>{_sidebar_icon_svg(item['icon'])}</span>"
            f"<span class='app-side-label'>{label}</span>"
            "</a>"
        )
    st.markdown(f"<nav class='app-side-nav'>{''.join(links)}</nav>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown(
        """
        <div class='brand-row'>
            <div class='brand-logo'></div>
            <div>
                <div class='sidebar-logo'>Artist 360° Intelligence</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Keep Streamlit routing, but render our own sidebar nav for exact layout control.
    current_page = st.navigation(app_pages, position="hidden")
    _render_custom_sidebar_nav()

    st.markdown(
        "<div class='appearance-title' style='margin:.25rem 0 .35rem; color: var(--text2); font-size:.78rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase;'>Appearance</div>",
        unsafe_allow_html=True,
    )
    is_dark = st.session_state.get("dark_mode", False)
    toggle_label = "☀️ Light Mode" if is_dark else "🌙 Dark Mode"
    if st.button(
        toggle_label,
        key="theme_toggle_btn",
        use_container_width=True,
    ):
        st.session_state.dark_mode = not is_dark
        st.query_params["theme"] = "dark" if st.session_state.dark_mode else "light"
        st.rerun()
    
    # Collapsible advanced settings
    with st.expander("🔍 Search & Filter", expanded=True):
        latam_only = st.toggle("🌎 Latin America", value=False, on_change=clear_active_profile, key="sidebar_latam_only_filter")
        
        selected_countries = []
        if latam_only:
            latam_country_mapping = {
                "Argentina": "Argentina",
                "Bolivia": "Bolivia",
                "Brazil": "Brazil",
                "Chile": "Chile",
                "Colombia": "Colombia",
                "Costa Rica": "Costa Rica",
                "Dominican Republic": "Dominican Republic",
                "Ecuador": "Ecuador",
                "El Salvador": "El Salvador",
                "Guatemala": "Guatemala",
                "Honduras": "Honduras",
                "Mexico": "Mexico",
                "Nicaragua": "Nicaragua",
                "Panama": "Panama",
                "Peru": "Peru",
                "Paraguay": "Paraguay",
                "Uruguay": "Uruguay",
                "Venezuela": "Venezuela"
            }
            options = list(latam_country_mapping.keys())
            default_selection = options
            
            selected_countries = custom_multiselect(
                "📍 Countries",
                options=options,
                default=default_selection,
                format_func=lambda x: latam_country_mapping.get(x, x),
                on_change=clear_active_profile,
                key="sidebar_countries_filter"
            )

        sony_music_only = st.toggle("🎵 Sony Music", value=False, on_change=clear_active_profile, key="sidebar_sony_music_filter")
        
        selected_sony_labels = []
        if sony_music_only:
            selected_sony_labels = [
                "Sony Music",
                "Sony Music Argentina",
                "Sony Music Associated Records",
                "Sony Music Australia",
                "Sony Music Brasil",
                "Sony Music Brazil",
                "Sony Music Colombia",
                "Sony Music Entertainment Australia",
                "Sony Music Entertainment Indonesia",
                "Sony Music Entertainment Japan",
                "Sony Music India",
                "Sony Music Japan",
                "Sony Music Labels",
                "Sony Music Latin",
                "Sony Music Nashville",
                "Sony Music Records",
                "Sony Music Spain",
                "SonyMusic Nashville",
                "Stuffed Monkey / Sony Music",
                "Stuffed Monkey/Sony Music",
                "Two Sides/Sony Music",
                "Columbia/Sony Music",
                "Grupo Frontera / Sony Music Latin",
                "Grupo Frontera LLC / Sony Music Latin",
                "Grupo Frontera LLC/Sony Music Latin",
                "Grupo Frontera Records / Sony Music Latin",
                "Grupo Frontera Records/Sony Music Latin",
                "Grupo Frontera/Sony Music Latin",
                "Mango Music / Sony Music Latin",
                "Palm Tree Records/Sony Music",
                "Premium Latin Music/Sony Music Latin",
                "Rancho Humilde / Sony Music Latin",
                "Rancho Humilde/Sony Music Latin",
                "River House Artists/Sony Music Nashville",
                "River House/Sony Music Nashville",
                "SAW Entertainment / Sony Music Nashville",
                "SAW Entertainment/Sony Music Nashville",
                "Street Mob Records/Sony Music Latin",
                "White Star/Sony Music Latin",
                "White World/Sony Music Latin"
            ]

    

    # Apply global filters (Latam, Countries, Labels)
    global_filtered = leaderboard.copy()
    
    if "label" in global_filtered.columns:
        global_filtered["canonical_label"] = global_filtered["label"].apply(
            lambda x: LABEL_NORM.get(str(x).strip(), str(x).strip()) if pd.notna(x) else ""
        )
    
    if latam_only:
        global_filtered = global_filtered[global_filtered["top_country"].isin(selected_countries)]
    if sony_music_only and "label" in global_filtered.columns:
        global_filtered = global_filtered[global_filtered["label"].isin(selected_sony_labels)]
    
    # Apply global sorting for Leaderboard list
    filtered = global_filtered.copy()
    filtered = filtered.sort_values("rank")
    
    
    # Status indicator
    status_color = "status-good" if len(runs) > 0 else "muted"
    st.markdown(f"<span class='{status_color}'>● Pipeline: {'Healthy' if len(runs) > 0 else 'Unknown'}</span>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Last run: {last_run_label}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Updated: {pd.Timestamp.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
    

current_page.run()
if current_page.url_path != "ai-data-analyst":
    render_footer()

# Auto-refresh functionality
if st.session_state.auto_refresh:
    import time
    time.sleep(30)
    st.rerun()
