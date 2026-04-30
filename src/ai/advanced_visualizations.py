"""
Advanced Visualization Module for Music Analytics Chatbot
Features:
- Intelligent multi-chart generation based on data characteristics
- Dynamic chart recommendations
- 10+ chart types with professional styling
- Interactive insights and statistics
- Comparative visualizations
- Data-driven aesthetic choices
"""

from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Professional color palettes
PALETTE_MODERN = {
    "primary": "#4f8ef7",
    "secondary": "#22d3a0",
    "accent1": "#7c5cfc",
    "accent2": "#f5a623",
    "accent3": "#06b6d4",
    "accent4": "#ec4899",
    "accent5": "#84cc16",
    "accent6": "#f97316",
}

PALETTE_DARK_BG = {
    "bg": "rgba(18,24,42,1)",
    "grid": "rgba(151,163,197,.12)",
    "border": "rgba(151,163,197,.18)",
    "text": "#eef2ff",
    "text_secondary": "#d6defa",
    "text_tertiary": "#c9d4f8",
    "hover_bg": "rgba(9,17,39,.95)",
    "hover_border": "rgba(79,142,247,.45)",
}

PALETTE_GRADIENT_COOL = ["#1d4ed8", "#7c5cfc", "#22d3a0"]
PALETTE_GRADIENT_WARM = ["#dc2626", "#f97316", "#f5a623"]


def _infer_data_characteristics(df: pd.DataFrame, x_col: str, y_col: str) -> Dict[str, Any]:
    """Analyze data to recommend optimal visualization."""
    chars = {
        "n_rows": len(df),
        "has_duplicates": df[x_col].duplicated().any() if x_col in df.columns else False,
        "is_numeric_y": pd.api.types.is_numeric_dtype(df[y_col]) if y_col in df.columns else False,
        "is_temporal_x": pd.api.types.is_datetime64_any_dtype(df[x_col]) if x_col in df.columns else False,
        "y_range": None,
        "y_variance": None,
        "has_outliers": False,
    }

    if chars["is_numeric_y"] and y_col in df.columns:
        numeric_y = pd.to_numeric(df[y_col], errors="coerce").dropna()
        if len(numeric_y) > 0:
            chars["y_range"] = (numeric_y.min(), numeric_y.max())
            chars["y_variance"] = numeric_y.std()
            q1 = numeric_y.quantile(0.25)
            q3 = numeric_y.quantile(0.75)
            iqr = q3 - q1
            chars["has_outliers"] = ((numeric_y < q1 - 1.5 * iqr) | (numeric_y > q3 + 1.5 * iqr)).any()

    return chars


def _select_optimal_charts(df: pd.DataFrame, x_col: str, y_col: str, question: str) -> List[Dict[str, Any]]:
    """Intelligently select 2-3 chart types based on data characteristics."""
    chars = _infer_data_characteristics(df, x_col, y_col)
    question_lower = question.lower()
    charts: List[Dict[str, Any]] = []

    if "rank" in question_lower or "top" in question_lower:
        charts.append(
            {
                "type": "horizontal_bar",
                "title": f"Ranking: {y_col.replace('_', ' ').title()}",
                "description": "Horizontal bar chart for easy rank comparison",
            }
        )
    elif "trend" in question_lower or "over time" in question_lower:
        charts.append(
            {
                "type": "line_with_markers",
                "title": f"Trend: {y_col.replace('_', ' ').title()} Over Time",
                "description": "Line chart showing progression",
            }
        )
    elif "distribution" in question_lower or "country" in question_lower:
        charts.append(
            {
                "type": "pie",
                "title": f"Distribution of {x_col.replace('_', ' ').title()}",
                "description": "Pie chart showing proportions",
            }
        )
    else:
        charts.append(
            {
                "type": "vertical_bar",
                "title": f"{y_col.replace('_', ' ').title()} by {x_col.replace('_', ' ').title()}",
                "description": "Bar chart comparing values",
            }
        )

    if chars["n_rows"] > 5 and not chars["has_duplicates"]:
        if "rank" not in question_lower and chars["is_numeric_y"]:
            charts.append(
                {
                    "type": "scatter_bubble",
                    "title": f"Detailed View: {y_col.replace('_', ' ').title()} Distribution",
                    "description": "Scatter plot showing individual data points",
                }
            )

    if chars["n_rows"] > 10 and chars["is_numeric_y"]:
        if "listener" in question_lower or "peak" in question_lower:
            charts.append(
                {
                    "type": "area",
                    "title": f"Cumulative {y_col.replace('_', ' ').title()}",
                    "description": "Area chart showing cumulative growth",
                }
            )
        elif chars["has_outliers"]:
            charts.append(
                {
                    "type": "box",
                    "title": f"Statistical Distribution: {y_col.replace('_', ' ').title()}",
                    "description": "Box plot showing quartiles and outliers",
                }
            )

    return charts


