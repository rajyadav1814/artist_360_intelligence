import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from html import escape
from src.ui.utils import CHART_COLORS, PLOTLY_CONFIG, style_figure

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
