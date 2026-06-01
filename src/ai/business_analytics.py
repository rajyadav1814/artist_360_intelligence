"""
Business Analytics Module - Comprehensive Data Visualization & Analysis
========================================================================
Features:
- Multi-chart intelligent generation for business reports
- 15+ professional visualization types
- Business metrics and KPI dashboards
- Comparative analysis and trend detection
- 20% text insights + 80% visualization layout
- Dark theme optimized for executive dashboards
"""

from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ============================================================================
# PROFESSIONAL COLOR SCHEMES
# ============================================================================

PALETTE_BUSINESS = {
    "primary": "#1f77b4",        # Blue
    "secondary": "#2ca02c",      # Green
    "accent1": "#d62728",        # Red
    "accent2": "#ff7f0e",        # Orange
    "accent3": "#9467bd",        # Purple
    "accent4": "#8c564b",        # Brown
    "accent5": "#e377c2",        # Pink
    "accent6": "#7f7f7f",        # Gray
    "neutral": "#bcbd22",        # Olive
    "info": "#17becf",           # Cyan
}

PALETTE_GRADIENT_SUCCESS = ["#06b6d4", "#0891b2", "#0e7490"]
PALETTE_GRADIENT_REVENUE = ["#dc2626", "#f97316", "#fbbf24"]
PALETTE_GRADIENT_PERFORMANCE = ["#7c3aed", "#3b82f6", "#06b6d4"]
PALETTE_GRADIENT_HEATMAP = ["#eff6ff", "#3b82f6", "#1e40af"]

PALETTE_DARK = {
    "bg": "#0d1117",
    "grid": "rgba(148, 163, 184, 0.1)",
    "border": "rgba(148, 163, 184, 0.2)",
    "text": "#f1f5f9",
    "text_secondary": "#cbd5e1",
    "text_tertiary": "#94a3b8",
    "hover_bg": "rgba(8, 12, 24, 0.95)",
    "hover_border": "rgba(31, 119, 180, 0.5)",
}

# ============================================================================
# CHART CREATION FUNCTIONS
# ============================================================================

def create_kpi_cards(df: pd.DataFrame, metrics: Dict[str, str]) -> None:
    """
    Create KPI metric cards in a grid layout.
    metrics: Dict with format {"metric_name": "column_name"}
    """
    if df.empty or not metrics:
        return
    
    cols = st.columns(len(metrics))
    for idx, (label, column) in enumerate(metrics.items()):
        if column not in df.columns:
            continue
        
        with cols[idx]:
            numeric_val = pd.to_numeric(df[column], errors="coerce").dropna()
            if not numeric_val.empty:
                value = numeric_val.sum() if numeric_val.sum() > 1000 else numeric_val.mean()
                st.metric(
                    label=label,
                    value=f"{value:,.0f}",
                    delta=None,
                    delta_color="off"
                )


def create_horizontal_bar_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    show_values: bool = True,
    top_n: Optional[int] = None
) -> go.Figure:
    """Create professional horizontal bar chart for rankings."""
    plot_df = df.copy()
    if top_n:
        plot_df = plot_df.nlargest(top_n, y_col)
    
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[y_col]).sort_values(y_col, ascending=True)
    
    fig = go.Figure(data=[
        go.Bar(
            y=plot_df[x_col],
            x=plot_df[y_col],
            orientation='h',
            marker=dict(
                color=plot_df[y_col],
                colorscale=PALETTE_GRADIENT_PERFORMANCE,
                line=dict(color=PALETTE_DARK["border"], width=0.5),
            ),
            text=[f"{int(v):,}" if show_values else "" for v in plot_df[y_col]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>" + y_col + ": %{x:,.0f}<extra></extra>",
        )
    ])
    
    _apply_business_theme(fig, title)
    return fig


def create_vertical_bar_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    show_values: bool = True
) -> go.Figure:
    """Create professional vertical bar chart for comparisons."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col])
    
    fig = go.Figure(data=[
        go.Bar(
            x=plot_df[x_col],
            y=plot_df[y_col],
            marker=dict(
                color=plot_df[y_col],
                colorscale=PALETTE_GRADIENT_SUCCESS,
                line=dict(color=PALETTE_DARK["border"], width=0.5),
            ),
            text=[f"{int(v):,}" if show_values else "" for v in plot_df[y_col]],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>" + y_col + ": %{y:,.0f}<extra></extra>",
        )
    ])
    
    fig.update_xaxes(tickangle=-45)
    _apply_business_theme(fig, title)
    return fig


def create_line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    show_area: bool = True
) -> go.Figure:
    """Create professional line chart for trend analysis."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col]).sort_values(x_col)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df[x_col],
        y=plot_df[y_col],
        mode='lines+markers',
        name=y_col,
        line=dict(color=PALETTE_BUSINESS["primary"], width=3, shape="spline"),
        marker=dict(size=8, color=PALETTE_BUSINESS["primary"], 
                   line=dict(color=PALETTE_DARK["text"], width=1)),
        fill="tozeroy" if show_area else None,
        fillcolor="rgba(31, 119, 180, 0.2)" if show_area else None,
        hovertemplate="<b>%{x}</b><br>" + y_col + ": %{y:,.0f}<extra></extra>",
    ))
    
    _apply_business_theme(fig, title)
    return fig


