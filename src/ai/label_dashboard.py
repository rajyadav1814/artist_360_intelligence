"""
Label Dashboard - displays top tracks and performance metrics by label
Similar to Sony Latin Pulse design
"""

import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from src.database.connection import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_weekly_date_range():
    """Get the date range for the current week"""
    today = datetime.now()
    # Get Monday of current week
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def get_top_tracks_by_streams(limit: int = 100, days_back: int = 7) -> pd.DataFrame:
    """Fetch top tracks by Spotify streams from the past N days"""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            query = """
                SELECT 
                    artist_title,
                    label,
                    rank,
                    SUM(streams) as total_streams,
                    AVG(streams) as avg_daily_streams,
                    COUNT(DISTINCT date) as days_charted,
                    MIN(rank) as best_rank,
                    MAX(rank) as worst_rank,
                    COUNT(*) as appearances,
                    MAX(date) as last_date
                FROM spotify_daily
                WHERE date >= NOW()::date - %s
                    AND label IS NOT NULL
                    AND streams > 0
                GROUP BY artist_title, label, rank
                ORDER BY total_streams DESC
                LIMIT %s
            """
            cur.execute(query, (days_back, limit))
            result = cur.fetchall()
            
            if not result:
                return pd.DataFrame()
            
            df = pd.DataFrame(result)
            
            # Convert numeric columns
            for col in ['total_streams', 'avg_daily_streams', 'rank', 'best_rank', 'worst_rank']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df.sort_values('total_streams', ascending=False)
    except Exception as e:
        logger.error(f"Error fetching top tracks: {e}")
        return pd.DataFrame()


def get_label_summary(days_back: int = 7) -> pd.DataFrame:
    """Get aggregate statistics by label"""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            query = """
                SELECT 
                    label,
                    COUNT(DISTINCT artist_title) as tracks,
                    SUM(streams) as total_streams,
                    COUNT(DISTINCT date) as days_in_chart,
                    MIN(rank) as best_rank,
                    COUNT(*) as total_appearances
                FROM spotify_daily
                WHERE date >= NOW()::date - %s
                    AND label IS NOT NULL
                    AND streams > 0
                GROUP BY label
                ORDER BY total_streams DESC
            """
            cur.execute(query, (days_back,))
            result = cur.fetchall()
            
            if not result:
                return pd.DataFrame()
            
            df = pd.DataFrame(result)
            
            # Convert numeric columns
            for col in ['tracks', 'total_streams', 'days_in_chart', 'best_rank', 'total_appearances']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
    except Exception as e:
        logger.error(f"Error fetching label summary: {e}")
        return pd.DataFrame()


def get_rank_statistics(days_back: int = 7) -> dict:
    """Get key statistics for specific ranks"""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            stats = {}
            
            # Get latest date
            cur.execute("SELECT MAX(date) as latest_date FROM spotify_daily")
            result = cur.fetchone()
            latest_date = result['latest_date'] if result else None
            
            if latest_date:
                # Top 100 sum on latest date
                cur.execute("""
                    SELECT SUM(streams) as total_streams
                    FROM spotify_daily
                    WHERE date = %s
                        AND rank <= 100
                        AND streams > 0
                """, (latest_date,))
                result = cur.fetchone()
                stats['top_100_avg'] = result['total_streams'] if result and result['total_streams'] else 0
            else:
                stats['top_100_avg'] = 0
            
            # Rank 100 specific (latest date)
            if latest_date:
                cur.execute("""
                    SELECT SUM(streams) as total
                    FROM spotify_daily
                    WHERE date = %s
                        AND rank = 100
                        AND streams > 0
                """, (latest_date,))
                result = cur.fetchone()
                stats['rank_100_streams'] = result['total'] if result and result['total'] else 0
            else:
                stats['rank_100_streams'] = 0
            
            # Rank 20 specific (latest date)
            if latest_date:
                cur.execute("""
                    SELECT SUM(streams) as total
                    FROM spotify_daily
                    WHERE date = %s
                        AND rank = 20
                        AND streams > 0
                """, (latest_date,))
                result = cur.fetchone()
                stats['rank_20_streams'] = result['total'] if result and result['total'] else 0
            else:
                stats['rank_20_streams'] = 0
            
            # Rank 30 specific (latest date)
            if latest_date:
                cur.execute("""
                    SELECT SUM(streams) as total
                    FROM spotify_daily
                    WHERE date = %s
                        AND rank = 30
                        AND streams > 0
                """, (latest_date,))
                result = cur.fetchone()
                stats['rank_30_streams'] = result['total'] if result and result['total'] else 0
            else:
                stats['rank_30_streams'] = 0
            
            return stats
    except Exception as e:
        logger.error(f"Error fetching rank statistics: {e}")
        return {}


