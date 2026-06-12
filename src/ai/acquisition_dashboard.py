"""
Acquisition dashboard — Commercial Signal Intelligence view.

Builds a per-artist acquisition recommendation card from the
`spotify_daily` (country='global') and `itunes_daily` (country='ww')
tables, plus a leaderboard ranking all artists in the window by a
composite acquisition score.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src.database.connection import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)


WINDOW_DAYS = 30  # take all available data within last N days

# ───────────────────────── theme CSS ──────────────────────────
_THEME_LIGHT = ":root{--bg:#F5F6FA;--bg2:#FFFFFF;--bg3:#F8F9FB;--bg4:#EEF1F7;--border:rgba(148,163,184,.2);--border2:rgba(148,163,184,.35);--t1:#1A1A1A;--t2:#4A5568;--t3:#8A8FA3;--t4:#A0AEC0;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"
_THEME_DARK  = ":root{--bg:#0d1117;--bg2:#161b27;--bg3:#1a2035;--bg4:#1e2740;--border:rgba(41,52,85,.7);--border2:rgba(58,70,97,.8);--t1:#e2e8f0;--t2:#94a3b8;--t3:#8b95ad;--t4:#6b7a99;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"


# ───────────────────────── data helpers ──────────────────────────

def _split_at(at: str | None) -> tuple[str, str]:
    if not at:
        return "—", "—"
    if " - " in at:
        artist, title = at.split(" - ", 1)
    else:
        artist, title = at, at
    return artist.strip(), title.strip()


def _initials(name: str) -> str:
    parts = [p for p in name.replace("&", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# Deterministic colour for each artist
_PALETTE = [
    "#fbbf24", "#60a5fa", "#a78bfa", "#2dd4bf", "#22c55e",
    "#f472b6", "#fb923c", "#94a3b8", "#f87171", "#34d399",
    "#c4b5fd", "#5eead4", "#fcd34d", "#f9a8d4", "#7dd3fc",
]


def _color_for(name: str) -> str:
    h = sum(ord(c) for c in name) % len(_PALETTE)
    return _PALETTE[h]


def _run_query(query: str, params: tuple) -> list[dict]:
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.error("acquisition query failed: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


@st.cache_data(ttl=300, show_spinner=False)
def _load_daily(table: str, country: str, days: int) -> pd.DataFrame:
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
    df["artist"], df["title"] = zip(*df["artist_title"].map(_split_at))
    return df


@st.cache_data(ttl=300, show_spinner=False)
def get_processed_artist_payloads(
    universe_df: pd.DataFrame,
    sp_artist_df: pd.DataFrame,
    it_artist_df: pd.DataFrame,
    sp_daily_df: pd.DataFrame,
    it_daily_df: pd.DataFrame,
    dates: list[date],
) -> dict[str, dict]:
    """
    Cached wrapper for building artist payloads.
    Caching the results of processing logic significantly improves dashboard responsiveness.
    """
    return _build_artist_payloads(universe_df, sp_artist_df, it_artist_df, sp_daily_df, it_daily_df, dates)


@st.cache_data(ttl=300, show_spinner=False)
def _load_artist_universe(days: int) -> pd.DataFrame:
    """Primary universe = artists ranked on iTunes WW within the given window."""
    query = """
        WITH bounds AS (SELECT MAX(scrape_date) AS max_d FROM itunes_artist_rankings)
        SELECT DISTINCT a.id AS artist_id, a.name
        FROM itunes_artist_rankings ir
        CROSS JOIN bounds b
        JOIN artists a ON a.id = ir.artist_id
        WHERE ir.scrape_date > (b.max_d - %s::int)
          AND ir.scrape_date <= b.max_d
          AND a.name IS NOT NULL
        ORDER BY a.name
    """
    rows = _run_query(query, (days,))
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["artist_id", "name"])


@st.cache_data(ttl=300, show_spinner=False)
def _load_spotify_artist_series(days: int) -> pd.DataFrame:
    """One row per (artist, scrape_date) using the latest scrape of the day."""
    query = """
        WITH bounds AS (SELECT MAX(scrape_date) AS max_d FROM spotify_artists),
        ranked AS (
            SELECT
              sa.artist_id,
              sa.scrape_date,
              sa.monthly_listeners,
              ROW_NUMBER() OVER (
                PARTITION BY sa.artist_id, sa.scrape_date
                ORDER BY sa.scraped_at DESC NULLS LAST
              ) AS rn
            FROM spotify_artists sa, bounds b
            WHERE sa.scrape_date >  (b.max_d - %s::int)
              AND sa.scrape_date <= b.max_d
        )
        SELECT r.artist_id, a.name, r.scrape_date, r.monthly_listeners
        FROM ranked r
        JOIN artists a ON a.id = r.artist_id
        WHERE r.rn = 1 AND r.monthly_listeners IS NOT NULL
    """
    rows = _run_query(query, (days,))
    if not rows:
        return pd.DataFrame(columns=["artist_id", "name", "scrape_date", "monthly_listeners"])
    df = pd.DataFrame(rows)
    df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
    df["monthly_listeners"] = pd.to_numeric(df["monthly_listeners"], errors="coerce")
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _load_itunes_artist_series(days: int) -> pd.DataFrame:
    """iTunes WW per-artist daily ranking + total points, deduped per day."""
    query = """
        WITH bounds AS (SELECT MAX(scrape_date) AS max_d FROM itunes_artist_rankings),
        ranked AS (
            SELECT
              ir.artist_id,
              ir.scrape_date,
              ir.rank,
              ir.rank_change,
              ir.total_points,
              ROW_NUMBER() OVER (
                PARTITION BY ir.artist_id, ir.scrape_date
                ORDER BY ir.scraped_at DESC NULLS LAST
              ) AS rn
            FROM itunes_artist_rankings ir, bounds b
            WHERE ir.scrape_date >  (b.max_d - %s::int)
              AND ir.scrape_date <= b.max_d
        )
        SELECT r.artist_id, a.name, r.scrape_date, r.rank, r.rank_change, r.total_points
        FROM ranked r
        JOIN artists a ON a.id = r.artist_id
        WHERE r.rn = 1
    """
    rows = _run_query(query, (days,))
    if not rows:
        return pd.DataFrame(columns=["artist_id", "name", "scrape_date", "rank", "rank_change", "total_points"])
    df = pd.DataFrame(rows)
    df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    df["total_points"] = pd.to_numeric(df["total_points"], errors="coerce")
    return df


# ───────────────────────── computation ──────────────────────────

def _series(values_by_date: dict[date, Any], dates: list[date]) -> list[Any]:
    return [values_by_date.get(d) if values_by_date.get(d) is not None else 0 for d in dates]


def _series_or_none(values_by_date: dict[date, Any], dates: list[date]) -> list[Any]:
    return [values_by_date.get(d) for d in dates]


def _signal(score: int, momentum: float) -> tuple[str, str]:
    if score >= 70:
        return "STRONG BUY", "sb-buy"
    if score >= 45:
        return "WATCH", "sb-watch"
    if momentum <= -10:
        return "CAUTION", "sb-caution"
    return "WATCH", "sb-watch"


def _build_artist_payloads(
    universe_df: pd.DataFrame,
    sp_artist_df: pd.DataFrame,
    it_artist_df: pd.DataFrame,
    sp_daily_df: pd.DataFrame,
    it_daily_df: pd.DataFrame,
    dates: list[date],
) -> dict[str, dict]:
    """Build per-artist payloads driven by the iTunes-ranked artist universe."""
    out: dict[str, dict] = {}
    if universe_df.empty:
        return out

    # ── Vectorized data prep ──
    # Pivot dataframes instead of doing group-by lookups in a loop for massive speed gains
    ml_pivot = sp_artist_df.pivot_table(index='name', columns='scrape_date', values='monthly_listeners', aggfunc='last').reindex(columns=dates) if not sp_artist_df.empty else pd.DataFrame(index=[], columns=dates)
    
    it_pts_pivot = it_artist_df.pivot_table(index='name', columns='scrape_date', values='total_points', aggfunc='last').reindex(columns=dates) if not it_artist_df.empty else pd.DataFrame(index=[], columns=dates)
    it_rank_pivot = it_artist_df.pivot_table(index='name', columns='scrape_date', values='rank', aggfunc='last').reindex(columns=dates) if not it_artist_df.empty else pd.DataFrame(index=[], columns=dates)
    it_rank_change_pivot = it_artist_df.pivot_table(index='name', columns='scrape_date', values='rank_change', aggfunc='last').reindex(columns=dates) if not it_artist_df.empty else pd.DataFrame(index=[], columns=dates)

    # Spotify chart presence (top tracks, label, best chart rank) is matched by display name.
    if not sp_daily_df.empty:
        sp_daily_by_artist = {n: g for n, g in sp_daily_df.groupby("artist")}
    else:
        sp_daily_by_artist = {}

    for _, urow in universe_df.iterrows():
        artist = urow["name"]
        if not artist:
            continue

        # ── Spotify monthly_listeners trajectory ──
        if artist in ml_pivot.index:
            ml_series_raw = [int(v) if pd.notna(v) else None for v in ml_pivot.loc[artist]]
        else:
            ml_series_raw = [None] * len(dates)

        # Drop scraper-format outliers: any point < 25% of the series max is likely a metric discontinuity
        peak_ml_raw = max([v for v in ml_series_raw if v is not None] or [0])
        threshold = peak_ml_raw * 0.25 if peak_ml_raw else 0
        ml_series = [v if (v is not None and v >= threshold) else None for v in ml_series_raw]
        ml_clean = [v for v in ml_series if v is not None and v > 0]
        peak_ml = max(ml_clean) if ml_clean else 0
        first_ml = ml_clean[0] if ml_clean else 0
        last_ml = ml_clean[-1] if ml_clean else 0
        momentum = ((last_ml - first_ml) / first_ml * 100) if first_ml else 0.0
        peak_vs_start = ((peak_ml - first_ml) / first_ml * 100) if first_ml else 0.0

        # ── iTunes WW per-artist trajectory ──
        if artist in it_pts_pivot.index:
            it_scores = [int(v) if pd.notna(v) else 0 for v in it_pts_pivot.loc[artist]]
            it_ranks = [int(v) if pd.notna(v) else None for v in it_rank_pivot.loc[artist]]
            # For best_it_date logic
            it_pts_row = it_pts_pivot.loc[artist].dropna()
            best_it_date = it_pts_row.idxmax() if not it_pts_row.empty else None
        else:
            it_scores = [0] * len(dates)
            it_ranks = [None] * len(dates)
            best_it_date = None

        is_new_champion = False
        if artist in it_rank_change_pivot.index:
            rc_series = it_rank_change_pivot.loc[artist].dropna()
            if not rc_series.empty and rc_series.iloc[-1] == "NEW":
                is_new_champion = True

        ranks_clean = [r for r in it_ranks if r is not None]
        best_it_rank = min(ranks_clean) if ranks_clean else None
        best_it_score = max([s for s in it_scores if s > 0], default=0)

        # ── Spotify chart presence (top tracks / label / best chart rank) ──
        sp_d = sp_daily_by_artist.get(artist)
        if sp_d is not None and not sp_d.empty:
            best_sp_rank = int(sp_d["rank"].min()) if sp_d["rank"].notna().any() else None
            best_sp_track = sp_d.loc[sp_d["rank"].idxmin(), "title"] if best_sp_rank is not None else "—"
            track_count = int(sp_d["title"].nunique())
            label_series = sp_d["label"].dropna()
            label = label_series.mode().iat[0] if not label_series.empty else "INDEPENDENT"
            track_agg = (
                sp_d.groupby("title")
                .agg(streams=("metric", "sum"), rank=("rank", "min"), days=("date", "nunique"))
                .reset_index()
                .sort_values("streams", ascending=False)
                .head(5)
            )
            tracks = [
                {
                    "name": row["title"],
                    "streams": int(row["streams"] or 0),
                    "rank": int(row["rank"]) if pd.notna(row["rank"]) else None,
                    "days": int(row["days"]),
                }
                for _, row in track_agg.iterrows()
            ]
        else:
            best_sp_rank = None
            best_sp_track = "—"
            track_count = 0
            label = "INDEPENDENT"
            tracks = []
        label_upper = (str(label) or "INDEPENDENT").upper()

        # ── A&R Business Acquisition Score (5 Pillars Approximation) ──
        # Reach (25%)
        sp_score = max(0, 10 - int((best_sp_rank or 200) / 10))
        it_score = max(0, 10 - int((best_it_rank or 200) / 10))
        tr_score = min(5, track_count * 2)
        reach = min(25, sp_score + it_score + tr_score)
        
        # Consistency (25%) & Momentum (25%) approximated for Python payload
        momentum_score = max(0, min(25, int(momentum * 0.5 + 10)))
        consistency = min(25, 10 + min(15, track_count * 3))
        
        # Longevity (15%)
        longevity = min(15, int(track_count * 3)) if tracks else 0
        
        # Commercial Depth (10%)
        depth = min(10, (3 if best_sp_rank and best_sp_rank <= 10 else 0) + (3 if best_it_rank and best_it_rank <= 10 else 0) + min(4, track_count))
        
        acq_score = min(100, max(0, reach + consistency + momentum_score + longevity + depth))
        signal_text, signal_class = _signal(acq_score, momentum)

        # ── Five signals ──
        signals: list[dict[str, str]] = []
        if peak_ml >= 1_000_000:
            signals.append({
                "icon": "🎧",
                "title": f"{_fmt_n(peak_ml)} monthly listeners",
                "desc": f"Peak Spotify monthly listeners across the {len(dates)}-day window — confirmed audience scale.",
            })
        if best_it_rank is not None and best_it_rank <= 50:
            signals.append({
                "icon": "🌍",
                "title": f"iTunes WW top-{best_it_rank}",
                "desc": f"Peak iTunes worldwide score {_fmt_n(best_it_score)} — strong cross-platform commercial signal.",
            })
        if track_count >= 2:
            signals.append({
                "icon": "🔥",
                "title": f"{track_count} tracks charting on Spotify Global",
                "desc": "Multiple simultaneous chart placements — broad catalogue activation.",
            })
        elif track_count == 1:
            signals.append({
                "icon": "🎵",
                "title": f"{best_sp_track} on Spotify Global",
                "desc": f"Single-track chart play at #{best_sp_rank} — focused momentum.",
            })
        if momentum >= 5:
            signals.append({
                "icon": "📈",
                "title": f"+{momentum:.1f}% monthly-listener growth",
                "desc": f"Listeners moved from {_fmt_n(first_ml)} to {_fmt_n(last_ml)} across the window.",
            })
        elif momentum <= -5:
            signals.append({
                "icon": "📉",
                "title": f"{momentum:.1f}% listener decline",
                "desc": f"Listeners fell from {_fmt_n(first_ml)} to {_fmt_n(last_ml)} — cooldown phase.",
            })
        if best_sp_rank is not None and best_sp_rank <= 10:
            signals.append({
                "icon": "🏆",
                "title": f"Top-10 Spotify Global · {best_sp_rank}",
                "desc": f"{best_sp_track} reached {best_sp_rank} on Spotify Global during the window.",
            })
        if not signals:
            signals.append({
                "icon": "💡",
                "title": "Tracked artist · monitoring",
                "desc": "Limited movement signals in the current window — continue monitoring.",
            })
        signals = signals[:5]

        out[artist] = {
            "avatar": _initials(artist),
            "color": _color_for(artist),
            "label": label_upper,
            "signal": signal_text,
            "signalClass": signal_class,
            "quote": _build_quote(artist, track_count, momentum, best_sp_rank, best_sp_track, best_it_rank, peak_ml),
            "spStreams": [v if v is not None else 0 for v in ml_series],
            "originalSpStreams": [v if v is not None else 0 for v in ml_series],
            "itScores": it_scores,
            "originalItScores": it_scores,
            "itRanks": it_ranks,
            "originalItRanks": it_ranks,
            "bestSpRank": f"{best_sp_rank}" if best_sp_rank else "—",
            "bestSpSub": (best_sp_track[:36] if best_sp_rank else "Not in Top 200"),
            "peakStreams": _fmt_n(peak_ml),
            "peakStreamsSub": "Peak Spotify listeners",
            "peakStreamsVal": peak_ml,
            "trackCount": str(track_count),
            "trackCountSub": "Simultaneous tracks",
            "bestItunes": str(best_it_rank) if best_it_rank else "—",
            "itunesSub": (
                f"Score {_fmt_n(best_it_score)} · {best_it_date.strftime('%b %d')}"
                if best_it_date else "Not ranked iTunes WW"
            ),
            "momentum": round(momentum, 1),
            "acqScore": int(acq_score),
            "tracks": tracks,
            "signals": signals,
            "isNewChampion": is_new_champion,
        }

    return out


def _build_quote(artist: str, tracks: int, momentum: float, best_sp: int | None, best_track: str, best_it: int | None, peak_ml: int = 0) -> str:
    pieces: list[str] = []
    if peak_ml >= 10_000_000:
        pieces.append(f"{_fmt_n(peak_ml)} Spotify monthly listeners at peak")
    if best_it is not None and best_it <= 10:
        pieces.append(f"iTunes WW {best_it}")
    elif best_it is not None and best_it <= 50:
        pieces.append(f"iTunes WW top-{best_it}")
    if best_sp is not None and best_sp <= 10:
        pieces.append(f"{best_track} at {best_sp} on Spotify Global")
    elif best_sp is not None:
        pieces.append(f"Best Spotify Global rank {best_sp}")
    if tracks >= 3:
        pieces.append(f"{tracks} simultaneous global tracks")
    if momentum >= 10:
        pieces.append(f"+{momentum:.1f}% listener momentum")
    elif momentum <= -10:
        pieces.append(f"{momentum:.1f}% listener decline")
    if not pieces:
        return f"{artist} ranked on iTunes WW with steady cross-platform presence."
    return ". ".join(pieces) + "."


def _fmt_n(n: float | int | None) -> str:
    if n is None or n == 0:
        return "—"
    a = abs(n)
    if a >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if a >= 1_000:
        return f"{n/1_000:.0f}K"
    return f"{int(n)}"


# ───────────────────────── render ──────────────────────────

def render_acquisition() -> None:
    st.markdown(
      "<div style='font-size: 0.92rem; color: var(--t2); margin: 0 0 14px; line-height: 1.5; font-weight: 500;'>"
      "🎤 Artist-level acquisition recommendations driven by peak Spotify monthly listeners, iTunes Worldwide performance, "
      "and recent audience momentum."
      "</div>",
      unsafe_allow_html=True,
    )

    period_days = 30

    sp_df = _load_daily("spotify_daily", "global", 30)
    it_df = _load_daily("itunes_daily", "ww", 30)
    universe_df = _load_artist_universe(30)
    sp_artist_df = _load_spotify_artist_series(30)
    it_artist_df = _load_itunes_artist_series(30)

    if universe_df.empty:
      st.warning("No iTunes artist rankings available — cannot build acquisition universe.")
      return

    # X-axis dates = union of distinct scrape_dates across the per-artist series
    date_set = set()
    if not sp_artist_df.empty:
      date_set.update(sp_artist_df["scrape_date"].unique())
    if not it_artist_df.empty:
      date_set.update(it_artist_df["scrape_date"].unique())
    if not date_set and not sp_df.empty:
      date_set.update(sp_df["date"].unique())
    dates = sorted(date_set)
    if not dates:
      st.warning("No dates found in window.")
      return

    artist_data = get_processed_artist_payloads(universe_df, sp_artist_df, it_artist_df, sp_df, it_df, dates)
    if not artist_data:
      st.warning("No artist signals could be computed.")
      return

    # Leaderboard sorted by acquisition score
    leaderboard = sorted(
        [
            {
                "n": name,
                "score": d["acqScore"],
                "momentum": (f"+{d['momentum']}%" if d["momentum"] >= 0 else f"{d['momentum']}%"),
                "signal": "BUY" if "BUY" in d["signal"] else ("CAUTION" if "CAUT" in d["signal"] else "WATCH"),
            }
            for name, d in artist_data.items()
        ],
        key=lambda r: r["score"],
        reverse=True,
    )

    # Momentum chart data — top 20 by abs momentum
    momentum_data = sorted(
        [{"n": name, "m": d["momentum"]} for name, d in artist_data.items()],
        key=lambda r: r["m"],
        reverse=True,
    )[:20]


    date_labels = [d.strftime("%b %d") for d in dates]
    date_range = f"{dates[0].strftime('%b %d')} - {dates[-1].strftime('%b %d, %Y')}" if dates else "Current window"

    # Default selected = top of leaderboard
    default_artist = leaderboard[0]["n"] if leaderboard else next(iter(artist_data))
    strong_buy_count = sum(1 for d in artist_data.values() if "BUY" in d["signal"])
    caution_count = sum(1 for d in artist_data.values() if "CAUT" in d["signal"])
    cross_platform_count = sum(
        1
        for d in artist_data.values()
        if d["bestSpRank"] != "—" and d["bestItunes"] != "—"
    )
    top_score = leaderboard[0] if leaderboard else {"n": "—", "score": 0}
    top_momentum = max(
        ({"n": name, "m": d["momentum"]} for name, d in artist_data.items()),
        key=lambda row: row["m"],
        default={"n": "—", "m": 0},
    )

    payload = {
        "dates": date_labels,
        "artists": artist_data,
        "leaderboard": leaderboard,
        "momentum": momentum_data,
        "defaultArtist": default_artist,
        "allArtists": list(artist_data.keys()),
        "maxWindowDays": 30,
        "summary": {
            "dateRange": date_range,
            "artistCount": len(artist_data),
            "strongBuyCount": strong_buy_count,
            "watchCount": max(0, len(artist_data) - strong_buy_count - caution_count),
            "cautionCount": caution_count,
            "crossPlatformCount": cross_platform_count,
            "topScoreArtist": top_score["n"],
            "topScore": top_score["score"],
            "topMomentumArtist": top_momentum["n"],
            "topMomentum": top_momentum["m"],
        },
    }

    html = _build_html_v2(payload, dark_mode=st.session_state.get("dark_mode", False))
    st_components.html(html, height=920, scrolling=True)


# ───────────────────────── HTML ──────────────────────────

def _build_html(payload: dict, dark_mode: bool = False) -> str:
    data_json = json.dumps(payload, default=str)
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    return """
  <!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
