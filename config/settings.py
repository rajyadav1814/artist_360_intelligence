import os
from dotenv import load_dotenv

load_dotenv()

# Database
# Use DATABASE_URL if available (for Supabase), otherwise use individual DB_* variables (for local)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Use Supabase connection string
    DB_CONFIG = {"dsn": DATABASE_URL}
else:
    # Use local PostgreSQL configuration
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "dbname": os.getenv("DB_NAME", "kworb_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }

# Scraper
BASE_URL = "https://kworb.net"
ITUNES_ARTISTS_URL = f"{BASE_URL}/itunes/"
SPOTIFY_ARTISTS_URL = f"{BASE_URL}/spotify/artists.html"
SPOTIFY_LISTENERS_URL = f"{BASE_URL}/spotify/listeners.html"

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


