import psycopg
from psycopg.rows import dict_row
from config.settings import DB_CONFIG
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_connection():
    """Return a new psycopg (v3) connection with dict-style rows."""
    try:
        conn = psycopg.connect(**DB_CONFIG, row_factory=dict_row)
        return conn
    except psycopg.OperationalError as exc:
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
