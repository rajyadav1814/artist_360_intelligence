"""Run all SQL migration files in order."""
import os
from src.database.connection import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "migrations",
)


def run_migrations() -> None:
    migration_files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")
    )
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for filename in migration_files:
                    filepath = os.path.join(MIGRATIONS_DIR, filename)
                    with open(filepath, "r", encoding="utf-8") as fh:
                        sql = fh.read()
                    cur.execute(sql)
                    logger.info(f"Applied migration: {filename}")
    finally:
        conn.close()
    logger.info("All migrations applied successfully")


if __name__ == "__main__":
    run_migrations()
