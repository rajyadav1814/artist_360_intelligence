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
_THEME_LIGHT = ":root{--bg:#F5F6FA;--bg2:#FFFFFF;--bg3:#F8F9FB;--bg4:#EEF1F7;--border:rgba(148,163,184,.2);--border2:rgba(148,163,184,.35);--t1:#1A1A1A;--t2:#4A5568;--t3:#8A8FA3;--t4:#A0AEC0;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"
_THEME_DARK  = ":root{--bg:#0d1117;--bg2:#161b26;--bg3:#1f2633;--bg4:#283041;--border:rgba(148,163,184,.15);--border2:rgba(148,163,184,.28);--t1:#ffffff;--t2:#cdd6e4;--t3:#8b95ad;--t4:#6b7a99;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"

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
    "global": "🌐 Global", "ww": "🌐 Global", "us": "🇺🇸 United States",
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
    # BIGHIT
    "Big Hit Entertainment":  "BIGHIT MUSIC",
    "Big Hit Music":          "BIGHIT MUSIC",
    "BigHit Music":           "BIGHIT MUSIC",
    "BIGHIT Music":           "BIGHIT MUSIC",
    "Big Hit":                "BIGHIT MUSIC",
    "BH Entertainment":       "BIGHIT MUSIC",
    # Epic
    "Epic":                   "Epic Records",
    # Warner
    "Warner":                 "Warner Records",
    "Warner Bros.":           "Warner Records",
    "Warner Bros. Records":   "Warner Records",
    "Warner Music":           "Warner Records",
    "WMG":                    "Warner Records",
    "WEA Records":            "Warner Records",
    # Columbia
    "Columbia":               "Columbia Records",
    "Columbia Music Entertainment": "Columbia Records",
    "Columbia/Sony Music":    "Columbia Records",
    # Atlantic
    "Atlantic":               "Atlantic Records",
    "Atlantic/Home Grown":    "Atlantic Records",
    # Republic
    "Republic":               "Republic Records",
    # Island
    "Island":                 "Island Records",
    "Island Def Jam":         "Island Records",
    "Island/Def Jam":         "Island Records",
    # Sony Music Latin
    "Premium Latin Music":         "Sony Music Latin",
    "Premium Latin":               "Sony Music Latin",
    "Premium Latin Music/Sony Music Latin": "Sony Music Latin",
    # Rancho Humilde
    "Rancho Humilde/Sony Music Latin":         "Rancho Humilde",
    "Rancho Humilde / Sony Music Latin":       "Rancho Humilde",
    "Rancho Humilde/Street Mob Records":       "Rancho Humilde",
    "Rancho Humilde / Street Mob Records":     "Rancho Humilde",
    # White Star Music
    "White Star":             "White Star Music",
    "White Star Records":     "White Star Music",
    "White Star Origins":     "White Star Music",
    "White Star Origin":      "White Star Music",
    "White Star Entertainment": "White Star Music",
    "White Star Inc":         "White Star Music",
    "White Star Lane Records": "White Star Music",
    "White Star Line":        "White Star Music",
    "White Star/Warner":      "White Star Music",
    "White Star/Warner Latina": "White Star Music",
    "White Star/Warner Music Latina": "White Star Music",
    # Interscope
    "Interscope":             "Interscope Records",
    # Def Jam
    "Def Jam":                "Def Jam Recordings",
    # Geffen
    "Geffen":                 "Geffen Records",
    "DGC":                    "Geffen Records",
    "DGC Records":            "Geffen Records",
    "DGC/Geffen":             "Geffen Records",
    "DGC/Geffen Records":     "Geffen Records",
    # Rimas
    "Rimas":                  "Rimas Entertainment",
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
    query = "SELECT MIN(date) as min_d, MAX(date) as max_d FROM spotify_daily WHERE label != 'Independent'"
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
        if c_code:
            c_name = COUNTRY_FLAGS.get(c_code.strip().lower(), c_code.strip().upper())
        else:
            c_name = "—"
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
        "<div style='font-size:0.85rem;color:#97a3c5;margin:-0.5rem 0 0.75rem 0'>"
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
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
__THEME__
body{background:var(--bg);font-family:'Outfit',system-ui,sans-serif;color:var(--t1);font-size:16px;line-height:1.55}
.body{padding:20px 22px;display:flex;flex-direction:column;gap:20px}
/* KPI bar */
.kpi-bar{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:4px}
.kpi{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;transition:.15s}
.kpi:hover{background:var(--bg3)}
.kpi-lbl{font-size:12px;color:var(--t3);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px;font-weight:600}
.kpi-val{font-size:32px;font-weight:700;letter-spacing:-.5px;line-height:1.15;color:var(--t1)}
.kpi-sub{font-size:13px;color:var(--t2);margin-top:5px;font-weight:500}
/* tabs */
.tab-row{display:flex;gap:0;border-bottom:1.5px solid var(--border2);margin-bottom:18px}
.tab{font-size:14px;font-weight:600;padding:7px 14px;color:var(--t2);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1.5px;letter-spacing:.2px;transition:.1s}
.tab.active{color:var(--t1);border-bottom:2px solid var(--blue)}
/* cards */
.card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
.card-ttl{font-size:14px;color:var(--t2);text-transform:uppercase;letter-spacing:.7px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border);font-weight:600}
.card-ttl-flex{display:flex;justify-content:space-between;align-items:center}
.time-chip{background:var(--bg3);color:var(--t2);font-size:11px;padding:3px 8px;border-radius:12px;font-weight:500;text-transform:none;letter-spacing:0;border:1px solid var(--border)}
.r2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
/* table */
.ctable{width:100%;border-collapse:collapse;font-size:14px}
.ctable th{font-size:13px;font-weight:600;color:var(--t3);text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:.5px}
.ctable td{padding:8px 10px;border-bottom:1px solid var(--border);color:var(--t1);font-size:14px}
.ctable tr:last-child td{border-bottom:none}
.ctable tr:hover td{background:var(--bg3)}
/* badge */
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600}
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

