import os
import time
import logging
from urllib.parse import quote
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

from functools import lru_cache


def _build_session():
    """Return a requests.Session configured with retries/backoff."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


@lru_cache(maxsize=1000)
def get_label(artist_title: str) -> Optional[str]:
    """Look up the record label for a given artist or track title using MusicBrainz."""
    mb_contact = os.getenv("MUSICBRAINZ_EMAIL")
    user_agent = "Artist360Intelligence/1.0 (https://github.com/rajyadav1814/artist_360_intelligence)"
    headers = {"User-Agent": user_agent}
    if mb_contact:
        headers["From"] = mb_contact
    else:
        logger.debug("MUSICBRAINZ_EMAIL not set — consider setting it to comply with MusicBrainz policies")

    session = _build_session()

    def safe_get(url, timeout=10):
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            # Respect MusicBrainz polite rate: at most ~1 request per second
            time.sleep(1)
            return resp
        except Exception:
            # Let caller handle logging and retries via session
            raise

    url = f"https://musicbrainz.org/ws/2/release/?query={quote(artist_title)}&fmt=json&limit=1"
    try:
        resp = safe_get(url, timeout=10)
        if resp is None:
            return None
        resp.raise_for_status()
        data = resp.json()
        releases = data.get("releases", [])
        if not releases:
            return None
        first = releases[0]
        label_info = first.get("label-info", [])
        if label_info:
            label_name = label_info[0].get("label", {}).get("name")
            if label_name:
                return label_name
        return None
    except Exception as e:
        logger.error(f"Error fetching label for '{artist_title}': {e}")
        return None
