"""
Music Analytics AI Agent — Token-Optimized with Categorized Suggestions
Changes from original:
1. PLAN_SYSTEM reduced ~60%: removed verbose examples, collapsed rules into compact bullets
2. SCHEMA_CONTEXT trimmed ~40%: removed redundant relationship prose, kept only join keys
3. _summarize_results: CSV preview reduced 5→3 rows, max_tokens 200→150
4. _claude_chat_json: max_tokens default 3000→1200 (SQL plan never needs 3000)
5. Question pre-routing: simple/common questions skip the AI plan call entirely
6. SUMMARY_SYSTEM trimmed: removed redundant rules
7. NEW: CATEGORIZED_SUGGESTIONS bank with 5 categories shown in empty state
8. NEW: _render_empty_state rebuilt with category grid (Performance, Trending, Rankings, Cross-platform, Geography)
All accuracy-critical logic (SQL safety, artist detection, retry, fallback) is unchanged.
"""

import json
import os
import re
import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import anthropic
from streamlit.errors import StreamlitSecretNotFoundError

from src.ai.advanced_visualizations import (
    render_multi_chart_view,
    render_insights_dashboard,
)
from src.database.connection import get_connection
from dotenv import load_dotenv

load_dotenv()

# ─── Constants ────────────────────────────────────────────────────────────────

ALLOWED_TABLES = {
    "artists",
    "itunes_artist_rankings",
    "spotify_artists",
    "trending_artists_monthly",
    "artist_details",
    "scrape_runs",
    "spotify_daily",
    "itunes_daily",
}

SCHEMA_CONTEXT = """
Tables (PostgreSQL):
artists(id,name)
itunes_artist_rankings(id,artist_id,rank,rank_change,total_points,itunes_points,spotify_points,apple_music_points,shazam_points,youtube_points,other_points,top_country,num_countries,scraped_at,scrape_date)
spotify_artists(id,artist_id,monthly_listeners,peak_listeners,peak_date,scraped_at,scrape_date)
trending_artists_monthly(id,artist_id,source,rank,rank_change,total_points,top_country,month,scraped_at)
artist_details(id,artist_id,songs_count,albums_count,countries_count,top_songs,top_albums,top_countries,scraped_at,scrape_date)
spotify_daily(id,date,country,rank,artist_title,days,peak,streams,streams_change,total_streams,label)
itunes_daily(id,date,country,rank,artist_title,days,peak,points,points_change,total_points,label)
scrape_runs(id,source,status,rows_upserted,error_msg,started_at,finished_at)

Joins: all artist tables join artists on artist_id=artists.id
daily tables: artist_title = 'Artist - Song Title'; label column = record label company
""".strip()