def create_multi_line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_cols: List[str],
    title: str,
) -> go.Figure:
    """Create multi-line chart for comparing multiple metrics over time."""
    plot_df = df.copy()
    
    fig = go.Figure()
    colors = list(PALETTE_BUSINESS.values())
    
    for idx, y_col in enumerate(y_cols):
        if y_col not in df.columns:
            continue
        plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
        plot_df_clean = plot_df.dropna(subset=[x_col, y_col]).sort_values(x_col)
        
        fig.add_trace(go.Scatter(
            x=plot_df_clean[x_col],
            y=plot_df_clean[y_col],
            mode='lines+markers',
            name=y_col.replace('_', ' ').title(),
            line=dict(color=colors[idx % len(colors)], width=2.5, shape="spline"),
            marker=dict(size=6),
            hovertemplate="<b>%{x}</b><br>" + y_col + ": %{y:,.0f}<extra></extra>",
        ))
    
    _apply_business_theme(fig, title)
    return fig


def create_pie_chart(
    df: pd.DataFrame,
    labels_col: str,
    values_col: str,
    title: str,
    top_n: int = 10
) -> go.Figure:
    """Create donut chart for composition analysis."""
    plot_df = df.copy()
    plot_df[values_col] = pd.to_numeric(plot_df[values_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[values_col]).nlargest(top_n, values_col)
    
    colors = [PALETTE_BUSINESS[k] for k in list(PALETTE_BUSINESS.keys())[:len(plot_df)]]
    
    fig = go.Figure(data=[go.Pie(
        labels=plot_df[labels_col],
        values=plot_df[values_col],
        hole=0.4,
        marker=dict(colors=colors, line=dict(color=PALETTE_DARK["bg"], width=2)),
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="<b>%{label}</b><br>Value: %{value:,.0f}<br>Percentage: %{percent}<extra></extra>",
    )])
    
    _apply_business_theme(fig, title)
    return fig


def create_scatter_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    size_col: Optional[str] = None,
    color_col: Optional[str] = None,
    title: str = "Scatter Analysis"
) -> go.Figure:
    """Create scatter plot for correlation analysis."""
    plot_df = df.copy()
    plot_df[x_col] = pd.to_numeric(plot_df[x_col], errors="coerce")
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col])
    
    if size_col and size_col in plot_df.columns:
        plot_df[size_col] = pd.to_numeric(plot_df[size_col], errors="coerce")
    
    if color_col and color_col in plot_df.columns:
        plot_df[color_col] = pd.to_numeric(plot_df[color_col], errors="coerce")
    
    fig = px.scatter(
        plot_df,
        x=x_col,
        y=y_col,
        size=size_col,
        color=color_col,
        color_continuous_scale=PALETTE_GRADIENT_PERFORMANCE,
        size_max=50,
        title=title,
    )
    
    fig.update_traces(marker=dict(opacity=0.7, line=dict(width=1, color=PALETTE_DARK["border"])))
    _apply_business_theme(fig, title)
    return fig