def _create_vertical_bar(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure:
    """Create vertical bar chart with professional styling."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col])

    fig = px.bar(
        plot_df,
        x=x_col,
        y=y_col,
        title=title,
        color_discrete_sequence=[PALETTE_MODERN["primary"]],
    )

    fig.update_traces(
        marker_color=PALETTE_MODERN["primary"],
        hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.0f}}<extra></extra>",
        text=[f"{int(v):,}" if pd.notna(v) else "" for v in plot_df[y_col]],
        textposition="outside",
    )

    fig.update_xaxes(tickangle=-22)
    _apply_dark_theme(fig)
    return fig


def _create_horizontal_bar(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure:
    """Create horizontal bar chart (ideal for rankings and comparisons)."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col]).sort_values(y_col, ascending=True)

    fig = px.bar(
        plot_df,
        x=y_col,
        y=x_col,
        orientation="h",
        title=title,
        color_discrete_sequence=[PALETTE_MODERN["primary"]],
    )

    fig.update_traces(
        marker_color=PALETTE_MODERN["primary"],
        text=[f"{int(v):,}" if pd.notna(v) else "" for v in plot_df[y_col]],
        textposition="outside",
        hovertemplate=f"<b>%{{y}}</b><br>{y_col}: %{{x:,.0f}}<extra></extra>",
    )

    _apply_dark_theme(fig)
    return fig


def _create_scatter_bubble(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure:
    """Create scatter/bubble chart with color and size encoding."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col])

    size_col = "rank" if "rank" in plot_df.columns else y_col
    if size_col in plot_df.columns:
        plot_df[size_col] = pd.to_numeric(plot_df[size_col], errors="coerce")

    fig = px.scatter(
        plot_df,
        x=x_col,
        y=y_col,
        size=size_col,
        color=y_col,
        color_continuous_scale=PALETTE_GRADIENT_COOL,
        title=title,
        size_max=50,
    )

    fig.update_traces(
        marker=dict(opacity=0.7, line=dict(width=2, color="rgba(255,255,255,.3)")),
        hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.0f}}<extra></extra>",
    )

    fig.update_coloraxes(showscale=True)
    _apply_dark_theme(fig)
    return fig


def _create_line_chart(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure:
    """Create line chart with smooth curves and markers."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col]).sort_values(x_col)

    fig = px.line(
        plot_df,
        x=x_col,
        y=y_col,
        title=title,
        markers=True,
    )

    fig.update_traces(
        line=dict(color=PALETTE_MODERN["primary"], width=3, shape="spline"),
        marker=dict(size=10, color=PALETTE_MODERN["primary"], line=dict(color="rgba(255,255,255,.3)", width=2)),
        fill="tozeroy",
        fillcolor="rgba(79,142,247,.1)",
        hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.0f}}<extra></extra>",
    )

    _apply_dark_theme(fig)
    return fig


def _create_area_chart(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure:
    """Create stacked area chart showing cumulative values."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col]).sort_values(x_col)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=plot_df[x_col],
            y=plot_df[y_col],
            name=y_col,
            fill="tozeroy",
            fillcolor="rgba(79,142,247,.3)",
            line=dict(color=PALETTE_MODERN["primary"], width=3),
            hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.0f}}<extra></extra>",
        )
    )

    fig.update_layout(title=title, hovermode="x unified")
    _apply_dark_theme(fig)
    return fig


def _create_pie_chart(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure:
    """Create pie/donut chart for distribution visualization."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col]).head(10)

    colors = [PALETTE_MODERN[k] for k in list(PALETTE_MODERN.keys())[: len(plot_df)]]

    fig = px.pie(
        plot_df,
        names=x_col,
        values=y_col,
        title=title,
        color_discrete_sequence=colors,
        hole=0.4,
    )

    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="<b>%{label}</b><br>Count: %{value}<extra></extra>",
    )

    _apply_dark_theme(fig)
    return fig


