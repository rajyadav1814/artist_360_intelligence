"""
Pulse Report - displays top tracks and performance metrics by label
Similar to Sony Latin Pulse design
"""

import numpy as np
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


def get_top_5_week_over_week() -> pd.DataFrame:
    """Get the top 5 tracks for the latest week vs prior week."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) as latest_date FROM spotify_daily")
            result = cur.fetchone()
            latest_date = result['latest_date'] if result else None
            if not latest_date:
                return pd.DataFrame()

            latest_date = pd.to_datetime(latest_date).date()
            current_start = latest_date - timedelta(days=6)
            prior_start = latest_date - timedelta(days=13)
            prior_end = latest_date - timedelta(days=7)

            query = """
                SELECT
                    artist_title,
                    label,
                    SUM(CASE WHEN date BETWEEN %s AND %s THEN streams ELSE 0 END) AS current_streams,
                    SUM(CASE WHEN date BETWEEN %s AND %s THEN streams ELSE 0 END) AS prior_streams,
                    MIN(CASE WHEN date BETWEEN %s AND %s THEN rank ELSE NULL END) AS current_best_rank,
                    MIN(CASE WHEN date BETWEEN %s AND %s THEN rank ELSE NULL END) AS prior_best_rank
                FROM spotify_daily
                WHERE date BETWEEN %s AND %s
                    AND label IS NOT NULL
                    AND streams > 0
                GROUP BY artist_title, label
                ORDER BY current_streams DESC
                LIMIT 10
            """

            cur.execute(
                query,
                (
                    current_start, latest_date,
                    prior_start, prior_end,
                    current_start, latest_date,
                    prior_start, prior_end,
                    prior_start, latest_date,
                )
            )
            result = cur.fetchall()
            if not result:
                return pd.DataFrame()

            df = pd.DataFrame(result)
            for col in ['current_streams', 'prior_streams', 'current_best_rank', 'prior_best_rank']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            df['stream_delta'] = df['current_streams'] - df['prior_streams']
            df['rank_delta'] = df['prior_best_rank'] - df['current_best_rank']

            return df.sort_values('current_streams', ascending=False).head(5)
    except Exception as e:
        logger.error(f"Error fetching weekly comparison data: {e}")
        return pd.DataFrame()


def get_top_10_weekly_trends(weeks: int = 10, top_n: int = 5) -> pd.DataFrame:
    """Get weekly best-rank trends for tracks that have stayed in the top 10."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) as latest_date FROM spotify_daily")
            result = cur.fetchone()
            latest_date = result['latest_date'] if result else None
            if not latest_date:
                return pd.DataFrame()

            latest_date = pd.to_datetime(latest_date).date()
            start_date = latest_date - timedelta(days=(weeks * 7) - 1)

            query = """
                SELECT
                    artist_title,
                    label,
                    date_trunc('week', date)::date AS week_start,
                    MIN(rank) AS best_rank
                FROM spotify_daily
                WHERE date BETWEEN %s AND %s
                    AND label IS NOT NULL
                GROUP BY artist_title, label, week_start
                HAVING MIN(rank) <= 10
                ORDER BY artist_title, week_start
            """
            cur.execute(query, (start_date, latest_date))
            result = cur.fetchall()
            if not result:
                return pd.DataFrame()

            df = pd.DataFrame(result)
            df['week_start'] = pd.to_datetime(df['week_start']).dt.date
            df['best_rank'] = pd.to_numeric(df['best_rank'], errors='coerce')

            summary = (
                df.groupby(['artist_title', 'label'])['week_start']
                .nunique()
                .reset_index(name='weeks_in_top_10')
                .sort_values(['weeks_in_top_10', 'artist_title'], ascending=[False, True])
            )

            top_tracks = summary.head(top_n)[['artist_title', 'label']]
            if top_tracks.empty:
                return pd.DataFrame()

            merged = df.merge(top_tracks, on=['artist_title', 'label'], how='inner')
            return merged.sort_values(['artist_title', 'week_start'])
    except Exception as e:
        logger.error(f"Error fetching top 10 weekly trends: {e}")
        return pd.DataFrame()


