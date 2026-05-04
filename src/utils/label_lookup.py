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
    """Look up the record label for a given artist or track title.
    
    In music metadata, "Label" refers to the record label (company) that released 
    or published the song, responsible for production, marketing, and distribution.
    
    Currently attempts batch-optimized lookup via AI agent if possible.
    """
    # For single calls, we still use the agent but it's less efficient than batching
    from src.ai.label_agent import get_labels_batch
    results = get_labels_batch([artist_title])
    return results.get(artist_title)

def get_labels_batch_optimized(titles: list[str]) -> dict[str, str]:
    """
    Look up record labels for a list of titles in batches.
    """
    from src.ai.label_agent import get_labels_batch
    
    final_results = {}
    # Process in chunks of 20 as requested
    for i in range(0, len(titles), 20):
        chunk = titles[i : i + 20]
        # Filter out titles already in cache if needed, but for simplicity:
        logger.info(f"Fetching labels for chunk {i//20 + 1}...")
        batch_results = get_labels_batch(chunk)
        final_results.update(batch_results)
        
    return final_results
