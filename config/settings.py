import os
from dotenv import load_dotenv

load_dotenv()

# Database
# Use DATABASE_URL if available (for Supabase), otherwise use individual DB_* variables (for local)
DATABASE_URL = os.getenv("DATABASE_URL")

# If running under Streamlit and the app's Secrets were added as a TOML file
# (or in Streamlit Cloud under a [database] table), load them as a fallback.
# 1. Try Streamlit secrets API first (works when actually deployed on Streamlit Cloud)
if not DATABASE_URL:
    try:
        import streamlit as st
        # Top-level: DATABASE_URL = "..."
        DATABASE_URL = st.secrets.get("DATABASE_URL") or DATABASE_URL

        # Nested under [database]
        if not DATABASE_URL:
            db_tbl = st.secrets.get("database") or {}
            DATABASE_URL = db_tbl.get("DATABASE_URL") or db_tbl.get("database_url")
            if db_tbl:
                os.environ.setdefault("DB_HOST", str(db_tbl.get("DB_HOST") or db_tbl.get("db_host") or os.getenv("DB_HOST", "")))
                os.environ.setdefault("DB_PORT", str(db_tbl.get("DB_PORT") or db_tbl.get("db_port") or os.getenv("DB_PORT", "5432")))
                os.environ.setdefault("DB_NAME", str(db_tbl.get("DB_NAME") or db_tbl.get("db_name") or os.getenv("DB_NAME", "")))
                os.environ.setdefault("DB_USER", str(db_tbl.get("DB_USER") or db_tbl.get("db_user") or os.getenv("DB_USER", "")))
                os.environ.setdefault("DB_PASSWORD", str(db_tbl.get("DB_PASSWORD") or db_tbl.get("db_password") or os.getenv("DB_PASSWORD", "")))
    except Exception:
        pass

# 2. Fall back to reading secrets.toml directly (local dev without `streamlit run`)
if not DATABASE_URL:
    try:
        import tomllib
        secrets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            with open(secrets_path, "rb") as fh:
                st_secrets = tomllib.load(fh)
            DATABASE_URL = st_secrets.get("DATABASE_URL") or DATABASE_URL
            db_tbl = st_secrets.get("database") or {}
            if not DATABASE_URL:
                DATABASE_URL = db_tbl.get("DATABASE_URL") or db_tbl.get("database_url")
            if db_tbl:
                os.environ.setdefault("DB_HOST", str(db_tbl.get("DB_HOST") or db_tbl.get("db_host") or os.getenv("DB_HOST", "")))
                os.environ.setdefault("DB_PORT", str(db_tbl.get("DB_PORT") or db_tbl.get("db_port") or os.getenv("DB_PORT", "5432")))
                os.environ.setdefault("DB_NAME", str(db_tbl.get("DB_NAME") or db_tbl.get("db_name") or os.getenv("DB_NAME", "")))
                os.environ.setdefault("DB_USER", str(db_tbl.get("DB_USER") or db_tbl.get("db_user") or os.getenv("DB_USER", "")))
                os.environ.setdefault("DB_PASSWORD", str(db_tbl.get("DB_PASSWORD") or db_tbl.get("db_password") or os.getenv("DB_PASSWORD", "")))
    except Exception:
        pass

if DATABASE_URL:
    DB_CONFIG = {"dsn": DATABASE_URL}
else:
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "dbname": os.getenv("DB_NAME", "artist"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "password"),
    }
    
# Scraper
BASE_URL = "https://kworb.net"
ITUNES_ARTISTS_URL = f"{BASE_URL}/itunes/"
ITUNES_TRACKS_URL = f"{BASE_URL}/ww"
SPOTIFY_ARTISTS_URL = f"{BASE_URL}/spotify/artists.html"
SPOTIFY_LISTENERS_URL = f"{BASE_URL}/spotify/listeners.html"
SPOTIFY_DAILY_URL = f"{BASE_URL}/spotify/country/{{country}}_daily.html"
ITUNES_DAILY_URL = f"{BASE_URL}/charts/itunes/{{country}}.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SCRAPE_DELAY = float(os.getenv("SCRAPE_DELAY_SECONDS", 2))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Logs directory
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


