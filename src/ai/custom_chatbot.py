"""
Music Analytics AI Agent — Production-Ready
- 70% visual / 30% text output
- Dynamic AI-powered SQL planning (no fixed queries)
- OpenAI SDK (replaces Anthropic)
- MCP-aligned architecture: plan → query → visualize → narrate
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
from openai import OpenAI, AuthenticationError, APIError
from streamlit.errors import StreamlitSecretNotFoundError

from src.ai.advanced_visualizations import (
    render_multi_chart_view,
    render_insights_dashboard,
)
from src.database.connection import get_connection

# ─── Constants ────────────────────────────────────────────────────────────────

ALLOWED_TABLES = {
    "artists",
    "itunes_artist_rankings",
    "spotify_artists",
    "trending_artists_monthly",
    "artist_details",
    "scrape_runs",
}

SCHEMA_CONTEXT = """
Database schema summary:
- artists(id, name, profile_url, created_at, updated_at)
- itunes_artist_rankings(id, artist_id, rank, rank_change, total_points, itunes_points, spotify_points, apple_music_points, shazam_points, youtube_points, other_points, top_country, num_countries, scraped_at TIMESTAMPTZ, scrape_date DATE)
- spotify_artists(id, artist_id, monthly_listeners, peak_listeners, peak_date, scraped_at TIMESTAMPTZ, scrape_date DATE)
- trending_artists_monthly(id, artist_id, source, rank, rank_change, total_points, top_country, month, scraped_at TIMESTAMPTZ)
- artist_details(id, artist_id, page_title, snapshot_text, songs_count, albums_count, countries_count, top_songs, top_albums, top_countries, scraped_at TIMESTAMPTZ, scrape_date DATE)
- scrape_runs(id, source, status, rows_upserted, error_msg, started_at, finished_at)

Key notes:
- Use scraped_at (timestamp) for precise latest data: MAX(scraped_at)
- Use scrape_date (date) for daily aggregations
- trending_artists_monthly has only scraped_at, no scrape_date

Relationships:
- Join metrics tables to artists using artists.id = <table>.artist_id.
""".strip()

DANGEROUS_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy)\b",
    re.IGNORECASE,
)
TABLE_REF_RE = re.compile(
    r"\b(?:from|join)\s+([a-z_][a-z0-9_\.]*)(?!\s*\()",
    re.IGNORECASE,
)
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
	r"\bexplain\b",
    r"\bwhy\b",
    r"\bsummary\b",
    r"\bsummarize\b",
    r"\btell me\b",
    r"\bwhat does\b",
    r"\bwhich artist\b",
    r"\bwho is\b",
    r"\bdetails?\b"
]

NO_CHART_PATTERNS = [
    
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
    r"\bdownload\b",
    r"\bcolumns?\b",
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


# ─── Secret / Config ──────────────────────────────────────────────────────────

def _read_secret(name: str) -> Optional[str]:
    try:
        if name in st.secrets:
            val = st.secrets.get(name)
            if val:
                return str(val).strip()
    except StreamlitSecretNotFoundError:
        pass
    env_val = os.getenv(name)
    if env_val:
        return env_val.strip()
    return None


def _resolve_api_key() -> Optional[str]:
    return _read_secret("OPENAI_API_KEY")


def _resolve_model() -> str:
    return _read_secret("OPENAI_MODEL") or "gpt-4o"


def _get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


# ─── OpenAI API Calls ─────────────────────────────────────────────────────────

def _openai_chat_json(
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 3000,
) -> Dict[str, Any]:
    """Call OpenAI and parse the response as JSON."""
    client = _get_client(api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except (json.JSONDecodeError, APIError) as e:
        st.warning(f"API error: {str(e)}")
        return {}


def _openai_chat_text(
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1000,
) -> str:
    """Call OpenAI and return the response as plain text."""
    client = _get_client(api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""
    except APIError as e:
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


def _find_artist_in_db(question: str) -> Optional[str]:
    """Try to match an artist name from the database using tokens from the question."""
    tokens = [t.strip() for t in re.split(r"\W+", question) if len(t.strip()) > 2]
    if not tokens:
        return None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for token in tokens[:6]:
                cur.execute(
                    "SELECT name FROM artists WHERE lower(name) LIKE %s LIMIT 1",
                    (f"%{token.lower()}%",),
                )
                row = cur.fetchone()
                if row:
                    return row[0]
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return None


def _local_plan(question: str) -> Dict[str, Any]:
    """Generate query plans locally without API calls."""
    q = question.lower()

    artist = _find_artist_in_db(question)
    if artist:
        limit = _extract_top_n(question) or 20
        return {
            "sql": f"""
                SELECT a.name, i.rank, i.total_points, i.top_country
                FROM itunes_artist_rankings i
                JOIN artists a ON a.id = i.artist_id
                WHERE a.name ILIKE '%{artist}%'
                ORDER BY i.scrape_date DESC, i.rank ASC
                LIMIT {limit}
            """,
            "chart_type": "multi",
            "x": "scrape_date",
            "y": "total_points",
            "title": f"Performance for {artist}",
        }

    if _is_top_intent(question):
        return _force_rank_plan(question)

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
                WITH latest AS (
                    SELECT MAX(scrape_date) AS scrape_date
                    FROM itunes_artist_rankings
                )
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
            WITH latest AS (
                SELECT MAX(scrape_date) AS scrape_date
                FROM itunes_artist_rankings
            )
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
    unknown_tables = referenced_tables.difference(ALLOWED_TABLES.union(cte_names))
    if unknown_tables:
        raise ValueError("Query referenced unsupported tables: " + ", ".join(sorted(unknown_tables)))
    if not LIMIT_RE.search(sql):
        sql = f"{sql} LIMIT 250"
    return sql


# ─── Query Plan ───────────────────────────────────────────────────────────────

PLAN_SYSTEM = f"""You are a music analytics SQL expert. Generate a safe query plan in JSON format.

