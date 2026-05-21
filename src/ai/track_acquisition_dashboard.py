"""
Track Acquisition dashboard — track-level acquisition signals from
Spotify Global + iTunes WW daily chart data.
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

WINDOW_DAYS = 13


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


@st.cache_data(ttl=300, show_spinner=False)
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
    rank_score = max(0, 40 - (best_rank or 100) * 0.4) if best_rank else 0
    stream_score = min(30, int(latest_streams / 300_000))
    momentum_score = max(-10, min(20, int(momentum)))
    itunes_bonus = 10 if best_it_rank and best_it_rank <= 25 else 5 if best_it_rank and best_it_rank <= 60 else 0
    return max(0, min(100, int(rank_score + stream_score + momentum_score + itunes_bonus)))


def _build_track_rows(sp_df: pd.DataFrame, it_df: pd.DataFrame, dates: list[date], region: str = "Global") -> list[dict[str, Any]]:
    sp_by_track = {name: group for name, group in sp_df.groupby("artist_title")} if not sp_df.empty else {}
    it_by_track = {name: group for name, group in it_df.groupby("artist_title")} if not it_df.empty else {}

    tracks: list[dict[str, Any]] = []
    seen = set()
    for track in sorted(set(sp_by_track) | set(it_by_track)):
        if not track or track in seen:
            continue
        seen.add(track)
        sp_group = sp_by_track.get(track, pd.DataFrame(columns=sp_df.columns))
        it_group = it_by_track.get(track, pd.DataFrame(columns=it_df.columns))
        artist, title = _split_at(track)
        label = "Independent"
        if not sp_group.empty and "label" in sp_group.columns:
            label_series = sp_group["label"].dropna()
            if not label_series.empty:
                label = str(label_series.mode().iat[0])
        date_to_stream = {row["date"]: int(row["metric"] or 0) for _, row in sp_group.iterrows()}
        date_to_sp_rank = {row["date"]: int(row["rank"]) for _, row in sp_group.iterrows()}
        date_to_it_score = {row["date"]: int(row["metric"] or 0) for _, row in it_group.iterrows()}
        date_to_it_rank = {row["date"]: int(row["rank"]) for _, row in it_group.iterrows()}

        sp_streams = [date_to_stream.get(d, 0) for d in dates]
        sp_ranks = [date_to_sp_rank.get(d) if d in date_to_sp_rank else None for d in dates]
        it_scores = [date_to_it_score.get(d, 0) for d in dates]
        it_ranks = [date_to_it_rank.get(d) if d in date_to_it_rank else None for d in dates]

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
            "bestRank": best_sp_rank or (best_it_rank or 0),
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
        "windowLabel": f"{len(tracks)} tracks · {len(dates)} days · {dates[0].strftime('%b %d')} – {dates[-1].strftime('%b %d, %Y')}",
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


def render_track_acquisition() -> None:
    st.markdown(
        "<div style='font-size:0.85rem;color:#97a3c5;margin:-0.5rem 0 0.75rem 0'>"
        "Track-level acquisition intelligence using Spotify Global/US + iTunes WW daily chart data."
        "</div>",
        unsafe_allow_html=True,
    )

    days = st.radio("Time window", ["7 Days", "14 Days", "30 Days"], index=0, horizontal=True, key="track_acq_period")
    if days == "7 Days":
        window_days = 7
    elif days == "14 Days":
        window_days = 14
    else:
        window_days = 30

    sp_global_df = _load_window("spotify_daily", "global", window_days)
    sp_us_df = _load_window("spotify_daily", "us", window_days)
    it_df = _load_window("itunes_daily", "ww", window_days)

    if sp_global_df.empty and sp_us_df.empty and it_df.empty:
        st.warning("No daily chart data available to build the track acquisition view.")
        return

    date_set = set()
    if not sp_global_df.empty:
        date_set.update(sp_global_df["date"].tolist())
    if not sp_us_df.empty:
        date_set.update(sp_us_df["date"].tolist())
    if not it_df.empty:
        date_set.update(it_df["date"].tolist())
    if not date_set:
        st.warning("No chart dates found in the selected window.")
        return

    dates = sorted(date_set)
    global_tracks = _build_track_rows(sp_global_df, it_df, dates, region="Global")
    us_tracks = _build_track_rows(sp_us_df, it_df, dates, region="US")

    if not global_tracks and not us_tracks:
        st.warning("No track acquisition rows could be built from the available chart data.")
        return

    payload = _build_payload(global_tracks, dates, region_label="Spotify Global")
    us_payload = _build_payload(us_tracks, dates, region_label="Spotify US")

    payload["usTracks"] = us_tracks
    payload["usSummary"] = us_payload.get("summary", {})

    html = _build_html(payload)
    st_components.html(html, height=1700, scrolling=True)


def _build_html(payload: dict[str, Any]) -> str:
    data_json = json.dumps(payload, default=str)
    return """
