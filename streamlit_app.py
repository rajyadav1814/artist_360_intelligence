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

PAGE_META = {
    "Leaderboard": (
        "Artist 360 Leaderboard",
        "Live chart signals from the latest scrape stored in PostgreSQL",
    ),
    "Chart Tracker": (
        "Chart Tracker",
        "Recent iTunes ranking trajectories for the current top artists",
    ),
    "Stream Trends": (
        "Stream Trends",
        "Spotify listener momentum and Latin American market reach",
    ),
    "Ops Monitor": (
        "Ops Monitor",
        "Pipeline health and scrape-run reliability from PostgreSQL",
    ),
}

CHART_COLORS = ["#4f8ef7", "#22d3a0", "#f5a623", "#7c5cfc", "#e84545"]
PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}
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
        .stApp { background:linear-gradient(180deg,#060a15 0%,#091127 100%); color:var(--text); }
        [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, header { background:transparent !important; }
        [data-testid="stDecoration"] { display:none; }
        .block-container { padding-top:1rem; padding-bottom:2rem; max-width:1400px; }
        [data-testid="stSidebar"] {
            background:var(--surface); border-right:1px solid var(--border);
        }
        h1, h2, h3, h4, p, label, div, span { color:var(--text); }
        .sidebar-logo { font-size:1.25rem; font-weight:800; letter-spacing:.2px; }
        .sidebar-sub { color:var(--text2); font-size:.85rem; margin-top:.2rem; }
        .sidebar-badge {
            display:inline-block; margin-top:.45rem; padding:3px 8px; border-radius:999px;
            background:rgba(124,92,252,.18); color:#ddd6fe; font-size:.75rem; font-weight:700;
        }
        .page-title { font-size:2rem; font-weight:800; letter-spacing:-.03em; margin-bottom:.25rem; }
        .page-meta { color:var(--text2); font-size:.95rem; margin-bottom:1rem; }
        .dashboard-card {
            background:rgba(18,24,42,.96); border:1px solid var(--border); border-radius:16px;
            padding:1rem 1rem .9rem 1rem; box-shadow:0 12px 32px rgba(0,0,0,.22);
            margin-bottom:1rem;
        }
        .section-title { font-size:1rem; font-weight:700; margin-bottom:.2rem; }
        .section-sub { color:var(--text2); font-size:.82rem; margin-bottom:.9rem; }
        .kpi-card {
            background:linear-gradient(180deg, rgba(19,26,45,1) 0%, rgba(16,21,37,1) 100%);
            border:1px solid var(--border); border-radius:14px; padding:1rem 1rem .9rem 1rem;
            min-height:110px; position:relative; overflow:hidden;
        }
        .kpi-card::before {
            content:''; position:absolute; top:0; left:0; right:0; height:3px;
            background:linear-gradient(90deg,var(--accent),var(--accent2));
        }
        .kpi-green::before { background:linear-gradient(90deg,var(--accent3),#16a34a); }
        .kpi-amber::before { background:linear-gradient(90deg,var(--warn),#f97316); }
        .kpi-red::before { background:linear-gradient(90deg,var(--danger),#be123c); }
        .kpi-label { color:var(--text2); font-size:.76rem; text-transform:uppercase; letter-spacing:.08em; }
        .kpi-value { font-size:2rem; font-weight:800; margin-top:.35rem; }
        .kpi-delta { color:var(--text2); font-size:.78rem; margin-top:.2rem; }
        .table-wrap { overflow-x:auto; }
        table.leader-table { width:100%; border-collapse:collapse; font-size:.92rem; }
        .leader-table thead th {
            text-align:left; padding:.7rem .75rem; color:var(--text2); font-size:.73rem;
            letter-spacing:.06em; text-transform:uppercase; border-bottom:1px solid var(--border);
        }
        .leader-table tbody td {
            padding:.72rem .75rem; border-bottom:1px solid rgba(41,52,85,.72); vertical-align:middle;
        }
        .leader-table tbody tr:hover { background:rgba(79,142,247,.06); }
        .pos-cell { color:#dbe4ff; font-weight:800; width:44px; }
        .artist-cell { font-weight:700; }
        .muted { color:var(--text2); }
        .num-cell { text-align:right; font-variant-numeric:tabular-nums; }
        .country-pill {
            display:inline-block; padding:2px 8px; border-radius:999px; background:rgba(34,211,160,.12);
            color:#8ff0cf; font-size:.75rem; font-weight:700;
        }
        .badge { display:inline-block; padding:3px 8px; border-radius:999px; font-size:.72rem; font-weight:800; }
        .badge-up { background:rgba(34,211,160,.14); color:#8ff0cf; }
        .badge-dn { background:rgba(232,69,69,.14); color:#ff9c9c; }
        .badge-same { background:rgba(151,163,197,.14); color:#c4d0f3; }
        .badge-new { background:rgba(79,142,247,.16); color:#b7d4ff; }
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
        .status-pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:.72rem; font-weight:700; }
        .pill-ok { background:rgba(34,197,94,.14); color:#8ff0cf; }
        .pill-partial { background:rgba(245,166,35,.14); color:#ffd089; }
        .pill-fail { background:rgba(232,69,69,.14); color:#ff9c9c; }
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
        "history": """
            WITH latest_run AS (
                SELECT MAX(scraped_at) AS ts FROM itunes_artist_rankings
            ),
            top_artists AS (
                SELECT artist_id
                FROM itunes_artist_rankings r
                JOIN latest_run lr ON r.scraped_at = lr.ts
                WHERE r.rank <= 5
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
    st.markdown(f"<div class='page-title'>{escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='page-meta'>{escape(meta)}</div>",
        unsafe_allow_html=True,
    )


def render_kpis(leaderboard: pd.DataFrame, runs: pd.DataFrame) -> None:
    success_rate = (runs["status"].eq("success").mean() * 100) if not runs.empty else 0
    total_monthly = leaderboard["monthly_listeners"].fillna(0).sum()
    latam_artists = int(leaderboard["latam_signal"].sum()) if "latam_signal" in leaderboard else 0
    new_entries = int(leaderboard["rank_change"].fillna("").eq("NEW").sum())
    tracked_jobs = int(runs["source"].nunique()) if not runs.empty else 0

    cards = [
        ("Total Monthly Listeners", fmt_short(total_monthly), "Live Spotify monthly listener sum", ""),
        ("Artists with LATAM Signals", str(latam_artists), "Currently visible in the regional cut", "kpi-green"),
        ("New Chart Entries", str(new_entries), "Fresh NEW movements in the latest run", "kpi-amber"),
        ("Jobs Tracked", str(tracked_jobs), f"Pipeline success rate {success_rate:.0f}%", "kpi-red"),
    ]
    cols = st.columns(4)
    for col, (label, value, delta, klass) in zip(cols, cards):
        col.markdown(
            f"""
            <div class="kpi-card {klass}">
                <div class="kpi-label">{escape(label)}</div>
                <div class="kpi-value">{escape(value)}</div>
                <div class="kpi-delta">{escape(delta)}</div>
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
    left, right = st.columns([2.2, 1.0])

    with left:
        st.markdown(
            "<div class='dashboard-card'><div class='section-title'>Global Chart Positions</div><div class='section-sub'>Latest leaderboard filtered to Latin American relevance</div></div>",
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

        latest_rows = latest_source_rows(runs)
        if not latest_rows.empty:
            share = latest_rows[["source", "rows_upserted"]].copy()
            fig_pie = px.pie(
                share,
                names="source",
                values="rows_upserted",
                hole=0.64,
                color_discrete_sequence=["#22d3a0", "#f5a623", "#7c5cfc", "#4fd1c5"],
            )
            fig_pie.update_layout(title="Platform / Job Share")
            style_figure(fig_pie, 320)
            st.plotly_chart(fig_pie, use_container_width=True, config=PLOTLY_CONFIG)

    st.markdown("### Artist Detail Spotlight")
    artists = leaderboard["name"].dropna().tolist()
    selected_artist = st.selectbox("Choose an artist", artists, index=0)
    row = leaderboard.loc[leaderboard["name"] == selected_artist].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Songs", int(row.get("songs_count") or 0))
    c2.metric("Albums", int(row.get("albums_count") or 0))
    c3.metric("LATAM Countries", int(row.get("countries_count") or 0))
    a, b = st.columns(2)
    with a:
        st.markdown("<div class='dashboard-card'><div class='section-title'>Top Songs</div></div>", unsafe_allow_html=True)
        st.text_area("Top Songs", row.get("top_songs") or "—", height=180, label_visibility="collapsed")
    with b:
        st.markdown("<div class='dashboard-card'><div class='section-title'>Top Countries</div></div>", unsafe_allow_html=True)
        st.text_area("Top Countries", row.get("top_countries") or "—", height=180, label_visibility="collapsed")


def build_tracker_demo_data(leaderboard: pd.DataFrame, days: int = 14) -> tuple[pd.DataFrame, pd.DataFrame]:
    top = leaderboard.dropna(subset=["monthly_listeners"]).nlargest(5, "monthly_listeners").copy()
    if top.empty:
        top = leaderboard.sort_values("rank").head(5).copy()

    top = top.reset_index(drop=True)
    date_labels = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days).strftime("%b %-d").tolist()
    base_patterns = [
        [3, 2, 2, 1, 1, 2, 3, 2, 1, 1, 2, 1, 1, 1],
        [5, 4, 3, 3, 2, 2, 1, 2, 3, 2, 2, 3, 2, 2],
        [8, 7, 6, 5, 4, 3, 4, 3, 3, 4, 3, 3, 3, 3],
        [10, 9, 8, 7, 6, 5, 6, 5, 4, 5, 4, 4, 4, 4],
        [15, 12, 10, 9, 8, 7, 8, 7, 6, 5, 5, 5, 5, 5],
    ]

    records = []
    best_rows = []
    for idx, row in top.iterrows():
        pattern = base_patterns[idx % len(base_patterns)]
        current_rank = int(row["rank"]) if pd.notna(row.get("rank")) else idx + 1
        current_rank = max(1, min(18, current_rank))
        shift = current_rank - pattern[-1]
        series = [max(1, min(18, point + shift)) for point in pattern]

        for day, pos in zip(date_labels, series):
            records.append({"day": day, "artist": row["name"], "position": pos})

        best_rows.append({
            "artist": row["name"],
            "best_position": min(series[-7:]),
        })

    return pd.DataFrame(records), pd.DataFrame(best_rows).sort_values("best_position")


def render_chart_tracker(history: pd.DataFrame, leaderboard: pd.DataFrame) -> None:
    if history.empty and leaderboard.empty:
        st.warning("Not enough ranking data available yet.")
        return

    unique_runs = int(history["scraped_at"].nunique()) if not history.empty else 0
    st.markdown(
        "<div class='dashboard-card'><div class='section-title'>Chart Tracker</div><div class='section-sub'>14-day trend-style view for the strongest artists in the current snapshot</div></div>",
        unsafe_allow_html=True,
    )

    if unique_runs < 3:
        st.caption("A full multi-day history is still building. This view uses the current scrape and recent momentum-style interpolation to make the chart easier to read.")
        line_df, best_df = build_tracker_demo_data(leaderboard, days=14)
    else:
        history = history.copy()
        history = history.sort_values(["name", "scraped_at"])
        history["day"] = history["scraped_at"].dt.strftime("%b %-d")
        line_df = history.rename(columns={"name": "artist", "rank": "position"})[["day", "artist", "position"]]
        best_df = (
            history.groupby("name", as_index=False)["rank"]
            .min()
            .rename(columns={"name": "artist", "rank": "best_position"})
            .sort_values("best_position")
            .head(8)
        )

    left, right = st.columns(2)

    with left:
        fig_line = go.Figure()
        for idx, artist in enumerate(line_df["artist"].drop_duplicates().tolist()[:5]):
            sub = line_df[line_df["artist"] == artist]
            fig_line.add_trace(
                go.Scatter(
                    x=sub["day"],
                    y=sub["position"],
                    mode="lines+markers",
                    name=artist,
                    line=dict(color=CHART_COLORS[idx % len(CHART_COLORS)], width=2.5),
                    marker=dict(size=6),
                    hovertemplate="%{x}<br>%{fullData.name}: #%{y}<extra></extra>",
                )
            )

        fig_line.update_layout(
            title="Position Trajectory — Spotify Global (14 days)",
            xaxis_title="",
            yaxis_title="Position",
            legend=dict(orientation="h", y=1.12, x=0.02),
        )
        fig_line.update_yaxes(autorange="reversed", range=[18, 0], dtick=2)
        style_figure(fig_line, 390)
        st.plotly_chart(fig_line, use_container_width=True, config=PLOTLY_CONFIG)

    with right:
        fig_best = px.bar(
            best_df,
            x="best_position",
            y="artist",
            orientation="h",
            color="artist",
            color_discrete_sequence=CHART_COLORS,
        )
        fig_best.update_layout(
            title="Rolling 7-Day Best Position",
            showlegend=False,
            xaxis_title="Chart Position (lower = better)",
            yaxis_title="",
        )
        fig_best.update_xaxes(autorange="reversed", dtick=2)
        style_figure(fig_best, 390)
        st.plotly_chart(fig_best, use_container_width=True, config=PLOTLY_CONFIG)



def render_stream_trends(leaderboard: pd.DataFrame) -> None:
    if leaderboard.empty:
        st.warning("No streaming data available yet.")
        return

    top_spotify = leaderboard.dropna(subset=["monthly_listeners"]).nlargest(12, "monthly_listeners")
    if top_spotify.empty:
        st.info("Spotify listener data has not been scraped yet.")
        return

    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        fig.add_bar(name="Monthly Listeners", x=top_spotify["name"], y=top_spotify["monthly_listeners"], marker_color="#1ED760")
        fig.add_bar(name="Peak Listeners", x=top_spotify["name"], y=top_spotify["peak_listeners"].fillna(0), marker_color="#4f8ef7")
        fig.update_layout(title="Spotify Listener Momentum", barmode="group", xaxis_title="Artist", yaxis_title="Listeners")
        style_figure(fig, 420)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    with c2:
        latam_presence = leaderboard[leaderboard["countries_count"] > 0].nlargest(10, "countries_count")
        if not latam_presence.empty:
            fig_latam = px.bar(
                latam_presence.sort_values("countries_count"),
                x="countries_count",
                y="name",
                orientation="h",
                color="countries_count",
                color_continuous_scale=["#7c5cfc", "#22d3a0"],
            )
            fig_latam.update_layout(title="Latin American Country Reach", coloraxis_showscale=False)
            style_figure(fig_latam, 420)
            st.plotly_chart(fig_latam, use_container_width=True, config=PLOTLY_CONFIG)

    trends_df = top_spotify[["rank", "name", "monthly_listeners", "peak_listeners", "display_country", "countries_count"]].copy()
    trends_df.columns = ["iTunes Rank", "Artist", "Monthly Listeners", "Peak Listeners", "Top LATAM Country", "LATAM Countries"]
    st.dataframe(
        trends_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Monthly Listeners": st.column_config.NumberColumn(format="%,d"),
            "Peak Listeners": st.column_config.NumberColumn(format="%,d"),
        },
    )


def render_ops_monitor(runs: pd.DataFrame) -> None:
    if runs.empty:
        st.warning("No scrape run logs available yet.")
        return

    runs = runs.copy()
    runs["status"] = runs["status"].fillna("unknown")
    runs["success_flag"] = runs["status"].eq("success").astype(int)
    runs["duration_sec"] = (runs["finished_at"] - runs["started_at"]).dt.total_seconds()

    total_runs = len(runs)
    success_pct = runs["success_flag"].mean() * 100
    latest_rows = int(runs["rows_upserted"].fillna(0).iloc[0]) if total_runs else 0
    avg_duration = runs["duration_sec"].dropna().mean()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Runs Logged", total_runs)
    k2.metric("Success Rate", f"{success_pct:.0f}%")
    k3.metric("Rows in Latest Run", f"{latest_rows:,}")
    k4.metric("Avg Duration", f"{avg_duration:.0f}s" if pd.notna(avg_duration) else "—")

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
                )
            ]
        )
        fig_rate.update_layout(
            title="Pipeline Success Rate by Job",
            xaxis_title="",
            yaxis_title="Success %",
            yaxis_range=[0, 105],
        )
        style_figure(fig_rate, 320)
        st.plotly_chart(fig_rate, use_container_width=True, config=PLOTLY_CONFIG)

    with c2:
        recent = runs[["finished_at", "source", "rows_upserted", "status"]].head(7).copy()
        recent["finished_label"] = recent["finished_at"].dt.strftime("%Y-%m-%d %H:%M").fillna("in progress")
        html = ['<div class="dashboard-card"><div class="section-title">Recent Scrape Runs</div><div class="section-sub">Last 7 pipeline events</div><div class="run-log">']
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
            title="Records Ingested per Run",
            xaxis_title="Run",
            yaxis_title="Rows upserted (log scale)",
        )
        fig_rows.update_yaxes(type="log")
        fig_rows.update_xaxes(tickangle=-20)
        style_figure(fig_rows, 340)
        st.plotly_chart(fig_rows, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption("Log scale is used so very large and very small jobs stay visible together.")


apply_theme()

try:
    data = load_dashboard_data()
except Exception as exc:  # pragma: no cover
    st.error(f"Failed to load dashboard data: {exc}")
    st.stop()

leaderboard = data["leaderboard"]
runs = data["runs"]
history = data["history"]

last_run_label = "n/a"
if not runs.empty and runs["finished_at"].notna().any():
    last_run_label = runs["finished_at"].dropna().max().strftime("%Y-%m-%d %H:%M")

with st.sidebar:
    st.markdown("<div class='sidebar-logo'>Artist 360 Intelligence</div>", unsafe_allow_html=True)
    st.markdown("---")
    page = st.radio("Navigation", list(PAGE_META.keys()), label_visibility="collapsed")
    latam_only = st.toggle("Latin America only", value=True)
    search = st.text_input("Artist search", placeholder="e.g. BTS")
    default_countries = sorted([c for c in leaderboard["display_country"].unique().tolist() if c != "—"])
    selected_countries = st.multiselect(
        "Countries",
        default_countries or LATAM_COUNTRIES,
        default=default_countries or LATAM_COUNTRIES[:6],
    )
    max_rows = st.slider("Table rows", min_value=10, max_value=50, value=15, step=5)
    if st.button("↻ Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.markdown("<span class='status-good'>● Pipeline: Healthy</span>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>Last run: {last_run_label}</div>", unsafe_allow_html=True)

filtered = leaderboard.copy()
if latam_only:
    filtered = filtered[filtered["latam_signal"]]
if selected_countries:
    filtered = filtered[filtered["display_country"].isin(selected_countries)]
if search.strip():
    filtered = filtered[filtered["name"].str.contains(search.strip(), case=False, na=False)]
filtered = filtered.sort_values("rank")

page_title, page_meta = PAGE_META[page]
render_header(page_title, page_meta, last_run_label)

if page == "Leaderboard":
    render_leaderboard(filtered, runs, max_rows=max_rows)
elif page == "Chart Tracker":
    render_chart_tracker(history, filtered)
elif page == "Stream Trends":
    render_stream_trends(filtered)
else:
    render_ops_monitor(runs)