Schema and Rules:
{SCHEMA_CONTEXT}

Important: All data is at the artist level. Rankings, points, and metrics refer to artists, not individual tracks. There are no track-level tables in the database.

Safety Requirements:
- Use ONLY SELECT and WITH (CTE) queries
- Use ONLY these tables: {', '.join(sorted(ALLOWED_TABLES))}
- Always add LIMIT with appropriate count (10-30 for executive queries)
- Use MAX(scraped_at) or MAX(scrape_date) for latest data, depending on table
- Prefer the most relevant numeric field for the question, not always total_points.
  For streams queries use monthly_listeners, for rank-focused queries use rank,
  for distribution questions use counts or percentages, and for time-based queries use month or scraped_at.
- No UPDATE, INSERT, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, COPY, EXEC

Response Format (JSON):
{{
    "sql": "SELECT ... LIMIT N",
    "chart_type": "multi",
    "x": "column_name",
    "y": "column_name",
    "title": "Chart Title",
    "show_summary": true,
    "show_chart": true,
    "show_table": false,
    "render_order": ["chart", "summary", "table"]
}}

The agent should decide the full response structure. If the question is visual-first, put chart before summary. If the question is detail-first, put table before summary. If the model wants only one section, use a render_order with just that section.

Examples of queries:
- Top tracks: SELECT a.name as artist, i.rank, i.total_points FROM itunes_artist_rankings i JOIN artists a ON i.artist_id = a.id WHERE i.scraped_at = (SELECT MAX(scraped_at) FROM itunes_artist_rankings) ORDER BY i.rank LIMIT 10
- Artist performance: SELECT a.name, SUM(s.monthly_listeners) as total_listeners FROM spotify_artists s JOIN artists a ON s.artist_id = a.id WHERE s.scrape_date >= '2026-01-01' GROUP BY a.name ORDER BY total_listeners DESC LIMIT 20
- Label performance: SELECT ad.top_songs as tracks FROM artist_details ad WHERE ad.scraped_at = (SELECT MAX(scraped_at) FROM artist_details) LIMIT 5