</style></head><body>

<div class='body'>

  <!-- KPI bar -->
  <div class='kpi-bar' id='kpiBar'></div>


  <!-- Tabs -->
  <div class='tab-row'>
    <div class='tab active' onclick="showTab('overview',this)">Overview</div>
    <div class='tab' onclick="showTab('itunes',this)">iTunes</div>
    <div class='tab' onclick="showTab('spotify',this)">Spotify</div>
    <div class='tab' onclick="showTab('country',this)">Country-wise</div>
  </div>

  <!-- Overview tab -->
  <div id='tab-overview'>
    <div class='r2' style='margin-bottom:16px'>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span id='topTracksTtl'>Top 5 tracks of Epic (Spotify)</span><span class='time-chip'>__DATA_DATE__</span></div>
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
        <div class='card-ttl card-ttl-flex'><span>Power score — overall dominance</span><span class='time-chip'>__DATA_DATE__</span></div>
        <div style='font-size:11px;color:var(--t3);margin-top:-8px;margin-bottom:12px'>20% iTunes entries + 20% Spotify entries + 30% Spotify streams + 30% iTunes streams</div>
        <div id='pwrBars'></div>
      </div>
    </div>
    <div class='card'>
      <div class='card-ttl card-ttl-flex'><span>Platform reach — separate volume split</span><span class='time-chip'>__DATA_DATE__</span></div>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:20px'>
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
        <div class='card-ttl card-ttl-flex'><span>iTunes — points by label (top 12)</span><span class='time-chip'>__DATA_DATE__</span></div>
        <div style='position:relative;height:300px'><canvas id='itBar'></canvas></div>
      </div>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span>iTunes — average chart rank (lower = better)</span><span class='time-chip'>__DATA_DATE__</span></div>
        <div style='position:relative;height:300px'><canvas id='itRank'></canvas></div>
      </div>
    </div>
    <div class='card' style='margin-top:16px'>
      <div class='card-ttl card-ttl-flex'><span>Top 10 iTunes Tracks by Points</span><span class='time-chip'>__DATA_DATE__</span></div>
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
        <div class='card-ttl card-ttl-flex'><span>Spotify — streams by label (top 12)</span><span class='time-chip'>__DATA_DATE__</span></div>
        <div style='position:relative;height:300px'><canvas id='spBar'></canvas></div>
      </div>
      <div class='card'>
        <div class='card-ttl card-ttl-flex'><span>Spotify — average chart rank (lower = better)</span><span class='time-chip'>__DATA_DATE__</span></div>
        <div style='position:relative;height:300px'><canvas id='spRank'></canvas></div>
      </div>
    </div>
    <div class='card' style='margin-top:16px'>
      <div class='card-ttl card-ttl-flex'><span>Top 10 Spotify Tracks by Streams</span><span class='time-chip'>__DATA_DATE__</span></div>
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
        <div class='card-ttl card-ttl-flex'><span>Dominant label by country</span><span class='time-chip'>__DATA_DATE__</span></div>
        <table class='ctable'>
          <thead><tr>
            <th>Country</th><th>Top Label</th><th style='text-align:right'>Entries</th>
            <th style='text-align:right'>Avg Rank</th><th style='text-align:right'>Streams</th>
          </tr></thead>
          <tbody id='ctryTbody'></tbody>
        </table>
      </div>
      <div class='card' style='display:flex;flex-direction:column;height:100%'>
        <div class='card-ttl card-ttl-flex'><span>Streams by country (Spotify)</span><span class='time-chip'>__DATA_DATE__</span></div>
        <div style='position:relative;flex-grow:1;min-height:400px'><canvas id='ctryStream'></canvas></div>
      </div>
    </div>
  </div>

  <!-- Fixes log tab -->
  <div id='tab-fixes' style='display:none'>
    <div class='card' style='margin-bottom:16px'>
      <div class='card-ttl card-ttl-flex'><span>Sub Labels Mapping</span><span class='time-chip'>__DATA_DATE__</span></div>
      <div class='fix-grid' id='fixGrid'></div>
    </div>

  </div>

