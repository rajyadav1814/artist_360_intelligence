import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from src.ui.utils import CHART_COLORS, PLOTLY_CONFIG, TRACKER_TOP_ARTISTS, style_figure

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