Generate the JSON plan only, no explanation."""


def _generate_plan(question: str, api_key: Optional[str], model: str) -> Dict[str, Any]:
    """Generate query plan via OpenAI or fall back to local heuristics."""
    if _is_top_intent(question):
        plan = _force_rank_plan(question)
        plan["source"] = "local"
        return plan

    if not api_key:
        plan = _local_plan(question)
        plan["source"] = "local"
        return plan

    try:
        plan = _openai_chat_json(
            api_key,
            model,
            system=PLAN_SYSTEM,
            user=f"User Question: {question}",
        )
        if not plan or not plan.get("sql"):
            raise ValueError("Empty plan returned")
        return {
            "sql": str(plan.get("sql", "")).strip(),
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
    except PermissionError:
        raise
    except Exception:
        plan = _local_plan(question)
        plan["source"] = "local"
        return plan


# ─── Data ─────────────────────────────────────────────────────────────────────

def _run_query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall() or []
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


def _clean_result_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cleaned = df.copy()
    cleaned.columns = [str(c).strip() for c in cleaned.columns]
    mask = pd.Series(True, index=cleaned.index)
    for col in cleaned.columns:
        mask &= cleaned[col].astype(str).str.strip().str.lower().eq(col.lower())
    if mask.any():
        cleaned = cleaned[~mask].copy()
    return cleaned


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return "n/a"
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

SUMMARY_SYSTEM = """You are a terse music industry analyst writing for executives.
Produce one concise executive summary that is roughly 30% of the response; the remaining output should be visual and data-driven.
Rules:
- Keep the summary to 1-2 sentences.
- Lead with the single most important number or finding.
- Name specific artists/tracks when visible in the data.
- End with one forward-looking implication.
- No bullet points. No headers.
- Do not repeat chart metrics or over-explain the visual output.
"""


def _summarize_results(
    question: str,
    sql: str,
    df: pd.DataFrame,
    api_key: Optional[str],
    model: str,
) -> str:
    if df.empty:
        return "📊 No results found for that question. Try adjusting your filters or asking differently."

    if not api_key:
        return "🤖 AI-powered analysis is required for detailed insights. Please configure your OpenAI API key to enable intelligent summaries."

    stats = _generate_summary_stats(df)
    row_count = stats["total_rows"]

    preview_csv = df.head(20).to_csv(index=False)
    return _openai_chat_text(
        api_key,
        model,
        system=SUMMARY_SYSTEM,
        user=f"Question: {question}\nTotal rows: {row_count}\n\nData preview:\n{preview_csv}",
        max_tokens=200,
    ) or f"Found {row_count} results."


# ─── Suggestions ──────────────────────────────────────────────────────────────

SUGGESTION_SYSTEM = """You are a music analytics assistant.
Given a question and result data, return a JSON object with key "suggestions" containing
exactly 3 follow-up questions as strings.
Rules:
- Each question must be specific and answerable from a music chart database.
- Reference actual entities from the data when possible.
- Vary type: one drill-down, one comparison, one trend/strategic question.
Return ONLY valid JSON: {"suggestions": ["...", "...", "..."]}"""


def _generate_suggestions_ai(
    question: str,
    df: pd.DataFrame,
    api_key: str,
    model: str,
) -> List[str]:
    cols = df.columns.tolist() if not df.empty else []
    sample = df.head(5).to_csv(index=False) if not df.empty else "no data"
    raw = _openai_chat_json(
        api_key,
        model,
        system=SUGGESTION_SYSTEM,
        user=f"Question: {question}\nColumns: {cols}\nSample:\n{sample}",
    )
    result = raw.get("suggestions", [])
    if isinstance(result, list) and len(result) >= 3:
        return [str(s) for s in result[:3]]
    return []


def _top_text_values(df: pd.DataFrame, column: str, limit: int = 3) -> List[str]:
    if column not in df.columns:
        return []
    series = df[column].dropna().astype(str).str.strip()
    return series[series.ne("")].drop_duplicates().head(limit).tolist()


def _default_dynamic_suggestions(question: str) -> List[str]:
    pool = [
        "What are the Top 5 tracks for FY2026?",
        "What are the Top 5 songs last week with label names?",
        "Who are the Top 20 artists by number of streams in FY2026?",
        "What is the performance of this artist YTD across all countries?",
        "Which artists are in Top 100 by number of tracks?",
        "What are the number of tracks in Top 100 for each label last week?",
        "What are the debut tracks in FY2026?",
        "Which tracks are consistently in Top 10 over the last 10 weeks?",
        "How many streams are required to enter Top 100 in FY2026?",
        "Compare Top 10 artists in a table with percentage analysis",
        "What are the Top 10 tracks in the previous 5 weeks?",
        "Analyze last 5 weeks of track and label performance",
        "Compare Top 5 tracks this week vs prior week",
        "Which independent artist should be acquired and why?",
    ]
    start = abs(hash(question.strip().lower() or "music")) % len(pool)
    return [pool[(start + offset) % len(pool)] for offset in range(3)]


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
    # Try AI-generated suggestions first
    if api_key and model and df is not None and not df.empty:
        ai_sug = _generate_suggestions_ai(question, df, api_key, model)
        if len(ai_sug) == 3:
            return ai_sug

    q = question.lower()
    suggestions: List[str] = []

    if df is not None and not df.empty:
        artist_names = _top_text_values(df, "name", limit=5)
        track_names = _top_text_values(df, "track", limit=5)
        labels = _top_text_values(df, "label", limit=5)

        if track_names:
            if len(track_names) > 1:
                _push_suggestion(suggestions, f"Compare {track_names[0]} vs {track_names[1]} performance")
            _push_suggestion(suggestions, f"Analyze {track_names[0]} performance over the last 10 weeks")
            _push_suggestion(suggestions, f"What is the label and metadata for {track_names[0]}?")

        if artist_names:
            if len(artist_names) > 1:
                _push_suggestion(suggestions, f"Compare {artist_names[0]} vs {artist_names[1]} by streams")
            _push_suggestion(suggestions, f"How many tracks does {artist_names[0]} have in Top 100?")
            _push_suggestion(suggestions, f"What is the performance of {artist_names[0]} YTD?")

        if labels:
            if len(labels) > 1:
                _push_suggestion(suggestions, f"Compare {labels[0]} vs {labels[1]} track counts")
            _push_suggestion(suggestions, f"Analyze {labels[0]} performance over the last 5 weeks")

        if "streams" in df.columns or "listeners" in df.columns:
            _push_suggestion(suggestions, "How many streams are required to enter Top 100?")
        if "rank" in df.columns:
            _push_suggestion(suggestions, "Which tracks consistently stay in Top 10?")

    if any(k in q for k in ["top", "rank", "track", "song"]):
        _push_suggestion(suggestions, "What are the Top 5 tracks for FY2026?")
        _push_suggestion(suggestions, "What are the Top 10 tracks in the previous 5 weeks?")
    if any(k in q for k in ["artist", "performer", "performance"]):
        _push_suggestion(suggestions, "Who are the Top 20 artists by streams in FY2026?")
        _push_suggestion(suggestions, "Compare Top 10 artists in a table with percentage analysis")
    if any(k in q for k in ["label", "independent"]):
        _push_suggestion(suggestions, "How many tracks does each label have in Top 100?")
    if any(k in q for k in ["trend", "consistency", "growth"]):
        _push_suggestion(suggestions, "Which tracks are consistently in Top 10 for 10 weeks?")
    if any(k in q for k in ["debut", "new", "entry"]):
        _push_suggestion(suggestions, "What are the debut tracks in FY2026?")
    if any(k in q for k in ["strategy", "acquire", "business"]):
        _push_suggestion(suggestions, "Based on last 5 weeks, which artist should be acquired?")
    if any(t in q for t in ["hi", "hello", "hey"]):
        _push_suggestion(suggestions, "What are the Top 5 tracks for FY2026?")
        _push_suggestion(suggestions, "Who are the Top 20 artists by streams?")
        _push_suggestion(suggestions, "How many tracks does each label have in Top 100?")
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
    columns = df.columns.tolist()
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    x = plan.get("x")
    y = plan.get("y")
    question_hint = (plan.get("title", "") + " " + str(plan.get("sql", ""))).lower()

    if x not in columns:
        if "name" in columns:
            x = "name"
        elif "artist" in columns:
            x = "artist"
        elif "top_country" in columns:
            x = "top_country"
        elif "month" in columns:
            x = "month"
        else:
            x = columns[0] if columns else None

    if y not in columns or y is None:
        if "stream" in question_hint or "listener" in question_hint:
            y = "monthly_listeners" if "monthly_listeners" in columns else numeric_cols[0] if numeric_cols else None
        elif "rank" in question_hint and "rank" in columns:
            y = "rank"
        elif "points" in question_hint and "total_points" in columns:
            y = "total_points"
        else:
            y = numeric_cols[0] if numeric_cols else None

    if y == "total_points" and "stream" in question_hint and "monthly_listeners" in columns:
        y = "monthly_listeners"
    if y == "total_points" and "rank" in question_hint and "rank" in columns:
        y = "rank"

    if x == y and len(columns) > 1:
        x = next((col for col in columns if col != y), x)

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
    for col in display_df.select_dtypes(include="number").columns:
        display_df[col] = display_df[col].apply(_format_value)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={col: st.column_config.TextColumn(width="medium") for col in display_df.columns},
    )
    if len(df) > max_rows:
        st.caption(f"Showing {max_rows} of {len(df)} results")


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


def _reset_chat_session() -> None:
    st.session_state.ai_chat_messages = []
    st.session_state.ai_pending_question = None
    st.session_state.ai_chat_title = None


def _derive_chat_title(question: str) -> str:
    words = question.strip().split()
    if not words:
        return "New chat"
    title = " ".join(words[:7]).strip()
    return (title + "...") if len(words) > 7 else title


def _render_chat_shell(has_messages: bool, title: Optional[str]) -> None:
    left_col, right_col = st.columns([6, 1.4])
    with left_col:
        label = title or "New chat"
        kicker = "Current chat" if has_messages else "AI Analyst"
        st.markdown(
            f"""<div class="ai-thread-head{''}">
                <div class="ai-thread-kicker">{kicker}</div>
                <div class="ai-thread-title">{label}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with right_col:
        st.button("+ New chat", key="ai_new_chat_button", use_container_width=True,
                  on_click=_reset_chat_session, disabled=not has_messages)


