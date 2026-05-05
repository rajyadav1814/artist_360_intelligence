import json
import os
from typing import Dict, List, Optional
import anthropic
from dotenv import load_dotenv
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

def _get_client() -> Optional[anthropic.Anthropic]:
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logger.warning("CLAUDE_API_KEY not found in environment")
        return None
    return anthropic.Anthropic(api_key=api_key)

def get_labels_batch(titles: List[str]) -> Dict[str, str]:
    """
    Use Claude to identify record labels for a batch of track/artist titles.
    Returns a dictionary mapping the input title to the identified label.
    """
    if not titles:
        return {}

    client = _get_client()
    if not client:
        return {title: "Independent" for title in titles}

    model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20240620")
    
    titles_str = "\n".join([f"- {t}" for t in titles])
    
    system_prompt = """
    You are a music industry expert. Your task is to identify the record label for the given list of music tracks/artists.
    The input will be a list of strings in the format "Artist - Title" or just "Video Title".

    In music metadata, "Label" means the record label (company) that released or published the song.
    A label is the company responsible for:
    - Producing the music
    - Marketing & promotion
    - Distribution (Spotify, Apple Music, etc.)
    
    Rules:
    1. Identify the primary record label (e.g., Columbia, Atlantic, Interscope, Republic).
    2. If it's an independent release, return "Independent" or the specific indie label name.
    3. Return the result ONLY as a JSON object where the key is the exact input string and the value is the label name.
    4. If you are unsure, return "Independent".
    5. Do not include any explanation or extra text.
    """

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"Provide record labels for these titles:\n{titles_str}"}
            ]
        )
        
        content = response.content[0].text if response.content else "{}"
        
        # Clean potential markdown formatting
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        labels_map = json.loads(content)
        
        # Ensure all requested titles have an entry
        final_map = {}
        for title in titles:
            final_map[title] = labels_map.get(title, "Independent")
            
        return final_map
        
    except Exception as e:
        logger.error(f"Error in batch label lookup: {e}")
        return {title: "Independent" for title in titles}