def create_heatmap_chart(
    df: pd.DataFrame,
    title: str = "Correlation Heatmap"
) -> go.Figure:
    """Create heatmap for correlation analysis."""
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.empty:
        return None
    
    corr_matrix = numeric_df.corr()
    
    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns,
        y=corr_matrix.columns,
        colorscale=PALETTE_GRADIENT_HEATMAP,
        zmid=0,
        text=np.round(corr_matrix.values, 2),
        texttemplate="%{text:.2f}",
        textfont={"size": 10},
        hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>",
    ))
    
    _apply_business_theme(fig, title)
    return fig


def create_area_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str
) -> go.Figure:
    """Create stacked area chart for cumulative analysis."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col]).sort_values(x_col)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df[x_col],
        y=plot_df[y_col],
        fill="tozeroy",
        fillcolor="rgba(31, 119, 180, 0.3)",
        line=dict(color=PALETTE_BUSINESS["primary"], width=2),
        name=y_col,
        hovertemplate="<b>%{x}</b><br>" + y_col + ": %{y:,.0f}<extra></extra>",
    ))
    
    _apply_business_theme(fig, title)
    return fig


def create_histogram(
    df: pd.DataFrame,
    column: str,
    title: str,
    bins: int = 20
) -> go.Figure:
    """Create histogram for distribution analysis."""
    plot_df = df.copy()
    plot_df[column] = pd.to_numeric(plot_df[column], errors="coerce")
    plot_df = plot_df.dropna(subset=[column])
    
    fig = go.Figure(data=[go.Histogram(
        x=plot_df[column],
        nbinsx=bins,
        marker=dict(color=PALETTE_BUSINESS["secondary"], line=dict(color=PALETTE_DARK["border"], width=1)),
        hovertemplate="Range: %{x}<br>Count: %{y}<extra></extra>",
    )])
    
    _apply_business_theme(fig, title)
    return fig


def create_box_plot(
    df: pd.DataFrame,
    y_col: str,
    x_col: Optional[str] = None,
    title: str = "Distribution Analysis"
) -> go.Figure:
    """Create box plot for statistical distribution."""
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[y_col])
    
    fig = px.box(
        plot_df,
        y=y_col,
        x=x_col,
        color_discrete_sequence=[PALETTE_BUSINESS["primary"]],
        title=title,
    )
    
    fig.update_traces(boxmean=True)
    _apply_business_theme(fig, title)
    return fig


def create_funnel_chart(
    df: pd.DataFrame,
    stage_col: str,
    value_col: str,
    title: str
) -> go.Figure:
    """Create funnel chart for stage conversion analysis."""
    plot_df = df.copy()
    plot_df[value_col] = pd.to_numeric(plot_df[value_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[value_col]).sort_values(value_col, ascending=False)
    
    fig = go.Figure(go.Funnel(
        y=plot_df[stage_col],
        x=plot_df[value_col],
        marker=dict(color=PALETTE_BUSINESS["primary"]),
        textposition="inside",
        textinfo="value+percent initial",
        hovertemplate="<b>%{y}</b><br>Value: %{x:,.0f}<extra></extra>",
    ))
    
    _apply_business_theme(fig, title)
    return fig


def create_gauge_chart(
    value: float,
    max_value: float = 100,
    title: str = "KPI Gauge",
    unit: str = "%"
) -> go.Figure:
    """Create gauge chart for KPI visualization."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title},
        delta={'reference': max_value * 0.8},
        gauge={
            'axis': {'range': [None, max_value]},
            'bar': {'color': PALETTE_BUSINESS["primary"]},
            'steps': [
                {'range': [0, max_value * 0.5], 'color': PALETTE_DARK["grid"]},
                {'range': [max_value * 0.5, max_value * 0.8], 'color': PALETTE_DARK["border"]},
                {'range': [max_value * 0.8, max_value], 'color': PALETTE_BUSINESS["secondary"]}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': max_value * 0.9
            }
        }
    ))
    
    _apply_business_theme(fig, title)
    return fig