def _render_empty_state() -> None:
    starter_prompts = _default_dynamic_suggestions("start")
    _, center_col, _ = st.columns([1.2, 3.6, 1.2])
    with center_col:
        st.markdown('<div class="ai-empty-stage">', unsafe_allow_html=True)
        st.markdown(
            """<div class="ai-hero-shell">
                <div class="ai-hero-badge">AI Analyst</div>
                <h2>Ask anything about your music data</h2>
                <p>Query PostgreSQL in natural language — get direct answers with charts, tables, and insights.</p>
            </div>""",
            unsafe_allow_html=True,
        )
        with st.form("ai_centered_prompt_form", clear_on_submit=True, border=False):
            question = st.text_input(
                "Start a conversation",
                placeholder="Ask about artists, listeners, rankings, countries, or trends",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Ask")
            if submitted and question.strip():
                _queue_follow_up_question(question.strip())
                st.rerun()

        st.markdown('<div class="ai-starter-grid">', unsafe_allow_html=True)
        starter_cols = st.columns(len(starter_prompts))
        for idx, prompt in enumerate(starter_prompts):
            with starter_cols[idx]:
                st.button(prompt, key=f"starter_prompt_{idx}", use_container_width=True,
                          on_click=_queue_follow_up_question, args=(prompt,))
        st.markdown("</div></div>", unsafe_allow_html=True)


def _render_follow_up_suggestions(suggestions: List[str], message_key: str) -> None:
    if not suggestions:
        return
    st.markdown("---")
    st.markdown("**💡 Try next:**")
    cols = st.columns(len(suggestions))
    for idx, suggestion in enumerate(suggestions):
        with cols[idx]:
            st.button(suggestion, key=f"{message_key}_suggestion_{idx}",
                      use_container_width=True, help="Click to explore this question",
                      on_click=_queue_follow_up_question, args=(suggestion,))


def _latest_assistant_index(messages: list) -> Optional[int]:
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].get("role") == "assistant":
            return idx
    return None