<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--bg2:#161b26;--bg3:#1f2633;--bg4:#283041;
  --border:#2a3446;--border2:#3a4661;
  --t1:#ffffff;--t2:#cdd6e4;--t3:#8b95ad;--t4:#5b657d;
  --green:#34d399;--gd:rgba(52,211,153,.18);
  --red:#fb7185;--rd:rgba(251,113,133,.18);
  --blue:#60a5fa;--bd:rgba(96,165,250,.18);
  --purple:#c4b5fd;--pd:rgba(196,181,253,.18);
  --amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;
}
body{background:var(--bg);font-family:'Inter',system-ui,sans-serif;color:var(--t1);font-size:13px;line-height:1.55}
.hdr{background:linear-gradient(180deg,#1a2235 0%,var(--bg2) 100%);border-bottom:1px solid var(--border);padding:20px 24px 16px}
.hdr-top{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.brand{font-size:11px;color:var(--t3);letter-spacing:1.4px;text-transform:uppercase;display:flex;align-items:center;gap:7px;margin-bottom:6px;font-weight:600}
.live{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
.dash-title{font-size:26px;font-weight:700;letter-spacing:-.5px;color:#fff}
.dash-sub{font-size:12px;color:var(--t2);letter-spacing:.3px;margin-top:4px;font-weight:500}
.filter-bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.filter-grp{display:flex;gap:3px;background:var(--bg3);padding:4px;border-radius:8px;border:1px solid var(--border2)}
.fp{font-size:13px;font-weight:600;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;background:transparent;color:var(--t3);transition:.15s;letter-spacing:.3px}
.fp:hover{color:var(--t1)}
.fp.on{background:var(--bg4);color:#fff}
.sel-wrap{position:relative}
.sel-wrap select{background:var(--bg3);border:1px solid var(--border2);color:var(--t2);font-size:13px;padding:8px 32px 8px 14px;border-radius:6px;cursor:pointer;appearance:none;font-family:inherit;letter-spacing:.3px;font-weight:600}
.sel-wrap::after{content:'▾';position:absolute;right:12px;top:50%;transform:translateY(-50%);color:var(--t3);pointer-events:none;font-size:14px}
.search-wrap{position:relative;flex:1;min-width:180px;max-width:280px}
.search-wrap input{width:100%;background:var(--bg3);border:1px solid var(--border2);color:var(--t1);font-size:13px;padding:8px 14px 8px 34px;border-radius:6px;font-family:inherit;outline:none}
.search-wrap input::placeholder{color:var(--t3)}
.search-wrap::before{content:'⌕';position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--t3);font-size:16px;pointer-events:none}
.kpi-bar{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;padding:16px 24px;background:var(--bg)}
.kpi{position:relative;background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:18px 18px 16px 22px;box-shadow:0 12px 24px rgba(0,0,0,.18);overflow:hidden;transition:transform .2s ease,border-color .2s ease,background-color .2s ease}
.kpi:hover{transform:translateY(-2px);border-color:rgba(148,163,184,.3);background:var(--bg3)}
.kpi::before{content:"";position:absolute;left:0;top:14%;bottom:14%;width:4px;border-radius:0 4px 4px 0;background:var(--blue)}
.kpi.k-green::before{background:var(--green)}
.kpi.k-amber::before{background:var(--amber)}
.kpi.k-purple::before{background:var(--purple)}
.kpi.k-blue::before{background:var(--blue)}
.kpi.k-red::before{background:var(--red)}
.kpi-lbl{font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--t3);margin-bottom:10px}
.kpi-val{font-size:28px;font-weight:900;color:#fff;line-height:1.1;margin-bottom:6px;letter-spacing:-.01em}
#kpi-fastest{font-size:14px;font-weight:800;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#fff;margin-top:4px}
.g{color:var(--green)}.r{color:var(--red)}.b{color:var(--blue)}.p{color:var(--purple)}.a{color:var(--amber)}
.kpi-sub{font-size:12px;color:var(--t2);font-weight:500;line-height:1.35}
.main-grid{display:grid;grid-template-columns:1fr 500px;gap:0;height:calc(100vh - 200px);min-height:580px}
.left-panel{border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.right-panel{display:flex;flex-direction:column;overflow:hidden;background:var(--bg2)}
.tbl-controls{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:6px;flex-wrap:wrap;background:var(--bg2)}
.tbl-controls-r{margin-left:auto;display:flex;align-items:center;gap:6px}
.sort-btn{font-size:10px;color:var(--t3);padding:4px 10px;border:1px solid var(--border2);border-radius:4px;cursor:pointer;background:transparent;white-space:nowrap;transition:.1s;font-weight:600}
.sort-btn.on{color:var(--t1);border-color:var(--blue);background:rgba(96,165,250,.1)}
.count-badge{font-size:10px;color:var(--t2);background:var(--bg3);padding:3px 8px;border-radius:4px;border:1px solid var(--border);font-weight:500}
.tbl-hdr{display:grid;gap:6px;padding:8px 16px;border-bottom:1px solid var(--border2);background:var(--bg2)}
.tbl-hdr span{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;cursor:pointer;font-weight:600}
.tbl-hdr span:hover{color:var(--t2)}
.tbl-body{flex:1;overflow-y:auto}
.tbl-body::-webkit-scrollbar{width:5px}
.tbl-body::-webkit-scrollbar-track{background:transparent}
.tbl-body::-webkit-scrollbar-thumb{background:var(--border2);border-radius:5px}
.track-row{display:grid;gap:8px;padding:12px 16px;border-bottom:1px solid var(--border);cursor:pointer;transition:.1s;align-items:center}
.track-row:hover{background:var(--bg3)}
.track-row.selected{background:var(--bg3);border-left:3px solid var(--blue);padding-left:13px}
.tr-num{font-size:13px;color:var(--t3);text-align:right;min-width:20px;font-weight:600}
.tr-info{overflow:hidden}
.tr-title{font-size:14px;font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-.1px}
.tr-artist{font-size:11px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px;font-weight:500}
.tr-val{font-size:13px;color:var(--t1);text-align:right;white-space:nowrap;font-weight:600;font-variant-numeric:tabular-nums}
.tr-val.g{color:var(--green)}.tr-val.r{color:var(--red)}
.spark{display:flex;align-items:flex-end;gap:1px;height:20px;margin-top:4px}
.spark-bar{width:4px;border-radius:2px;min-height:2px}
.sig{display:inline-flex;align-items:center;font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:.4px;white-space:nowrap}
.sig-buy{background:var(--gd);color:var(--green);border:1px solid rgba(52,211,153,.35)}
.sig-watch{background:var(--bd);color:var(--blue);border:1px solid rgba(96,165,250,.35)}
.sig-hold{background:var(--bg3);color:var(--t2);border:1px solid var(--border2)}
.sig-pass{background:var(--rd);color:var(--red);border:1px solid rgba(251,113,133,.35)}
.detail-hdr{padding:20px 22px 16px;border-bottom:1px solid var(--border);background:var(--bg2);flex-shrink:0}
.detail-accent{height:3px;background:linear-gradient(90deg,var(--green),var(--teal));margin:-20px -22px 16px;margin-bottom:16px}
.detail-title{font-size:18px;font-weight:700;letter-spacing:-.3px;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fff}
.detail-artist{font-size:12px;color:var(--t2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px;font-weight:600}
.detail-label-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.pill-lbl{font-size:10px;color:var(--t2);padding:4px 10px;border-radius:12px;border:1px solid var(--border2);background:var(--bg3);font-weight:600}
.detail-stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}
.ds{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px 14px}
.ds-l{font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;font-weight:600}
.ds-v{font-size:18px;font-weight:700;letter-spacing:-.3px;color:#fff}
.ds-s{font-size:10px;color:var(--t2);margin-top:3px;font-weight:500}
.detail-body{flex:1;overflow-y:auto;padding:16px 22px}
.detail-body::-webkit-scrollbar{width:5px}
.detail-body::-webkit-scrollbar-thumb{background:var(--border2);border-radius:5px}
.section-mini{margin-bottom:20px}
.section-mini-title{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border);font-weight:600}
.dual-legend{display:flex;gap:14px;margin-bottom:10px}
.dl-item{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--t2);font-weight:500}
.dl-dot{width:12px;height:3px;border-radius:1px}
.sig-item{display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)}
.sig-item:last-child{border-bottom:none}
.sig-icon{font-size:16px;flex-shrink:0;margin-top:2px}
.sig-text{flex:1}
.sig-title{font-size:13px;font-weight:600;color:var(--t1);margin-bottom:3px}
.sig-desc{font-size:12px;color:var(--t2);line-height:1.55}
.score-ring{display:flex;align-items:center;gap:14px;background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:14px 18px;margin-bottom:16px}
.ring-num{font-size:32px;font-weight:700;letter-spacing:-.5px;color:#fff}
.ring-info{flex:1}
.ring-lbl{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px;font-weight:600}
.ring-bar-bg{height:6px;background:var(--bg4);border-radius:3px;overflow:hidden}
.ring-bar-fg{height:6px;border-radius:3px;transition:.4s}
.ring-sub{font-size:11px;color:var(--t2);margin-top:6px;font-weight:500}
</style>
</head><body>

<!-- Header -->
<div class="hdr">
  <div class="hdr-top">
    <div>
      <div class="dash-title">Track Acquisition</div>
      <div class="dash-sub" id="hdr-sub"></div>
    </div>
    <div class="filter-bar">
      <div class="search-wrap">
        <input type="text" id="searchInput" placeholder="Search track or artist..." oninput="applyFilters()">
      </div>
      <div class="sel-wrap">
        <select id="regionSel" onchange="changeRegion()">
          <option value="global">Global Stats</option>
          <option value="us">United States Stats</option>
        </select>
      </div>
      <div class="sel-wrap">
        <select id="platformSel" onchange="applyFilters()">
          <option value="all">All Platforms</option>
          <option value="spotify">Spotify Only</option>
          <option value="itunes">iTunes Only</option>
          <option value="cross">Cross-Platform</option>
        </select>
      </div>
      <div class="sel-wrap">
        <select id="signalSel" onchange="applyFilters()">
          <option value="all">All Signals</option>
          <option value="BUY">Strong Buy</option>
          <option value="WATCH">Watch</option>
          <option value="HOLD">Hold</option>
          <option value="PASS">Pass</option>
        </select>
      </div>
      <div class="filter-grp">
        <button class="fp on" onclick="setPeriod('all',this)">All</button>
        <button class="fp" onclick="setPeriod('rising',this)">Rising</button>
        <button class="fp" onclick="setPeriod('stable',this)">Stable</button>
        <button class="fp" onclick="setPeriod('falling',this)">Falling</button>
      </div>
    </div>
  </div>
</div>

<!-- KPI Bar -->
<div class="kpi-bar">
  <div class="kpi k-green"><div class="kpi-lbl">Strong Buy tracks</div><div class="kpi-val g" id="kpi-buy">—</div><div class="kpi-sub">of tracked tracks</div></div>
  <div class="kpi k-amber"><div class="kpi-lbl">Top acquisition score</div><div class="kpi-val a" id="kpi-top-score">—</div><div class="kpi-sub" id="kpi-top-title">—</div></div>
  <div class="kpi k-purple"><div class="kpi-lbl">Fastest rising track</div><div class="kpi-val" id="kpi-fastest">—</div><div class="kpi-sub" id="kpi-fastest-sub">—</div></div>
  <div class="kpi k-blue"><div class="kpi-lbl">Cross-platform tracks</div><div class="kpi-val b" id="kpi-cross">—</div><div class="kpi-sub">on both Spotify + iTunes WW</div></div>
  <div class="kpi k-red"><div class="kpi-lbl">Avg momentum</div><div class="kpi-val p" id="kpi-momentum">—</div><div class="kpi-sub">across tracked tracks</div></div>
</div>

<!-- Main Grid -->
<div class="main-grid">
  <div class="left-panel">
    <div class="tbl-controls">
      <span class="count-badge" id="count-badge">— tracks</span>
      <div class="tbl-controls-r">
        <span style="font-size:9px;color:var(--t3)">Sort by:</span>
        <button class="sort-btn on" onclick="setSort('acq',this)">Acq Score</button>
        <button class="sort-btn" onclick="setSort('momentum',this)">Momentum</button>
        <button class="sort-btn" onclick="setSort('rank',this)">Rank</button>
        <button class="sort-btn" onclick="setSort('streams',this)">Streams</button>
        <button class="sort-btn" onclick="setSort('growth',this)">Growth %</button>
      </div>
    </div>
    <div class="tbl-hdr" style="grid-template-columns:24px 1fr 50px 70px 80px 100px 75px">
      <span>#</span><span>Track · Artist</span><span style="text-align:right">Rank</span>
      <span style="text-align:right">Streams</span><span style="text-align:right">Momentum</span>
      <span style="text-align:right;padding-right:12px">Signal</span><span style="text-align:right">Acq Score</span>
    </div>
    <div class="tbl-body" id="track-table"></div>
  </div>
  <div class="right-panel">
    <div class="detail-hdr" id="detail-hdr">
      <div class="detail-accent" id="detail-accent"></div>
      <div class="detail-title" id="detail-title">Select a track</div>
      <div class="detail-artist" id="detail-artist">Click any row to view acquisition profile</div>
      <div class="detail-label-row" id="detail-labels"></div>
      <div class="detail-stats" id="detail-stats"></div>
    </div>
    <div class="detail-body">
      <div class="score-ring" id="score-ring" style="display:none">
        <div>
          <div class="ring-lbl">Acquisition score</div>
          <div class="ring-num" id="ring-num">—</div>
          <div class="sig" id="ring-sig" style="margin-top:4px">—</div>
        </div>
        <div class="ring-info" style="flex:1;padding-left:10px">
          <div class="ring-bar-bg"><div class="ring-bar-fg" id="ring-bar" style="width:0%"></div></div>
          <div class="ring-sub" id="ring-sub"></div>
        </div>
      </div>
      <div class="section-mini" id="chart-section" style="display:none">
        <div class="section-mini-title">stream + rank trajectory</div>
        <div class="dual-legend">
          <span class="dl-item"><span class="dl-dot" style="background:var(--green)"></span>Streams</span>
          <span class="dl-item"><span class="dl-dot" style="background:var(--purple)"></span>Rank (right axis)</span>
        </div>
        <div class="cw" style="height:220px"><canvas id="detailChart" role="img" aria-label="Selected track stream and rank trajectory over time."></canvas></div>
      </div>
      <div class="section-mini" id="it-chart-section" style="display:none">
        <div class="section-mini-title">iTunes WW — score trajectory</div>
        <div class="cw" style="height:220px"><canvas id="detailItChart" role="img" aria-label="Selected track iTunes WW score trajectory."></canvas></div>
      </div>
      <div class="section-mini" id="signals-section" style="display:none">
        <div class="section-mini-title">Acquisition signals</div>
        <div id="signals-list"></div>
      </div>
      <div id="empty-state" style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:300px;color:var(--t3);text-align:center;gap:8px">
        <div style="font-size:28px">↑</div>
        <div style="font-size:12px">Select a track from the list<br>to view its acquisition profile</div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const PAYLOAD = __PAYLOAD__;
const DATES = PAYLOAD.dates;
let TRACKS = PAYLOAD.tracks;
let SUM = PAYLOAD.summary || {};

function updateKPIs(sum) {
  if (!sum) return;
  document.getElementById('kpi-buy').textContent = sum.strongBuy !== undefined ? sum.strongBuy : '—';
  document.getElementById('kpi-top-score').textContent = sum.topScore !== undefined ? sum.topScore : '—';
  document.getElementById('kpi-top-title').textContent = sum.topTitle || '—';
  document.getElementById('kpi-fastest').textContent = sum.fastest || '—';
  document.getElementById('kpi-fastest-sub').textContent = sum.fastestSub || '—';
  document.getElementById('kpi-cross').textContent = sum.crossCount !== undefined ? sum.crossCount : '—';
  document.getElementById('kpi-momentum').textContent = sum.avgMomentum !== undefined ? `${sum.avgMomentum > 0 ? '+' : ''}${sum.avgMomentum}%` : '—';
}

if (SUM) {
  document.getElementById('hdr-sub').textContent = PAYLOAD.windowLabel || '';
  updateKPIs(SUM);
}

let currentSort='acq';
let currentPeriod='all';
let selectedId=PAYLOAD.defaultTrackId;
let detailChart=null;
let detailItChart=null;

function changeRegion() {
  const r = document.getElementById('regionSel').value;
  TRACKS = r === 'global' ? PAYLOAD.tracks : PAYLOAD.usTracks;
  const sum = r === 'global' ? PAYLOAD.summary : PAYLOAD.usSummary;
  PAYLOAD.regionLabel = r === 'global' ? 'Spotify Global' : 'Spotify US';
  updateKPIs(sum);
  
  selectedId = TRACKS[0]?.id;
  renderTable();
  if (selectedId) {
    selectTrack(selectedId);
  } else {
    document.getElementById('empty-state').style.display = 'flex';
    document.getElementById('score-ring').style.display = 'none';
    document.getElementById('chart-section').style.display = 'none';
    document.getElementById('it-chart-section').style.display = 'none';
    document.getElementById('signals-section').style.display = 'none';
  }
}

function fmtN(n,d=1){if(!n&&n!==0)return'—';const a=Math.abs(n);if(a>=1e6)return(n/1e6).toFixed(d)+'M';if(a>=1e3)return(n/1e3).toFixed(0)+'K';return Math.round(n).toString();}
function signalClass(s){return{BUY:'sig-buy',WATCH:'sig-watch',HOLD:'sig-hold',PASS:'sig-pass'}[s]||'sig-hold';}
function signalLabel(s){return{BUY:'STRONG BUY',WATCH:'WATCH',HOLD:'HOLD',PASS:'PASS'}[s]||s;}
function buildSpark(streams,color){const valid=streams.filter(v=>v&&v>0);if(!valid.length)return'<span style="color:var(--t3);font-size:9px">—</span>';const mx=Math.max(...valid);const mn=Math.min(...valid);return`<div class="spark">${streams.slice(-8).map(s=>{const pct=mx===mn?50:Math.round((s-mn)/(mx-mn)*100);const h=Math.max(2,Math.round(pct/100*18));const c=s>=valid[0]?color:'var(--t3)';return`<div class="spark-bar" style="height:${h}px;background:${c}"></div>`}).join('')}</div>`;}
function renderTable(){const q=document.getElementById('searchInput').value.toLowerCase();const plat=document.getElementById('platformSel').value;const sig=document.getElementById('signalSel').value;let data=[...TRACKS];if(q) data=data.filter(t=>t.title.toLowerCase().includes(q)||t.artist.toLowerCase().includes(q));if(plat!=='all') data=data.filter(t=>t.platform===plat);if(sig!=='all') data=data.filter(t=>t.signal===sig);if(currentPeriod==='rising') data=data.filter(t=>t.momentum>0);if(currentPeriod==='stable') data=data.filter(t=>Math.abs(t.momentum)<=5);if(currentPeriod==='falling') data=data.filter(t=>t.momentum<0);const sortMap={acq:'acqScore',momentum:'momentum',rank:'bestRank',streams:'latestStreams',growth:'growth'};const key=sortMap[currentSort]||'acqScore';const asc=key==='bestRank';data.sort((a,b)=>asc?a[key]-b[key]:b[key]-a[key]);document.getElementById('count-badge').textContent=`${data.length} track${data.length!==1?'s':''}`;const displayData=data;const el=document.getElementById('track-table');let htmlStr='';displayData.forEach((t,i)=>{const momColor=t.momentum>5?'g':t.momentum<-5?'r':'';const spark=buildSpark(t.spStreams,t.acqColor);htmlStr+=`<div class="track-row${t.id===selectedId?' selected':''}" style="grid-template-columns:24px 1fr 50px 70px 80px 100px 75px" onclick="selectTrack(${t.id})"><span class="tr-num">${i+1}</span><div class="tr-info"><div class="tr-title">${t.title}</div><div class="tr-artist">${t.artist} ${t.platform==='cross'?'<span style="color:var(--teal);font-size:8px">✦ cross</span>':''}</div>${spark}</div><span class="tr-val">#${t.bestRank}</span><span class="tr-val">${fmtN(t.latestStreams)}</span><span class="tr-val ${momColor}">${t.momentum>0?'+':''}${t.momentum}%</span><span style="text-align:right;padding-right:12px"><span class="sig ${signalClass(t.signal)}">${signalLabel(t.signal)}</span></span><span class="tr-val a">${t.acqScore}</span></div>`;});el.innerHTML=htmlStr;}
function selectTrack(id){selectedId=id;const t=TRACKS.find(x=>x.id===id);if(!t)return;renderTable();document.getElementById('empty-state').style.display='none';document.getElementById('detail-title').textContent=t.title;document.getElementById('detail-artist').textContent=t.artist.toUpperCase()+' · '+t.label.toUpperCase();document.getElementById('detail-accent').style.background=`linear-gradient(90deg,${t.acqColor},#2dd4bf)`;const labelRow=document.getElementById('detail-labels');const crossBadge=t.platform==='cross'?'<span class="pill-lbl" style="color:var(--teal);border-color:rgba(45,212,191,.3)">✦ Cross-platform</span>':'';const indBadge=t.label.toLowerCase().includes('independ')?'<span class="pill-lbl" style="color:var(--green);border-color:rgba(34,197,94,.3)">Independent</span>':'';labelRow.innerHTML=`<span class="pill-lbl">${t.label}</span><span class="pill-lbl">${t.platform.toUpperCase()}</span>${crossBadge}${indBadge}<span class="sig ${signalClass(t.signal)}">${signalLabel(t.signal)}</span>`;const statData=[{l:'Best Rank',v:`#${t.bestRank}`,s:PAYLOAD.regionLabel||'Spotify Global',vc:''},{l:'Latest Streams',v:fmtN(t.latestStreams,1),s:`${t.growth>0?'+':''}${t.growth}% growth`,vc:t.growth>0?'g':'r'},{l:'Momentum',v:`${t.momentum>0?'+':''}${t.momentum}%`,s:'Window change',vc:t.momentum>0?'g':'r'},{l:'Window Days',v:t.days,s:'days in chart',vc:''}];document.getElementById('detail-stats').innerHTML=statData.map(s=>`<div class="ds"><div class="ds-l">${s.l}</div><div class="ds-v ${s.vc}">${s.v}</div><div class="ds-s">${s.s}</div></div>`).join('');const ring=document.getElementById('score-ring');ring.style.display='flex';document.getElementById('ring-num').textContent=t.acqScore;document.getElementById('ring-num').className=`ring-num ${t.momentum>0?'g':''}`;const sigEl=document.getElementById('ring-sig');sigEl.className=`sig ${signalClass(t.signal)}`;sigEl.textContent=signalLabel(t.signal);const pct=Math.round(t.acqScore);document.getElementById('ring-bar').style.cssText=`width:${pct}%;background:${t.acqColor}`;document.getElementById('ring-sub').textContent=`Ranked #${TRACKS.sort((a,b)=>b.acqScore-a.acqScore).findIndex(x=>x.id===id)+1} of ${TRACKS.length} tracked tracks`;const chartSection=document.getElementById('chart-section');chartSection.style.display='block';const spCtx=document.getElementById('detailChart').getContext('2d');if(detailChart)detailChart.destroy();detailChart=new Chart(spCtx,{type:'line',data:{labels:DATES,datasets:[{label:'Streams',data:t.spStreams,borderColor:t.acqColor,backgroundColor:t.acqColor+'10',borderWidth:2,tension:.4,fill:true,pointBackgroundColor:t.acqColor,pointRadius:3,yAxisID:'y',spanGaps:true},{label:'Rank',data:t.spRanks,borderColor:'rgba(167,139,250,.7)',borderDash:[4,2],borderWidth:1.5,tension:.3,fill:false,pointBackgroundColor:'#a78bfa',pointRadius:2,yAxisID:'y1',spanGaps:true}]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.datasetIndex===0?`${c.raw?.toLocaleString()} streams`:`Rank #${c.raw}`}}},scales:{x:{grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#444',font:{size:9}}},y:{position:'left',grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:t.acqColor,font:{size:9},callback:v=>fmtN(v,0).replace('+','')}},y1:{position:'right',reverse:true,grid:{display:false},ticks:{color:'#a78bfa',font:{size:9},callback:v=>'#'+v}}}}});const itSection=document.getElementById('it-chart-section');const hasIt=t.itScores&&t.itScores.some(v=>v&&v>0);itSection.style.display=hasIt?'block':'none';if(hasIt){const itCtx=document.getElementById('detailItChart').getContext('2d');if(detailItChart)detailItChart.destroy();detailItChart=new Chart(itCtx,{type:'line',data:{labels:DATES,datasets:[{label:'iTunes Score',data:t.itScores,borderColor:'#a78bfa',backgroundColor:'rgba(167,139,250,.08)',borderWidth:2,tension:.4,fill:true,pointBackgroundColor:'#a78bfa',pointRadius:3,spanGaps:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.raw?`Score: ${c.raw.toLocaleString()}`:'Not charting'}}},scales:{x:{grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#444',font:{size:9}}},y:{grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#a78bfa',font:{size:9},callback:v=>fmtN(v,0).replace('+','')}}}}});}document.getElementById('signals-section').style.display='block';document.getElementById('signals-list').innerHTML=t.signals.map(s=>`<div class="sig-item"><span class="sig-icon">${s.icon}</span><div class="sig-text"><div class="sig-title">${s.t}</div><div class="sig-desc">${s.d}</div></div></div>`).join('');}
function setSort(s,el){currentSort=s;document.querySelectorAll('.sort-btn').forEach(b=>b.classList.remove('on'));el.classList.add('on');renderTable();}
function setPeriod(p,el){currentPeriod=p;document.querySelectorAll('.fp').forEach(b=>b.classList.remove('on'));el.classList.add('on');renderTable();}
function applyFilters(){renderTable();}
renderTable();setTimeout(()=>selectTrack(PAYLOAD.defaultTrackId),80);
</script>
</body></html>
""".replace("__PAYLOAD__", data_json)