*{box-sizing:border-box;margin:0;padding:0}
__THEME__
body{background:var(--bg);font-family:'Inter',system-ui,sans-serif;color:var(--t1);font-size:16px;line-height:1.55}
.hdr{background:linear-gradient(180deg,#1a2235 0%,var(--bg2) 100%);border-bottom:1px solid var(--border);padding:20px 24px 16px;display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:14px}
.brand{font-size:13px;color:var(--t3);letter-spacing:1.4px;text-transform:uppercase;display:flex;align-items:center;gap:8px;margin-bottom:6px;font-weight:700}
.live-dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:blink 2s infinite;flex-shrink:0}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
.dash-title{font-size:28px;font-weight:800;letter-spacing:-.5px;color:var(--t1)}
.dash-sub{font-size:14px;color:var(--t2);letter-spacing:.3px;margin-top:4px;font-weight:600}
.fy-pill{font-size:10px;color:var(--t2);background:var(--bg3);border:1px solid var(--border2);padding:5px 12px;border-radius:20px;font-weight:500;letter-spacing:.3px}

.selector-bar{background:var(--bg2);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;position:relative;z-index:50}
.sel-label{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.8px;font-weight:700;white-space:nowrap}
.dd-wrap{position:relative;flex:1;max-width:420px}
.dd-trigger{width:100%;display:flex;align-items:center;gap:10px;padding:9px 14px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;cursor:pointer;color:var(--t1);font-size:13px;font-weight:500;transition:.15s}
.dd-trigger:hover{border-color:var(--blue);background:var(--bg4)}
.dd-trigger.open{border-color:var(--blue);box-shadow:0 0 0 3px rgba(96,165,250,.15)}
.dd-av{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0}
.dd-current{flex:1;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dd-arrow{font-size:11px;color:var(--t3);transition:transform .15s}
.dd-trigger.open .dd-arrow{transform:rotate(180deg)}
.dd-panel{position:absolute;top:calc(100% + 6px);left:0;right:0;background:var(--bg2);border:1px solid var(--border2);border-radius:10px;box-shadow:0 12px 40px rgba(0,0,0,.55);max-height:380px;display:none;flex-direction:column;overflow:hidden;z-index:100}
.dd-panel.open{display:flex}
.dd-search-wrap{padding:10px;border-bottom:1px solid var(--border)}
.dd-search{width:100%;padding:8px 12px;background:var(--bg3);border:1px solid var(--border2);border-radius:6px;color:var(--t1);font-size:13px;outline:none}
.dd-search:focus{border-color:var(--blue)}
.dd-list{flex:1;overflow-y:auto;padding:4px 0}
.dd-opt{display:flex;align-items:center;gap:10px;padding:8px 14px;cursor:pointer;color:var(--t2);font-size:13px;transition:.1s}
.dd-opt:hover{background:var(--bg3);color:var(--t1)}
.dd-opt.on{background:rgba(96,165,250,.12);color:var(--t1);font-weight:600}
.dd-opt-meta{font-size:10px;color:var(--t3);margin-left:auto;font-variant-numeric:tabular-nums}
.dd-empty{padding:18px;text-align:center;color:var(--t3);font-size:12px}

.body{padding:20px 22px;display:flex;flex-direction:column;gap:18px}

.acq-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.25)}
.acq-card.buy{border-top:3px solid var(--green)}
.acq-card.watch{border-top:3px solid var(--blue)}
.acq-card.caution{border-top:3px solid var(--red)}
.acq-header{padding:14px 20px 12px;border-bottom:1px solid var(--border)}
.acq-meta{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px;font-weight:600}
.acq-row{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:14px}
.acq-left{flex:1;min-width:240px}
.acq-id-row{display:flex;align-items:center;gap:12px;margin-bottom:4px}
.acq-avatar{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0}
.acq-name{font-size:22px;font-weight:800;letter-spacing:-.5px;line-height:1.2;color:var(--t1)}
.acq-sublabel{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.7px;margin-top:2px;font-weight:600}
.acq-quote{font-size:14px;color:var(--t2);line-height:1.5;border-left:2px solid var(--border2);padding-left:12px;margin-top:10px}
.signal-badge{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;padding:7px 14px;border-radius:6px;letter-spacing:.5px;text-transform:uppercase;white-space:nowrap}
.sb-buy{background:var(--gd);color:var(--green);border:1px solid rgba(52,211,153,.4)}
.sb-watch{background:var(--bd);color:var(--blue);border:1px solid rgba(96,165,250,.4)}
.sb-caution{background:var(--rd);color:var(--red);border:1px solid rgba(251,113,133,.4)}