</div>

<script src='https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js'></script>
<script>
Chart.defaults.font.family = "'Outfit', system-ui, sans-serif";
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
  {lbl:'Top label overall',   val:K.top_label, sub:'Based on latest daily chart'},
  {lbl:'iTunes labels', val:K.it_unique_before, sub:'Based on latest daily chart'},
  {lbl:'Spotify labels',val:K.sp_unique_before, sub:'Based on latest daily chart'},
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
  topTracksTtl.innerText = 'Top 10 tracks of ' + label + ' (Spotify)';
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
    {label:'iTunes',  data:itTop.map(d=>d.points), backgroundColor:'#60a5fa',borderRadius:0}
  ]},
  options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{x:{ticks:{color:tc,font:{size:12},maxRotation:45},grid:{color:gc}},
            y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}}}}
});
new Chart(document.getElementById('stackBarSpotify'),{
  type:'bar',
  data:{labels:spTop.map(d=>d.label),datasets:[
    {label:'Spotify', data:spTop.map(d=>d.total_streams), backgroundColor:'#34d399',borderRadius:0}
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
    datasets:[{label:'Points',data:itTop.map(d=>d.points),backgroundColor:'#60a5fa',borderRadius:3}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}},
            x:{ticks:{color:tc,font:{size:12}},grid:{color:gc}}}}
});

new Chart(document.getElementById('itRank'),{
  type:'bar',
  data:{labels:itTop.map(d=>d.label),
    datasets:[{label:'Avg Rank',data:itTop.map(d=>d.avg_rank),backgroundColor:'#c4b5fd',borderRadius:3}]},
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
    datasets:[{label:'Streams',data:spTop.map(d=>d.total_streams),backgroundColor:'#34d399',borderRadius:3}]},
  options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{y:{ticks:{color:tc,font:{size:12}},grid:{color:gc}},
            x:{ticks:{color:tc,font:{size:12}},grid:{color:gc}}}}
});

new Chart(document.getElementById('spRank'),{
  type:'bar',
  data:{labels:spTop.map(d=>d.label),
    datasets:[{label:'Avg Rank',data:spTop.map(d=>d.avg_rank),backgroundColor:'#f9a8d4',borderRadius:3}]},
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
    datasets:[{label:'Streams',data:streamTop.map(d=>d.total_streams),backgroundColor:'#34d399',borderRadius:3}]},
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
""".replace("__DATA__", data_json).replace("__THEME__", theme_css).replace("__DATA_DATE__", payload.get("data_date", "All-Time"))