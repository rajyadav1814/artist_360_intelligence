import os
from dotenv import load_dotenv

load_dotenv()

# Database
# Use DATABASE_URL if available (for Supabase), otherwise use individual DB_* variables (for local)
DATABASE_URL = os.getenv("DATABASE_URL")

# If running under Streamlit and the app's Secrets were added as a TOML file
# (or in Streamlit Cloud under a [database] table), load them as a fallback.
if not DATABASE_URL:
    try:
        import tomllib
        secrets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            with open(secrets_path, "rb") as fh:
                st_secrets = tomllib.load(fh)
            # top-level DATABASE_URL
            DATABASE_URL = st_secrets.get("DATABASE_URL") or DATABASE_URL
            # or nested under [database]
            db_tbl = st_secrets.get("database") or {}
            if not DATABASE_URL:
                DATABASE_URL = db_tbl.get("DATABASE_URL") or db_tbl.get("database_url")
            # Also populate individual DB_* if present
            if db_tbl:
                os.environ.setdefault("DB_HOST", db_tbl.get("DB_HOST") or db_tbl.get("db_host", os.getenv("DB_HOST")))
                os.environ.setdefault("DB_PORT", str(db_tbl.get("DB_PORT") or db_tbl.get("db_port", os.getenv("DB_PORT"))))
                os.environ.setdefault("DB_NAME", db_tbl.get("DB_NAME") or db_tbl.get("db_name", os.getenv("DB_NAME")))
                os.environ.setdefault("DB_USER", db_tbl.get("DB_USER") or db_tbl.get("db_user", os.getenv("DB_USER")))
                os.environ.setdefault("DB_PASSWORD", db_tbl.get("DB_PASSWORD") or db_tbl.get("db_password", os.getenv("DB_PASSWORD")))
    except Exception:
        # tomllib may not be available on very old Pythons; ignore fallback in that case
        pass

if DATABASE_URL:
    # Use Supabase connection string
    DB_CONFIG = {"dsn": DATABASE_URL}
else:
    # Use local PostgreSQL configuration
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "ep-crimson-bird-am5ez25h-pooler.c-5.us-east-1.aws.neon.tech"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "dbname": os.getenv("DB_NAME", "artist"),
        "user": os.getenv("DB_USER", "neondb_owner"),
        "password": os.getenv("DB_PASSWORD", "npg_b3lREgINh6Dk"),
    }

# Scraper
BASE_URL = "https://kworb.net"
ITUNES_ARTISTS_URL = f"{BASE_URL}/itunes/"
ITUNES_TRACKS_URL = f"{BASE_URL}/ww"
SPOTIFY_ARTISTS_URL = f"{BASE_URL}/spotify/artists.html"
SPOTIFY_LISTENERS_URL = f"{BASE_URL}/spotify/listeners.html"
SPOTIFY_DAILY_URL = f"{BASE_URL}/spotify/country/{{country}}_daily.html"
ITUNES_DAILY_URL = f"{BASE_URL}/charts/itunes/{{country}}.html"
YOUTUBE_DAILY_URL = f"{BASE_URL}/youtube/"

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