def _create_box_plot(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure:
    """Create box plot showing statistical distribution."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[y_col])

    fig = px.box(
        plot_df,
        y=y_col,
        title=title,
        color_discrete_sequence=[PALETTE_MODERN["secondary"]],
    )

    fig.update_traces(
        marker=dict(color=PALETTE_MODERN["secondary"], opacity=0.7),
        boxmean=True,
        hovertemplate=f"{y_col}: %{{y}}<extra></extra>",
    )

    _apply_dark_theme(fig)
    return fig


def _create_sunburst(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure | None:
    """Create sunburst chart for hierarchical data."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col]).head(20)

    if len(plot_df) < 3:
        return None

    fig = px.sunburst(
        plot_df,
        names=x_col,
        values=y_col,
        title=title,
        color=y_col,
        color_continuous_scale=PALETTE_GRADIENT_COOL,
    )

    _apply_dark_theme(fig)
    return fig


def _create_histogram(df: pd.DataFrame, y_col: str, title: str) -> go.Figure:
    """Create histogram for distribution analysis."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[y_col])

    fig = px.histogram(
        plot_df,
        y=y_col,
        nbins=20,
        title=title,
        color_discrete_sequence=[PALETTE_MODERN["accent1"]],
    )

    fig.update_traces(
        marker_color=PALETTE_MODERN["accent1"],
        hovertemplate=f"{y_col} range: %{{x}}<br>Count: %{{y}}<extra></extra>",
    )

    _apply_dark_theme(fig)
    return fig


def _create_waterfall(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure | None:
    """Create waterfall chart showing sequential changes."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col]).head(15)

    if len(plot_df) < 2:
        return None

    measures = ["relative"] * (len(plot_df) - 1) + ["total"]
    fig = go.Figure(
        go.Waterfall(
            name="Changes",
            x=plot_df[x_col],
            y=plot_df[y_col],
            measure=measures,
            connector={"line": {"color": PALETTE_MODERN["primary"]}},
            increasing={"marker": {"color": PALETTE_MODERN["secondary"]}},
            decreasing={"marker": {"color": PALETTE_MODERN["accent2"]}},
            totals={"marker": {"color": PALETTE_MODERN["primary"]}},
        )
    )

    fig.update_layout(title=title)
    _apply_dark_theme(fig)
    return fig


def _apply_dark_theme(fig: go.Figure) -> None:
    """Apply consistent dark theme styling to any figure."""
    fig.update_layout(
        title=dict(
            font=dict(size=20, color=PALETTE_DARK_BG["text"], family="Segoe UI, Inter, sans-serif"),
            x=0.03,
            xanchor="left",
        ),
        hovermode="closest",
        plot_bgcolor=PALETTE_DARK_BG["bg"],
        paper_bgcolor=PALETTE_DARK_BG["bg"],
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor=PALETTE_DARK_BG["grid"],
            showline=True,
            linewidth=1,
            linecolor=PALETTE_DARK_BG["border"],
            tickfont=dict(color=PALETTE_DARK_BG["text_secondary"], size=10),
            title_font=dict(color=PALETTE_DARK_BG["text_tertiary"], size=11),
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor=PALETTE_DARK_BG["grid"],
            showline=True,
            linewidth=1,
            linecolor=PALETTE_DARK_BG["border"],
            tickfont=dict(color=PALETTE_DARK_BG["text_secondary"], size=10),
            title_font=dict(color=PALETTE_DARK_BG["text_tertiary"], size=11),
        ),
        font=dict(family="Segoe UI, Inter, sans-serif", size=12, color=PALETTE_DARK_BG["text"]),
        height=500,
        margin=dict(l=40, r=20, t=70, b=40),
        legend=dict(
            title_text="",
            bgcolor="rgba(18,24,42,0.8)",
            bordercolor=PALETTE_DARK_BG["border"],
            borderwidth=1,
            font=dict(color=PALETTE_DARK_BG["text_secondary"]),
        ),
        hoverlabel=dict(
            bgcolor=PALETTE_DARK_BG["hover_bg"],
            bordercolor=PALETTE_DARK_BG["hover_border"],
            font=dict(color=PALETTE_DARK_BG["text"]),
        ),
    )


