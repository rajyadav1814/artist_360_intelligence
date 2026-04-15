import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from html import escape
from src.ui.utils import CHART_COLORS, PLOTLY_CONFIG, style_figure

def render_stream_trends(leaderboard: pd.DataFrame, top_history: pd.DataFrame, history: pd.DataFrame = pd.DataFrame()) -> None:
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
            st.plotly_chart(fig_growth, use_container_width=True, config=PLOTLY_CONFIG)
    
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
            st.info("Market reach needs source point breakdown data.")
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
            time_ranges = {0: "Daily (Last Run)", 7: "7 days", 14: "14 days", 30: "30 days"}
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
                # DAILY MODE: Use the rank_change from DB
                row = gl_filtered[gl_filtered["name"] == name].iloc[0]
                start_positions[name] = row["current_pos"] + row["db_change"]
                range_peaks[name] = min(row["current_pos"], start_positions[name])
            else:
                # Artist history logic
                artist_hist = history[(history["name"] == name) & (history["scraped_at"] >= cutoff_date)] if not history.empty else pd.DataFrame()
                
                if not artist_hist.empty:
                    sorted_hist = artist_hist.sort_values("scraped_at")
                    start_positions[name] = sorted_hist.iloc[0]["rank"]
                    range_peaks[name] = artist_hist["rank"].min()
                else:
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

        st.markdown("<br>", unsafe_allow_html=True)
        gl_chart_df = gl_filtered.sort_values("range_peak", ascending=False)
        
        if not gl_chart_df.empty:
            max_all_time_rank = gl_chart_df["range_peak"].max()
            fig_move = go.Figure()
            
            for idx, (_, row) in enumerate(gl_chart_df.iterrows()):
                unique_color = CHART_COLORS[idx % len(CHART_COLORS)]
                pos_score = max_all_time_rank + 1 - row["range_peak"]
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
                        f"Current: #{int(row['current_pos'])}<br><extra></extra>"
                    ),
                    showlegend=False
                ))
                
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
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(title="", gridcolor="rgba(255,255,255,0.05)"),
                height=max(500, len(gl_chart_df) * 40),
                margin=dict(l=180, r=150, t=60, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                bargap=0.35
            )
            
            chart_box_height = 750 if len(gl_chart_df) > 15 else None
            with st.container(height=chart_box_height):
                st.plotly_chart(fig_move, use_container_width=True, config=PLOTLY_CONFIG)