.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--border);border-top:1px solid var(--border)}
.stat-cell{background:var(--bg2);padding:12px 18px;transition:.15s}
.stat-cell:hover{background:var(--bg3)}
.stat-lbl{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px;font-weight:800}
.stat-val{font-size:22px;font-weight:800;letter-spacing:-.5px;color:var(--t1);font-variant-numeric:tabular-nums}
.stat-val.g{color:var(--green)}.stat-val.r{color:var(--red)}.stat-val.b{color:var(--blue)}.stat-val.p{color:var(--purple)}.stat-val.a{color:var(--amber)}
.stat-sub{font-size:11px;color:var(--t2);margin-top:5px;font-weight:500}
.stat-sub.g{color:var(--green)}.stat-sub.r{color:var(--red)}

.charts-row{display:grid;grid-template-columns:1.8fr 1fr;gap:16px}
.chart-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
.chart-ttl{font-size:12px;font-weight:600;color:var(--t2);letter-spacing:.4px;margin-bottom:14px;text-transform:uppercase;padding-bottom:10px;border-bottom:1px solid var(--border)}
.cw{position:relative;width:100%}

.track-list{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
.trk-hdr{display:grid;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2);margin-bottom:4px}
.trk-hdr span{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;font-weight:600}
.trk{display:grid;gap:8px;padding:11px 0;border-bottom:1px solid var(--border);align-items:center}
.trk:last-child{border-bottom:none}
.trk-rank{font-size:12px;color:var(--t3);text-align:center;font-weight:600}
.trk-name{font-size:13px;font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-.1px}
.trk-val{font-size:13px;color:var(--t2);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:500}

.signals-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
.sig-row{display:flex;align-items:flex-start;gap:14px;padding:12px 0;border-bottom:1px solid var(--border)}
.sig-row:last-child{border-bottom:none}
.sig-icon{font-size:20px;flex-shrink:0;margin-top:1px}
.sig-title{font-size:13px;font-weight:600;color:var(--t1);margin-bottom:3px;letter-spacing:-.1px}
.sig-desc{font-size:12px;color:var(--t2);line-height:1.55}

.leader-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px;max-height:560px;overflow-y:auto}
.leader-row{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid var(--border);cursor:pointer;transition:.12s;border-radius:6px}
.leader-row:last-child{border-bottom:none}
.leader-row:hover{background:var(--bg3);margin:0 -8px;padding:9px 8px}
.leader-row.on{background:rgba(96,165,250,.1);margin:0 -8px;padding:9px 8px}
.leader-rank{font-size:12px;color:var(--t3);min-width:22px;text-align:center;font-weight:700}
.leader-av{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0}
.leader-name{flex:1;font-size:13px;font-weight:600;color:var(--t1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.score-bar-bg{height:4px;background:var(--bg4);border-radius:3px;margin-top:4px;overflow:hidden}
.score-bar-fg{height:4px;border-radius:3px;transition:width .4s}

.hero-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:stretch}
.hero-row > *{min-width:0}
.stack-col{display:flex;flex-direction:column;gap:16px;min-width:0;height:100%}
.stack-col .track-list,
.stack-col .signals-card{flex:1 1 0;min-height:0}
.stack-col .track-list{display:flex;flex-direction:column}
.stack-col .signals-card{display:flex;flex-direction:column}

@media (max-width: 1100px){
  .hero-row{grid-template-columns:1fr}
}

.sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border)}
.sh-l{font-size:14px;font-weight:600;color:var(--t1);letter-spacing:-.2px}
.sh-r{font-size:11px;color:var(--t2);background:var(--bg3);padding:5px 12px;border-radius:5px;border:1px solid var(--border2);font-weight:500}

::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:var(--bg2)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:var(--t4)}
</style></head><body>

<div style="background:var(--bg2); border-bottom:1px solid var(--border); padding: 16px 28px;">
  <div style="max-width:1200px;margin:0 auto;">
    <details style="cursor:pointer;">
      <summary style="font-size:13px;font-weight:700;color:var(--t1);outline:none;user-select:none;display:flex;align-items:center;gap:8px;">
        <span style="color:var(--blue);font-size:15px;">ℹ️</span> How is the Acquisition Score calculated?
      </summary>
      <div style="font-size:13px;color:var(--t2);line-height:1.6;margin-top:12px;padding-left:18px;border-left:2px solid var(--border2);margin-left:6px;">
        Every artist is graded on a 0-100 scale using five key pillars to determine their true business value:<br><br>
        <b>Reach (25%)</b> — How big is their audience?<br>
        <b>Consistency (25%)</b> — Do they stick around?<br>
        <b>Momentum (25%)</b> — Are they gaining traction? <br>
        <b>Longevity (15%)</b> — Do they have staying power?<br>
        <b>Commercial Depth (10%)</b> — Do they have a deep catalog?<br>
      </div>
    </details>
  </div>
</div>

<div class="selector-bar">
  <span class="sel-label">Select artist</span>
  <div class="dd-wrap" id="dd-wrap">
    <div class="dd-trigger" id="dd-trigger">
      <div class="dd-av" id="dd-av">--</div>
      <div class="dd-current" id="dd-current">—</div>
      <span class="dd-arrow">▼</span>
    </div>
    <div class="dd-panel" id="dd-panel">
      <div class="dd-search-wrap"><input class="dd-search" id="dd-search" placeholder="Search artists..." autocomplete="off"></div>
      <div class="dd-list" id="dd-list"></div>
    </div>
  </div>
  <span class="sel-label" style="margin-left:auto;color:var(--t2)" id="dd-count"></span>
