import json
import os
import re
from typing import Any, Dict, Optional

import httpx
import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from src.ai.advanced_visualizations import (
	render_multi_chart_view,
	render_insights_dashboard,
)
from src.database.connection import get_connection

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
- itunes_artist_rankings(id, artist_id, rank, rank_change, total_points, itunes_points, spotify_points, apple_music_points, shazam_points, youtube_points, other_points, top_country, num_countries, scraped_at, scrape_date)
- spotify_artists(id, artist_id, monthly_listeners, peak_listeners, peak_date, scraped_at, scrape_date)
- trending_artists_monthly(id, artist_id, source, rank, rank_change, total_points, top_country, month, scraped_at)
- artist_details(id, artist_id, page_title, snapshot_text, songs_count, albums_count, countries_count, top_songs, top_albums, top_countries, scraped_at, scrape_date)
- scrape_runs(id, source, status, rows_upserted, error_msg, started_at, finished_at)

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
]

NO_CHART_PATTERNS = [
	r"\bexplain\b",
	r"\bwhy\b",
	r"\bsummary\b",
	r"\bsummarize\b",
	r"\btell me\b",
	r"\bwhat does\b",
	r"\bwhich artist\b",
	r"\bwho is\b",
	r"\bdetails?\b",
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
	return _read_secret("OPENAI_MODEL") or "gpt-4o-mini"


def _openai_chat_json(api_key: str, model: str, messages: list[dict[str, str]]) -> Dict[str, Any]:
	with httpx.Client(timeout=45.0) as client:
		response = client.post(
			"https://api.openai.com/v1/chat/completions",
			headers={
				"Authorization": f"Bearer {api_key}",
				"Content-Type": "application/json",
			},
			json={
				"model": model,
				"messages": messages,
				"temperature": 0.1,
				"response_format": {"type": "json_object"},
			},
		)

	if response.status_code == 401:
		raise PermissionError("OpenAI authentication failed (invalid API key).")
	response.raise_for_status()

	payload = response.json()
	content = payload["choices"][0]["message"].get("content", "{}")
	return json.loads(content)


def _openai_chat_text(api_key: str, model: str, messages: list[dict[str, str]]) -> str:
	with httpx.Client(timeout=45.0) as client:
		response = client.post(
			"https://api.openai.com/v1/chat/completions",
			headers={
				"Authorization": f"Bearer {api_key}",
				"Content-Type": "application/json",
			},
			json={
				"model": model,
				"messages": messages,
				"temperature": 0.3,
			},
		)

	if response.status_code == 401:
		raise PermissionError("OpenAI authentication failed (invalid API key).")
	response.raise_for_status()

	payload = response.json()
	return payload["choices"][0]["message"].get("content", "")


def _local_plan(question: str) -> Dict[str, Any]:
	"""Generate query plans locally without API calls."""
	q = question.lower()

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


def _clean_result_df(df: pd.DataFrame) -> pd.DataFrame:
	"""Clean DataFrame by removing header-like rows and normalizing columns."""
	if df.empty:
		return df

	cleaned = df.copy()
	cleaned.columns = [str(c).strip() for c in cleaned.columns]

	mask_header_like = pd.Series(True, index=cleaned.index)
	for col in cleaned.columns:
		mask_header_like &= cleaned[col].astype(str).str.strip().str.lower().eq(col.lower())

	if mask_header_like.any():
		cleaned = cleaned[~mask_header_like].copy()

	return cleaned


def _format_value(value: Any) -> str:
	"""Format values for display with proper units and formatting."""
	if pd.isna(value):
		return "n/a"
	if isinstance(value, (int, float)):
		if float(value).is_integer():
			return f"{int(value):,}"
		return f"{value:,.2f}"
	return str(value)


def _small_talk_response(question: str) -> Optional[str]:
	"""Generate friendly responses to small talk."""
	q = question.strip().lower()
	for pattern in SMALL_TALK_PATTERNS:
		if re.match(pattern, q):
			break
	else:
		return None

	if q in {"thanks", "thank you"}:
		return "You're welcome. I can help with rankings, listeners, countries, trends, or quick summaries from the database."

	if "how are you" in q or "how r you" in q:
		return "I’m ready. Ask about rankings, listeners, countries, scrape activity, or artist details and I’ll keep it concise."

	return (
		"Hi. how can i help you today?"	)


def _wants_chart(question: str) -> bool:
	q = question.lower()
	if any(re.search(pattern, q) for pattern in NO_CHART_PATTERNS):
		return False
	return any(re.search(pattern, q) for pattern in CHART_TRIGGER_PATTERNS)


def _should_render_chart(question: str, df: pd.DataFrame, chart_spec: Dict[str, Any]) -> bool:
	if df.empty:
		return False
	if not chart_spec.get("x") or not chart_spec.get("y"):
		return False
	if not _wants_chart(question):
		return False
	if len(df) < 2:
		return False
	return True


def _wants_data_table(question: str, df: pd.DataFrame) -> bool:
	"""Return True only when the user intent suggests inspecting raw rows."""
	if df.empty:
		return False
	q = question.lower()
	if any(re.search(pattern, q) for pattern in NO_TABLE_PATTERNS):
		return False
	if any(re.search(pattern, q) for pattern in TABLE_TRIGGER_PATTERNS):
		return True
	if len(df) <= 5 and ("name" in df.columns or "source" in df.columns):
		return True
	return False


def _push_suggestion(suggestions: list[str], suggestion: Optional[str], limit: int = 3) -> None:
	"""Append a suggestion if it is non-empty and not already present."""
	if not suggestion:
		return
	normalized = suggestion.strip()
	if not normalized:
		return
	if normalized in suggestions:
		return
	if len(suggestions) >= limit:
		return
	suggestions.append(normalized)


def _top_text_values(df: pd.DataFrame, column: str, limit: int = 3) -> list[str]:
	"""Return the top non-empty text values for a column."""
	if column not in df.columns:
		return []
	series = df[column].dropna().astype(str).str.strip()
	series = series[series.ne("")]
	return series.drop_duplicates().head(limit).tolist()


def _default_dynamic_suggestions(question: str) -> list[str]:
	"""Build non-static fallback suggestions based on the current topic."""
	pool = [
		"Show the current top 5 artists by rank",
		"Which countries appear most in the latest ranking snapshot?",
		"Give me a short summary of recent scrape activity",
		"Which artist has the highest monthly listeners right now?",
		"Compare ranking points versus Spotify listeners",
		"Which artists have the strongest country reach?",
		"Show recent scrape runs with failed statuses",
		"Summarize the latest iTunes ranking snapshot",
	]
	if not pool:
		return []
	start = abs(hash(question.strip().lower() or "music")) % len(pool)
	return [pool[(start + offset) % len(pool)] for offset in range(3)]


def _build_follow_up_suggestions(question: str, df: Optional[pd.DataFrame] = None) -> list[str]:
	"""Generate contextual follow-up suggestions from the current topic and result set."""
	q = question.lower()
	suggestions: list[str] = []

	if df is not None and not df.empty:
		artist_names = _top_text_values(df, "name")
		countries = _top_text_values(df, "top_country")
		sources = _top_text_values(df, "source")

		if "monthly_listeners" in df.columns:
			if artist_names:
				_push_suggestion(suggestions, f"Compare {artist_names[0]} and {artist_names[min(1, len(artist_names) - 1)]} by monthly listeners" if len(artist_names) > 1 else f"Give me a short profile of {artist_names[0]}")
			_push_suggestion(suggestions, "Which artist has the highest peak listeners?")
			_push_suggestion(suggestions, "Show current top artists by ranking points")

		if "rank" in df.columns and "total_points" in df.columns:
			if artist_names:
				_push_suggestion(suggestions, f"Why is {artist_names[0]} ranked this high?")
			_push_suggestion(suggestions, "Which artists have the biggest rank changes?")
			_push_suggestion(suggestions, "Show a chart of top artists by total points")

		if "top_country" in df.columns and "artists_count" in df.columns:
			if countries:
				_push_suggestion(suggestions, f"Which artists are driving the ranking in {countries[0]}?")
				if len(countries) > 1:
					_push_suggestion(suggestions, f"Compare artist presence in {countries[0]} and {countries[1]}")
			_push_suggestion(suggestions, "Show the top artists by total points")

		if "source" in df.columns and "rows_upserted" in df.columns:
			if sources:
				_push_suggestion(suggestions, f"Which {sources[0]} scrape run loaded the most rows?")
			_push_suggestion(suggestions, "Show scrape runs with failed status")
			_push_suggestion(suggestions, "Summarize overall scrape health")

		if "name" in df.columns and "top_country" in df.columns and artist_names:
			_push_suggestion(suggestions, f"Tell me more about {artist_names[0]}")
			if countries:
				_push_suggestion(suggestions, f"Which other artists are strongest in {countries[0]}?")

	if any(token in q for token in ["hi", "hello", "hey", "hii"]):
		_push_suggestion(suggestions, "Summarize the latest ranking snapshot")
		_push_suggestion(suggestions, "Which artist has the highest monthly listeners right now?")
		_push_suggestion(suggestions, "Show recent scrape activity")

	if "listener" in q or "spotify" in q:
		_push_suggestion(suggestions, "Which artists are growing fastest by rank?")
		_push_suggestion(suggestions, "Compare listener leaders with ranking leaders")

	if "country" in q:
		_push_suggestion(suggestions, "Which artists have the highest total points overall?")
		_push_suggestion(suggestions, "Show the latest ranking leaders by country")

	if "run" in q or "scrape" in q or "activity" in q:
		_push_suggestion(suggestions, "Which source is producing the largest loads?")
		_push_suggestion(suggestions, "Show the most recent failed scrape runs")

	for fallback in _default_dynamic_suggestions(question):
		_push_suggestion(suggestions, fallback)

	return suggestions[:3]


def _queue_follow_up_question(question: str) -> None:
	"""Queue a suggestion chip question for immediate processing on rerun."""
	st.session_state.ai_pending_question = question


def _reset_chat_session() -> None:
	"""Clear the current conversation and return to the empty state."""
	st.session_state.ai_chat_messages = []
	st.session_state.ai_pending_question = None
	st.session_state.ai_chat_title = None


def _derive_chat_title(question: str) -> str:
	"""Build a short thread title from the first user prompt."""
	words = question.strip().split()
	if not words:
		return "New chat"
	title = " ".join(words[:7]).strip()
	if len(words) > 7:
		title += "..."
	return title


def _render_chat_shell(has_messages: bool, title: Optional[str]) -> None:
	"""Render a ChatGPT-style top action bar with current thread context."""
	left_col, right_col = st.columns([6, 1.4])
	with left_col:
		if has_messages:
			st.markdown(
				f"""
				<div class="ai-thread-head">
					<div class="ai-thread-kicker">Current chat</div>
					<div class="ai-thread-title">{title or 'New chat'}</div>
				</div>
				""",
				unsafe_allow_html=True,
			)
		else:
			st.markdown(
				"""
				<div class="ai-thread-head ai-thread-head-empty">
					<div class="ai-thread-kicker">AI Analyst</div>
					<div class="ai-thread-title">New chat</div>
				</div>
				""",
				unsafe_allow_html=True,
			)
	with right_col:
		st.button(
			"+ New chat",
			key="ai_new_chat_button",
			use_container_width=True,
			on_click=_reset_chat_session,
			disabled=not has_messages,
		)


def _render_empty_state() -> Optional[str]:
	"""Render a centered, ChatGPT-like composer before the first message."""
	starter_prompts = _default_dynamic_suggestions("start")
	outer_left, center_col, outer_right = st.columns([1.2, 3.6, 1.2])
	with center_col:
		st.markdown('<div class="ai-empty-stage">', unsafe_allow_html=True)
		st.markdown(
			"""
			<div class="ai-hero-shell">
				<div class="ai-hero-badge">AI Analyst</div>
				<h2>Ask anything about your music data</h2>
				<p>Query PostgreSQL in natural language, get a direct answer, and only see charts or tables when they add value.</p>
			</div>
			""",
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
				st.button(
					prompt,
					key=f"starter_prompt_{idx}",
					use_container_width=True,
					on_click=_queue_follow_up_question,
					args=(prompt,),
				)
		st.markdown('</div>', unsafe_allow_html=True)
		st.markdown('</div>', unsafe_allow_html=True)

	return None


def _render_follow_up_suggestions(suggestions: list[str], message_key: str) -> None:
	"""Render suggestion buttons with improved styling."""
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
			)


def _generate_plan(question: str, api_key: Optional[str], model: str) -> Dict[str, Any]:
	"""Generate query plan from AI or use fallback local plan."""
	if _is_top_intent(question):
		return _force_rank_plan(question)

	if not api_key:
		return _local_plan(question)

	try:
		plan = _openai_chat_json(
			api_key,
			model,
			messages=[
				{
					"role": "system",
					"content": (
						"You are a music analytics assistant. Generate a safe query plan in JSON with keys: "
						"sql, chart_type, x, y, title. chart_type must be 'multi' for intelligent multi-chart. "
						"Always use LIMIT with appropriate count (10-20 for top-N queries)."
					),
				},
				{
					"role": "user",
					"content": (
						f"{SCHEMA_CONTEXT}\n\n"
						"Rules:\n"
						"- Use only listed tables and columns.\n"
						"- Use only SELECT/CTE style queries.\n"
						"- Keep results readable.\n"
						"- For 'top 10' queries, ensure LIMIT 10.\n"
						f"Question: {question}"
					),
				},
			],
		)
		return {
			"sql": str(plan.get("sql", "")).strip(),
			"chart_type": str(plan.get("chart_type") or ("multi" if _wants_chart(question) else "none")).lower(),
			"x": plan.get("x"),
			"y": plan.get("y"),
			"title": plan.get("title") or "Results",
		}
	except PermissionError:
		raise
	except Exception:
		return _local_plan(question)


def _enforce_safe_sql(candidate_sql: str) -> str:
	"""Validate SQL for safety and add default LIMIT."""
	sql = candidate_sql.strip().rstrip(";")
	sql_l = sql.lower()

	if not sql_l:
		raise ValueError("No query generated for this question.")
	if not (sql_l.startswith("select") or sql_l.startswith("with")):
		raise ValueError("Only SELECT queries are allowed.")
	if DANGEROUS_SQL_RE.search(sql):
		raise ValueError("Query contains unsafe keywords.")

	cte_names = {name.lower() for name in CTE_NAME_RE.findall(sql)}
	referenced_tables = {
		tbl.split(".")[-1].lower()
		for tbl in TABLE_REF_RE.findall(sql)
	}
	unknown_tables = referenced_tables.difference(ALLOWED_TABLES.union(cte_names))
	if unknown_tables:
		raise ValueError(
			"Query referenced unsupported tables: " + ", ".join(sorted(unknown_tables))
		)

	if not LIMIT_RE.search(sql):
		sql = f"{sql} LIMIT 250"

	return sql


def _run_query(sql: str) -> pd.DataFrame:
	"""Execute query and return results as DataFrame."""
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


def _generate_summary_stats(df: pd.DataFrame) -> Dict[str, Any]:
	"""Generate statistical summary of results."""
	stats = {
		"total_rows": len(df),
		"columns": df.columns.tolist(),
	}

	numeric_cols = df.select_dtypes(include="number").columns.tolist()
	for col in numeric_cols:
		valid_data = df[col].dropna()
		if len(valid_data) > 0:
			stats[f"{col}_max"] = valid_data.max()
			stats[f"{col}_min"] = valid_data.min()
			stats[f"{col}_mean"] = valid_data.mean()
			stats[f"{col}_median"] = valid_data.median()

	return stats


def _summarize_results(
	question: str,
	sql: str,
	df: pd.DataFrame,
	api_key: Optional[str],
	model: str,
) -> str:
	"""Generate intelligent summary of query results."""
	if df.empty:
		return "📊 No results found for that question. Try adjusting your filters or asking differently."

	stats = _generate_summary_stats(df)
	row_count = stats["total_rows"]

	if not api_key:
		if "name" in df.columns and "monthly_listeners" in df.columns:
			top = df.nlargest(3, "monthly_listeners")
			lines = [
				f"Here’s a quick read on the top {row_count} artists by monthly listeners.",
				"\nLeading artists:",
			]
			for idx, (_, row) in enumerate(top.iterrows(), 1):
				lines.append(f"{idx}. **{row['name']}** with {_format_value(row['monthly_listeners'])} listeners")

			if "peak_listeners" in df.columns:
				avg_peak = df["peak_listeners"].mean()
				lines.append(f"\nAverage peak listeners across this set: {_format_value(avg_peak)}.")

			lines.append(f"\nI’m showing {row_count} results.")
			return "\n".join(lines)

		if "top_country" in df.columns and "artists_count" in df.columns:
			top = df.nlargest(3, "artists_count")
			lines = [
				"Here’s the current country distribution from the latest rankings.",
				"\nTop countries:",
			]
			for idx, (_, row) in enumerate(top.iterrows(), 1):
				lines.append(f"{idx}. **{row['top_country']}** with {_format_value(row['artists_count'])} artists")

			lines.append(f"\nThis result covers {row_count} countries.")
			return "\n".join(lines)

		return f"I found {row_count} results. I can also visualize them if you want a chart."

	# AI-powered summary
	preview_csv = df.head(20).to_csv(index=False)
	prompt = (
		"You are a music data analyst. Generate a concise, conversational summary in 3-4 sentences with key metrics. "
		"Keep the tone natural and helpful, not robotic or overly cheerful. Avoid emojis unless the user used them first.\n\n"
		f"Question: {question}\n"
		f"Results returned: {row_count}\n"
		f"Data preview:\n{preview_csv}"
	)
	try:
		text = _openai_chat_text(
			api_key,
			model,
			messages=[
				{
					"role": "system",
					"content": "Be accurate, concise, and conversational. Include relevant statistics. Use simple markdown only when helpful.",
				},
				{"role": "user", "content": prompt},
			],
		)
		if text:
			return text
	except PermissionError:
		raise
	except Exception:
		pass

	return f"I found {row_count} results. If you want, I can also turn this into a chart."


def _choose_chart_spec(df: pd.DataFrame, plan: Dict[str, Any]) -> Dict[str, Any]:
	"""Select appropriate chart specifications based on data."""
	columns = df.columns.tolist()
	numeric_cols = df.select_dtypes(include="number").columns.tolist()

	x = plan.get("x")
	y = plan.get("y")
	chart_type = str(plan.get("chart_type", "multi")).lower()

	if x not in columns:
		x = columns[0] if columns else None
	if y not in columns:
		y = numeric_cols[0] if numeric_cols else None

	return {
		"chart_type": chart_type,
		"x": x,
		"y": y,
		"title": plan.get("title") or "Results",
	}


def _render_data_table(df: pd.DataFrame, max_rows: int = 10) -> None:
	"""Render a formatted data table."""
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


def _latest_assistant_index(messages: list[dict[str, Any]]) -> Optional[int]:
	"""Return the index of the most recent assistant message in chat history."""
	for idx in range(len(messages) - 1, -1, -1):
		if messages[idx].get("role") == "assistant":
			return idx
	return None


def render_custom_chatbot() -> None:
	"""Main chatbot interface with advanced multi-chart visualization."""
	st.markdown(
		"""
		<style>
		.ai-empty-stage {
			display: flex;
			flex-direction: column;
			justify-content: flex-start;
			gap: 0.65rem;
			padding: clamp(0.35rem, 2vh, 1.1rem) 0 0.5rem;
		}
		.ai-thread-head {
			display: flex;
			flex-direction: column;
			gap: 0.2rem;
			padding: 0.15rem 0 0.75rem;
		}
		.ai-thread-head-empty {
			opacity: 0.84;
		}
		.ai-thread-kicker {
			font-size: 0.76rem;
			letter-spacing: 0.08em;
			text-transform: uppercase;
			color: #7e8cb4;
		}
		.ai-thread-title {
			font-size: 1.15rem;
			font-weight: 600;
			color: #eef2ff;
			letter-spacing: -0.02em;
		}
		.ai-hero-shell {
			display: flex;
			flex-direction: column;
			justify-content: flex-start;
			align-items: center;
			text-align: center;
			gap: 0.55rem;
			padding: 0.2rem 0 0.35rem;
		}
		.ai-hero-shell h2 {
			margin: 0;
			font-size: clamp(1.5rem, 2.8vw, 2.5rem);
			line-height: 1.05;
			font-weight: 700;
			letter-spacing: -0.03em;
			color: #f6f8ff;
		}
		.ai-hero-shell p {
			max-width: 42rem;
			margin: 0;
			font-size: 0.93rem;
			line-height: 1.45;
			color: #98a4c8;
		}
		.ai-hero-badge {
			display: inline-flex;
			align-items: center;
			padding: 0.45rem 0.9rem;
			border-radius: 999px;
			border: 1px solid rgba(123, 145, 255, 0.28);
			background: rgba(25, 34, 73, 0.6);
			color: #c9d4ff;
			font-size: 0.85rem;
			letter-spacing: 0.04em;
			text-transform: uppercase;
		}
		.ai-starter-grid {
			margin-top: 0.45rem;
		}
		.ai-empty-stage div[data-testid="stForm"] {
			max-width: 860px;
			margin-left: auto;
			margin-right: auto;
		}
		div[data-testid="stForm"] {
			background: linear-gradient(180deg, rgba(22, 27, 47, 0.96) 0%, rgba(16, 20, 38, 0.96) 100%);
			border: 1px solid rgba(130, 146, 219, 0.14);
			border-radius: 26px;
			padding: 0.55rem;
			box-shadow: 0 22px 48px rgba(0, 0, 0, 0.28);
		}
		div[data-testid="stForm"] div[data-testid="stTextInput"] input {
			background: transparent;
			border: 0;
			font-size: 1rem;
			color: #f4f7ff;
		}
		div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button {
			border-radius: 999px;
			padding: 0.6rem 1.2rem;
			font-weight: 600;
			background: linear-gradient(135deg, #5f79ff 0%, #8ca2ff 100%);
			border: 0;
			color: #081022;
		}
		.stChatMessage {
			padding: 0.5rem 0;
			border-radius: 0.75rem;
		}
		.stChatMessage [data-testid="stMarkdownContainer"] {
			line-height: 1.6;
		}
		/* Chat-style left/right conversation layout */
		div[data-testid="stChatMessage"] {
			max-width: min(900px, 92vw);
			margin-left: auto;
			margin-right: auto;
			width: 100%;
			display: flex;
			align-items: flex-start;
			justify-content: flex-start;
			gap: 0.35rem;
		}
		div[data-testid^="stChatMessageAvatar"] {
			display: none !important;
		}
		div[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {
			max-width: min(700px, 76vw);
			border-radius: 16px;
			padding: 0.58rem 0.9rem;
			width: fit-content;
			min-width: 0;
		}
		/* Assistant on LEFT (text-first, minimal bubble) */
		div[data-testid="stChatMessage"]:has([data-testid*="assistant"], [data-testid*="Assistant"], [aria-label="assistant"]) {
			justify-content: flex-start;
		}
		div[data-testid="stChatMessage"]:has([data-testid*="assistant"], [data-testid*="Assistant"], [aria-label="assistant"]) [data-testid="stChatMessageContent"] {
			background: transparent;
			border: 0;
			padding-left: 0;
			padding-right: 0;
			max-width: min(720px, 80vw);
		}
		/* User on RIGHT (compact dark pill) */
		div[data-testid="stChatMessage"]:has([data-testid*="user"], [data-testid*="User"], [aria-label="user"]) {
			justify-content: flex-end;
		}
		div[data-testid="stChatMessage"]:has([data-testid*="user"], [data-testid*="User"], [aria-label="user"]) [data-testid="stChatMessageContent"] {
			background: linear-gradient(165deg, rgba(49, 53, 64, 0.9) 0%, rgba(36, 40, 51, 0.9) 100%);
			border: 1px solid rgba(130, 140, 170, 0.26);
			max-width: min(360px, 66vw);
			border-radius: 18px;
		}
		div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
			text-align: left;
		}
		div[data-testid="stChatInput"] {
			padding-top: 0.85rem;
		}
		div[data-testid="stChatInput"] textarea,
		div[data-testid="stChatInput"] input {
			border-radius: 22px;
			background: rgba(24, 29, 50, 0.96);
			border: 1px solid rgba(130, 146, 219, 0.12);
		}
		div[data-testid="stButton"] > button[kind="secondary"] {
			border-radius: 999px;
			background: rgba(18, 24, 43, 0.92);
			border: 1px solid rgba(130, 146, 219, 0.16);
			color: #e5ebff;
			font-weight: 600;
		}
		@media (max-height: 860px) {
			.ai-starter-grid {
				display: none;
			}
		}
		</style>
		""",
		unsafe_allow_html=True,
	)

	if "ai_chat_messages" not in st.session_state:
		st.session_state.ai_chat_messages = []
	if "ai_pending_question" not in st.session_state:
		st.session_state.ai_pending_question = None
	if "ai_chat_title" not in st.session_state:
		st.session_state.ai_chat_title = None

	api_key = _resolve_api_key()
	model = _resolve_model()
	pending_question = st.session_state.ai_pending_question
	if pending_question:
		st.session_state.ai_pending_question = None
	question: Optional[str] = None
	_render_chat_shell(bool(st.session_state.ai_chat_messages), st.session_state.ai_chat_title)
	if not st.session_state.ai_chat_messages and not pending_question:
		question = _render_empty_state()
	else:
		st.caption("Ask data questions in plain language. I’ll answer directly and only add charts when they are useful.")
	latest_assistant_idx = _latest_assistant_index(st.session_state.ai_chat_messages)

	# Display chat history
	for msg_idx, message in enumerate(st.session_state.ai_chat_messages):
		with st.chat_message(message["role"], avatar="🤖" if message["role"] == "assistant" else "👤"):
			st.markdown(message["content"])
			
			# Render multi-chart visualization
			if message["role"] == "assistant" and message.get("show_chart") and message.get("chart_data"):
				chart_df = pd.DataFrame(message["chart_data"])
				if not chart_df.empty:
					chart_spec = message.get("chart_spec", {})
					x = chart_spec.get("x")
					y = chart_spec.get("y")
					question = message.get("question", "")
					
					if x and y:
						render_multi_chart_view(chart_df, x, y, question)
						render_insights_dashboard(chart_df, x, y)

			if message["role"] == "assistant" and message.get("show_table") and message.get("chart_data"):
				table_df = pd.DataFrame(message["chart_data"])
				if not table_df.empty:
					_render_data_table(table_df, max_rows=15)

			# Render follow-up suggestions
			if (
				message["role"] == "assistant"
				and msg_idx == latest_assistant_idx
				and not pending_question
			):
				_render_follow_up_suggestions(
					message.get("suggestions", []),
					message_key=f"assistant_{msg_idx}",
				)

	# Input section
	if st.session_state.ai_chat_messages:
		question = st.chat_input("Ask about artists, listeners, rankings, countries, or trends")
	if not question:
		question = pending_question
	if not question:
		return
	if not st.session_state.ai_chat_messages:
		st.session_state.ai_chat_title = _derive_chat_title(question)

	# Add user message
	st.session_state.ai_chat_messages.append({"role": "user", "content": question})
	with st.chat_message("user", avatar="👤"):
		st.markdown(question)

	# Generate assistant response
	with st.chat_message("assistant", avatar="🤖"):
		with st.spinner("Looking through the data..."):
			try:
				# Check for small talk
				small_talk = _small_talk_response(question)
				if small_talk:
					suggestions = _build_follow_up_suggestions(question)
					st.markdown(small_talk)
					_render_follow_up_suggestions(suggestions, "assistant_current")
					st.session_state.ai_chat_messages.append(
						{
							"role": "assistant",
							"content": small_talk,
							"suggestions": suggestions,
						}
					)
					return

				# Generate and execute query
				plan = _generate_plan(question, api_key, model)
				safe_sql = _enforce_safe_sql(plan["sql"])
				result_df = _clean_result_df(_run_query(safe_sql))

				# Generate summaries and visualizations
				chart_spec = _choose_chart_spec(result_df, plan)
				show_chart = _should_render_chart(question, result_df, chart_spec)
				show_table = _wants_data_table(question, result_df)
				answer = _summarize_results(question, safe_sql, result_df, api_key, model)
				suggestions = _build_follow_up_suggestions(question, result_df)

				# Display answer summary
				st.markdown(answer)
				
				# Display multi-chart intelligent visualization
				if show_chart:
					render_multi_chart_view(
						result_df,
						chart_spec["x"],
						chart_spec["y"],
						question
					)
					
					# Display insights dashboard
					render_insights_dashboard(
						result_df,
						chart_spec["x"],
						chart_spec["y"]
					)
				
				# Display data table
				if show_table:
					_render_data_table(result_df)
				
				# Follow-up suggestions
				_render_follow_up_suggestions(suggestions, "assistant_current")

				# Save to chat history
				st.session_state.ai_chat_messages.append(
					{
						"role": "assistant",
						"content": answer,
						"chart_data": result_df.to_dict(orient="records"),
						"chart_spec": chart_spec,
						"show_chart": show_chart,
						"show_table": show_table,
						"suggestions": suggestions,
						"question": question,
					}
				)

			except PermissionError as e:
				err = (
					"OpenAI authentication failed. Please check that your API key is set correctly in the environment or Streamlit secrets."
				)
				st.error(err)
				suggestions = _build_follow_up_suggestions("artists")
				_render_follow_up_suggestions(suggestions, "assistant_current")
				st.session_state.ai_chat_messages.append({"role": "assistant", "content": err, "suggestions": suggestions})

			except Exception as exc:
				err = f"I couldn’t complete that request: {str(exc)}"
				st.error(err)
				suggestions = _build_follow_up_suggestions(question)
				_render_follow_up_suggestions(suggestions, "assistant_current")
				st.session_state.ai_chat_messages.append({"role": "assistant", "content": err, "suggestions": suggestions})