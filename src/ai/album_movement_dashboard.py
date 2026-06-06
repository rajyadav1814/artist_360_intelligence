"""
Movement dashboard — business-perspective rank + chart-point momentum for
iTunes albums and tracks. Pulls dynamic data from itunes_artist_album/track tables.

Beyond raw rank/points momentum, this view frames movement for business
decisions:
  • Acceleration — is daily growth speeding up? (catches breakouts early)
  • Label intelligence — independent-vs-major split and top labels by momentum
  • New & Notable — fresh chart entrants and rank-threshold crossings

Note: iTunes "points" are a chart-weighting metric, not streams or revenue, so
no dollar estimate is shown for albums (unlike the track dashboard).
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
# High-density Professional Palette
_THEME_LIGHT = ":root{--bg:#f1f3f9;--bg2:#ffffff;--bg3:#f8fafc;--bg4:#e2e8f0;--border:#e2e8f0;--border2:#cbd5e1;--t1:#0f172a;--t2:#334155;--t3:#64748b;--t4:#94a3b8;--green:#10b981;--gd:rgba(16,185,129,.1);--red:#f43f5e;--rd:rgba(244,63,94,.1);--blue:#3b82f6;--bd:rgba(59,130,246,.1);--purple:#8b5cf6;--pd:rgba(139,92,246,.1);--amber:#f59e0b;--teal:#14b8a6;--pink:#ec4899;}"
_THEME_DARK  = ":root{--bg:#0b0e14;--bg2:#13171f;--bg3:#1a1f29;--bg4:#232a37;--border:rgba(255,255,255,.06);--border2:rgba(255,255,255,.12);--t1:#f8fafc;--t2:#94a3b8;--t3:#64748b;--t4:#475569;--green:#10b981;--gd:rgba(16,185,129,.12);--red:#f43f5e;--rd:rgba(244,63,94,.12);--blue:#3b82f6;--bd:rgba(59,130,246,.12);--purple:#8b5cf6;--pd:rgba(139,92,246,.12);--amber:#f59e0b;--teal:#14b8a6;--pink:#ec4899;--orange:#f59e0b;}"

# Region scope -> (unused, itunes_country)
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

# ─────────────────────── business constants ─────────────────────
# Albums with <= this many days on chart (or that appeared mid-window) are "new".
NEW_ON_CHART_DAYS = 14

# Rank thresholds we treat as meaningful business milestones.
RANK_TIERS = (10, 50)

# Substrings that identify a major-label (or major-distributed) release. The
# scraper tags many rows literally as "Independent"; anything not matching here
# is bucketed as Independent / Unattributed.
_MAJOR_LABEL_KEYWORDS = (
    "universal", "sony", "warner", "columbia", "atlantic", "capitol",
    "interscope", "republic", "rca", "island", "epic", "def jam", "polydor",
    "emi", "geffen", "motown", "parlophone", "virgin", "verve", "mercury",
    "blue note", "decca", "elektra", "roadrunner", "300 entertainment",
    "big machine", "fueled by ramen", "aftermath", "darkroom", "ovo sound",
)


def _label_tier(label: str | None) -> str:
    """Classify a label string as 'Major' or 'Independent'."""
    if not label:
        return "Independent"
    low = label.strip().lower()
    if not low or low == "—" or "independent" in low:
        return "Independent"
    for kw in _MAJOR_LABEL_KEYWORDS:
        if kw in low:
            return "Major"
    return "Independent"


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
    """Load rows from `table` for the given country within the most recent
    `days`-day window ending on max(date). Includes the columns needed for
    momentum, acceleration, label and new-entry analysis."""
    query = f"""
        WITH bounds AS (
            SELECT MAX(date) AS max_d FROM {table} WHERE country = %s
        )
        SELECT
            d.date,
            d.rank,
            d.artist_title,
            d.points         AS metric,
            d.points_change  AS metric_change,
            d.days,
            d.peak,
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
    for col in ("rank", "metric", "metric_change", "days", "peak"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _accel(changes: list[Any]) -> float:
    """Acceleration = (avg daily change in second half) − (first half).
    Positive ⇒ momentum is speeding up. Needs a few data points to be useful."""
    vals = [float(c) for c in changes if c is not None]
    if len(vals) < 4:
        return 0.0
    half = len(vals) // 2
    early = vals[:half]
    late = vals[len(vals) - half:]
    return (sum(late) / len(late)) - (sum(early) / len(early))


def _build_track_records(df: pd.DataFrame, dates: list[date], metric_key: str) -> list[dict[str, Any]]:
    """For every artist_title build a record with per-date rank + metric arrays
    plus derived business signals (acceleration, label tier, new-entry,
    threshold crossings)."""
    if df.empty:
        return []
    grouped = (
        df.sort_values("rank")
        .groupby(["artist_title", "date"], as_index=False)
        .first()
    )
    n_dates = len(dates)
    records: list[dict[str, Any]] = []
    for at, g in grouped.groupby("artist_title"):
        g = g.set_index("date")
        ranks: list[Any] = []
        metrics: list[Any] = []
        changes: list[Any] = []
        for d in dates:
            if d in g.index:
                row = g.loc[d]
                ranks.append(int(row["rank"]) if pd.notna(row["rank"]) else None)
                metrics.append(int(row["metric"]) if pd.notna(row["metric"]) else None)
                changes.append(int(row["metric_change"]) if pd.notna(row.get("metric_change")) else None)
            else:
                ranks.append(None)
                metrics.append(None)
                changes.append(None)

        first_idx = next((i for i, r in enumerate(ranks) if r is not None), None)
        last_idx = next((i for i in range(n_dates - 1, -1, -1) if ranks[i] is not None), None)
        if first_idx is None or last_idx is None:
            continue
        first_rank = ranks[first_idx]
        last_rank = ranks[last_idx]
        first_metric = next((m for m in metrics if m is not None), None)
        last_metric = next((m for m in reversed(metrics) if m is not None), None)

        rg = first_rank - last_rank          # positive = improved
        sg = (last_metric or 0) - (first_metric or 0)
        accel = _accel(changes)

        days_last = None
        if "days" in g.columns and g["days"].notna().any():
            days_last = int(g["days"].dropna().iloc[-1])
        appeared_mid = first_idx > 0
        is_new = appeared_mid or (days_last is not None and days_last <= NEW_ON_CHART_DAYS)

        crossed = 0
        for tier in RANK_TIERS:
            if first_rank > tier and last_rank <= tier:
                crossed = tier
                break

        artist, title = _split_at(at)
        label = g["label"].dropna().iloc[0] if g["label"].notna().any() else None
        tier = _label_tier(label)

        records.append({
            "n": artist,
            "t": title,
            "ranks": ranks,
            metric_key: metrics,
            "rg": int(rg),
            "sg": int(sg),
            "accel": int(round(accel)),
            "lbl": label or "—",
            "tier": tier,
            "new": bool(is_new),
            "crossed": int(crossed),
            "appeared": bool(appeared_mid),
            "days": days_last,
            "_metric_last": int(last_metric or 0),
        })
    return records


def _top_n(records: list[dict], n: int, *, risers: bool) -> list[dict]:
    if not records:
        return []
    max_sg = max((abs(r["sg"]) for r in records), default=1) or 1
    for r in records:
        r["_score"] = r["rg"] + (r["sg"] / max_sg) * 50
    if risers:
        filtered = [r for r in records if r["rg"] > 0 or r["sg"] > 0]
        filtered.sort(key=lambda r: r["_score"], reverse=True)
    else:
        filtered = [r for r in records if r["rg"] < 0 or r["sg"] < 0]
        filtered.sort(key=lambda r: r["_score"])
    return [_clean(r) for r in filtered[:n]]


def _clean(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def _heating(records: list[dict], n: int) -> list[dict]:
    """Albums whose daily growth is accelerating — earliest breakout signal."""
    pool = [r for r in records if r.get("accel", 0) > 0]
    pool.sort(key=lambda r: r["accel"], reverse=True)
    return [_clean(r) for r in pool[:n]]


def _new_and_notable(records: list[dict], n: int) -> list[dict]:
    """High-velocity market entrants and rank-threshold crossings.
    Sorted by 'Impact Score' (Score gain + Rank gain)."""
    pool = [r for r in records if r.get("new") or r.get("crossed")]
    # Prioritize entries with significant score growth (consumer demand)
    pool.sort(key=lambda r: (r.get("sg", 0) + (r.get("rg", 0) * 10)), reverse=True)
    return [_clean(r) for r in pool[:n]]


def _top20_today(df: pd.DataFrame, latest: date) -> list[dict[str, Any]]:
    today = df[df["date"] == latest].copy()
    if today.empty:
        return []
    prev_dates = sorted([d for d in df["date"].unique() if d < latest])
    prev = prev_dates[-1] if prev_dates else None
    prev_df = df[df["date"] == prev] if prev is not None else pd.DataFrame()
    prev_map = dict(zip(prev_df["artist_title"], prev_df["metric"])) if not prev_df.empty else {}
    today = today.sort_values("rank").head(20)
    out: list[dict[str, Any]] = []
    for _, row in today.iterrows():
        artist, title = _split_at(row["artist_title"])
        s = int(row["metric"]) if pd.notna(row["metric"]) else 0
        prev_v = prev_map.get(row["artist_title"])
        c = int(s - prev_v) if prev_v is not None and pd.notna(prev_v) else 0
        out.append({"t": title, "a": artist, "s": s, "c": c})
    return out


# ─────────────────────────── render ───────────────────────────────

def render_album_movement() -> None:
    st.markdown(
        "<div style='font-size:0.85rem;color:#97a3c5;margin:-0.5rem 0 0.75rem 0'>"
        "Business-lens market momentum on the iTunes chart — acceleration, label "
        "share and breakouts."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Filter bar ────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        view_type = custom_selectbox("View", ["Albums", "Tracks"], index=0, key="am_view")
    with c2:
        scope_label = custom_selectbox("Region", list(SCOPES.keys()), index=0, key="am_scope")
    with c3:
        period_label = custom_selectbox("Period", list(PERIOD_DAYS.keys()), index=0, key="am_period")

    _, it_country = SCOPES[scope_label]
    days = PERIOD_DAYS[period_label]
    table_name = "itunes_artist_album" if view_type == "Albums" else "itunes_artist_track"

    it_df = _load_window(table_name, it_country, days)

    if it_df.empty:
        st.warning("No daily chart data available for the selected window.")
        return

    it_dates = it_df["date"].tolist() if not it_df.empty and "date" in it_df.columns else []
    all_dates = sorted(set(it_dates))
    if not all_dates:
        st.warning("No dates found in window.")
        return

    it_records = _build_track_records(it_df, all_dates, "scores")

    it_risers = _top_n(it_records, 15, risers=True)
    it_fallers = _top_n(it_records, 15, risers=False)
    it_heating = _heating(it_records, 10)
    it_new = _new_and_notable(it_records, 10)

    # ── Business KPIs ─────────────────────────────────────────────
    total_metric = sum(r.get("_metric_last", 0) for r in it_records) or 1
    indie_metric = sum(r.get("_metric_last", 0) for r in it_records if r.get("tier") == "Independent")
    indie_share = round(indie_metric / total_metric * 100)

    new_count = sum(1 for r in it_records if r.get("new"))
    breakout_top10 = sum(1 for r in it_records if r.get("crossed") == 10)
    rising_count = sum(1 for r in it_records if r["rg"] > 0)
    
    # Entry Velocity: Avg rank gain of new entrants
    new_entries = [r for r in it_records if r.get("new") and r["rg"] > 0]
    avg_entry_velocity = round(sum(r["rg"] for r in new_entries) / len(new_entries)) if new_entries else 0

    hottest = max(it_records, key=lambda r: r.get("accel", 0), default=None)
    top_riser = it_risers[0] if it_risers else None

    kpis = {
        "tracked": len(it_records),
        "rising_count": rising_count,
        "indie_share": indie_share,
        "new_count": new_count,
        "entry_velocity": avg_entry_velocity,
        "breakout_top10": breakout_top10,
        "hottest": _clean(hottest) if hottest else None,
        "top_riser": top_riser,
        "entity_type": view_type,
        "entity_singular": view_type[:-1]  # Album or Track
    }

    date_strs = [d.strftime("%b %d") for d in all_dates]
    window_label = f"{all_dates[0].strftime('%b %d')}–{all_dates[-1].strftime('%b %d, %Y')} · {PERIOD_LABELS[period_label]}"

    payload: dict[str, Any] = {
        "dates": date_strs,
        "window_label": window_label,
        "scope": scope_label,
        "period": PERIOD_LABELS.get(period_label, period_label),
        "it_risers": it_risers,
        "it_fallers": it_fallers,
        "it_heating": it_heating,
        "it_new": it_new,
        "kpis": kpis,
        "new_on_chart_days": NEW_ON_CHART_DAYS,
    }

    html = _build_html(payload, dark_mode=st.session_state.get("dark_mode", True))
    st_components.html(html, height=1900, scrolling=True)


def _build_html(payload: dict, dark_mode: bool = False) -> str:
    data_json = json.dumps(payload, default=str)
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    return """
<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
*{box-sizing:border-box;margin:0;padding:0;scrollbar-width:thin;scrollbar-color:var(--border2) transparent}
__THEME__
body{background:var(--bg);font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;color:var(--t1);font-size:14px;line-height:1.5;overflow-x:hidden}
.kpi-bar{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--border);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:20px}
.kpi{background:var(--bg2);padding:16px 20px;transition:.15s}
.kpi:hover{background:var(--bg3)}
.kpi-lbl{font-size:10px;color:var(--t4);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-weight:700}
.kpi-val{font-size:24px;font-weight:700;letter-spacing:-0.02em;line-height:1;color:var(--t1);font-variant-numeric:tabular-nums}
.kpi-sub{font-size:11px;color:var(--t3);margin-top:6px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi-val.g{color:var(--green)}.kpi-val.r{color:var(--red)}.kpi-val.p{color:var(--purple)}.kpi-val.a{color:var(--amber)}.kpi-val.b{color:var(--blue)}.kpi-val.t{color:var(--teal)}
.body{padding:18px 20px;display:flex;flex-direction:column;gap:18px;max-width:100%;}
.r2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
.sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.sh-l{font-size:16px;font-weight:600;color:var(--t1);letter-spacing:-.2px}
.sh-r{font-size:11px;color:var(--t2);background:var(--bg3);padding:4px 11px;border-radius:5px;border:1px solid var(--border2);font-weight:500}
.card-ttl{font-size:12px;color:var(--t2);text-transform:uppercase;letter-spacing:.7px;margin-bottom:12px;padding-bottom:9px;border-bottom:1px solid var(--border);font-weight:600}
.card-note{font-size:12px;color:var(--t3);margin:-2px 0 16px;line-height:1.5}
.trk{display:grid;gap:8px;padding:12px 0;border-bottom:1px solid var(--border);align-items:center;transition:.1s}
.trk:hover{background:var(--bg3);margin:0 -12px;padding:12px 12px;border-radius:8px}
.trk:last-child{border-bottom:none !important}
.trk-hdr{display:grid;gap:8px;padding:8px 0;border-bottom:1px solid var(--border2);margin-bottom:4px}
.trk-hdr span{font-size:10px;color:var(--t4);text-transform:uppercase;letter-spacing:.6px;font-weight:700}
.rn{font-size:13px;color:var(--t3);text-align:center;min-width:20px;font-weight:600}
.tn{font-size:14px;font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-0.01em}
.ta{font-size:11px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px;font-weight:500;display:flex;align-items:center;gap:6px}
.tv{font-size:13px;color:var(--t1);text-align:right;white-space:nowrap;font-weight:600;font-variant-numeric:tabular-nums}
.bu{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--gd);color:var(--green);min-width:42px;border:1px solid rgba(52,211,153,.35)}
.bd{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--rd);color:var(--red);min-width:42px;border:1px solid rgba(251,113,133,.35)}
.bn{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--bg3);color:var(--t4);min-width:42px;border:1px solid var(--border2)}
.chip{font-size:9px;font-weight:800;padding:2px 6px;border-radius:4px;letter-spacing:.5px;text-transform:uppercase;white-space:nowrap}
.chip-major{background:var(--pd);color:var(--purple);border:1px solid rgba(196,181,253,.4)}
.chip-indie{background:rgba(96,165,250,.12);color:var(--blue);border:1px solid rgba(96,165,250,.4)}
.chip-new{background:rgba(252,211,77,.16);color:var(--amber);border:1px solid rgba(252,211,77,.45)}
.chip-cross{background:var(--gd);color:var(--green);border:1px solid rgba(52,211,153,.4)}
.accel{font-size:10px;font-weight:700;color:var(--amber)}
.bar-row{display:grid;grid-template-columns:1fr 56px 64px;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)}
.bar-row:last-child{border-bottom:none}
.bar-name{font-size:13px;font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{height:8px;background:var(--bg4);border-radius:4px;overflow:hidden;margin-top:5px}
.bar-fill{height:8px;border-radius:4px}
.section-label{font-size:13px;font-weight:700;letter-spacing:.5px;margin-bottom:12px;display:flex;align-items:center;gap:8px;text-transform:uppercase}
.section-dot{width:10px;height:10px;border-radius:50%;display:inline-block;box-shadow:0 0 6px currentColor}
.empty{color:var(--t3);font-size:11px;padding:14px 0}
</style></head><body>

<div class='body'>

  <!-- Business KPI bar -->
  <div class='kpi-bar' id='kpi-bar'></div>

  <!-- Guide Banner -->
  <div class='card' style='padding:16px 20px'>
    <div style='display:flex;justify-content:space-between;align-items:center;cursor:pointer;' onclick='toggleGuide()'>
      <div style='display:flex;align-items:center;gap:10px;font-weight:700;color:var(--t1);font-size:14.5px;'>
        <span style='font-size:16px;'>💡</span> How to read this — business signals & columns
      </div>
      <span id='guide-toggle-icon' style='font-size:12px;color:var(--t3);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;'>[ Show Details ]</span>
    </div>
    <div id='guide-content' style='display:none;margin-top:14px;border-top:1px solid var(--border);padding-top:14px;'>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:24px;'>
        <div>
          <div style='font-weight:700;font-size:12px;text-transform:uppercase;color:var(--t2);letter-spacing:0.8px;margin-bottom:8px;'>Business signals</div>
          <div style='display:grid;grid-template-columns:auto 1fr;gap:9px 12px;font-size:12px;color:var(--t3);line-height:1.45;max-width:100%;'>
            <b style='color:var(--t2);white-space:nowrap;'>🚀 Momentum Velocity</b>
            <span>Entries where daily growth is <i>accelerating</i>. Indicates early-stage viral breakouts before they hit peak rank.</span>
            <b style='color:var(--t2);white-space:nowrap;'>Market Tracking</b>
            <span>Identifies 'Debuts' (first appearance in window), 'New' entries (≤__NEWDAYS__ days on chart), and milestone crossings.</span>
            <b style='color:var(--t2);white-space:nowrap;'>Indie / Major</b>
            <span>Market share classification. "Independent" serves as a proxy for non-distributed or boutique label performance.</span>
            <b style='color:var(--t2);white-space:nowrap;'>Points</b>
            <span>iTunes chart-weighting metric — not streams or revenue, so no dollar estimate is shown.</span>
          </div>
        </div>
        <div>
          <div style='font-weight:700;font-size:12px;text-transform:uppercase;color:var(--t2);letter-spacing:0.8px;margin-bottom:8px;'>Risers / Fallers columns</div>
          <div style='display:grid;grid-template-columns:auto 1fr;gap:9px 12px;font-size:12px;color:var(--t3);line-height:1.45;max-width:100%;'>
            <b style='color:var(--t2);white-space:nowrap;'>Start / Now</b>
            <span>Chart rank at the start and end of the window.</span>
            <b style='color:var(--t2);white-space:nowrap;'>History</b>
            <span>Daily rank trajectory across the window. Higher path = better position (#1 rank is at the top).</span>
            <b style='color:var(--t2);white-space:nowrap;'>Score</b>
            <span>Latest daily iTunes chart points.</span>
            <b style='color:var(--t2);white-space:nowrap;'>Change</b>
            <span>Net change in points across the window.</span>
            <b style='color:var(--t2);white-space:nowrap;'>Δ Rank</b>
            <span>Net rank shift. ▲ Gaining rank indicates increasing consumer demand; ▼ Falling indicates a trajectory cooldown. 🚀 marks accelerating growth.</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Heating Up + New & Notable -->
  <div class='r2'>
    <div class='card'>
      <div class='sh'><span class='sh-l'>🚀 Momentum Velocity</span><span class='sh-r'>acceleration</span></div>
      <div class='card-note'>Early-stage breakout signals where current daily point velocity exceeds the window average.</div>
      <div id='it-heating'></div>
    </div>
    <div class='card'>
      <div class='sh'><span class='sh-l'>✨ Market Entry & Breakouts</span><span class='sh-r'>impact entrants</span></div>
      <div class='card-note'>Debut chart entries and releases crossing strategic rank thresholds (Top 10/50) in this window.</div>
      <div id='it-new'></div>
    </div>
  </div>

  <!-- Risers / Fallers -->
  <div class='r2'>
    <div class='card' id='risers-section'>
      <div class='sh'><span class='sh-l'>📈 Top Risers</span><span class='sh-r'>rank + points composite</span></div>
      <div class='card-note'>Gaining momentum — identifies those climbing the chart through rank improvement and daily point growth.</div>
      <div class='section-label' style='color:var(--purple)'><span class='section-dot' style='background:var(--purple)'></span>iTunes · Rank + Score</div>
      <div class='trk-hdr' style='grid-template-columns:24px 1fr 40px 40px 80px 60px 60px 58px'>
        <span></span><span id='hdr-name-riser'>Artist · Release</span><span style='text-align:center'>Start</span><span style='text-align:center'>Now</span><span style='text-align:center'>History</span><span style='text-align:right'>Score</span><span style='text-align:right'>+Score</span><span style='text-align:right'>Δ Rank</span>
      </div>
      <div id='it-risers'></div>
    </div>

    <div class='card' id='fallers-section'>
      <div class='sh'><span class='sh-l'>📉 Top Fallers</span><span class='sh-r'>rank + points composite</span></div>
      <div class='card-note'>Falling trajectory — highlights releases losing ground due to dropping chart ranks and net point losses.</div>
      <div class='section-label' style='color:var(--red)'><span class='section-dot' style='background:var(--red)'></span>iTunes · Rank + Score lost</div>
      <div class='trk-hdr' style='grid-template-columns:24px 1fr 40px 40px 80px 60px 60px 58px'>
        <span></span><span id='hdr-name-faller'>Artist · Release</span><span style='text-align:center'>Start</span><span style='text-align:center'>Now</span><span style='text-align:center'>History</span><span style='text-align:right'>Score</span><span style='text-align:right'>Lost</span><span style='text-align:right'>Δ Rank</span>
      </div>
      <div id='it-fallers'></div>
    </div>
  </div>

</div>

<script>
const PAYLOAD = __DATA__;

function fmtN(n,dec=1){if(n===null||n===undefined||isNaN(n))return'—';n=parseFloat(n);const a=Math.abs(n),sign=n<0?'−':n>0?'+':'';if(a>=1e6)return sign+(a/1e6).toFixed(dec)+'M';if(a>=1e3)return sign+(a/1e3).toFixed(0)+'K';return sign+a.toFixed(0);}
function fmtUSD(n){if(n===null||n===undefined||isNaN(n))return'—';n=parseFloat(n);const a=Math.abs(n),sign=n<0?'−':'';if(a>=1e6)return sign+'$'+(a/1e6).toFixed(2)+'M';if(a>=1e3)return sign+'$'+(a/1e3).toFixed(1)+'K';return sign+'$'+n.toFixed(0);}
function toggleGuide(){const c=document.getElementById('guide-content');const i=document.getElementById('guide-toggle-icon');if(c.style.display==='none'){c.style.display='block';i.textContent='[ Hide Details ]';}else{c.style.display='none';i.textContent='[ Show Details ]';}} // Guide toggle

// ── KPI bar ──
function renderKPIs(){
  const k = PAYLOAD.kpis || {};
  const ent = k.entity_type || 'Albums';
  const hot = k.hottest, riser = k.top_riser;
  const tiles = [
    {l:ent + ' Tracking', v:(k.tracked!=null?k.tracked:'—'), c:'', s:'active in '+PAYLOAD.period},
    {l:'Rising ' + ent.toLowerCase(), v:(k.rising_count!=null?k.rising_count:'—'), c:'g', s:'gained rank in window'},
    {l:'Independent share', v:(k.indie_share!=null?k.indie_share+'%':'—'), c:'b', s:'of tracked chart points'},
    {l:'New Entries', v:(k.new_count!=null?k.new_count:'—'), c:'a', s:k.breakout_top10+' hit Top 10'},
    {l:'Entry Velocity', v:(k.entry_velocity?'+'+k.entry_velocity:'—'), c:'t', s:'Avg rank gain for debuts'},
    {l:'Top riser', v:(riser?'▲'+riser.rg:'—'), c:'g', s:riser?(riser.n+' — '+riser.t):'—'}
  ];
  document.getElementById('kpi-bar').innerHTML = tiles.map(t=>
    `<div class='kpi'><div class='kpi-lbl'>${t.l}</div><div class='kpi-val ${t.c}'>${t.v}</div><div class='kpi-sub'>${t.s}</div></div>`
  ).join('');
  
  // Update table headers based on type
  const label = "Artist · " + (k.entity_singular || "Release");
  document.getElementById('hdr-name-riser').textContent = label;
  document.getElementById('hdr-name-faller').textContent = label;
}

function genSpark(ranks, color, width=70, height=18){
  const valid = ranks.filter(r => r !== null);
  if(valid.length < 2) return `<div style='text-align:center;color:var(--t4);font-size:10px'>—</div>`;
  const min = Math.min(...valid), max = Math.max(...valid);
  const range = (max - min) || 1;
  const w = width, h = height;
  const pts = ranks.map((r, i) => {
    if(r === null) return null;
    const x = (i / (ranks.length - 1)) * w;
    const y = ((r - min) / range) * h; // Invert: smaller rank = higher Y
    return `${x},${y}`;
  }).filter(p => p !== null).join(' ');
  return `<div style='display:flex;justify-content:center'><svg width="${w}" height="${h}" style="overflow:visible;"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.85" /></svg></div>`;
}

function tierChip(t){return t==='Major'?`<span class='chip chip-major'>Major</span>`:'';}
function metaChips(d){
  let c = tierChip(d.tier);
  if(d.appeared){c+=`<span class='chip chip-new' style='background:rgba(16,185,129,.12);color:var(--green);border-color:rgba(16,185,129,.3)'>Debut</span>`;}
  else if(d.new){c+=`<span class='chip chip-new'>New</span>`;}
  if(d.crossed){c+=`<span class='chip chip-cross'>↑Top ${d.crossed}</span>`;}
  return c;
}

// ── Risers / Fallers table ──
function renderTable(elId, data){
  const el = document.getElementById(elId);
  if(!el) return;
  if(!data || !data.length){ el.innerHTML="<div class='empty'>No data in selected window.</div>"; return; }
  let html='';
  data.forEach((d,i)=>{
    const metricArr = d.scores || [];
    const latVal = [...metricArr].reverse().find(v=>v!==null) || 0;
    const latRank = [...d.ranks].reverse().find(v=>v!==null);
    const startRank = d.ranks.find(v=>v!==null);
    const rankColor = d.rg>0?'var(--green)':d.rg<0?'var(--red)':'var(--t3)';
    const sgColor = d.sg>0?'var(--blue)':d.sg<0?'var(--red)':'var(--t3)';
    const sgSign = d.sg>0?'+':d.sg<0?'−':'';
    const valFmt = (latVal||0).toLocaleString();
    const sgLabel = Math.abs(d.sg).toLocaleString();
    const rankBadge = d.rg>0?`<span class='bu'>▲${d.rg}</span>`:d.rg<0?`<span class='bd'>▼${Math.abs(d.rg)}</span>`:`<span class='bn'>—</span>`;
    const heat = (d.accel>0)?` <span class='accel' title='accelerating'>🚀</span>`:'';
    html += `<div class='trk' style='grid-template-columns:24px 1fr 40px 40px 80px 60px 60px 58px'>
      <span class='rn'>${i+1}</span>
      <div style='min-width:0'>
        <div class='tn'>${d.t}</div>
        <div class='ta'>${d.n} ${metaChips(d)} <span style='color:var(--t4);margin-left:4px'>• ${d.days?d.days+'d':''}</span></div>
      </div>
      <span style='font-size:13px;color:var(--t3);text-align:center;font-weight:600'>${startRank||'—'}</span>
      <span style='font-size:13px;color:${rankColor};text-align:center;font-weight:700'>${latRank||'—'}</span>
      ${genSpark(d.ranks, d.rg >= 0 ? 'var(--green)' : 'var(--red)')}
      <span class='tv'>${valFmt}</span>
      <span class='tv' style='color:${sgColor}'>${sgSign}${sgLabel}</span>
      <span style='text-align:right'>${rankBadge}${heat}</span>
    </div>`;
  });
  el.innerHTML = html;
}

// ── Heating / New compact list ──
function renderCompact(elId, data, kind){
  const el = document.getElementById(elId);
  if(!el) return;
  if(!data || !data.length){ el.innerHTML=`<div class='empty'>None in selected window.</div>`; return; }
  let html='';
  data.forEach((d,i)=>{
    const latRank = [...d.ranks].reverse().find(v=>v!==null);
    let right;
    if(kind==='heat'){
      right = `<span class='accel'>🚀 ${(d.accel>0?'+':'')+d.accel.toLocaleString()}/day</span>`;
    } else {
      right = d.crossed?`<span class='chip chip-cross'>↑Top ${d.crossed}</span>`:`<span class='chip chip-new'>New</span>`;
    }
    html += `<div class='trk' style='grid-template-columns:22px 1fr 60px auto'>
      <span class='rn'>${i+1}</span>
      <div style='min-width:0'>
        <div class='tn'>${d.t}</div>
        <div class='ta'>${d.n} ${tierChip(d.tier)} <span style='color:var(--t3)'>#${latRank||'—'} • ${d.days?d.days+'d':''}</span></div>
      </div>
      <div style='padding-top:4px'>${genSpark(d.ranks, 'var(--t4)', 50, 12)}</div>
      <span style='text-align:right;font-size:12px;font-weight:700'>${right}</span>
    </div>`;
  });
  el.innerHTML = html;
}

// ── render ──
renderKPIs();
renderTable('it-risers', PAYLOAD.it_risers);
renderTable('it-fallers', PAYLOAD.it_fallers);
renderCompact('it-heating', PAYLOAD.it_heating, 'heat');
renderCompact('it-new', PAYLOAD.it_new, 'new');
</script>
</body></html>
""".replace("__DATA__", data_json).replace("__THEME__", theme_css).replace("__NEWDAYS__", str(NEW_ON_CHART_DAYS))
