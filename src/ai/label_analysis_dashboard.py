"""
Label Analysis dashboard — rich HTML/JS dashboard rendering label-level
dominance, normalization stats, and cross-platform reach for iTunes and
Spotify chart data. Mirrors the structure of album_movement.py.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src.database.connection import get_connection
from src.utils.logger import get_logger
from src.utils.ui import custom_selectbox

logger = get_logger(__name__)

# ─────────────────────── theme CSS ──────────────────────────────
_THEME_LIGHT = ":root{--bg:#F5F6FA;--bg2:#FFFFFF;--bg3:#F8F9FB;--bg4:#EEF1F7;--border:rgba(148,163,184,.2);--border2:rgba(148,163,184,.35);--t1:#1A1A1A;--t2:#4A5568;--t3:#8A8FA3;--t4:#A0AEC0;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#e31b23;--rd:rgba(227,27,35,.18);--blue:#e31b23;--bd:rgba(227,27,35,.18);--purple:#8f0f1c;--pd:rgba(143,15,28,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#ffb3bb;}"
_THEME_DARK  = ":root{--bg:#0d1117;--bg2:#161b26;--bg3:#1f2633;--bg4:#283041;--border:rgba(148,163,184,.15);--border2:rgba(148,163,184,.28);--t1:#ffffff;--t2:#cdd6e4;--t3:#8b95ad;--t4:#6b7a99;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#e31b23;--rd:rgba(227,27,35,.18);--blue:#e31b23;--bd:rgba(227,27,35,.18);--purple:#8f0f1c;--pd:rgba(143,15,28,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#ffb3bb;}"

# ─────────────────────── constants ──────────────────────────────

# Region scope → (itunes_country, spotify_country)
SCOPES: dict[str, tuple[str, str]] = {
    "Global / WW": ("ww", "global"),
    "United States": ("us", "us"),
    "Mexico":        ("mx", "mx"),
    "Argentina":     ("ar", "ar"),
    "Colombia":      ("co", "co"),
    "Brazil":        ("br", "br"),
}

COUNTRY_FLAGS: dict[str, str] = {
    "us": "🇺🇸 United States",
    "gb": "🇬🇧 United Kingdom", "uk": "🇬🇧 United Kingdom", "ar": "🇦🇷 Argentina",
    "au": "🇦🇺 Australia", "at": "🇦🇹 Austria", "be": "🇧🇪 Belgium",
    "bo": "🇧🇴 Bolivia", "br": "🇧🇷 Brazil", "bg": "🇧🇬 Bulgaria",
    "ca": "🇨🇦 Canada", "cl": "🇨🇱 Chile", "co": "🇨🇴 Colombia",
    "cr": "🇨🇷 Costa Rica", "cz": "🇨🇿 Czech Republic", "dk": "🇩🇰 Denmark",
    "do": "🇩🇴 Dominican Republic", "ec": "🇪🇨 Ecuador", "eg": "🇪🇬 Egypt",
    "sv": "🇸🇻 El Salvador", "ee": "🇪🇪 Estonia", "fi": "🇫🇮 Finland",
    "fr": "🇫🇷 France", "de": "🇩🇪 Germany", "gr": "🇬🇷 Greece",
    "gt": "🇬🇹 Guatemala", "hn": "🇭🇳 Honduras", "hk": "🇭🇰 Hong Kong",
    "hu": "🇭🇺 Hungary", "is": "🇮🇸 Iceland", "in": "🇮🇳 India",
    "id": "🇮🇩 Indonesia", "ie": "🇮🇪 Ireland", "il": "🇮🇱 Israel",
    "it": "🇮🇹 Italy", "jp": "🇯🇵 Japan", "lv": "🇱🇻 Latvia",
    "lt": "🇱🇹 Lithuania", "lu": "🇱🇺 Luxembourg", "my": "🇲🇾 Malaysia",
    "mx": "🇲🇽 Mexico", "ma": "🇲🇦 Morocco", "nl": "🇳🇱 Netherlands",
    "nz": "🇳🇿 New Zealand", "ni": "🇳🇮 Nicaragua", "ng": "🇳🇬 Nigeria",
    "no": "🇳🇴 Norway", "pa": "🇵🇦 Panama", "py": "🇵🇾 Paraguay",
    "pe": "🇵🇪 Peru", "ph": "🇵🇭 Philippines", "pl": "🇵🇱 Poland",
    "pt": "🇵🇹 Portugal", "ro": "🇷🇴 Romania", "sa": "🇸🇦 Saudi Arabia",
    "sg": "🇸🇬 Singapore", "sk": "🇸🇰 Slovakia", "za": "🇿🇦 South Africa",
    "kr": "🇰🇷 South Korea", "es": "🇪🇸 Spain", "se": "🇸🇪 Sweden",
    "ch": "🇨🇭 Switzerland", "tw": "🇹🇼 Taiwan", "th": "🇹🇭 Thailand",
    "tr": "🇹🇷 Turkey", "ae": "🇦🇪 UAE", "ua": "🇺🇦 Ukraine",
    "uy": "🇺🇾 Uruguay", "vn": "🇻🇳 Vietnam", "ve": "🇻🇪 Venezuela"
}

# Label normalization map: variant → canonical
LABEL_NORM: dict[str, str] = {
    # Sony / Columbia / Epic / RCA / Syco
    "Sony Music": "Sony Music Entertainment",
    "Sony Music Argentina": "Sony Music Entertainment",
    "Sony Music Associated Records": "Sony Music Entertainment",
    "Sony Music Australia": "Sony Music Entertainment",
    "Sony Music Brasil": "Sony Music Entertainment",
    "Sony Music Brazil": "Sony Music Entertainment",
    "Sony Music Colombia": "Sony Music Entertainment",
    "Sony Music Entertainment Australia": "Sony Music Entertainment",
    "Sony Music Entertainment Indonesia": "Sony Music Entertainment",
    "Sony Music Entertainment Japan": "Sony Music Entertainment",
    "Sony Music India": "Sony Music Entertainment",
    "Sony Music Japan": "Sony Music Entertainment",
    "Sony Music Labels": "Sony Music Entertainment",
    "Sony Music Latin": "Sony Music Latin",
    "Sony Music Nashville": "Sony Music Nashville",
    "Sony Music Records": "Sony Music Entertainment",
    "Sony Music Spain": "Sony Music Entertainment",
    "SonyMusic Nashville": "Sony Music Nashville",
    "Stuffed Monkey / Sony Music": "Sony Music Entertainment",
    "Stuffed Monkey/Sony Music": "Sony Music Entertainment",
    "Two Sides/Sony Music": "Sony Music Entertainment",
    "Columbia/Sony Music": "Columbia Records",
    "Grupo Frontera / Sony Music Latin": "Sony Music Latin",
    "Grupo Frontera LLC / Sony Music Latin": "Sony Music Latin",
    "Grupo Frontera LLC/Sony Music Latin": "Sony Music Latin",
    "Grupo Frontera Records / Sony Music Latin": "Sony Music Latin",
    "Grupo Frontera Records/Sony Music Latin": "Sony Music Latin",
    "Grupo Frontera/Sony Music Latin": "Sony Music Latin",
    "Mango Music / Sony Music Latin": "Sony Music Latin",
    "Palm Tree Records/Sony Music": "Sony Music Entertainment",
    "Premium Latin Music/Sony Music Latin": "Sony Music Latin",
    "Rancho Humilde / Sony Music Latin": "Rancho Humilde",
    "Rancho Humilde/Sony Music Latin": "Rancho Humilde",
    "River House Artists/Sony Music Nashville": "Sony Music Nashville",
    "River House/Sony Music Nashville": "Sony Music Nashville",
    "SAW Entertainment / Sony Music Nashville": "Sony Music Nashville",
    "SAW Entertainment/Sony Music Nashville": "Sony Music Nashville",
    "Street Mob Records/Sony Music Latin": "Sony Music Latin",
    "White Star/Sony Music Latin": "Sony Music Latin",
    "White World/Sony Music Latin": "Sony Music Latin",

    "Columbia": "Columbia Records",
    "Columbia Music Entertainment": "Columbia Records",
    "Columbia Nashville": "Columbia Records",
    "Albert Productions/Columbia Records": "Columbia Records",
    "Disruptor Records/Columbia Records": "Columbia Records",
    "Disruptor/Columbia": "Columbia Records",
    "Disruptor/Columbia Records": "Columbia Records",
    "Palm Tree/Columbia": "Columbia Records",
    "River House Artists/Columbia Nashville": "Columbia Records",
    "Rubyworks/Columbia": "Columbia Records",
    "SAW Entertainment / Columbia Nashville": "Columbia Records",
    "SAW Entertainment/Columbia": "Columbia Records",
    "SAW Entertainment/Columbia Nashville": "Columbia Records",
    "SAW/Columbia Nashville": "Columbia Records",
    "SAWGOD / Columbia Nashville": "Columbia Records",
    "SAWGOD Records/Columbia": "Columbia Records",
    "SAWGOD Records/Columbia Nashville": "Columbia Records",
    "SAWGOD/Columbia": "Columbia Records",
    "SAWGOD/Columbia Nashville": "Columbia Records",
    "SAWGOD/Columbia Records": "Columbia Records",
    "SonyATV/Columbia Nashville": "Columbia Records",
    "Syco/Columbia Records": "Columbia Records",
    
    "Epic": "Epic Records",
    "Epic Records Japan": "Epic Records",
    "Epic Records/Sommer House": "Epic Records",
    "Epic/Record Company TEN": "Epic Records",
    "Phonogenic/Epic Records": "Epic Records",
    "Sommer House / Epic": "Epic Records",
    "Sommer House/Epic": "Epic Records",
    "Sommer House/Epic Records": "Epic Records",

    "RCA": "RCA Records",
    "Cult / RCA": "RCA Records",
    "Cult Records/RCA": "RCA Records",
    "Cult Records/RCA Records": "RCA Records",
    "Cult/RCA": "RCA Records",
    "Hickman Holler/RCA Records": "RCA Records",
    "LLOUD/RCA Records": "RCA Records",
    "Lloud/RCA Records": "RCA Records",
    "Monkey Puzzle / RCA Records": "RCA Records",
    "Monkey Puzzle/RCA": "RCA Records",
    "Monkey Puzzle/RCA Records": "RCA Records",
    "RCA Victor": "RCA Records",
    
    "Syco": "Syco Music",

    # Warner / Asylum / Elektra / Sire / Parlophone
    "Warner": "Warner Records",
    "Warner Bros.": "Warner Records",
    "Warner Bros. Records": "Warner Records",
    "Warner Music": "Warner Records",
    "Warner Music Argentina": "Warner Records",
    "Warner Music Brasil": "Warner Records",
    "Warner Music Finland": "Warner Records",
    "Warner Music France": "Warner Records",
    "Warner Music Germany": "Warner Records",
    "Warner Music Group": "Warner Records",
    "Warner Music Italy": "Warner Records",
    "Warner Music Latina": "Warner Music Latina",
    "Warner Music Mexico": "Warner Records",
    "Warner Music Nashville": "Warner Records",
    "Warner Music Spain": "Warner Records",
    "WMG": "Warner Records",
    "WEA Records": "Warner Records",
    "Baby Records/Warner Music Latina": "Warner Music Latina",
    "Blue Chair Records / Warner Music Nashville": "Warner Records",
    "Blue Chair Records/Warner Music Nashville": "Warner Records",
    "Blue Chair/Warner": "Warner Records",
    "Blue Chair/Warner Music Nashville": "Warner Records",
    "CoJo Music/Warner Music Nashville": "Warner Records",
    "CoJo Records/Warner Music Nashville": "Warner Records",
    "Grupo Frontera/Warner Music Latina": "Warner Music Latina",
    "Neon16/Warner": "Warner Records",
    "Night Street / Warner Records": "Warner Records",
    "Night Street Records / Warner Records": "Warner Records",
    "Night Street Records/Warner": "Warner Records",
    "Night Street Records/Warner Records": "Warner Records",
    "Night Street/Warner Records": "Warner Records",
    "Sire/Warner Bros. Records": "Warner Records",
    "Warner Records/Island Records": "Warner Records",
    "White Star / Warner Music Latina": "White Star Music",
    "White Star Origin/Warner Music Latina": "White Star Music",
    "White Star/Warner": "White Star Music",
    "White Star/Warner Latin": "White Star Music",
    "White Star/Warner Latina": "White Star Music",
    "White Star/Warner Music Latina": "White Star Music",
    "White World Music / Warner": "White World Music",
    "White World Music / Warner Latina": "White World Music",
    "White World Music / Warner Music Latina": "White World Music",
    "White World Music/Warner": "White World Music",
    "White World Music/Warner Latina": "White World Music",
    "White World Music/Warner Music Latina": "White World Music",
    "White World/Warner": "White World Music",
    "White World/Warner Latina": "White World Music",
    "Asylum": "Asylum Records",
    "Asylum/Atlantic": "Asylum Records",
    "Asylum/Atlantic Records": "Asylum Records",
    "Elektra": "Elektra Records",
    "Sire": "Sire Records",
    "Parlophone": "Parlophone Records",

    # Universal / Republic / Interscope / Def Jam / Island / Geffen / EMI / Capitol / Polydor / Motown / Decca
    "Universal Music": "Universal Music Group",
    "Universal Music Brasil": "Universal Music Group",
    "Universal Music Chile": "Universal Music Group",
    "Universal Music Italia": "Universal Music Group",
    "Universal Music Italy": "Universal Music Group",
    "Universal Music Japan": "Universal Music Group",
    "Universal Music Latin": "Universal Music Latin",
    "Universal Music Latino": "Universal Music Latin",
    "Universal Music Mexico": "Universal Music Group",
    "Universal Music Spain": "Universal Music Group",
    "Universal Sigma": "Universal Music Group",
    "Disa / Universal Music Latino": "Universal Music Latin",
    "Disa Records/Universal Music Latin": "Universal Music Latin",
    "Disa/Universal Music Latin": "Universal Music Latin",
    "Disa/Universal Music Latino": "Universal Music Latin",
    "Eleven / Universal Music Australia": "Universal Music Group",
    "Eleven/Universal": "Universal Music Group",
    "Grupo Frontera/Universal Music Latin": "Universal Music Latin",
    "Grupo Frontera/Universal Music Latino": "Universal Music Latin",
    "Koch Universal Music": "Universal Music Group",
    "MPL/Universal Music": "Universal Music Group",
    "Music VIP/Universal Music Latin": "Universal Music Latin",
    "Neon16 / Universal Music Latino": "Universal Music Latin",
    "Neon16/Universal Music Latino": "Universal Music Latin",
    "Polydor/Universal": "Universal Music Group",
    "Sublime Recordings/Universal": "Universal Music Group",
    "Two Sides/Universal Music": "Universal Music Group",

    "Republic": "Republic Records",
    "Republic Nashville": "Republic Records",
    "Big Loud / Mercury / Republic": "Republic Records",
    "Big Loud/Mercury/Republic": "Republic Records",
    "Casablanca Records/Republic Records": "Republic Records",
    "Casablanca/Republic": "Republic Records",
    "Cash Money Records / Republic Records": "Republic Records",
    "Cash Money/Republic Records": "Republic Records",
    "Golden Child Recordings/Republic Records": "Republic Records",
    "Lava/Republic Records": "Republic Records",
    "Mercury Records / Republic Records": "Republic Records",
    "Mercury Records/Republic Records": "Republic Records",
    "Mercury/Republic": "Republic Records",
    "Mercury/Republic Records": "Republic Records",
    "OVO Sound / Republic": "OVO Sound",
    "OVO Sound / Republic Records": "OVO Sound",
    "OVO Sound/Republic": "OVO Sound",
    "OVO Sound/Republic Records": "OVO Sound",
    "OVO/Republic": "OVO Sound",
    "XO / Republic Records": "Republic Records",
    "XO/Republic": "Republic Records",
    "XO/Republic Records": "Republic Records",
    "Young Money/Cash Money/Republic": "Republic Records",
    "Young Money/Cash Money/Republic Records": "Republic Records",
    
    "Interscope": "Interscope Records",
    "Aftermath/Interscope": "Interscope Records",
    "Aftermath/Interscope Records": "Interscope Records",
    "Bichota Records / Interscope": "Interscope Records",
    "Bichota Records / Interscope Records": "Interscope Records",
    "Bichota Records/Interscope": "Interscope Records",
    "Darkroom/Interscope": "Interscope Records",
    "Darkroom/Interscope Records": "Interscope Records",
    "Dreamville/Roc Nation/Interscope": "Interscope Records",
    "MCA Nashville/Interscope": "Interscope Records",
    "Mercury/Interscope": "Interscope Records",
    "Modular/Interscope": "Interscope Records",
    "Mosley Music / Interscope Records": "Interscope Records",
    "Mosley Music/Interscope": "Interscope Records",
    "Mosley Music/Interscope Records": "Interscope Records",
    "Mosley/Interscope": "Interscope Records",
    "Mosley/Interscope Records": "Interscope Records",
    "NEON16 / Interscope": "Interscope Records",
    "NEON16/Interscope": "Interscope Records",
    "Neon16 / Interscope": "Interscope Records",
    "Neon16 / Interscope Records": "Interscope Records",
    "Neon16/Interscope": "Interscope Records",
    "Neon16/Interscope Records": "Interscope Records",
    "Shady Records/Interscope Records": "Interscope Records",
    "Shady/Aftermath/Interscope": "Interscope Records",
    "Shady/Interscope": "Interscope Records",
    "Top Dawg Entertainment/Aftermath/Interscope": "Interscope Records",
    "Top Dawg Entertainment/Interscope": "Interscope Records",
    "Top Dawg Entertainment/Interscope Records": "Interscope Records",
    "pgLang/Interscope": "Interscope Records",
    
    "Def Jam": "Def Jam Recordings",
    "ILH Mgmt / Def Jam": "Def Jam Recordings",
    "ILH Productions/Def Jam Recordings": "Def Jam Recordings",
    "ILH/Def Jam": "Def Jam Recordings",
    "Island Def Jam": "Def Jam Recordings",
    "Island/Def Jam": "Def Jam Recordings",
    "Roc La Familia / Def Jam": "Def Jam Recordings",
    "Roc La Familia/Def Jam": "Def Jam Recordings",
    "Roc-A-Fella/Def Jam": "Def Jam Recordings",
    "Roc-La-Familia/Def Jam": "Def Jam Recordings",
    "Schoolboy/Raymond Braun/Island Def Jam": "Def Jam Recordings",
    
    "Island": "Island Records",
    "Amusement / Island Records": "Island Records",
    "Amusement Records/Island Records": "Island Records",
    "Amusement/Island": "Island Records",
    "Amusement/Island Records": "Island Records",
    "Island Records / Virgin Music": "Island Records",
    "Island Records/Virgin Music": "Island Records",
    "Island/RBMG": "Island Records",
    "PMR Records/Island Records": "Island Records",
    "PMR/Island": "Island Records",
    "PMR/Island Records": "Island Records",
    "RBMG/Island Records": "Island Records",
    "Schoolboy/Raymond Braun/Island Records": "Island Records",
    
    "Geffen": "Geffen Records",
    "DGC": "Geffen Records",
    "DGC Records": "Geffen Records",
    "DGC / Geffen": "Geffen Records",
    "DGC/Geffen": "Geffen Records",
    "DGC/Geffen Records": "Geffen Records",
    "Geffen Records/HYBE": "Geffen Records",
    "HYBE x Geffen": "Geffen Records",
    
    "EMI": "EMI Records",
    "EMI Latin": "EMI Records",
    "EMI Nashville": "EMI Records",
    "EMI Records Japan": "EMI Records",
    "EMI Records Nashville": "EMI Records",
    "EMI/Hollywood Records": "EMI Records",
    "EMI/Mercury Records": "EMI Records",
    
    "Capitol": "Capitol Records",
    "Capitol CMG": "Capitol Records",
    "Capitol Nashville": "Capitol Records",
    "Capitol Records Nashville": "Capitol Records",
    "Locomotion / Capitol Records": "Capitol Records",
    "Locomotion/Capitol": "Capitol Records",
    "Locomotion/Capitol Records": "Capitol Records",
    "MPL/Capitol": "Capitol Records",
    "MPL/Capitol Records": "Capitol Records",
    "Roswell/Capitol": "Capitol Records",
    "Roswell/Capitol Records": "Capitol Records",
    
    "Polydor": "Polydor Records",
    "Motown": "Motown Records",
    "Virgin EMI": "Virgin Records",
    "Virgin Music": "Virgin Records",
    "Decca": "Decca Records",

    # Atlantic / Cactus Jack
    "Atlantic": "Atlantic Records",
    "Atlantic/Home Grown": "Atlantic Records",
    "Cactus Jack / Atlantic": "Cactus Jack Records",
    "Cactus Jack/Atlantic": "Cactus Jack Records",
    "Cactus Jack/Atlantic Records": "Cactus Jack Records",
    "Monkey Puzzle/Atlantic": "Atlantic Records",
    "Cactus Jack": "Cactus Jack Records",
    
    # BIGHIT
    "BIGHIT Music": "BIGHIT MUSIC",
    "BigHit Music": "BIGHIT MUSIC",
    "Big Hit Entertainment": "BIGHIT MUSIC",
    "Big Hit Music": "BIGHIT MUSIC",
    "Big Hit": "BIGHIT MUSIC",
    "BH Entertainment": "BIGHIT MUSIC",
    
    # Roc Nation
    "Dreamville/Roc Nation": "Roc Nation",
    "Roc Nation/VI Music": "Roc Nation",
    "Westbury Road/Roc Nation": "Roc Nation",
    
    # Rimas
    "Rimas": "Rimas Entertainment",
    
    # Rancho Humilde
    "Rancho Humilde/Street Mob Records": "Rancho Humilde",
    "Rancho Humilde / Street Mob Records": "Rancho Humilde",
    "Rancho Humilde/Sony Music Latin": "Rancho Humilde",
    "Rancho Humilde / Sony Music Latin": "Rancho Humilde",

    # White Star
    "White Star":             "White Star Music",
    "White Star Records":     "White Star Music",
    "White Star Origins":     "White Star Music",
    "White Star Origin":      "White Star Music",
    "White Star Entertainment": "White Star Music",
    "White Star Inc":         "White Star Music",
    "White Star Lane Records": "White Star Music",
    "White Star Line":        "White Star Music",

    # OVO Sound
    "OVO Sound": "OVO Sound",
}

TOP_N_LABELS = 12


# ─────────────────────── data helpers ──────────────────────────

def _normalize_label(label: str | None) -> str:
    """Apply LABEL_NORM map; return canonical or original if not found."""
    if not label:
        return "—"
    return LABEL_NORM.get(label.strip(), label.strip())


@st.cache_data(ttl=300, show_spinner=False)
def _get_data_date() -> str:
    """Fetch the min and max date from spotify_daily to show in the UI."""
    query = "SELECT MIN(scraped_at) as min_d, MAX(scraped_at) as max_d FROM spotify_daily"
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            res = cur.fetchone()
            if res and res.get("min_d") and res.get("max_d"):
                min_d = res["min_d"].strftime("%b %d, %Y")
                max_d = res["max_d"].strftime("%b %d, %Y")
                if min_d == max_d:
                    return max_d
                return f"{min_d} - {max_d}"
    except Exception:
        pass
    return "All-Time"


@st.cache_data(ttl=300, show_spinner=False)
def _load_itunes_labels(country: str) -> pd.DataFrame:
    """
    Load latest-date iTunes data grouped by label.
    Returns columns: label, entries, avg_rank, points
    """
    query = """
        SELECT
            d.label,
            COUNT(*)                       AS entries,
            AVG(d.rank)                    AS avg_rank,
            SUM(d.points)                  AS points
        FROM itunes_daily d
        WHERE d.label IS NOT NULL
          AND d.label != 'Independent'
        GROUP BY d.label
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        logger.error("label_analysis load_itunes_labels failed (%s): %s", country, e)
        return pd.DataFrame(columns=["label", "entries", "avg_rank", "points"])
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    if not rows:
        return pd.DataFrame(columns=["label", "entries", "avg_rank", "points"])
    df = pd.DataFrame(rows, columns=["label", "entries", "avg_rank", "points"])
    df["entries"]     = pd.to_numeric(df["entries"], errors="coerce").fillna(0).astype(int)
    df["avg_rank"]    = pd.to_numeric(df["avg_rank"], errors="coerce").round(1)
    df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0).astype(int)
    df["label"] = df["label"].apply(_normalize_label)
    df = df.groupby("label", as_index=False).agg(
        entries=("entries", "sum"),
        avg_rank=("avg_rank", "mean"),
        points=("points", "sum"),
    )
    df["avg_rank"] = df["avg_rank"].round(1)
    return df.sort_values("points", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def _load_spotify_labels(country: str) -> pd.DataFrame:
    """
    Load latest-date Spotify data grouped by label.
    Returns columns: label, entries, avg_rank, total_streams
    """
    query = """
        SELECT
            d.label,
            COUNT(*)                       AS entries,
            AVG(d.rank)                    AS avg_rank,
            SUM(d.streams)                 AS total_streams
        FROM spotify_daily d
        WHERE d.label IS NOT NULL
          AND d.label != 'Independent'
        GROUP BY d.label
        ORDER BY total_streams DESC
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        logger.error("label_analysis load_spotify_labels failed (%s): %s", country, e)
        return pd.DataFrame(columns=["label", "entries", "avg_rank", "total_streams"])
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    if not rows:
        return pd.DataFrame(columns=["label", "entries", "avg_rank", "total_streams"])
    df = pd.DataFrame(rows, columns=["label", "entries", "avg_rank", "total_streams"])
    df["entries"]       = pd.to_numeric(df["entries"], errors="coerce").fillna(0).astype(int)
    df["avg_rank"]      = pd.to_numeric(df["avg_rank"], errors="coerce").round(1)
    df["total_streams"] = pd.to_numeric(df["total_streams"], errors="coerce").fillna(0).astype(int)
    df["label"] = df["label"].apply(_normalize_label)
    df = df.groupby("label", as_index=False).agg(
        entries=("entries", "sum"),
        avg_rank=("avg_rank", "mean"),
        total_streams=("total_streams", "sum"),
    )
    df["avg_rank"] = df["avg_rank"].round(1)
    return df.sort_values("total_streams", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def _load_all_top_tracks_by_label() -> dict[str, list[dict[str, Any]]]:
    """Fetch top 10 tracks for all labels based on total streams from Spotify."""
    query = """
        SELECT label, artist_title, MIN(rank) AS rank, SUM(streams) AS total_streams
        FROM spotify_daily
        WHERE label IS NOT NULL
          AND label != 'Independent'
        GROUP BY label, artist_title
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            
        df = pd.DataFrame([dict(r) for r in rows])
        if df.empty:
            return {}
        df["total_streams"] = pd.to_numeric(df["total_streams"], errors="coerce").fillna(0).astype(int)
        df["label"] = df["label"].apply(_normalize_label)
        
        df = df.groupby(["label", "artist_title"], as_index=False).agg(
            rank=("rank", "min"),
            total_streams=("total_streams", "max")
        )
        df = df.sort_values(["label", "total_streams"], ascending=[True, False])
        top_10 = df.groupby("label").head(10)
        
        result = {}
        for label, group in top_10.groupby("label"):
            result[label] = group[["artist_title", "rank", "total_streams"]].to_dict(orient="records")
        return result
    except Exception as e:
        logger.error("Failed to load top tracks by label: %s", e)
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def _load_itunes_top_tracks() -> list[dict[str, Any]]:
    """Fetch top 10 iTunes tracks overall based on points."""
    query = """
        SELECT artist_title, label, MIN(rank) AS rank, SUM(points) AS points
        FROM itunes_daily
        WHERE label IS NOT NULL
          AND label != 'Independent'
        GROUP BY artist_title, label
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            
        df = pd.DataFrame([dict(r) for r in rows])
        if df.empty:
            return []
        df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0).astype(int)
        df["label"] = df["label"].apply(_normalize_label)
        
        df = df.groupby(["label", "artist_title"], as_index=False).agg(
            rank=("rank", "min"),
            points=("points", "max")
        )
        df = df.sort_values("points", ascending=False).head(10)
        return df.to_dict(orient="records")
    except Exception as e:
        logger.error("Failed to load top iTunes tracks: %s", e)
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _load_spotify_top_tracks() -> list[dict[str, Any]]:
    """Fetch top 10 Spotify tracks overall based on total streams."""
    query = """
        SELECT artist_title, label, MIN(rank) AS rank, SUM(streams) AS total_streams
        FROM spotify_daily
        WHERE label IS NOT NULL
          AND label != 'Independent'
        GROUP BY artist_title, label
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            
        df = pd.DataFrame([dict(r) for r in rows])
        if df.empty:
            return []
        df["total_streams"] = pd.to_numeric(df["total_streams"], errors="coerce").fillna(0).astype(int)
        df["label"] = df["label"].apply(_normalize_label)
        
        df = df.groupby(["label", "artist_title"], as_index=False).agg(
            rank=("rank", "min"),
            total_streams=("total_streams", "max")
        )
        df = df.sort_values("total_streams", ascending=False).head(10)
        return df.to_dict(orient="records")
    except Exception as e:
        logger.error("Failed to load top Spotify tracks: %s", e)
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _load_country_dominance() -> list[dict[str, Any]]:
    """
    For each country return the dominant label (most chart entries on Spotify).
    Queries spotify_artist_track across all countries.
    """
    query = """
        WITH ranked AS (
            SELECT
                d.country,
                d.label,
                COUNT(*) AS entries,
                AVG(d.rank) AS avg_rank,
                SUM(d.streams) AS total_streams,
                ROW_NUMBER() OVER (PARTITION BY d.country ORDER BY SUM(d.streams) DESC) AS rn
            FROM spotify_daily d
            WHERE d.label IS NOT NULL
              AND d.label != 'Independent'
            GROUP BY d.country, d.label
        )
        SELECT country, label, entries, avg_rank, total_streams
        FROM ranked
        WHERE rn = 1
        ORDER BY total_streams DESC
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        logger.error("label_analysis load_country_dominance failed: %s", e)
        return []
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    out: list[dict[str, Any]] = []
    # Clear cache by adding a comment here
    for row in rows:
        c_code = row.get("country")
        if not c_code or c_code.strip().lower() in ("global", "ww"):
            continue
        c_name = COUNTRY_FLAGS.get(c_code.strip().lower(), c_code.strip().upper())
        out.append({
            "country":       c_name,
            "label":         _normalize_label(row.get("label")),
            "entries":       int(row["entries"]) if row.get("entries") else 0,
            "avg_rank":      round(float(row["avg_rank"]), 1) if row.get("avg_rank") else 0.0,
            "total_streams": int(row["total_streams"]) if row.get("total_streams") else 0,
        })
    return out


def prefetch_label_data() -> None:
    """Prefetch default region label data to warm up the cache."""
    _load_itunes_labels("ww")
    _load_spotify_labels("global")
    _load_country_dominance()


def _build_normalization_stats(
    it_raw_df: pd.DataFrame,
    sp_raw_df: pd.DataFrame,
) -> dict[str, Any]:
    """
    Computes before/after unique label counts and top merged groups.
    it_raw_df / sp_raw_df should contain raw (un-normalized) label column.
    """
    it_before = int(it_raw_df["label"].nunique()) if not it_raw_df.empty else 0
    sp_before = int(sp_raw_df["label"].nunique()) if not sp_raw_df.empty else 0

    it_after = int(it_raw_df["label"].apply(_normalize_label).nunique()) if not it_raw_df.empty else 0
    sp_after = int(sp_raw_df["label"].apply(_normalize_label).nunique()) if not sp_raw_df.empty else 0

    return {
        "it_before": it_before,
        "it_after":  it_after,
        "it_saved":  it_before - it_after,
        "sp_before": sp_before,
        "sp_after":  sp_after,
        "sp_saved":  sp_before - sp_after,
    }


def _compute_power_scores(
    it_df: pd.DataFrame,
    sp_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Power score = 20% iTunes entries + 20% Spotify entries + 30% Spotify streams + 30% iTunes streams.
    Returns top-10 labels sorted by power score descending.
    """
    if it_df.empty and sp_df.empty:
        return []

    merged = pd.merge(
        it_df[["label", "entries", "points"]].rename(
            columns={"entries": "it_entries", "points": "it_streams"}
        ),
        sp_df[["label", "entries", "total_streams"]].rename(
            columns={"entries": "sp_entries", "total_streams": "sp_streams"}
        ),
        on="label",
        how="outer",
    ).fillna(0)

    max_it_ent = merged["it_entries"].max() or 1
    max_sp_ent = merged["sp_entries"].max() or 1
    max_it_str = merged["it_streams"].max() or 1
    max_sp_str = merged["sp_streams"].max() or 1

    merged["power"] = (
        0.20 * (merged["it_entries"] / max_it_ent) * 100
        + 0.20 * (merged["sp_entries"] / max_sp_ent) * 100
        + 0.30 * (merged["sp_streams"] / max_sp_str) * 100
        + 0.30 * (merged["it_streams"] / max_it_str) * 100
    ).round(1)

    top = merged.nlargest(10, "power").reset_index(drop=True)
    return top.to_dict(orient="records")


def _top_n_labels(df: pd.DataFrame, n: int = TOP_N_LABELS) -> list[dict[str, Any]]:
    """Return top-N labels from a normalised label DataFrame."""
    if df.empty:
        return []
    return df.head(n).to_dict(orient="records")


# ─────────────────────────── render ───────────────────────────────

def render_label_analysis() -> None:
    st.markdown(
        "<div style='font-size: 0.92rem; color: var(--t2); margin: 0 0 14px; line-height: 1.5; font-weight: 500;'>"
        "Label dominance, normalization stats, and cross-platform reach across iTunes &amp; Spotify."
        "</div>",
        unsafe_allow_html=True,
    )

    scope_label = "Global / WW"
    it_country, sp_country = "ww", "global"

    # ── Load data ─────────────────────────────────────────────────
    with st.spinner("Loading label data…"):
        it_df = _load_itunes_labels(it_country)
        sp_df = _load_spotify_labels(sp_country)
        country_dom = _load_country_dominance()
        label_top_tracks = _load_all_top_tracks_by_label()
        it_top_tracks = _load_itunes_top_tracks()
        sp_top_tracks = _load_spotify_top_tracks()
        data_date = _get_data_date()

    if it_df.empty and sp_df.empty:
        st.warning("No label data available for the selected region.")
        return

    # ── Derived metrics ───────────────────────────────────────────
    norm_stats  = _build_normalization_stats(it_df, sp_df)
    power_scores = _compute_power_scores(it_df, sp_df)

    top_label_overall = (
        power_scores[0]["label"] if power_scores else "—"
    )
    top_label_entries = int(
        (power_scores[0].get("it_entries", 0) or 0)
        + (power_scores[0].get("sp_entries", 0) or 0)
    ) if power_scores else 0

    it_top = _top_n_labels(it_df)
    sp_top = _top_n_labels(sp_df)

    # Build normalization fix groups for the Fixes log tab
    fix_groups: list[dict[str, Any]] = []
    inv: dict[str, list[str]] = {}
    for variant, canonical in LABEL_NORM.items():
        inv.setdefault(canonical, []).append(variant)
    # Merge entry counts from both platforms
    it_counts = (
        it_df.set_index("label")["entries"].to_dict() if not it_df.empty else {}
    )
    sp_counts = (
        sp_df.set_index("label")["entries"].to_dict() if not sp_df.empty else {}
    )
    for canonical, variants in inv.items():
        total = (it_counts.get(canonical, 0) or 0) + (sp_counts.get(canonical, 0) or 0)
        fix_groups.append({"canonical": canonical, "variants": variants, "count": total})
    fix_groups.sort(key=lambda x: x["count"], reverse=True)

    payload = {
        "scope":         scope_label,
        "norm_stats":    norm_stats,
        "power_scores":  power_scores,
        "it_top":        it_top,
        "sp_top":           sp_top,
        "country_dom":      country_dom,
        "label_top_tracks": label_top_tracks,
        "it_top_tracks":    it_top_tracks,
        "sp_top_tracks":    sp_top_tracks,
        "data_date":        data_date,
        "fix_groups":    fix_groups,
        "kpis": {
            "top_label":         top_label_overall,
            "top_label_entries": top_label_entries,
            "it_unique_before":  norm_stats["it_before"],
            "it_unique_after":   norm_stats["it_after"],
            "sp_unique_before":  norm_stats["sp_before"],
            "sp_unique_after":   norm_stats["sp_after"],
        },
    }

    html = _build_html(payload, dark_mode=st.session_state.get("dark_mode", True))
    st_components.html(html, height=1100, scrolling=True)


# ─────────────────────────── HTML template ───────────────────────────

def _build_html(payload: dict, dark_mode: bool = False) -> str:  # noqa: FBT001, FBT002
    data_json  = json.dumps(payload, default=str)
    theme_css  = _THEME_DARK if dark_mode else _THEME_LIGHT
    return """
<!DOCTYPE html><html><head><meta charset='utf-8'>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
__THEME__
body{background:var(--bg);font-family:'Inter',system-ui,sans-serif;color:var(--t1);font-size:16px;line-height:1.55}
.body{padding:20px 22px;display:flex;flex-direction:column;gap:20px}
/* KPI bar */
.kpi-bar{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:4px;width:100%}
.kpi{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;transition:.15s}
.kpi:hover{background:var(--bg3)}
.kpi-lbl{font-size:12px;color:var(--t3);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px;font-weight:600}
.kpi-val{font-size:32px;font-weight:700;letter-spacing:-.5px;line-height:1.15;color:var(--t1)}
.kpi-sub{font-size:13px;color:var(--t2);margin-top:5px;font-weight:500}
/* tabs */
.tab-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:18px;align-items:stretch;width:100%}
.tab{display:inline-flex;align-items:center;justify-content:center;font-size:14px;padding:10px 16px;border-radius:999px;background:var(--bg3);color:var(--t2);cursor:pointer;border:1px solid var(--border);min-width:0;transition:.15s;font-weight:500;white-space:nowrap}
.tab:hover{background:var(--bg4);border-color:var(--border2);color:var(--t1);transform:translateY(-1px)}
.tab.active{background:linear-gradient(135deg,#e31b23,#b31217);color:#ffffff;border-color:#e31b23;font-weight:700;box-shadow:0 10px 22px rgba(227,27,35,.22),inset 0 1px 0 rgba(255,255,255,.18);transform:translateY(-1px)}
/* cards */
.card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
.card-ttl{font-size:14px;color:var(--t2);text-transform:uppercase;letter-spacing:.7px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border);font-weight:600}
.card-ttl-flex{display:flex;justify-content:space-between;align-items:center}
.r2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
/* table */
.ctable{width:100%;border-collapse:collapse;font-size:14px}
.ctable th{font-size:13px;font-weight:600;color:var(--t3);text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:.5px}
.ctable td{padding:8px 10px;border-bottom:1px solid var(--border);color:var(--t1);font-size:14px}
.ctable tr:last-child td{border-bottom:none}
.ctable tr:hover td{background:var(--bg3)}
/* badge */
.badge{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:999px;min-width:42px;background:var(--bg3);color:var(--t2);border:1px solid var(--border2)}
/* bar */
.bar-wrap{margin:4px 0}
.bar-lbl{font-size:13px;color:var(--t2);display:flex;justify-content:space-between;margin-bottom:3px}
.bar-outer{background:var(--bg4);border-radius:3px;height:9px;overflow:hidden}
.bar-fill{height:9px;border-radius:3px}
/* fix groups */
.fix-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.fix-group{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px 14px}
.fix-canonical{font-size:14px;font-weight:600;color:var(--t1);margin-bottom:6px;display:flex;align-items:center;gap:8px}
.fix-variant{font-size:13px;color:var(--t3);padding:2px 0 2px 12px;display:flex;align-items:center;gap:4px}
.fix-count{font-size:12px;color:var(--t3);background:var(--bg3);padding:1px 6px;border-radius:10px;margin-left:auto;white-space:nowrap}
@media(max-width:900px){.kpi-bar{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){.kpi-bar{grid-template-columns:1fr}}
@media(max-width:900px){.tab-row{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){.tab-row{grid-template-columns:1fr}}
@media(max-width:900px){.r2, .fix-grid{grid-template-columns:1fr}}

</style></head><body>

<div class='body'>

  <!-- KPI bar -->
  <div class='kpi-bar' id='kpiBar'></div>


  <!-- Tabs -->
  <div class='tab-row'>
    <div class='tab active' onclick="showTab('overview',this)">📊 Overview</div>
    <div class='tab' onclick="showTab('itunes',this)">🎵 iTunes</div>
    <div class='tab' onclick="showTab('spotify',this)">🎧 Spotify</div>
    <div class='tab' onclick="showTab('country',this)">🌍 Country</div>
  </div>

  <!-- Overview tab -->
  <div id='tab-overview'>
    <div class='r2' style='margin-bottom:16px'>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span id='topTracksTtl'>🔥 Top 5 tracks of Epic (Spotify)</span></div>
        <div style='font-size:11px;color:var(--t3);margin-top:-8px;margin-bottom:10px'>Historical data based on total streams</div>
        <table class='ctable'>
          <thead>
            <tr>
              <th>Track</th>
              <th style='text-align:right;width:80px'>Rank</th>
              <th style='text-align:right;width:120px'>Streams</th>
            </tr>
          </thead>
          <tbody id='epicTbody'></tbody>
        </table>
      </div>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span>⚡ Power score — overall dominance</span></div>
        <div style='font-size:11px;color:var(--t3);margin-top:-8px;margin-bottom:12px'>20% iTunes entries + 20% Spotify entries + 30% Spotify streams + 30% iTunes streams</div>
        <div id='pwrBars'></div>
      </div>
    </div>
    <div class='card'>
      <div class='card-ttl card-ttl-flex'><span>🌐 Platform reach — separate volume split</span></div>
      <div class='r2'>
        <div>
          <div style='font-size:12px;font-weight:600;margin-bottom:8px;text-align:center;color:var(--t2)'>iTunes Streams</div>
          <div style='position:relative;height:200px'><canvas id='stackBarItunes'></canvas></div>
        </div>
        <div>
          <div style='font-size:12px;font-weight:600;margin-bottom:8px;text-align:center;color:var(--t2)'>Spotify Streams</div>
          <div style='position:relative;height:200px'><canvas id='stackBarSpotify'></canvas></div>
        </div>
      </div>
    </div>
  </div>

  <!-- iTunes tab -->
  <div id='tab-itunes' style='display:none'>
    <div class='r2'>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span>🍏 iTunes — points by label (top 12)</span></div>
        <div style='position:relative;height:300px'><canvas id='itBar'></canvas></div>
      </div>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span>📉 iTunes — average chart rank (lower = better)</span></div>
        <div style='position:relative;height:300px'><canvas id='itRank'></canvas></div>
      </div>
    </div>
    <div class='card' style='margin-top:16px'>
      <div class='card-ttl card-ttl-flex'><span>🏅 Top 10 iTunes Tracks by Points</span></div>
      <table class='ctable'>
        <thead>
          <tr>
            <th>Track</th>
            <th>Label</th>
            <th style='text-align:right;width:80px'>Rank</th>
            <th style='text-align:right;width:120px'>Points</th>
          </tr>
        </thead>
        <tbody id='itTopTbody'></tbody>
      </table>
    </div>
  </div>

  <!-- Spotify tab -->
  <div id='tab-spotify' style='display:none'>
    <div class='r2'>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span>🎼 Spotify — streams by label (top 12)</span></div>
        <div style='position:relative;height:300px'><canvas id='spBar'></canvas></div>
      </div>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span>📈 Spotify — average chart rank (lower = better)</span></div>
        <div style='position:relative;height:300px'><canvas id='spRank'></canvas></div>
      </div>
    </div>
    <div class='card' style='margin-top:16px'>
      <div class='card-ttl card-ttl-flex'><span>🏆 Top 10 Spotify Tracks by Streams</span></div>
      <table class='ctable'>
        <thead>
          <tr>
            <th>Track</th>
            <th>Label</th>
            <th style='text-align:right;width:80px'>Rank</th>
            <th style='text-align:right;width:120px'>Streams</th>
          </tr>
        </thead>
        <tbody id='spTopTbody'></tbody>
      </table>
    </div>
  </div>

  <!-- Country-wise tab -->
  <div id='tab-country' style='display:none'>
    <div class='r2' style='margin-bottom:16px'>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span>🧭 Dominant label by country</span></div>
        <table class='ctable'>
          <thead><tr>
            <th>Country</th><th>Top Label</th><th style='text-align:right'>Entries</th>
            <th style='text-align:right'>Avg Rank</th><th style='text-align:right'>Streams</th>
          </tr></thead>
          <tbody id='ctryTbody'></tbody>
        </table>
      </div>
      <div class='card' style='display:flex;flex-direction:column;height:100%'>
        <div class='card-ttl card-ttl-flex'><span>🗺️ Streams by country (Spotify)</span></div>
        <div style='position:relative;flex-grow:1;min-height:400px'><canvas id='ctryStream'></canvas></div>
      </div>
    </div>
  </div>

  <!-- Fixes log tab -->
  <div id='tab-fixes' style='display:none'>
    <div class='card' style='margin-bottom:16px'>
      <div class='card-ttl card-ttl-flex'><span>🧩 Sub Labels Mapping</span></div>
      <div class='fix-grid' id='fixGrid'></div>
    </div>

  </div>

</div>

<script src='https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js'></script>
<script>
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
const PAYLOAD = __DATA__;
const K = PAYLOAD.kpis;
const isDark = document.documentElement.style.getPropertyValue('--bg') !== '';
const tc = getComputedStyle(document.documentElement).getPropertyValue('--t3').trim() || '#8b95ad';
const gc = getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || 'rgba(148,163,184,.15)';

// ── helpers ──────────────────────────────────────────────────
function fmtN(n){if(n===null||n===undefined)return'—';n=+n;const a=Math.abs(n);if(a>=1e9)return(a/1e9).toFixed(1)+'B';if(a>=1e6)return(a/1e6).toFixed(1)+'M';if(a>=1e3)return(a/1e3).toFixed(0)+'K';return a.toFixed(0);}
function showTab(id,el){
  ['overview','itunes','spotify','country','fixes'].forEach(t=>{
    document.getElementById('tab-'+t).style.display='none';
  });
  document.getElementById('tab-'+id).style.display='block';
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
}

// ── KPI bar ──────────────────────────────────────────────────
const kpiData = [
  {lbl:'🏆 Top label overall',   val:K.top_label, sub:'Based on latest daily chart'},
  {lbl:'🍏 iTunes labels', val:K.it_unique_after},
  {lbl:'🎧 Spotify labels',val:K.sp_unique_after},
];
const kpiBar = document.getElementById('kpiBar');
kpiData.forEach(k=>{
  kpiBar.innerHTML += `<div class='kpi'>
    <div class='kpi-lbl'>${k.lbl}</div>
    <div class='kpi-val'>${k.val}</div>
    ${k.sub ? `<div class='kpi-sub'>${k.sub}</div>` : ''}
  </div>`;
});


// ── Power score bars ─────────────────────────────────────────
const pwrBars = document.getElementById('pwrBars');
(PAYLOAD.power_scores||[]).forEach(p=>{
  const pct = Math.min(100, Math.max(0, p.power));
  pwrBars.innerHTML += `<div class='bar-wrap' style='cursor:pointer;padding:4px;border-radius:4px;transition:background 0.2s' onmouseover="this.style.background='var(--bg4)'" onmouseout="this.style.background='transparent'" onclick="showLabelTracks('${p.label.replace(/'/g,"\\'")}')">
    <div class='bar-lbl'><span>${p.label}</span><span style='color:var(--blue);font-weight:600'>${p.power.toFixed(1)}</span></div>
    <div class='bar-outer'><div class='bar-fill' style='width:${pct}%;background:linear-gradient(90deg,var(--blue),var(--purple))'></div></div>
  </div>`;
});

// ── Overview charts ───────────────────────────────────────────
const itTop  = PAYLOAD.it_top  || [];
const spTop  = PAYLOAD.sp_top  || [];


const epicTbody = document.getElementById('epicTbody');
const topTracksTtl = document.getElementById('topTracksTtl');

function showLabelTracks(label) {
  topTracksTtl.innerText = '🔥 Top 10 tracks of ' + label + ' (Spotify)';
  const tracks = PAYLOAD.label_top_tracks[label] || [];
  epicTbody.innerHTML = '';
  if(tracks.length === 0) {
    epicTbody.innerHTML = `<tr><td colspan='3' style='text-align:center;color:var(--t3)'>No data available</td></tr>`;
    return;
  }
  tracks.forEach(d=>{
    epicTbody.innerHTML += `<tr>
      <td style='font-weight:600'>${d.artist_title}</td>
      <td style='text-align:right'>${d.rank}</td>
      <td style='text-align:right'>${fmtN(d.total_streams)}</td>
    </tr>`;
  });
}

// Initial render
const defaultLabel = PAYLOAD.power_scores && PAYLOAD.power_scores.length > 0 ? PAYLOAD.power_scores[0].label : 'Epic';
showLabelTracks(defaultLabel);

new Chart(document.getElementById('stackBarItunes'),{
  type:'bar',
  data:{labels:itTop.map(d=>d.label),datasets:[
    {label:'iTunes',  data:itTop.map(d=>d.points), backgroundColor:'#e31b23',borderRadius:0}
  ]},
  options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{x:{ticks:{color:tc,font:{size:12},maxRotation:45},grid:{color:gc}},
            y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}}}}
});
new Chart(document.getElementById('stackBarSpotify'),{
  type:'bar',
  data:{labels:spTop.map(d=>d.label),datasets:[
    {label:'Spotify', data:spTop.map(d=>d.total_streams), backgroundColor:'#b31217',borderRadius:0}
  ]},
  options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{x:{ticks:{color:tc,font:{size:12},maxRotation:45},grid:{color:gc}},
            y:{ticks:{color:tc,font:{size:12},callback:v=>fmtN(v)},grid:{color:gc}}}}
});

// ── iTunes tab charts ─────────────────────────────────────────
new Chart(document.getElementById('itBar'),{
  type:'bar',
  data:{labels:itTop.map(d=>d.label),
    datasets:[{label:'Points',data:itTop.map(d=>d.points),backgroundColor:'#e31b23',borderRadius:3}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}},
            x:{ticks:{color:tc,font:{size:12}},grid:{color:gc}}}}
});

new Chart(document.getElementById('itRank'),{
  type:'bar',
  data:{labels:itTop.map(d=>d.label),
    datasets:[{label:'Avg Rank',data:itTop.map(d=>d.avg_rank),backgroundColor:'#8f0f1c',borderRadius:3}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`Avg rank: ${c.parsed.x}`}}},
    scales:{y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}},
            x:{reverse:false,ticks:{color:tc,font:{size:12}},grid:{color:gc}}}}
});

const itTopTbody = document.getElementById('itTopTbody');
if (itTopTbody) {
  (PAYLOAD.it_top_tracks || []).forEach(d => {
    itTopTbody.innerHTML += `<tr>
      <td style='font-weight:600'>${d.artist_title}</td>
      <td><span class='badge' style='background:var(--bg3);border:1px solid var(--border)'>${d.label}</span></td>
      <td style='text-align:right'>${d.rank}</td>
      <td style='text-align:right'>${fmtN(d.points)}</td>
    </tr>`;
  });
}

// ── Spotify tab charts ────────────────────────────────────────
new Chart(document.getElementById('spBar'),{
  type:'bar',
  data:{labels:spTop.map(d=>d.label),
    datasets:[{label:'Streams',data:spTop.map(d=>d.total_streams),backgroundColor:'#b31217',borderRadius:3}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}},
            x:{ticks:{color:tc,font:{size:12}},grid:{color:gc}}}}
});

new Chart(document.getElementById('spRank'),{
  type:'bar',
  data:{labels:spTop.map(d=>d.label),
    datasets:[{label:'Avg Rank',data:spTop.map(d=>d.avg_rank),backgroundColor:'#ff8f99',borderRadius:3}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`Avg rank: ${c.parsed.x}`}}},
    scales:{y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}},
            x:{ticks:{color:tc,font:{size:12}},grid:{color:gc}}}}
});

const spTopTbody = document.getElementById('spTopTbody');
if (spTopTbody) {
  (PAYLOAD.sp_top_tracks || []).forEach(d => {
    spTopTbody.innerHTML += `<tr>
      <td style='font-weight:600'>${d.artist_title}</td>
      <td><span class='badge' style='background:var(--bg3);border:1px solid var(--border)'>${d.label}</span></td>
      <td style='text-align:right'>${d.rank}</td>
      <td style='text-align:right'>${fmtN(d.total_streams)}</td>
    </tr>`;
  });
}



// ── Country-wise tab ─────────────────────────────────────────
const ctryData = PAYLOAD.country_dom || [];
const ctb = document.getElementById('ctryTbody');
ctryData.forEach(d=>{
  ctb.innerHTML += `<tr>
    <td style='font-weight:600'>${d.country}</td>
    <td><span class='badge' style='background:var(--bd);color:var(--blue)'>${d.label}</span></td>
    <td style='text-align:right'>${d.total_streams.toLocaleString()} streams</td>
    <td style='text-align:right'>${d.avg_rank}</td>
    <td style='text-align:right'>${fmtN(d.total_streams)}</td>
  </tr>`;
});

const streamTop = [...ctryData].sort((a,b)=>b.total_streams-a.total_streams);

new Chart(document.getElementById('ctryStream'),{
  type:'bar',
  data:{labels:streamTop.map(d=>d.country),
    datasets:[{label:'Streams',data:streamTop.map(d=>d.total_streams),backgroundColor:'#b31217',borderRadius:3}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>fmtN(c.parsed.x)+' streams'}}},
    scales:{y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}},
            x:{ticks:{color:tc,font:{size:12},callback:v=>fmtN(v)},grid:{color:gc}}}}
});

// ── Fixes log tab ─────────────────────────────────────────────
const fg = document.getElementById('fixGrid');
(PAYLOAD.fix_groups||[]).forEach(g=>{
  fg.innerHTML += `<div class='fix-group'>
    <div class='fix-canonical'>
      <span class='badge' style='background:var(--bd);color:var(--blue)'>${g.canonical}</span>
      <span class='fix-count'>${(g.count||0).toLocaleString()} total entries</span>
    </div>
    ${(g.variants||[]).map(v=>`<div class='fix-variant'><span style='color:var(--t4);font-size:10px'>↩</span><span>${v}</span></div>`).join('')}
  </div>`;
});


</script>
</body></html>
""".replace("__DATA__", data_json).replace("__THEME__", theme_css)