def render_multi_chart_view(df: pd.DataFrame, x_col: str, y_col: str, question: str) -> None:
    """Render multiple intelligent chart views based on data."""
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        st.info("📊 No data available for visualization")
        return

    charts_to_render = _select_optimal_charts(df, x_col, y_col, question)

    if not charts_to_render:
        st.info("📊 Unable to determine optimal charts")
        return

    for idx, chart_info in enumerate(charts_to_render):
        chart_type = chart_info["type"]
        title = chart_info["title"]

        try:
            if chart_type == "vertical_bar":
                fig = _create_vertical_bar(df, x_col, y_col, title)
            elif chart_type == "horizontal_bar":
                fig = _create_horizontal_bar(df, x_col, y_col, title)
            elif chart_type == "scatter_bubble":
                fig = _create_scatter_bubble(df, x_col, y_col, title)
            elif chart_type == "line_with_markers":
                fig = _create_line_chart(df, x_col, y_col, title)
            elif chart_type == "area":
                fig = _create_area_chart(df, x_col, y_col, title)
            elif chart_type == "pie":
                fig = _create_pie_chart(df, x_col, y_col, title)
            elif chart_type == "box":
                fig = _create_box_plot(df, x_col, y_col, title)
            elif chart_type == "sunburst":
                fig = _create_sunburst(df, x_col, y_col, title)
            elif chart_type == "histogram":
                fig = _create_histogram(df, y_col, title)
            elif chart_type == "waterfall":
                fig = _create_waterfall(df, x_col, y_col, title)
            else:
                continue

            if fig:
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    key=f"chart_{idx}_{question}",
                    config={"displaylogo": False, "toImageButtonOptions": {"format": "png"}},
                )
                st.caption(f"📈 {chart_info['description']}")

        except Exception as exc:
            st.warning(f"Could not render {chart_type}: {str(exc)}")


def render_comparative_charts(df: pd.DataFrame, metrics: List[str], x_col: str, title: str) -> None:
    """Render side-by-side comparison charts for multiple metrics."""
    if df.empty or not metrics:
        return

    valid_metrics = [metric for metric in metrics if metric in df.columns]
    if not valid_metrics:
        return

    st.subheader(title)
    metrics_per_row = 3

    for row_start in range(0, len(valid_metrics), metrics_per_row):
        row_metrics = valid_metrics[row_start : row_start + metrics_per_row]
        cols = st.columns(len(row_metrics))
        for col_idx, metric in enumerate(row_metrics):
            with cols[col_idx]:
                try:
                    fig = _create_vertical_bar(
                        df.head(10),
                        x_col,
                        metric,
                        metric.replace("_", " ").title(),
                    )
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        key=f"comp_chart_{row_start}_{col_idx}_{metric}",
                    )
                except Exception:
                    st.warning(f"Could not render {metric}")


def render_insights_dashboard(df: pd.DataFrame, x_col: str, y_col: str) -> None:
    """Render interactive insights dashboard with statistics."""
    if df.empty or y_col not in df.columns:
        return

    numeric_y = pd.to_numeric(df[y_col], errors="coerce").dropna()
    if numeric_y.empty:
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Records", f"{len(df):,}", delta=None, delta_color="off")

    with col2:
        st.metric("Average Value", f"{numeric_y.mean():,.0f}", delta=None, delta_color="off")

    with col3:
        st.metric("Max Value", f"{numeric_y.max():,.0f}", delta=None, delta_color="off")

    with col4:
        st.metric("Min Value", f"{numeric_y.min():,.0f}", delta=None, delta_color="off")

    st.subheader("📊 Distribution Insights")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.write(f"**Median**: {numeric_y.median():,.0f}")
        st.write(f"**Std Dev**: {numeric_y.std():,.0f}")

    with col_b:
        st.write(f"**Q1 (25%)**: {numeric_y.quantile(0.25):,.0f}")
        st.write(f"**Q3 (75%)**: {numeric_y.quantile(0.75):,.0f}")

    with col_c:
        st.write(f"**Range**: {numeric_y.max() - numeric_y.min():,.0f}")
        st.write(f"**Variance**: {numeric_y.var():,.0f}")