</div>

<div class="body">

  <div class="hero-row">
    <div class="acq-card" id="acq-card">
      <div class="acq-header">
        <div class="acq-meta" style="display:flex;justify-content:space-between">
          <span>Acquisition recommendation</span>
          <span id="d-label-top" style="color:var(--t2);text-transform:none"></span>
        </div>
        <div class="acq-row">
          <div class="acq-left">
            <div class="acq-id-row">
              <div class="acq-avatar" id="d-av"></div>
              <div>
                <div class="acq-name" id="d-name"></div>
                <div class="acq-sublabel" id="d-label"></div>
              </div>
              <div style="margin-left:auto; display:flex; align-items:center; gap:16px;">
                <div style="text-align:right">
                  <div style="font-size:10px;color:var(--t3);text-transform:uppercase;font-weight:700;letter-spacing:0.5px">ACQ SCORE</div>
                  <div style="font-size:24px;font-weight:800;color:var(--t1);line-height:1" id="d-score">--</div>
                </div>
                <div class="signal-badge" id="d-signal"></div>
              </div>
            </div>
            <div class="acq-quote" id="d-quote"></div>
          </div>
        </div>
      </div>
      <div class="stat-grid" style="grid-template-columns: repeat(3, 1fr);">
        <div class="stat-cell">
          <div class="stat-lbl">START LISTENERS</div>
          <div class="stat-val" id="d-l1-v">—</div>
          <div class="stat-sub" id="d-l1-s"></div>
        </div>
        <div class="stat-cell">
          <div class="stat-lbl">CURRENT LISTENERS</div>
          <div class="stat-val" id="d-l2-v">—</div>
          <div class="stat-sub" id="d-l2-s"></div>
        </div>
        <div class="stat-cell">
          <div class="stat-lbl">LISTENER CHANGE</div>
          <div class="stat-val" id="d-l3-v">—</div>
          <div class="stat-sub" id="d-l3-s"></div>
        </div>
        <div class="stat-cell">
          <div class="stat-lbl">START RANK</div>
          <div class="stat-val" id="d-s1-v">—</div>
          <div class="stat-sub" id="d-s1-s"></div>
        </div>
        <div class="stat-cell">
          <div class="stat-lbl">CURRENT RANK</div>
          <div class="stat-val" id="d-s2-v">—</div>
          <div class="stat-sub" id="d-s2-s"></div>
        </div>
        <div class="stat-cell">
          <div class="stat-lbl">RANK CHANGE</div>
          <div class="stat-val" id="d-s3-v">—</div>
          <div class="stat-sub" id="d-s3-s"></div>
        </div>
      </div>
      <div style="padding:12px 20px">
          <div class="chart-ttl" style="margin-bottom:8px">iTunes WW Rank trajectory · last window</div>
          <div class="cw" style="height:150px" id="chart-ml"></div>
      </div>
      <div style="padding:12px 20px; border-top: 1px solid var(--border);">
          <div class="chart-ttl" style="margin-bottom:8px">Spotify Daily Listener Gain/Loss (%) · last window</div>
          <div class="cw" style="height:150px" id="chart-sp-listeners"></div>
      </div>
    </div>

    <div class="stack-col">
      <div class="track-list">
        <div class="sh"><span class="sh-l" id="tracks-title">Top tracks · Spotify Global</span><span class="sh-r">By total streams</span></div>
        <div class="trk-hdr" style="grid-template-columns:30px 1fr 80px 64px 50px">
          <span></span><span>Track</span><span style="text-align:right">Streams</span><span style="text-align:right">Best Rank</span><span style="text-align:right">Days</span>
        </div>
        <div id="tracks-list"></div>
      </div>

      <div class="signals-card">
        <div class="sh"><span class="sh-l">Why this artist · signals</span></div>
        <div id="five-signals"></div>
      </div>
    </div>
  </div>



</div>

<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<script>
const PAYLOAD = __PAYLOAD__;
const DATES = PAYLOAD.dates;
const ARTISTS = PAYLOAD.artists;
const ALL_ARTISTS = PAYLOAD.allArtists;
let LEADERBOARD = PAYLOAD.leaderboard;
const MOMENTUM_DATA = PAYLOAD.momentum;

let currentTimeWindowDays = 30;

document.getElementById('dd-count').textContent = ALL_ARTISTS.length + ' artists tracked';

let currentArtist=null;
function fmtN(n){if(!n)return'—';const a=Math.abs(n);if(a>=1e6)return(n/1e6).toFixed(1)+'M';if(a>=1e3)return(n/1e3).toFixed(0)+'K';return n.toString();}

function _jsAcqScore(bestSpRank, bestItRank, trackCount, mlArray, itScoresArray, tracks) {
    const spScore = Math.max(0, 10 - Math.floor((bestSpRank || 200) / 10));
    const itScore = Math.max(0, 10 - Math.floor((bestItRank || 200) / 10));
    const trScore = Math.min(5, trackCount * 2);
    const reach = Math.min(25, spScore + itScore + trScore);
    
    let daysPresent = 0, streak = 0, maxStreak = 0;
    for(let i=0; i<itScoresArray.length; i++){
        if(itScoresArray[i] > 0) {
            daysPresent++; streak++;
            if(streak > maxStreak) maxStreak = streak;
        } else { streak = 0; }
    }
    const presenceScore = Math.min(10, daysPresent);
    const streakScore = Math.min(5, maxStreak);
    
    const mlClean = mlArray.filter(v => v > 0);
    let cvScore = 0, momentum = 0;
    if (mlClean.length > 2) {
        let sum = 0; for(let i=0; i<mlClean.length; i++) sum += mlClean[i];
        let mean = sum / mlClean.length;
        let variance = 0; for(let i=0; i<mlClean.length; i++) variance += Math.pow(mlClean[i] - mean, 2);
        let std = Math.sqrt(variance / mlClean.length);
        let cv = mean > 0 ? std / mean : 1;
        cvScore = Math.max(0, 10 - Math.floor(cv * 50));
        
        let n = mlClean.length, sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
        for(let i=0; i<n; i++) { sumX+=i; sumY+=mlClean[i]; sumXY+=i*mlClean[i]; sumXX+=i*i; }
        let slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
        let normSlope = mean > 0 ? (slope / mean) * 100 : 0;
        let slopeScore = Math.max(0, Math.min(15, Math.floor(normSlope * 5 + 5)));
        
        let wow = mlClean[0] > 0 ? (mlClean[mlClean.length-1] / mlClean[0] - 1) * 100 : 0;
        let wowScore = Math.max(0, Math.min(10, Math.floor(wow / 2)));
        momentum = Math.min(25, slopeScore + wowScore);
    }
    const consistency = Math.min(25, presenceScore + cvScore + streakScore);
    
    let longevity = 0;
    if (tracks && tracks.length > 0) {
        let sumDays = 0, maxDays = 0;
        for(let i=0; i<tracks.length; i++) {
            let d = tracks[i].days || 0;
            sumDays += d; if(d > maxDays) maxDays = d;
        }
        let avgDays = sumDays / tracks.length;
        longevity = Math.min(15, Math.floor(avgDays / 7) + Math.floor(maxDays / 14));
    }
    
    const depth = Math.min(10, ((bestSpRank && bestSpRank <= 10)?3:0) + ((bestItRank && bestItRank <= 10)?3:0) + Math.min(4, trackCount));
    return Math.min(100, Math.max(0, Math.round(reach + consistency + momentum + longevity + depth)));
}
function _jsSignal(score, momentum) {
    if (score >= 70) return ["STRONG BUY", "sb-buy"];
    if (score >= 45) return ["WATCH", "sb-watch"];
    if (momentum <= -10) return ["CAUTION", "sb-caution"];
    return ["WATCH", "sb-watch"];
}

function recalculateAll() {
    const startIndex = Math.max(0, DATES.length - currentTimeWindowDays);
    
    for (const name in ARTISTS) {
        const a = ARTISTS[name];
        const ml = (a.originalSpStreams || a.spStreams).slice(startIndex);
        const itS = (a.originalItScores || a.itScores).slice(startIndex);
        const itR = (a.originalItRanks || a.itRanks).slice(startIndex);
        
        const mlClean = ml.filter(v => v > 0);
        const peakMl = mlClean.length ? Math.max(...mlClean) : 0;
        const firstMl = mlClean.length ? mlClean[0] : null;
        const lastMl = mlClean.length ? mlClean[mlClean.length - 1] : null;
        const mom = firstMl ? ((lastMl - firstMl) / firstMl * 100) : 0.0;
        
        let firstMlD = null, lastMlD = null;
        for(let i=0; i<ml.length; i++) {
            if(ml[i] > 0) {
                if(!firstMlD) firstMlD = DATES[startIndex+i];
                lastMlD = DATES[startIndex+i];
            }
        }
        
        const ranksClean = itR.filter(r => r !== null && r > 0);
        const bestIt = ranksClean.length ? Math.min(...ranksClean) : null;
        
        let firstR = null, firstD = null;
        let lastR = null, lastD = null;
        for(let i=0; i<itR.length; i++) {
            if(itR[i]) {
                if(firstR === null) { firstR = itR[i]; firstD = DATES[startIndex+i]; }
                lastR = itR[i]; lastD = DATES[startIndex+i];
            }
        }
        
        let rankChangeStr = '—';
        let rankChangeSub = '';
        if(firstR !== null && lastR !== null && firstR !== lastR) {
            let diff = firstR - lastR;
            rankChangeStr = (diff > 0 ? '+' : '') + diff;
            rankChangeSub = diff > 0 ? 'gained positions' : 'lost positions';
            a.rankChangeColor = diff > 0 ? 'g' : 'r';
        } else if (firstR === lastR && firstR !== null) {
            rankChangeStr = '0';
            rankChangeSub = 'no change';
            a.rankChangeColor = '';
        } else {
            a.rankChangeColor = '';
        }
        
        a.startRank = firstR ? '#' + firstR : '—';
        a.startRankDate = firstD || 'unranked';
        a.currentRank = lastR ? '#' + lastR : '—';
        a.currentRankDate = lastD || 'unranked';
        a.rankChangeStr = rankChangeStr;
        a.rankChangeSub = rankChangeSub;

        a.spListenersArray = ml.map(v => v > 0 ? v : null);
        
        a.startListStr = firstMl !== null ? fmtN(firstMl) : '—';
        a.startListDate = firstMlD || 'no data';
        a.currListStr = lastMl !== null ? fmtN(lastMl) : '—';
        a.currListDate = lastMlD || 'no data';
        
        if (firstMl !== null && lastMl !== null) {
            let diff = lastMl - firstMl;
            let momStr = mom > 0 ? '+' + mom.toFixed(1) + '%' : mom.toFixed(1) + '%';
            a.listChangeStr = (diff > 0 ? '+' : '') + fmtN(diff);
            a.listChangeSub = momStr + ' momentum';
            a.listChangeColor = diff > 0 ? 'g' : (diff < 0 ? 'r' : '');
            if(diff === 0) { a.listChangeStr = '0'; a.listChangeSub = 'no change'; a.listChangeColor = ''; }
        } else {
            a.listChangeStr = '—';
            a.listChangeSub = '';
            a.listChangeColor = '';
        }

        const bestSp = (a.bestSpRank && a.bestSpRank !== '—') ? parseInt(a.bestSpRank) : null;
        const score = _jsAcqScore(bestSp, bestIt, parseInt(a.trackCount), ml, itS, a.tracks);
        const [sigTxt, sigCls] = _jsSignal(score, mom);
        
        a.acqScore = score;
        a.momentum = Math.round(mom * 10) / 10;
        a.signal = sigTxt;
        a.signalClass = sigCls;
        a.spStreams = ml;
        a.itScores = itS;
        a.itRanks = itR;
        a.peakStreamsVal = peakMl;
        a.firstMlVal = firstMl;
    }

    LEADERBOARD = ALL_ARTISTS.map(name => {
        const a = ARTISTS[name];
        return {
            n: name,
            score: a.acqScore,
            momentum: (a.momentum >= 0 ? '+' : '') + a.momentum + '%',
            signal: a.signal.includes('BUY') ? 'BUY' : (a.signal.includes('CAUT') ? 'CAUTION' : 'WATCH')
        };
    }).sort((a, b) => b.score - a.score);

    renderLeaderboard();
    renderDdList(ddSearch.value);
    if (currentArtist) selectArtist(currentArtist);
}