def create_waterfall_chart(
    df: pd.DataFrame,
    category_col: str,
    value_col: str,
    title: str
) -> go.Figure:
    """Create waterfall chart for sequential change analysis."""
    plot_df = df.copy()
    plot_df[value_col] = pd.to_numeric(plot_df[value_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[value_col]).head(15)
    
    measures = ["relative"] * (len(plot_df) - 1) + ["total"]
    
    fig = go.Figure(go.Waterfall(
        name="Changes",
        x=plot_df[category_col],
        y=plot_df[value_col],
        measure=measures,
        connector={"line": {"color": PALETTE_BUSINESS["primary"]}},
        increasing={"marker": {"color": PALETTE_BUSINESS["secondary"]}},
        decreasing={"marker": {"color": PALETTE_BUSINESS["accent1"]}},
        totals={"marker": {"color": PALETTE_BUSINESS["primary"]}},
    ))
    
    _apply_business_theme(fig, title)
    return fig


def create_sunburst_chart(
    df: pd.DataFrame,
    labels_col: str,
    values_col: str,
    parents_col: Optional[str] = None,
    title: str = "Hierarchical Distribution"
) -> go.Figure:
    """Create sunburst for hierarchical data."""
    plot_df = df.copy()
    plot_df[values_col] = pd.to_numeric(plot_df[values_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[values_col]).head(30)
    
    colors = [PALETTE_BUSINESS[k] for k in list(PALETTE_BUSINESS.keys())[:len(plot_df)]]
    
    fig = go.Figure(go.Sunburst(
        labels=plot_df[labels_col],
        parents=plot_df[parents_col] if parents_col else [""] * len(plot_df),
        values=plot_df[values_col],
        marker=dict(colors=colors),
    ))
    
    _apply_business_theme(fig, title)
    return fig


def create_dashboard_grid(
    figures: List[Tuple[go.Figure, int]],
    title: str = "Business Analytics Dashboard"
) -> None:
    """
    Display multiple figures in a grid layout.
    figures: List of (figure, column_span) tuples where column_span is 1-3
    """
    st.subheader(title)
    
    container = st.container()
    cols = st.columns(3)
    col_idx = 0
    
    for fig, span in figures:
        if col_idx + span > 3:
            col_idx = 0
        
        with cols[col_idx:col_idx + span]:
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        
        col_idx += span


# ============================================================================
# BUSINESS ANALYTICS HELPER FUNCTIONS
# ============================================================================

def calculate_growth_rate(
    df: pd.DataFrame,
    value_col: str,
    group_col: Optional[str] = None,
) -> Dict[str, float]:
    """Calculate growth rates for metrics."""
    numeric_vals = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if len(numeric_vals) < 2:
        return {}
    
    values = numeric_vals.values
    growth_rate = ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0
    
    return {"growth_rate": growth_rate, "start": values[0], "end": values[-1]}


def generate_insights_text(
    df: pd.DataFrame,
    metrics: Dict[str, str],
    analysis_type: str = "general"
) -> str:
    """Generate concise text insights (20% of report)."""
    insights = []
    
    for metric_name, column in metrics.items():
        if column not in df.columns:
            continue
        
        numeric_vals = pd.to_numeric(df[column], errors="coerce").dropna()
        if numeric_vals.empty:
            continue
        
        mean_val = numeric_vals.mean()
        max_val = numeric_vals.max()
        min_val = numeric_vals.min()
        
        if analysis_type == "revenue":
            insights.append(f"**{metric_name}**: Total ${mean_val:,.0f} avg, peak ${max_val:,.0f}")
        elif analysis_type == "performance":
            growth = calculate_growth_rate(df, column)
            if growth:
                insights.append(f"**{metric_name}**: {growth['growth_rate']:+.1f}% growth ({growth['start']:.0f} → {growth['end']:.0f})")
        else:
            insights.append(f"**{metric_name}**: Avg {mean_val:,.0f} | Max {max_val:,.0f} | Min {min_val:,.0f}")
    
    return " | ".join(insights) if insights else "No data available for analysis"


# ============================================================================
# THEME APPLICATION
# ============================================================================

def _apply_business_theme(fig: go.Figure, title: str = "") -> None:
    """Apply professional business theme to any figure."""
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=18, color=PALETTE_DARK["text"], family="Arial, sans-serif"),
            x=0.02,
            xanchor="left",
            y=0.98,
            yanchor="top",
        ),
        hovermode="closest",
        plot_bgcolor=PALETTE_DARK["bg"],
        paper_bgcolor=PALETTE_DARK["bg"],
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor=PALETTE_DARK["grid"],
            showline=True,
            linewidth=1,
            linecolor=PALETTE_DARK["border"],
            tickfont=dict(color=PALETTE_DARK["text_secondary"], size=9),
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor=PALETTE_DARK["grid"],
            showline=True,
            linewidth=1,
            linecolor=PALETTE_DARK["border"],
            tickfont=dict(color=PALETTE_DARK["text_secondary"], size=9),
        ),
        font=dict(family="Arial, sans-serif", size=11, color=PALETTE_DARK["text"]),
        margin=dict(l=50, r=20, t=60, b=50),
        height=500,
        legend=dict(
            title_text="",
            bgcolor="rgba(15, 23, 42, 0.8)",
            bordercolor=PALETTE_DARK["border"],
            borderwidth=1,
            font=dict(color=PALETTE_DARK["text_secondary"]),
        ),
        hoverlabel=dict(
            bgcolor=PALETTE_DARK["hover_bg"],
            bordercolor=PALETTE_DARK["hover_border"],
            font=dict(color=PALETTE_DARK["text"]),
        ),
    )