def get_acquisition_candidates(weeks_back: int = 10, limit: int = 10) -> pd.DataFrame:
    """Get acquisition candidate artists ranked by momentum and independent signal."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) AS latest_date FROM spotify_daily")
            result = cur.fetchone()
            latest_date = result['latest_date'] if result else None
            if not latest_date:
                return pd.DataFrame()

            latest_date = pd.to_datetime(latest_date).date()
            start_date = latest_date - timedelta(days=(weeks_back * 7) - 1)

            query = """
                SELECT
                    artist_title,
                    label,
                    date_trunc('week', date)::date AS week_start,
                    SUM(streams) AS week_streams,
                    MIN(rank) AS best_rank
                FROM spotify_daily
                WHERE date BETWEEN %s AND %s
                    AND streams > 0
                GROUP BY artist_title, label, week_start
            """
            cur.execute(query, (start_date, latest_date))
            rows = cur.fetchall()
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df['week_start'] = pd.to_datetime(df['week_start']).dt.date
            df['week_streams'] = pd.to_numeric(df['week_streams'], errors='coerce').fillna(0)
            df['best_rank'] = pd.to_numeric(df['best_rank'], errors='coerce').fillna(999)

            last_week = df['week_start'].max()
            prior_week = last_week - timedelta(days=7)
            current = df[df['week_start'] == last_week]
            prior = df[df['week_start'] == prior_week]
            if current.empty or prior.empty:
                return pd.DataFrame()

            merged = current.merge(
                prior[['artist_title', 'label', 'week_streams', 'best_rank']],
                on=['artist_title', 'label'],
                suffixes=('', '_prior')
            )
            if merged.empty:
                return pd.DataFrame()

            merged['stream_growth'] = merged['week_streams'] - merged['week_streams_prior']
            merged['growth_pct'] = merged['stream_growth'] / merged['week_streams_prior'].replace({0: 1})
            merged['rank_change'] = merged['best_rank_prior'] - merged['best_rank']
            merged['independent'] = merged['label'].fillna('').str.contains('independent', case=False, na=False)
            merged['latest_week'] = last_week
            merged['prior_week'] = prior_week
            merged['label'] = merged['label'].fillna('Independent')

            # Only keep candidates with positive week-over-week stream growth.
            merged = merged[merged['stream_growth'] > 0]
            if merged.empty:
                return pd.DataFrame()

            merged['score'] = merged['growth_pct'] * 1.2 + (merged['week_streams'] / 1_000_000)
            candidate_df = merged.sort_values(['independent', 'score'], ascending=[False, False]).head(limit)
            return candidate_df.reset_index(drop=True)
    except Exception as e:
        logger.error(f"Error fetching acquisition candidates: {e}")
        return pd.DataFrame()


def get_acquisition_candidate(artist_title: str = None, label: str = None, weeks_back: int = 10) -> dict:
    """Return a single acquisition candidate, optionally based on selected artist."""
    candidate_df = get_acquisition_candidates(weeks_back=weeks_back, limit=10)
    if candidate_df.empty:
        return {}

    if artist_title and label:
        candidate = candidate_df[
            (candidate_df['artist_title'] == artist_title) &
            (candidate_df['label'] == label)
        ]
        if candidate.empty:
            candidate = candidate_df.head(1)
    else:
        candidate = candidate_df.head(1)

    if candidate.empty:
        return {}

    candidate = candidate.iloc[0]
    label_tracks = (candidate_df[candidate_df['best_rank'] <= 100]['artist_title'].nunique())
    return {
        'artist_title': candidate['artist_title'],
        'label': candidate['label'],
        'latest_week': candidate['latest_week'],
        'prior_week': candidate['prior_week'],
        'latest_streams': int(candidate['week_streams']),
        'prior_streams': int(candidate['week_streams_prior']),
        'stream_growth': int(candidate['stream_growth']),
        'growth_pct': float(candidate['growth_pct'] * 100),
        'latest_rank': int(candidate['best_rank']),
        'prior_rank': int(candidate['best_rank_prior']),
        'rank_change': int(candidate['rank_change']),
        'tracks_in_top_100': int(label_tracks),
        'independent': bool(candidate['independent']),
    }


def get_streaming_trajectory(artist_title: str, label: str, weeks: int = 10) -> pd.DataFrame:
    """Get the weekly streaming trajectory for a given track."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) AS latest_date FROM spotify_daily")
            result = cur.fetchone()
            latest_date = result['latest_date'] if result else None
            if not latest_date:
                return pd.DataFrame()

            latest_date = pd.to_datetime(latest_date).date()
            start_date = latest_date - timedelta(days=(weeks * 7) - 1)

            query = """
                SELECT
                    date_trunc('week', date)::date AS week_start,
                    SUM(streams) AS week_streams
                FROM spotify_daily
                WHERE date BETWEEN %s AND %s
                    AND artist_title = %s
                    AND label = %s
                    AND streams > 0
                GROUP BY week_start
                ORDER BY week_start
            """
            cur.execute(query, (start_date, latest_date, artist_title, label))
            rows = cur.fetchall()
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df['week_start'] = pd.to_datetime(df['week_start']).dt.date
            df['week_streams'] = pd.to_numeric(df['week_streams'], errors='coerce').fillna(0)
            return df
    except Exception as e:
        logger.error(f"Error fetching streaming trajectory: {e}")
        return pd.DataFrame()


