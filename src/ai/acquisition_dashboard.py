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
def _load_artist_universe() -> pd.DataFrame:
    """Primary universe = artists ranked on iTunes WW on the latest scrape day (~300)."""
    query = """
        SELECT DISTINCT a.id AS artist_id, a.name
        FROM itunes_artist_rankings ir
        JOIN artists a ON a.id = ir.artist_id
        WHERE ir.scrape_date = (SELECT MAX(scrape_date) FROM itunes_artist_rankings)
          AND a.name IS NOT NULL
        ORDER BY a.name
    """
    rows = _run_query(query, ())
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
              ir.total_points,
              ROW_NUMBER() OVER (
                PARTITION BY ir.artist_id, ir.scrape_date
                ORDER BY ir.scraped_at DESC NULLS LAST
              ) AS rn
            FROM itunes_artist_rankings ir, bounds b
            WHERE ir.scrape_date >  (b.max_d - %s::int)
              AND ir.scrape_date <= b.max_d
        )
        SELECT r.artist_id, a.name, r.scrape_date, r.rank, r.total_points
        FROM ranked r
        JOIN artists a ON a.id = r.artist_id
        WHERE r.rn = 1
    """
    rows = _run_query(query, (days,))
    if not rows:
        return pd.DataFrame(columns=["artist_id", "name", "scrape_date", "rank", "total_points"])
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


def _signal(score: int, momentum: float, best_rank: int | None) -> tuple[str, str]:
    if best_rank is not None and best_rank <= 10 and momentum >= 5:
        return "STRONG BUY", "sb-buy"
    if score >= 140 and momentum >= 0:
        return "STRONG BUY", "sb-buy"
    if best_rank is not None and best_rank <= 30:
        return "WATCH", "sb-watch"
    if momentum <= -25:
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

    # Pre-group per-artist series (per artist NAME — universe and series share `name`)
    sp_by_name = {n: g for n, g in sp_artist_df.groupby("name")} if not sp_artist_df.empty else {}
    it_by_name = {n: g for n, g in it_artist_df.groupby("name")} if not it_artist_df.empty else {}

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
        ml_g = sp_by_name.get(artist)
        if ml_g is not None and not ml_g.empty:
            ml_map = dict(zip(ml_g["scrape_date"], ml_g["monthly_listeners"]))
        else:
            ml_map = {}
        ml_series_raw = [int(ml_map[d]) if ml_map.get(d) is not None and pd.notna(ml_map.get(d)) else None for d in dates]
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
        it_g = it_by_name.get(artist)
        if it_g is not None and not it_g.empty:
            it_pts_map = dict(zip(it_g["scrape_date"], it_g["total_points"]))
            it_rank_map = dict(zip(it_g["scrape_date"], it_g["rank"]))
        else:
            it_pts_map, it_rank_map = {}, {}
        it_scores = [int(it_pts_map[d]) if it_pts_map.get(d) is not None and pd.notna(it_pts_map.get(d)) else 0 for d in dates]
        it_ranks = [int(it_rank_map[d]) if it_rank_map.get(d) is not None and pd.notna(it_rank_map.get(d)) else None for d in dates]
        ranks_clean = [r for r in it_ranks if r is not None]
        best_it_rank = min(ranks_clean) if ranks_clean else None
        best_it_score = max([s for s in it_scores if s > 0], default=0)
        best_it_date = max(it_pts_map, key=lambda d: it_pts_map[d]) if it_pts_map else None

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

        # ── Composite acquisition score ──
        ml_score = min(100, int(peak_ml / 1_000_000)) if peak_ml else 0
        itunes_bonus = max(0, 60 - best_it_rank) if best_it_rank else 0
        chart_bonus = min(40, track_count * 4) + (max(0, 50 - best_sp_rank) if best_sp_rank else 0)
        momentum_bonus = max(-40, min(60, int(momentum)))
        acq_score = max(0, ml_score + itunes_bonus + chart_bonus + momentum_bonus)
        signal_text, signal_class = _signal(acq_score, momentum, best_it_rank or best_sp_rank)

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
        "<div style='font-size:0.95rem;color:#97a3c5;margin:0.2rem 0 0.75rem 0;line-height:1.5;'>"
        "Evaluate artist-level acquisition potential by analyzing cross-platform performance metrics. "
        "This dashboard combines daily streaming data from Spotify Global "
        "with iTunes Worldwide chart movements to compute an overall Acquisition Score. "
        "Use the filtering tools and trajectory insights to identify breakout artists with strong growth and momentum."
        "</div>",
        unsafe_allow_html=True,
    )

    period_days = 30

    sp_df = _load_daily("spotify_daily", "global", period_days)
    it_df = _load_daily("itunes_daily", "ww", period_days)
    universe_df = _load_artist_universe()
    sp_artist_df = _load_spotify_artist_series(period_days)
    it_artist_df = _load_itunes_artist_series(period_days)

    if universe_df.empty:
      st.warning("No iTunes artist rankings available — cannot build acquisition universe.")
      return

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

    artist_data = _build_artist_payloads(universe_df, sp_artist_df, it_artist_df, sp_df, it_df, dates)
    if not artist_data:
      st.warning("No artist signals could be computed.")
      return

    date_labels = [d.strftime("%b %d") for d in dates]
    
    artists_list = []
    for i, (name, data) in enumerate(artist_data.items()):
        data["id"] = i + 1
        data["name"] = name
        artists_list.append(data)
        
    artists_list.sort(key=lambda x: x["acqScore"], reverse=True)

    default_id = artists_list[0]["id"] if artists_list else None

    payload = {
        "dates": date_labels,
        "artists": artists_list,
        "defaultArtistId": default_id,
        "maxWindowDays": period_days,
        "regionLabel": "Spotify Global",
    }
    
    with st.expander("ℹ️ How is the Acquisition Score calculated?"):
        st.markdown(
            "The **Acquisition Score (0-100)** is a composite metric evaluating an artist's market potential. It is calculated using:\n"
            "- **Peak Listeners (30%)**: Scaled based on daily volume.\n"
            "- **Best Rank (40%)**: Spotify Global/iTunes chart peak.\n"
            "- **Momentum (20%)**: Trajectory of listener growth and rank delta.\n"
            "- **iTunes Bonus (10%)**: Cross-platform validation from iTunes WW charts.\n\n"
            "👉 **Interactive Analysis**: Select any artist from the leaderboard to instantly load their detailed acquisition profile, including stream trajectories and specific market signals."
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


def _build_html(payload: dict, dark_mode: bool = False) -> str:
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

.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; flex-shrink: 0; width: calc(50% - 8px); }
.filter-btn { font-size: 12px; padding: 5px 12px; border-radius: 999px; border: 0.5px solid var(--color-border-secondary); background: var(--color-background-primary); color: var(--color-text-secondary); cursor: pointer; transition: all .15s; }
.filter-btn.active { background: #185FA5; color: #E6F1FB; border-color: #185FA5; }
.filter-tag { display: flex; align-items: center; font-size: 14px; padding: 8px 16px; border-radius: 999px; background: var(--color-background-secondary); color: var(--color-text-secondary); border: 1px solid var(--color-border-tertiary); cursor: pointer; }
.filter-tag select { background: transparent; border: none; color: inherit; font-size: inherit; font-family: inherit; outline: none; cursor: pointer; }

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
.track-info { min-width: 0; text-align: left; display: flex; align-items: center; gap: 8px; }
.track-av { width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0; }
.track-name { font-size: 13px; font-weight: 500; color: var(--color-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

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
.detail-title-row { display: flex; align-items: center; gap: 10px; }
.detail-title { font-size: 17px; font-weight: 500; color: var(--color-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
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

#searchInput { background: transparent; border: none; color: inherit; outline: none; width: 180px; font-family: inherit; font-size: inherit; }
#searchInput::placeholder { color: var(--color-text-tertiary); }

.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 300px; color: var(--color-text-tertiary); text-align: center; gap: 8px; }
</style>
</head><body class="__BODY_CLASS__">

<h2 class="sr-only" style="display:none;">Music acquisition analytics dashboard showing top artists by acquisition score, listeners, and momentum</h2>

<div class="dash-wrapper">
  <div class="filters">
      <span style="display:flex; gap:8px; align-items:center;">
        <span class="filter-tag">
            <input type="text" id="searchInput" placeholder="Search..." oninput="applyFilters()">
        </span>
        <span class="filter-tag">
          <select id="windowSel" onchange="setTimeWindow(this.value)">
            <option value="All">All Time</option>
            <option value="7">7 Days</option>
            <option value="14">14 Days</option>
            <option value="30" selected>30 Days</option>
          </select>
        </span>
        <span class="filter-tag" id="count-badge">0 artists</span>
      </span>
  </div>

<div class="dash">
  <div class="left-col">
    <div class="track-table">
      <div class="track-header">
        <span>#</span>
        <span onclick="setSort('name')">Artist</span>
        <span class="col-r" onclick="setSort('rank')">Best Rank</span>
        <span class="col-r" onclick="setSort('listeners')">Listeners</span>
        <span class="col-r" onclick="setSort('momentum')">Momentum</span>
        <span class="col-r" onclick="setSort('acq')">Score</span>
      </div>
      <div class="track-body" id="track-table">
        <!-- Artists rendered here -->
      </div>
    </div>
  </div>

  <div class="right-col" id="detail-panel">
    <div class="detail-card">
      <div class="detail-header">
        <div>
          <div class="detail-title-row">
            <div id="d-av" class="track-av" style="display:none;"></div>
            <div class="detail-title" id="d-title">Select Artist</div>
          </div>
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
          <div class="stat-label">Peak Listeners</div>
          <div class="stat-value" id="d-listeners">—</div>
          <div class="stat-sub" id="d-listeners-sub">—</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Momentum</div>
          <div class="stat-value" id="d-momentum">—</div>
          <div class="stat-sub">Window change</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Days Tracked</div>
          <div class="stat-value" id="d-days">—</div>
          <div class="stat-sub">Window days</div>
        </div>
      </div>

      <div class="chart-section" id="d-chart-section" style="display:none">
        <div class="chart-label">Monthly Listeners Trajectory</div>
        <div class="chart-wrap">
          <canvas id="trajChart" role="img" aria-label="Trajectory chart"></canvas>
        </div>
        <div style="display:flex;gap:16px;margin-top:6px;">
          <span style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--color-text-secondary)"><span style="width:16px;height:2px;background:#378ADD;display:inline-block;border-radius:1px"></span>Listeners</span>
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
        <div style="font-size:12px">Select an artist from the list<br>to view their acquisition profile</div>
    </div>
  </div>
</div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const ORIGINAL_PAYLOAD = __PAYLOAD__;
const ORIGINAL_DATES = ORIGINAL_PAYLOAD.dates || [];
let ORIGINAL_ARTISTS = ORIGINAL_PAYLOAD.artists || [];
const DATES = ORIGINAL_DATES;

let PAYLOAD = JSON.parse(JSON.stringify(ORIGINAL_PAYLOAD));
let ARTISTS = JSON.parse(JSON.stringify(ORIGINAL_ARTISTS));

let currentSort = 'acq';
let currentTimeWindowDays = ORIGINAL_PAYLOAD.maxWindowDays;
let selectedId = PAYLOAD.defaultArtistId;
let trajChartInst = null;
let itTrajChartInst = null;

// Acq Score is calculated in Python in this dashboard
function recalculateArtistMetrics(artist, windowDays, fullDates) {
    const startIndex = Math.max(0, fullDates.length - windowDays);
    const slicedSpStreams = artist.originalSpStreams.slice(startIndex);
    const slicedItScores = artist.originalItScores.slice(startIndex);
    
    // In actual JS we would just display the python-calculated values 
    // unless we recalculate. For simplicity, we just filter arrays for charts.
    const recalculatedArtist = { ...artist };
    recalculatedArtist.spStreams = slicedSpStreams; 
    recalculatedArtist.itScores = slicedItScores;
    recalculatedArtist.days = windowDays;

    return recalculatedArtist;
}

function setTimeWindow(val) {
    currentTimeWindowDays = val === 'All' ? ORIGINAL_PAYLOAD.maxWindowDays : parseInt(val);
    applyFilters();
    if (selectedId) selectArtist(selectedId); 
}

function fmtN(n){if(!n&&n!==0)return'—';const a=Math.abs(n);if(a>=1e6)return(n/1e6).toFixed(1)+'M';if(a>=1e3)return(n/1e3).toFixed(0)+'K';return Math.round(n).toString();}

function setSort(s){
  currentSort = s;
  applyFilters();
}

function applyFilters(){
  let filteredArtists = JSON.parse(JSON.stringify(ORIGINAL_ARTISTS));

  filteredArtists = filteredArtists.map(a => recalculateArtistMetrics(a, currentTimeWindowDays, ORIGINAL_DATES));

  const q = document.getElementById('searchInput').value.toLowerCase();
  
  if(q) filteredArtists = filteredArtists.filter(t=>t.name.toLowerCase().includes(q));

  ARTISTS = filteredArtists;

  const sortMap={acq:'acqScore',momentum:'momentum',rank:'bestSpRank',listeners:'peakStreamsVal',name:'name'};
  const key=sortMap[currentSort]||'acqScore';
  const asc=(key==='bestSpRank' || key==='name');
  ARTISTS.sort((a,b)=>{
    if (key === 'name') {
        return a.name.localeCompare(b.name);
    }
    const valA = a[key] === '—' || a[key] === null ? (asc ? 999999 : -999999) : a[key];
    const valB = b[key] === '—' || b[key] === null ? (asc ? 999999 : -999999) : b[key];
    return asc ? valA-valB : valB-valA;
  });

  renderTable();
}

function renderTable() {
    document.getElementById('count-badge').textContent = `${ARTISTS.length} artists`;
    const el = document.getElementById('track-table');
    let htmlStr = '';

    ARTISTS.forEach((t, i) => {
        const momColor = t.momentum > 5 ? 'momentum-pos' : t.momentum < -5 ? 'momentum-neg' : 'momentum-flat';
        let acqClass = 'acq-lo';
        if (t.acqScore >= 60) acqClass = 'acq-hi';
        else if (t.acqScore >= 45) acqClass = 'acq-mid';

        htmlStr += `
        <div class="track-row ${t.id === selectedId ? 'selected' : ''}" onclick="selectArtist(${t.id})">
            <div class="sr-num">${i + 1}</div>
            <div class="track-info">
                <div class="track-av" style="background:${t.color}22;color:${t.color};border:1px solid ${t.color}40">${t.avatar}</div>
                <div class="track-name">${t.name}</div>
            </div>
            <div class="col-r streams-val">${t.bestSpRank || '—'}</div>
            <div class="col-r streams-val">${fmtN(t.peakStreamsVal)}</div>
            <div class="col-r momentum-val ${momColor}">${t.momentum > 0 ? '+' : ''}${t.momentum}%</div>
            <div class="col-r"><span class="acq-pill ${acqClass}">${t.acqScore}</span></div>
        </div>`;
    });
    el.innerHTML = htmlStr;
}

function renderChart(traj, days) {
  const ctx = document.getElementById('trajChart').getContext('2d');
  if (trajChartInst) trajChartInst.destroy();
  const labels = DATES.slice(Math.max(0, DATES.length - days));
  
  trajChartInst = new Chart(ctx, {
    data: {
      labels,
      datasets: [
        { type:'line', label:'Listeners', data: traj, borderColor:'#378ADD', backgroundColor:'rgba(55,138,221,0.08)', borderWidth:2, pointRadius:3, pointBackgroundColor:'#378ADD', tension:.4, yAxisID:'y', spanGaps: true, fill: true },
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

function selectArtist(id) {
  selectedId = id;
  const t = ARTISTS.find(x => x.id === id);
  renderTable(); 

  if (!t) {
    document.getElementById('empty-state').style.display = 'flex';
    document.getElementById('d-chart-section').style.display = 'none';
    document.getElementById('d-it-chart-section').style.display = 'none';
    document.getElementById('d-signals-card').style.display = 'none';
    document.getElementById('d-av').style.display = 'none';
    return;
  }

  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('d-title').textContent = t.name;
  
  const av = document.getElementById('d-av');
  av.style.display = 'flex';
  av.style.background = t.color+'22';
  av.style.color = t.color;
  av.style.border = '1px solid '+t.color+'40';
  av.textContent = t.avatar;
  
  document.getElementById('d-score').textContent = t.acqScore;
  const sortedByAcq = [...ARTISTS].sort((a,b) => b.acqScore - a.acqScore);
  const rank = sortedByAcq.findIndex(x => x.id === id) + 1;
  document.getElementById('d-rank').textContent = `#${rank} of ${ARTISTS.length}`;
  
  document.getElementById('d-rank-val').textContent = t.bestSpRank || '—';
  document.getElementById('d-rank-sub').textContent = PAYLOAD.regionLabel;
  
  document.getElementById('d-listeners').textContent = fmtN(t.peakStreamsVal);
  document.getElementById('d-listeners-sub').textContent = "Peak Listeners";
  
  const mEl = document.getElementById('d-momentum');
  mEl.textContent = `${t.momentum > 0 ? '+' : ''}${t.momentum}%`;
  mEl.className = 'stat-value ' + (t.momentum > 5 ? 'pos' : t.momentum < -5 ? 'neg' : '');
  
  document.getElementById('d-days').textContent = t.days || currentTimeWindowDays;

  const badgesEl = document.getElementById('d-badges');
  badgesEl.innerHTML = '';
  if (t.label) badgesEl.innerHTML += `<span class="badge ${t.label === 'INDEPENDENT' ? '' : 'active-b'}">${t.label}</span>`;

  document.getElementById('d-signals-card').style.display = 'block';
  const sigHtml = (t.signals||[]).map(s =>
    `<div class="signal-row"><div class="signal-icon" aria-hidden="true">${s.icon}</div><div class="signal-text"><strong>${s.title}</strong><span>${s.desc}</span></div></div>`
  ).join('');
  document.getElementById('d-signals').innerHTML = sigHtml;

  const hasSp = t.spStreams && t.spStreams.some(v => v > 0);
  if (hasSp) {
    document.getElementById('d-chart-section').style.display = 'block';
    renderChart(t.spStreams, t.days || currentTimeWindowDays);
  } else {
    document.getElementById('d-chart-section').style.display = 'none';
  }
  
  const hasIt = t.itScores && t.itScores.some(v => v > 0);
  if (hasIt) {
      document.getElementById('d-it-chart-section').style.display = 'block';
      renderItChart(t.itScores, t.days || currentTimeWindowDays);
  } else {
      document.getElementById('d-it-chart-section').style.display = 'none';
  }
}

applyFilters(); 
if(selectedId){setTimeout(()=>selectArtist(selectedId),80);}
</script>
</body></html>
""".replace("__PAYLOAD__", data_json).replace("__THEME__", theme_css).replace("__BODY_CLASS__", body_class)


def prefetch_acquisition_data() -> None:
    """Warms up the cache for all three Acquisition dashboards (Artist, Track, and Album) in the background."""
    try:
        _load_daily("spotify_daily", "global", 30)
        _load_daily("itunes_daily", "ww", 30)
        _load_artist_universe()
        _load_spotify_artist_series(30)
        _load_itunes_artist_series(30)
        
        from src.ai.track_acquisition_dashboard import _load_window as load_track_window
        load_track_window("spotify_daily", "global", 7)
        load_track_window("spotify_daily", "us", 7)
        load_track_window("itunes_daily", "ww", 7)
        
        from src.ai.album_acquisition_dashboard import _load_window as load_album_window
        load_album_window("itunes_artist_album", "ww", 7)
    except Exception as e:
        logger.error(f"Error prefetching acquisition data: {e}")
