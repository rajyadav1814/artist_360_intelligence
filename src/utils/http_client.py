import time
import requests
from config.settings import HEADERS, SCRAPE_DELAY
from src.utils.logger import get_logger

logger = get_logger(__name__)


def fetch_page(url: str, retries: int = 3, delay: float = SCRAPE_DELAY) -> str | None:
    """Fetch a URL and return HTML text, with retry logic and polite delay."""
    for attempt in range(1, retries + 1):
        try:
            time.sleep(delay)
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            logger.info(f"Fetched [{response.status_code}] {url}")
            return response.text
        except requests.RequestException as exc:
            logger.warning(f"Attempt {attempt}/{retries} failed for {url}: {exc}")
            if attempt < retries:
                time.sleep(delay * attempt)
    logger.error(f"All retries exhausted for {url}")
    return None
