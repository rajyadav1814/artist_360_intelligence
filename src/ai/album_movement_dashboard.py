"""
Album Movement dashboard — rich HTML/JS dashboard rendering rank + metric
momentum for iTunes albums. Pulls dynamic data from the itunes_artist_album
table.
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
from src.utils.ui import custom_selectbox

logger = get_logger(__name__)

# ─────────────────────── theme CSS ──────────────────────────────
_THEME_LIGHT = ":root{--bg:#F5F6FA;--bg2:#FFFFFF;--bg3:#F8F9FB;--bg4:#EEF1F7;--border:rgba(148,163,184,.2);--border2:rgba(148,163,184,.35);--t1:#1A1A1A;--t2:#4A5568;--t3:#8A8FA3;--t4:#A0AEC0;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"
_THEME_DARK  = ":root{--bg:#0d1117;--bg2:#161b26;--bg3:#1f2633;--bg4:#283041;--border:rgba(148,163,184,.15);--border2:rgba(148,163,184,.28);--t1:#ffffff;--t2:#cdd6e4;--t3:#8b95ad;--t4:#6b7a99;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"


# Region scope -> iTunes album country
SCOPES: dict[str, tuple[str, str]] = {
    "Global / WW": ("global", "ww"),
    "United States": ("us", "us"),
}

PERIOD_DAYS: dict[str, int] = {
    "Latest (5d)": 5,
    "7 Days": 7,
    "14 Days": 14,
    "Monthly": 30,
}

PERIOD_LABELS: dict[str, str] = {
    "Latest (5d)": "5-day window",
    "7 Days": "7-day window",
    "14 Days": "14-day window",
    "Monthly": "30-day window",
}


# ───────────────────────── data helpers ──────────────────────────

def _split_at(at: str | None) -> tuple[str, str]:
    if not at:
        return "—", "—"
    if " - " in at:
        artist, title = at.split(" - ", 1)
    else:
        artist, title = at, at
    return artist.strip(), title.strip()


@st.cache_data(ttl=300, show_spinner=False)
def _load_window(table: str, country: str, days: int) -> pd.DataFrame:
    """Load all rows from `table` for the given country within the most recent
    `days`-day window ending on max(date)."""
    metric_col = "points" if table == "itunes_artist_album" else "points"
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
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query, (country, country, days))
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        logger.error("album_movement load_window failed (%s/%s): %s", table, country, e)
        return pd.DataFrame()
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    df["metric"] = pd.to_numeric(df["metric"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _build_track_records(df: pd.DataFrame, dates: list[date], metric_key: str) -> list[dict[str, Any]]:
    """For every artist_title build a record with per-date rank + metric arrays."""
    if df.empty:
        return []
    # Best (lowest) rank per (artist_title, date) — defensive in case duplicates
    grouped = (
        df.sort_values("rank")
        .groupby(["artist_title", "date"], as_index=False)
        .first()
    )
    records: list[dict[str, Any]] = []
    for at, g in grouped.groupby("artist_title"):
        g = g.set_index("date")
        ranks: list[Any] = []
        metrics: list[Any] = []
        for d in dates:
            if d in g.index:
                row = g.loc[d]
                ranks.append(int(row["rank"]) if pd.notna(row["rank"]) else None)
                metrics.append(int(row["metric"]) if pd.notna(row["metric"]) else None)
            else:
                ranks.append(None)
                metrics.append(None)
        # Need start + end values to be useful
        first_rank = next((r for r in ranks if r is not None), None)
        last_rank = next((r for r in reversed(ranks) if r is not None), None)
        first_metric = next((m for m in metrics if m is not None), None)
        last_metric = next((m for m in reversed(metrics) if m is not None), None)
        if first_rank is None or last_rank is None:
            continue
        rg = first_rank - last_rank  # positive = improved
        sg = (last_metric or 0) - (first_metric or 0)
        artist, title = _split_at(at)
        label = g["label"].dropna().iloc[0] if g["label"].notna().any() else None
        records.append({
            "n": artist,
            "t": title,
            "ranks": ranks,
            metric_key: metrics,
            "rg": int(rg),
            "sg": int(sg),
            "lbl": label or "—",
        })
    return records


def _top_n(records: list[dict], n: int, *, risers: bool) -> list[dict]:
    if not records:
        return []
    # Composite score: rank gain weight + normalized metric gain
    max_sg = max((abs(r["sg"]) for r in records), default=1) or 1
    for r in records:
        r["_score"] = r["rg"] + (r["sg"] / max_sg) * 50
    if risers:
        filtered = [r for r in records if r["rg"] > 0 or r["sg"] > 0]
        filtered.sort(key=lambda r: r["_score"], reverse=True)
    else:
        filtered = [r for r in records if r["rg"] < 0 or r["sg"] < 0]
        filtered.sort(key=lambda r: r["_score"])
    out = []
    for r in filtered[:n]:
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        out.append(c)
    return out


def _consistent_records(records: list[dict], n: int, metric_key: str) -> list[dict[str, Any]]:
    """Rank albums by repeated chart presence, rank quality, and point volume."""
    rows: list[dict[str, Any]] = []
    for r in records:
        ranks = [x for x in r.get("ranks", []) if x is not None]
        metrics = [x for x in r.get(metric_key, []) if x is not None]
        if not ranks:
            continue
        total_metric = int(sum(metrics))
        rows.append({
            "n": r["n"],
            "t": r["t"],
            "lbl": r.get("lbl", "—"),
            "days": len(ranks),
            "best": int(min(ranks)),
            "avg": round(sum(ranks) / len(ranks), 1),
            "latest": int(metrics[-1]) if metrics else 0,
            "total": total_metric,
        })
    if not rows:
        return []
    max_total = max((r["total"] for r in rows), default=1) or 1
    for r in rows:
        rank_quality = max(0, 250 - r["avg"])
        metric_quality = (r["total"] / max_total) * 1000
        r["score"] = int((r["days"] * 1000) + (rank_quality * 8) + metric_quality)
    rows.sort(key=lambda r: (r["score"], r["days"], -r["avg"]), reverse=True)
    return rows[:n]


def _top20_today(df: pd.DataFrame, latest: date) -> list[dict[str, Any]]:
    today = df[df["date"] == latest].copy()
    if today.empty:
        return []
    # Find previous date for change computation
    prev_dates = sorted([d for d in df["date"].unique() if d < latest])
    prev = prev_dates[-1] if prev_dates else None
    prev_df = df[df["date"] == prev] if prev is not None else pd.DataFrame()
    prev_metric_map = dict(zip(prev_df["artist_title"], prev_df["metric"])) if not prev_df.empty else {}
    prev_rank_map = dict(zip(prev_df["artist_title"], prev_df["rank"])) if not prev_df.empty else {}
    today = today.sort_values("rank").head(20)
    out: list[dict[str, Any]] = []
    for _, row in today.iterrows():
        artist, title = _split_at(row["artist_title"])
        label = str(row["label"]) if "label" in row and pd.notna(row["label"]) else "—"
        s = int(row["metric"]) if pd.notna(row["metric"]) else 0
        prev_v = prev_metric_map.get(row["artist_title"])
        c = int(s - prev_v) if prev_v is not None and pd.notna(prev_v) else 0
        prev_rank = prev_rank_map.get(row["artist_title"])
        if prev_rank is not None and pd.notna(prev_rank):
            movement: str | int = int(prev_rank - row["rank"])
        else:
            movement = "NEW"
        out.append({
            "rank": int(row["rank"]) if pd.notna(row["rank"]) else None,
            "t": title,
            "a": artist,
            "s": s,
            "c": c,
            "m": movement,
            "lbl": label,
        })
    return out


# ─────────────────────────── render ───────────────────────────────

def render_album_movement(labels_filter: list[str] | None = None) -> None:
    # ── Filter bar ────────────────────────────────────────────────
    c0, c1, c2 = st.columns([1.7, 1.2, 1.2])
    with c0:
        st.markdown(
            "<div style='font-size:0.85rem;color:#97a3c5;padding-top:1.95rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
            "Rank + point momentum across iTunes album charts."
            "</div>",
            unsafe_allow_html=True,
        )
    with c1:
        scope_label = custom_selectbox("Region", list(SCOPES.keys()), index=0, key="am_scope")
    with c2:
        period_label = custom_selectbox("Period", list(PERIOD_DAYS.keys()), index=0, key="am_period")

    _, it_country = SCOPES[scope_label]
    days = PERIOD_DAYS[period_label]

    it_df = _load_window("itunes_artist_album", it_country, days)

    if labels_filter:
        if not it_df.empty and "label" in it_df.columns:
            it_df = it_df[it_df["label"].isin(labels_filter)]

    if it_df.empty:
        st.warning("No daily chart data available for the selected window.")
        return

    # Build aligned date axis
    it_dates = it_df["date"].tolist() if not it_df.empty and "date" in it_df.columns else []
    all_dates = sorted(set(it_dates))
    if not all_dates:
        st.warning("No dates found in window.")
        return

    it_records = _build_track_records(it_df, all_dates, "scores") if not it_df.empty else []

    it_risers = _top_n(it_records, 15, risers=True)
    it_fallers = _top_n(it_records, 15, risers=False)
    it_consistent = _consistent_records(it_records, 15, "scores")

    it_top20 = _top20_today(it_df, all_dates[-1]) if not it_df.empty else []

    # KPIs
    it_no1 = next((t for t in it_top20 if True), None)

    big_rank_riser = max(
        it_risers,
        key=lambda r: r["rg"],
        default=None,
    )
    big_faller = min(
        it_fallers,
        key=lambda r: r["rg"],
        default=None,
    )
    big_score_riser = max(it_risers, key=lambda r: r["sg"], default=None)
    rising_count = sum(1 for r in it_records if r["rg"] > 0)

    # Spotlight = top riser per platform
    it_spot = it_risers[0] if it_risers else None

    date_strs = [d.strftime("%b %d") for d in all_dates]
    window_label = f"{all_dates[0].strftime('%b %d')} - {all_dates[-1].strftime('%b %d, %Y')} · {PERIOD_LABELS[period_label]}"

    payload = {
        "dates": date_strs,
        "window_label": window_label,
        "scope": scope_label,
        "it_risers": it_risers,
        "it_fallers": it_fallers,
        "it_consistent": it_consistent,
        "it_top20": it_top20,
        "it_spot": it_spot,
        "kpis": {
            "it_no1": it_no1,
            "big_rank_riser": big_rank_riser,
            "big_score_riser": big_score_riser,
            "big_faller": big_faller,
            "rising_count": rising_count,
            "tracked": len(it_records),
        },
    }

    html = _build_html(payload, dark_mode=st.session_state.get("dark_mode", True))
    st_components.html(html, height=1040, scrolling=True)


# ─────────────────────────── HTML template ───────────────────────────

def _build_html(payload: dict, dark_mode: bool = False) -> str:
    data_json = json.dumps(payload, default=str)
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    return """
<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
__THEME__
body{background:var(--bg);font-family:'Inter',system-ui,sans-serif;color:var(--t1);font-size:14px;line-height:1.45}
.dash{padding:12px 4px 14px}
.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;gap:12px}
.title{font-size:18px;font-weight:600;color:var(--t1)}
.sub{font-size:12px;color:var(--t2);margin-top:2px}
.tag{font-size:10px;padding:2px 7px;border-radius:4px;font-weight:700;border:1px solid var(--border)}
.pt-it{background:rgba(252,211,77,.16);color:var(--amber)}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-bottom:14px}
.kpi{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px 14px}
.kpi-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.kpi-icon{width:22px;height:22px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center;background:var(--bg3);border:1px solid var(--border);color:var(--blue);flex:0 0 auto}
.kpi-icon svg{width:14px;height:14px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}
.kpi-icon.green{color:var(--green);background:var(--gd)}
.kpi-icon.amber{color:var(--amber);background:rgba(252,211,77,.15)}
.kpi-icon.purple{color:var(--purple);background:var(--pd)}
.kpi-label{font-size:12px;color:var(--t2)}
.kpi-value{font-size:22px;font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi-sub{font-size:11px;color:var(--t3);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tab-bar{display:flex;gap:10px;justify-content:flex-start;margin-bottom:12px;border-bottom:1px solid var(--border);padding:4px 0 10px;overflow-x:auto}
.tab{min-width:132px;padding:8px 14px;font-size:12px;font-weight:700;background:rgba(251,113,133,.10);border:1px solid rgba(251,113,133,.28);border-radius:10px;cursor:pointer;color:var(--t1);white-space:nowrap;text-align:center;transition:background .15s,border-color .15s,box-shadow .15s}
.tab:hover{background:rgba(251,113,133,.14);border-color:rgba(251,113,133,.42)}
.tab.active{background:rgba(251,113,133,.18);border-color:rgba(251,113,133,.55);box-shadow:0 0 0 2px rgba(251,113,133,.08)}
.panel{display:none}.panel.active{display:block}
.tab-desc{font-size:12px;color:var(--t2);line-height:1.45;margin:0 0 10px;max-width:920px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:14px 14px}
.section-label{font-size:11px;font-weight:700;color:var(--t2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;display:flex;align-items:center;gap:7px}
.note{font-size:11px;color:var(--t2);line-height:1.45;margin:-2px 0 12px}
.metric-pill{display:inline-flex;align-items:center;justify-content:center;border-radius:4px;padding:2px 6px;font-size:10px;font-weight:700;background:var(--bg3);color:var(--t2);border:1px solid var(--border)}
.rank-table{width:100%;border-collapse:collapse;font-size:13px}
.rank-table th{text-align:left;font-size:11px;font-weight:700;color:var(--t2);padding:6px 8px;border-bottom:1px solid var(--border)}
.rank-table td{padding:9px 8px;border-bottom:1px solid var(--border);color:var(--t1);vertical-align:middle}
.rank-table tr:last-child td{border-bottom:0}
.rank-table tr:hover td{background:var(--bg3)}
.rank-num{font-size:12px;font-weight:700;color:var(--t2);min-width:22px}
.item-name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px}
.item-sub{font-size:11px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px;margin-top:1px}
.bar-wrap{display:flex;align-items:center;gap:8px;margin-top:4px}
.bar-bg{flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden}
.bar-fill{height:100%;border-radius:3px}
.mv-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px}
.mv-row:last-child{border-bottom:0}
.mv-left{min-width:0;flex:1}
.mv-art{font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mv-trk{color:var(--t2);font-size:11px;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mv-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:5px}
.mv-val{font-size:13px;font-weight:700;min-width:58px;text-align:right;font-variant-numeric:tabular-nums}
.up{color:var(--green)}.dn{color:var(--red)}
.live-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)}
.live-row:last-child{border-bottom:0}
.live-rank{font-size:15px;font-weight:700;min-width:30px;color:var(--t1)}
.live-info{flex:1;min-width:0}
.live-title{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.live-meta{font-size:11px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.live-score{font-size:12px;color:var(--t2);text-align:right;min-width:64px;font-variant-numeric:tabular-nums}
.badge{display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;min-width:34px}
.badge-up{background:var(--gd);color:var(--green)}
.badge-down{background:var(--rd);color:var(--red)}
.badge-eq{background:var(--bg3);color:var(--t2)}
.badge-new{background:var(--bd);color:var(--blue)}
.chart-wrap{position:relative;width:100%;height:300px}
.chart-wrap.consistency-chart{height:440px}
.legend-row{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;font-size:12px;color:var(--t2)}
.legend-item{display:flex;align-items:center;gap:5px;max-width:180px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.legend-dot{width:10px;height:10px;border-radius:2px;flex:0 0 auto}
.empty{color:var(--t3);font-size:12px;padding:12px 0}
@media(max-width:720px){.top{align-items:flex-start;flex-direction:column}.two-col{grid-template-columns:1fr}.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.tab{min-width:118px;padding:8px 12px}}
</style></head><body>
<div class='dash'>
  <div class='kpi-grid'>
    <div class='kpi'><div class='kpi-head'><span class='kpi-icon'><svg viewBox='0 0 24 24'><circle cx='12' cy='12' r='9'/><circle cx='12' cy='12' r='2'/><path d='M12 3v3'/><path d='M21 12h-3'/></svg></span><div class='kpi-label'>Albums tracked</div></div><div class='kpi-value' id='kpi-tracked'>0</div><div class='kpi-sub'>Active movement records</div></div>
    <div class='kpi'><div class='kpi-head'><span class='kpi-icon green'><svg viewBox='0 0 24 24'><path d='M3 17l6-6 4 4 8-8'/><path d='M14 7h7v7'/></svg></span><div class='kpi-label'>Rising albums</div></div><div class='kpi-value up' id='kpi-rising'>0</div><div class='kpi-sub'>Positive rank movement</div></div>
    <div class='kpi'><div class='kpi-head'><span class='kpi-icon amber'><svg viewBox='0 0 24 24'><path d='M12 19V5'/><path d='M5 12l7-7 7 7'/></svg></span><div class='kpi-label'>Top rank riser</div></div><div class='kpi-value' id='kpi-riser'>-</div><div class='kpi-sub' id='kpi-riser-sub'>No movement</div></div>
    <div class='kpi'><div class='kpi-head'><span class='kpi-icon purple'><svg viewBox='0 0 24 24'><path d='M3 3v18h18'/><path d='M7 15l4-4 3 3 5-7'/></svg></span><div class='kpi-label'>Biggest point gain</div></div><div class='kpi-value' id='kpi-score'>-</div><div class='kpi-sub' id='kpi-score-sub'>iTunes points</div></div>
  </div>

  <div class='tab-bar'>
    <button class='tab active' onclick="showTab(event,'live')">Top Tracks</button>
    <button class='tab' onclick="showTab(event,'movement')">Top Movement</button>
    <button class='tab' onclick="showTab(event,'trend')">Rank Trend</button>
    <button class='tab' onclick="showTab(event,'consistency')">Consistency</button>
  </div>

  <div class='panel active' id='panel-consistency'>
    <div class='tab-desc'>Highlights albums with the strongest sustained chart footprint, combining repeated presence, best rank, average rank, and total points across the selected window.</div>
    <div class='card'>
      <div class='section-label'><span class='tag pt-it'>iTunes</span> Top consistent albums</div>
      <div class='note'>Best for finding albums with sustained chart footprint, not just one-day spikes.</div>
      <table class='rank-table'><thead><tr><th>#</th><th>Album</th><th>Best</th><th>Avg</th><th>Total points</th><th>Score</th></tr></thead><tbody id='it-cons-body'></tbody></table>
    </div>
    <div class='card' style='margin-top:14px'>
      <div class='section-label'>Album consistency score - top 15</div>
      <div class='chart-wrap consistency-chart'><canvas id='consistencyChart'></canvas></div>
    </div>
  </div>

  <div class='panel' id='panel-movement'>
    <div class='tab-desc'>Shows albums with the sharpest gains and drops by comparing their first available rank and points with the latest available values in the selected window.</div>
    <div class='two-col'>
      <div class='card'><div class='section-label'><span class='tag pt-it'>iTunes</span> Biggest album movers up</div><div class='note'>Positive momentum: rank climbed, points grew, or both.</div><div id='it-up-list'></div></div>
      <div class='card'><div class='section-label'><span class='tag pt-it'>iTunes</span> Biggest album movers down</div><div class='note'>Negative momentum: rank dropped, points fell, or both.</div><div id='it-down-list'></div></div>
    </div>
  </div>

  <div class='panel' id='panel-live'>
    <div class='tab-desc'>Lists the latest iTunes album chart leaders, including current position, artist, latest points, and day-over-day rank movement.</div>
    <div class='card'><div class='section-label'><span class='tag pt-it'>iTunes</span> Top 20 latest albums</div><div class='note'>Current chart leaders with day-over-day rank movement and latest points.</div><div id='live-it-list'></div></div>
  </div>

  <div class='panel' id='panel-trend'>
    <div class='tab-desc'>Plots daily rank paths for top rising albums so you can quickly spot steady climbs, sudden jumps, and unstable movement patterns.</div>
    <div class='card'>
      <div class='section-label'><span class='tag pt-it'>iTunes</span> Album rank trend - top risers</div>
      <div class='note'>Tracks the top risers from the movement tab. The y-axis is reversed because #1 is the strongest rank.</div>
      <div class='legend-row' id='it-trend-legend'></div>
      <div class='chart-wrap'><canvas id='itTrendChart'></canvas></div>
    </div>
  </div>
</div>

<script src='https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js'></script>
<script>
const PAYLOAD = __DATA__;
const COLORS = ['#3266ad','#d85a30','#1d9e75','#ba7517','#993556','#3b6d11','#534ab7','#888780'];

function showTab(evt,id){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  evt.currentTarget.classList.add('active');
  document.getElementById('panel-'+id).classList.add('active');
}
function fmtNum(n){
  if(n===null||n===undefined||isNaN(n))return'-';
  n=Number(n); const a=Math.abs(n);
  if(a>=1e9)return (n/1e9).toFixed(1)+'B';
  if(a>=1e6)return (n/1e6).toFixed(1)+'M';
  if(a>=1e3)return (n/1e3).toFixed(0)+'K';
  return String(Math.round(n));
}
function metricArr(d){return d.scores || []}
function latestPoints(d){return [...metricArr(d)].reverse().find(v=>v!==null) || 0}
function latestRank(d){return [...(d.ranks||[])].reverse().find(v=>v!==null)}
function startRank(d){return (d.ranks||[]).find(v=>v!==null)}
function rankBadge(n){
  if(n==='NEW')return '<span class="badge badge-new">NEW</span>';
  n=Number(n);
  if(!n)return '<span class="badge badge-eq">=</span>';
  if(n>0)return `<span class="badge badge-up">+${n}</span>`;
  return `<span class="badge badge-down">${n}</span>`;
}
function movementRow(d){
  const up = d.sg >= 0;
  return `<div class='mv-row'>
    <div class='mv-left'>
      <div class='mv-art'>${d.n}</div>
      <div class='mv-trk'>${d.t}</div>
      <div class='mv-meta'>
        <span class='metric-pill'>#${startRank(d)||'-'} to #${latestRank(d)||'-'}</span>
        <span class='metric-pill'>latest ${fmtNum(latestPoints(d))} points</span>
      </div>
      ${d.lbl && d.lbl !== '—' ? `<div style='margin-top:4px;'><span style='display:inline-block;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:700;background:var(--bg3);color:var(--t2);border:1px solid var(--border);'>${d.lbl}</span></div>` : ''}
    </div>
    <div class='mv-val ${up?'up':'dn'}'>${up?'+':'-'}${fmtNum(Math.abs(d.sg))} points</div>
    ${rankBadge(d.rg)}
  </div>`;
}
function renderList(id, data){
  const el=document.getElementById(id);
  if(!el)return;
  el.innerHTML = data && data.length ? data.map(movementRow).join('') : "<div class='empty'>No data in selected window.</div>";
}
function liveRow(r){
  return `<div class='live-row'>
    <div class='live-rank'>${r.rank || '-'}</div>
    <div class='live-info'>
      <div class='live-title'>${r.t}</div>
      <div class='live-meta'>${r.a}</div>
      ${r.lbl && r.lbl !== '—' ? `<div style='margin-top:4px;'><span style='display:inline-block;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:700;background:var(--bg3);color:var(--t2);border:1px solid var(--border);'>${r.lbl}</span></div>` : ''}
    </div>
    <div style='display:flex;align-items:center;gap:6px'><div class='live-score'>${fmtNum(r.s)} points</div>${rankBadge(r.m)}</div>
  </div>`;
}
function renderLive(id, data){
  const el=document.getElementById(id);
  if(!el)return;
  el.innerHTML = data && data.length ? data.map(liveRow).join('') : "<div class='empty'>No latest chart rows.</div>";
}
function renderConsistency(id, data){
  const el=document.getElementById(id);
  if(!el)return;
  if(!data || !data.length){
    el.innerHTML = "<tr><td colspan='6' class='empty'>No consistency data.</td></tr>";
    return;
  }
  const maxScore = Math.max(...data.map(d=>d.score),1);
  el.innerHTML = data.map((d,i)=>{
    const pct = Math.max(4, Math.round(d.score / maxScore * 100));
    return `<tr>
      <td class='rank-num'>${i+1}</td>
      <td>
        <div class='item-name'>${d.t}</div>
        <div class='item-sub'>${d.n}</div>
        ${d.lbl && d.lbl !== '—' ? `<div style='margin-top:4px;margin-bottom:2px;'><span style='display:inline-block;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:700;background:var(--bg3);color:var(--t2);border:1px solid var(--border);'>${d.lbl}</span></div>` : ''}
        <div class='bar-wrap'><div class='bar-bg'><div class='bar-fill' style='width:${pct}%;background:#3266ad'></div></div><span style='font-size:10px;color:var(--t3)'>${pct}%</span></div>
      </td>
      <td>#${d.best}</td>
      <td>#${d.avg}</td>
      <td>${fmtNum(d.total)}</td>
      <td>${fmtNum(d.score)}</td>
    </tr>`;
  }).join('');
}

document.getElementById('kpi-tracked').textContent = (PAYLOAD.kpis.tracked || 0).toLocaleString();
document.getElementById('kpi-rising').textContent = (PAYLOAD.kpis.rising_count || 0).toLocaleString();
const br = PAYLOAD.kpis.big_rank_riser;
document.getElementById('kpi-riser').textContent = br ? br.n : '-';
document.getElementById('kpi-riser-sub').textContent = br ? `${br.t} · +${br.rg} rank` : 'No movement';
const bs = PAYLOAD.kpis.big_score_riser;
document.getElementById('kpi-score').textContent = bs ? bs.n : '-';
document.getElementById('kpi-score-sub').textContent = bs ? `${bs.t} · +${fmtNum(bs.sg)} points` : 'iTunes points';

renderConsistency('it-cons-body', PAYLOAD.it_consistent);
renderList('it-up-list', PAYLOAD.it_risers);
renderList('it-down-list', PAYLOAD.it_fallers);
renderLive('live-it-list', PAYLOAD.it_top20);

function makeTrend(canvasId, legendId, rows){
  const canvas=document.getElementById(canvasId);
  const legend=document.getElementById(legendId);
  if(!canvas || !rows || !rows.length){ if(legend) legend.innerHTML="<span class='empty'>No trend data.</span>"; return; }
  const top=rows.slice(0,8);
  legend.innerHTML = top.map((d,i)=>`<span class='legend-item'><span class='legend-dot' style='background:${COLORS[i]}'></span>${d.n}</span>`).join('');
  new Chart(canvas,{type:'line',data:{labels:PAYLOAD.dates,datasets:top.map((d,i)=>({label:d.n,data:d.ranks,borderColor:COLORS[i],backgroundColor:'transparent',borderWidth:2,pointRadius:2,tension:.25,spanGaps:true}))},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{reverse:true,title:{display:true,text:'Chart rank (lower is better)',color:getComputedStyle(document.documentElement).getPropertyValue('--t2')},ticks:{color:getComputedStyle(document.documentElement).getPropertyValue('--t2')},grid:{color:'rgba(128,128,128,.14)'}},x:{ticks:{color:getComputedStyle(document.documentElement).getPropertyValue('--t2'),maxRotation:35},grid:{display:false}}}}});
}
makeTrend('itTrendChart','it-trend-legend',PAYLOAD.it_risers);
function makeConsistencyChart(){
  const canvas=document.getElementById('consistencyChart');
  const rows=(PAYLOAD.it_consistent || []).slice(0,15);
  if(!canvas || !rows.length)return;
  new Chart(canvas,{type:'bar',data:{labels:rows.map(d=>(d.t.length>22?d.t.slice(0,22)+'...':d.t)),datasets:[{data:rows.map(d=>d.score),backgroundColor:'#3266ad',borderRadius:4,borderSkipped:false,categoryPercentage:.72,barPercentage:.72,maxBarThickness:14}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',layout:{padding:{top:8,bottom:8}},plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`${fmtNum(ctx.raw)} score`}}},scales:{x:{ticks:{color:getComputedStyle(document.documentElement).getPropertyValue('--t2')},grid:{color:'rgba(128,128,128,.14)'}},y:{ticks:{color:getComputedStyle(document.documentElement).getPropertyValue('--t2'),padding:10},grid:{display:false}}}}});
}
makeConsistencyChart();
</script>
</body></html>
""".replace("__DATA__", data_json).replace("__THEME__", theme_css)
