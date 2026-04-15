import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from html import escape
from src.ui.components import render_kpis, fmt_short
from src.ui.utils import CHART_COLORS, PLOTLY_CONFIG, style_figure

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

def prepare_leaderboard_table(leaderboard: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    table_df = leaderboard.head(max_rows)[
        [
            "rank",
            "name",
            "top_song",
            "top_country",
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

def render_leaderboard(leaderboard: pd.DataFrame, runs: pd.DataFrame, max_rows: int) -> None:
    if leaderboard.empty:
        st.warning("No leaderboard data available yet. Run the scraper first.")
        return

    render_kpis(leaderboard, runs)

    st.markdown("<br>", unsafe_allow_html=True)

    # Keep all five controls in one row: Table, Analysis, Compare, Download
    selected_view = st.session_state.get("leaderboard_view", "📋 Table")
    btn_col1, btn_col2, btn_col3 = st.columns(3, gap="small")
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
                    custom_data=["top_country", "rank"],
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
                        "Top market: %{customdata[0]}<br>"
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
                    leaderboard.loc[leaderboard["top_country"].ne("—"), "top_country"]
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
                style_figure(fig_scatter, 300)
                st.plotly_chart(fig_scatter, use_container_width=True, config=PLOTLY_CONFIG)

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
                    hovertemplate="<b>%{x}</b><br>Required Points: %{y:,.0f}<br>Tier Artist: %{customdata}<extra></extra>",
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
                    hovertemplate="<b>%{x}</b><br>Required Listeners: %{y:,.0f}<br>Tier Artist: %{customdata}<extra></extra>",
                    customdata=thresh_df["Artist"]
                )
                style_figure(fig_thresh_ls, 320)
                st.plotly_chart(fig_thresh_ls, use_container_width=True, config=PLOTLY_CONFIG)
            
            with st.expander("📋 View Threshold Data Points"):
                st.dataframe(
                    thresh_df[["Tier", "Points", "Listeners", "Artist"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Points": st.column_config.NumberColumn(format="%d"),
                        "Listeners": st.column_config.NumberColumn(format="%d"),
                    }
                )
