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
      "<div style='font-size: 0.92rem; color: var(--t2); margin: 0 0 14px; line-height: 1.5; font-weight: 500;'>"
      "🎤 Artist-level acquisition recommendations driven by peak Spotify monthly listeners, iTunes Worldwide performance, "
      "and recent audience momentum."
      "</div>",
      unsafe_allow_html=True,
    )

    period_days = 30

    sp_df = _load_daily("spotify_daily", "global", 30)
    it_df = _load_daily("itunes_daily", "ww", 30)
    universe_df = _load_artist_universe()
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

    artist_data = _build_artist_payloads(universe_df, sp_artist_df, it_artist_df, sp_df, it_df, dates)
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

    # Default selected = top of leaderboard
    default_artist = leaderboard[0]["n"] if leaderboard else next(iter(artist_data))

    payload = {
        "dates": date_labels,
        "artists": artist_data,
        "leaderboard": leaderboard,
        "momentum": momentum_data,
        "defaultArtist": default_artist,
        "allArtists": list(artist_data.keys()),
        "maxWindowDays": 30,
    }

    html = _build_html(payload, dark_mode=st.session_state.get("dark_mode", False))
    st_components.html(html, height=1700, scrolling=True)


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
.acq-header{padding:20px 22px 16px;border-bottom:1px solid var(--border)}
.acq-meta{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.7px;margin-bottom:8px;font-weight:600}
.acq-row{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:14px}
.acq-left{flex:1;min-width:240px}
.acq-id-row{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.acq-avatar{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;flex-shrink:0}
.acq-name{font-size:26px;font-weight:800;letter-spacing:-.5px;line-height:1.2;color:var(--t1)}
.acq-sublabel{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.7px;margin-top:3px;font-weight:600}
.acq-quote{font-size:15px;color:var(--t2);line-height:1.65;border-left:2px solid var(--border2);padding-left:14px;margin-top:12px}
.signal-badge{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;padding:7px 14px;border-radius:6px;letter-spacing:.5px;text-transform:uppercase;white-space:nowrap}
.sb-buy{background:var(--gd);color:var(--green);border:1px solid rgba(52,211,153,.4)}
.sb-watch{background:var(--bd);color:var(--blue);border:1px solid rgba(96,165,250,.4)}
.sb-caution{background:var(--rd);color:var(--red);border:1px solid rgba(251,113,133,.4)}

.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--border);border-top:1px solid var(--border)}
.stat-cell{background:var(--bg2);padding:16px 18px;transition:.15s}
.stat-cell:hover{background:var(--bg3)}
.stat-lbl{font-size:12px;color:var(--t3);text-transform:uppercase;letter-spacing:.7px;margin-bottom:7px;font-weight:800}
.stat-val{font-size:26px;font-weight:800;letter-spacing:-.5px;color:var(--t1);font-variant-numeric:tabular-nums}
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

.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}

.sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border)}
.sh-l{font-size:14px;font-weight:600;color:var(--t1);letter-spacing:-.2px}
.sh-r{font-size:11px;color:var(--t2);background:var(--bg3);padding:5px 12px;border-radius:5px;border:1px solid var(--border2);font-weight:500}

::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:var(--bg2)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:var(--t4)}
</style></head><body>

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
  <div class="filter-grp" style="margin-left:12px">
    <button class="fp" onclick="setTimeWindow('1 Day',this)">1 Day</button>
    <button class="fp" onclick="setTimeWindow('7 Days',this)">7 Days</button>
    <button class="fp on" onclick="setTimeWindow('30 Days',this)">30 Days</button>
  </div>
  <span class="sel-label" style="margin-left:auto;color:var(--t2)" id="dd-count"></span>
</div>

<div class="body">

  <div class="two-col">
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

    <div class="leader-card">
    <div class="sh"><span class="sh-l">Acquisition leaderboard · all artists ranked</span><span class="sh-r">Composite score</span></div>
    <div style="font-size:15px;color:var(--t2);margin-bottom:14px;line-height:1.7">
      <b>How is this calculated?</b><br>
      Artists are ranked by a composite acquisition score, combining Spotify monthly listeners, iTunes worldwide chart performance, number of tracks charting, and recent momentum. The score reflects cross-platform commercial signals and is updated daily.
    </div>
    <div id="leaderboard"></div>
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