# ─── Main Entrypoint ──────────────────────────────────────────────────────────

def render_custom_chatbot() -> None:
    """Main chatbot interface — OpenAI-powered, 70% visual."""
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
        div[data-testid="stChatMessage"]{max-width:min(900px,92vw);margin-left:auto;margin-right:auto;
            width:100%;display:flex;align-items:flex-start;justify-content:flex-start;gap:.35rem}
        div[data-testid="stChatMessage"] [data-testid="stChatMessageContent"]{max-width:min(700px,76vw);
            border-radius:16px;padding:.58rem .9rem;width:fit-content;min-width:0}
        div[data-testid="stChatMessage"]:has([aria-label="assistant"]) [data-testid="stChatMessageContent"]{
            background:transparent;border:0;padding-left:0;padding-right:0;max-width:min(720px,80vw)}
        div[data-testid="stChatMessage"]:has([aria-label="user"]){justify-content:flex-end}
        div[data-testid="stChatMessage"]:has([aria-label="user"]) [data-testid="stChatMessageContent"]{
            background:linear-gradient(165deg,rgba(49,53,64,.9),rgba(36,40,51,.9));
            border:1px solid rgba(130,140,170,.26);max-width:min(360px,66vw);border-radius:18px}
        div[data-testid="stChatInput"]{padding-top:.85rem}
        div[data-testid="stChatInput"] textarea,div[data-testid="stChatInput"] input{border-radius:22px;
            background:rgba(24,29,50,.96);border:1px solid rgba(130,146,219,.12)}
        div[data-testid="stButton"]>button[kind="secondary"]{border-radius:999px;
            background:rgba(18,24,43,.92);border:1px solid rgba(130,146,219,.16);color:#e5ebff;font-weight:600}
        @media(max-height:860px){.ai-starter-grid{display:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Session state
    ss = st.session_state
    ss.setdefault("ai_chat_messages", [])
    ss.setdefault("ai_pending_question", None)
    ss.setdefault("ai_chat_title", None)

    api_key = _resolve_api_key()
    model = _resolve_model()

    pending_question = ss.ai_pending_question
    if pending_question:
        ss.ai_pending_question = None

    question: Optional[str] = None
    _render_chat_shell(bool(ss.ai_chat_messages), ss.ai_chat_title)

    if not ss.ai_chat_messages and not pending_question:
        _render_empty_state()
    else:
        st.caption("Ask data questions in plain language. Charts and visuals appear automatically.")

    latest_assistant_idx = _latest_assistant_index(ss.ai_chat_messages)

    # Replay chat history
    for msg_idx, message in enumerate(ss.ai_chat_messages):
        with st.chat_message(message["role"], avatar="🤖" if message["role"] == "assistant" else "👤"):
            if message["role"] == "assistant":
                render_order = message.get("render_order", ["chart", "summary", "table"])
                if isinstance(render_order, str):
                    try:
                        render_order = json.loads(render_order)
                    except Exception:
                        render_order = [section.strip().lower() for section in render_order.split(",") if section.strip()]
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
                and not pending_question
            ):
                _render_follow_up_suggestions(
                    message.get("suggestions", []),
                    message_key=f"assistant_{msg_idx}",
                )

    # Input
    if ss.ai_chat_messages:
        question = st.chat_input("Ask about artists, listeners, rankings, countries, or trends")
    if not question:
        question = pending_question
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
                # Small talk fast path
                small_talk = _small_talk_response(question)
                if small_talk:
                    suggestions = _build_follow_up_suggestions(question)
                    st.markdown(small_talk)
                    _render_follow_up_suggestions(suggestions, "assistant_current")
                    ss.ai_chat_messages.append({
                        "role": "assistant", "content": small_talk, "suggestions": suggestions,
                    })
                    return

                # Plan → Query → Render
                plan = _generate_plan(question, api_key, model)

                safe_sql = _enforce_safe_sql(plan["sql"])
                result_df = _clean_result_df(_run_query(safe_sql))

                chart_spec = _choose_chart_spec(result_df, plan)
                show_chart = plan.get("show_chart") if isinstance(plan.get("show_chart"), bool) else _should_render_chart(question, result_df, chart_spec)
                show_table = plan.get("show_table") if isinstance(plan.get("show_table"), bool) else _wants_data_table(question, result_df)
                show_summary = plan.get("show_summary") if isinstance(plan.get("show_summary"), bool) else True

                render_order = plan.get("render_order", ["chart", "summary", "table"])
                if isinstance(render_order, str):
                    try:
                        render_order = json.loads(render_order)
                    except Exception:
                        render_order = [section.strip().lower() for section in render_order.split(",") if section.strip()]
                if not isinstance(render_order, list):
                    render_order = ["summary", "chart", "table"]

                answer = _summarize_results(question, safe_sql, result_df, api_key, model) if show_summary else ""
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

            except (AuthenticationError, PermissionError):
                err = "OpenAI authentication failed. Check that OPENAI_API_KEY is set correctly."
                st.error(err)
                suggestions = _build_follow_up_suggestions("artists")
                _render_follow_up_suggestions(suggestions, "assistant_current")
                ss.ai_chat_messages.append({"role": "assistant", "content": err, "suggestions": suggestions})

            except Exception as exc:
                err = f"I couldn't complete that request: {str(exc)}"
                st.error(err)
                suggestions = _build_follow_up_suggestions(question)
                _render_follow_up_suggestions(suggestions, "assistant_current")
                ss.ai_chat_messages.append({"role": "assistant", "content": err, "suggestions": suggestions})