def get_risers_and_fallers(limit: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Get the top rising and falling tracks by rank movement between weeks."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) AS latest_date FROM spotify_daily")
            result = cur.fetchone()
            latest_date = result['latest_date'] if result else None
            if not latest_date:
                return pd.DataFrame(), pd.DataFrame()

            latest_date = pd.to_datetime(latest_date).date()
            current_start = latest_date - timedelta(days=6)
            prior_start = latest_date - timedelta(days=13)
            prior_end = latest_date - timedelta(days=7)

            query = """
                SELECT
                    artist_title,
                    label,
                    MIN(CASE WHEN date BETWEEN %s AND %s THEN rank ELSE NULL END) AS current_best_rank,
                    MIN(CASE WHEN date BETWEEN %s AND %s THEN rank ELSE NULL END) AS prior_best_rank,
                    SUM(CASE WHEN date BETWEEN %s AND %s THEN streams ELSE 0 END) AS current_streams,
                    SUM(CASE WHEN date BETWEEN %s AND %s THEN streams ELSE 0 END) AS prior_streams
                FROM spotify_daily
                WHERE date BETWEEN %s AND %s
                    AND streams > 0
                GROUP BY artist_title, label
            """
            cur.execute(
                query,
                (
                    current_start, latest_date,
                    prior_start, prior_end,
                    current_start, latest_date,
                    prior_start, prior_end,
                    prior_start, latest_date,
                )
            )
            rows = cur.fetchall()
            if not rows:
                return pd.DataFrame(), pd.DataFrame()

            df = pd.DataFrame(rows)
            df['current_best_rank'] = pd.to_numeric(df['current_best_rank'], errors='coerce')
            df['prior_best_rank'] = pd.to_numeric(df['prior_best_rank'], errors='coerce')
            df['current_streams'] = pd.to_numeric(df['current_streams'], errors='coerce').fillna(0)
            df['prior_streams'] = pd.to_numeric(df['prior_streams'], errors='coerce').fillna(0)
            df = df.dropna(subset=['current_best_rank', 'prior_best_rank'])
            if df.empty:
                return pd.DataFrame(), pd.DataFrame()

            df['rank_change'] = df['prior_best_rank'] - df['current_best_rank']
            df['stream_delta'] = df['current_streams'] - df['prior_streams']

            risers = df[df['rank_change'] > 0].sort_values(['rank_change', 'current_best_rank'], ascending=[False, True]).head(limit)
            fallers = df[df['rank_change'] < 0].sort_values(['rank_change', 'current_best_rank'], ascending=[True, True]).head(limit)
            return risers, fallers
    except Exception as e:
        logger.error(f"Error fetching risers/fallers: {e}")
        return pd.DataFrame(), pd.DataFrame()


def get_top_artists_by_streams(limit: int = 20) -> pd.DataFrame:
    """Return aggregated top artists by total streams from the latest week."""
    tracks_df = get_top_tracks_by_streams(limit=500)
    if tracks_df.empty:
        return pd.DataFrame()

    artist_summary = (
        tracks_df.groupby('artist_title', as_index=False)
        .agg(
            total_streams=('total_streams', 'sum'),
            track_count=('artist_title', 'nunique'),
            best_rank=('best_rank', 'min')
        )
        .sort_values('total_streams', ascending=False)
    )
    return artist_summary.head(limit)


