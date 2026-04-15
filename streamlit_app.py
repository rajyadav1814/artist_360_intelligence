from __future__ import annotations
import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src.scrapers.artist_details_scraper import LATIN_AMERICAN_COUNTRIES
from skeleton import render_dashboard_skeleton
from src.ui.styles import apply_theme
from src.ui.components import render_header, render_footer, render_chatbot_widget
from src.ui.pages.leaderboard import render_leaderboard
from src.ui.pages.chart_tracker import render_chart_tracker
from src.ui.pages.stream_trends import render_stream_trends
from src.ui.pages.debut_artist import render_debut_artist_chart
from src.ui.pages.ops_monitor import render_ops_monitor
from src.data_loader import load_dashboard_data
from src.ui.utils import LATAM_COUNTRIES

# 1. Page Configuration
st.set_page_config(
    page_title="Artist 360 Intelligence",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Session State Initialization
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False
if "comparison_mode" not in st.session_state:
    st.session_state.comparison_mode = False
if "leaderboard_view" not in st.session_state:
    st.session_state.leaderboard_view = "📋 Table"

# 3. Apply Theme
apply_theme()

# 4. Global Constants
PAGE_META = {
    "Leaderboard": (
        "Artist 360 Leaderboard",
        "Top Latin artists ranked by iTunes performance, Spotify reach, and global footprint",
    ),
    "Debut Artist": (
        "Debut Artist",
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
    "Ops Monitor": (
        "Ops Monitor",
        "Operational telemetry and data pipeline health monitoring",
    ),
}

# 5. Data Loading
data = load_dashboard_data()
leaderboard = data["leaderboard"]
runs = data["runs"]
history = data["history"]
top_history = data["top_history"]

# Prepare last run label
if not runs.empty:
    last_run = runs.iloc[0]
    finished = last_run["finished_at"]
    if pd.isna(finished):
        last_run_label = "In progress..."
    else:
        last_run_label = finished.strftime("%b %d, %H:%M")
else:
    last_run_label = "Never"

# 6. Sidebar Logic (Filters & Navigation)
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
    
    # Page-independent Filters
    with st.expander("🔍 Search & Filter", expanded=True):
        artist_rank_sorted = leaderboard.sort_values("rank")["name"].dropna().unique().tolist()
        artist_options = ["All artists"] + [str(a) for a in artist_rank_sorted]
        selected_artist = st.selectbox("🎤 Artist search", artist_options, index=0)
        
        latam_only = st.toggle("🌎 Latin America", value=True)
        
        default_countries = sorted([c for c in leaderboard["display_country"].unique().tolist() if c != "—"])
        selected_countries = st.multiselect(
            "📍 Countries",
            default_countries or LATAM_COUNTRIES,
            default=default_countries or LATAM_COUNTRIES[:6],
        )

    with st.expander("🎛️ Display Options", expanded=True):
        max_rows = st.slider("📊 Table rows", min_value=10, max_value=300, value=15, step=5)
    
    # Action buttons
    st.markdown("### 🔄 Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    auto_refresh_sidebar = st.toggle("⏱️ Auto-refresh (30s)", value=st.session_state.auto_refresh)
    if auto_refresh_sidebar != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_refresh_sidebar
    
    # Status indicator
    status_color = "status-good" if not runs.empty else "muted"
    st.markdown(f"<span class='{status_color}'>● Pipeline: {'Healthy' if not runs.empty else 'Unknown'}</span>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Last run: {last_run_label}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Updated: {pd.Timestamp.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

# 7. Filtering Data
filtered = leaderboard.copy()
if latam_only:
    filtered = filtered[filtered["latam_signal"]]
if selected_countries:
    filtered = filtered[filtered["display_country"].isin(selected_countries)]
if selected_artist != "All artists":
    filtered = filtered[filtered["name"] == selected_artist]
filtered = filtered.sort_values("rank")

# 8. Page Wrappers
def show_leaderboard_page():
    page_title, page_meta = PAGE_META["Leaderboard"]
    render_header(page_title, page_meta, last_run_label)
    render_leaderboard(filtered, runs, max_rows=max_rows)

def show_chart_tracker_page():
    page_title, page_meta = PAGE_META["Chart Tracker"]
    render_header(page_title, page_meta, last_run_label)
    render_chart_tracker(history, filtered)

def show_stream_trends_page():
    page_title, page_meta = PAGE_META["Stream Trends"]
    render_header(page_title, page_meta, last_run_label)
    render_stream_trends(filtered, top_history, history)

def show_debut_artist_page():
    page_title, page_meta = PAGE_META["Debut Artist"]
    render_header(page_title, page_meta, last_run_label)
    render_debut_artist_chart(filtered)

def show_ops_monitor_page():
    page_title, page_meta = PAGE_META["Ops Monitor"]
    render_header(page_title, page_meta, last_run_label)
    render_ops_monitor(runs)

# 9. Navigation Setup
app_pages = [
    st.Page(show_leaderboard_page, title="Leaderboard", icon=":material/trending_up:", url_path="leaderboard", default=True),
    st.Page(show_debut_artist_page, title="Debut Artist", icon=":material/artist:", url_path="debut-artist"),
    st.Page(show_chart_tracker_page, title="Chart Tracker", icon=":material/desktop_windows:", url_path="chart-tracker"),
    st.Page(show_stream_trends_page, title="Stream Trends", icon=":material/show_chart:", url_path="stream-trends"),
    st.Page(show_ops_monitor_page, title="Ops Monitor", icon=":material/tune:", url_path="ops-monitor"),
]

# 10. Router execution
current_page = st.navigation(app_pages, position="sidebar", expanded=True)
current_page.run()

# 11. Global Components (Rendered on every page)
render_footer()
render_chatbot_widget()

# 12. Auto-refresh functionality
if st.session_state.auto_refresh:
    import time
    time.sleep(30)
    st.rerun()