DANGEROUS_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy)\b",
    re.IGNORECASE,
)
TABLE_REF_RE = re.compile(
    r"\b(?:from|join)\s+([a-z_][a-z0-9_\.]*)(?!\s*\()",
    re.IGNORECASE,
)
SQL_RESERVED_FROM = {"year", "month", "day", "hour", "minute", "second", "date", "week", "quarter"}
CTE_NAME_RE = re.compile(r"(?:with|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)

SMALL_TALK_PATTERNS = [
    r"^\s*(hi|hello|hey|hii|yo)\s*$",
    r"^\s*(how are you|how r you|what's up|wassup)\s*[?!.]*\s*$",
    r"^\s*(thanks|thank you|ok|okay|cool)\s*[!.,]*\s*$",
]

CHART_TRIGGER_PATTERNS = [
    r"\bchart\b",
    r"\bgraph\b",
    r"\bplot\b",
    r"\bvisual",
    r"\btrend",
    r"\bcompare",
    r"\bdistribution\b",
    r"\bbreakdown\b",
    r"\bover time\b",
    r"\btop\s+\d+\b",
]

NO_CHART_PATTERNS = [
    r"\bwho is\b",
    r"\bwhat is\b",
    r"\bdescribe\b",
    r"\bprofile\b",
    r"\bdetails?\b",
    r"\bexplain\b",
    r"\btell me\b",
    r"\blist\b",
]

TABLE_TRIGGER_PATTERNS = [
    r"\btable\b",
    r"\bshow me the data\b",
    r"\bshow data\b",
    r"\braw data\b",
    r"\brows?\b",
    r"\brecords?\b",
    r"\blist\b",
    r"\bdetails?\b",
    r"\bcolumns?\b",
    r"\ball\b",
]

NO_TABLE_PATTERNS = [
    r"^\s*(hi|hello|hey|hii|yo)\s*$",
    r"\bsummary\b",
    r"\bsummarize\b",
    r"\bexplain\b",
    r"\bwhy\b",
    r"\bbrief\b",
    r"\bquick\b",
]

LOCAL_PLAN_PATTERNS = [
    r"\btop\s+\d+\s+artist",
    r"\btrending\b",
    r"\bmonthly listener",
    r"\bspotify listener",
    r"\bscrape\s+run",
    r"\brank(ing)?\b",
    r"\btop countr",
]

# ─── Categorized Suggestion Bank ──────────────────────────────────────────────

CATEGORIZED_SUGGESTIONS = {
    "performance": {
        "label": "Performance",
        "icon": "📈",
        "questions": [
            "Who are the top 10 artists by total Spotify streams right now, and how have their stream counts changed day over day?",
            "What is the average chart lifespan of a top-10 iTunes song before it drops out of the top 50?",
            "Which songs on Spotify had the biggest single-day stream drop — possible signs of fading momentum?",
        ],
    },
    "trending": {
        "label": "Trending",
        "icon": "🔥",
        "questions": [
            "What are the fastest-rising songs on iTunes in the last 7 days — which songs gained the most chart positions?",
            "Who are the trending artists this month, and which of them were outside the top 50 last month?",
            "Show the monthly trending movement for artists — who gained the most rank positions month over month on iTunes global?",
            "Identify breakout artists: who had zero iTunes presence last month but entered the top 100 this month?",
        ],
    },
    "rankings": {
        "label": "Rankings",
        "icon": "🏆",
        "questions": [
            "Which artists maintained a stable rank (no change) on iTunes for 3+ consecutive days — who has the most chart consistency?",
            "Which artists have the highest follower counts on Spotify, and how does follower count correlate with daily stream volume?",
            "Which artist has the most songs simultaneously charting across all platforms today?",
            "What is the rank distribution of songs by artist — do certain artists cluster at the top or spread across positions?",
            "Which songs are ranked #1 globally on both Spotify and iTunes today?",
        ],
    },
    "cross_platform": {
        "label": "Cross-platform",
        "icon": "🌐",
        "questions": [
            "Which songs are ranked #1 globally on both Spotify and iTunes today — and which artists dominate both platforms simultaneously?",
            "Build a cross-platform performance score for each artist using Spotify streams and iTunes rank — who tops the leaderboard?",
            "Which artist has the most songs simultaneously charting across Spotify and iTunes today?",
        ],
    },
    "geography": {
        "label": "Geography",
        "icon": "🗺️",
        "questions": [
            "Which artists appear in the top 20 on iTunes across the most countries — who has the broadest global reach?",
            "Which countries produce the most iTunes chart entries — what are the top 5 markets by artist representation?",
            "Which artists are charting in 10 or more countries on iTunes — who are the truly global acts in this dataset?",
        ],
    },
}


# ─── Secret / Config ──────────────────────────────────────────────────────────

def _read_secret(name: str) -> Optional[str]:
    try:
        if name in st.secrets:
            val = st.secrets.get(name)
            if val:
                return str(val).strip()
    except StreamlitSecretNotFoundError:
        pass
    try:
        ai_section = st.secrets.get("ai", {})
        if ai_section and name in ai_section:
            val = ai_section[name]
            if val:
                return str(val).strip()
    except (StreamlitSecretNotFoundError, Exception):
        pass
    env_val = os.getenv(name)
    if env_val:
        return env_val.strip()
    return None


def _resolve_api_key() -> Optional[str]:
    return _read_secret("CLAUDE_API_KEY")


def _resolve_model() -> str:
    return _read_secret("CLAUDE_MODEL") or "claude-opus-4-7"


def _get_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


# ─── Claude API Calls ─────────────────────────────────────────────────────────

def _extract_usage(response) -> Dict[str, int]:
    try:
        usage = response.usage
        return {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        }
    except Exception:
        return {"input_tokens": 0, "output_tokens": 0}


def _accumulate_tokens(usage: Dict[str, int]) -> None:
    ss = st.session_state
    ss.setdefault("ai_token_usage", {"input_tokens": 0, "output_tokens": 0})
    ss.ai_token_usage["input_tokens"] += usage.get("input_tokens", 0)
    ss.ai_token_usage["output_tokens"] += usage.get("output_tokens", 0)


def _claude_chat_json(
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
) -> Dict[str, Any]:
    client = _get_client(api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        _accumulate_tokens(_extract_usage(response))
        content = response.content[0].text if response.content else "{}"
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except (json.JSONDecodeError, anthropic.APIError) as e:
        st.warning(f"API error: {str(e)}")
        return {}


def _claude_chat_text(
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1000,
) -> str:
    client = _get_client(api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        _accumulate_tokens(_extract_usage(response))
        return response.content[0].text if response.content else ""
    except anthropic.APIError as e:
        st.warning(f"API error: {str(e)}")
        return ""


# ─── Query Helpers ────────────────────────────────────────────────────────────

def _extract_top_n(question: str) -> Optional[int]:
    match = re.search(r"\btop\s+(\d{1,3})\b", question.lower())
    if match:
        return max(1, min(int(match.group(1)), 100))
    return None


def _is_top_intent(question: str) -> bool:
    q = question.lower()
    return "top" in q or "highest" in q or "best" in q


def _force_rank_plan(question: str) -> Dict[str, Any]:
    limit = _extract_top_n(question) or 10
    return {
        "sql": f"""
            WITH latest AS (
                SELECT MAX(scrape_date) AS scrape_date
                FROM itunes_artist_rankings
            )
            SELECT a.name, i.rank, i.total_points, i.top_country
            FROM itunes_artist_rankings i
            JOIN artists a ON a.id = i.artist_id
            WHERE i.scrape_date = (SELECT scrape_date FROM latest)
            ORDER BY i.rank ASC
            LIMIT {limit}
        """,
        "chart_type": "multi",
        "x": "name",
        "y": "total_points",
        "title": f"Top {limit} Artists by Current Rank",
    }


_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "as", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "shall", "can",
    "not", "no", "nor", "so", "if", "then", "than", "too", "very",
    "just", "about", "above", "after", "again", "all", "also", "any",
    "because", "before", "between", "both", "each", "few", "get",
    "give", "got", "how", "into", "its", "let", "like", "long",
    "make", "many", "more", "most", "much", "must", "new", "now",
    "old", "only", "other", "our", "out", "over", "own", "put",
    "same", "she", "some", "still", "such", "take", "tell", "that",
    "their", "them", "these", "they", "this", "those", "through",
    "under", "until", "upon", "want", "way", "what", "when", "where",
    "which", "while", "who", "whom", "why", "you", "your", "his", "her",
    "him", "he", "it", "its", "hi", "hello", "hey", "the", "and", "for",
    "top", "best", "songs", "song", "album", "albums",
    "artist", "artists", "rank", "ranking", "rankings", "stream", "streams",
    "listener", "listeners", "monthly", "country", "countries", "point",
    "points", "chart", "charts", "show", "list", "data", "details",
    "performance", "compare", "comparison", "trend", "trending", "analysis",
    "analyze", "last", "week", "month", "year", "total", "number",
    "music", "label", "labels", "spotify", "itunes", "apple", "youtube",
    "shazam", "global", "current", "recent", "latest",
    "day", "days", "today", "yesterday", "previous", "daily", "weekly",
    "name", "names", "with", "without", "give", "show", "five", "ten",
    "track", "tracks", "title", "titles", "video", "videos", "release",
    "releases", "owner", "owners", "representative", "representatives",
}


def _find_artists_in_db(question: str) -> List[str]:
    raw_tokens = [t.strip() for t in re.split(r"\W+", question) if len(t.strip()) > 2]
    tokens = []
    for t in raw_tokens:
        t_l = t.lower()
        if t_l in _STOP_WORDS or t_l.isdigit():
            continue
        if t_l.endswith('s') and len(t_l) > 2:
            t_l = t_l[:-1]
        tokens.append(t_l)

    if not tokens:
        return []

    found_map = {}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for window_size in range(min(len(tokens), 4), 1, -1):
                for i in range(len(tokens) - window_size + 1):
                    phrase = " ".join(tokens[i:i + window_size])
                    cur.execute(
                        "SELECT name FROM artists WHERE lower(name) = %s LIMIT 1",
                        (phrase.lower(),),
                    )
                    row = cur.fetchone()
                    if row:
                        name = row["name"] if isinstance(row, dict) else row[0]
                        found_map[name] = max(found_map.get(name, 0), window_size * 10)

            for window_size in range(min(len(tokens), 4), 1, -1):
                for i in range(len(tokens) - window_size + 1):
                    phrase = " ".join(tokens[i:i + window_size])
                    cur.execute(
                        "SELECT name FROM artists WHERE lower(name) ILIKE %s LIMIT 3",
                        (f"%{phrase.lower()}%",),
                    )
                    for row in cur.fetchall():
                        name = row["name"] if isinstance(row, dict) else row[0]
                        if re.search(r'\b' + re.escape(phrase.lower()) + r'\b', name.lower()):
                            found_map[name] = max(found_map.get(name, 0), window_size * 5)

            matched_words = set()
            for name in found_map:
                for word in name.lower().split():
                    matched_words.add(word)

            for t in tokens:
                if t in matched_words:
                    continue
                cur.execute(
                    "SELECT name FROM artists WHERE lower(name) = %s OR lower(name) ILIKE %s LIMIT 1",
                    (t, f"% {t}%"),
                )
                row = cur.fetchone()
                if row:
                    name = row["name"] if isinstance(row, dict) else row[0]
                    found_map[name] = max(found_map.get(name, 0), 1)

    finally:
        try:
            conn.close()
        except Exception:
            pass

    sorted_artists = [k for k, v in sorted(found_map.items(), key=lambda item: item[1], reverse=True)]

    final = []
    for a in sorted_artists:
        is_collab = any(marker in a.lower() for marker in [' & ', ' x ', ' feat', ' and ', ', '])
        if is_collab:
            is_redundant = False
            for other in sorted_artists:
                if other != a and other.lower() in a.lower() and len(other) > 3:
                    is_redundant = True
                    break
            if is_redundant:
                continue
        if " " not in a and a.lower() not in tokens:
            continue
        final.append(a)
    return final


def _build_artist_profile(artist_name: str) -> Dict[str, Any]:
    safe_artist = artist_name.replace("'", "''")
    return {
        "sql": f"""
            SELECT
                a.name,
                i.rank AS current_rank,
                i.total_points,
                i.itunes_points,
                i.spotify_points,
                i.apple_music_points,
                i.shazam_points,
                i.youtube_points,
                i.top_country,
                i.num_countries,
                TO_CHAR(i.scrape_date, 'DD Mon YYYY') AS ranking_date,
                s.monthly_listeners,
                s.peak_listeners,
                ad.top_songs,
                ad.top_albums,
                ad.top_countries,
                ad.songs_count,
                ad.albums_count,
                ad.countries_count
            FROM artists a
            LEFT JOIN LATERAL (
                SELECT * FROM itunes_artist_rankings
                WHERE artist_id = a.id ORDER BY scrape_date DESC LIMIT 1
            ) i ON true
            LEFT JOIN LATERAL (
                SELECT * FROM spotify_artists
                WHERE artist_id = a.id ORDER BY scrape_date DESC LIMIT 1
            ) s ON true
            LEFT JOIN LATERAL (
                SELECT * FROM artist_details
                WHERE artist_id = a.id ORDER BY scraped_at DESC LIMIT 1
            ) ad ON true
            WHERE a.name ILIKE '%{safe_artist}%'
            LIMIT 1
        """,
        "chart_type": "none",
        "x": "name",
        "y": "total_points",
        "title": f"Complete Profile: {artist_name}",
        "show_chart": False,
        "show_table": True,
        "show_summary": True,
        "render_order": ["summary", "table"],
    }


def _local_plan(question: str) -> Dict[str, Any]:
    """Generate query plans locally without API calls."""
    q = question.lower()

    _is_song_query = any(kw in q for kw in ["song", "songs"])
    _is_daily_scope = any(kw in q for kw in ["last day", "yesterday", "today", "daily", "last 24"])
    if _is_top_intent(question) and _is_song_query and _is_daily_scope:
        limit = _extract_top_n(question) or 5
        return {
            "sql": f"""
                WITH latest AS (SELECT MAX(date) AS latest_date FROM spotify_daily)
                SELECT sd.rank, sd.artist_title, sd.label, sd.streams, sd.total_streams,
                       TO_CHAR(sd.date, 'DD Mon YYYY') AS date
                FROM spotify_daily sd
                WHERE sd.date = (SELECT latest_date FROM latest)
                  AND (sd.country = 'global' OR sd.country IS NULL)
                ORDER BY sd.streams DESC
                LIMIT {limit}
            """,
            "chart_type": "multi",
            "x": "artist_title",
            "y": "streams",
            "title": f"Top {limit} Songs — Last Day",
            "show_chart": True,
            "show_table": True,
            "show_summary": True,
            "render_order": ["summary", "chart", "table"],
        }

    if _is_top_intent(question) and not any(kw in q for kw in ["song", "album", "countr", "detail", "listener", "track"]):
        artists = _find_artists_in_db(question)
        if not artists:
            return _force_rank_plan(question)
    else:
        artists = _find_artists_in_db(question)

    if artists:
        limit = _extract_top_n(question) or 20
        safe_artists = [a.replace("'", "''") for a in artists]
        if len(artists) > 1:
            artist_conditions = " OR ".join([f"a.name ILIKE '%{a}%'" for a in safe_artists])
            where_clause = f"({artist_conditions})"
            title = f"Comparison: {', '.join(artists)}"
            sql_limit = len(artists)
        else:
            where_clause = f"a.name ILIKE '%{safe_artists[0]}%'"
            title = f"Details for {artists[0]}"
            sql_limit = 1

        if any(kw in q for kw in ["rank", "point", "performance"]):
            return {
                "sql": f"""
                    SELECT DISTINCT ON (a.id) a.name, i.rank, i.total_points, i.top_country as global_top_market,
                           ad.top_countries as all_charting_territories, ad.top_songs
                    FROM artists a
                    LEFT JOIN itunes_artist_rankings i ON i.artist_id = a.id
                    LEFT JOIN artist_details ad ON ad.artist_id = a.id
                    WHERE {where_clause}
                    ORDER BY a.id, i.scrape_date DESC NULLS LAST, ad.scraped_at DESC NULLS LAST
                    LIMIT {len(artists)}
                """,
                "chart_type": "multi",
                "x": "name",
                "y": "total_points",
                "title": f"Performance: {', '.join(artists)}",
            }

        if any(kw in q for kw in ["song", "songs", "album", "albums", "countr", "detail"]):
            return {
                "sql": f"""
                    SELECT DISTINCT ON (a.id) a.name, ad.top_songs, ad.top_albums, ad.top_countries,
                           ad.songs_count, ad.albums_count, ad.countries_count
                    FROM artist_details ad
                    JOIN artists a ON a.id = ad.artist_id
                    WHERE {where_clause}
                    ORDER BY a.id, ad.scraped_at DESC
                    LIMIT {sql_limit}
                """,
                "chart_type": "none",
                "x": "name",
                "y": "songs_count",
                "title": title,
                "show_chart": False,
                "show_table": True,
                "show_summary": True,
                "render_order": ["summary", "table"],
            }

        if any(kw in q for kw in ["listener", "listeners", "spotify", "stream"]):
            if len(artists) > 1:
                return {
                    "sql": f"""
                        SELECT DISTINCT ON (a.id) a.name, s.monthly_listeners, s.peak_listeners,
                               TO_CHAR(s.scrape_date, 'DD Mon YYYY') as scrape_date
                        FROM spotify_artists s
                        JOIN artists a ON a.id = s.artist_id
                        WHERE {where_clause}
                        ORDER BY a.id, s.scrape_date DESC
                        LIMIT {len(artists)}
                    """,
                    "chart_type": "multi",
                    "x": "name",
                    "y": "monthly_listeners",
                    "title": f"Spotify Comparison: {', '.join(artists)}",
                }
            return {
                "sql": f"""
                    SELECT a.name, s.monthly_listeners, s.peak_listeners,
                           TO_CHAR(s.scrape_date, 'DD Mon YYYY') as scrape_date
                    FROM spotify_artists s
                    JOIN artists a ON a.id = s.artist_id
                    WHERE {where_clause}
                    ORDER BY s.scrape_date DESC
                    LIMIT {limit}
                """,
                "chart_type": "multi",
                "x": "scrape_date",
                "y": "monthly_listeners",
                "title": f"Spotify Listeners for {artists[0]}",
            }

        if len(artists) > 1:
            return {
                "sql": f"""
                    SELECT DISTINCT ON (a.id) a.name, i.rank, i.total_points, i.top_country,
                           ad.songs_count, ad.countries_count
                    FROM artists a
                    LEFT JOIN itunes_artist_rankings i ON i.artist_id = a.id
                    LEFT JOIN artist_details ad ON ad.artist_id = a.id
                    WHERE {where_clause}
                    ORDER BY a.id, i.scrape_date DESC, ad.scraped_at DESC
                    LIMIT {len(artists)}
                """,
                "chart_type": "multi",
                "x": "name",
                "y": "total_points",
                "title": f"Comparison: {', '.join(artists)}",
            }

        return _build_artist_profile(artists[0])

    if _is_top_intent(question):
        return _force_rank_plan(question)

    if "trending" in q:
        return {
            "sql": """
                SELECT a.name, t.rank, t.total_points, t.top_country, t.month
                FROM trending_artists_monthly t
                JOIN artists a ON a.id = t.artist_id
                ORDER BY t.scraped_at DESC, t.rank ASC
                LIMIT 20
            """,
            "chart_type": "multi",
            "x": "name",
            "y": "total_points",
            "title": "Trending Artists This Month",
        }

    if "listener" in q or "spotify" in q:
        return {
            "sql": """
                SELECT a.name, MAX(s.monthly_listeners) AS monthly_listeners,
                       MAX(s.peak_listeners) AS peak_listeners
                FROM spotify_artists s
                JOIN artists a ON a.id = s.artist_id
                WHERE s.monthly_listeners IS NOT NULL
                GROUP BY a.id, a.name
                ORDER BY monthly_listeners DESC
                LIMIT 10
            """,
            "chart_type": "multi",
            "x": "name",
            "y": "monthly_listeners",
            "title": "Top 10 Artists by Monthly Listeners",
        }

    if "country" in q:
        return {
            "sql": """
                WITH latest AS (SELECT MAX(scrape_date) AS scrape_date FROM itunes_artist_rankings)
                SELECT top_country, COUNT(*) AS artists_count
                FROM itunes_artist_rankings
                WHERE scrape_date = (SELECT scrape_date FROM latest)
                AND top_country IS NOT NULL AND top_country <> ''
                GROUP BY top_country
                ORDER BY artists_count DESC
                LIMIT 12
            """,
            "chart_type": "multi",
            "x": "top_country",
            "y": "artists_count",
            "title": "Top Countries by Artist Presence",
        }

    if "song" in q or "songs" in q:
        return {
            "sql": """
                SELECT a.name as artist, ad.top_songs, ad.songs_count
                FROM artist_details ad
                JOIN artists a ON a.id = ad.artist_id
                WHERE ad.top_songs IS NOT NULL AND ad.top_songs <> ''
                ORDER BY ad.songs_count DESC, ad.scraped_at DESC
                LIMIT 10
            """,
            "chart_type": "none",
            "x": "artist",
            "y": "songs_count",
            "title": "Popular Songs Across Top Artists",
            "show_chart": False,
            "show_table": True,
            "show_summary": True,
            "render_order": ["summary", "table"],
        }

    if "scrape" in q or "run" in q or "activity" in q:
        return {
            "sql": """
                SELECT source, status, rows_upserted, finished_at
                FROM scrape_runs
                WHERE finished_at IS NOT NULL
                ORDER BY finished_at DESC
                LIMIT 30
            """,
            "chart_type": "multi",
            "x": "finished_at",
            "y": "rows_upserted",
            "title": "Processing Summary Over Time",
        }

    return {
        "sql": """
            WITH latest AS (SELECT MAX(scrape_date) AS scrape_date FROM itunes_artist_rankings)
            SELECT a.name, i.rank, i.total_points, i.top_country
            FROM itunes_artist_rankings i
            JOIN artists a ON a.id = i.artist_id
            WHERE i.scrape_date = (SELECT scrape_date FROM latest)
            ORDER BY i.rank ASC
            LIMIT 10
        """,
        "chart_type": "multi",
        "x": "name",
        "y": "total_points",
        "title": "Top 10 Artists by Current Rank",
    }


# ─── SQL Safety ───────────────────────────────────────────────────────────────

def _enforce_safe_sql(candidate_sql: str) -> str:
    sql = candidate_sql.strip().rstrip(";")
    sql_l = sql.lower()
    if not sql_l:
        raise ValueError("No query generated for this question.")
    if not (sql_l.startswith("select") or sql_l.startswith("with")):
        raise ValueError("Only SELECT queries are allowed.")
    if DANGEROUS_SQL_RE.search(sql):
        raise ValueError("Query contains unsafe keywords.")
    cte_names = {name.lower() for name in CTE_NAME_RE.findall(sql)}
    referenced_tables = {tbl.split(".")[-1].lower() for tbl in TABLE_REF_RE.findall(sql)}
    referenced_tables = referenced_tables.difference(SQL_RESERVED_FROM)
    unknown_tables = referenced_tables.difference(ALLOWED_TABLES.union(cte_names))
    if unknown_tables:
        raise ValueError("Query referenced unsupported tables: " + ", ".join(sorted(unknown_tables)))
    if not LIMIT_RE.search(sql):
        sql = f"{sql} LIMIT 250"
    return sql


# ─── Query Plan ───────────────────────────────────────────────────────────────

PLAN_SYSTEM = f"""You are a music analytics SQL expert. Return ONLY a JSON query plan.

Schema:
{SCHEMA_CONTEXT}

Table routing:
- songs/albums/countries for artist → artist_details (top_songs, top_albums, top_countries are text columns)
- rankings/points → itunes_artist_rankings
- listeners/Spotify → spotify_artists
- monthly trends → trending_artists_monthly
- daily track charts → spotify_daily (global: country='global') or itunes_daily (global: country='ww')
- scrape activity → scrape_runs

Key SQL rules:
- SELECT/WITH only. LIMIT 10-30 default.
- Latest data: MAX(scrape_date) or MAX(scraped_at) subquery
- Avoid duplicate rows: use DISTINCT ON (id) ORDER BY id, date DESC
- Format dates: TO_CHAR(date,'DD Mon YYYY')
- Artist exact match: artists.name = 'Name' (not ILIKE for specific names)
- Multiple artists: use OR / IN for all of them
- No arbitrary filters: If no artist is explicitly mentioned in the question or detected in context, DO NOT filter by specific artist names; query all tracks/labels globally.
- "label" column = record label company (in daily tables)
- "last day": date=(SELECT MAX(date) FROM spotify_daily)
- "last 7 days": date>=(SELECT MAX(date) FROM spotify_daily)-INTERVAL '7 days'
- Independent artists: label ILIKE '%Independent%'
- rank_change is VARCHAR — cast to integer for numeric comparison
- top_country = single best market; for full market list use artist_details.top_countries
- Debut = release_date within requested period; else call it "catalog hit"
- Percentage: value*100.0/SUM(value) OVER()

show_chart=true only if question asks for visual/trend/comparison/distribution.
show_table=true for list/detail/raw data questions.
show_chart=false for single-entity profile questions.

JSON response format (no explanation, no markdown):
{{"sql":"SELECT...","chart_type":"multi","x":"col","y":"col","title":"Title","show_summary":true,"show_chart":true,"show_table":false,"render_order":["summary","chart","table"]}}"""


def _is_locally_handleable(question: str) -> bool:
    q = question.lower()
    for pattern in LOCAL_PLAN_PATTERNS:
        if re.search(pattern, q):
            return True
    if _find_artists_in_db(question):
        simple_intents = ["listener", "song", "album", "rank", "point", "countr", "stream", "detail", "profile"]
        if any(kw in q for kw in simple_intents):
            return True
    return False


def _generate_plan(question: str, api_key: Optional[str], model: str) -> Dict[str, Any]:
    """Generate query plan via Claude or fall back to local heuristics."""
    if _is_locally_handleable(question):
        plan = _local_plan(question)
        plan["source"] = "local"
        return plan

    if api_key:
        try:
            detected = _find_artists_in_db(question)
            user_input = f"Question: {question}"
            if detected:
                user_input += f"\nArtists detected: {', '.join(detected)}"

            plan = _claude_chat_json(
                api_key,
                model,
                system=PLAN_SYSTEM,
                user=user_input,
                max_tokens=1200,
            )
            if plan and plan.get("sql"):
                sql_str = str(plan.get("sql", "")).strip()
                try:
                    _enforce_safe_sql(sql_str)
                except ValueError:
                    pass
                else:
                    return {
                        "sql": sql_str,
                        "chart_type": str(plan.get("chart_type") or ("multi" if _wants_chart(question) else "none")).lower(),
                        "x": plan.get("x"),
                        "y": plan.get("y"),
                        "title": plan.get("title") or "Results",
                        "show_summary": plan.get("show_summary", True),
                        "show_chart": plan.get("show_chart", True),
                        "show_table": plan.get("show_table", False),
                        "render_order": plan.get("render_order", ["summary", "chart", "table"]),
                        "source": "ai",
                    }
        except Exception:
            pass

    q_lower = question.lower()
    _is_song_q = any(kw in q_lower for kw in ["song", "songs", "stream", "streams"])
    if _is_top_intent(question) and not _is_song_q:
        plan = _force_rank_plan(question)
        plan["source"] = "local"
        return plan

    plan = _local_plan(question)
    plan["source"] = "local"
    return plan


# ─── Artist Data Availability ─────────────────────────────────────────────────

def _check_artist_data_availability(artist_name: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM artists WHERE name ILIKE %s LIMIT 1", (f"%{artist_name}%",))
            row = cur.fetchone()
            if not row:
                return {"found": False, "artist_id": None, "tables": {}}
            artist_id = row["id"] if isinstance(row, dict) else row[0]
            tables_check = {
                "itunes_artist_rankings": "Rankings (rank, points, countries)",
                "spotify_artists": "Spotify (monthly listeners, peak)",
                "artist_details": "Details (top songs, albums, countries)",
                "trending_artists_monthly": "Monthly trends",
            }
            available = {}
            for table, desc in tables_check.items():
                cur.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE artist_id = %s", (artist_id,))
                result = cur.fetchone()
                cnt = result["cnt"] if isinstance(result, dict) else result[0]
                if cnt > 0:
                    available[table] = {"count": cnt, "description": desc}
            return {"found": True, "artist_id": artist_id, "artist_name": artist_name, "tables": available}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _retry_with_available_data(question: str, artist_name: str) -> Optional[Dict[str, Any]]:
    availability = _check_artist_data_availability(artist_name)
    if not availability["found"] or not availability["tables"]:
        return None
    safe_artist = artist_name.replace("'", "''")
    tables = availability["tables"]

    if "artist_details" in tables:
        return {
            "sql": f"""
                SELECT a.name, ad.top_songs, ad.top_albums, ad.top_countries,
                       ad.songs_count, ad.albums_count, ad.countries_count
                FROM artist_details ad
                JOIN artists a ON a.id = ad.artist_id
                WHERE a.name ILIKE '%{safe_artist}%'
                ORDER BY ad.scraped_at DESC LIMIT 1
            """,
            "chart_type": "none", "x": "name", "y": "songs_count",
            "title": f"Available Details for {artist_name}",
            "show_chart": False, "show_table": True, "show_summary": True,
            "render_order": ["summary", "table"], "source": "retry",
        }
    if "spotify_artists" in tables:
        return {
            "sql": f"""
                SELECT a.name, s.monthly_listeners, s.peak_listeners,
                       TO_CHAR(s.scrape_date, 'DD Mon YYYY') as scrape_date
                FROM spotify_artists s
                JOIN artists a ON a.id = s.artist_id
                WHERE a.name ILIKE '%{safe_artist}%'
                ORDER BY s.scrape_date DESC LIMIT 10
            """,
            "chart_type": "multi", "x": "scrape_date", "y": "monthly_listeners",
            "title": f"Spotify Data for {artist_name}",
            "show_chart": True, "show_table": True, "show_summary": True,
            "render_order": ["summary", "chart", "table"], "source": "retry",
        }
    if "itunes_artist_rankings" in tables:
        return {
            "sql": f"""
                SELECT a.name, i.rank, i.total_points, i.top_country,
                       TO_CHAR(i.scrape_date, 'DD Mon YYYY') as scrape_date
                FROM itunes_artist_rankings i
                JOIN artists a ON a.id = i.artist_id
                WHERE a.name ILIKE '%{safe_artist}%'
                ORDER BY i.scrape_date DESC LIMIT 10
            """,
            "chart_type": "multi", "x": "scrape_date", "y": "total_points",
            "title": f"Rankings for {artist_name}",
            "show_chart": True, "show_table": True, "show_summary": True,
            "render_order": ["summary", "chart", "table"], "source": "retry",
        }
    if "trending_artists_monthly" in tables:
        return {
            "sql": f"""
                SELECT a.name, t.rank, t.total_points, t.top_country, t.month
                FROM trending_artists_monthly t
                JOIN artists a ON a.id = t.artist_id
                WHERE a.name ILIKE '%{safe_artist}%'
                ORDER BY t.scraped_at DESC LIMIT 10
            """,
            "chart_type": "multi", "x": "month", "y": "total_points",
            "title": f"Monthly Trends for {artist_name}",
            "show_chart": True, "show_table": True, "show_summary": True,
            "render_order": ["summary", "chart", "table"], "source": "retry",
        }
    return None


# ─── Data ─────────────────────────────────────────────────────────────────────

def _run_query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall() or []
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame([dict(r) for r in rows])
            for col in df.select_dtypes(include=['object']):
                df[col] = df[col].apply(lambda x: x.encode('latin1').decode('utf-8') if isinstance(x, str) and 'Ã' in x else x)
            return df
    finally:
        conn.close()


def _clean_result_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cleaned = df.copy()
    cleaned.columns = [str(c).strip() for c in cleaned.columns]
    for col in cleaned.columns:
        if pd.api.types.is_datetime64_any_dtype(cleaned[col]) or \
           cleaned[col].apply(lambda x: isinstance(x, (datetime.date, datetime.datetime))).all():
            try:
                cleaned[col] = cleaned[col].apply(lambda x: x.strftime('%d %b %Y') if pd.notnull(x) else "n/a")
            except:
                pass
    mask = pd.Series(True, index=cleaned.index)
    for col in cleaned.columns:
        mask &= cleaned[col].astype(str).str.strip().str.lower().eq(col.lower())
    if mask.any():
        cleaned = cleaned[~mask].copy()
    return cleaned


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return "n/a"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime('%d %b %Y')
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return f"{int(value):,}"
        return f"{value:,.2f}"
    return str(value)


def _generate_summary_stats(df: pd.DataFrame) -> Dict[str, Any]:
    stats: Dict[str, Any] = {"total_rows": len(df), "columns": df.columns.tolist()}
    for col in df.select_dtypes(include="number").columns:
        valid = df[col].dropna()
        if len(valid):
            stats[f"{col}_max"] = valid.max()
            stats[f"{col}_min"] = valid.min()
            stats[f"{col}_mean"] = valid.mean()
            stats[f"{col}_median"] = valid.median()
    return stats


# ─── Summarize ────────────────────────────────────────────────────────────────

SUMMARY_SYSTEM = """Music industry analyst. Write a 2-3 sentence executive summary.
- Lead with the single most important number or finding.
- Name specific artists/songs from the data.
- If requested data is missing, briefly note it.
- End with one forward-looking implication.
- No bullets, no headers, no markdown tables."""


def _summarize_results(
    question: str,
    sql: str,
    df: pd.DataFrame,
    api_key: Optional[str],
    model: str,
) -> str:
    if df.empty:
        artists = _find_artists_in_db(question)
        if artists:
            artist = artists[0]
            avail = _check_artist_data_availability(artist)
            if avail["found"] and not avail["tables"]:
                return f"📊 **{artist}** exists in our database but currently has no scraped performance data. The data may not have been collected yet."
            elif not avail["found"]:
                return f"📊 No artist matching your query was found. Try checking the spelling or searching for a different artist."
        return "📊 No results found for that question. Try adjusting your filters or asking differently."

    if not api_key:
        return "🤖 AI-powered analysis requires a Claude API key."

    stats = _generate_summary_stats(df)
    row_count = stats["total_rows"]
    preview_csv = df.head(3).to_csv(index=False)
    return _claude_chat_text(
        api_key,
        model,
        system=SUMMARY_SYSTEM,
        user=f"Q: {question}\nRows: {row_count}\nData:\n{preview_csv}",
        max_tokens=150,
    ) or f"Found {row_count} results."


# ─── Suggestions ──────────────────────────────────────────────────────────────

def _top_text_values(df: pd.DataFrame, column: str, limit: int = 3) -> List[str]:
    if column not in df.columns:
        return []
    series = df[column].dropna().astype(str).str.strip()
    return series[series.ne("")].drop_duplicates().head(limit).tolist()


def _default_dynamic_suggestions(question: str) -> List[str]:
    """Return 3 starter suggestions cycling through all categories."""
    all_questions = []
    for cat in ["performance", "trending", "rankings", "cross_platform", "geography"]:
        all_questions.extend(CATEGORIZED_SUGGESTIONS[cat]["questions"])
    start = abs(hash(question.strip().lower() or "music")) % len(all_questions)
    return [all_questions[(start + offset) % len(all_questions)] for offset in range(3)]


def _push_suggestion(suggestions: List[str], suggestion: Optional[str], limit: int = 3) -> None:
    if not suggestion:
        return
    normalized = suggestion.strip()
    if not normalized or normalized in suggestions or len(suggestions) >= limit:
        return
    suggestions.append(normalized)


def _build_follow_up_suggestions(
    question: str,
    df: Optional[pd.DataFrame] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> List[str]:
    q = question.lower()
    suggestions: List[str] = []

    if df is not None and not df.empty:
        artist_names = _top_text_values(df, "name", limit=5)
        labels = _top_text_values(df, "label", limit=5)

        if artist_names:
            if len(artist_names) > 1:
                _push_suggestion(suggestions, f"Compare {artist_names[0]} vs {artist_names[1]} by streams")
            _push_suggestion(suggestions, f"How many songs does {artist_names[0]} have in Top 100?")
            _push_suggestion(suggestions, f"What is the performance of {artist_names[0]} YTD?")
        if labels:
            if len(labels) > 1:
                _push_suggestion(suggestions, f"Compare {labels[0]} vs {labels[1]} song counts")
            _push_suggestion(suggestions, f"Analyze {labels[0]} performance over the last 5 weeks")
        if "streams" in df.columns or "listeners" in df.columns:
            _push_suggestion(suggestions, "How many streams are required to enter Top 100?")
        if "rank" in df.columns:
            _push_suggestion(suggestions, "Which songs consistently stay in Top 10?")

    if any(k in q for k in ["top", "rank", "song"]):
        _push_suggestion(suggestions, "What are the Top 5 songs for FY2026?")
        _push_suggestion(suggestions, "What are the Top 10 songs in the previous 5 weeks?")
    if any(k in q for k in ["artist", "performer", "performance"]):
        _push_suggestion(suggestions, "Who are the Top 20 artists by streams in FY2026?")
        _push_suggestion(suggestions, "Compare Top 10 artists in a table with percentage analysis")
    if any(k in q for k in ["label", "independent"]):
        _push_suggestion(suggestions, "How many songs does each label have in Top 100?")
    if any(k in q for k in ["trend", "consistency", "growth"]):
        _push_suggestion(suggestions, "Which songs are consistently in Top 10 for 10 weeks?")
    if any(k in q for k in ["debut", "new", "entry"]):
        _push_suggestion(suggestions, "What are the debut songs in FY2026?")
    if any(k in q for k in ["strategy", "acquire", "business"]):
        _push_suggestion(suggestions, "Based on last 5 weeks, which artist should be acquired?")
    if any(t in q for t in ["hi", "hello", "hey"]):
        _push_suggestion(suggestions, "What are the Top 5 songs for FY2026?")
        _push_suggestion(suggestions, "Who are the Top 20 artists by streams?")
        _push_suggestion(suggestions, "How many songs does each label have in Top 100?")
    if "stream" in q or "listener" in q:
        _push_suggestion(suggestions, "How many streams are required to enter Top 100?")
    if "label" in q or "independent" in q:
        _push_suggestion(suggestions, "Which independent artists should be acquired?")

    for fallback in _default_dynamic_suggestions(question):
        _push_suggestion(suggestions, fallback)

    return suggestions[:3]


# ─── Chart / Table Helpers ────────────────────────────────────────────────────

def _wants_chart(question: str) -> bool:
    q = question.lower()
    if any(re.search(p, q) for p in NO_CHART_PATTERNS):
        return False
    return any(re.search(p, q) for p in CHART_TRIGGER_PATTERNS)


def _should_render_chart(question: str, df: pd.DataFrame, chart_spec: Dict[str, Any]) -> bool:
    if df.empty or not chart_spec.get("x") or not chart_spec.get("y"):
        return False
    x_col = chart_spec.get("x")
    y_col = chart_spec.get("y")
    if x_col not in df.columns or y_col not in df.columns:
        return False
    if df[y_col].dropna().empty:
        return False
    if not _wants_chart(question) or len(df) < 2:
        return False
    return True


def _wants_data_table(question: str, df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    q = question.lower()
    if any(re.search(p, q) for p in NO_TABLE_PATTERNS):
        return False
    if any(re.search(p, q) for p in TABLE_TRIGGER_PATTERNS):
        return True
    if len(df) <= 5 and ("name" in df.columns or "source" in df.columns):
        return True
    return False


def _choose_chart_spec(df: pd.DataFrame, plan: Dict[str, Any]) -> Dict[str, Any]:
    columns = [c.lower() for c in df.columns.tolist()]
    orig_columns = df.columns.tolist()
    col_map = {c.lower(): c for c in orig_columns}
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    x = plan.get("x")
    y = plan.get("y")
    question_hint = (plan.get("title", "") + " " + str(plan.get("sql", ""))).lower()

    if not x or x.lower() not in columns:
        potential_x = ["name", "artist", "song", "track", "title", "top_country", "month", "label", "source", "scrape_date", "scraped_at"]
        for p in potential_x:
            if p in columns:
                x = col_map[p]
                break
        if not x and orig_columns:
            x = orig_columns[0]

    if not y or y.lower() not in columns:
        potential_y = []
        if "stream" in question_hint or "listener" in question_hint:
            potential_y = ["monthly_listeners", "peak_listeners"]
        elif "rank" in question_hint:
            potential_y = ["rank", "rank_change"]
        elif "point" in question_hint:
            potential_y = ["total_points", "itunes_points", "spotify_points"]
        for p in potential_y:
            if p in columns:
                y = col_map[p]
                break
        if not y and numeric_cols:
            y = numeric_cols[0]

    if x not in orig_columns or y not in orig_columns:
        return {"chart_type": "none", "x": None, "y": None, "title": plan.get("title")}

    return {
        "chart_type": str(plan.get("chart_type", "multi")).lower(),
        "x": x,
        "y": y,
        "title": plan.get("title") or "Results",
    }


def _render_data_table(df: pd.DataFrame, max_rows: int = 10) -> None:
    if df.empty:
        return
    st.markdown("### 📋 Data Details")
    display_df = df.head(max_rows).copy()
    
    # Exclude profile_url, page_title, and snapshot_text columns from rendering
    cols_to_drop = [c for c in ["profile_url", "page_title", "snapshot_text"] if c in display_df.columns]
    if cols_to_drop:
        display_df = display_df.drop(columns=cols_to_drop)
        
    for col in display_df.select_dtypes(include="number").columns:
        display_df[col] = display_df[col].apply(_format_value)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={col: st.column_config.TextColumn(width="medium") for col in display_df.columns},
    )


# ─── Small Talk ───────────────────────────────────────────────────────────────

def _small_talk_response(question: str) -> Optional[str]:
    q = question.strip().lower()
    for pattern in SMALL_TALK_PATTERNS:
        if re.match(pattern, q):
            break
    else:
        return None
    if q in {"thanks", "thank you"}:
        return "You're welcome. I can help with rankings, listeners, countries, trends, or quick summaries from the database."
    if "how are you" in q or "how r you" in q:
        return "I'm ready. Ask about rankings, listeners, countries, scrape activity, or artist details and I'll keep it concise."
    return "Hi! How can I help you today?"


# ─── UI Shell ─────────────────────────────────────────────────────────────────

def _queue_follow_up_question(question: str) -> None:
    st.session_state.ai_pending_question = question
    st.session_state.ai_is_processing = True


def _submit_center_prompt() -> None:
    question = st.session_state.get("ai_center_prompt_input", "").strip()
    if not question or st.session_state.get("ai_is_processing", False):
        return
    _queue_follow_up_question(question)
    st.session_state.ai_center_prompt_input = ""


def _reset_chat_session() -> None:
    st.session_state.ai_chat_messages = []
    st.session_state.ai_pending_question = None
    st.session_state.ai_chat_title = None
    st.session_state.ai_is_processing = False
    st.session_state.ai_active_question = None
    st.session_state.ai_token_usage = {"input_tokens": 0, "output_tokens": 0}
    st.session_state.ai_selected_suggestion_category = "performance"


def _derive_chat_title(question: str) -> str:
    words = question.strip().split()
    if not words:
        return "New chat"
    title = " ".join(words[:7]).strip()
    return (title + "...") if len(words) > 7 else title


def _render_token_badge() -> None:
    usage = st.session_state.get("ai_token_usage", {"input_tokens": 0, "output_tokens": 0})
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    total = inp + out
    if total == 0:
        return

    def _fmt(n: int) -> str:
        return f"{n/1000:.1f}k" if n >= 1000 else str(n)

    st.markdown(
        f"""
        <div style="display:flex;gap:.55rem;flex-wrap:wrap;margin-bottom:.4rem">
            <span style="display:inline-flex;align-items:center;gap:.32rem;
                background:rgba(25,34,73,.7);border:1px solid rgba(123,145,255,.22);
                border-radius:999px;padding:.28rem .7rem;font-size:.76rem;color:#a8b8e8">
                <span style="color:#22d3a0;font-size:.72rem">⬆</span>
                <span style="color:#7e8cb4;letter-spacing:.04em">IN</span>
                <span style="font-weight:600;color:#dce6ff">{_fmt(inp)}</span>
            </span>
            <span style="display:inline-flex;align-items:center;gap:.32rem;
                background:rgba(25,34,73,.7);border:1px solid rgba(123,145,255,.22);
                border-radius:999px;padding:.28rem .7rem;font-size:.76rem;color:#a8b8e8">
                <span style="color:#7c5cfc;font-size:.72rem">⬇</span>
                <span style="color:#7e8cb4;letter-spacing:.04em">OUT</span>
                <span style="font-weight:600;color:#dce6ff">{_fmt(out)}</span>
            </span>
            <span style="display:inline-flex;align-items:center;gap:.32rem;
                background:rgba(25,34,73,.7);border:1px solid rgba(79,142,247,.28);
                border-radius:999px;padding:.28rem .7rem;font-size:.76rem;color:#a8b8e8">
                <span style="color:#4f8ef7;font-size:.72rem">◈</span>
                <span style="color:#7e8cb4;letter-spacing:.04em">TOTAL</span>
                <span style="font-weight:600;color:#dce6ff">{_fmt(total)}</span>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_chat_shell(has_messages: bool, title: Optional[str]) -> None:
    left_col, right_col = st.columns([6, 1.4])
    # with left_col:
    #     label = title or "New chat"
    #     kicker = "Current chat" if has_messages else "AI Analyst"
    #     st.markdown(
    #         f"""<div class="ai-thread-head">
    #             <div class="ai-thread-kicker">{kicker}</div>
    #             <div class="ai-thread-title">{label}</div>
    #         </div>""",
    #         unsafe_allow_html=True,
    #     )
    with right_col:
        st.button(
            "+ New chat",
            key="ai_new_chat_button",
            use_container_width=True,
            on_click=_reset_chat_session,
            disabled=not has_messages or st.session_state.get("ai_is_processing", False),
        )


def _render_empty_state() -> None:
    _, center_col, _ = st.columns([1.2, 3.6, 1.2])
    with center_col:
        st.markdown('<div class="ai-empty-stage">', unsafe_allow_html=True)

        # ── Hero headline ────────────────────────────────────────────────────
        st.markdown(
            """<div class="ai-hero-shell">
                <div class="ai-hero-badge">AI Analyst</div>
                <h2>Ask anything about your music data</h2>
                <p>Query PostgreSQL in natural language — get direct answers with charts, tables, and insights.</p>
            </div>""",
            unsafe_allow_html=True,
        )

        # ── Search / prompt field (press Enter to submit) ───────────────────
        st.text_input(
            "Start a conversation",
            placeholder="Ask about artists, listeners, rankings, countries, or trends",
            label_visibility="collapsed",
            disabled=st.session_state.get("ai_is_processing", False),
            key="ai_center_prompt_input",
            on_change=_submit_center_prompt,
        )

        # ── Category suggestion grid ─────────────────────────────────────────
        st.markdown(
            """
            <style>
            .cat-container {
                margin-top: 1.5rem;
            }
            .cat-buttons {
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin-bottom: 1rem;
            }
            .question-capsules {
                display: flex;
                overflow-x: auto;
                gap: 0.6rem;
                padding-bottom: 0.8rem;
                scrollbar-width: thin;
                scrollbar-color: rgba(130, 146, 219, .3) transparent;
            }
            .question-capsules::-webkit-scrollbar {
                height: 4px;
            }
            .question-capsules::-webkit-scrollbar-thumb {
                background: rgba(130, 146, 219, .3);
                border-radius: 10px;
            }
            
            /* Category buttons styling */
            div.cat-btn-wrapper > div[data-testid="stButton"] > button {
                border-radius: 20px !important;
                padding: 0.4rem 1rem !important;
                font-size: 0.85rem !important;
                border: 1px solid rgba(130, 146, 219, .2) !important;
                background: rgba(30, 38, 68, 0.4) !important;
                color: #e5ebff !important;
            }
            div.cat-btn-wrapper > div[data-testid="stButton"] > button:hover {
                border-color: rgba(130, 146, 219, .6) !important;
                background: rgba(30, 38, 68, 0.8) !important;
            }
            div.cat-btn-active > div[data-testid="stButton"] > button {
                background: rgba(123, 145, 255, 0.2) !important;
                border-color: rgba(123, 145, 255, 0.5) !important;
                color: #1A1A1A !important;
                font-weight: 600 !important;
            }

            /* Question capsules styling */
            div.q-capsule-wrapper > div[data-testid="stButton"] > button {
                border-radius: 30px !important;
                white-space: nowrap !important;
                padding: 0.5rem 1.2rem !important;
                font-size: 0.8rem !important;
                background: rgba(18, 24, 43, 0.9) !important;
                border: 1px solid rgba(130, 146, 219, 0.15) !important;
                color: #cbd5f5 !important;
                height: auto !important;
                min-height: 0 !important;
            }
            div.q-capsule-wrapper > div[data-testid="stButton"] > button:hover {
                border-color: rgba(123, 145, 255, 0.4) !important;
                color: #1A1A1A !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        if "ai_selected_suggestion_category" not in st.session_state or st.session_state.ai_selected_suggestion_category is None:
            st.session_state.ai_selected_suggestion_category = "performance"

        disabled = st.session_state.get("ai_is_processing", False)

        # Render Category Buttons
        cat_cols = st.columns(len(CATEGORIZED_SUGGESTIONS))
        for idx, (cat_key, cat_data) in enumerate(CATEGORIZED_SUGGESTIONS.items()):
            is_active = st.session_state.ai_selected_suggestion_category == cat_key
            with cat_cols[idx]:
                st.markdown(f'<div class="cat-btn-wrapper {"cat-btn-active" if is_active else ""}">', unsafe_allow_html=True)
                if st.button(f"{cat_data['icon']} {cat_data['label']}", key=f"btn_cat_{cat_key}", use_container_width=True):
                    st.session_state.ai_selected_suggestion_category = cat_key
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        selected_cat = st.session_state.ai_selected_suggestion_category
        if selected_cat and selected_cat in CATEGORIZED_SUGGESTIONS:
            questions = CATEGORIZED_SUGGESTIONS[selected_cat]["questions"]
            
            # Show questions in rows of 3
            for i in range(0, len(questions), 3):
                batch = questions[i:i+3]
                q_cols = st.columns(3)
                for idx, q_text in enumerate(batch):
                    with q_cols[idx]:
                        st.markdown('<div class="q-capsule-wrapper">', unsafe_allow_html=True)
                        if st.button(q_text, key=f"q_cap_{selected_cat}_{i+idx}", on_click=_queue_follow_up_question, args=(q_text,), disabled=disabled, use_container_width=True):
                            pass
                        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


def _render_follow_up_suggestions(suggestions: List[str], message_key: str) -> None:
    if not suggestions:
        return
    st.markdown("---")
    st.markdown("**💡 Try next:**")
    cols = st.columns(len(suggestions))
    for idx, suggestion in enumerate(suggestions):
        with cols[idx]:
            st.button(
                suggestion,
                key=f"{message_key}_suggestion_{idx}",
                use_container_width=True,
                help="Click to explore this question",
                on_click=_queue_follow_up_question,
                args=(suggestion,),
                disabled=st.session_state.get("ai_is_processing", False),
            )


def _latest_assistant_index(messages: list) -> Optional[int]:
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].get("role") == "assistant":
            return idx
    return None


# ─── Main Entrypoint ──────────────────────────────────────────────────────────

def render_custom_chatbot() -> None:
    st.markdown(
        """
        <style>
        .ai-empty-stage{display:flex;flex-direction:column;justify-content:flex-start;gap:.65rem;padding:clamp(.35rem,2vh,1.1rem) 0 .5rem}
        .ai-thread-head{display:flex;flex-direction:column;gap:.2rem;padding:.15rem 0 .75rem}
        .ai-thread-kicker{font-size:.76rem;letter-spacing:.08em;text-transform:uppercase;color:#7e8cb4}
        .ai-thread-title{font-size:1.15rem;font-weight:600;color:#eef2ff;letter-spacing:-.02em}
        .ai-hero-shell{display:flex;flex-direction:column;justify-content:flex-start;align-items:center;
            text-align:center;gap:.55rem;padding:.2rem 0 .35rem}
        .ai-hero-shell h2{margin:0;font-size:clamp(1.5rem,2.8vw,2.5rem);line-height:1.05;font-weight:700;
            letter-spacing:-.03em;color:#f6f8ff}
        .ai-hero-shell p{max-width:42rem;margin:0;font-size:.93rem;line-height:1.45;color:#98a4c8}
        .ai-hero-badge{display:inline-flex;align-items:center;padding:.45rem .9rem;border-radius:999px;
            border:1px solid rgba(123,145,255,.28);background:rgba(25,34,73,.6);
            color:#c9d4ff;font-size:.85rem;letter-spacing:.04em;text-transform:uppercase}
        .ai-starter-grid{margin-top:.45rem}
        .ai-empty-stage div[data-testid="stForm"]{max-width:860px;margin-left:auto;margin-right:auto}
        div[data-testid="stForm"]{background:linear-gradient(180deg,rgba(22,27,47,.96),rgba(16,20,38,.96));
            border:1px solid rgba(130,146,219,.14);border-radius:26px;padding:.55rem;
            box-shadow:0 22px 48px rgba(0,0,0,.28)}
        div[data-testid="stForm"] div[data-testid="stTextInput"] input{background:transparent;border:0;font-size:1rem;color:#f4f7ff}
        div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button{border-radius:999px;
            padding:.6rem 1.2rem;font-weight:600;background:linear-gradient(135deg,#5f79ff,#8ca2ff);border:0;color:#081022}
        div[data-testid^="stChatMessageAvatar"]{display:none!important}
        div[data-testid="stChatMessage"]{max-width:min(920px,94vw);margin-left:auto;margin-right:auto;
            width:100%;display:flex;align-items:flex-start;justify-content:flex-start;gap:.5rem;padding:.35rem .3rem}
        div[data-testid="stChatMessage"] [data-testid="stChatMessageContent"]{max-width:min(760px,84vw);
            border-radius:14px;padding:.8rem 1rem;width:fit-content;min-width:0;line-height:1.55;
            font-size:.97rem;color:#e9eefc}
        div[data-testid="stChatMessage"]:has([aria-label="assistant"]) [data-testid="stChatMessageContent"]{
            background:rgba(17,24,44,.58);border:1px solid rgba(126,142,207,.22);max-width:min(760px,84vw);
            border-radius:14px;box-shadow:0 12px 28px rgba(4,10,24,.18)}
        div[data-testid="stChatMessage"]:has([aria-label="user"]){justify-content:flex-end}
        div[data-testid="stChatMessage"]:has([aria-label="user"]) [data-testid="stChatMessageContent"]{
            background:linear-gradient(170deg,rgba(45,53,79,.92),rgba(37,44,68,.92));
            border:1px solid rgba(133,151,220,.32);max-width:min(500px,72vw);border-radius:18px;
            box-shadow:0 14px 30px rgba(2,8,24,.22)}
        div[data-testid="stChatMessage"] p{margin:.25rem 0}
        div[data-testid="stChatInput"]{padding-top:1rem;max-width:min(1000px,94vw);margin:0 auto}
        div[data-testid="stChatInput"] > div { background: transparent !important; border: none !important; box-shadow: none !important; }
        div[data-testid="stChatInput"] div:has(> div[data-baseweb="base-input"]) {
            background: rgba(35,43,76,.96) !important;
            border: 1px solid rgba(132,149,218,.5) !important;
            border-radius: 26px !important;
            box-shadow: 0 12px 30px rgba(2,6,18,.4) !important;
        }
        div[data-testid="stChatInput"] div[data-baseweb="base-input"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }
        div[data-testid="stChatInput"] textarea, div[data-testid="stChatInput"] input {
            background: transparent !important;
            border: none !important;
            color: #1A1A1A !important;
            box-shadow: none !important;
            padding: 0.6rem 0.9rem !important;
        }
        div[data-testid="stChatInput"] button{border-radius:14px!important;background:linear-gradient(135deg,#6f88ff,#93a8ff)!important;
            color:#0a122b!important;border:0!important;font-weight:600!important}
        @media(max-width:760px){
            div[data-testid="stChatMessage"]{padding:.2rem 0}
            div[data-testid="stChatMessage"] [data-testid="stChatMessageContent"]{max-width:89vw;padding:.72rem .85rem}
            div[data-testid="stChatMessage"]:has([aria-label="user"]) [data-testid="stChatMessageContent"]{max-width:84vw}
        }
        @media(max-height:860px){.ai-starter-grid{display:none}}
        
        /* Spinner Loader Centering & Styling */
        div[data-testid="stSpinner"] {
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            width: 100% !important;
            margin: 2.2rem auto !important;
        }
        div[data-testid="stSpinner"] > div {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.85rem !important;
        }
        div[data-testid="stSpinner"] p {
            text-align: center !important;
            color: #c9d4ff !important;
            font-weight: 600 !important;
            font-size: 0.96rem !important;
            letter-spacing: 0.02em !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    ss = st.session_state
    ss.setdefault("ai_chat_messages", [])
    ss.setdefault("ai_pending_question", None)
    ss.setdefault("ai_chat_title", None)
    ss.setdefault("ai_is_processing", False)
    ss.setdefault("ai_active_question", None)
    ss.setdefault("ai_token_usage", {"input_tokens": 0, "output_tokens": 0})

    api_key = _resolve_api_key()
    model = _resolve_model()

    if ss.ai_pending_question:
        ss.ai_active_question = ss.ai_pending_question
        ss.ai_pending_question = None
        ss.ai_is_processing = True

    _render_chat_shell(bool(ss.ai_chat_messages), ss.ai_chat_title)

    if not ss.ai_chat_messages and not ss.ai_active_question:
        _render_empty_state()
    else:
        st.caption("Ask data questions in plain language. Charts and visuals appear automatically.")

    latest_assistant_idx = _latest_assistant_index(ss.ai_chat_messages)

    for msg_idx, message in enumerate(ss.ai_chat_messages):
        with st.chat_message(message["role"], avatar="🤖" if message["role"] == "assistant" else "👤"):
            if message["role"] == "assistant":
                render_order = message.get("render_order", ["chart", "summary", "table"])
                if isinstance(render_order, str):
                    try:
                        render_order = json.loads(render_order)
                    except Exception:
                        render_order = [s.strip().lower() for s in render_order.split(",") if s.strip()]
                if not isinstance(render_order, list):
                    render_order = ["summary", "chart", "table"]

                show_summary = message.get("show_summary", True)
                show_chart = message.get("show_chart", False) and message.get("chart_data")
                show_table = message.get("show_table", False) and message.get("chart_data")

                for section in render_order:
                    if section == "summary" and show_summary and message.get("content"):
                        st.markdown(message["content"])
                    if section == "chart" and show_chart:
                        chart_df = pd.DataFrame(message["chart_data"])
                        if not chart_df.empty:
                            spec = message.get("chart_spec", {})
                            x, y = spec.get("x"), spec.get("y")
                            if x and y:
                                render_multi_chart_view(chart_df, x, y, message.get("question", ""))
                                render_insights_dashboard(chart_df, x, y)
                    if section == "table" and show_table:
                        table_df = pd.DataFrame(message["chart_data"])
                        if not table_df.empty:
                            _render_data_table(table_df, max_rows=15)
            else:
                st.markdown(message["content"])

            if (
                message["role"] == "assistant"
                and msg_idx == latest_assistant_idx
                and not ss.ai_pending_question
            ):
                _render_follow_up_suggestions(
                    message.get("suggestions", []),
                    message_key=f"assistant_{msg_idx}",
                )

    if ss.ai_chat_messages or ss.ai_active_question:
        chat_val = st.chat_input(
            "Ask about artists, listeners, rankings, countries, or trends",
            disabled=ss.ai_is_processing,
        )
        if chat_val:
            ss.ai_active_question = chat_val
            ss.ai_is_processing = True
            st.rerun()

    question = ss.ai_active_question
    if not question:
        return

    if not ss.ai_chat_messages:
        ss.ai_chat_title = _derive_chat_title(question)

    ss.ai_chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="👤"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Analyzing your data…"):
            try:
                small_talk = _small_talk_response(question)
                if small_talk:
                    suggestions = _build_follow_up_suggestions(question)
                    st.markdown(small_talk)
                    _render_follow_up_suggestions(suggestions, "assistant_current")
                    ss.ai_chat_messages.append({
                        "role": "assistant",
                        "content": small_talk,
                        "suggestions": suggestions,
                    })
                    ss.ai_is_processing = False
                    ss.ai_active_question = None
                    st.rerun()

                plan = _generate_plan(question, api_key, model)
                safe_sql = _enforce_safe_sql(plan["sql"])

                try:
                    result_df = _clean_result_df(_run_query(safe_sql))
                except Exception:
                    result_df = pd.DataFrame()
                    local_fallback = _local_plan(question)
                    if local_fallback.get("sql"):
                        try:
                            fallback_sql = _enforce_safe_sql(local_fallback["sql"])
                            result_df = _clean_result_df(_run_query(fallback_sql))
                            if not result_df.empty:
                                plan = local_fallback
                                safe_sql = fallback_sql
                        except Exception:
                            pass

                if result_df.empty:
                    artist_names = _find_artists_in_db(question)
                    if artist_names:
                        artist_name = artist_names[0]
                        profile_plan = _build_artist_profile(artist_name)
                        try:
                            profile_sql = _enforce_safe_sql(profile_plan["sql"])
                            profile_df = _clean_result_df(_run_query(profile_sql))
                            if not profile_df.empty:
                                result_df = profile_df
                                plan = profile_plan
                                safe_sql = profile_sql
                        except Exception:
                            pass

                        if result_df.empty:
                            retry_plan = _retry_with_available_data(question, artist_name)
                            if retry_plan:
                                try:
                                    retry_sql = _enforce_safe_sql(retry_plan["sql"])
                                    retry_df = _clean_result_df(_run_query(retry_sql))
                                    if not retry_df.empty:
                                        result_df = retry_df
                                        plan = retry_plan
                                        safe_sql = retry_sql
                                except Exception:
                                    pass

                chart_spec = _choose_chart_spec(result_df, plan)
                show_chart = (
                    plan.get("show_chart")
                    if isinstance(plan.get("show_chart"), bool)
                    else _should_render_chart(question, result_df, chart_spec)
                )
                show_table = (
                    plan.get("show_table")
                    if isinstance(plan.get("show_table"), bool)
                    else _wants_data_table(question, result_df)
                )
                show_summary = (
                    plan.get("show_summary")
                    if isinstance(plan.get("show_summary"), bool)
                    else True
                )

                render_order = plan.get("render_order", ["chart", "summary", "table"])
                if isinstance(render_order, str):
                    try:
                        render_order = json.loads(render_order)
                    except Exception:
                        render_order = [s.strip().lower() for s in render_order.split(",") if s.strip()]
                if not isinstance(render_order, list):
                    render_order = ["summary", "chart", "table"]

                answer = (
                    _summarize_results(question, safe_sql, result_df, api_key, model)
                    if show_summary
                    else ""
                )
                suggestions = _build_follow_up_suggestions(question, result_df, api_key, model)

                for section in render_order:
                    if section == "summary" and show_summary and answer:
                        st.markdown(answer)
                    if section == "chart" and show_chart:
                        render_multi_chart_view(result_df, chart_spec["x"], chart_spec["y"], question)
                        render_insights_dashboard(result_df, chart_spec["x"], chart_spec["y"])
                    if section == "table" and show_table:
                        _render_data_table(result_df)

                _render_follow_up_suggestions(suggestions, "assistant_current")

                ss.ai_chat_messages.append({
                    "role": "assistant",
                    "content": answer,
                    "chart_data": result_df.to_dict(orient="records"),
                    "chart_spec": chart_spec,
                    "show_summary": show_summary,
                    "show_chart": show_chart,
                    "show_table": show_table,
                    "render_order": render_order,
                    "suggestions": suggestions,
                    "question": question,
                })

            except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
                err = "Claude authentication failed. Check that CLAUDE_API_KEY is set correctly."
                st.error(err)
                suggestions = _build_follow_up_suggestions("artists")
                _render_follow_up_suggestions(suggestions, "assistant_current")
                ss.ai_chat_messages.append({
                    "role": "assistant",
                    "content": err,
                    "suggestions": suggestions,
                })

            except Exception as exc:
                err = f"I couldn't complete that request: {str(exc)}"
                st.error(err)
                suggestions = _build_follow_up_suggestions(question)
                _render_follow_up_suggestions(suggestions, "assistant_current")
                ss.ai_chat_messages.append({
                    "role": "assistant",
                    "content": err,
                    "suggestions": suggestions,
                })

            ss.ai_is_processing = False
            ss.ai_active_question = None
            st.rerun()