function avInitials(n){return n.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();}
function avColor(name){return ARTISTS[name]?.color||'#94a3b8';}

const PLOTLY_LAYOUT_BASE = {
  paper_bgcolor:'rgba(0,0,0,0)',
  plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Inter,system-ui,sans-serif',color:'#000000',size:11},
  margin:{l:48,r:18,t:10,b:58},
  hoverlabel:{bgcolor:getComputedStyle(document.documentElement).getPropertyValue('--bg2').trim()||'#FFFFFF',bordercolor:getComputedStyle(document.documentElement).getPropertyValue('--border2').trim()||'#3a4661',font:{color:'#000000',size:12}},
  showlegend:false,
  xaxis:{gridcolor:'rgba(255,255,255,0.05)',zerolinecolor:'rgba(255,255,255,0.08)',tickfont:{color:'#000000'},linecolor:'rgba(255,255,255,0.08)'},
  yaxis:{gridcolor:'rgba(255,255,255,0.05)',zerolinecolor:'rgba(255,255,255,0.08)',tickfont:{color:'#000000'},linecolor:'rgba(255,255,255,0.08)'}
};
const PLOTLY_CFG = {displaylogo:false,displayModeBar:false,responsive:true};
function layoutClone(extra){
  const base = JSON.parse(JSON.stringify(PLOTLY_LAYOUT_BASE));
  return Object.assign(base, extra||{});
}
function buildDateAxis(labels){
  const count = labels.length;
  if(!count){
    return {tickmode:'array', tickvals:[], ticktext:[]};
  }

  const targetTicks = count <= 7 ? 7 : count <= 14 ? 8 : 9;
  const step = Math.max(1, Math.ceil(count / targetTicks));
  const tickvals = [];
  const ticktext = [];

  for(let i = 0; i < count; i += step){
    const label = labels[i];
    tickvals.push(label);
    ticktext.push(label.replace(' ', '<br>'));
  }

  const last = labels[count - 1];
  if(tickvals[tickvals.length - 1] !== last){
    tickvals.push(last);
    ticktext.push(last.replace(' ', '<br>'));
  }

  return {
    tickmode:'array',
    tickvals,
    ticktext,
    tickangle:0,
    tickfont:{color:'#000000', size:10},
    automargin:true,
  };
}

// ─── Dropdown ────────────────────────────────────────
const ddTrigger = document.getElementById('dd-trigger');
const ddPanel = document.getElementById('dd-panel');
const ddSearch = document.getElementById('dd-search');
const ddList = document.getElementById('dd-list');
const ddAv = document.getElementById('dd-av');
const ddCurrent = document.getElementById('dd-current');

function renderDdList(filter){
  const f = (filter||'').toLowerCase().trim();
  // Sort by acquisition score desc using leaderboard order
  const orderMap = new Map(LEADERBOARD.map((d,i)=>[d.n,i]));
  const sorted = [...ALL_ARTISTS].sort((a,b)=>(orderMap.get(a)??999)-(orderMap.get(b)??999));
  const matches = sorted.filter(a=>!f||a.toLowerCase().includes(f));
  ddList.innerHTML = '';
  if(!matches.length){
    ddList.innerHTML = '<div class="dd-empty">No artists match.</div>';
    return;
  }
  matches.forEach(name=>{
    const data = ARTISTS[name];
    const lb = LEADERBOARD.find(x=>x.n===name);
    const score = lb?lb.score:'';
    const opt = document.createElement('div');
    opt.className = 'dd-opt'+(name===currentArtist?' on':'');
    const col = avColor(name);
    opt.innerHTML = `
      <div class="dd-av" style="background:${col}22;color:${col};border:1px solid ${col}40">${avInitials(name)}</div>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${name}</span>
      <span class="dd-opt-meta">${score}</span>`;
    opt.onclick = ()=>{ selectArtist(name); closeDd(); };
    ddList.appendChild(opt);
  });
}
function openDd(){ ddPanel.classList.add('open'); ddTrigger.classList.add('open'); ddSearch.value=''; renderDdList(''); setTimeout(()=>ddSearch.focus(),0); }
function closeDd(){ ddPanel.classList.remove('open'); ddTrigger.classList.remove('open'); }
ddTrigger.onclick = (e)=>{ e.stopPropagation(); ddPanel.classList.contains('open')?closeDd():openDd(); };
ddSearch.oninput = ()=>renderDdList(ddSearch.value);
document.addEventListener('click',(e)=>{ if(!document.getElementById('dd-wrap').contains(e.target)) closeDd(); });

// ─── Selection ───────────────────────────────────────
function selectArtist(name){
  const d=ARTISTS[name];
  if(!d)return;
  currentArtist = name;

  // Dropdown trigger
  ddCurrent.textContent = name;
  ddAv.textContent = d.avatar;
  ddAv.style.background = d.color+'22';
  ddAv.style.color = d.color;
  ddAv.style.border = `1px solid ${d.color}40`;

  // Acq Card
  const ac = document.getElementById('acq-card');
  ac.className = 'acq-card ' + d.signalClass.replace('sb-','');
  document.getElementById('d-label-top').textContent = currentTimeWindowDays + '-day acquisition signal';
  
  document.getElementById('d-av').textContent = d.avatar;
  document.getElementById('d-av').style.background = d.color+'22';
  document.getElementById('d-av').style.color = d.color;
  
  document.getElementById('d-name').innerHTML = name + (d.isNewChampion ? ' <span style="font-size:10px;background:var(--gd);border:1px solid var(--green);color:var(--green);padding:2px 6px;border-radius:4px;vertical-align:middle;margin-left:8px;font-weight:700;">NEW CHAMPION</span>' : '');
  document.getElementById('d-label').textContent = '';
  
  const dsig = document.getElementById('d-signal');
  dsig.textContent = d.signal;
  dsig.className = 'signal-badge ' + d.signalClass;
  
  document.getElementById('d-score').textContent = d.acqScore;
  
  document.getElementById('d-quote').textContent = d.quote;
  
  document.getElementById('d-l1-v').textContent = d.startListStr;
  document.getElementById('d-l1-s').textContent = d.startListDate;
  document.getElementById('d-l2-v').textContent = d.currListStr;
  document.getElementById('d-l2-s').textContent = d.currListDate;
  const l3 = document.getElementById('d-l3-v');
  l3.textContent = d.listChangeStr;
  l3.className = 'stat-val ' + (d.listChangeColor || '');
  document.getElementById('d-l3-s').textContent = d.listChangeSub;
  
  document.getElementById('d-s1-v').textContent = d.startRank;
  document.getElementById('d-s1-s').textContent = d.startRankDate;
  document.getElementById('d-s2-v').textContent = d.currentRank;
  document.getElementById('d-s2-s').textContent = d.currentRankDate;
  
  const v3 = document.getElementById('d-s3-v');
  v3.textContent = d.rankChangeStr;
  v3.className = 'stat-val ' + (d.rankChangeColor || '');
  
  document.getElementById('d-s3-s').textContent = d.rankChangeSub;
  
  const layout = layoutClone({
    xaxis: buildDateAxis(DATES.slice(Math.max(0, DATES.length - currentTimeWindowDays))),
    yaxis: {autorange: 'reversed', visible: true, title: {text: 'Rank Position', font: {size: 10, color: '#000000'}}},
    margin:{l:50,r:20,t:10,b:30}
  });
  const rankLabels = (d.itRanks || []).map(v => (v && v > 0) ? `#${v}` : '');
  const firstRank = (d.itRanks || []).find(v => v && v > 0);
  const lastRank = [...(d.itRanks || [])].reverse().find(v => v && v > 0);
  const rankDelta = (firstRank && lastRank) ? (firstRank - lastRank) : null;
  const rankDeltaLabel = rankDelta === null ? 'No rank change' : `${rankDelta > 0 ? '+' : ''}${rankDelta} positions`;
  const trace = {
    x: DATES.slice(Math.max(0, DATES.length - currentTimeWindowDays)),
    y: (d.itRanks||[]).map(v=>v>0?v:null),
    type: 'scatter',
    mode: 'lines+markers+text',
    connectgaps: true,
    line: {color: d.color, width: 2, shape:'hv'},
    marker: {size: 6, color: d.color},
    text: rankLabels,
    textposition: 'top center',
    textfont: {size: 10, color: '#000000'},
    hovertemplate: '%{x}<br><b>#%{y} iTunes WW</b><extra></extra>'
  };
  Plotly.newPlot('chart-ml', [trace], {
    ...layout,
    annotations: [{
      xref: 'paper',
      yref: 'paper',
      x: 1,
      y: 1.16,
      xanchor: 'right',
      yanchor: 'top',
      text: rankDeltaLabel,
      showarrow: false,
      font: {size: 11, color: '#000000'}
    }]
  }, PLOTLY_CFG);

  const spListenersArray = d.spListenersArray || [];
  const pctChanges = spListenersArray.map((v, i) => {
      if (i === 0) return null;
      const prev = spListenersArray[i - 1];
      if (v === null || prev === null || prev === 0) return null;
      return ((v - prev) / prev) * 100;
  });
  const colors = pctChanges.map(v => (v === null || v >= 0) ? 'rgba(52, 211, 153, 0.8)' : 'rgba(251, 113, 133, 0.8)');
  const pctLabels = pctChanges.map(v => {
    if (v === null) return '';
    if (v > 0) return `↑ +${v.toFixed(1)}%`;
    if (v < 0) return `↓ ${v.toFixed(1)}%`;
    return `0.0%`;
  });

  const layoutSp = layoutClone({
    xaxis: buildDateAxis(DATES.slice(Math.max(0, DATES.length - currentTimeWindowDays))),
    yaxis: {visible: true, title: {text: '% Change', font: {size: 10, color: '#000000'}}, ticksuffix: '%', zeroline: true},
    margin:{l:60,r:20,t:10,b:36}
  });
  const traceSp = {
    x: DATES.slice(Math.max(0, DATES.length - currentTimeWindowDays)),
    y: pctChanges,
    type: 'bar',
    marker: {color: colors},
    text: pctLabels,
    texttemplate: '%{text}',
    textposition: 'auto',
    textfont: {size: 10, color: '#000000'},
    cliponaxis: false,
    hovertemplate: '%{x}<br><b>%{y:+.1f}%</b><extra></extra>'
  };
  Plotly.newPlot('chart-sp-listeners', [traceSp], layoutSp, PLOTLY_CFG);

  // Tracks
  const tl=document.getElementById('tracks-list');
  tl.innerHTML='';
  document.getElementById('tracks-title').textContent=`Top tracks · ${name} · Spotify Global`;
  const maxStreams = (d.tracks||[]).length ? d.tracks[0].streams : 1;
  (d.tracks||[]).forEach((t,i)=>{
    const pct=Math.max(4,Math.round((t.streams/maxStreams)*100));
    const row=document.createElement('div');
    row.className='trk';
    row.style.gridTemplateColumns='30px 1fr 80px 64px 50px';
    row.innerHTML=`
      <span class="trk-rank">${i+1}</span>
      <div style="min-width:0">
        <div class="trk-name">${t.name}</div>
        <div style="height:4px;background:var(--bg4);border-radius:3px;margin-top:5px">
          <div style="width:${pct}%;height:4px;background:${d.color};border-radius:3px"></div>
        </div>
      </div>
      <span class="trk-val">${fmtN(t.streams)}</span>
      <span class="trk-val">${t.rank?+t.rank:'—'}</span>
      <span class="trk-val">${t.days}d</span>`;
    tl.appendChild(row);
  });

  // Signals
  const sl=document.getElementById('five-signals');
  sl.innerHTML='';
  (d.signals||[]).forEach(s=>{
    const row=document.createElement('div');
    row.className='sig-row';
    row.innerHTML=`<span class="sig-icon">${s.icon}</span><div><div class="sig-title">${s.title}</div><div class="sig-desc">${s.desc}</div></div>`;
    sl.appendChild(row);
  });

  // Highlight leaderboard row
  document.querySelectorAll('.leader-row').forEach(r=>{
    r.classList.toggle('on', r.dataset.artist===name);
  });
}