def render_business_report(
    df: pd.DataFrame,
    title: str,
    metrics: Dict[str, str],
    chart_config: List[Dict[str, Any]],
    insights: Optional[str] = None
) -> None:
    """
    Render complete business report with 20% text and 80% visualizations.
    
    Args:
        df: DataFrame with analysis data
        title: Report title
        metrics: KPI metrics dict {"label": "column_name"}
        chart_config: List of chart configs with keys:
                     - type: chart type (line, bar, pie, scatter, etc.)
                     - x_col, y_col: column names
                     - title: chart title
                     - params: additional parameters
        insights: Optional insights text (auto-generated if not provided)
    """
    st.subheader(title)
    
    # 20% Text Content
    text_col, viz_col = st.columns([1, 4])
    
    with text_col:
        st.markdown("### 📊 Key Insights")
        if insights is None:
            insights = generate_insights_text(df, metrics)
        st.markdown(insights)
        
        # KPI Cards
        st.markdown("### 📈 KPIs")
        create_kpi_cards(df, metrics)
    
    # 80% Visualization Content
    with viz_col:
        if not chart_config:
            st.info("No visualization configuration provided")
            return
        
        for chart_info in chart_config:
            chart_type = chart_info.get("type", "line")
            x_col = chart_info.get("x_col")
            y_col = chart_info.get("y_col")
            chart_title = chart_info.get("title", f"{chart_type.title()} Analysis")
            params = chart_info.get("params", {})
            
            if not x_col or not y_col:
                continue
            
            try:
                if chart_type == "line":
                    fig = create_line_chart(df, x_col, y_col, chart_title, **params)
                elif chart_type == "bar":
                    fig = create_vertical_bar_chart(df, x_col, y_col, chart_title, **params)
                elif chart_type == "h_bar":
                    fig = create_horizontal_bar_chart(df, x_col, y_col, chart_title, **params)
                elif chart_type == "pie":
                    fig = create_pie_chart(df, x_col, y_col, chart_title, **params)
                elif chart_type == "area":
                    fig = create_area_chart(df, x_col, y_col, chart_title)
                elif chart_type == "scatter":
                    fig = create_scatter_chart(df, x_col, y_col, title=chart_title, **params)
                elif chart_type == "histogram":
                    fig = create_histogram(df, y_col, chart_title, **params)
                elif chart_type == "box":
                    fig = create_box_plot(df, y_col, x_col, chart_title)
                elif chart_type == "heatmap":
                    fig = create_heatmap_chart(df, chart_title)
                elif chart_type == "waterfall":
                    fig = create_waterfall_chart(df, x_col, y_col, chart_title)
                elif chart_type == "funnel":
                    fig = create_funnel_chart(df, x_col, y_col, chart_title)
                else:
                    continue
                
                if fig:
                    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
            
            except Exception as e:
                st.warning(f"Could not render {chart_type}: {str(e)}")
