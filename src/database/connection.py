import psycopg2
from psycopg2.extras import RealDictCursor
from config.settings import DB_CONFIG
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_connection():
    """Return a new psycopg2 connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except psycopg2.OperationalError as exc:
        logger.error(f"Database connection failed: {exc}")
        raise


def execute_query(query: str, params=None, fetch: bool = False):
    """Execute a query and optionally return rows."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if fetch:
                    return cur.fetchall()
    finally:
        conn.close()