def get_label_weekly_trends(weeks: int = 6, top_n: int = 8) -> pd.DataFrame:
    """Get weekly label stream trends for the top labels."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) AS latest_date FROM spotify_daily")
            result = cur.fetchone()
            latest_date = result['latest_date'] if result else None
            if not latest_date:
                return pd.DataFrame()

            latest_date = pd.to_datetime(latest_date).date()
            start_date = latest_date - timedelta(days=(weeks * 7) - 1)

            query = """
                SELECT
                    date_trunc('week', date)::date AS week_start,
                    label,
                    SUM(streams) AS week_streams
                FROM spotify_daily
                WHERE date BETWEEN %s AND %s
                    AND label IS NOT NULL
                    AND streams > 0
                GROUP BY week_start, label
            """
            cur.execute(query, (start_date, latest_date))
            rows = cur.fetchall()
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df['week_start'] = pd.to_datetime(df['week_start']).dt.date
            df['week_streams'] = pd.to_numeric(df['week_streams'], errors='coerce').fillna(0)

            top_labels = (
                df.groupby('label')['week_streams']
                .sum()
                .nlargest(top_n)
                .index
                .tolist()
            )
            return df[df['label'].isin(top_labels)].sort_values(['label', 'week_start'])
    except Exception as e:
        logger.error(f"Error fetching label weekly trends: {e}")
        return pd.DataFrame()


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


def render_pulse_report():
    """Main render function for the Pulse Report"""
    
    def render_metric_card(title: str, value: str, subtitle: str) -> None:
        st.markdown(
            f"""
            <div class='kpi-card'>
                <div class='metric-title'>{title}</div>
                <div class='metric-value'>{value}</div>
                <div class='metric-subtitle'>{subtitle}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <style>
        /* Global Theme Variables */
        :root {
            --primary-bg: #0a0e1a;
            --secondary-bg: #111827;
            --tertiary-bg: #1e293b;
            --accent-primary: #3b82f6;
            --accent-secondary: #8b5cf6;
            --accent-success: #10b981;
            --accent-warning: #f59e0b;
            --accent-danger: #ef4444;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-light: rgba(148, 163, 184, 0.1);
            --border-medium: rgba(148, 163, 184, 0.2);
            --shadow-light: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            --shadow-medium: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            --shadow-heavy: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
            --gradient-primary: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
            --gradient-secondary: linear-gradient(135deg, #10b981 0%, #3b82f6 100%);
        }

        /* Animations */
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        @keyframes shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }

        /* Base Styles */
        .dashboard-container {
            background: var(--primary-bg);
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.6;
        }

        /* Hero Section */
        .top-hero {
            background: var(--gradient-primary);
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 24px;
            padding: 2rem 2.5rem;
            margin-bottom: 2rem;
            position: relative;
            overflow: hidden;
            animation: fadeInUp 0.8s ease-out;
        }
        .top-hero::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.05) 50%, transparent 70%);
            animation: shimmer 3s infinite;
        }
        .hero-title {
            font-size: 2.5rem;
            font-weight: 900;
            letter-spacing: -0.05em;
            margin-bottom: 0.5rem;
            color: #ffffff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
            position: relative;
            z-index: 1;
        }
        .hero-meta {
            color: rgba(255, 255, 255, 0.9);
            font-size: 1.1rem;
            font-weight: 500;
            position: relative;
            z-index: 1;
        }

        /* Section Titles */
        .section-title {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 1.25rem;
            font-weight: 700;
            margin-bottom: 2.25rem;
            color: var(--text-primary);
            padding: 0.5rem 0;
            border-bottom: 2px solid var(--accent-primary);
            animation: fadeInUp 0.6s ease-out;
        }
        .section-title::before {
            content: '';
            width: 4px;
            height: 24px;
            background: var(--gradient-primary);
            border-radius: 2px;
        }

        .section-block {
            margin-bottom: 2.5rem;
        }

        .section-panel {
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid var(--border-medium);
            border-radius: 22px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.75rem;
        }

        .section-panel-title {
            font-size: 1rem;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.85rem;
        }

        .stDataFrame {
            border-radius: 18px !important;
            background: rgba(15, 23, 42, 0.96) !important;
            border: 1px solid rgba(148, 163, 184, 0.12) !important;
            overflow: hidden !important;
            margin-bottom: 1.75rem !important;
        }

        /* Metric Cards */
        .kpi-card {
            background: var(--secondary-bg);
            border: 1px solid var(--border-medium);
            border-radius: 20px;
            padding: 1.5rem;
            min-height: 140px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
            animation: fadeInUp 0.7s ease-out;
            margin-bottom: 1.75rem;
        }
        .kpi-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: var(--gradient-primary);
        }
        .kpi-card:hover {
            transform: translateY(-4px);
            box-shadow: var(--shadow-heavy);
            border-color: var(--accent-primary);
        }
        .kpi-card .metric-title {
            font-size: 0.875rem;
            color: var(--text-secondary);
            letter-spacing: 0.05em;
            text-transform: uppercase;
            margin-bottom: 0.75rem;
            font-weight: 600;
        }
        .kpi-card .metric-value {
            font-size: 2.25rem;
            font-weight: 900;
            color: var(--text-primary);
            line-height: 1;
            margin-bottom: 0.5rem;
        }
        .kpi-card .metric-subtitle {
            color: var(--accent-primary);
            font-size: 0.875rem;
            font-weight: 500;
        }

        /* Data Tables */
        .data-table {
            background: var(--secondary-bg);
            border: 1px solid var(--border-light);
            border-radius: 16px;
            overflow: hidden;
            animation: fadeInUp 0.8s ease-out;
            margin-bottom: 1.75rem;
        }
        .table-box {
            margin-bottom: 2rem;
        }
        .data-table th {
            background: var(--tertiary-bg);
            color: var(--text-primary);
            font-weight: 700;
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border-medium);
        }
        .data-table td {
            padding: 0.875rem 1rem;
            border-bottom: 1px solid var(--border-light);
            color: var(--text-secondary);
        }
        .data-table tr:hover {
            background: rgba(59, 130, 246, 0.05);
        }

        /* Mini Cards */
        .mini-card {
            background: var(--secondary-bg);
            border: 1px solid var(--border-medium);
            border-radius: 16px;
            padding: 1.25rem;
            transition: all 0.3s ease;
            animation: fadeInUp 0.6s ease-out;
        }
        .mini-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-medium);
            border-color: var(--accent-primary);
        }
        .mini-stat {
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.5rem;
            font-weight: 600;
        }
        .mini-value {
            font-size: 1.75rem;
            font-weight: 800;
            color: var(--text-primary);
            line-height: 1.1;
        }

        /* Acquisition Card */
        .acquisition-card {
            background: var(--gradient-secondary);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 24px;
            padding: 2rem;
            margin-bottom: 1.5rem;
            position: relative;
            overflow: hidden;
            animation: fadeInUp 0.8s ease-out;
        }
        .acquisition-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.03) 50%, transparent 70%);
            animation: shimmer 4s infinite;
        }
        .acquisition-title {
            font-size: 1.125rem;
            color: #10b981;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.5rem;
            font-weight: 700;
        }
        .acquisition-artist {
            font-size: 2rem;
            font-weight: 900;
            margin-bottom: 0.5rem;
            color: #ffffff;
        }
        .acquisition-meta {
            color: rgba(255, 255, 255, 0.9);
            font-size: 1rem;
            margin-bottom: 1.5rem;
        }
        .acquisition-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .acquisition-metric {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }
        .acquisition-metric-label {
            color: rgba(255, 255, 255, 0.8);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }
        .acquisition-metric-value {
            color: #ffffff;
            font-size: 1.25rem;
            font-weight: 800;
        }
        .acquisition-note {
            color: rgba(255, 255, 255, 0.9);
            font-size: 0.95rem;
            line-height: 1.5;
        }

        /* Chart Styling */
        .plotly-chart {
            background: var(--secondary-bg) !important;
            border-radius: 16px;
            border: 1px solid var(--border-light);
            overflow: hidden;
            margin-bottom: 1.75rem;
        }

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            background: var(--secondary-bg);
            border-radius: 12px;
            padding: 0.5rem;
            margin-bottom: 1rem;
        }
        .stTabs [data-baseweb="tab"] {
            background: transparent;
            color: var(--text-secondary);
            font-weight: 600;
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background: rgba(59, 130, 246, 0.1);
            color: var(--text-primary);
        }
        .stTabs [aria-selected="true"] {
            background: var(--gradient-primary) !important;
            color: #ffffff !important;
        }

        /* Info Messages */
        .stInfo {
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 12px;
            color: var(--text-primary);
        }

        /* Responsive Design */
        @media (max-width: 768px) {
            .top-hero {
                padding: 1.5rem 1rem;
            }
            .hero-title {
                font-size: 2rem;
            }
            .kpi-card {
                min-height: 120px;
                padding: 1rem;
            }
            .acquisition-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }

        /* Acquisition Section Styles */
        .acquisition-header {
            font-size: 0.85rem;
            color: #82d3a0;
            text-transform: uppercase;
            letter-spacing: 0.16em;
            margin-bottom: 0.5rem;
        }

        .acquisition-artist {
            font-size: 1.8rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
        }

        .acquisition-meta {
            color: #94a3b8;
            font-size: 0.95rem;
        }

        .acquisition-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.85rem;
            width: min(100%, 460px);
        }

        .acquisition-description {
            margin-top: 1rem;
            color: #94a3b8;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    monday, sunday = get_weekly_date_range()
    week_num = monday.strftime("%W")
    date_range = f"{monday.strftime('%B %d')} - {sunday.strftime('%B %d, %Y')}"

    st.markdown(
        f"""
        <div class='top-hero'>
            <div class='hero-title'>Pulse Report</div>
            <div class='hero-meta'>{date_range} • Live Spotify weekly performance</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["RANKINGS", "ARTISTS", "LABELS", "MOVEMENT", "ACQUISITION"])

    with tab1:
        st.markdown("<div class='section-title'>📊 Rankings</div>", unsafe_allow_html=True)
        tracks_df = get_top_tracks_by_streams(limit=100)
        rank_stats = get_rank_statistics()
        if not tracks_df.empty:
            cols = st.columns(4, gap='large')
            with cols[0]:
                render_metric_card("TOP 100 STREAMS", format_number(rank_stats.get('top_100_avg', 0)), "Total volume for Top 100 entries")
            with cols[1]:
                render_metric_card("RANK 100", format_number(rank_stats.get('rank_100_streams', 0)), "Streams at rank 100")
            with cols[2]:
                render_metric_card("RANK 20", format_number(rank_stats.get('rank_20_streams', 0)), "Streams at rank 20")
            with cols[3]:
                render_metric_card("RANK 30", format_number(rank_stats.get('rank_30_streams', 0)), "Streams at rank 30")

            st.markdown("<div class='section-note'>Top 5 most-streamed tracks and the broader ranking momentum for the current rolling week.</div>", unsafe_allow_html=True)
            top_5 = tracks_df.head(5).copy()
            top_5['total_streams'] = top_5['total_streams'].apply(format_number)
            top_5['rank'] = top_5['rank'].astype(int)
            top_5['best_rank'] = top_5['best_rank'].astype(int)
            top_5['days_charted'] = top_5['days_charted'].astype(int)
            st.dataframe(
                top_5[['artist_title', 'label', 'rank', 'total_streams', 'best_rank', 'days_charted']].rename(
                    columns={
                        'artist_title': 'Track',
                        'label': 'Label',
                        'rank': 'Current Rank',
                        'total_streams': 'Total Streams',
                        'best_rank': 'Best Rank',
                        'days_charted': 'Days Charted',
                    }
                ),
                use_container_width=True,
                hide_index=True,
                height=320,
            )

            st.markdown("<div class='section-title'>📈 Weekly Comparison</div>", unsafe_allow_html=True)
            compare_df = get_top_5_week_over_week()
            if not compare_df.empty:
                compare_df_display = compare_df.copy()
                compare_df_display['current_streams'] = compare_df_display['current_streams'].apply(format_number)
                compare_df_display['prior_streams'] = compare_df_display['prior_streams'].apply(format_number)
                compare_df_display['stream_delta'] = compare_df_display['stream_delta'].apply(format_number)
                compare_df_display[['current_best_rank', 'prior_best_rank', 'rank_delta']] = compare_df_display[['current_best_rank', 'prior_best_rank', 'rank_delta']].astype(int)
                st.dataframe(
                    compare_df_display.rename(columns={
                        'artist_title': 'Track',
                        'label': 'Label',
                        'current_streams': 'Current Week',
                        'prior_streams': 'Prior Week',
                        'current_best_rank': 'Rank WK Current',
                        'prior_best_rank': 'Rank WK Prior',
                        'stream_delta': 'Stream Δ',
                        'rank_delta': 'Rank Δ',
                    })[[
                        'Track', 'Label', 'Current Week', 'Prior Week', 'Stream Δ', 'Rank WK Current', 'Rank WK Prior', 'Rank Δ'
                    ]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Weekly comparison data is not available yet.")

            st.markdown("<div class='section-title'>📉 Consistent Top 10 Performance</div>", unsafe_allow_html=True)
            trend_df = get_top_10_weekly_trends()
            if not trend_df.empty:
                fig = px.line(
                    trend_df,
                    x='week_start',
                    y='best_rank',
                    color='artist_title',
                    markers=True,
                    labels={'week_start': 'Week', 'best_rank': 'Best Rank'},
                )
                fig.update_yaxes(autorange='reversed', title='Best Rank', dtick=1)
                fig.update_layout(
                    height=420,
                    paper_bgcolor='rgba(15,23,42,0.98)',
                    plot_bgcolor='rgba(15,23,42,0.98)',
                    font=dict(color='#e2e8f0'),
                    legend_title_text='Track',
                    margin=dict(l=0, r=0, t=30, b=0),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Consistent Top 10 trend data is not available.")
        else:
            st.info("No track rankings found for the current period.")

    with tab2:
        st.markdown("<div class='section-title'>🎧 Artist Spotlight</div>", unsafe_allow_html=True)
        artists = get_top_artists_by_streams(limit=20)
        if not artists.empty:
            artists['total_streams'] = artists['total_streams'].apply(format_number)
            artists_display = artists.rename(columns={
                'artist_title': 'Artist',
                'total_streams': 'Total Streams',
                'track_count': 'Tracks in Top 100',
                'best_rank': 'Best Rank',
            })
            st.dataframe(artists_display, use_container_width=True, hide_index=True, height=520)

            fig = px.bar(
                artists.head(12),
                x='total_streams',
                y='artist_title',
                orientation='h',
                labels={'total_streams': 'Total Streams', 'artist_title': 'Artist'},
                title='Top Artists by Total Weekly Streams',
            )
            fig.update_layout(
                height=420,
                paper_bgcolor='rgba(15,23,42,0.98)',
                plot_bgcolor='rgba(15,23,42,0.98)',
                font=dict(color='#e2e8f0'),
                margin=dict(l=0, r=0, t=30, b=0),
                yaxis={'categoryorder': 'total ascending'},
            )
            fig.update_xaxes(tickformat=',')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No artist performance data available.")

    with tab3:
        st.markdown("<div class='section-title'>🏷️ Label Scorecard</div>", unsafe_allow_html=True)
        label_df = get_label_summary()
        if not label_df.empty:
            label_df['stream_share'] = label_df['total_streams'] / label_df['total_streams'].sum()
            label_df = label_df.sort_values('total_streams', ascending=False)
            label_df['total_streams'] = label_df['total_streams'].apply(format_number)
            label_df['stream_share'] = label_df['stream_share'].apply(lambda x: f"{x:.1%}")
            st.dataframe(
                label_df.rename(columns={
                    'label': 'Label',
                    'tracks': 'Tracks',
                    'total_streams': 'Total Streams',
                    'best_rank': 'Best Rank',
                    'stream_share': 'Share',
                })[['Label', 'Tracks', 'Total Streams', 'Best Rank', 'Share']].head(12),
                use_container_width=True,
                hide_index=True,
                height=520,
            )

            label_trends = get_label_weekly_trends(weeks=6, top_n=8)
            if not label_trends.empty:
                label_trends = label_trends.copy()
                label_trends['week_streams_m'] = label_trends['week_streams'] / 1_000_000

                max_streams = label_trends['week_streams_m'].max()
                nonzero_streams = label_trends['week_streams_m'][label_trends['week_streams_m'] > 0]
                if len(nonzero_streams) >= 4:
                    q75 = np.percentile(nonzero_streams, 75)
                else:
                    q75 = nonzero_streams.median() if not nonzero_streams.empty else 0

                if q75 > 0 and max_streams / q75 > 20:
                    axis_type = 'log'
                    subtitle_text = ' (log scale)'
                else:
                    axis_type = 'linear'
                    subtitle_text = ''

                fig = px.line(
                    label_trends,
                    x='week_start',
                    y='week_streams_m',
                    color='label',
                    markers=True,
                    labels={'week_start': 'Week', 'week_streams_m': 'Streams (M)', 'label': 'Label'},
                    title='Top Label Weekly Stream Trends',
                )
                fig.update_traces(
                    mode='lines+markers',
                    marker=dict(size=6),
                    line=dict(width=2.5),
                    hovertemplate='<b>%{fullData.name}</b><br>%{x|%b %d}: %{y:.1f}M<extra></extra>',
                )
                fig.update_layout(
                    height=420,
                    paper_bgcolor='rgba(15,23,42,0.98)',
                    plot_bgcolor='rgba(15,23,42,0.98)',
                    font=dict(color='#e2e8f0'),
                    margin=dict(l=0, r=0, t=40, b=0),
                    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                    hovermode='x unified',
                    title=dict(text=f'Top Label Weekly Stream Trends{subtitle_text}', x=0.01, xanchor='left'),
                )
                fig.update_xaxes(
                    showgrid=False,
                    tickfont=dict(color='#cbd5e1'),
                    title_text='Week',
                )
                fig.update_yaxes(
                    type=axis_type,
                    tickformat=',.1f',
                    showgrid=True,
                    gridcolor='rgba(148,163,184,0.12)',
                    title_text='Streams (Million)',
                )
                st.plotly_chart(fig, use_container_width=True, config={'responsive': True})
            else:
                st.info("Label weekly trend data is not available.")
        else:
            st.info("No label summary data available.")

    with tab4:
        st.markdown("<div class='section-title'>⚡ Chart Movement</div>", unsafe_allow_html=True)
        risers, fallers = get_risers_and_fallers(limit=8)
        col1, col2 = st.columns(2, gap='large')

        with col1:
            st.markdown("<div class='section-panel'><div class='section-panel-title'>Top Risers</div></div>", unsafe_allow_html=True)
            if not risers.empty:
                risers_display = risers.copy()
                risers_display['current_streams'] = risers_display['current_streams'].apply(format_number)
                risers_display['prior_streams'] = risers_display['prior_streams'].apply(format_number)
                risers_display['rank_change'] = risers_display['rank_change'].astype(int)
                st.dataframe(
                    risers_display.rename(columns={
                        'artist_title': 'Track',
                        'label': 'Label',
                        'current_best_rank': 'Current Rank',
                        'prior_best_rank': 'Prior Rank',
                        'rank_change': 'Rank Δ',
                        'current_streams': 'Current Streams',
                        'prior_streams': 'Prior Streams',
                    })[['Track', 'Label', 'Current Rank', 'Prior Rank', 'Rank Δ', 'Current Streams', 'Prior Streams']],
                    use_container_width=True,
                    hide_index=True,
                    height=380,
                )
            else:
                st.info("No rising tracks available.")

        with col2:
            st.markdown("<div class='section-panel'><div class='section-panel-title'>Top Fallers</div></div>", unsafe_allow_html=True)
            if not fallers.empty:
                fallers_display = fallers.copy()
                fallers_display['current_streams'] = fallers_display['current_streams'].apply(format_number)
                fallers_display['prior_streams'] = fallers_display['prior_streams'].apply(format_number)
                fallers_display['rank_change'] = fallers_display['rank_change'].astype(int)
                st.dataframe(
                    fallers_display.rename(columns={
                        'artist_title': 'Track',
                        'label': 'Label',
                        'current_best_rank': 'Current Rank',
                        'prior_best_rank': 'Prior Rank',
                        'rank_change': 'Rank Δ',
                        'current_streams': 'Current Streams',
                        'prior_streams': 'Prior Streams',
                    })[['Track', 'Label', 'Current Rank', 'Prior Rank', 'Rank Δ', 'Current Streams', 'Prior Streams']],
                    use_container_width=True,
                    hide_index=True,
                    height=380,
                )
            else:
                st.info("No falling tracks available.")

    with tab5:
        st.markdown("<div class='section-title'>🎯 Acquisition & Momentum</div>", unsafe_allow_html=True)
        candidate_df = get_acquisition_candidates()
        if not candidate_df.empty:
            option_labels = [
                f"{row['artist_title']} — {row['label']} ({format_number(row['week_streams'])} streams)"
                for _, row in candidate_df.iterrows()
            ]
            selected_index = st.selectbox(
                "Select candidate artist",
                list(range(len(option_labels))),
                format_func=lambda i: option_labels[i],
            )
            selected_row = candidate_df.iloc[selected_index]
            candidate = get_acquisition_candidate(
                artist_title=selected_row['artist_title'],
                label=selected_row['label'],
            )

            st.markdown(
                f"""
                <div class='table-box'>
                    <div style='display:flex; justify-content:space-between; flex-wrap:wrap; gap:16px;'>
                        <div>
                            <div class='acquisition-header'>Acquisition Signal</div>
                            <div class='acquisition-artist'>{candidate['artist_title']}</div>
                            <div class='acquisition-meta'>Label: {candidate['label']} • {"Independent" if candidate['independent'] else "Major"}</div>
                        </div>
                        <div class='acquisition-grid'>
                            <div class='mini-card'><div class='mini-stat'>Latest Week Rank</div><div class='mini-value'>{candidate['latest_rank']}</div></div>
                            <div class='mini-card'><div class='mini-stat'>Latest Week Streams</div><div class='mini-value'>{format_number(candidate['latest_streams'])}</div></div>
                            <div class='mini-card'><div class='mini-stat'>WoW Growth</div><div class='mini-value'>{format_number(candidate['stream_growth'])} ({candidate['growth_pct']:.0f}%)</div></div>
                            <div class='mini-card'><div class='mini-stat'>Tracks in Top 100</div><div class='mini-value'>{candidate['tracks_in_top_100']}</div></div>
                        </div>
                    </div>
                    <div class='acquisition-description'>This candidate is showing accelerating momentum and strong label acquisition signal. Review the weekly trajectory and consider prioritized attention for licensing or partnership.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            trajectory_df = get_streaming_trajectory(candidate['artist_title'], candidate['label'])
            if not trajectory_df.empty:
                fig = px.line(
                    trajectory_df,
                    x='week_start',
                    y='week_streams',
                    markers=True,
                    labels={'week_start': 'Week', 'week_streams': 'Streams'},
                    title='Candidate Weekly Streaming Trajectory',
                )
                fig.update_layout(
                    height=440,
                    paper_bgcolor='rgba(15,23,42,0.98)',
                    plot_bgcolor='rgba(15,23,42,0.98)',
                    font=dict(color='#e2e8f0'),
                    margin=dict(l=0, r=0, t=30, b=0),
                )
                fig.update_yaxes(tickformat=',')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info('Streaming trajectory data unavailable for this candidate.')
        else:
            st.info('No acquisition signal available for the current period.')


# Export the render function for use in main app
__all__ = ['render_pulse_report']
