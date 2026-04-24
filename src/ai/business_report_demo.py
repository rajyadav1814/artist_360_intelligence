"""
Business Analytics Agent - Report Generation Example
====================================================
Demonstrates using the Anthropic-powered analytics agent to generate
reports with 20% text insights and 80% visualizations.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random

from src.ai.business_analytics import (
    render_business_report,
    create_kpi_cards,
    generate_insights_text,
    create_line_chart,
    create_horizontal_bar_chart,
    create_scatter_chart,
    create_pie_chart,
    create_heatmap_chart,
)

# ============================================================================
# SAMPLE DATA GENERATION (Replace with actual data)
# ============================================================================

def generate_sample_analytics_data() -> pd.DataFrame:
    """Generate sample music analytics data for demonstration."""
    artists = [
        "The Weeknd", "Taylor Swift", "Bad Bunny", "Drake", "Olivia Rodrigo",
        "Billie Eilish", "Post Malone", "Dua Lipa", "Ariana Grande", "Ed Sheeran",
        "Harry Styles", "Weeknd", "Kanye West", "Coldplay", "Dua Lipa",
        "Shawn Mendes", "Niall Horan", "Khalid", "Travis Scott", "Juice WRLD"
    ]
    
    dates = [datetime.now() - timedelta(days=x) for x in range(30, 0, -1)]
    
    data = []
    for date in dates:
        for artist in artists:
            data.append({
                "date": date,
                "artist": artist,
                "monthly_listeners": random.randint(10_000_000, 100_000_000),
                "peak_listeners": random.randint(1_000_000, 20_000_000),
                "rank": random.randint(1, 100),
                "rank_change": random.randint(-10, 10),
                "total_points": random.randint(1000, 50000),
                "top_country": random.choice(["US", "UK", "ES", "MX", "BR", "DE", "FR"]),
                "num_countries": random.randint(50, 195),
                "itunes_points": random.randint(100, 5000),
                "spotify_points": random.randint(100, 5000),
            })
    
    return pd.DataFrame(data)


# ============================================================================
# BUSINESS REPORT EXAMPLES
# ============================================================================

def render_executive_summary_report():
    """Generate executive summary report with KPIs and trends."""
    st.title("📊 Executive Summary - Music Analytics Report")
    
    # Generate sample data
    df = generate_sample_analytics_data()
    latest_df = df[df['date'] == df['date'].max()].copy()
    
    # Define metrics for KPI cards (20% text)
    kpi_metrics = {
        "Total Listeners": "monthly_listeners",
        "Peak Listeners": "peak_listeners",
        "Artists": "artist",
        "Markets": "num_countries",
    }
    
    # Define charts for visualizations (80% visual)
    chart_config = [
        {
            "type": "line",
            "x_col": "date",
            "y_col": "monthly_listeners",
            "title": "Monthly Listeners Trend Over Time",
            "params": {"show_area": True}
        },
        {
            "type": "h_bar",
            "x_col": "artist",
            "y_col": "rank",
            "title": "Top 15 Artists by Ranking",
            "params": {"top_n": 15}
        },
        {
            "type": "scatter",
            "x_col": "monthly_listeners",
            "y_col": "peak_listeners",
            "title": "Monthly vs Peak Listeners Correlation",
            "params": {"color_col": "rank"}
        },
        {
            "type": "pie",
            "x_col": "top_country",
            "y_col": "num_countries",
            "title": "Market Distribution by Country",
            "params": {"top_n": 8}
        }
    ]
    
    # Generate insights text
    insights = generate_insights_text(latest_df, kpi_metrics, "revenue")
    
    # Render complete report
    render_business_report(
        df=df,
        title="Executive Summary - Weekly Report",
        metrics=kpi_metrics,
        chart_config=chart_config,
        insights=insights
    )


def render_performance_analysis_report():
    """Generate detailed performance analysis with multiple metrics."""
    st.title("📈 Performance Analysis - Quarterly Review")
    
    df = generate_sample_analytics_data()
    
    kpi_metrics = {
        "Avg. Listeners": "monthly_listeners",
        "Peak Performance": "peak_listeners",
        "Quality Score": "total_points",
    }
    
    chart_config = [
        {
            "type": "heatmap",
            "x_col": "artist",
            "y_col": "monthly_listeners",
            "title": "Listener Performance Heatmap"
        },
        {
            "type": "bar",
            "x_col": "top_country",
            "y_col": "num_countries",
            "title": "Geographic Reach by Country",
        },
        {
            "type": "scatter",
            "x_col": "total_points",
            "y_col": "rank_change",
            "title": "Score vs Momentum Analysis"
        },
    ]
    
    insights = generate_insights_text(df, kpi_metrics, "performance")
    
    render_business_report(
        df=df,
        title="Performance Analysis Report",
        metrics=kpi_metrics,
        chart_config=chart_config,
        insights=insights
    )


def render_market_distribution_report():
    """Generate market and distribution analysis."""
    st.title("🌍 Market Distribution Analysis")
    
    df = generate_sample_analytics_data()
    market_df = df.groupby('top_country').agg({
        'num_countries': 'mean',
        'monthly_listeners': 'sum',
        'total_points': 'sum',
        'artist': 'count'
    }).reset_index()
    market_df.columns = ['country', 'reach', 'total_listeners', 'market_score', 'artist_count']
    
    kpi_metrics = {
        "Markets Covered": "reach",
        "Total Listeners": "total_listeners",
        "Market Score": "market_score",
    }
    
    chart_config = [
        {
            "type": "pie",
            "x_col": "country",
            "y_col": "total_listeners",
            "title": "Listener Distribution by Market",
            "params": {"top_n": 10}
        },
        {
            "type": "bar",
            "x_col": "country",
            "y_col": "artist_count",
            "title": "Artist Presence by Country",
        },
        {
            "type": "h_bar",
            "x_col": "country",
            "y_col": "market_score",
            "title": "Market Strength Rankings",
            "params": {"top_n": 12}
        },
    ]
    
    insights = generate_insights_text(market_df, kpi_metrics, "distribution")
    
    render_business_report(
        df=market_df,
        title="Market Distribution Report",
        metrics=kpi_metrics,
        chart_config=chart_config,
        insights=insights
    )


# ============================================================================
# MAIN APP
# ============================================================================

def main():
    """Main application with multiple report options."""
    st.set_page_config(
        page_title="Business Analytics Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Sidebar navigation
    st.sidebar.title("📊 Reports")
    report_type = st.sidebar.radio(
        "Select Report Type",
        [
            "Executive Summary",
            "Performance Analysis",
            "Market Distribution"
        ]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    ### Report Features
    - **20% Text**: Key insights, KPIs, and analysis
    - **80% Visualizations**: Charts, graphs, and dashboards
    - **Business-Focused**: Revenue, performance, and distribution metrics
    - **Dark Theme**: Professional executive dashboard styling
    """)
    
    # Render selected report
    if report_type == "Executive Summary":
        render_executive_summary_report()
    elif report_type == "Performance Analysis":
        render_performance_analysis_report()
    else:
        render_market_distribution_report()
    
    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    **Powered by**: Anthropic Claude 3.5 Sonnet  
    **Built with**: Streamlit + Plotly  
    **Theme**: Dark Executive
    """)


if __name__ == "__main__":
    main()