def format_number(num):
    """Format large numbers for display"""
    if num is None or pd.isna(num):
        return "—"
    num = float(num)
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    else:
        return f"{int(num)}"


def render_label_dashboard():
    """Main render function for the label dashboard"""
    
    # Header with date range
    monday, sunday = get_weekly_date_range()
    week_num = monday.strftime("%W")
    date_range = f"{monday.strftime('%B %d')} - {sunday.strftime('%B %d, %Y')}"
    
    # Title section
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"<div class='page-title'>Label Market Pulse</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='page-meta'>WEEK {week_num} • {date_range} • Live Spotify Data</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
            <div style='text-align: right; padding-top: 0.5rem;'>
                <div style='display: flex; align-items: center; justify-content: flex-end; gap: 0.5rem;'>
                    <span style='width: 8px; height: 8px; background: #22d3a0; border-radius: 50%; animation: pulse 2s infinite;'></span>
                    <span style='color: #97a3c5; font-size: 0.85rem;'>LIVE</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    # Navigation tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["RANKINGS", "ARTISTS", "LABELS", "MOVEMENT", "ACQUISITION"])
    
    with tab1:  # RANKINGS
        st.subheader("📊 Track Rankings")
        
        # Fetch data
        tracks_df = get_top_tracks_by_streams(limit=100)
        rank_stats = get_rank_statistics()
        
        if not tracks_df.empty:
            # Key metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Top 100 Entry",
                    format_number(rank_stats.get('top_100_avg', 0)),
                    "all top 100 streams"
                )
            
            with col2:
                st.metric(
                    "Rank 100",
                    format_number(rank_stats.get('rank_100_streams', 0)),
                    "rank 100 streams"
                )
            
            with col3:
                st.metric(
                    "Rank 20",
                    format_number(rank_stats.get('rank_20_streams', 0)),
                    "rank 20 streams"
                )
            
            with col4:
                st.metric(
                    "Rank 30",
                    format_number(rank_stats.get('rank_30_streams', 0)),
                    "rank 30 streams"
                )
            
            st.divider()
            
            # Top 5 with label details
            st.markdown("#### 🔝 Top 5 Tracks Last 7 Days")
            
            top_5 = tracks_df.head(5).copy()
            
            # Create detailed table
            display_df = top_5[[
                'artist_title', 'label', 'rank', 'total_streams', 
                'best_rank', 'days_charted', 'appearances'
            ]].copy()
            
            display_df.columns = ['Track', 'Label', 'Current Rank', 'Total Streams', 'Best Rank', 'Days Charted', 'Appearances']
            
            # Format numeric columns
            display_df['Total Streams'] = display_df['Total Streams'].apply(format_number)
            display_df['Current Rank'] = display_df['Current Rank'].astype(int)
            display_df['Best Rank'] = display_df['Best Rank'].astype(int)
            display_df['Days Charted'] = display_df['Days Charted'].astype(int)
            display_df['Appearances'] = display_df['Appearances'].astype(int)
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Track": st.column_config.TextColumn(width="large"),
                    "Label": st.column_config.TextColumn(width="medium"),
                    "Current Rank": st.column_config.NumberColumn(width="small"),
                    "Total Streams": st.column_config.TextColumn(width="medium"),
                    "Best Rank": st.column_config.NumberColumn(width="small"),
                    "Days Charted": st.column_config.NumberColumn(width="small"),
                    "Appearances": st.column_config.NumberColumn(width="small"),
                }
            )
            
            st.divider()
            
            # Full rankings table
            st.markdown("#### 📋 Full Rankings (Top 50)")
            
            full_display = tracks_df.head(50)[[
                'artist_title', 'label', 'rank', 'total_streams', 
                'best_rank', 'days_charted'
            ]].copy()
            
            full_display.columns = ['Track', 'Label', 'Current Rank', 'Total Streams', 'Best Rank', 'Days Charted']
            full_display['Total Streams'] = full_display['Total Streams'].apply(format_number)
            full_display['Current Rank'] = full_display['Current Rank'].astype(int)
            full_display['Best Rank'] = full_display['Best Rank'].astype(int)
            full_display['Days Charted'] = full_display['Days Charted'].astype(int)
            
            st.dataframe(
                full_display,
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            st.info("No track data available for the selected period")
    
    with tab2:  # ARTISTS
        st.subheader("🎤 Artist Performance")
        
        tracks_df = get_top_tracks_by_streams(limit=100)
        
        if not tracks_df.empty:
            # Group by artist
            artist_summary = tracks_df.groupby('artist_title').agg({
                'total_streams': 'sum',
                'artist_title': 'count'
            }).rename(columns={'artist_title': 'track_count'}).sort_values('total_streams', ascending=False)
            
            st.markdown("#### Top Artists by Total Streams")
            
            top_artists = artist_summary.head(20).reset_index()
            top_artists.columns = ['Artist', 'Total Streams', 'Track Count']
            top_artists['Total Streams'] = top_artists['Total Streams'].apply(format_number)
            
            st.dataframe(top_artists, use_container_width=True, hide_index=True)
        else:
            st.info("No artist data available")
    
    with tab3:  # LABELS
        st.subheader("🏷️ Label Performance")
        
        label_df = get_label_summary()
        
        if not label_df.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Top Labels by Volume")
                
                display_labels = label_df[[
                    'label', 'tracks', 'total_streams', 'best_rank'
                ]].copy()
                
                display_labels.columns = ['Label', 'Tracks', 'Total Streams', 'Best Rank']
                display_labels['Total Streams'] = display_labels['Total Streams'].apply(format_number)
                display_labels['Best Rank'] = display_labels['Best Rank'].astype(int)
                
                st.dataframe(
                    display_labels.head(15),
                    use_container_width=True,
                    hide_index=True
                )
            
            with col2:
                st.markdown("#### Label Market Share")
                
                # Create pie chart
                fig = px.pie(
                    label_df.head(10),
                    values='total_streams',
                    names='label',
                    title="Top 10 Labels by Streams"
                )
                
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(
                    height=400,
                    paper_bgcolor='rgba(18,24,42,1)',
                    plot_bgcolor='rgba(18,24,42,1)',
                    font=dict(color='#e8eaf6'),
                    margin=dict(l=0, r=0, t=30, b=0)
                )
                
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No label data available")
    
    with tab4:  # MOVEMENT
        st.subheader("📈 Chart Movement")
        
        tracks_df = get_top_tracks_by_streams(limit=50)
        
        if not tracks_df.empty:
            # Calculate movement (best_rank vs current rank)
            tracks_df['movement'] = tracks_df['best_rank'] - tracks_df['rank']
            
            # Rising (positive movement)
            rising = tracks_df[tracks_df['movement'] > 0].head(10)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 📈 Rising Tracks")
                
                if not rising.empty:
                    rising_display = rising[[
                        'artist_title', 'label', 'rank', 'total_streams', 'movement'
                    ]].copy()
                    
                    rising_display.columns = ['Track', 'Label', 'Rank', 'Streams', 'Movement']
                    rising_display['Streams'] = rising_display['Streams'].apply(format_number)
                    
                    st.dataframe(rising_display, use_container_width=True, hide_index=True)
                else:
                    st.info("No rising tracks in current period")
            
            with col2:
                st.markdown("#### 📊 Trending Summary")
                
                total_tracks = len(tracks_df)
                rising_count = len(rising)
                steady = total_tracks - rising_count
                
                trend_data = {
                    'Status': ['Rising', 'Steady'],
                    'Count': [rising_count, steady]
                }
                
                fig = px.bar(
                    trend_data,
                    x='Status',
                    y='Count',
                    title='Track Movement Distribution'
                )
                
                fig.update_layout(
                    height=300,
                    paper_bgcolor='rgba(18,24,42,1)',
                    plot_bgcolor='rgba(18,24,42,1)',
                    font=dict(color='#e8eaf6'),
                    margin=dict(l=0, r=0, t=30, b=0),
                    showlegend=False
                )
                
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No movement data available")
    
    with tab5:  # ACQUISITION
        st.subheader("🎯 Market Acquisition")
        
        label_df = get_label_summary()
        
        if not label_df.empty:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_tracks = label_df['tracks'].sum()
                st.metric("Total Unique Tracks", int(total_tracks))
            
            with col2:
                total_labels = len(label_df)
                st.metric("Active Labels", int(total_labels))
            
            with col3:
                total_streams = label_df['total_streams'].sum()
                st.metric("Total Streams", format_number(total_streams))
            
            st.divider()
            
            # Trends
            st.markdown("#### Acquisition Metrics")
            
            metrics = label_df[[
                'label', 'tracks', 'total_streams', 'best_rank', 'days_in_chart'
            ]].copy()
            
            metrics.columns = ['Label', 'Tracks', 'Streams', 'Best Rank', 'Days in Chart']
            metrics['Streams'] = metrics['Streams'].apply(format_number)
            metrics['Best Rank'] = metrics['Best Rank'].astype(int)
            
            st.dataframe(
                metrics.head(20),
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            st.info("No acquisition data available")


# Export the render function for use in main app
__all__ = ['render_label_dashboard']