function _jsAcqScore(peakMl, bestItRank, trackCount, bestSpRank, momentum) {
    const mlScore = Math.min(100, Math.floor(peakMl / 1000000));
    const itunesBonus = bestItRank ? Math.max(0, 60 - bestItRank) : 0;
    const chartBonus = Math.min(40, trackCount * 4) + (bestSpRank ? Math.max(0, 50 - bestSpRank) : 0);
    const momentumBonus = Math.max(-40, Math.min(60, Math.floor(momentum)));
    return Math.max(0, mlScore + itunesBonus + chartBonus + momentumBonus);
}
function _jsSignal(score, momentum, bestRank) {
    if (bestRank && bestRank <= 10 && momentum >= 5) return ["STRONG BUY", "sb-buy"];
    if (score >= 140 && momentum >= 0) return ["STRONG BUY", "sb-buy"];
    if (bestRank && bestRank <= 30) return ["WATCH", "sb-watch"];
    if (momentum <= -25) return ["CAUTION", "sb-caution"];
    return ["WATCH", "sb-watch"];
}

function setTimeWindow(label, el) {
    currentTimeWindowDays = label === '1 Day' ? 1 : label === '7 Days' ? 7 : 30;
    document.querySelectorAll('.filter-grp button').forEach(btn => btn.classList.remove('on'));
    el.classList.add('on');
    recalculateAll();
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
        const firstMl = mlClean.length ? mlClean[0] : 0;
        const lastMl = mlClean.length ? mlClean[mlClean.length - 1] : 0;
        const mom = firstMl ? ((lastMl - firstMl) / firstMl * 100) : 0.0;
        
        const ranksClean = itR.filter(r => r !== null && r > 0);
        const bestIt = ranksClean.length ? Math.min(...ranksClean) : null;
        
        const bestSp = (a.bestSpRank && a.bestSpRank !== '—') ? parseInt(a.bestSpRank) : null;
        const score = _jsAcqScore(peakMl, bestIt, parseInt(a.trackCount), bestSp, mom);
        const [sigTxt, sigCls] = _jsSignal(score, mom, bestIt || bestSp);
        
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
  font:{family:'Inter,system-ui,sans-serif',color:'#cdd6e4',size:11},
  margin:{l:48,r:18,t:10,b:58},
  hoverlabel:{bgcolor:getComputedStyle(document.documentElement).getPropertyValue('--bg2').trim()||'#FFFFFF',bordercolor:getComputedStyle(document.documentElement).getPropertyValue('--border2').trim()||'#3a4661',font:{color:getComputedStyle(document.documentElement).getPropertyValue('--t1').trim()||'#1A1A1A',size:12}},
  showlegend:false,
  xaxis:{gridcolor:'rgba(255,255,255,0.05)',zerolinecolor:'rgba(255,255,255,0.08)',tickfont:{color:getComputedStyle(document.documentElement).getPropertyValue('--t3').trim()||'#8b95ad'},linecolor:'rgba(255,255,255,0.08)'},
  yaxis:{gridcolor:'rgba(255,255,255,0.05)',zerolinecolor:'rgba(255,255,255,0.08)',tickfont:{color:getComputedStyle(document.documentElement).getPropertyValue('--t3').trim()||'#8b95ad'},linecolor:'rgba(255,255,255,0.08)'}
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
    tickfont:{color:'#9aa5bd', size:10},
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
renderLeaderboard();

selectArtist(PAYLOAD.defaultArtist);
window.addEventListener('load',()=>{ try{ selectArtist(PAYLOAD.defaultArtist); }catch(e){console.error(e);} });
</script>
</body></html>
""".replace("__PAYLOAD__", data_json).replace("__THEME__", theme_css)


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