// ─── Leaderboard ─────────────────────────────────────
function renderLeaderboard() {
const maxScore=(LEADERBOARD[0]?.score)||1;
const lb=document.getElementById('leaderboard');
if (!lb) return;
lb.innerHTML = '';
LEADERBOARD.forEach((d,i)=>{
  const pct=Math.round(d.score/maxScore*100);
  const col=d.signal==='BUY'?'var(--green)':(d.signal==='CAUTION'?'var(--red)':'var(--blue)');
  const av=avInitials(d.n);
  const avCol=avColor(d.n);
  const momNum = parseFloat(d.momentum);
  const row=document.createElement('div');
  row.className='leader-row';
  row.dataset.artist = d.n;
  row.onclick=()=>selectArtist(d.n);
  row.innerHTML=`
    <span class="leader-rank">${i+1}</span>
    <div class="leader-av" style="background:${avCol}22;color:${avCol};border:1px solid ${avCol}40">${av}</div>
    <div style="flex:1;min-width:0">
      <div class="leader-name">${d.n}</div>
      <div class="score-bar-bg"><div class="score-bar-fg" style="width:${pct}%;background:${col}"></div></div>
    </div>
    <div style="text-align:right">
      <div style="font-size:13px;font-weight:700;color:${col};font-variant-numeric:tabular-nums">${d.score}</div>
      <div style="font-size:10px;color:${momNum>=0?'var(--green)':'var(--red)'};font-weight:600">${d.momentum}</div>
    </div>`;
  lb.appendChild(row);
});
}
recalculateAll();
currentArtist = PAYLOAD.defaultArtist;
selectArtist(PAYLOAD.defaultArtist);
window.addEventListener('load',()=>{ try{ selectArtist(PAYLOAD.defaultArtist); }catch(e){console.error(e);} });
</script>
</body></html>
""".replace("__PAYLOAD__", data_json).replace("__THEME__", theme_css)


def _build_html_v2(payload: dict, dark_mode: bool = False) -> str:
    data_json = json.dumps(payload, default=str)
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    return """
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
*{box-sizing:border-box;margin:0;padding:0}
__THEME__
body{background:var(--bg);font-family:Inter,system-ui,sans-serif;color:var(--t1);font-size:12px;line-height:1.35}
.d{padding:8px 12px 16px;max-width:none;margin:0 auto}.top-bar{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px;padding-bottom:16px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px}.brand-icon{width:38px;height:38px;border-radius:8px;background:#085041;color:#E1F5EE;display:flex;align-items:center;justify-content:center;font-weight:800}
.brand-title{font-size:16px;font-weight:700}.brand-sub{font-size:11px;color:var(--t3);margin-top:2px}.top-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.period-pill,.status-live{font-size:11px;font-weight:600;padding:5px 10px;border-radius:20px;border:1px solid var(--border2);color:var(--t2);background:var(--bg2)}
.status-live{background:var(--gd);color:var(--green);border-color:rgba(52,211,153,.28);display:flex;align-items:center;gap:5px}.status-live span{width:6px;height:6px;border-radius:50%;background:var(--green)}
.search-wrap{display:flex;align-items:center;gap:7px;border:1px solid var(--border2);border-radius:8px;padding:6px 10px;background:var(--bg2)}.search-wrap input{border:0;background:transparent;outline:0;font-size:12px;color:var(--t1);width:150px}
.kpi-row{display:grid;grid-template-columns:repeat(6,minmax(118px,1fr));gap:8px;margin-bottom:10px}.kcard{background:var(--bg2);border:1px solid var(--border);border-radius:7px;padding:10px 12px;position:relative;overflow:hidden;cursor:pointer;min-height:86px}
.kcard:hover{border-color:var(--border2)}.kcard-bar{position:absolute;top:0;left:0;width:3px;height:100%}.kcard-label{font-size:10px;color:var(--t2);margin-bottom:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.kcard-val{font-size:22px;font-weight:800;line-height:1}.kcard-sub{font-size:10px;color:var(--t3);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kcard-delta{display:inline-flex;max-width:100%;font-size:10px;font-weight:700;margin-top:6px;padding:2px 7px;border-radius:20px;background:var(--bg3);color:var(--t2);border:1px solid var(--border);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tab-row{display:flex;gap:8px;margin-bottom:10px;background:var(--bg2);border:1px solid var(--border);border-radius:999px;padding:4px;position:sticky;top:0;z-index:3;box-shadow:0 6px 18px rgba(15,23,42,.04)}.tab{flex:1;min-height:34px;padding:8px 12px;font-size:12px;font-weight:800;background:transparent;border:1px solid transparent;border-radius:999px;cursor:pointer;color:var(--t2);display:flex;align-items:center;justify-content:center;transition:background .18s ease,border-color .18s ease,color .18s ease,box-shadow .18s ease,transform .18s ease}.tab:hover{background:rgba(227,27,35,.08);border-color:rgba(227,27,35,.18);color:var(--t1);transform:translateY(-1px)}.tab.on{background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(255,232,234,.96));color:#8f0f1c;border-color:#e31b23;box-shadow:0 8px 20px rgba(227,27,35,.16),inset 0 1px 0 rgba(255,255,255,.5);transform:translateY(-1px)}
.panel{display:none}.panel.on{display:block}.bcard{background:var(--bg2);border:1px solid var(--border);border-radius:7px;padding:12px 14px;margin-bottom:10px}.section-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;gap:8px;flex-wrap:wrap}.section-title{font-size:12px;font-weight:800}
.table-card{padding:0;overflow:hidden}.table-scroll{overflow:auto;max-height:610px}.filter-pills{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}.fp{padding:4px 10px;font-size:11px;border:1px solid var(--border2);border-radius:20px;background:transparent;cursor:pointer;color:var(--t2);font-weight:700}.fp.on{background:var(--bg2);color:var(--t1);border-color:var(--blue)}
.tbl{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}.tbl th{position:sticky;top:0;z-index:2;background:var(--bg2);font-size:10px;font-weight:800;color:var(--t3);text-align:left;padding:7px 8px;border-bottom:1px solid var(--border);cursor:pointer;white-space:nowrap;text-transform:uppercase}.tbl td{padding:8px 8px;border-bottom:1px solid var(--border);vertical-align:middle}.tbl tr:last-child td{border-bottom:0}.tbl tr:hover td{background:var(--bg3);cursor:pointer}
.art-avatar{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;flex-shrink:0}.art-name{font-weight:800;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.art-genre{font-size:10px;color:var(--t3);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.score-bar{height:5px;border-radius:3px;background:var(--bg4);margin-top:4px;overflow:hidden}.score-fill{height:100%;border-radius:3px}.badge{display:inline-flex;align-items:center;font-size:10px;font-weight:800;padding:2px 7px;border-radius:4px;white-space:nowrap}
.b-new{background:var(--gd);color:var(--green)}.b-hot{background:rgba(252,211,77,.16);color:var(--amber)}.b-watch{background:var(--bd);color:var(--blue)}.b-cross{background:var(--pd);color:var(--purple)}.b-neu{background:var(--bg3);color:var(--t2);border:1px solid var(--border)}
.two-col{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);gap:10px}.pipeline-row{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--border)}.pipeline-row:last-child{border-bottom:0}.priority-dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0}.pl-stage{font-size:10px;font-weight:800;min-width:82px;padding:3px 7px;border-radius:4px;text-align:center}
.stage-prospect{background:var(--bd);color:var(--blue)}.stage-eval{background:rgba(252,211,77,.16);color:var(--amber)}.stage-nego{background:var(--pd);color:var(--purple)}.stage-signed{background:var(--gd);color:var(--green)}
.chart-wrap{position:relative;width:100%;height:190px}.score-chart{height:430px}.leg{display:flex;flex-wrap:wrap;gap:8px;margin-top:7px}.leg-item{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--t2)}
.spot-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);align-items:center;justify-content:center;padding:18px;z-index:50}.spot-bg.open{display:flex}.spot-modal{background:var(--bg2);border:1px solid var(--border2);border-radius:8px;padding:20px;width:100%;max-width:540px;position:relative;box-shadow:0 20px 80px rgba(0,0,0,.35)}.spot-close{position:absolute;top:10px;right:10px;background:transparent;border:0;cursor:pointer;color:var(--t2);font-size:18px;padding:4px}
.spot-name{font-size:18px;font-weight:800;margin-bottom:2px}.spot-sub{font-size:11px;color:var(--t3);margin-bottom:14px}.spot-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}.spot-kpi{background:var(--bg3);border-radius:8px;padding:10px 12px}.spot-kpi-label{font-size:10px;color:var(--t2);margin-bottom:3px}.spot-kpi-val{font-size:15px;font-weight:800}.btn{font-size:11px;padding:5px 10px;border:1px solid var(--border2);border-radius:7px;background:transparent;color:var(--t1);cursor:pointer;font-weight:700}
@media(max-width:1100px){.kpi-row{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:720px){.kpi-row{grid-template-columns:repeat(2,minmax(0,1fr))}.two-col{grid-template-columns:1fr}.tab span{display:none}.spot-grid{grid-template-columns:1fr}.tbl{min-width:780px}.top-right{width:100%}.search-wrap{flex:1}.search-wrap input{width:100%}}
</style></head><body>
<div class="d">
  <div class="kpi-row" id="kpiRow"></div>
  <div class="tab-row"><button class="tab on" onclick="showTab('top10',this)"><span>Top 10 targets</span></button><button class="tab" onclick="showTab('newartists',this)"><span>New artists</span></button><button class="tab" onclick="showTab('scoring',this)"><span>Scoring</span></button></div>
  <div class="panel on" id="panel-top10"><div class="bcard table-card"><div class="table-scroll"><table class="tbl"><thead><tr><th style="width:38px;padding-left:14px">#</th><th style="width:210px" onclick="sortTop10('artist')">Artist</th><th style="width:92px" onclick="sortTop10('oppScore')">Opp. score</th><th style="width:88px" onclick="sortTop10('platform')">Platform</th><th style="width:80px" onclick="sortTop10('peakRank')">Peak rank</th><th style="width:92px" onclick="sortTop10('momentumVal')">Momentum</th><th style="width:78px" onclick="sortTop10('markets')">Signals</th><th style="width:100px">Status</th><th style="width:82px">Action</th></tr></thead><tbody id="top10Body"></tbody></table></div></div></div>
  <div class="panel" id="panel-newartists"><div class="bcard table-card"><div class="table-scroll"><table class="tbl"><thead><tr><th style="width:38px;padding-left:14px">#</th><th style="width:210px" onclick="sortNew('artist')">Artist</th><th style="width:88px">Debut</th><th style="width:80px" onclick="sortNew('peakRank')">Peak rank</th><th style="width:100px" onclick="sortNew('streams')">Audience</th><th style="width:88px">Platform</th><th style="width:92px" onclick="sortNew('potential')">Potential</th><th style="width:100px">Recommend</th></tr></thead><tbody id="newArtistBody"></tbody></table></div></div></div>
  <div class="panel" id="panel-scoring"><div class="section-hd"><div class="section-title">Opportunity score breakdown - top 10 targets</div><button class="btn" onclick="sendPrompt('Explain how the artist acquisition opportunity score is calculated and what factors matter most for signing decisions')">Methodology</button></div><div class="chart-wrap score-chart"><canvas id="scoreChart"></canvas></div><div class="bcard"><div class="section-hd"><div class="section-title">Score components</div></div><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;font-size:12px"><div><div style="font-weight:800;margin-bottom:3px">iTunes consistency</div><div style="color:var(--t2)">Rank, score and chart presence.</div></div><div><div style="font-weight:800;margin-bottom:3px">Spotify reach</div><div style="color:var(--t2)">Listener scale and chart tracks.</div></div><div><div style="font-weight:800;margin-bottom:3px">Momentum</div><div style="color:var(--t2)">Recent listener growth or cooling.</div></div><div><div style="font-weight:800;margin-bottom:3px">Cross-platform</div><div style="color:var(--t2)">Bonus for iTunes plus Spotify validation.</div></div></div></div></div>
</div>
<div class="spot-bg" id="acqSpot" onclick="closeAcqSpot(event)"><div class="spot-modal" onclick="event.stopPropagation()"><button class="spot-close" onclick="closeAcqSpot()" aria-label="Close">x</button><div class="spot-name" id="asName"></div><div class="spot-sub" id="asSub"></div><div class="spot-grid" id="asKpis"></div><div style="margin-top:4px;display:flex;gap:8px;flex-wrap:wrap"></div></div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const PAYLOAD=__PAYLOAD__,DATES=PAYLOAD.dates||[],ARTISTS=PAYLOAD.artists||{},ALL_ARTISTS=PAYLOAD.allArtists||[],SUMMARY=PAYLOAD.summary||{};const periodPill=document.getElementById('periodPill');if(periodPill)periodPill.textContent=SUMMARY.dateRange||'Current window';
function fmtN(n){if(!n)return'0';const a=Math.abs(n);if(a>=1e9)return(n/1e9).toFixed(1)+'B';if(a>=1e6)return(n/1e6).toFixed(1)+'M';if(a>=1e3)return(n/1e3).toFixed(0)+'K';return Math.round(n).toString()}
function initials(n){return(n||'?').replace(/&/g,' ').split(/\\s+/).filter(Boolean).slice(0,2).map(w=>w[0]).join('').toUpperCase()||'?'}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function sendPrompt(q){try{window.parent.postMessage({type:'streamlit:setComponentValue',value:{prompt:q}},'*')}catch(e){console.log(q)}}function openAcqSpotEncoded(v){openAcqSpot(decodeURIComponent(v))}function briefArtist(v){sendPrompt('Generate a one-page acquisition brief for '+decodeURIComponent(v))}function dealUpdateArtist(v){sendPrompt('Give me a deal status update and negotiation strategy for acquiring '+decodeURIComponent(v))}
function bestRank(a){const vals=[parseInt(a.bestSpRank),parseInt(a.bestItunes)].filter(v=>Number.isFinite(v)&&v>0);return vals.length?Math.min(...vals):999}
function platform(a){const sp=a.bestSpRank&&a.bestSpRank!=='—'&&a.bestSpRank!=='-';const it=a.bestItunes&&a.bestItunes!=='—'&&a.bestItunes!=='-';if(sp&&it)return'cross';if(sp)return'spotify';return'itunes'}
function firstActiveDate(a){const idx=(a.originalSpStreams||a.spStreams||[]).findIndex(v=>v>0),itIdx=(a.originalItScores||a.itScores||[]).findIndex(v=>v>0),first=[idx,itIdx].filter(v=>v>=0).sort((x,y)=>x-y)[0];return Number.isFinite(first)?DATES[first]:'Current'}
function isNew(a){const idx=(a.originalSpStreams||a.spStreams||[]).findIndex(v=>v>0),itIdx=(a.originalItScores||a.itScores||[]).findIndex(v=>v>0),first=[idx,itIdx].filter(v=>v>=0).sort((x,y)=>x-y)[0];return!!a.isNewChampion||(Number.isFinite(first)&&first>=Math.floor(DATES.length*.35))}
function statusFor(a){if(a.acqScore>=90)return'nego';if(a.acqScore>=78)return'eval';if(a.acqScore>=60)return'prospect';return'watch'}function stageLabel(s){return{nego:'Negotiation',eval:'Evaluation',prospect:'Prospect',signed:'Signed',watch:'Watchlist'}[s]||s}function stageClass(s){return{nego:'stage-nego',eval:'stage-eval',prospect:'stage-prospect',signed:'stage-signed'}[s]||''}
function recFor(a){if(a.acqScore>=88)return'Sign now';if(a.acqScore>=78)return'Priority';if(a.acqScore>=62)return'Watch';if(a.acqScore>=45)return'Monitor';return'Pass'}function recClass(r){return{'Sign now':'b-new',Priority:'b-hot',Watch:'b-watch',Monitor:'b-cross',Pass:'b-neu'}[r]||'b-neu'}function colorForScore(s){return s>=90?'#34d399':s>=78?'#60a5fa':s>=60?'#fcd34d':'#fb7185'}
const ROWS=ALL_ARTISTS.map(name=>{const a=ARTISTS[name]||{},pf=platform(a),pk=bestRank(a),tracks=parseInt(a.trackCount||0,10)||0,score=Number(a.acqScore||0);return{artist:name,avatar:a.avatar||initials(name),color:a.color||'#60a5fa',label:a.label||'Independent',platform:pf,peakRank:pk,momentumVal:Number(a.momentum||0),momentum:(Number(a.momentum||0)>=0?'+':'')+Number(a.momentum||0).toFixed(1)+'%',markets:Math.max(1,(a.signals||[]).length+tracks),oppScore:score,status:statusFor({acqScore:score}),streams:Number(a.peakStreamsVal||0),isNew:isNew(a),debutDate:firstActiveDate(a),potential:score,recommend:recFor({acqScore:score}),quote:a.quote||'',signals:a.signals||[],tracks:a.tracks||[],itunesRank:a.bestItunes||'-',spotifyRank:a.bestSpRank||'-'}}).sort((a,b)=>b.oppScore-a.oppScore);
const TOP10=ROWS.slice(0,10),NEW_ARTISTS=ROWS.filter(a=>a.isNew).sort((a,b)=>b.potential-a.potential).slice(0,30),PIPELINE=ROWS.filter(a=>a.oppScore>=60).slice(0,12).map(a=>({...a,since:a.debutDate,value:a.oppScore>=90?'High':a.oppScore>=78?'Medium':'TBD',priority:a.oppScore>=82?'high':'med'}));let top10SortKey='oppScore',top10SortDir=-1,newSortKey='potential',newSortDir=-1,spotArtist='';
function renderKpis(){const high=ROWS.filter(a=>a.oppScore>=78).length,cross=ROWS.filter(a=>a.platform==='cross').length,avg=Math.round(ROWS.reduce((s,a)=>s+a.oppScore,0)/Math.max(1,ROWS.length)),pipe=PIPELINE.length,k=[['#0C447C','Total targets',ROWS.length,'Active watchlist',`${TOP10.length} top targets`],['#1D9E75','High priority',high,'Score 78+',`${PIPELINE.filter(a=>a.status==='nego').length} in negotiation`],['#534AB7','New entrants',NEW_ARTISTS.length,'Debut in window','Chart emergence'],['#993556','Cross-platform',cross,'iTunes + Spotify','Highest value tier'],['#BA7517','Avg opp. score',avg,'Out of 100','Live composite'],['#D85A30','Deal pipeline',pipe,'Active deal stages',`${PIPELINE.filter(a=>a.status==='eval'||a.status==='nego').length} active reviews`]];document.getElementById('kpiRow').innerHTML=k.map(x=>`<div class="kcard" onclick="sendPrompt('Explain ${esc(x[1])} in the artist acquisition dashboard')"><div class="kcard-bar" style="background:${x[0]}"></div><div class="kcard-label">${x[1]}</div><div class="kcard-val">${x[2]}</div><div class="kcard-sub">${x[3]}</div><div class="kcard-delta">${x[4]}</div></div>`).join('')}
function platformBadge(p){if(p==='cross')return'<span class="badge b-cross">Cross</span>';if(p==='spotify')return'<span class="badge b-new">Spotify</span>';return'<span class="badge b-hot">iTunes</span>'}
function artistCell(a){return`<div style="display:flex;align-items:center;gap:8px"><div class="art-avatar" style="background:${a.color}22;color:${a.color};border:1px solid ${a.color}40">${esc(a.avatar)}</div><div style="min-width:0"><div class="art-name">${esc(a.artist)}${a.isNew?' <span class="badge b-new" style="font-size:9px;padding:1px 5px">New</span>':''}</div><div class="art-genre">${esc(a.label)}</div></div></div>`}
function sortTop10(k){if(top10SortKey===k)top10SortDir*=-1;else{top10SortKey=k;top10SortDir=-1}renderTop10()}function sortNew(k){if(newSortKey===k)newSortDir*=-1;else{newSortKey=k;newSortDir=-1}renderNewArtists()}
function renderTop10(){const d=[...TOP10];d.sort((a,b)=>typeof a[top10SortKey]==='string'?top10SortDir*a[top10SortKey].localeCompare(b[top10SortKey]):top10SortDir*(a[top10SortKey]-b[top10SortKey]));const mx=Math.max(...d.map(a=>a.oppScore),1);document.getElementById('top10Body').innerHTML=d.map((a,i)=>`<tr onclick="openAcqSpotEncoded('${encodeURIComponent(a.artist)}')"><td style="padding-left:14px;font-weight:800;color:var(--t2)">${i+1}</td><td>${artistCell(a)}</td><td><div style="font-weight:800">${a.oppScore}</div><div class="score-bar"><div class="score-fill" style="width:${Math.round(a.oppScore/mx*100)}%;background:${colorForScore(a.oppScore)}"></div></div></td><td>${platformBadge(a.platform)}</td><td style="font-weight:800;text-align:center">${a.peakRank===999?'-':'#'+a.peakRank}</td><td><span style="font-weight:800;color:${a.momentumVal>=0?'var(--green)':'var(--red)'}">${a.momentum}</span></td><td style="text-align:center">${a.markets}</td><td>${stageClass(a.status)?`<span class="pl-stage ${stageClass(a.status)}">${stageLabel(a.status)}</span>`:`<span class="badge b-watch">${stageLabel(a.status)}</span>`}</td><td><button class="btn" onclick="event.stopPropagation();briefArtist('${encodeURIComponent(a.artist)}')">Brief</button></td></tr>`).join('')||'<tr><td colspan="9" style="padding:18px;text-align:center;color:var(--t3)">No targets available.</td></tr>'}
function renderNewArtists(){const d=[...NEW_ARTISTS];d.sort((a,b)=>typeof a[newSortKey]==='string'?newSortDir*a[newSortKey].localeCompare(b[newSortKey]):newSortDir*(a[newSortKey]-b[newSortKey]));document.getElementById('newArtistBody').innerHTML=d.map((a,i)=>`<tr onclick="openAcqSpotEncoded('${encodeURIComponent(a.artist)}')"><td style="padding-left:14px;color:var(--t2);font-weight:800">${i+1}</td><td>${artistCell(a)}</td><td><span class="badge b-new">${esc(a.debutDate)}</span></td><td style="font-weight:800;text-align:center">${a.peakRank===999?'-':'#'+a.peakRank}</td><td>${fmtN(a.streams)}</td><td>${platformBadge(a.platform)}</td><td><div style="display:flex;align-items:center;gap:6px"><span style="font-weight:800;color:${colorForScore(a.potential)}">${a.potential}</span><div class="score-bar" style="flex:1"><div class="score-fill" style="width:${a.potential}%;background:${colorForScore(a.potential)}"></div></div></div></td><td><span class="badge ${recClass(a.recommend)}">${a.recommend}</span></td></tr>`).join('')||'<tr><td colspan="8" style="padding:18px;text-align:center;color:var(--t3)">No new artists available.</td></tr>'}
function renderCharts(){if(!window.Chart)return;const css=getComputedStyle(document.documentElement),text=css.getPropertyValue('--t2').trim()||'#94a3b8',grid=css.getPropertyValue('--border').trim()||'rgba(148,163,184,.2)';new Chart(document.getElementById('scoreChart'),{type:'bar',data:{labels:TOP10.map(a=>a.artist.length>18?a.artist.slice(0,18)+'...':a.artist),datasets:[{label:'iTunes consistency',data:TOP10.map(a=>a.platform==='spotify'?4:Math.min(35,Math.max(10,110-a.peakRank))),backgroundColor:'#60a5fa',stack:'score'},{label:'Spotify reach',data:TOP10.map(a=>a.platform==='itunes'?5:Math.min(30,10+(a.tracks.length*6))),backgroundColor:'#34d399',stack:'score'},{label:'Momentum',data:TOP10.map(a=>Math.max(5,Math.min(20,10+a.momentumVal/2))),backgroundColor:'#fcd34d',stack:'score'},{label:'Cross-platform',data:TOP10.map(a=>a.platform==='cross'?15:0),backgroundColor:'#c4b5fd',stack:'score'}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{position:'bottom',labels:{color:text,boxWidth:10}}},scales:{x:{stacked:true,max:100,grid:{color:grid},ticks:{color:text}},y:{stacked:true,grid:{display:false},ticks:{color:text}}}}})}
function openAcqSpot(artist){const a=ROWS.find(r=>r.artist===artist);if(!a)return;spotArtist=artist;document.getElementById('asName').textContent=a.artist;const tags=[a.platform==='cross'?'Cross-platform':a.platform==='spotify'?'Spotify artist':'iTunes artist'];if(a.isNew)tags.push('New chart entrant');if(PIPELINE.find(p=>p.artist===a.artist))tags.push('In pipeline');document.getElementById('asSub').textContent=tags.join(' / ')+' / '+(SUMMARY.dateRange||'current window');document.getElementById('asKpis').innerHTML=[['Opportunity score',a.oppScore+'/100'],['Peak chart rank',a.peakRank===999?'-':'#'+a.peakRank],['Momentum',a.momentum],['Audience',fmtN(a.streams)],['iTunes rank',a.itunesRank],['Spotify rank',a.spotifyRank],['Recommendation',a.recommend],['Signals',a.signals.length||a.markets]].map(k=>`<div class="spot-kpi"><div class="spot-kpi-label">${k[0]}</div><div class="spot-kpi-val">${esc(k[1])}</div></div>`).join('');document.getElementById('acqSpot').classList.add('open')}
function closeAcqSpot(e){if(!e||e.target===document.getElementById('acqSpot'))document.getElementById('acqSpot').classList.remove('open')}function asAsk(){closeAcqSpot();sendPrompt(`Generate a full acquisition brief for ${spotArtist}: chart performance summary, commercial opportunity, competitive risk, deal structure recommendation, and suggested offer range.`)}function acqDoSearch(q){if(!q)return;const f=ROWS.find(a=>a.artist.toLowerCase().includes(q.toLowerCase()));if(f)openAcqSpot(f.artist)}function showTab(id,b){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));b.classList.add('on');document.getElementById('panel-'+id).classList.add('on')}
renderKpis();renderTop10();renderNewArtists();renderCharts();
</script></body></html>
""".replace("__PAYLOAD__", data_json).replace("__THEME__", theme_css)


def prefetch_acquisition_data() -> None:
    """Warms up the cache for all three Acquisition dashboards (Artist, Track, and Album) in the background."""
    try:
        # Artist Acquisition Prep
        sp_df = _load_daily("spotify_daily", "global", WINDOW_DAYS)
        it_df = _load_daily("itunes_daily", "ww", WINDOW_DAYS)
        _load_artist_universe(WINDOW_DAYS)
        sp_artist_df = _load_spotify_artist_series(WINDOW_DAYS)
        it_artist_df = _load_itunes_artist_series(WINDOW_DAYS)

        # Pre-build dates and payloads
        date_set = set()
        if not sp_artist_df.empty: date_set.update(sp_artist_df["scrape_date"].unique())
        if not it_artist_df.empty: date_set.update(it_artist_df["scrape_date"].unique())
        dates = sorted(date_set)
        if dates:
            universe_df = _load_artist_universe(WINDOW_DAYS)
            get_processed_artist_payloads(universe_df, sp_artist_df, it_artist_df, sp_df, it_df, dates)
        
        # Track Acquisition Prep
        from src.ai.track_acquisition_dashboard import _load_window_multi as load_track_multi
        from src.ai.track_acquisition_dashboard import _load_window as load_track_window
        from src.ai.track_acquisition_dashboard import get_processed_track_rows
        latam_codes = ["ar", "bo", "br", "cl", "co", "cr", "do", "ec", "sv", "gt", "hn", "mx", "ni", "pa", "pe", "py", "uy", "ve"]
        all_codes = ["global", "us"] + latam_codes
        sp_all_df = load_track_multi("spotify_daily", all_codes, 30)
        it_track_df = load_track_window("itunes_daily", "ww", 30)
        if not sp_all_df.empty:
            track_dates = sorted(set(sp_all_df["date"]))
            get_processed_track_rows(sp_all_df[sp_all_df["country"] == "global"], it_track_df, track_dates, region="Global")
            get_processed_track_rows(sp_all_df[sp_all_df["country"] == "us"], it_track_df, track_dates, region="US")
        
        # Album Acquisition Prep
        from src.ai.album_acquisition_dashboard import _load_window_multi as load_album_multi
        from src.ai.album_acquisition_dashboard import get_processed_album_rows
        album_all_df = load_album_multi("itunes_artist_album", ["ww", "us"] + latam_codes, 30)
        if not album_all_df.empty:
            album_dates = sorted(set(album_all_df["date"]))
            get_processed_album_rows(album_all_df[album_all_df["country"] == "ww"], pd.DataFrame(), album_dates, region="Global")
    except Exception as e:
        logger.error(f"Error prefetching acquisition data: {e}")
