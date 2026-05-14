from __future__ import annotations

from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as st_components

from src.ai.custom_chatbot import render_custom_chatbot
from src.database.connection import get_connection
from src.scrapers.artist_details_scraper import LATIN_AMERICAN_COUNTRIES
from src.utils.image_utils import get_artist_image_url, get_fallback_avatar_url
from skeleton import render_dashboard_skeleton
import requests


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
    "Artist Spotlight": (
        "Artist Spotlight",
        "View and analyze individual artist details and chart performance",
    ),
    "Chart Tracker": (
        "Chart Tracker",
        "Historical rank trajectories for top artists, revealing trends and momentum",
    ),
    "Stream Trends": (
        "Stream Trends",
        "Insights into streaming performance, growth patterns, and listener demographics",
    ),
    "AI Data Analyst": (
        "AI Data Analyst",
        "Ask natural-language questions and get content + charts (Powered by Table Details Bot)",
    ),
    "Artist Analysis": (
        "Artist Analysis",
        "Deep dive into artist performance, label distribution, market movement, and acquisition metrics",
    ),
    "Ops Monitor": (
        "Ops Monitor",
        "Operational dashboard showing recent data collection runs, their status, and performance metrics",
    ),
}

CHART_COLORS = ["#4f8ef7", "#22d3a0", "#f5a623", "#7c5cfc", "#e84545", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#a855f7"]
PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}
TRACKER_TOP_ARTISTS = 100
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
            padding-top: 3.5rem; /* Balanced gap for tooltips */
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
            background: #111827;
            border: 1px solid #1e2d47;
            border-radius: 12px;
            padding: 24px 20px 18px;
            min-height: 158px;
            width: 100%;
            position: relative; 
            overflow: visible; 
            height: 100%;
            display: flex;
            flex-direction: column;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            animation: fadeIn 0.6s ease-out;
        }
        .kpi-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 32px rgba(0,0,0,.4);
            border-color: rgba(79,142,247,.3);
            z-index: 1000; /* Ensure hovered card and its tooltip are on top */
        }
        .kpi-card::before {
            content:''; position:absolute; top:0; left:0; right:0; height:4px;
            border-radius: 12px 12px 0 0;
            background: linear-gradient(90deg, var(--accent), var(--accent2));
            transition: height 0.3s ease;
        }
        .kpi-card:hover::before {
            height: 5px;
        }
        .kpi-green::before { background: linear-gradient(90deg, var(--accent3), #16a34a); }
        .kpi-amber::before { background: linear-gradient(90deg, var(--warn), #f97316); }
        .kpi-red::before { background: linear-gradient(90deg, var(--danger), #be123c); }
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
            border-radius: 999px; overflow: hidden; margin-top: auto;
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
            width: 360px;
            background-color: rgba(13, 20, 38, 0.99);
            backdrop-filter: blur(12px);
            color: var(--text);
            text-align: left;
            border-radius: 12px;
            padding: 16px 20px;
            position: absolute;
            z-index: 99999;
            top: 100%;
            left: 50%;
            transform: translateX(-50%) translateY(0);
            opacity: 0;
            transition: opacity 0.3s ease, transform 0.3s ease;
            border: 1px solid rgba(79, 142, 247, 0.4);
            box-shadow: 0 25px 60px rgba(0,0,0,0.8);
            font-size: 0.86rem;
            line-height: 1.6;
            pointer-events: auto;
            max-height: 320px;
            overflow-y: auto;
            overscroll-behavior: contain;
            scrollbar-width: thin;
            scrollbar-color: var(--accent) transparent;
        }
        .tooltip:hover .tooltiptext {
            visibility: visible; 
            opacity: 1; 
            transform: translateX(-50%) translateY(10px);
        }
        .tooltip .tooltiptext::after {
            content: ""; position: absolute; bottom: 100%; left: 50%;
            margin-left: -10px; border-width: 10px; border-style: solid;
            border-color: transparent transparent rgba(13, 20, 38, 0.99) transparent;
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
            background: rgba(79, 142, 247, 0.4);
            border-radius: 10px;
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
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
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
            SELECT a.name, r.rank, r.total_points, r.num_countries, r.scraped_at
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
        """,
        "raw_benchmarks": """
            SELECT date as chart_date, rank, streams
            FROM spotify_daily
            WHERE country = 'global'
            AND date >= (SELECT MAX(date) FROM spotify_daily) - INTERVAL '30 days'
            ORDER BY date DESC, rank ASC
        """,
        "debuts": """
            WITH first_appearances AS (
                SELECT artist_id, MIN(scraped_at) as first_seen
                FROM itunes_artist_rankings
                GROUP BY artist_id
            )
            SELECT a.name, fa.first_seen as debut_at, r.rank as debut_rank, r.total_points as debut_points
            FROM first_appearances fa
            JOIN artists a ON a.id = fa.artist_id
            JOIN itunes_artist_rankings r ON r.artist_id = fa.artist_id AND r.scraped_at = fa.first_seen
            WHERE fa.first_seen >= NOW() - INTERVAL '30 days'
            ORDER BY fa.first_seen DESC
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
    if not frames["raw_benchmarks"].empty:
        frames["raw_benchmarks"]["chart_date"] = pd.to_datetime(frames["raw_benchmarks"]["chart_date"], errors="coerce")
    if not frames["debuts"].empty:
        frames["debuts"]["debut_at"] = pd.to_datetime(frames["debuts"]["debut_at"], errors="coerce")

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

    # Clean up page_title by removing redundant suffix
    if "page_title" in leaderboard.columns:
        suffix = " on Spotify, Apple Music and Other Streaming Services"
        leaderboard["page_title"] = leaderboard["page_title"].str.replace(suffix, "", case=False, regex=False)

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


@st.cache_data(ttl=3600)
def get_wikipedia_data(artist_name: str) -> dict | None:
    """Fetch artist summary and metadata from Wikipedia."""
    # 1. Search for the artist to get the exact title
    search_url = "https://en.wikipedia.org/w/api.php"
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": f"{artist_name} musician",  # Add 'musician' to narrow down
        "format": "json",
        "srlimit": 1
    }
    
    headers = {
        "User-Agent": "Artist360Intelligence/1.0 (https://artist360.example.com; contact@example.com)"
    }
    
    try:
        r = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        r.raise_for_status()
        search_results = r.json()
        
        if not search_results.get("query", {}).get("search"):
            # Try without 'musician' if no results
            search_params["srsearch"] = artist_name
            r = requests.get(search_url, params=search_params, headers=headers, timeout=10)
            search_results = r.json()
            if not search_results.get("query", {}).get("search"):
                return None
            
        title = search_results["query"]["search"][0]["title"]
        
        # 2. Get summary and metadata
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
        r = requests.get(summary_url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        # Silently fail or log, don't break the UI
        return None


@st.cache_data(ttl=600)
def get_artist_deep_analysis(artist_name: str) -> dict:
    """Fetch deep analysis for a specific artist from daily charts."""
    conn = get_connection()
    try:
        # 1. Tracks that reached Top 100
        # We search artist_title for the artist name
        query_tracks = """
            SELECT artist_title, MIN(rank) as peak_rank, MAX(streams) as peak_daily_streams, 
                   MAX(total_streams) as lifetime_streams, COUNT(DISTINCT date) as days_on_chart
            FROM spotify_daily
            WHERE artist_title ILIKE %s
            AND rank <= 100
            GROUP BY artist_title
            ORDER BY peak_rank ASC
        """
        
        # 2. Daily Trajectory
        query_trajectory = """
            SELECT date, SUM(streams) as total_daily_streams, MIN(rank) as best_rank_that_day
            FROM spotify_daily
            WHERE artist_title ILIKE %s
            GROUP BY date
            ORDER BY date ASC
        """
        
        # 3. Weekly Analysis
        query_weekly = """
            SELECT DATE_TRUNC('week', date) as week, SUM(streams) as weekly_streams,
                   COUNT(DISTINCT artist_title) as active_tracks
            FROM spotify_daily
            WHERE artist_title ILIKE %s
            GROUP BY week
            ORDER BY week DESC
        """
        
        search_pattern = f"%{artist_name}%"
        
        with conn.cursor() as cur:
            # Tracks
            cur.execute(query_tracks, (search_pattern,))
            tracks = [dict(row) for row in cur.fetchall()]
            
            # Trajectory
            cur.execute(query_trajectory, (search_pattern,))
            trajectory = [dict(row) for row in cur.fetchall()]
            
            # Weekly
            cur.execute(query_weekly, (search_pattern,))
            weekly = [dict(row) for row in cur.fetchall()]
            
        return {
            "top_100_tracks": pd.DataFrame(tracks),
            "trajectory": pd.DataFrame(trajectory),
            "weekly_summary": pd.DataFrame(weekly)
        }
    except Exception as e:
        return {
            "top_100_tracks": pd.DataFrame(),
            "trajectory": pd.DataFrame(),
            "weekly_summary": pd.DataFrame(),
            "error": str(e)
        }
    finally:
        conn.close()


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
        
    latam_artists = int(leaderboard["latam_signal"].sum()) if "latam_signal" in leaderboard else 0
    
    # Identify new entries
    new_mask = leaderboard["rank_change"].fillna("").eq("NEW")
    new_entries = int(new_mask.sum())
    
    # Details for tooltip
    new_entries_details = ""
    if new_entries > 0:
        new_df = leaderboard[new_mask].sort_values("rank")
        top_new_rank = int(new_df["rank"].iloc[0])
        details = []
        for _, row in new_df.iterrows():
            details.append(f"<div style='display:flex;justify-content:space-between;gap:1.5rem;padding:2px 0;margin-bottom:2px;'><span>{escape(row['name'])}</span><span style='color:var(--accent3);font-weight:700;'>#{int(row['rank'])}</span></div>")
        
        new_entries_title = "New Chart Entries"
        header_html = "<div style='display:flex;justify-content:space-between;padding:2px 0 6px;margin-bottom:6px;border-bottom:1px solid rgba(79,142,247,0.1);font-size:0.65rem;text-transform:uppercase;letter-spacing:0.03em;color:var(--accent);font-weight:700;'><span>Artist</span><span>Artist Rank</span></div>"
        new_entries_details = (
            "<div style='position:sticky;top:-16px;background:rgba(13,20,38,1);padding:4px 0 12px;margin-bottom:12px;font-weight:800;font-size:0.75rem;text-transform:uppercase;color:var(--text2);letter-spacing:0.05em;z-index:10;border-bottom:1px solid rgba(79,142,247,0.15);'>"
            "New Chart Entries</div>"
            f"{header_html}"
            "<div>" + "".join(details) + "</div>"
        )
    else:
        new_entries_title = "New Chart Entries"

    # Calculate progress percentages — top 300 artists sum ~24–30B
    max_listeners = 30_000_000_000
    listener_progress = min(100, (total_monthly / max_listeners * 100))
    artist_progress = min(100, (latam_artists / len(leaderboard) * 100)) if len(leaderboard) > 0 else 0

    cards = [
        ("Spotify Monthly Listeners", fmt_short(total_monthly), "Live Spotify monthly listener sum", "", listener_progress, 
         "<b>Total Ecosystem Reach</b><br>Combined monthly listeners across all tracked artists. This represents the total potential audience reach within the current dataset."),
        ("Artists with LATAM Signals", str(latam_artists), "Currently visible in the regional cut", "kpi-green", artist_progress, 
         "<b>Regional Market Presence</b><br>Count of artists currently appearing on charts in Latin American countries (Mexico, Colombia, Brazil, Argentina, etc.)."),
        (new_entries_title, str(new_entries), "Fresh NEW movements in the latest run", "kpi-amber", 0, new_entries_details),
    ]
    cols = st.columns(len(cards))
    for col, (label, value, delta, klass, progress, tooltip_text) in zip(cols, cards):
        tooltip_html = f'<div class="tooltiptext">{tooltip_text}</div>' if tooltip_text else ''
        tooltip_class = 'tooltip' if tooltip_text else ''
        progress_html = f'<div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>' if progress > 0 else ''
        
        # Build the HTML string without leading spaces to avoid markdown code block interpretation
        card_html = (
            f'<div class="kpi-card {klass} {tooltip_class}">'
            f'<div class="kpi-label">{escape(label)}</div>'
            f'<div class="kpi-value">{escape(value)}</div>'
            f'<div class="kpi-delta">{escape(delta)}</div>'
            f'{progress_html}{tooltip_html}'
            f'</div>'
        )
        col.markdown(card_html, unsafe_allow_html=True)


def prepare_leaderboard_table(leaderboard: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    table_df = leaderboard.head(max_rows)[
        [
            "rank",
            "name",
            "top_song",
            "top_country",
            "monthly_listeners",
            "peak_listeners",
            # "rank_change",
        ]
    ].copy()
    # table_df["rank_change"] = table_df["rank_change"].fillna("=").replace("", "=")
    table_df["monthly_listeners"] = table_df["monthly_listeners"].apply(fmt_short)
    table_df["peak_listeners"] = table_df["peak_listeners"].apply(fmt_short)
    table_df.columns = [
        "Rank",
        "Artist",
        "Top Song",
        "Top Country",
        "Monthly Listeners",
        "Peak Listeners",
        # "Trend",
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

    # Keep all five controls in one row: Table, Analysis, Compare, Download
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
    # with btn_col3:
    #     st.button(
    #         "🎯 Spotlight",
    #         use_container_width=True,
    #         type="primary" if selected_view == "🎯 Spotlight" else "secondary",
    #         key="view_spotlight_btn",
    #         on_click=set_leaderboard_view,
    #         args=("🎯 Spotlight",),
    #     )
    with btn_col3:
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
                    # "Trend": st.column_config.TextColumn(width="small"),
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

        with col_b:
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

        with col_a:
            scatter_data = analysis_df.dropna(subset=["monthly_listeners", "countries_count"])
            if scatter_data.empty:
                st.info("Not enough listener and country coverage data to render analysis charts.")
            else:
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

        # New Threshold Analysis Row
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            "<div class='dashboard-card'><div class='section-title'>⚡ Chart Entry Thresholds</div><div class='section-sub'>Points and listeners required to reach specific leaderboard tiers</div></div>",
            unsafe_allow_html=True,
        )
        
        target_ranks = [10, 20, 50, 100, 150, 200]
        threshold_records = []
        for r_val in target_ranks:
            # Find the artist at or just below this rank to define the entry threshold
            match_row = leaderboard[leaderboard["rank"] >= r_val].sort_values("rank").head(1)
            if not match_row.empty:
                threshold_records.append({
                    "Tier": f"Top {r_val}",
                    "Rank": r_val,
                    "Points": float(match_row.iloc[0].get("total_points", 0)),
                    "Listeners": float(match_row.iloc[0].get("monthly_listeners", 0)),
                    "Artist": match_row.iloc[0]["name"]
                })
        
        if threshold_records:
            thresh_df = pd.DataFrame(threshold_records)
            t_col1, t_col2 = st.columns(2)
            
            with t_col1:
                fig_thresh_pts = px.line(
                    thresh_df, x="Tier", y="Points",
                    markers=True, text="Points",
                    title="Required Total Points by Tier",
                    color_discrete_sequence=["#7c5cfc"]
                )
                fig_thresh_pts.update_traces(
                    textposition="top center",
                    texttemplate="%{y:.2s}",
                    hovertemplate="<b>%{x}</b><br>Required Points: %{y:,.0f}<br><extra></extra>",
                    customdata=thresh_df["Artist"]
                )
                style_figure(fig_thresh_pts, 320)
                st.plotly_chart(fig_thresh_pts, use_container_width=True, config=PLOTLY_CONFIG)
                
            with t_col2:
                fig_thresh_ls = px.line(
                    thresh_df, x="Tier", y="Listeners",
                    markers=True, text="Listeners",
                    title="Required Monthly Listeners by Tier",
                    color_discrete_sequence=["#22d3a0"]
                )
                fig_thresh_ls.update_traces(
                    textposition="top center",
                    texttemplate="%{y:.2s}",
                    hovertemplate="<b>%{x}</b><br>Required Listeners: %{y:,.0f}<br><extra></extra>",
                    customdata=thresh_df["Artist"]
                )
                style_figure(fig_thresh_ls, 320)
                st.plotly_chart(fig_thresh_ls, use_container_width=True, config=PLOTLY_CONFIG)
            
            with st.expander("📋 View Threshold Data Points"):
                display_df = thresh_df[["Tier", "Points", "Listeners"]].copy()
                display_df["Points"] = display_df["Points"].apply(fmt_short)
                display_df["Listeners"] = display_df["Listeners"].apply(fmt_short)
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Points": st.column_config.TextColumn(),
                        "Listeners": st.column_config.TextColumn(),
                    }
                )
        else:
            st.info("Not enough data to calculate thresholds for the requested ranks.")

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
                countries_items = [item.strip() for item in str(row.get("top_country") or "").split("\n") if item.strip()]

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

        latest_scraped_at = None
        window_start = None
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

            # Keep a full day-by-day axis for the selected range even when scrape runs are sparse.
            if latest_scraped_at is not None and window_start is not None:
                target_dates = pd.date_range(start=window_start.normalize(), end=latest_scraped_at.normalize(), freq="D")
                has_sparse_days = line_df["date"].dt.normalize().nunique() < len(target_dates)
                if has_sparse_days:
                    daily_parts = []
                    for artist_name, artist_rows in line_df.groupby("artist", sort=False):
                        artist_daily = artist_rows.copy()
                        artist_daily["date"] = artist_daily["date"].dt.normalize()
                        artist_daily = (
                            artist_daily.sort_values("date")
                            .drop_duplicates(subset=["date"], keep="last")
                            .set_index("date")
                            .reindex(target_dates)
                        )
                        artist_daily["artist"] = artist_name
                        artist_daily["position"] = pd.to_numeric(artist_daily["position"], errors="coerce")
                        artist_daily["position"] = artist_daily["position"].interpolate(method="linear").ffill().bfill()
                        artist_daily = artist_daily.reset_index().rename(columns={"index": "date"})
                        artist_daily["day"] = artist_daily["date"].dt.strftime("%b %-d")
                        daily_parts.append(artist_daily[["day", "date", "artist", "position"]])

                    if daily_parts:
                        line_df = pd.concat(daily_parts, ignore_index=True)
                        st.info(
                            "📊 Historical runs are sparse in this window, so missing days are interpolated for smoother day-by-day trends.",
                            icon="ℹ️",
                        )

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
    with st.expander("📊 Detailed Movement Analysis", expanded=True):
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
    
    with tab2:
        col_select, col_spacer = st.columns([0.25, 0.75])
        with col_select:
            top_n_market = st.selectbox(
                "Top artists",
                options=[10, 50, 100, 200],
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
                st.plotly_chart(fig_market_share, use_container_width=True, config=PLOTLY_CONFIG)

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
                st.plotly_chart(fig_source_bars, use_container_width=True, config=PLOTLY_CONFIG)

    with tab3:
        # Control bar for Global Charting
        gl_control1, gl_control2 = st.columns([1, 1])
        with gl_control1:
            top_n_options = [10, 20, 50, 100, 200]
            selected_n = st.selectbox("🎯 Select Top List", options=top_n_options, index=2, key="gl_chart_top_n_dropdown")
        
        with gl_control2:
            time_ranges = {1: "Daily (Last Run)", 7: "7 days", 14: "14 days", 30: "30 days"}
            selected_days = st.selectbox("📅 Time Range", options=list(time_ranges.keys()), format_func=lambda x: time_ranges[x], index=0)

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
            lambda r: f"#{int(r['start_pos'])} ➔ #{int(r['current_pos'])}" if r['range_change'] != 0 else f"#{int(r['current_pos'])} (No change in {selected_days}d)", axis=1
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
                        f"Peak in {selected_days}d: #{int(row['range_peak'])}<br>"
                        f"Starting: #{int(row['start_pos'])}<br>"
                        f"Current: #{int(row['current_pos'])}<br>"
                        f"Movement: {row['movement_label']}<extra></extra>"
                    ),
                    showlegend=False
                ))
                
                # Label at the end: Show transition Clearly (Pela #X ➔ Have #Y)
                trend_arrow = "↑" if row["range_change"] > 0 else "↓" if row["range_change"] < 0 else "•"
                label_text = f" <b>#{int(row['start_pos'])} {trend_arrow} #{int(row['current_pos'])}</b>"
                
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
                height=max(500, len(gl_chart_df) * 40),
                margin=dict(l=180, r=150, t=60, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                bargap=0.35
            )
            
            chart_box_height = 750 if len(gl_chart_df) > 15 else None
            with st.container(height=chart_box_height):
                st.plotly_chart(fig_move, use_container_width=True, config=PLOTLY_CONFIG)
        
    
    # Detailed Data Table removed as requested


def render_debut_artist_chart(leaderboard: pd.DataFrame) -> None:
    if leaderboard.empty:
        st.warning("No artist data available yet.")
        return

    sorted_artists = leaderboard.sort_values("rank").dropna(subset=["name", "rank"]).copy()
    
    sorted_artists["rank"] = sorted_artists["rank"].astype(int)
    sorted_artists["display_label"] = sorted_artists["name"]
    artist_options = sorted_artists["display_label"].tolist()
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Get global selection or default to top ranked
    default_artist = st.session_state.get("global_selected_artist", "All artists")
    if default_artist == "All artists" and artist_options:
        default_artist = artist_options[0]
        
    try:
        # Check if the exact label or the name is in options
        if default_artist in artist_options:
            default_idx = artist_options.index(default_artist)
        else:
            # Fallback: try to find an option that matches the artist name
            matches = [i for i, opt in enumerate(artist_options) if default_artist in opt]
            default_idx = matches[0] if matches else 0
    except (ValueError, IndexError):
        default_idx = 0

    col1, col2 = st.columns([1.5, 1.6])
    with col2:
        selected_label = st.selectbox(
            "🎤 Select an Artist",
            artist_options,
            index=default_idx if artist_options else None,
            key="debut_artist_select"
        )
    
    # Sync global selection if changed here
    if selected_label != st.session_state.get("global_selected_artist"):
        st.session_state.global_selected_artist = selected_label
        st.rerun()
    
    if not selected_label:
        st.info("Please select an artist from the dropdown above.")
        return
    
    selected_artist = selected_label.split(" - ", 1)[1] if " - " in selected_label else selected_label
    
    artist_data = leaderboard[leaderboard["name"] == selected_artist]
    
    if artist_data.empty:
        st.warning(f"No data found for {selected_artist}.")
        return
    
    row = artist_data.iloc[0]
    
    # --- Artist Hero Section (New) ---
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Try to get real image URL, fallback to generated avatar
    real_img_url = get_artist_image_url(row['name'])
    display_img = real_img_url if real_img_url else get_fallback_avatar_url(row['name'])
    
    hero_col1, hero_col2 = st.columns([1, 4])
    with hero_col1:
        st.markdown(
            f"""
            <div style="display: flex; justify-content: center; align-items: center; padding: 10px;">
                <img src="{display_img}" style="width: 100%; max-width: 180px; border-radius: 24px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); border: 2px solid var(--border);">
            </div>
            """,
            unsafe_allow_html=True
        )
    with hero_col2:
        st.markdown(f"<h1 style='margin-bottom: 0;'>{escape(row['name'])}</h1>", unsafe_allow_html=True)
        if pd.notna(row.get('page_title')):
            st.markdown(f"<p style='color: var(--text2); font-size: 1.1rem;'>{escape(str(row.get('page_title')))}</p>", unsafe_allow_html=True)
        
        # Action badges
        st.markdown(
            f"""
            <div style="display: flex; gap: 10px; margin-top: 15px; flex-wrap: wrap;">
                <span class="badge badge-new" style="padding: 5px 12px; font-size: 0.85rem;">#{int(row['rank'])}</span>
                <span class="badge badge-up" style="padding: 5px 12px; font-size: 0.85rem;">{escape(str(row.get('display_country') or 'Global'))}</span>
                <span class="badge badge-same" style="padding: 5px 12px; font-size: 0.85rem;">{fmt_short(row.get('monthly_listeners'))} Monthly</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        rank_val = int(row.get("rank")) if pd.notna(row.get("rank")) else 0
        st.metric("📊 Current Rank", f"{rank_val}")
    with kpi2:
        songs_val = row.get("songs_count")
        st.metric("🎵 Songs", int(songs_val) if pd.notna(songs_val) else 0)
    with kpi3:
        albums_val = row.get("albums_count")
        st.metric("💿 Albums", int(albums_val) if pd.notna(albums_val) else 0)
    with kpi4:
        countries_val = row.get("countries_count")
        st.metric("🌎 LATAM Countries", int(countries_val) if pd.notna(countries_val) else 0)
    
    kpi5, kpi6, kpi7, kpi8 = st.columns(4)
    with kpi5:
        ml_val = row.get("monthly_listeners")
        st.metric("👥 Monthly Listeners", fmt_short(ml_val) if pd.notna(ml_val) else "—")
    with kpi6:
        peak_val = row.get("peak_listeners")
        st.metric("🚀 Peak Listeners", fmt_short(peak_val) if pd.notna(peak_val) else "—")
    with kpi7:
        points_val = row.get("total_points")
        st.metric("⭐ Total Points", fmt_short(points_val) if pd.notna(points_val) else "—")
    with kpi8:
        trend_change = str(row.get("rank_change") or "=").strip()
        st.metric("📈 Trend", trend_change)

    st.markdown("<br>", unsafe_allow_html=True)
    
    with st.expander("📋 Artist Profile Details", expanded=True):
        profile_title = str(row.get("page_title") or "").strip()
        profile_snapshot = str(row.get("snapshot_text") or "").strip()
        
        if profile_title:
            st.markdown(f"#### 🪪 {escape(profile_title)}")
        if profile_snapshot:
            st.caption(profile_snapshot)
        
        meta_left, meta_right = st.columns(2)
        with meta_left:
            st.markdown(f"**🌍 Top Country:** {escape(str(row.get('display_country') or '—'))}")
            st.markdown(f"**🎵 Top Song:** {escape(str(row.get('top_song') or '—'))}")
                
    # --- Wikipedia Bio Section (New) ---
    wiki_data = get_wikipedia_data(row['name'])
    if wiki_data:
        with st.expander("📖 Wikipedia Biography & Background", expanded=True):
            w_col1, w_col2 = st.columns([1, 2.5])
            
            with w_col1:
                image_url = wiki_data.get("originalimage", {}).get("source") or wiki_data.get("thumbnail", {}).get("source")
                if image_url:
                    st.markdown(
                        f"""
                        <div style="border-radius: 12px; overflow: hidden; border: 1px solid var(--border); box-shadow: 0 10px 25px rgba(0,0,0,0.3); max-height: 320px; background: rgba(0,0,0,0.2); display: flex; justify-content: center;">
                            <img src="{image_url}" style="max-width: 100%; max-height: 320px; object-fit: contain; display: block;">
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                    st.markdown("<br>", unsafe_allow_html=True)
                
                desc = wiki_data.get("description")
                if desc:
                    st.markdown(f"**Role:** {desc}")
                
                source_url = wiki_data.get("content_urls", {}).get("desktop", {}).get("page")
                if source_url:
                    st.markdown(f"[View on Wikipedia ↗️]({source_url})")

            with w_col2:
                st.markdown(f"#### {wiki_data.get('title')}")
                extract = wiki_data.get("extract")
                if extract:
                    st.markdown(f"<div style='font-size: 0.95rem; line-height: 1.6; color: var(--text);'>{extract}</div>", unsafe_allow_html=True)
                else:
                    st.info("Detailed biography is currently being summarized...")

    st.markdown("<br>", unsafe_allow_html=True)
    
    songs_items = [item.strip() for item in str(row.get("top_songs") or "").split("\n") if item.strip()]
    albums_items = [item.strip() for item in str(row.get("top_albums") or "").split("\n") if item.strip()]
    countries_items = [item.strip() for item in str(row.get("top_countries") or "").split("\n") if item.strip()]
    top_n_count = len(songs_items)

    with st.expander("🎵 Top Tracks, Albums & Countries", expanded=True):
        col_songs, col_albums, col_countries = st.columns(3)

        with col_songs:
            st.markdown(f"#### 🎵 Top {top_n_count} Tracks" if top_n_count else "#### 🎵 Top Songs")
            if songs_items:
                for idx, item in enumerate(songs_items, start=1):
                    st.markdown(f"{idx}. {escape(item)}")
            else:
                st.caption("No songs available.")

        with col_albums:
            st.markdown("#### 💿 Top Albums")
            if albums_items:
                for idx, item in enumerate(albums_items, start=1):
                    st.markdown(f"{idx}. {escape(item)}")
            else:
                st.caption("No albums available.")

        with col_countries:
            st.markdown("#### 🗺️ Top Countries")
            if countries_items:
                for idx, item in enumerate(countries_items, start=1):
                    st.markdown(f"{idx}. {escape(item)}")
            else:
                st.caption("No countries available.")

    # if countries_items:
        # with st.expander("📊 Market Share", expanded=True):
        #     total_countries = len(countries_items)
        #     if total_countries > 0:
        #         share_data = [{"Country": c, "Share": 1} for c in countries_items]
        #         share_df = pd.DataFrame(share_data)
        #         fig_share = px.pie(
        #             share_df,
        #             names="Country",
        #             values="Share",
        #             hole=0.58,
        #             color="Country",
        #             color_discrete_sequence=CHART_COLORS,
        #         )
        #         fig_share.update_traces(
        #             textposition="inside",
        #             textinfo="percent+label",
        #             hovertemplate="<b>%{label}</b><br>Market share<extra></extra>",
        #         )
        #         fig_share.update_layout(
        #             title="Market Distribution",
        #             showlegend=False,
        #             annotations=[
        #                 dict(
        #                     text="Share<br>by<br>country",
        #                     x=0.5,
        #                     y=0.5,
        #                     showarrow=False,
        #                     font=dict(size=11, color="#cbd5f5"),
        #                 )
        #             ],
        #         )
        #         style_figure(fig_share, 260)
        #         st.plotly_chart(fig_share, use_container_width=True, config=PLOTLY_CONFIG)
    
    with st.expander("📊 Performance Summary", expanded=True):
        songs_s = row.get("songs_count")
        albums_s = row.get("albums_count")
        countries_s = row.get("countries_count")
        summary_data = {
            "Metric": ["Rank", "Monthly Listeners", "Peak Listeners", "Songs", "Albums", "LATAM Countries", "Total Points"],
            "Value": [
                str(rank_val),
                str(fmt_short(row.get("monthly_listeners"))) if pd.notna(row.get("monthly_listeners")) else "—",
                str(fmt_short(row.get("peak_listeners"))) if pd.notna(row.get("peak_listeners")) else "—",
                str(int(songs_s)) if pd.notna(songs_s) else "0",
                str(int(albums_s)) if pd.notna(albums_s) else "0",
                str(int(countries_s)) if pd.notna(countries_s) else "0",
                str(fmt_short(row.get("total_points"))) if pd.notna(row.get("total_points")) else "—",
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)


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
top_history = data.get("top_history", pd.DataFrame())
raw_benchmarks = data.get("raw_benchmarks", pd.DataFrame())
debuts = data.get("debuts", pd.DataFrame())

last_run_label = "n/a"
if not runs.empty and runs["finished_at"].notna().any():
    last_run_label = runs["finished_at"].dropna().max().strftime("%Y-%m-%d %H:%M")





def show_leaderboard_page() -> None:
    page_title, page_meta = PAGE_META["Leaderboard"]
    render_header(page_title, page_meta, last_run_label)
    # Use global_filtered to allow the spotlight and full table context
    render_leaderboard(global_filtered, runs, max_rows=max_rows)


def show_chart_tracker_page() -> None:
    page_title, page_meta = PAGE_META["Chart Tracker"]
    render_header(page_title, page_meta, last_run_label)
    # Use global_filtered to show top artists + selected artist spotlight
    render_chart_tracker(history, global_filtered)


def show_stream_trends_page() -> None:
    page_title, page_meta = PAGE_META["Stream Trends"]
    render_header(page_title, page_meta, last_run_label)
    render_stream_trends(filtered, leaderboard, top_history, history)


def show_debut_artist_page() -> None:
    page_title, page_meta = PAGE_META["Artist Spotlight"]
    render_header(page_title, page_meta, last_run_label)
    # Use global_filtered to allow changing artists in the dropdown
    render_debut_artist_chart(global_filtered)


def show_ai_analyst_page() -> None:
    page_title, page_meta = PAGE_META["AI Data Analyst"]
    render_header(page_title, page_meta, last_run_label)
    render_custom_chatbot()


def show_artist_analysis_page() -> None:
    global raw_benchmarks, debuts
    page_title, page_meta = PAGE_META["Artist Analysis"]
    render_header(page_title, page_meta, last_run_label)
    
    # Persistent Sub-tab Navigation for Artist Analysis
    if "analysis_sub_tab" not in st.session_state:
        st.session_state.analysis_sub_tab = "📊 Ranking"
    
    tab_names = ["📊 Ranking", "👤 Artist", "🏷️ Label", "📈 Movement", "💰 Acquisition"]
    t_cols = st.columns(len(tab_names))
    for i, name in enumerate(tab_names):
        is_active = st.session_state.analysis_sub_tab == name
        if t_cols[i].button(name, key=f"subtab_btn_{name}", use_container_width=True, type="primary" if is_active else "secondary"):
            st.session_state.analysis_sub_tab = name
            st.rerun()
            
    st.divider()
    active_tab = st.session_state.analysis_sub_tab
    
    if active_tab == "📊 Ranking":
        # Calculate and Display Aggregate Streaming Metrics
        if not raw_benchmarks.empty:
            latest_date = raw_benchmarks['chart_date'].max()
            latest_bench = raw_benchmarks[raw_benchmarks['chart_date'] == latest_date]
            
            t20_streams = latest_bench[latest_bench['rank'] <= 20]['streams'].sum()
            t50_streams = latest_bench[latest_bench['rank'] <= 50]['streams'].sum()
            t100_streams = latest_bench[latest_bench['rank'] <= 100]['streams'].sum()
            
            st.markdown(f"""
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; margin-top: 10px;">
                <div style="background: linear-gradient(135deg, rgba(79, 142, 247, 0.12) 0%, rgba(79, 142, 247, 0.05) 100%); border: 1px solid rgba(79, 142, 247, 0.25); border-radius: 16px; padding: 22px; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.15); transition: transform 0.3s ease;">
                    <div style="color: #4f8ef7; font-size: 0.8rem; font-weight: 700; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.9;">Top 20 Total Streams</div>
                    <div style="font-size: 2.2rem; font-weight: 800; color: #ffffff; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">{fmt_short(t20_streams)}</div>
                    <div style="color: #8fa3ad; font-size: 0.85rem; margin-top: 8px; font-weight: 500;">Market Leaders Volume</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(34, 211, 160, 0.12) 0%, rgba(34, 211, 160, 0.05) 100%); border: 1px solid rgba(34, 211, 160, 0.25); border-radius: 16px; padding: 22px; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.15); transition: transform 0.3s ease;">
                    <div style="color: #22d3a0; font-size: 0.8rem; font-weight: 700; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.9;">Top 50 Total Streams</div>
                    <div style="font-size: 2.2rem; font-weight: 800; color: #ffffff; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">{fmt_short(t50_streams)}</div>
                    <div style="color: #8fa3ad; font-size: 0.85rem; margin-top: 8px; font-weight: 500;">Mid-Chart Momentum</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(124, 92, 252, 0.12) 0%, rgba(124, 92, 252, 0.05) 100%); border: 1px solid rgba(124, 92, 252, 0.25); border-radius: 16px; padding: 22px; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.15); transition: transform 0.3s ease;">
                    <div style="color: #7c5cfc; font-size: 0.8rem; font-weight: 700; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.9;">Top 100 Total Streams</div>
                    <div style="font-size: 2.2rem; font-weight: 800; color: #ffffff; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">{fmt_short(t100_streams)}</div>
                    <div style="color: #8fa3ad; font-size: 0.85rem; margin-top: 8px; font-weight: 500;">Total Chart Reach</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("### 📊 Top Artist Rankings")
        # Global filter already applied to 'leaderboard' via 'global_filtered' if we want consistency
        # but here we use the full leaderboard for a broader view
        top_n = st.slider("Show top N artists", 10, 100, 20)
        top_df = leaderboard.sort_values("total_points", ascending=False).head(top_n)
        
        fig = px.bar(
            top_df,
            x="total_points",
            y="name",
            orientation="h",
            title=f"Top {top_n} Artists by Total Points",
            color="total_points",
            color_continuous_scale="Blues",
            labels={"total_points": "Points", "name": "Artist"}
        )
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
        style_figure(fig, 500)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        
        st.markdown("#### 🏆 Artist Ranking List")
        
        # Professional Ranking Table with interactive buttons for reliable redirection
        # Header
        h1, h2, h3, h4, h5 = st.columns([0.6, 2, 1.2, 1.2, 1.2])
        with h1: st.markdown("**Rank**")
        with h2: st.markdown("**Artist Name**")
        with h3: st.markdown("**Listeners**")
        with h4: st.markdown("**Spotify Pts**")
        with h5: st.markdown("**Action**")
        
        st.divider()
        
        # Display rows in a scrollable container for better UI
        container_height = 500
        with st.container(height=container_height):
            for _, row in top_df.iterrows():
                r1, r2, r3, r4, r5 = st.columns([0.6, 2, 1.2, 1.2, 1.2])
                with r1: st.markdown(f"**#{row['rank']}**")
                with r2: st.markdown(f"{row['name']}")
                with r3: st.write(f"{fmt_short(row['monthly_listeners'])}" if pd.notna(row['monthly_listeners']) else "—")
                with r4: st.write(f"{fmt_short(row['spotify_points'])}" if pd.notna(row['spotify_points']) else "—")
                with r5:
                    if st.button("Get Details ➔", key=f"btn_rank_{row['name']}", use_container_width=True):
                        st.session_state.global_selected_artist = row['name']
                        # Set redirection flag for Artist Spotlight page
                        st.session_state.redirect_to_page = "Artist Spotlight"
                        # Clear specific page state to ensure the dropdown updates
                        if "debut_artist_select" in st.session_state:
                            del st.session_state["debut_artist_select"]
                        st.rerun()

    elif active_tab == "👤 Artist":
        st.markdown("### 👤 Artist Performance Analysis")
        
        # 🌟 Quick Analysis Select (Enhanced with Search & Refresh)
        qa_h1, qa_h2, qa_h3 = st.columns([0.45, 0.37, 0.18])
        with qa_h1:
            st.markdown("#### 🌟 Quick Analysis Select")
        with qa_h2:
            artist_list = ["Select Artist..."] + sorted(leaderboard["name"].tolist())
            current_sel = st.session_state.get("global_selected_artist", "Select Artist...")
            if current_sel not in artist_list:
                current_sel_idx = 0
            else:
                current_sel_idx = artist_list.index(current_sel)
                
            selected_artist_search = st.selectbox(
                "Search Artist",
                options=artist_list,
                index=current_sel_idx,
                key="quick_analysis_search",
                label_visibility="collapsed",
                placeholder="🔍 Search & Analyze Artist..."
            )
            
            if selected_artist_search != "Select Artist..." and selected_artist_search != st.session_state.get("global_selected_artist"):
                st.session_state.global_selected_artist = selected_artist_search
                if "debut_artist_select" in st.session_state:
                    del st.session_state["debut_artist_select"]
                st.rerun()
                
        with qa_h3:
            if st.button("🔄 Refresh", key="refresh_quick_analysis", use_container_width=True, help="Update data and show next set of top artists"):
                st.cache_data.clear()
                if "quick_select_offset" not in st.session_state:
                    st.session_state.quick_select_offset = 0
                st.session_state.quick_select_offset = (st.session_state.quick_select_offset + 12) % 48
                st.rerun()

        # Determine which artists to show (12 at a time)
        offset = st.session_state.get("quick_select_offset", 0)
        if offset >= len(leaderboard):
            offset = 0
            
        display_quick_df = leaderboard.iloc[offset:offset+12]
        
        quick_cols = st.columns(4)
        for idx, (_, row) in enumerate(display_quick_df.iterrows()):
            with quick_cols[idx % 4]:
                # Highlight selected artist if any
                btn_label = row['name']
                if st.session_state.get("global_selected_artist") == row['name']:
                    btn_label = f"✨ {row['name']}"
                
                if st.button(btn_label, key=f"quick_tab_{row['name']}_{offset}", use_container_width=True):
                    st.session_state.global_selected_artist = row['name']
                    st.rerun()

        st.divider()
        selected = st.session_state.get("global_selected_artist", "All artists")
        
        if selected == "All artists":
            st.markdown("#### 📋 Artist Directory")
            st.info("Click on a top artist above or use the sidebar search to analyze specific performance metrics.")
            
            # Searchable inventory
            search_q = st.text_input("🔍 Filter Artist List", placeholder="Search by name...", key="tab_artist_search")
            
            display_df_dir = leaderboard.copy()
            if search_q:
                display_df_dir = display_df_dir[display_df_dir["name"].str.contains(search_q, case=False, na=False)]
            
            st.dataframe(
                display_df_dir[["rank", "name", "display_country", "total_points", "monthly_listeners"]].sort_values("rank"),
                column_config={
                    "rank": "Rank",
                    "name": "Artist Name",
                    "display_country": "Market",
                    "total_points": "Points",
                    "monthly_listeners": "Listeners"
                },
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            artist_rows = leaderboard[leaderboard["name"] == selected]
            if not artist_rows.empty:
                row = artist_rows.iloc[0]
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Global Rank", f"#{row['rank']}")
                col2.metric("Total Points", f"{row['total_points']:,}")
                col3.metric("Monthly Listeners", fmt_short(row['monthly_listeners']) if pd.notna(row['monthly_listeners']) else "—")
                col4.metric("Market Reach", f"{row['countries_count']} countries")
                
                # 📊 Analytical Performance Summary (Relative to Top 100)
                st.markdown("#### 📊 Analytical Performance Summary")
                
                # Calculate market averages for comparison
                avg_points = leaderboard["total_points"].mean()
                avg_listeners = leaderboard["monthly_listeners"].mean()
                avg_reach = leaderboard["countries_count"].mean()
                
                pts_vs_avg = ((row['total_points'] - avg_points) / avg_points) * 100 if avg_points > 0 else 0
                listeners_vs_avg = ((row['monthly_listeners'] - avg_listeners) / avg_listeners) * 100 if avg_listeners > 0 and pd.notna(row['monthly_listeners']) else 0
                reach_vs_avg = ((row['countries_count'] - avg_reach) / avg_reach) * 100 if avg_reach > 0 else 0
                
                summary_cols = st.columns(3)
                with summary_cols[0]:
                    st.markdown(f"""
                    <div style="background: rgba(28, 32, 45, 0.4); border-radius: 12px; border-left: 4px solid #4f8ef7; padding: 15px; height: 100%;">
                        <div style="color: #8fa3ad; font-size: 0.8rem; font-weight: 600;">MARKET STANDING</div>
                        <div style="font-size: 1.2rem; font-weight: 700; color: white; margin-top: 5px;">{"+" if pts_vs_avg > 0 else ""}{pts_vs_avg:.1f}%</div>
                        <div style="color: #a1a1a1; font-size: 0.85rem; margin-top: 3px;">Relative to Top 100 Average Points</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with summary_cols[1]:
                    st.markdown(f"""
                    <div style="background: rgba(28, 32, 45, 0.4); border-radius: 12px; border-left: 4px solid #22d3a0; padding: 15px; height: 100%;">
                        <div style="color: #8fa3ad; font-size: 0.8rem; font-weight: 600;">AUDIENCE POWER</div>
                        <div style="font-size: 1.2rem; font-weight: 700; color: white; margin-top: 5px;">{"+" if listeners_vs_avg > 0 else ""}{listeners_vs_avg:.1f}%</div>
                        <div style="color: #a1a1a1; font-size: 0.85rem; margin-top: 3px;">Relative to Top 100 Average Listeners</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with summary_cols[2]:
                    st.markdown(f"""
                    <div style="background: rgba(28, 32, 45, 0.4); border-radius: 12px; border-left: 4px solid #7c5cfc; padding: 15px; height: 100%;">
                        <div style="color: #8fa3ad; font-size: 0.8rem; font-weight: 600;">GLOBAL DOMINANCE</div>
                        <div style="font-size: 1.2rem; font-weight: 700; color: white; margin-top: 5px;">{"+" if reach_vs_avg > 0 else ""}{reach_vs_avg:.1f}%</div>
                        <div style="color: #a1a1a1; font-size: 0.85rem; margin-top: 3px;">Relative to Top 100 Average Reach</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Descriptive Summary Logic
                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                best_rank_label = f"#{int(row['best_rank'])}" if pd.notna(row['best_rank']) else "N/A"
                weeks_label = f"{int(row['weeks_on_chart'])} weeks" if pd.notna(row['weeks_on_chart']) else "Data pending"
                
                standing_desc = "Outperforming the market average" if pts_vs_avg > 0 else "Approaching market average"
                reach_desc = f"dominating in {row['countries_count']} countries" if row['countries_count'] > avg_reach else f"active in {row['countries_count']} markets"
                
                st.info(f"✨ **Artist Insight**: {selected} is currently {standing_desc}, {reach_desc}. With a career peak of **{best_rank_label}** and **{weeks_label}** on the charts, this artist shows {'strong longevity' if (row['weeks_on_chart'] or 0) > 10 else 'emerging momentum'} in the global Latin landscape.")
                st.divider()

                # Wikipedia Bio (New)
                wiki_data = get_wikipedia_data(selected)
                if wiki_data:
                    with st.expander("📖 Wikipedia Biography", expanded=False):
                        w_c1, w_c2 = st.columns([1, 3])
                        with w_c1:
                            img_url = wiki_data.get("originalimage", {}).get("source") or wiki_data.get("thumbnail", {}).get("source")
                            if img_url:
                                st.markdown(
                                    f"""
                                    <div style="border-radius: 10px; overflow: hidden; border: 1px solid var(--border); max-height: 220px; background: rgba(0,0,0,0.2); display: flex; justify-content: center;">
                                        <img src="{img_url}" style="max-width: 100%; max-height: 220px; object-fit: contain;">
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                        with w_c2:
                            st.markdown(f"**{wiki_data.get('description', 'Artist')}**")
                            st.write(wiki_data.get("extract", ""))
                            if "content_urls" in wiki_data:
                                st.markdown(f"[Read more on Wikipedia]({wiki_data['content_urls']['desktop']['page']})")

                # Show history if available
                artist_hist = history[history["name"] == selected]
                if not artist_hist.empty:
                    fig_hist = px.line(
                        artist_hist, 
                        x="scraped_at", 
                        y="rank", 
                        title=f"Rank Trajectory: {selected}",
                        markers=True
                    )
                    fig_hist.update_yaxes(autorange="reversed")
                    style_figure(fig_hist, 400)
                    st.plotly_chart(fig_hist, use_container_width=True, config=PLOTLY_CONFIG)
                else:
                    st.info(f"📊 Rank Trajectory data for **{selected}** is being collected. Historical trends will appear as more snapshots are captured.")
            else:
                st.error(f"Data not found for {selected}")
        
    elif active_tab == "🏷️ Label":
        st.markdown("### 🏷️ Label Market Intelligence")
        st.info("Distribution of top artists across major record labels and independent groups.")
        
        # Artist-Label Mapping (Heuristic-based for Top Artists)
        ARTIST_LABELS = {
            "Bad Bunny": "Rimas Entertainment",
            "Karol G": "Universal Music Latino",
            "Shakira": "Sony Music Latin",
            "J Balvin": "Universal Music Latino",
            "Maluma": "Sony Music Latin",
            "Rauw Alejandro": "Sony Music Latin",
            "Peso Pluma": "Double P Records",
            "Feid": "Universal Music Latino",
            "Myke Towers": "Warner Music Latina",
            "Anuel AA": "Real Hasta la Muerte",
            "Daddy Yankee": "Universal Music Latino",
            "Rosalía": "Sony Music (Columbia)",
            "Bizarrap": "Dale Play Records",
            "Ozuna": "Sony Music Latin",
            "Farruko": "Sony Music Latin",
            "Camilo": "Sony Music Latin",
            "Sebastian Yatra": "Universal Music Latino",
            "Christian Nodal": "Sony Music Latin",
            "Luis Miguel": "Warner Music Latina",
            "Enrique Iglesias": "Sony Music Latin",
            "Marc Anthony": "Sony Music Latin",
            "Ricky Martin": "Sony Music Latin",
            "Romeo Santos": "Sony Music Latin",
            "Prince Royce": "Sony Music Latin",
            "Becky G": "Sony Music Latin",
            "Natti Natasha": "Sony Music Latin",
            "Junior H": "Warner Music Latina",
            "Natanael Cano": "Warner Music Latina",
            "Fuerza Regida": "Sony Music Latin",
            "Eslabon Armado": "DEL Records",
            "Young Miko": "The Wave Music Group",
            "Tini": "Sony Music Latin",
            "Maria Becerra": "Warner Music Latina",
        }
        
        # Apply labels to leaderboard
        label_df = leaderboard.copy()
        label_df["label"] = label_df["name"].map(ARTIST_LABELS).fillna("Independent / Other")
        
        # Summarize by Label
        label_summary = label_df.groupby("label").agg({
            "name": "count",
            "total_points": "sum"
        }).reset_index().rename(columns={"name": "artist_count"})
        
        l_col1, l_col2 = st.columns([1, 1.2])
        
        with l_col1:
            st.markdown("#### 📊 Market Share by Points")
            fig_label = px.pie(
                label_summary, 
                values="total_points", 
                names="label", 
                hole=0.4,
                color_discrete_sequence=CHART_COLORS
            )
            style_figure(fig_label, 350)
            st.plotly_chart(fig_label, use_container_width=True, config=PLOTLY_CONFIG)
            
        with l_col2:
            st.markdown("#### 🏢 Label Directory")
            selected_label = st.selectbox("Select a Label to view Artists", ["All Labels"] + sorted(label_summary["label"].tolist()))
            
            if selected_label == "All Labels":
                st.dataframe(label_summary.sort_values("artist_count", ascending=False), use_container_width=True, hide_index=True)
            else:
                artists_under_label = label_df[label_df["label"] == selected_label].sort_values("rank")
                st.markdown(f"**Artists under {selected_label}:**")
                for _, a_row in artists_under_label.iterrows():
                    st.markdown(f"- **{a_row['name']}** (Rank #{a_row['rank']})")
                    
        st.divider()
        st.markdown("#### 📈 Top Label Performance (Drill-down)")
        st.info("Click on a label to see its full roster and top track performance.")
        
        # Sort labels by total points
        sorted_labels = label_summary.sort_values("total_points", ascending=False)
        
        for _, l_row in sorted_labels.iterrows():
            label_name = l_row["label"]
            with st.expander(f"🏢 {label_name} — {l_row['artist_count']} Artists | {fmt_short(l_row['total_points'])} Points"):
                label_artists = label_df[label_df["label"] == label_name].sort_values("rank")
                
                # Create a clean details table for the label
                details_data = []
                for _, a_row in label_artists.iterrows():
                    details_data.append({
                        "Artist": a_row["name"],
                        "Top Track": a_row.get("top_song", "—"),
                        "Total Streams (Pts)": f"{a_row['total_points']:,}"
                    })
                
                st.dataframe(
                    pd.DataFrame(details_data),
                    use_container_width=True,
                    hide_index=True
                )
                
                if label_name != "Independent / Other":
                    st.caption(f"💡 {label_name} currently manages {l_row['artist_count']} of the top 100 global Latin artists.")
        
    elif active_tab == "📈 Movement":
        st.markdown("### 📈 Market Movement")
        st.info("Tracking momentum and significant rank shifts within the last 24 hours.")
        
        # Calculate some movement if possible
        if "rank_change" in leaderboard.columns:
            gainers = leaderboard[leaderboard["rank_change"].str.startswith("+", na=False)].copy()
            if not gainers.empty:
                gainers["change_val"] = pd.to_numeric(gainers["rank_change"].str.replace("+", "", regex=False), errors="coerce")
                top_gainers = gainers.dropna(subset=["change_val"]).sort_values("change_val", ascending=False).head(10)
                if not top_gainers.empty:
                    st.markdown("#### 🚀 Top Gainers")
                    st.dataframe(top_gainers[["name", "rank", "rank_change", "total_points"]], use_container_width=True, hide_index=True)
            
            # Top Losers
            losers = leaderboard[leaderboard["rank_change"].str.startswith("-", na=False)].copy()
            if not losers.empty:
                losers["change_val"] = pd.to_numeric(losers["rank_change"].str.replace("-", "", regex=False), errors="coerce")
                top_losers = losers.dropna(subset=["change_val"]).sort_values("change_val", ascending=False).head(10)
                if not top_losers.empty:
                    st.markdown("#### 📉 Top Losers")
                    st.dataframe(top_losers[["name", "rank", "rank_change", "total_points"]], use_container_width=True, hide_index=True)
            
            if gainers.empty and losers.empty:
                st.write("No significant movement detected in the current snapshot.")
        
        # 🆕 New Artist Debuts Section
        st.divider()
        st.markdown("#### 🆕 New Artist Debuts")
        st.info("Tracking artists who recently made their first appearance on the global charts.")
        
        if not debuts.empty:
            # Filters for Debuts
            d_col1, d_col2 = st.columns([1, 1.2])
            with d_col1:
                debut_period = st.radio("⏱️ Filter By", ["Today", "Last Week"], horizontal=True, key="debut_period_filter")
            
            # Use latest debut date as "today" reference
            latest_debut = debuts["debut_at"].max()
            
            if debut_period == "Today":
                period_debuts = debuts[debuts["debut_at"].dt.date == latest_debut.date()].copy()
                # Fallback if no debuts today: show last 24h
                if period_debuts.empty:
                    period_debuts = debuts[debuts["debut_at"] >= (latest_debut - pd.Timedelta(hours=24))].copy()
                period_label = "Today"
            else:
                period_debuts = debuts[debuts["debut_at"].dt.date > (latest_debut.date() - pd.Timedelta(days=7))].copy()
                period_label = "Last Week"
            
            if not period_debuts.empty:
                # Summary Metric Card
                st.success(f"🔥 **{len(period_debuts)}** new artists debuted {period_label.lower()}!")
                
                # Debut Volume Graph
                st.markdown(f"##### 📈 Debut Momentum ({period_label})")
                daily_debuts = period_debuts.copy()
                daily_debuts["date"] = daily_debuts["debut_at"].dt.date
                counts = daily_debuts.groupby("date").size().reset_index(name="Artist Count")
                
                fig_debut = px.line(
                    counts, 
                    x="date", 
                    y="Artist Count", 
                    markers=True,
                    title="Daily New Additions",
                    color_discrete_sequence=["#7c5cfc"]
                )
                fig_debut.update_traces(line=dict(width=3), marker=dict(size=8))
                style_figure(fig_debut, 300)
                st.plotly_chart(fig_debut, use_container_width=True, config=PLOTLY_CONFIG)
                
                # Debut List
                st.markdown("##### 🏆 Debut List")
                # Merge with current leaderboard to show progression if possible
                display_df = period_debuts.merge(
                    leaderboard[["name", "rank", "total_points"]], 
                    on="name", 
                    how="left"
                )
                display_df = display_df.rename(columns={
                    "rank": "Current Rank",
                    "total_points": "Current Points"
                })
                
                # Format for display
                display_df["debut_at"] = display_df["debut_at"].dt.strftime("%d %b %H:%M")
                
                st.dataframe(
                    display_df[["name", "debut_at", "debut_rank", "Current Rank", "debut_points", "Current Points"]].sort_values("debut_rank"),
                    column_config={
                        "name": "Artist Name",
                        "debut_at": "First Seen",
                        "debut_rank": "Entry Rank",
                        "Current Rank": "Now",
                        "debut_points": st.column_config.NumberColumn("Entry Pts", format="%d"),
                        "Current Points": st.column_config.NumberColumn("Total Pts", format="%d")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info(f"No new artists debuted {period_label.lower()}.")
        else:
            st.warning("No debut data available in the last 30 days.")
        
        st.divider()
        st.markdown("#### 🌊 Streaming Chart")
        st.info("Daily stream counts required to enter specific chart positions.")
        
        # Using global raw_benchmarks
        if not raw_benchmarks.empty:
            # Row for filters
            f_col1, f_col2 = st.columns([1, 1.2])
            with f_col1:
                rank_threshold = st.selectbox(
                    "🎯 Select Chart Threshold",
                    options=[10, 20, 50, 100, 200],
                    index=3,
                    help="Select the chart position to analyze (e.g., Top 100)."
                )
            with f_col2:
                num_days = st.number_input(
                    "📅 Days to analyze (1 = Today)",
                    min_value=1,
                    max_value=30,
                    value=7,
                    help="1 means only today, 2 means today & yesterday, etc."
                )
            
            # Calculate benchmarks based on selection
            benchmarks_full = raw_benchmarks[raw_benchmarks["rank"] <= rank_threshold].groupby("chart_date").agg(
                min_streams_val=("streams", "min"),
                max_streams_val=("streams", "max"),
                avg_streams_val=("streams", "mean")
            ).reset_index().rename(columns={
                "min_streams_val": f"min_streams_top{rank_threshold}",
                "max_streams_val": f"max_streams_top{rank_threshold}",
                "avg_streams_val": f"avg_streams_top{rank_threshold}"
            })
            
            # 1. Custom Metric Cards (Today vs Yesterday)
            bench_sorted = benchmarks_full.sort_values("chart_date", ascending=False)
            if len(bench_sorted) >= 2:
                val_col = f"min_streams_top{rank_threshold}"
                today_val = bench_sorted.iloc[0][val_col]
                yesterday_val = bench_sorted.iloc[1][val_col]
                avg_val = bench_sorted.iloc[0][f"avg_streams_top{rank_threshold}"]
                max_val = bench_sorted.iloc[0][f"max_streams_top{rank_threshold}"]
                delta = today_val - yesterday_val
                
                delta_color = "#ff4b4b" if delta > 0 else "#22d3a0" # Red for harder barrier, Green for easier
                delta_icon = "↑" if delta > 0 else "↓"
                
                st.markdown(f"""
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 25px;">
                    <div style="background: rgba(79, 142, 247, 0.05); border: 1px solid rgba(79, 142, 247, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #4f8ef7; font-size: 0.85rem; font-weight: 600; margin-bottom: 8px;">TOP {rank_threshold} BARRIER</div>
                        <div style="font-size: 1.8rem; font-weight: 700; color: white;">{int(today_val):,}</div>
                        <div style="color: {delta_color}; font-size: 0.9rem; font-weight: 500; margin-top: 5px;">
                            {delta_icon} {abs(int(delta)):,} <span style="color: #a1a1a1; font-size: 0.8rem;">vs yesterday</span>
                        </div>
                    </div>
                    <div style="background: rgba(34, 211, 160, 0.05); border: 1px solid rgba(34, 211, 160, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #22d3a0; font-size: 0.85rem; font-weight: 600; margin-bottom: 8px;">AVG TOP {rank_threshold} STREAMS</div>
                        <div style="font-size: 1.8rem; font-weight: 700; color: white;">{int(avg_val):,}</div>
                        <div style="color: #a1a1a1; font-size: 0.8rem; margin-top: 5px;">Current Global Momentum</div>
                    </div>
                    <div style="background: rgba(161, 161, 161, 0.05); border: 1px solid rgba(161, 161, 161, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #a1a1a1; font-size: 0.85rem; font-weight: 600; margin-bottom: 8px;">GLOBAL #1 TRACK</div>
                        <div style="font-size: 1.8rem; font-weight: 700; color: white;">{int(max_val):,}</div>
                        <div style="color: #a1a1a1; font-size: 0.8rem; margin-top: 5px;">Peak Performance Benchmark</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                st.info(f"💡 Entry Barrier Analysis: To crack the Top {rank_threshold} today, a track needs at least **{int(today_val):,}** streams.")
            
            # Apply time range filter for charts
            benchmarks = benchmarks_full.sort_values("chart_date", ascending=False).head(int(num_days)).copy()
            
            # Horizontal Bar Chart
            benchmarks["date_str"] = benchmarks["chart_date"].dt.strftime("%d %b %Y")
            val_col = f"min_streams_top{rank_threshold}"
            
            fig_bench = px.bar(
                benchmarks,
                x=val_col,
                y="date_str",
                orientation="h",
                title=f"Ranking: Min Streams Top{rank_threshold}",
                color=val_col,
                color_continuous_scale="Blues",
                labels={val_col: "min_streams", "date_str": "chart_date"}
            )
            fig_bench.update_traces(
                hovertemplate="<b>%{y}</b><br>Min Streams: %{x:,.0f}<extra></extra>"
            )
            fig_bench.update_layout(
                yaxis={'categoryorder': 'total ascending'},
                coloraxis_showscale=False
            )
            style_figure(fig_bench, 500)
            st.plotly_chart(fig_bench, use_container_width=True, config=PLOTLY_CONFIG)
            
            # Secondary Charts: Trend analysis
            period_label = f"{int(num_days)} Day{'s' if num_days > 1 else ''}"
            st.markdown(f"#### 📈 Top {rank_threshold} Stream Trends ({period_label})")
            fig_trend = px.line(
                benchmarks.sort_values("chart_date"), 
                x="chart_date", 
                y=[f"min_streams_top{rank_threshold}", f"avg_streams_top{rank_threshold}"],
                markers=True,
                title=f"Min vs Avg Streams for Top {rank_threshold}",
                labels={"value": "Streams", "variable": "Metric", "chart_date": "Date"}
            )
            fig_trend.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            style_figure(fig_trend, 350)
            st.plotly_chart(fig_trend, use_container_width=True, config=PLOTLY_CONFIG)

            # Prepare a clean dataframe for display
            table_df = benchmarks[[
                "chart_date", 
                f"min_streams_top{rank_threshold}", 
                f"max_streams_top{rank_threshold}", 
                f"avg_streams_top{rank_threshold}"
            ]].copy()
            
            table_df.columns = ["Date", "Min Streams", "Max Streams", "Avg Streams"]
            table_df = table_df.dropna(subset=["Date"]).reset_index(drop=True)
            table_df["Date"] = table_df["Date"].dt.strftime("%d %b %Y")

            # 3. Custom Premium Data Table
            st.markdown(f"#### 📋 Top {rank_threshold} Market Benchmarks")
            st.caption(f"**Entry Barrier**: Min streams to enter Top {rank_threshold} | **Peak**: Global #1 track performance")
            
            # HTML for the data rows (No leading spaces to avoid markdown code block issues)
            rows_html = ""
            for _, row in table_df.iterrows():
                rows_html += f"<tr>" \
                             f"<td style='padding: 12px; font-style: italic; color: #a1a1a1;'>{row['Date']}</td>" \
                             f"<td style='padding: 12px; text-align: right; font-weight: 600; color: #4f8ef7;'>{int(row['Min Streams']):,}</td>" \
                             f"<td style='padding: 12px; text-align: right;'>{int(row['Max Streams']):,}</td>" \
                             f"<td style='padding: 12px; text-align: right; color: #22d3a0;'>{int(row['Avg Streams']):,}</td>" \
                             f"</tr>"
            
            table_html = f"""<div style="background: rgba(28, 32, 45, 0.4); border-radius: 12px; border: 1px solid rgba(151,163,197,0.1); padding: 10px; overflow-x: auto;">
<table style="width: 100%; border-collapse: collapse; color: white; font-family: 'Inter', sans-serif; font-size: 0.95rem;">
<thead>
<tr style="border-bottom: 2px solid rgba(151,163,197,0.2); font-weight: bold;">
<th style="padding: 12px; text-align: left; color: #a1a1a1;">📅 DATE</th>
<th style="padding: 12px; text-align: right; color: #4f8ef7;">📉 ENTRY BARRIER</th>
<th style="padding: 12px; text-align: right; color: #ffffff;">🚀 RANK #1 PEAK</th>
<th style="padding: 12px; text-align: right; color: #22d3a0;">📊 TOP {rank_threshold} AVG</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>"""
            st.markdown(table_html, unsafe_allow_html=True)
        else:
            st.warning("No benchmark data available. Please ensure the daily scraper is running.")
        
    elif active_tab == "💰 Acquisition":
        st.markdown("### 💰 Acquisition & Growth Intelligence")
        
        # 0. Integrated Artist Search for this tab
        artist_options = ["All artists"] + sorted(leaderboard["name"].dropna().unique().tolist())
        
        # Try to sync with global if possible, but allow local override
        default_idx = 0
        global_sel = st.session_state.get("global_selected_artist", "All artists")
        if global_sel in artist_options:
            default_idx = artist_options.index(global_sel)
            
        selected_artist = st.selectbox(
            "🔍 Search & Analyze Specific Artist",
            options=artist_options,
            index=default_idx,
            key="acq_tab_search",
            help="Select an artist to view deep streaming trajectory, weekly analysis, and Top 100 tracks."
        )
        
        # Sync back to global if user changes it here
        if selected_artist != st.session_state.get("global_selected_artist"):
            st.session_state.global_selected_artist = selected_artist
            st.rerun()
            
        st.info("Analyzing how effectively artists are acquiring new fans and expanding into global markets.")
        
        # 1. Growth Velocity Summary
        if selected_artist == "All artists":
            st.markdown("#### 🚀 Global Growth Velocity")
            # Calculate daily change in points for top artists
            if not history.empty:
                # Get latest and previous snapshot dates
                dates = sorted(history["scraped_at"].unique())
                if len(dates) >= 2:
                    latest_date = dates[-1]
                    prev_date = dates[-2]
                    
                    latest_snap = history[history["scraped_at"] == latest_date]
                    prev_snap = history[history["scraped_at"] == prev_date]
                    
                    growth_df = latest_snap.merge(
                        prev_snap[["name", "total_points", "num_countries"]], 
                        on="name", 
                        suffixes=("_now", "_prev")
                    )
                    growth_df["points_delta"] = growth_df["total_points_now"] - growth_df["total_points_prev"]
                    growth_df["country_delta"] = growth_df["num_countries_now"] - growth_df["num_countries_prev"]
                    
                    top_growers = growth_df.sort_values("points_delta", ascending=False).head(10)
                    
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        fig_growers = px.bar(
                            top_growers,
                            x="points_delta",
                            y="name",
                            orientation="h",
                            title="Top 10 Points Gainers (Last 24h)",
                            color="points_delta",
                            color_continuous_scale="Viridis",
                            labels={"points_delta": "Points Gained", "name": "Artist"}
                        )
                        style_figure(fig_growers, 400)
                        st.plotly_chart(fig_growers, use_container_width=True, config=PLOTLY_CONFIG)
                    
                    with c2:
                        st.markdown("#### 🌍 Market Expansion")
                        new_markets = growth_df[growth_df["country_delta"] > 0].sort_values("country_delta", ascending=False)
                        if not new_markets.empty:
                            st.success(f"**{len(new_markets)}** artists acquired new countries!")
                            for _, m_row in new_markets.head(5).iterrows():
                                st.markdown(f"**{m_row['name']}**: +{int(m_row['country_delta'])} countries")
                        else:
                            st.write("No new market acquisitions detected in the last snapshot.")
                else:
                    st.warning("Insufficient historical data to calculate growth velocity.")
            
            st.divider()
        
        else:
            # Artist-specific Acquisition
            st.markdown(f"#### 👤 {selected_artist}: Deep Acquisition Profile")
            
            # Filter Controls - Compact
            f_col1, f_col2 = st.columns([1, 1])
            with f_col1:
                time_grain = st.radio("📊 View By", ["Day", "Week"], horizontal=True, key="acq_time_grain", label_visibility="collapsed")
            with f_col2:
                lookback_days = st.selectbox("📅 Timeframe", [7, 14, 30, 60, 90, 180, 365, 730], index=2, format_func=lambda x: f"Last {x} Days", key="acq_deep_lookback", label_visibility="collapsed")
            
            # Fetch deep data
            deep_data = get_artist_deep_analysis(selected_artist)
            artist_history = history[history["name"] == selected_artist]
            
            if not deep_data["trajectory"].empty:
                # Apply lookback filter with robust timezone handling
                def to_naive(ts):
                    if hasattr(ts, 'tz_localize'):
                        return ts.tz_localize(None)
                    return pd.to_datetime(ts).replace(tzinfo=None)

                latest_date = to_naive(deep_data["trajectory"]["date"].max())
                cutoff_date = latest_date - pd.Timedelta(days=lookback_days)
                
                # Normalize data columns
                deep_data["trajectory"]["date"] = pd.to_datetime(deep_data["trajectory"]["date"]).dt.tz_localize(None)
                if not deep_data["weekly_summary"].empty:
                    deep_data["weekly_summary"]["week"] = pd.to_datetime(deep_data["weekly_summary"]["week"]).dt.tz_localize(None)
                
                filtered_trajectory = deep_data["trajectory"][deep_data["trajectory"]["date"] >= cutoff_date]
                filtered_weekly = deep_data["weekly_summary"][deep_data["weekly_summary"]["week"] >= cutoff_date] if not deep_data["weekly_summary"].empty else pd.DataFrame()
                
                # 1. Premium Metrics Row
                m_c1, m_c2, m_c3, m_c4 = st.columns(4)
                
                total_streams = deep_data["trajectory"]["total_daily_streams"].sum()
                total_tracks = len(deep_data["top_100_tracks"])
                best_rank = deep_data["trajectory"]["best_rank_that_day"].min()
                
                m_c1.metric("Total Streams (DB)", fmt_short(total_streams))
                m_c2.metric("Top 100 Tracks", f"{total_tracks}")
                m_c3.metric("Peak Global Rank", f"#{int(best_rank)}" if pd.notna(best_rank) else "N/A")
                
                # Calculation for weekly growth
                if not deep_data["weekly_summary"].empty and len(deep_data["weekly_summary"]) >= 2:
                    current_w = deep_data["weekly_summary"].iloc[0]["weekly_streams"]
                    prev_w = deep_data["weekly_summary"].iloc[1]["weekly_streams"]
                    w_growth = ((current_w - prev_w) / prev_w * 100) if prev_w > 0 else 0
                    m_c4.metric("Weekly Stream Growth", f"{w_growth:.1f}%", delta=f"{w_growth:.1f}%")
                else:
                    m_c4.metric("Weekly Stream Growth", "N/A")
                
                st.divider()
                
                # 2. Charts Row
                chart_col1, chart_col2 = st.columns([2, 1])
                
                with chart_col1:
                    if time_grain == "Day":
                        st.markdown(f"##### 📈 Daily Streaming Trajectory (Last {lookback_days}d)")
                        if not filtered_trajectory.empty:
                            fig_traj = px.area(
                                filtered_trajectory,
                                x="date",
                                y="total_daily_streams",
                                title=f"Daily Aggregated Streams for {selected_artist}",
                                color_discrete_sequence=["#22d3a0"]
                            )
                            style_figure(fig_traj, 350)
                            st.plotly_chart(fig_traj, use_container_width=True, config=PLOTLY_CONFIG)
                        else:
                            st.info("No daily data available for this timeframe.")
                    else:
                        st.markdown(f"##### 📈 Weekly Streaming Trajectory (Last {lookback_days}d)")
                        if not filtered_weekly.empty:
                            fig_traj = px.bar(
                                filtered_weekly,
                                x="week",
                                y="weekly_streams",
                                title=f"Weekly Aggregated Streams for {selected_artist}",
                                color_discrete_sequence=["#4f8ef7"]
                            )
                            style_figure(fig_traj, 350)
                            st.plotly_chart(fig_traj, use_container_width=True, config=PLOTLY_CONFIG)
                        else:
                            st.info("No weekly data available for this timeframe.")
                
                with chart_col2:
                    # Summary Table based on grain
                    st.markdown(f"##### 🗓️ {time_grain}ly Performance")
                    if time_grain == "Day":
                        if not filtered_trajectory.empty:
                            day_df = filtered_trajectory.sort_values("date", ascending=False).copy()
                            day_df["date"] = day_df["date"].dt.strftime("%d %b %Y")
                            st.dataframe(
                                day_df,
                                column_config={
                                    "date": "Date",
                                    "total_daily_streams": st.column_config.NumberColumn("Streams", format="%d"),
                                    "best_rank_that_day": "Peak Rank"
                                },
                                hide_index=True,
                                use_container_width=True,
                                height=350
                            )
                    else:
                        if not filtered_weekly.empty:
                            weekly_df = filtered_weekly.sort_values("week", ascending=False).copy()
                            weekly_df["week"] = weekly_df["week"].dt.strftime("%d %b %Y")
                            st.dataframe(
                                weekly_df,
                                column_config={
                                    "week": "Week Starting",
                                    "weekly_streams": st.column_config.NumberColumn("Streams", format="%d"),
                                    "active_tracks": "Tracks"
                                },
                                hide_index=True,
                                use_container_width=True,
                                height=350
                            )
                
                # 3. Top 100 Tracks List
                st.markdown("##### 🎶 Tracks in Global Top 100")
                if not deep_data["top_100_tracks"].empty:
                    st.dataframe(
                        deep_data["top_100_tracks"],
                        column_config={
                            "artist_title": "Track Name",
                            "peak_rank": "Peak Rank",
                            "peak_daily_streams": st.column_config.NumberColumn("Peak Daily", format="%d"),
                            "lifetime_streams": st.column_config.NumberColumn("Total Streams", format="%d"),
                            "days_on_chart": "Days"
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("No tracks found in the Top 100 for this artist yet.")
                
                # 4. ROI & Efficiency Metrics (Existing)
                st.markdown("#### 📊 Market Efficiency & Longevity")
                if selected_artist in leaderboard["name"].values:
                    row = leaderboard[leaderboard["name"] == selected_artist].iloc[0]
                    
                    e_c1, e_c2, e_c3, e_c4 = st.columns(4)
                    
                    # Efficiency: Points per 1M Listeners
                    efficiency = (row['total_points'] / (row['monthly_listeners'] / 1_000_000)) if pd.notna(row['monthly_listeners']) and row['monthly_listeners'] > 0 else 0
                    e_c1.metric("Fan Efficiency", f"{efficiency:.1f}", help="Points generated per 1 million listeners.")
                    
                    # Market Penetration
                    penetration = row.get('num_countries', 0)
                    e_c2.metric("Market Reach", f"{penetration} countries")
                    
                    # Best Rank Achieved (from longevity)
                    best_ever = row.get('best_rank', row['rank'])
                    e_c3.metric("Peak Career Rank", f"#{int(best_ever)}")
                    
                    # Longevity
                    weeks = row.get('weeks_on_chart', 1)
                    e_c4.metric("Chart Longevity", f"{int(weeks)} weeks")
                    
                    st.markdown(
                        f"""
                        <div style='background: rgba(79, 142, 247, 0.1); border: 1px solid rgba(79, 142, 247, 0.2); border-radius: 12px; padding: 20px; margin-top: 15px;'>
                            <div style='font-weight: 600; color: #4f8ef7; margin-bottom: 10px;'>💡 Acquisition Insight</div>
                            <div style='color: white; font-size: 0.95rem;'>
                                {selected_artist} has successfully charted <b>{total_tracks}</b> tracks in the Global Top 100. 
                                With a current efficiency score of <b>{efficiency:.1f}</b>, the artist shows 
                                <b>{'strong' if total_tracks > 5 else 'emerging'}</b> market penetration.
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            
            elif not artist_history.empty:
                # Fallback to simple charts if deep data is missing
                st.warning("Detailed streaming analysis for this artist is currently being indexed. Showing point trends instead.")
                a_c1, a_c2 = st.columns(2)
                with a_c1:
                    # Format dates for readability
                    fig_market = px.line(artist_history, x="scraped_at", y="num_countries", title="Market Footprint")
                    fig_market.update_xaxes(tickformat="%d %b\n%H:%M")
                    style_figure(fig_market, 300); st.plotly_chart(fig_market, use_container_width=True)
                with a_c2:
                    fig_points = px.area(artist_history, x="scraped_at", y="total_points", title="Points Trend")
                    fig_points.update_xaxes(tickformat="%d %b\n%H:%M")
                    style_figure(fig_points, 300); st.plotly_chart(fig_points, use_container_width=True)
            else:
                st.warning(f"No acquisition data found for {selected_artist}. Please ensure the artist is in the current Top 100.")

        st.divider()
        
        # 4. 🛒 Quick Acquisition List
        st.markdown("#### 🛒 Quick Acquisition Opportunities")
        
        # Add Day Filter
        lookback_days = st.selectbox(
            "📅 Analyze Growth Over",
            options=[1, 7, 14, 30],
            format_func=lambda x: f"Last {x} Day{'s' if x > 1 else ''}",
            index=0,
            help="Compare current performance with data from N days ago to identify growth trends."
        )
        
        st.caption(f"Direct list of trending artists sorted by {lookback_days}d point accumulation for rapid decision-making.")
        
        # Logic to find the snapshot from N days ago
        if not history.empty:
            h_dates = sorted(history["scraped_at"].unique())
            latest_d = h_dates[-1]
            target_date = latest_d - pd.Timedelta(days=lookback_days)
            past_dates = [d for d in h_dates if d <= target_date]
            
            if not past_dates:
                prev_d = h_dates[0]
                actual_days = (latest_d - prev_d).days
            else:
                prev_d = past_dates[-1]
                actual_days = (latest_d - prev_d).days

            # IMPORTANT: Use leaderboard as base to get ALL current artists
            prev_h = history[history["scraped_at"] == prev_d]
            
            # Merge leaderboard with historical snapshot
            acq_df = leaderboard.merge(
                prev_h[["name", "total_points", "rank"]], 
                on="name", 
                how="left",
                suffixes=("", "_prev")
            )
            
            # Fill NaN for new entries
            acq_df["total_points_prev"] = acq_df["total_points_prev"].fillna(0)
            acq_df["monthly_listeners"] = acq_df["monthly_listeners"].fillna(0)
            acq_df["rank"] = acq_df["rank"].fillna(0)
            acq_df["pts_delta"] = acq_df["total_points"] - acq_df["total_points_prev"]
            
            # Sort by growth - showing ALL
            acq_list = acq_df.sort_values("pts_delta", ascending=False)
            
            # HTML for the data rows
            # HTML for the data rows - COMPACT & LEFT-ALIGNED
            acq_rows_html = ""
            for _, a_row in acq_list.iterrows():
                color = "#22d3a0" if a_row['pts_delta'] > 0 else "#ff4b4b"
                icon = "▲" if a_row['pts_delta'] > 0 else "▼"
                ml = a_row['monthly_listeners']
                if ml >= 1_000_000: listeners = f"{ml/1_000_000:.1f}M"
                elif ml > 0: listeners = f"{int(ml/1000)}K"
                else: listeners = "---"
                
                acq_rows_html += f"<tr style='border-bottom: 1px solid rgba(151,163,197,0.08);'><td style='padding: 16px 12px; color: #6e7681; font-weight: 700; width: 80px;'>#{int(a_row['rank'])}</td><td style='padding: 16px 12px; font-weight: 600; color: #ffffff;'>{a_row['name']}</td><td style='padding: 16px 12px; color: #4f8ef7; font-weight: 600;'>{listeners}</td><td style='padding: 16px 12px; text-align: right; color: {color}; font-weight: 700;'><span style='margin-right: 4px;'>{icon}</span>{int(a_row['pts_delta']):,} pts</td></tr>"
            
            # Full Table - COMPACT & LEFT-ALIGNED
            acq_table_html = f"<div style='height: 600px; overflow-y: auto; border: 1px solid rgba(151,163,197,0.15); border-radius: 16px; background: #0d1117;'><table style='width: 100%; border-collapse: collapse; font-family: sans-serif;'><thead style='position: sticky; top: 0; background: #161b22; z-index: 10; border-bottom: 2px solid rgba(151,163,197,0.2);'><tr><th style='padding: 18px 12px; text-align: left; color: #8b949e; font-size: 0.75rem; text-transform: uppercase;'>Rank</th><th style='padding: 18px 12px; text-align: left; color: #8b949e; font-size: 0.75rem; text-transform: uppercase;'>Artist</th><th style='padding: 18px 12px; text-align: left; color: #8b949e; font-size: 0.75rem; text-transform: uppercase;'>Listeners</th><th style='padding: 18px 12px; text-align: right; color: #8b949e; font-size: 0.75rem; text-transform: uppercase;'>Growth ({actual_days}d)</th></tr></thead><tbody>{acq_rows_html}</tbody></table></div>"
            
            st.markdown(acq_table_html, unsafe_allow_html=True)
        else:
            st.warning("Historical data snapshots are currently unavailable. Please check back later.")


# Define app pages after functions are defined
app_pages = [
    st.Page(
        show_leaderboard_page,
        title="Leaderboard",
        icon=":material/trending_up:",
        url_path="leaderboard",
        default=True,
    ),
    st.Page(
        show_debut_artist_page,
        title="Artist Spotlight",
        icon=":material/artist:",
        url_path="artist-spotlight",
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
        show_ai_analyst_page,
        title="AI Data Analyst",
        icon=":material/smart_toy:",
        url_path="ai-data-analyst",
    ),
    st.Page(
        show_artist_analysis_page,
        title="Artist Analysis",
        icon=":material/analytics:",
        url_path="artist-analysis",
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
    
    # Handle page redirection requests
    if st.session_state.get("redirect_to_page"):
        target_page_title = st.session_state.pop("redirect_to_page")
        for pg in app_pages:
            if getattr(pg, "title", "") == target_page_title:
                st.switch_page(pg)
    
    # Collapsible advanced settings
    with st.expander("🔍 Search & Filter", expanded=True):
        artist_rank_sorted = leaderboard.sort_values("rank")["name"].dropna().unique().tolist()
        artist_options = ["All artists"] + [str(a) for a in artist_rank_sorted]
        
        # Initialize session state if not present
        if "global_selected_artist" not in st.session_state:
            st.session_state.global_selected_artist = "All artists"
            
        try:
            current_idx = artist_options.index(st.session_state.global_selected_artist)
        except ValueError:
            current_idx = 0
            
        selected_artist = st.selectbox(
            "🎤 Artist search", 
            artist_options, 
            index=current_idx,
            key="sidebar_artist_search"
        )
        
        # Update global state
        if selected_artist != st.session_state.global_selected_artist:
            st.session_state.global_selected_artist = selected_artist
            st.rerun()
        latam_only = st.toggle("🌎 Latin America", value=True)
        
        selected_countries = []
        if latam_only:
            default_countries = sorted([c for c in leaderboard["display_country"].unique().tolist() if c != "—"])
            selected_countries = st.multiselect(
                "📍 Countries",
                default_countries or LATAM_COUNTRIES,
                default=default_countries or LATAM_COUNTRIES[:6],
            )

    
    with st.expander("🎛️ Display Options", expanded=True):
        max_rows = st.slider("📊 Table rows", min_value=10, max_value=300, value=15, step=5)
    
    # Apply global filters (Latam, Countries)
    global_filtered = leaderboard.copy()
    if latam_only:
        global_filtered = global_filtered[global_filtered["latam_signal"]]
        if selected_countries:
            global_filtered = global_filtered[global_filtered["display_country"].isin(selected_countries)]
    
    # Apply artist filter for appropriate views (Leaderboard list)
    filtered = global_filtered.copy()
    if selected_artist != "All artists":
        filtered = filtered[filtered["name"] == selected_artist]
    filtered = filtered.sort_values("rank")
    
    
    # Status indicator
    status_color = "status-good" if len(runs) > 0 else "muted"
    st.markdown(f"<span class='{status_color}'>● Pipeline: {'Healthy' if len(runs) > 0 else 'Unknown'}</span>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Last run: {last_run_label}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Updated: {pd.Timestamp.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
    

current_page.run()
if getattr(current_page, "title", "") != "AI Data Analyst":
    render_footer()

# Auto-refresh functionality
if st.session_state.auto_refresh:
    import time
    time.sleep(30)
    st.rerun()
