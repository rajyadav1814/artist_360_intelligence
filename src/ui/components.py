import streamlit as st
import pandas as pd
from html import escape

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

def render_chatbot_widget() -> None:
    BOT_SRC = "https://copilotstudio.microsoft.com/environments/4b079cee-b5d6-e253-856d-c427359af206/bots/cr917_agentT1zDET/webchat?__version__=2"
    st.markdown(
        f"""
        <style>
            #chatbot-btn {{
                position: fixed; bottom: 20px; right: 20px; width: 60px; height: 60px;
                background: linear-gradient(135deg, #4f8ef7, #7c5cfc);
                border-radius: 50%; display: flex; align-items: center; justify-content: center;
                box-shadow: 0 10px 25px rgba(79,142,247,0.4); cursor: pointer; z-index: 9999;
                transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); color: white; font-size: 24px;
            }}
            #chatbot-btn:hover {{ transform: scale(1.1) rotate(5deg); }}
            #chatbot-container {{
                position: fixed; bottom: 90px; right: 20px; width: 380px; height: 500px;
                background: white; border-radius: 16px; box-shadow: 0 15px 45px rgba(0,0,0,0.3);
                z-index: 9998; overflow: hidden; display: none; border: 1px solid rgba(0,0,0,0.1);
                animation: fadeIn 0.3s ease;
            }}
        </style>
        <div id="chatbot-btn" onclick="toggleChat()">🤖</div>
        <div id="chatbot-container">
            <iframe src="{BOT_SRC}" frameborder="0" style="width: 100%; height: 100%;"></iframe>
        </div>
        <script>
            function toggleChat() {{
                var container = document.getElementById('chatbot-container');
                if (container.style.display === 'none' || container.style.display === '') {{
                    container.style.display = 'block';
                }} else {{
                    container.style.display = 'none';
                }}
            }}
        </script>
        """,
        unsafe_allow_html=True,
    )
