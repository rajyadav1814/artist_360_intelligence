"""
Track Acquisition dashboard — track-level acquisition signals from
Spotify Global + iTunes WW daily chart data.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src.database.connection import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_DAYS = 13

# ─────────────────────── theme CSS ──────────────────────────────
_THEME_LIGHT = ":root{--bg:#F5F6FA;--bg2:#FFFFFF;--bg3:#F8F9FB;--bg4:#EEF1F7;--border:rgba(148,163,184,.2);--border2:rgba(148,163,184,.35);--t1:#1A1A1A;--t2:#4A5568;--t3:#8A8FA3;--t4:#A0AEC0;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"
_THEME_DARK  = ":root{--bg:#0d1117;--bg2:#161b27;--bg3:#1a2035;--bg4:#1e2740;--border:rgba(41,52,85,.7);--border2:rgba(58,70,97,.8);--t1:#e2e8f0;--t2:#94a3b8;--t3:#8b95ad;--t4:#6b7a99;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"



def _split_at(at: str | None) -> tuple[str, str]:
    if not at:
        return "—", "—"
    if " - " in at:
        artist, title = at.split(" - ", 1)
    else:
        artist, title = at, at
    return artist.strip(), title.strip()


def _run_query(query: str, params: tuple) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.error("track acquisition query failed: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


@st.cache_data(ttl=299, show_spinner=False)
def _load_window(table: str, country: str, days: int) -> pd.DataFrame:
    metric_col = "streams" if table == "spotify_daily" else "points"
    query = f"""
        WITH bounds AS (
            SELECT MAX(date) AS max_d FROM {table} WHERE country = %s
        )
        SELECT
            d.date,
            d.rank,
            d.artist_title,
            d.{metric_col} AS metric,
            d.label
        FROM {table} d, bounds b
        WHERE d.country = %s
          AND d.date >  (b.max_d - %s::int)
          AND d.date <= b.max_d
    """
    rows = _run_query(query, (country, country, days))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    df["metric"] = pd.to_numeric(df["metric"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


@st.cache_data(ttl=299, show_spinner=False)
def _load_window_multi(table: str, countries: list[str], days: int) -> pd.DataFrame:
    metric_col = "streams" if table == "spotify_daily" else "points"
    placeholders = ", ".join(["%s"] * len(countries))
    query = f"""
        WITH bounds AS (
            SELECT country, MAX(date) AS max_d FROM {table} WHERE country IN ({placeholders}) GROUP BY country
        )
        SELECT
            d.country,
            d.date,
            d.rank,
            d.artist_title,
            d.{metric_col} AS metric,
            d.label
        FROM {table} d
        JOIN bounds b ON d.country = b.country
        WHERE d.date >  (b.max_d - %s::int)
          AND d.date <= b.max_d
    """
    params = tuple(countries) + (days,)
    rows = _run_query(query, params)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    df["metric"] = pd.to_numeric(df["metric"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


@st.cache_data(ttl=299, show_spinner=False)
def get_processed_track_rows(sp_df: pd.DataFrame, it_df: pd.DataFrame, dates: list[date], region: str = "Global") -> list[dict[str, Any]]:
    """
    Cached wrapper for building track rows.
    Processing can take seconds if there are many tracks; caching results makes the dashboard instant on reload.
    """
    return _build_track_rows(sp_df, it_df, dates, region=region)


@st.cache_data(ttl=299, show_spinner=False)
def get_all_region_track_rows(
    sp_all_df: pd.DataFrame,
    it_global_df: pd.DataFrame,
    it_ww_df: pd.DataFrame,
    dates: list[date],
    latam_codes: tuple[str, ...],
    limit: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    """Build track rows for every region (global, US, all LATAM countries) in a
    single cached call instead of one `get_processed_track_rows` call per
    country.

    Previously this dashboard called the cached per-region builder once for
    "global", once for "us", and once for *each* of the 18 LATAM country
    codes — 20 separate `st.cache_data` lookups, each of which has to hash
    its own (sliced) DataFrame argument before it can even check the cache.
    That hashing cost is paid on every rerun regardless of cache hits.

    Splitting `sp_all_df` by country with a single `groupby` up front (instead
    of re-filtering the full DataFrame with a boolean mask 18 times) and
    wrapping the whole batch in one cache entry collapses ~20 hash + lookup
    round trips into 1.
    """
    results: dict[str, list[dict[str, Any]]] = {}

    results["global"] = _build_track_rows(sp_all_df, it_global_df, dates, region="Global")[:limit]

    if sp_all_df.empty:
        sp_by_country: dict[str, pd.DataFrame] = {}
    else:
        sp_by_country = {code: grp for code, grp in sp_all_df.groupby("country", sort=False)}

    sp_us = sp_by_country.get("us", pd.DataFrame())
    results["us"] = _build_track_rows(sp_us, it_ww_df, dates, region="US")[:limit]

    for code in latam_codes:
        sp_code = sp_by_country.get(code, pd.DataFrame())
        results[code] = _build_track_rows(sp_code, it_ww_df, dates, region=code.upper())[:limit]

    return results


def _fmt_n(n: float | int | None) -> str:
    if n is None or n == 0:
        return "—"
    a = abs(n)
    if a >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if a >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(int(n))


def _signal_style(acq_score: int, momentum: float, best_rank: int | None) -> tuple[str, str, str]:
    if acq_score >= 70 and momentum >= 5:
        return "BUY", "sig-buy", "#22c55e"
    if acq_score >= 55 and momentum >= 0:
        return "WATCH", "sig-watch", "#60a5fa"
    if acq_score >= 40:
        return "HOLD", "sig-hold", "#fbbf24"
    return "PASS", "sig-pass", "#fb7185"


def _acq_score(latest_streams: int, best_rank: int | None, momentum: float, best_it_rank: int | None) -> int:
    rank_score = max(0, 20 - (best_rank or 100) * 0.2) if best_rank else 0
    stream_score = min(30, int(latest_streams / 300_000))
    momentum_score = max(-20, min(40, int(momentum * 2)))
    itunes_bonus = 10 if best_it_rank and best_it_rank <= 25 else 5 if best_it_rank and best_it_rank <= 60 else 0
    return max(0, min(100, int(rank_score + stream_score + momentum_score + itunes_bonus)))


def _build_track_rows(sp_df: pd.DataFrame, it_df: pd.DataFrame, dates: list[date], region: str = "Global") -> list[dict[str, Any]]:
    # ── Pivot-based data prep for massive speed gains over row-by-row iteration ──
    # Spotify
    sp_streams_p = sp_df.pivot_table(index='artist_title', columns='date', values='metric', aggfunc='sum').reindex(columns=dates, fill_value=0) if not sp_df.empty else pd.DataFrame(index=[], columns=dates)
    sp_ranks_p = sp_df.pivot_table(index='artist_title', columns='date', values='rank', aggfunc='min').reindex(columns=dates) if not sp_df.empty else pd.DataFrame(index=[], columns=dates)
    # Get most frequent label per track
    labels_map = sp_df.groupby('artist_title')['label'].apply(lambda x: str(x.mode().iat[0]) if not x.dropna().empty else "Independent").to_dict() if (not sp_df.empty and "label" in sp_df.columns) else {}
    
    # iTunes
    it_scores_p = it_df.pivot_table(index='artist_title', columns='date', values='metric', aggfunc='sum').reindex(columns=dates, fill_value=0) if not it_df.empty else pd.DataFrame(index=[], columns=dates)
    it_ranks_p = it_df.pivot_table(index='artist_title', columns='date', values='rank', aggfunc='min').reindex(columns=dates) if not it_df.empty else pd.DataFrame(index=[], columns=dates)

    tracks: list[dict[str, Any]] = []
    all_track_titles = sorted(set(sp_streams_p.index) | set(it_scores_p.index))
    
    for track in all_track_titles:
        if not track: continue
        
        artist, title = _split_at(track)
        label = labels_map.get(track, "Independent")

        sp_streams = sp_streams_p.loc[track].tolist() if track in sp_streams_p.index else [0] * len(dates)
        sp_ranks = [int(v) if pd.notna(v) else None for v in sp_ranks_p.loc[track]] if track in sp_ranks_p.index else [None] * len(dates)
        it_scores = it_scores_p.loc[track].tolist() if track in it_scores_p.index else [0] * len(dates)
        it_ranks = [int(v) if pd.notna(v) else None for v in it_ranks_p.loc[track]] if track in it_ranks_p.index else [None] * len(dates)

        has_sp = any(v > 0 for v in sp_streams)
        has_it = any(v > 0 for v in it_scores)
        if not has_sp and not has_it:
            continue

        first_sp = next((v for v in sp_streams if v > 0), 0)
        latest_sp = next((v for v in reversed(sp_streams) if v > 0), 0)
        first_rank = next((r for r in sp_ranks if r is not None), None)
        latest_rank = next((r for r in reversed(sp_ranks) if r is not None), None)
        best_sp_rank = min([r for r in sp_ranks if r is not None], default=None)
        best_it_rank = min([r for r in it_ranks if r is not None], default=None)

        growth = round((latest_sp - first_sp) / first_sp * 100, 1) if first_sp else 0.0
        rank_delta = (first_rank - latest_rank) if first_rank is not None and latest_rank is not None else 0
        momentum = round(rank_delta * 0.24 + growth * 0.35, 1)

        platform = "cross" if has_sp and has_it else ("spotify" if has_sp else "itunes")
        acq_score = _acq_score(latest_sp, best_sp_rank, momentum, best_it_rank)
        signal, signal_class, color = _signal_style(acq_score, momentum, best_sp_rank)

        total_streams = sum(sp_streams)

        region_title = "Global" if region == "Global" else "US"
        if best_sp_rank is not None and best_sp_rank <= 20:
            rank_signal = f"Top {best_sp_rank} Spotify {region_title}"
        elif best_sp_rank is not None:
            rank_signal = f"Spotify {region_title} Top {best_sp_rank}"
        else:
            rank_signal = f"Spotify {region_title} chart watch"

        signals: list[dict[str, str]] = []
        if growth >= 25:
            signals.append({"icon": "🚀", "t": f"+{growth:.1f}% stream growth", "d": "Strong volume acceleration across the tracked window."})
        elif growth >= 0:
            signals.append({"icon": "📈", "t": f"{growth:.1f}% stream growth", "d": "Healthy audience momentum over the recent chart window."})
        else:
            signals.append({"icon": "📉", "t": f"{growth:.1f}% stream decline", "d": "Streams are cooling; monitor for stabilization."})

        if platform == "cross":
            signals.append({"icon": "🌍", "t": "Cross-platform signal", "d": f"Appearing on both Spotify {region_title} and iTunes WW charts."})
        elif platform == "spotify":
            signals.append({"icon": "🎧", "t": f"Spotify-{region_title} native momentum", "d": f"Strong Spotify {region_title} traction even without iTunes chart entry."})
        else:
            signals.append({"icon": "🍎", "t": "iTunes WW curve", "d": "iTunes-only chart signal; could still breakout to Spotify."})

        if label and "independ" in label.lower():
            signals.append({"icon": "💡", "t": "Independent / unsigned", "d": "Clean acquisition candidate with limited major-label competition."})
        else:
            signals.append({"icon": "🏷️", "t": f"Label: {label}", "d": "Track-level signal from a managed catalogue or label roster."})

        if best_sp_rank is not None and best_sp_rank <= 10:
            signals.append({"icon": "🏆", "t": rank_signal, "d": f"Elite placement on Spotify {region_title} charts."})
        elif best_it_rank is not None and best_it_rank <= 20:
            signals.append({"icon": "📊", "t": f"iTunes #{best_it_rank}", "d": "Strong iTunes WW validation for the track."})
        elif has_it:
            signals.append({"icon": "🔁", "t": "iTunes momentum present", "d": "Track is charting on iTunes WW and may cross into Spotify."})

        signals = signals[:5]

        tracks.append({
            "id": len(tracks) + 1,
            "title": title,
            "artist": artist,
            "label": label,
            "genre": "—",
            "platform": platform,
            "spStreams": sp_streams,
            "spRanks": sp_ranks,
            "itScores": it_scores,
            "itRanks": it_ranks,
            "bestRank": best_sp_rank or best_it_rank,
            "bestSpRank": best_sp_rank,
            "bestItRank": best_it_rank,
            "hasSp": has_sp,
            "hasIt": has_it,
            "latestStreams": latest_sp,
            "firstStreams": first_sp,
            "momentum": momentum,
            "growth": round(growth, 1),
            "acqScore": acq_score,
            "signal": signal,
            "days": len(dates),
            "totalStreams": total_streams,
            "acqColor": color,
            "signals": signals,
        })

    tracks.sort(key=lambda row: row["acqScore"], reverse=True)
    return tracks


def _build_payload(tracks: list[dict[str, Any]], dates: list[date], limit: int = 100, region_label: str = "Spotify Global") -> dict[str, Any]:
    if not tracks:
        return {}

    strong_buy = sum(1 for t in tracks if t["signal"] == "BUY")
    cross_count = sum(1 for t in tracks if t["platform"] == "cross")
    top_track = tracks[0]

    # Calculate Spotify stream growth to find the fastest rising track from the top 100 tracks
    fastest_track = None
    max_sp_growth = -999999.0

    for t in tracks[:limit]:
        # Spotify growth
        sp = t["spStreams"]
        first_sp = next((v for v in sp if v > 0), 0)
        latest_sp = next((v for v in reversed(sp) if v > 0), 0)
        sp_growth = ((latest_sp - first_sp) / first_sp * 100) if first_sp else 0.0

        if sp_growth > max_sp_growth:
            max_sp_growth = sp_growth
            fastest_track = t

    if fastest_track:
        fastest_name = f"{fastest_track['artist']} — {fastest_track['title']}"
        fastest_sub = f"{max_sp_growth:+.1f}% stream growth"
    else:
        fastest_name = "—"
        fastest_sub = "—"

    avg_momentum = round(sum(t["momentum"] for t in tracks) / len(tracks), 1)

    return {
        "dates": [d.strftime("%b %d") for d in dates],
        "fyLabel": f"Track Acquisition · Real data",
        "tracks": tracks,
        "defaultTrackId": tracks[0]["id"] if tracks else None,
        "regionLabel": region_label,
        "summary": {
            "strongBuy": strong_buy,
            "topScore": top_track["acqScore"] if tracks else 0,
            "topTitle": f"{top_track['artist']} — {top_track['title']}" if tracks else "—",
            "fastest": fastest_name,
            "fastestSub": fastest_sub,
            "crossCount": cross_count,
            "avgMomentum": avg_momentum,
        },
    }


def render_track_acquisition(labels_filter: list[str] | None = None) -> None:
    st.markdown(
        "<div style='font-size: 0.92rem; color: var(--t2); margin: 0 0 14px; line-height: 1.5; font-weight: 500;'>"
        "🎵 Evaluate track-level acquisition potential by analyzing cross-platform performance metrics. "
        "This dashboard combines daily streaming data from Spotify (Global, US, and LATAM markets) "
        "with iTunes Worldwide chart movements to compute an overall Acquisition Score. "
        "Use the filtering tools and trajectory insights to identify breakout tracks with strong growth and momentum."
        "</div>",
        unsafe_allow_html=True,
    )

    # Load data for the maximum window (30 days) and let JS filter it
    window_days = 30
    latam_codes = ["ar", "bo", "br", "cl", "co", "cr", "do", "ec", "sv", "gt", "hn", "mx", "ni", "pa", "pe", "py", "uy", "ve"]
    all_codes = ["global", "us"] + latam_codes
    it_all_codes = ["ww", "us"]

    # These two queries are independent (different tables, separate
    # connections via _run_query) so there's no reason to wait on one before
    # starting the other.
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_sp_all = executor.submit(_load_window_multi, "spotify_daily", all_codes, window_days)
        f_it_all = executor.submit(_load_window_multi, "itunes_daily", it_all_codes, window_days)
        sp_all_df = f_sp_all.result()
        it_all_df = f_it_all.result()

    if labels_filter and not sp_all_df.empty and "label" in sp_all_df.columns:
        sp_all_df = sp_all_df[sp_all_df["label"].isin(labels_filter)]
    
    sp_global_df = sp_all_df if not sp_all_df.empty else pd.DataFrame()

    if labels_filter and not it_all_df.empty and "label" in it_all_df.columns:
        it_all_df = it_all_df[it_all_df["label"].isin(labels_filter)]
        
    it_global_df = it_all_df if not it_all_df.empty else pd.DataFrame()
    it_ww_df = it_all_df[it_all_df["country"] == "ww"] if not it_all_df.empty else pd.DataFrame()

    if sp_global_df.empty and it_global_df.empty:
        st.warning("No daily chart data available to build the track acquisition view.")
        return

    date_set = set()
    for df in [sp_global_df, it_global_df, it_ww_df]:
        if not df.empty:
            date_set.update(df["date"].tolist())

    if not date_set:
        st.warning("No chart dates found in the selected window.")
        return

    dates = sorted(date_set)

    # Build track rows for every region (global, US, and all LATAM codes) in
    # one batched + cached pass instead of 20 separate cached calls, each of
    # which previously had to hash its own sliced DataFrame before it could
    # even check the cache. See get_all_region_track_rows for details.
    all_region_tracks = get_all_region_track_rows(
        sp_all_df, it_global_df, it_ww_df, dates, tuple(latam_codes), limit=100
    )
    global_tracks = all_region_tracks.get("global", [])
    us_tracks = all_region_tracks.get("us", [])
    latam_tracks = {code: all_region_tracks.get(code, []) for code in latam_codes}

    if not global_tracks and not us_tracks and not any(latam_tracks.values()):
        st.warning("No track acquisition rows could be built from the available chart data.")
        return

    payload = _build_payload(global_tracks, dates, region_label="Spotify Global")
    us_payload = _build_payload(us_tracks, dates, region_label="Spotify US")

    payload.setdefault("tracks", [])
    payload.setdefault("dates", [d.strftime("%b %d") for d in dates])
    
    default_id = None
    if global_tracks: default_id = global_tracks[0]["id"]
    elif us_tracks: default_id = us_tracks[0]["id"]
    
    payload.setdefault("defaultTrackId", default_id)
    payload.setdefault("regionLabel", "Spotify Global")
    payload.setdefault("summary", {})
    payload["maxWindowDays"] = window_days

    payload["usTracks"] = us_tracks
    payload["usSummary"] = us_payload.get("summary", {})
    payload["latamTracks"] = latam_tracks

    with st.expander("ℹ️ How is the Acquisition Score calculated?"):
        st.markdown(
            "The **Acquisition Score (0-100)** is a composite metric evaluating a track's market potential. It is calculated using:\n"
            "- **Latest Streams (30%)**: Scaled based on daily volume.\n"
            "- **Best Rank (20%)**: Spotify Global/US chart peak.\n"
            "- **Momentum (40%)**: Trajectory of stream growth and rank delta. Computed as `(Rank Delta * 0.24) + (Stream Growth % * 0.35)`.\n"
            "- **iTunes Bonus (10%)**: Cross-platform validation from iTunes WW charts.\n\n"
            "👉 **Interactive Analysis**: Select any track from the leaderboard to instantly load its detailed acquisition profile, including stream trajectories and specific market signals."
        )
        st.markdown(
            """
            <style>
            [data-testid="stExpander"] {
                border: 2px solid var(--border) !important;
                border-radius: 12px !important;
                background-color: var(--surface) !important;
                overflow: hidden !important;
            }
            [data-testid="stExpander"] summary {
                background-color: var(--surface2) !important;
                border-bottom: 1px solid var(--border) !important;
            }
            [data-testid="stExpander"] summary p {
                font-family: 'Inter', system-ui, sans-serif !important;
                font-weight: 600 !important;
                font-size: 15px !important;
                color: var(--text) !important;
            }
            [data-testid="stExpander"] .stMarkdown p, 
            [data-testid="stExpander"] .stMarkdown li {
                font-family: 'Inter', system-ui, sans-serif !important;
                font-size: 14px !important;
                color: var(--text2) !important;
                line-height: 1.6 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    html = _build_html(payload, dark_mode=st.session_state.get("dark_mode", True))
    st_components.html(html, height=750, scrolling=True)


def _build_html(payload: dict[str, Any], dark_mode: bool = False) -> str:
    data_json = json.dumps(payload, default=str)
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    body_class = "dark" if dark_mode else "light"
    return """
<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
__THEME__
:root {
  --color-background-primary: var(--bg2);
  --color-background-secondary: var(--bg3);
  --color-border-secondary: var(--border2);
  --color-border-tertiary: var(--border);
  --color-text-primary: var(--t1);
  --color-text-secondary: var(--t2);
  --color-text-tertiary: var(--t3);
  --border-radius-md: 6px;
  --border-radius-lg: 10px;
  --font-sans: 'Inter', system-ui, sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); font-family: var(--font-sans); color: var(--t1); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }

.dash-wrapper { display: flex; flex-direction: column; gap: 12px; height: 100vh; padding: 12px 16px; overflow: hidden; }
.dash { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; flex: 1; min-height: 0; }

.left-col { display: flex; flex-direction: column; gap: 12px; overflow: hidden; }

.filters { display: flex; gap: 8px; align-items: center; flex-wrap: nowrap; flex-shrink: 0; width: 100%; overflow-x: auto; padding-bottom: 2px; }
.filter-row { display: flex; gap: 8px; align-items: center; flex-wrap: nowrap; width: 100%; min-width: 0; }
.filter-btn { font-size: 12px; padding: 5px 12px; border-radius: 999px; border: 0.5px solid var(--color-border-secondary); background: var(--color-background-primary); color: var(--color-text-secondary); cursor: pointer; transition: all .15s; }
.filter-btn.active { background: #185FA5; color: #E6F1FB; border-color: #185FA5; }
.filter-tag { display: flex; align-items: center; font-size: 14px; padding: 8px 16px; border-radius: 999px; background: var(--color-background-secondary); color: var(--color-text-secondary); border: 1px solid var(--color-border-tertiary); cursor: pointer; flex: 0 1 220px; min-width: 180px; }
.filter-tag select { background: transparent; border: none; color: inherit; font-size: inherit; font-family: inherit; outline: none; cursor: pointer; width: 100%; min-width: 0; }
.window-chip-group { display: flex; gap: 8px; flex-wrap: nowrap; align-items: center; }
.window-chip { border: 1px solid var(--color-border-tertiary); background: var(--color-background-primary); color: var(--color-text-secondary); font: inherit; font-size: 13px; line-height: 1; padding: 9px 14px; min-height: 38px; border-radius: 999px; cursor: pointer; transition: all .15s ease; white-space: nowrap; flex: 0 0 auto; }
.window-chip:hover { border-color: #185FA5; color: #185FA5; }
.window-chip.active { background: #185FA5; border-color: #185FA5; color: #E6F1FB; }

.track-table { background: var(--color-background-primary); border: 2px solid var(--color-border-secondary); border-radius: var(--border-radius-lg); overflow: hidden; display: flex; flex-direction: column; flex: 1; min-height: 0; transition: border-color 0.2s; }
.track-table:hover { border-color: #E24B4A; }
.track-header { display: grid; grid-template-columns: 28px 1fr 56px 72px 72px 52px; gap: 8px; padding: 9px 14px; border-bottom: 0.5px solid var(--color-border-tertiary); background: var(--color-background-secondary); flex-shrink: 0; }
.track-header span { font-size: 11px; color: var(--color-text-tertiary); font-weight: 500; text-transform: uppercase; letter-spacing: .04em; cursor: pointer; text-align: left; }
.track-header .col-r { text-align: right; }

.track-body { overflow-y: auto; flex: 1; }
.track-body::-webkit-scrollbar { width: 5px; }
.track-body::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 5px; }

.track-row { display: grid; grid-template-columns: 28px 1fr 56px 72px 72px 52px; gap: 8px; padding: 9px 14px; border-bottom: 0.5px solid var(--color-border-tertiary); align-items: center; cursor: pointer; transition: background .1s; }
.track-row:last-child { border-bottom: none; }
.track-row:hover { background: var(--color-background-secondary); }
.track-row.selected { background: #E6F1FB; }
.dark .track-row.selected { background: #042C53; }

.sr-num { font-size: 12px; color: var(--color-text-tertiary); text-align: center; }
.track-info { min-width: 0; text-align: left; }
.track-name { font-size: 13px; font-weight: 500; color: var(--color-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.track-artist { font-size: 11px; color: var(--color-text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 1px; }

.col-r { text-align: right; }
.streams-val { font-size: 12px; color: var(--color-text-primary); font-weight: 500; font-variant-numeric: tabular-nums; }
.momentum-val { font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums; }
.momentum-pos { color: #1D9E75; }
.momentum-neg { color: #E24B4A; }
.momentum-flat { color: var(--color-text-secondary); }

.acq-pill { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 20px; border-radius: 999px; font-size: 11px; font-weight: 500; }
.acq-hi { background: #EAF3DE; color: #3B6D11; }
.acq-mid { background: #E6F1FB; color: #185FA5; }
.acq-lo { background: #F1EFE8; color: #5F5E5A; }

.right-col { display: flex; flex-direction: column; gap: 12px; overflow-y: auto; padding-right: 4px; }
.right-col::-webkit-scrollbar { width: 5px; }
.right-col::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 5px; }

.detail-card { background: var(--color-background-primary); border: 2px solid var(--color-border-secondary); border-radius: var(--border-radius-lg); padding: 16px; flex-shrink: 0; transition: border-color 0.2s; }
.detail-card:hover { border-color: #E24B4A; }

.detail-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 12px; }
.detail-title { font-size: 17px; font-weight: 500; color: var(--color-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
.detail-artist { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
.detail-badges { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.badge { font-size: 10px; padding: 3px 8px; border-radius: 4px; border: 0.5px solid var(--color-border-secondary); color: var(--color-text-secondary); background: var(--color-background-secondary); }
.badge.active-b { background: #E6F1FB; color: #185FA5; border-color: #B5D4F4; }

.acq-score-big { font-size: 40px; font-weight: 500; color: var(--color-text-primary); line-height: 1; }
.acq-label { font-size: 11px; color: var(--color-text-secondary); margin-top: 3px; }
.acq-rank { font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px; }

.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.stat-box { background: var(--color-background-secondary); border-radius: var(--border-radius-md); padding: 10px 12px; border: 2px solid var(--color-border-secondary); transition: border-color 0.2s; }
.stat-box:hover { border-color: #E24B4A; }
.stat-label { font-size: 10px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .04em; margin-bottom: 4px; }
.stat-value { font-size: 16px; font-weight: 500; color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.stat-sub { font-size: 10px; color: var(--color-text-secondary); margin-top: 2px; }
.stat-value.pos { color: #1D9E75; }
.stat-value.neg { color: #E24B4A; }

.chart-section { margin-bottom: 4px; }
.chart-label { font-size: 11px; color: var(--color-text-secondary); margin-bottom: 6px; font-weight: 500; }
.chart-wrap { position: relative; width: 100%; height: 130px; }

.signals-section { }
.signals-label { font-size: 11px; color: var(--color-text-secondary); font-weight: 500; margin-bottom: 8px; text-transform: uppercase; letter-spacing: .04em; }
.signal-row { display: flex; gap: 10px; align-items: flex-start; padding: 8px 0; border-bottom: 0.5px solid var(--color-border-tertiary); }
.signal-row:last-child { border-bottom: none; }
.signal-icon { font-size: 16px; margin-top: 1px; flex-shrink: 0; }
.signal-text strong { font-size: 12px; font-weight: 500; color: var(--color-text-primary); display: block; }
.signal-text span { font-size: 11px; color: var(--color-text-secondary); line-height: 1.4; }

#searchInput { background: transparent; border: none; color: inherit; outline: none; width: 100%; min-width: 0; font-family: inherit; font-size: inherit; }
#searchInput::placeholder { color: var(--color-text-tertiary); }

.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 300px; color: var(--color-text-tertiary); text-align: center; gap: 8px; }

@media (max-width: 1100px) {
  .dash-wrapper { height: auto; overflow: visible; }
  .dash { grid-template-columns: 1fr; }
  .filters { width: 100%; }
  .filter-row { width: max-content; }
  .window-chip-group { flex-wrap: nowrap; }
  .left-col { overflow: visible; }
  .track-table { min-height: 400px; max-height: 600px; }
  .right-col { overflow: visible; }
}
</style>
</head><body class="__BODY_CLASS__">

<h2 class="sr-only" style="display:none;">Music acquisition analytics dashboard showing top tracks by acquisition score, streams, and momentum</h2>

<div class="dash-wrapper">
  <div class="filters">

      <span class="filter-row">
        <span class="filter-tag">
            <input type="text" id="searchInput" placeholder="Search..." oninput="applyFilters()">
        </span>
        <span class="filter-tag">
          <select id="regionSel" onchange="changeRegion()">
            <option value="global">All Country</option>
            <option value="us">United States Country</option>
            <optgroup label="Latin America">
              <option value="ar">Argentina Country</option>
              <option value="bo">Bolivia Country</option>
              <option value="br">Brazil Country</option>
              <option value="cl">Chile Country</option>
              <option value="co">Colombia Country</option>
              <option value="cr">Costa Rica Country</option>
              <option value="do">Dominican Republic Country</option>
              <option value="ec">Ecuador Country</option>
              <option value="sv">El Salvador Country</option>
              <option value="gt">Guatemala Country</option>
              <option value="hn">Honduras Country</option>
              <option value="mx">Mexico Country</option>
              <option value="ni">Nicaragua Country</option>
              <option value="pa">Panama Country</option>
              <option value="pe">Peru Country</option>
              <option value="py">Paraguay Country</option>
              <option value="uy">Uruguay Country</option>
              <option value="ve">Venezuela Country</option>
            </optgroup>
          </select>
        </span>
        <span class="window-chip-group" role="tablist" aria-label="Time window">
          <button type="button" class="window-chip" data-window="7" onclick="setTimeWindow(7, this)">Last Week</button>
          <button type="button" class="window-chip" data-window="14" onclick="setTimeWindow(14, this)">Last 2 Weeks</button>
          <button type="button" class="window-chip active" data-window="30" onclick="setTimeWindow(30, this)">Last Month</button>
        </span>
      </span>
  </div>

<div class="dash">
  <div class="left-col">
    <div class="track-table">
      <div class="track-header">
        <span>#</span>
        <span onclick="setSort('title')">Artist / Track</span>
        <span class="col-r" onclick="setSort('rank')">Rank</span>
        <span class="col-r" onclick="setSort('streams')">Streams</span>
        <span class="col-r" onclick="setSort('momentum')">Momentum</span>
        <span class="col-r" onclick="setSort('acq')">Score</span>
      </div>
      <div class="track-body" id="track-table">
        <!-- Tracks rendered here -->
      </div>
    </div>
  </div>

  <div class="right-col" id="detail-panel">
    <div class="detail-card">
      <div class="detail-header">
        <div>
          <div class="detail-title" id="d-title">Select Track</div>
          <div class="detail-artist" id="d-artist">—</div>
          <div class="detail-badges" id="d-badges">
          </div>
        </div>
        <div style="text-align:right;">
          <div class="acq-score-big" id="d-score">—</div>
          <div class="acq-label">Acq. Score</div>
          <div class="acq-rank" id="d-rank">—</div>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-box">
          <div class="stat-label">Best Rank</div>
          <div class="stat-value" id="d-rank-val">—</div>
          <div class="stat-sub" id="d-rank-sub">Global</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Latest Streams - Daily</div>
          <div class="stat-value" id="d-streams">—</div>
          <div class="stat-sub" id="d-streams-sub">—</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Momentum (0.24*Rank + 0.35*Growth)</div>
          <div class="stat-value" id="d-momentum">—</div>
          <div class="stat-sub" id="d-momentum-sub">Window change</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Days in Chart</div>
          <div class="stat-value" id="d-days">—</div>
          <div class="stat-sub">Window days</div>
        </div>
      </div>

      <div class="chart-section" id="d-chart-section" style="display:none">
        <div class="chart-label">Stream + Rank Trajectory</div>
        <div class="chart-wrap">
          <canvas id="trajChart" role="img" aria-label="Trajectory chart"></canvas>
        </div>
        <div style="display:flex;gap:16px;margin-top:6px;">
          <span style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--color-text-secondary)"><span style="width:16px;height:2px;background:#378ADD;display:inline-block;border-radius:1px"></span>Streams</span>
          <span style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--color-text-secondary)"><span style="width:16px;height:2px;background:#9FE1CB;display:inline-block;border-radius:1px;border-top:2px dashed #9FE1CB;height:0"></span>Rank</span>
        </div>
      </div>
      
      <div class="chart-section" id="d-it-chart-section" style="display:none; margin-top: 12px;">
        <div class="chart-label">iTunes Trajectory</div>
        <div class="chart-wrap">
          <canvas id="itTrajChart" role="img" aria-label="iTunes Trajectory chart"></canvas>
        </div>
        <div style="display:flex;gap:16px;margin-top:6px;">
          <span style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--color-text-secondary)"><span style="width:16px;height:2px;background:#a78bfa;display:inline-block;border-radius:1px"></span>Score</span>
        </div>
      </div>

      <div id="d-signals-card" style="display:none; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--color-border-tertiary);">
        <div class="signals-label">Acquisition Signals</div>
        <div id="d-signals">
          <!-- Signals here -->
        </div>
      </div>
    </div>
    
    <div id="empty-state" class="empty-state">
        <div style="font-size:28px">↑</div>
        <div style="font-size:12px">Select a track from the list<br>to view its acquisition profile</div>
    </div>
  </div>
</div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const ORIGINAL_PAYLOAD = __PAYLOAD__;
const ORIGINAL_DATES = ORIGINAL_PAYLOAD.dates || [];
const ORIGINAL_GLOBAL_TRACKS = ORIGINAL_PAYLOAD.tracks || [];
const ORIGINAL_US_TRACKS = ORIGINAL_PAYLOAD.usTracks || [];
const ORIGINAL_LATAM_TRACKS = ORIGINAL_PAYLOAD.latamTracks || {};
const DATES = ORIGINAL_DATES;

let PAYLOAD = JSON.parse(JSON.stringify(ORIGINAL_PAYLOAD));
let TRACKS = (PAYLOAD.tracks && PAYLOAD.tracks.length) ? PAYLOAD.tracks : (PAYLOAD.usTracks || []);

let currentRegion = 'global';
let currentSort = 'acq';
let currentPeriod = 'all';
let currentTimeWindowDays = ORIGINAL_PAYLOAD.maxWindowDays;

let selectedId = PAYLOAD.defaultTrackId || (TRACKS.length ? TRACKS[0].id : null);
let trajChartInst = null;
let itTrajChartInst = null;

// Acq Score
function _jsAcqScore(latestStreams, bestRank, momentum, bestItRank) {
    const safeRank = Number.isFinite(Number(bestRank)) && Number(bestRank) > 0 ? Number(bestRank) : null;
    const safeItRank = Number.isFinite(Number(bestItRank)) && Number(bestItRank) > 0 ? Number(bestItRank) : null;
    const safeStreams = Number.isFinite(Number(latestStreams)) ? Number(latestStreams) : 0;
    const safeMomentum = Number.isFinite(Number(momentum)) ? Number(momentum) : 0;
    const rankScore = Math.max(0, 20 - (safeRank || 100) * 0.2);
    const streamScore = Math.min(30, Math.floor(safeStreams / 300000));
    const momentumScore = Math.max(-20, Math.min(40, Math.floor(safeMomentum * 2)));
    const itunesBonus = safeItRank && safeItRank <= 25 ? 10 : (safeItRank && safeItRank <= 60 ? 5 : 0);
    return Math.max(0, Math.min(100, Math.floor(rankScore + streamScore + momentumScore + itunesBonus)));
}

function bestRankFrom(ranks) {
    const values = (ranks || []).map(Number).filter(v => Number.isFinite(v) && v > 0);
    return values.length ? Math.min(...values) : null;
}

function displayRank(rank) {
    const value = Number(rank);
    return Number.isFinite(value) && value > 0 ? Math.round(value).toString() : '—';
}

// Signals
function _jsBuildSignals(track, regionLabel) {
    const signals = [];
    const regionTitle = regionLabel.includes("US") ? "US" : "Global";

    if (track.growth >= 25) {
        signals.push({icon: "🚀", t: `+${track.growth.toFixed(1)}% stream growth`, d: "Strong volume acceleration across the tracked window."});
    } else if (track.growth >= 0) {
        signals.push({icon: "📈", t: `${track.growth.toFixed(1)}% stream growth`, d: "Healthy audience momentum over the recent chart window."});
    } else {
        signals.push({icon: "📉", t: `${track.growth.toFixed(1)}% stream decline`, d: "Streams are cooling; monitor for stabilization."});
    }

    if (track.platform === "cross") {
        signals.push({icon: "🌍", t: "Cross-platform signal", d: `Appearing on both Spotify ${regionTitle} and iTunes WW charts.`});
    } else if (track.platform === "spotify") {
        signals.push({icon: "🎧", t: `Spotify-${regionTitle} native momentum`, d: `Strong Spotify ${regionTitle} traction even without iTunes chart entry.`});
    } else {
        signals.push({icon: "🍎", t: "iTunes WW curve", d: "iTunes-only chart signal; could still breakout to Spotify."});
    }

    if (track.label && track.label.toLowerCase().includes("independ")) {
        signals.push({icon: "💡", t: "Independent / unsigned", d: "Clean acquisition candidate with limited major-label competition."});
    } else {
        signals.push({icon: "🏷️", t: `Label: ${track.label}`, d: "Track-level signal from a managed catalogue or label roster."});
    }

    if (track.bestRank && track.bestRank <= 10) { 
        signals.push({icon: "🏆", t: `Top ${track.bestRank} Spotify ${regionTitle}`, d: `Elite placement on Spotify ${regionTitle} charts.`});
    } else if (track.bestItRank && track.bestItRank <= 20) {
        signals.push({icon: "📊", t: `iTunes #${track.bestItRank}`, d: "Strong iTunes WW validation for the track."});
    } else if (track.hasIt) {
        signals.push({icon: "🔁", t: "iTunes momentum present", d: "Track is charting on iTunes WW and may cross into Spotify."});
    }

    return signals.slice(0, 5);
}

function recalculateTrackMetrics(track, windowDays, fullDates, regionLabel) {
    const startIndex = Math.max(0, fullDates.length - windowDays);
    const slicedSpStreams = track.originalSpStreams.slice(startIndex);
    const slicedSpRanks = track.originalSpRanks.slice(startIndex);
    const slicedItScores = track.originalItScores.slice(startIndex);
    const slicedItRanks = track.originalItRanks.slice(startIndex);

    const hasSp = slicedSpStreams.some(v => v > 0);
    const hasIt = slicedItScores.some(v => v > 0);

    const firstSp = slicedSpStreams.find(v => v > 0) || 0;
    const latestSp = [...slicedSpStreams].reverse().find(v => v > 0) || 0;
    const firstRank = slicedSpRanks.find(r => r !== null) || null;
    const latestRank = [...slicedSpRanks].reverse().find(r => r !== null) || null;
    const bestSpRank = bestRankFrom(slicedSpRanks);
    const bestItRank = bestRankFrom(slicedItRanks);

    const growth = firstSp ? Number(((latestSp - firstSp) / firstSp * 100).toFixed(1)) : 0.0;
    const rankDelta = (firstRank !== null && latestRank !== null) ? (firstRank - latestRank) : 0;
    const momentum = Number((rankDelta * 0.24 + growth * 0.35).toFixed(1));

    const acqScore = _jsAcqScore(latestSp, bestSpRank, momentum, bestItRank);

    const recalculatedTrack = { ...track };
    recalculatedTrack.spStreams = slicedSpStreams; 
    recalculatedTrack.spRanks = slicedSpRanks;
    recalculatedTrack.itScores = slicedItScores;
    recalculatedTrack.itRanks = slicedItRanks;
    recalculatedTrack.bestRank = bestSpRank || bestItRank;
    recalculatedTrack.bestSpRank = bestSpRank;
    recalculatedTrack.bestItRank = bestItRank;
    recalculatedTrack.latestStreams = latestSp;
    recalculatedTrack.firstStreams = firstSp;
    recalculatedTrack.momentum = momentum;
    recalculatedTrack.growth = growth;
    recalculatedTrack.acqScore = acqScore;
    recalculatedTrack.days = windowDays;
    recalculatedTrack.totalStreams = slicedSpStreams.reduce((sum, v) => sum + v, 0);
    recalculatedTrack.signals = _jsBuildSignals(recalculatedTrack, regionLabel);
    recalculatedTrack.hasSp = hasSp;
    recalculatedTrack.hasIt = hasIt;

    return recalculatedTrack;
}

function changeRegion() {
  const r = document.getElementById('regionSel').value;
  currentRegion = r;
  
  if (r === 'global') {
    PAYLOAD.regionLabel = 'Spotify Global';
    TRACKS = JSON.parse(JSON.stringify(ORIGINAL_GLOBAL_TRACKS));
  } else if (r === 'us') {
    PAYLOAD.regionLabel = 'Spotify US';
    TRACKS = JSON.parse(JSON.stringify(ORIGINAL_US_TRACKS));
  } else {
    PAYLOAD.regionLabel = `Spotify ${r.toUpperCase()}`;
    TRACKS = JSON.parse(JSON.stringify(ORIGINAL_LATAM_TRACKS[r] || []));
  }

  TRACKS.forEach(track => {
    track.originalSpStreams = [...track.spStreams];
    track.originalSpRanks = [...track.spRanks];
    track.originalItScores = [...track.itScores];
    track.originalItRanks = [...track.itRanks];
  });

  TRACKS = TRACKS.map(track => recalculateTrackMetrics(track, currentTimeWindowDays, ORIGINAL_DATES, PAYLOAD.regionLabel));

  selectedId = TRACKS[0]?.id;
  applyFilters();
}

function setTimeWindow(val) {
    currentTimeWindowDays = Number.parseInt(val, 10) || ORIGINAL_PAYLOAD.maxWindowDays;
    document.querySelectorAll('.window-chip').forEach(btn => btn.classList.toggle('active', btn.dataset.window === String(currentTimeWindowDays)));
    applyFilters();
    if (selectedId) selectTrack(selectedId); 
}

function fmtN(n){if(!n&&n!==0)return'—';const a=Math.abs(n);if(a>=1e6)return(n/1e6).toFixed(1)+'M';if(a>=1e3)return(n/1e3).toFixed(0)+'K';return Math.round(n).toString();}

function windowLabel(days) {
  if (days <= 7) return 'Last week';
  if (days <= 14) return 'Last 2 weeks';
  return 'Last month';
}

function setSort(s){
  currentSort = s;
  applyFilters();
}

function setPeriod(p, el){
  currentPeriod = p;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
  applyFilters();
}

function applyFilters(){
  let filteredTracks = [];
  if (currentRegion === 'global') {
      filteredTracks = JSON.parse(JSON.stringify(ORIGINAL_GLOBAL_TRACKS));
  } else if (currentRegion === 'us') {
      filteredTracks = JSON.parse(JSON.stringify(ORIGINAL_US_TRACKS));
  } else {
      filteredTracks = JSON.parse(JSON.stringify(ORIGINAL_LATAM_TRACKS[currentRegion] || []));
  }

  filteredTracks.forEach(track => {
    track.originalSpStreams = [...track.spStreams];
    track.originalSpRanks = [...track.spRanks];
    track.originalItScores = [...track.itScores];
    track.originalItRanks = [...track.itRanks];
  });

  filteredTracks = filteredTracks.map(track => recalculateTrackMetrics(track, currentTimeWindowDays, ORIGINAL_DATES, PAYLOAD.regionLabel));
  filteredTracks = filteredTracks.filter(t => Number(t.acqScore) > 0);

  const q = document.getElementById('searchInput').value.toLowerCase();
  
  if(q) filteredTracks = filteredTracks.filter(t=>t.title.toLowerCase().includes(q)||t.artist.toLowerCase().includes(q));
  if(currentPeriod==='rising') filteredTracks = filteredTracks.filter(t=>t.momentum>5);
  if(currentPeriod==='stable') filteredTracks = filteredTracks.filter(t=>Math.abs(t.momentum)<=5);
  if(currentPeriod==='falling') filteredTracks = filteredTracks.filter(t=>t.momentum<-5);

  TRACKS = filteredTracks;

  const sortMap={acq:'acqScore',momentum:'momentum',rank:'bestRank',streams:'latestStreams',title:'title'};
  const key=sortMap[currentSort]||'acqScore';
  const asc=(key==='bestRank' || key==='title');
  TRACKS.sort((a,b)=>{
    if (key === 'title') {
        return a.title.localeCompare(b.title);
    }
    if (key === 'bestRank') {
        const ar = Number.isFinite(Number(a[key])) && Number(a[key]) > 0 ? Number(a[key]) : Number.POSITIVE_INFINITY;
        const br = Number.isFinite(Number(b[key])) && Number(b[key]) > 0 ? Number(b[key]) : Number.POSITIVE_INFINITY;
        return ar - br;
    }
    return asc ? a[key]-b[key] : b[key]-a[key];
  });

  renderTable();
}

function renderTable() {
    const el = document.getElementById('track-table');
    let htmlStr = '';

    TRACKS.forEach((t, i) => {
        const momColor = t.momentum > 5 ? 'momentum-pos' : t.momentum < -5 ? 'momentum-neg' : 'momentum-flat';
        let acqClass = 'acq-lo';
        if (t.acqScore >= 60) acqClass = 'acq-hi';
        else if (t.acqScore >= 45) acqClass = 'acq-mid';

        htmlStr += `
        <div class="track-row ${t.id === selectedId ? 'selected' : ''}" onclick="selectTrack(${t.id})">
            <div class="sr-num">${i + 1}</div>
            <div class="track-info">
                <div class="track-name">${t.title}</div>
                <div class="track-artist">${t.artist}${t.label && t.label !== '—' ? ' - ' + t.label : ''}</div>
            </div>
            <div class="col-r streams-val">${displayRank(t.bestRank)}</div>
            <div class="col-r streams-val">${fmtN(t.latestStreams)}</div>
            <div class="col-r momentum-val ${momColor}">${t.momentum > 0 ? '+' : ''}${t.momentum}%</div>
            <div class="col-r"><span class="acq-pill ${acqClass}">${t.acqScore}</span></div>
        </div>`;
    });
    el.innerHTML = htmlStr;
}

function renderChart(traj, ranks, days) {
  const ctx = document.getElementById('trajChart').getContext('2d');
  if (trajChartInst) trajChartInst.destroy();
  const labels = DATES.slice(Math.max(0, DATES.length - days));
  
  trajChartInst = new Chart(ctx, {
    data: {
      labels,
      datasets: [
        { type:'line', label:'Streams', data: traj, borderColor:'#378ADD', backgroundColor:'rgba(55,138,221,0.08)', borderWidth:2, pointRadius:3, pointBackgroundColor:'#378ADD', tension:.4, yAxisID:'y', spanGaps: true, fill: true },
        { type:'line', label:'Rank', data: ranks, borderColor:'#9FE1CB', borderWidth:2, borderDash:[4,3], pointRadius:3, pointBackgroundColor:'#9FE1CB', tension:.4, yAxisID:'y2', spanGaps: true }
      ]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{ legend:{ display:false } },
      scales:{
        x:{ display:true, ticks:{ font:{size:9}, color:'#888', maxTicksLimit:6 }, grid:{ display:false } },
        y:{ display:true, ticks:{ font:{size:9}, color:'#888', maxTicksLimit:4, callback:v=>fmtN(v) }, grid:{ color:'rgba(128,128,128,0.1)' } },
        y2:{ display:true, position:'right', reverse:true, grid:{display:false}, ticks:{ font:{size:9}, color:'#9FE1CB', callback:v=>'#'+v } }
      }
    }
  });
}

function renderItChart(traj, days) {
  const ctx = document.getElementById('itTrajChart').getContext('2d');
  if (itTrajChartInst) itTrajChartInst.destroy();
  const labels = DATES.slice(Math.max(0, DATES.length - days));
  
  itTrajChartInst = new Chart(ctx, {
    data: {
      labels,
      datasets: [
        { type:'line', label:'iTunes Score', data: traj, borderColor:'#a78bfa', backgroundColor:'rgba(167,139,250,.08)', borderWidth:2, pointRadius:3, pointBackgroundColor:'#a78bfa', tension:.4, yAxisID:'y', spanGaps: true, fill: true },
      ]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{ legend:{ display:false } },
      scales:{
        x:{ display:true, ticks:{ font:{size:9}, color:'#888', maxTicksLimit:6 }, grid:{ display:false } },
        y:{ display:true, ticks:{ font:{size:9}, color:'#888', maxTicksLimit:4, callback:v=>fmtN(v) }, grid:{ color:'rgba(128,128,128,0.1)' } }
      }
    }
  });
}

function selectTrack(id) {
  selectedId = id;
  const t = TRACKS.find(x => x.id === id);
  renderTable(); 

  if (!t) {
    document.getElementById('empty-state').style.display = 'flex';
    document.getElementById('d-chart-section').style.display = 'none';
    document.getElementById('d-it-chart-section').style.display = 'none';
    document.getElementById('d-signals-card').style.display = 'none';
    return;
  }

  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('d-title').textContent = t.title;
  document.getElementById('d-artist').textContent = t.artist + (t.label ? ' · ' + t.label : '');
  
  document.getElementById('d-score').textContent = t.acqScore;
  const sortedByAcq = [...TRACKS].sort((a,b) => b.acqScore - a.acqScore);
  const rank = sortedByAcq.findIndex(x => x.id === id) + 1;
  document.getElementById('d-rank').textContent = `#${rank} of ${TRACKS.length}`;
  
  document.getElementById('d-rank-val').textContent = displayRank(t.bestRank);
  document.getElementById('d-rank-sub').textContent = PAYLOAD.regionLabel;
  
  document.getElementById('d-streams').textContent = fmtN(t.latestStreams);
  document.getElementById('d-streams-sub').textContent = `${windowLabel(currentTimeWindowDays)} · ${t.growth > 0 ? '+' : ''}${t.growth}% growth`;
  document.getElementById('d-streams-sub').style.color = t.growth > 0 ? '#1D9E75' : t.growth < 0 ? '#E24B4A' : 'var(--color-text-secondary)';
  
  const mEl = document.getElementById('d-momentum');
  mEl.textContent = `${t.momentum > 0 ? '+' : ''}${t.momentum}%`;
  mEl.className = 'stat-value ' + (t.momentum > 5 ? 'pos' : t.momentum < -5 ? 'neg' : '');
  document.getElementById('d-momentum-sub').textContent = `${windowLabel(currentTimeWindowDays)} window`;

  document.getElementById('d-days').textContent = t.days;

  const badgesEl = document.getElementById('d-badges');
  badgesEl.innerHTML = '';
  if (t.platform) badgesEl.innerHTML += `<span class="badge active-b">${t.platform.toUpperCase()}</span>`;
  if (t.label && t.label.toLowerCase().includes('independ')) badgesEl.innerHTML += `<span class="badge">Independent</span>`;

  document.getElementById('d-signals-card').style.display = 'block';
  const sigHtml = t.signals.map(s =>
    `<div class="signal-row"><div class="signal-icon" aria-hidden="true">${s.icon}</div><div class="signal-text"><strong>${s.t}</strong><span>${s.d}</span></div></div>`
  ).join('');
  document.getElementById('d-signals').innerHTML = sigHtml;

  document.getElementById('d-chart-section').style.display = 'block';
  renderChart(t.spStreams, t.spRanks, t.days);
  
  const hasIt = t.itScores && t.itScores.some(v => v > 0);
  if (hasIt) {
      document.getElementById('d-it-chart-section').style.display = 'block';
      renderItChart(t.itScores, t.days);
  } else {
      document.getElementById('d-it-chart-section').style.display = 'none';
  }
}

changeRegion(); 
if(selectedId){setTimeout(()=>selectTrack(selectedId),80);}
</script>
</body></html>
""".replace("__PAYLOAD__", data_json).replace("__THEME__", theme_css).replace("__BODY_CLASS__", body_class)