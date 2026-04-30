import os
import sys
import anthropic
import pandas as pd
from dotenv import load_dotenv
from src.database.connection import get_connection

# Load environment variables
load_dotenv()

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20240620")

# Fallback: read Streamlit secrets TOML if env vars not set (useful when running
# under Streamlit Cloud or when secrets were synced to .streamlit/secrets.toml)
if not CLAUDE_API_KEY or not CLAUDE_MODEL:
    try:
        import tomllib
        secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
        # also check workspace-level .streamlit
        alt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".streamlit", "secrets.toml")
        for p in (secrets_path, alt_path):
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    s = tomllib.load(fh)
                CLAUDE_API_KEY = CLAUDE_API_KEY or s.get("CLAUDE_API_KEY")
                CLAUDE_MODEL = CLAUDE_MODEL or s.get("CLAUDE_MODEL")
                # also check under [ai] or top-level
                ai_tbl = s.get("ai") or {}
                CLAUDE_API_KEY = CLAUDE_API_KEY or ai_tbl.get("CLAUDE_API_KEY")
                CLAUDE_MODEL = CLAUDE_MODEL or ai_tbl.get("CLAUDE_MODEL")
                break
    except Exception:
        pass

if not CLAUDE_API_KEY:
    print("Error: CLAUDE_API_KEY not found in environment or .streamlit/secrets.toml.")
    sys.exit(1)

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

def get_db_schema():
    return """
    Database Tables and Columns (PostgreSQL):
    
    1. artists (id, name, profile_url)
       - Primary table for artists.
    
    2. itunes_artist_rankings (artist_id, rank, rank_change, total_points, scrape_date)
       - Global artist rankings. Joined with artists.id.
    
    3. spotify_artists (artist_id, monthly_listeners, peak_listeners, peak_date, scrape_date)
       - Spotify monthly listener stats. Joined with artists.id.
    
    4. track_metadata (artist_title, label_name, representative_owner)
       - Metadata for tracks. 'artist_title' is unique and matches 'spotify_daily.artist_title'.
    
    5. spotify_daily (date, country, rank, artist_title, days, peak, streams, streams_change, total_streams)
       - Daily Spotify track charts. 'artist_title' is the song name (formatted as 'Artist - Song').
       - Common countries: 'global', 'us'.
    
    6. itunes_daily (date, country, rank, artist_title, days, peak, points, points_change, total_points)
       - Daily iTunes track charts. 'artist_title' is formatted as 'Artist - Song'.
       - Common countries: 'ww' (Worldwide), 'us'.
    
    7. youtube_daily (date, rank, video_title, views, likes)
       - Daily YouTube charts.
    
    8. artist_details (artist_id, page_title, songs_count, albums_count, countries_count, top_songs, top_albums, top_countries, scrape_date)
       - Detailed artist stats. Joined with artists.id.

    Guidelines for SQL Generation:
    - For "performance" queries, analyze BOTH 'spotify_daily' (streams) and 'itunes_daily' (points) to give a balanced view.
    - To get "Label Names" or "Representative Owners", ALWAYS JOIN with 'track_metadata' ON artist_title.
    - If the user asks about "acquisition" or "independent artists", filter by label_name='Independent' in track_metadata and look at combined performance across platforms.
    - For "Last week", use: date >= (SELECT MAX(date) FROM spotify_daily) - INTERVAL '7 days'.
    - For "Debut tracks" on a specific date, find tracks that exist on that date but NOT before that date in the same table.
    - For "Consistency", find tracks that appear in the Top X positions for all N consecutive days.
    - Always use ILIKE for artist or track names to be flexible.
    - Limit results to 50 unless asked for more.
    """

def ask_bot(question):
    schema = get_db_schema()
    
    # Step 1: AI generates SQL
    prompt = f"""
    You are a high-level Music Industry Strategy Consultant and Data Analyst. 
    Based on this PostgreSQL schema:
    {schema}
    
    Convert this user question into a VALID and EFFICIENT PostgreSQL query: "{question}"
    
    Important rules:
    1. Output ONLY the raw SQL query. No markdown, no explanation.
    2. If the user asks for "performance" or "rankings" generally, try to provide data from BOTH 'spotify_daily' and 'itunes_daily' (using a JOIN or UNION if appropriate).
    3. If label details or acquisition insights are needed, JOIN with 'track_metadata'.
    4. For "last week" or "previous day", use the latest date in the database as the reference point.
    5. Always use ILIKE for text matching to ensure flexibility.
    """
    
    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        sql_query = message.content[0].text.strip()
        if "```sql" in sql_query:
            sql_query = sql_query.split("```sql")[1].split("```")[0].strip()
        elif "```" in sql_query:
            sql_query = sql_query.split("```")[1].strip()
            
        # Step 2: Run SQL
        import psycopg2
        from config.settings import DB_CONFIG
        
        local_config = DB_CONFIG.copy()
        if 'cursor_factory' in local_config:
            del local_config['cursor_factory']
            
        conn = psycopg2.connect(**local_config)
        try:
            df = pd.read_sql_query(sql_query, conn)
        finally:
            conn.close()
        
        if df.empty:
            return f"I couldn't find any data for that request. (SQL used: {sql_query})"

        # Step 3: Natural language answer
        result_str = df.to_string(index=False)
        final_prompt = f"""
        You are a Music Industry Strategy Consultant. 
        User Question: {question}
        Database Result Data:
        {result_str}
        
        Provide a comprehensive, professional analysis in English.
        1. Format the data into a clean Markdown table.
        2. Highlight key trends, outliers, or strategic takeaways.
        3. If the user asked for business advice (like acquisition), provide a data-backed recommendation.
        4. If the data has numerical values suitable for a chart, include a JSON block:
        [CHART_DATA]
        {{
            "type": "bar" or "line", 
            "labels": ["X axis labels"],
            "datasets": [{{ "label": "Metric Name", "data": [Y axis values] }}]
        }}
        [/CHART_DATA]
        """
        
        final_message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": final_prompt}]
        )
        
        return final_message.content[0].text
    except Exception as e:
        return f"Error occurred: {e}\n\nTraceback: {str(e)}"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run a single question from command line
        question = " ".join(sys.argv[1:])
        print(ask_bot(question))
    else:
        print("--- Advanced Music AI Analyst (Table Details Engine) ---")
        print("Type 'exit' to quit.")
        while True:
            try:
                user_q = input("\nAsk your question: ")
                if user_q.lower() == 'exit': break
                if not user_q.strip(): continue
                
                answer = ask_bot(user_q)
                print(f"\n[AI Answer]:\n{answer}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
