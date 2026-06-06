"""
Track Movement dashboard — business-perspective rank + metric momentum for
Spotify and iTunes top tracks. Pulls dynamic data from the spotify_daily and
itunes_daily tables.

Beyond raw rank/metric momentum, this view frames movement for business
decisions:
  • Acceleration — is daily growth speeding up? (catches breakouts early)
  • Commercial value — estimated daily revenue from Spotify streams
  • Label intelligence — independent-vs-major split and top labels by momentum
  • New & Notable — fresh chart entrants and rank-threshold crossings
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


# Region scope -> (spotify_country, itunes_country)
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
# Blended industry-average NET payout per Spotify stream (USD). This is an
# estimate for relative comparison only — actual payouts vary by deal/territory.
SPOTIFY_NET_PER_STREAM_USD = 0.0035

# Tracks with <= this many days on chart (or that appeared mid-window) are "new".
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
    momentum, acceleration, revenue, label and new-entry analysis."""
    metric_col = "streams" if table == "spotify_daily" else "points"
    change_col = "streams_change" if table == "spotify_daily" else "points_change"
    query = f"""
        WITH bounds AS (
            SELECT MAX(date) AS max_d FROM {table} WHERE country = %s
        )
        SELECT
            d.date,
            d.rank,
            d.artist_title,
            d.{metric_col}  AS metric,
            d.{change_col}  AS metric_change,
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
        logger.error("track_movement load_window failed (%s/%s): %s", table, country, e)
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


def _build_track_records(
    df: pd.DataFrame, dates: list[date], metric_key: str, *, is_spotify: bool
) -> list[dict[str, Any]]:
    """For every artist_title build a record with per-date rank + metric arrays
    plus derived business signals (acceleration, revenue, label tier, new-entry,
    threshold crossings)."""
    if df.empty:
        return []
    # Best (lowest) rank per (artist_title, date) — defensive against duplicates
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

        # New-entry: appeared mid-window OR low days-on-chart at latest date
        days_last = None
        if "days" in g.columns and g["days"].notna().any():
            days_last = int(g["days"].dropna().iloc[-1])
        appeared_mid = first_idx > 0
        is_new = appeared_mid or (days_last is not None and days_last <= NEW_ON_CHART_DAYS)

        # Threshold crossings — broke INTO a tier during the window
        crossed = 0
        for tier in RANK_TIERS:
            if first_rank > tier and last_rank <= tier:
                crossed = tier
                break

        artist, title = _split_at(at)
        label = g["label"].dropna().iloc[0] if g["label"].notna().any() else None
        tier = _label_tier(label)

        rec: dict[str, Any] = {
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
        }
        # Commercial value — Spotify streams only (iTunes "points" ≠ revenue)
        if is_spotify:
            rec["rev"] = round((last_metric or 0) * SPOTIFY_NET_PER_STREAM_USD)
            rec["rev_delta"] = round(sg * SPOTIFY_NET_PER_STREAM_USD)
        records.append(rec)
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
    return [_clean(r) for r in filtered[:n]]


def _clean(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def _heating(records: list[dict], n: int) -> list[dict]:
    """Tracks whose daily growth is accelerating — earliest breakout signal."""
    pool = [r for r in records if r.get("accel", 0) > 0]
    pool.sort(key=lambda r: r["accel"], reverse=True)
    return [_clean(r) for r in pool[:n]]


def _new_and_notable(records: list[dict], n: int) -> list[dict]:
    """New chart entrants + rank-threshold crossings, ranked by momentum."""
    pool = [r for r in records if r.get("new") or r.get("crossed")]
    # Sort: threshold crossings first (lower tier = bigger deal), then rank gain
    pool.sort(key=lambda r: (-(1 if r.get("crossed") else 0), r.get("crossed") or 999, -r["rg"]))
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

def render_track_movement() -> None:
    st.markdown(
        "<div style='font-size:0.85rem;color:#97a3c5;margin:-0.5rem 0 0.75rem 0'>"
        "Business-lens momentum across Spotify and iTunes daily charts — revenue, "
        "acceleration, label share and breakouts."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Filter bar ────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
    with c1:
        scope_label = custom_selectbox("Region", list(SCOPES.keys()), index=0, key="tm_scope")
    with c2:
        period_label = custom_selectbox("Period", list(PERIOD_DAYS.keys()), index=0, key="tm_period")
    with c3:
        platform = custom_selectbox(
            "Platform",
            ["Both", "Spotify", "iTunes"],
            index=0,
            key="tm_platform",
        )

    sp_country, it_country = SCOPES[scope_label]
    days = PERIOD_DAYS[period_label]

    sp_df = _load_window("spotify_daily", sp_country, days)
    it_df = _load_window("itunes_daily", it_country, days)

    if sp_df.empty and it_df.empty:
        st.warning("No daily chart data available for the selected window.")
        return

    sp_dates = sp_df["date"].tolist() if not sp_df.empty and "date" in sp_df.columns else []
    it_dates = it_df["date"].tolist() if not it_df.empty and "date" in it_df.columns else []
    all_dates = sorted(set(sp_dates) | set(it_dates))
    if not all_dates:
        st.warning("No dates found in window.")
        return

    sp_records = _build_track_records(sp_df, all_dates, "streams", is_spotify=True) if not sp_df.empty else []
    it_records = _build_track_records(it_df, all_dates, "scores", is_spotify=False) if not it_df.empty else []

    sp_risers = _top_n(sp_records, 15, risers=True)
    sp_fallers = _top_n(sp_records, 15, risers=False)
    it_risers = _top_n(it_records, 15, risers=True)
    it_fallers = _top_n(it_records, 15, risers=False)

    sp_heating = _heating(sp_records, 8)
    it_heating = _heating(it_records, 8)
    sp_new = _new_and_notable(sp_records, 8)
    it_new = _new_and_notable(it_records, 8)

    sp_top20 = _top20_today(sp_df, all_dates[-1]) if not sp_df.empty else []
    it_top20 = _top20_today(it_df, all_dates[-1]) if not it_df.empty else []

    # ── Business KPIs ─────────────────────────────────────────────
    est_daily_rev = sum(r.get("rev", 0) for r in sp_records)
    rev_delta = sum(r.get("rev_delta", 0) for r in sp_records)

    combined = sp_records + it_records
    total_metric = sum(r.get("_metric_last", 0) for r in combined) or 1
    indie_metric = sum(r.get("_metric_last", 0) for r in combined if r.get("tier") == "Independent")
    indie_share = round(indie_metric / total_metric * 100)

    new_count = sum(1 for r in combined if r.get("new"))
    breakout_top10 = sum(1 for r in combined if r.get("crossed") == 10)

    hottest = max(combined, key=lambda r: r.get("accel", 0), default=None)
    biggest_rev_swing = max(sp_records, key=lambda r: abs(r.get("rev_delta", 0)), default=None)

    kpis = {
        "est_daily_rev": est_daily_rev,
        "rev_delta": rev_delta,
        "indie_share": indie_share,
        "new_count": new_count,
        "breakout_top10": breakout_top10,
        "hottest": _clean(hottest) if hottest else None,
        "rev_swing": _clean(biggest_rev_swing) if biggest_rev_swing else None,
        "tracked": len(combined),
    }

    date_strs = [d.strftime("%b %d") for d in all_dates]

    payload = {
        "dates": date_strs,
        "scope": scope_label,
        "platform": platform,
        "period": PERIOD_LABELS.get(period_label, period_label),
        "per_stream": SPOTIFY_NET_PER_STREAM_USD,
        "sp_risers": sp_risers,
        "sp_fallers": sp_fallers,
        "it_risers": it_risers,
        "it_fallers": it_fallers,
        "sp_heating": sp_heating,
        "it_heating": it_heating,
        "sp_new": sp_new,
        "it_new": it_new,
        "sp_top20": sp_top20,
        "it_top20": it_top20,
        "kpis": kpis,
    }

    html = _build_html(payload, dark_mode=st.session_state.get("dark_mode", True))
    iframe_height = 2100 if platform == "Both" else 1700
    st_components.html(html, height=iframe_height, scrolling=True)


# ─────────────────────────── HTML template ───────────────────────────

def _build_html(payload: dict, dark_mode: bool = False) -> str:
    data_json = json.dumps(payload, default=str)
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    return """
<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
*{box-sizing:border-box;margin:0;padding:0}
__THEME__
body{background:var(--bg);font-family:'Inter',system-ui,sans-serif;color:var(--t1);font-size:15px;line-height:1.55}
.kpi-bar{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--border);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:18px}
.kpi{background:var(--bg2);padding:15px 16px;transition:.15s}
.kpi:hover{background:var(--bg3)}
.kpi-lbl{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px;font-weight:600}
.kpi-val{font-size:23px;font-weight:700;letter-spacing:-.5px;line-height:1.15;color:var(--t1)}
.kpi-sub{font-size:11px;color:var(--t2);margin-top:5px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi-val.g{color:var(--green)}.kpi-val.r{color:var(--red)}.kpi-val.p{color:var(--purple)}.kpi-val.a{color:var(--amber)}.kpi-val.b{color:var(--blue)}.kpi-val.t{color:var(--teal)}
.body{padding:18px 20px;display:flex;flex-direction:column;gap:18px}
.r2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
.sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.sh-l{font-size:16px;font-weight:600;color:var(--t1);letter-spacing:-.2px}
.sh-r{font-size:11px;color:var(--t2);background:var(--bg3);padding:4px 11px;border-radius:5px;border:1px solid var(--border2);font-weight:500}
.card-ttl{font-size:12px;color:var(--t2);text-transform:uppercase;letter-spacing:.7px;margin-bottom:12px;padding-bottom:9px;border-bottom:1px solid var(--border);font-weight:600}
.card-note{font-size:12px;color:var(--t3);margin:-2px 0 12px;line-height:1.5}
.trk{display:grid;gap:8px;padding:10px 0;border-bottom:1px solid var(--border);align-items:center;transition:.1s}
.trk:hover{background:var(--bg3);margin:0 -8px;padding:10px 8px;border-radius:6px}
.trk:last-child{border-bottom:none}
.trk-hdr{display:grid;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2);margin-bottom:2px}
.trk-hdr span{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;font-weight:600}
.rn{font-size:13px;color:var(--t3);text-align:center;min-width:20px;font-weight:600}
.tn{font-size:14px;font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-.1px}
.ta{font-size:11px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px;font-weight:500;display:flex;align-items:center;gap:6px}
.tv{font-size:13px;color:var(--t1);text-align:right;white-space:nowrap;font-weight:600;font-variant-numeric:tabular-nums}
.tv-sub{font-size:10px;color:var(--t3);text-align:right;font-weight:500;margin-top:2px}
.bu{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--gd);color:var(--green);min-width:42px;border:1px solid rgba(52,211,153,.35)}
.bd{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--rd);color:var(--red);min-width:42px;border:1px solid rgba(251,113,133,.35)}
.bn{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--bg3);color:var(--t2);min-width:42px;border:1px solid var(--border2)}
.chip{font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;letter-spacing:.4px;text-transform:uppercase;white-space:nowrap}
.chip-major{background:var(--pd);color:var(--purple);border:1px solid rgba(196,181,253,.4)}
.chip-indie{background:var(--bd);color:var(--blue);border:1px solid rgba(96,165,250,.4)}
.chip-new{background:rgba(252,211,77,.16);color:var(--amber);border:1px solid rgba(252,211,77,.45)}
.chip-cross{background:var(--gd);color:var(--green);border:1px solid rgba(52,211,153,.4)}
.accel{font-size:10px;font-weight:700;color:var(--amber)}
.bar-row{display:grid;grid-template-columns:1fr 56px 64px;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)}
.bar-row:last-child{border-bottom:none}
.bar-name{font-size:13px;font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{height:8px;background:var(--bg4);border-radius:4px;overflow:hidden;margin-top:5px}
.bar-fill{height:8px;border-radius:4px}
.tier-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.tier-box{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:13px 15px}
.tier-name{font-size:11px;text-transform:uppercase;letter-spacing:.6px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:7px}
.tier-share{font-size:26px;font-weight:700;letter-spacing:-.5px}
.tier-meta{font-size:11px;color:var(--t3);margin-top:4px;font-weight:500}
.section-label{font-size:13px;font-weight:700;letter-spacing:.5px;margin-bottom:12px;display:flex;align-items:center;gap:8px;text-transform:uppercase}
.section-dot{width:10px;height:10px;border-radius:50%;display:inline-block;box-shadow:0 0 6px currentColor}
.hide{display:none !important}
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
          <div style='display:grid;grid-template-columns:auto 1fr;gap:9px 12px;font-size:12px;color:var(--t3);line-height:1.45;'>
            <b style='color:var(--t2);white-space:nowrap;'>Est. revenue</b>
            <span>Spotify daily streams × est. net payout ($__RATE__/stream). Relative indicator, not booked revenue. iTunes "points" are not revenue.</span>
            <b style='color:var(--t2);white-space:nowrap;'>🚀 Heating Up</b>
            <span>Daily growth is <i>accelerating</i> (2nd-half avg daily change &gt; 1st-half). Surfaces breakouts earlier than net gain.</span>
            <b style='color:var(--t2);white-space:nowrap;'>New & Notable</b>
            <span>Fresh chart entrants (≤__NEWDAYS__ days on chart or appeared mid-window) and tracks that broke into the Top 10 / Top 50.</span>
            <b style='color:var(--t2);white-space:nowrap;'>Indie / Major</b>
            <span>Label tier by streaming share. "Independent" includes unattributed releases, so indie share is an upper bound.</span>
          </div>
        </div>
        <div>
          <div style='font-weight:700;font-size:12px;text-transform:uppercase;color:var(--t2);letter-spacing:0.8px;margin-bottom:8px;'>Risers / Fallers columns</div>
          <div style='display:grid;grid-template-columns:auto 1fr;gap:9px 12px;font-size:12px;color:var(--t3);line-height:1.45;'>
            <b style='color:var(--t2);white-space:nowrap;'>Start / Now</b>
            <span>Chart rank at the start and end of the window.</span>
            <b style='color:var(--t2);white-space:nowrap;'>Value</b>
            <span>Latest daily streams (Spotify, with est. $/day) or daily chart points (iTunes).</span>
            <b style='color:var(--t2);white-space:nowrap;'>Change</b>
            <span>Net change in streams / points across the window.</span>
            <b style='color:var(--t2);white-space:nowrap;'>Δ Rank</b>
            <span>Net rank shift. ▲ Gaining rank indicates increasing audience demand; ▼ Falling indicates a cooling phase. 🚀 marks accelerating growth.</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Heating Up + New & Notable -->
  <div class='r2'>
    <div class='card' id='heating-card'>
      <div class='sh'><span class='sh-l'>🚀 Heating Up</span><span class='sh-r'>accelerating momentum</span></div>
      <div class='card-note'>Daily growth is speeding up — the earliest breakout signal, before net totals catch up.</div>
      <div id='sp-heat-block'>
        <div class='section-label' style='color:var(--green)'><span class='section-dot' style='background:var(--green)'></span>Spotify</div>
        <div id='sp-heating'></div>
      </div>
      <div id='it-heat-block' style='margin-top:16px'>
        <div class='section-label' style='color:var(--purple)'><span class='section-dot' style='background:var(--purple)'></span>iTunes</div>
        <div id='it-heating'></div>
      </div>
    </div>

    <div class='card' id='new-card'>
      <div class='sh'><span class='sh-l'>✨ New & Notable</span><span class='sh-r'>entrants & breakouts</span></div>
      <div class='card-note'>Fresh chart entrants and tracks crossing key rank milestones (Top 10 / Top 50).</div>
      <div id='sp-new-block'>
        <div class='section-label' style='color:var(--green)'><span class='section-dot' style='background:var(--green)'></span>Spotify</div>
        <div id='sp-new'></div>
      </div>
      <div id='it-new-block' style='margin-top:16px'>
        <div class='section-label' style='color:var(--purple)'><span class='section-dot' style='background:var(--purple)'></span>iTunes</div>
        <div id='it-new'></div>
      </div>
    </div>
  </div>

  <div class='r2'>
    <div class='card' id='risers-section'>
      <div class='sh'><span class='sh-l'>📈 Top Risers</span><span class='sh-r'>rank + metric composite</span></div>
      <div class='card-note'>Gaining momentum — tracks climbing the chart based on a composite of rank improvement and stream/point growth.</div>
      <div id='sp-riser-block'>
        <div class='section-label' style='color:var(--green)'><span class='section-dot' style='background:var(--green)'></span>Spotify · Rank + Streams</div>
        <div class='trk-hdr' style='grid-template-columns:24px 1fr 46px 46px 70px 64px 58px'>
          <span></span><span>Artist · Track</span><span style='text-align:center'>Start</span><span style='text-align:center'>Now</span><span style='text-align:right'>Streams</span><span style='text-align:right'>+Streams</span><span style='text-align:right'>Δ Rank</span>
        </div>
        <div id='sp-risers'></div>
      </div>
      <div id='it-riser-block' style='margin-top:16px'>
        <div class='section-label' style='color:var(--purple)'><span class='section-dot' style='background:var(--purple)'></span>iTunes · Rank + Score</div>
        <div class='trk-hdr' style='grid-template-columns:24px 1fr 46px 46px 70px 64px 58px'>
          <span></span><span>Artist · Track</span><span style='text-align:center'>Start</span><span style='text-align:center'>Now</span><span style='text-align:right'>Score</span><span style='text-align:right'>+Score</span><span style='text-align:right'>Δ Rank</span>
        </div>
        <div id='it-risers'></div>
      </div>
    </div>

    <div class='card' id='fallers-section'>
      <div class='sh'><span class='sh-l'>📉 Top Fallers</span><span class='sh-r'>rank + metric composite</span></div>
      <div class='card-note'>Falling trajectory — tracks losing ground due to dropping chart ranks and net stream/point losses.</div>
      <div id='sp-faller-block'>
        <div class='section-label' style='color:var(--red)'><span class='section-dot' style='background:var(--red)'></span>Spotify · Rank + Streams lost</div>
        <div class='trk-hdr' style='grid-template-columns:24px 1fr 46px 46px 70px 64px 58px'>
          <span></span><span>Artist · Track</span><span style='text-align:center'>Start</span><span style='text-align:center'>Now</span><span style='text-align:right'>Streams</span><span style='text-align:right'>Lost</span><span style='text-align:right'>Δ Rank</span>
        </div>
        <div id='sp-fallers'></div>
      </div>
      <div id='it-faller-block' style='margin-top:16px'>
        <div class='section-label' style='color:var(--red)'><span class='section-dot' style='background:var(--red)'></span>iTunes · Rank + Score lost</div>
        <div class='trk-hdr' style='grid-template-columns:24px 1fr 46px 46px 70px 64px 58px'>
          <span></span><span>Artist · Track</span><span style='text-align:center'>Start</span><span style='text-align:center'>Now</span><span style='text-align:right'>Score</span><span style='text-align:right'>Lost</span><span style='text-align:right'>Δ Rank</span>
        </div>
        <div id='it-fallers'></div>
      </div>
    </div>
  </div>

</div>

<script>
const PAYLOAD = __DATA__;
const PLATFORM = PAYLOAD.platform;
const SHOW_SP = PLATFORM !== 'iTunes';
const SHOW_IT = PLATFORM !== 'Spotify';
const RATE = PAYLOAD.per_stream;

function fmtN(n,dec=1){if(n===null||n===undefined||isNaN(n))return'—';n=parseFloat(n);const a=Math.abs(n),sign=n<0?'−':n>0?'+':'';if(a>=1e6)return sign+(a/1e6).toFixed(dec)+'M';if(a>=1e3)return sign+(a/1e3).toFixed(0)+'K';return sign+a.toFixed(0);}
function fmtM(n,dec=2){if(n===null||n===undefined||isNaN(n))return'—';n=parseFloat(n);const a=Math.abs(n);const sign=n<0?'−':'';return sign+(a/1e6).toFixed(dec)+'M';}
function fmtUSD(n){if(n===null||n===undefined||isNaN(n))return'—';n=parseFloat(n);const a=Math.abs(n),sign=n<0?'−':'';if(a>=1e6)return sign+'$'+(a/1e6).toFixed(2)+'M';if(a>=1e3)return sign+'$'+(a/1e3).toFixed(1)+'K';return sign+'$'+a.toFixed(0);}
function fmtUSDsigned(n){if(n===null||n===undefined||isNaN(n))return'—';const s=n>0?'+':n<0?'−':'';n=Math.abs(parseFloat(n));if(n>=1e6)return s+'$'+(n/1e6).toFixed(2)+'M';if(n>=1e3)return s+'$'+(n/1e3).toFixed(1)+'K';return s+'$'+n.toFixed(0);}

function toggleGuide(){const c=document.getElementById('guide-content');const i=document.getElementById('guide-toggle-icon');if(c.style.display==='none'){c.style.display='block';i.textContent='[ Hide Details ]';}else{c.style.display='none';i.textContent='[ Show Details ]';}}

// ── KPI bar ──
function renderKPIs(){
  const k = PAYLOAD.kpis || {};
  const hot = k.hottest, sw = k.rev_swing;
  const tiles = [
    {l:'Est. daily revenue', v:fmtUSD(k.est_daily_rev), c:'g', s:'Spotify · tracked tracks'},
    {l:'Revenue swing', v:fmtUSDsigned(k.rev_delta), c:(k.rev_delta>=0?'g':'r'), s:'Δ over '+PAYLOAD.period},
    {l:'Independent share', v:(k.indie_share!=null?k.indie_share+'%':'—'), c:'b', s:'of tracked streaming'},
    {l:'New entries', v:(k.new_count!=null?k.new_count:'—'), c:'a', s:k.breakout_top10+' broke into Top 10'},
    {l:'Hottest track', v:(hot?'🚀':'—'), c:'t', s:hot?(hot.n+' — '+hot.t):'no acceleration'},
    {l:'Biggest $ swing', v:(sw?fmtUSDsigned(sw.rev_delta):'—'), c:(sw&&sw.rev_delta>=0?'g':'r'), s:sw?(sw.n+' — '+sw.t):'—'},
  ];
  document.getElementById('kpi-bar').innerHTML = tiles.map(t=>
    `<div class='kpi'><div class='kpi-lbl'>${t.l}</div><div class='kpi-val ${t.c}'>${t.v}</div><div class='kpi-sub'>${t.s}</div></div>`
  ).join('');
}

// ── chips ──
function tierChip(t){return t==='Major'?`<span class='chip chip-major'>Major</span>`:'';}
function metaChips(d){
  let c = tierChip(d.tier);
  if(d.crossed){c+=`<span class='chip chip-cross'>↑Top ${d.crossed}</span>`;}
  else if(d.new){c+=`<span class='chip chip-new'>New</span>`;}
  return c;
}

// ── Risers / Fallers table ──
function renderTable(elId, data, isSpotify){
  const el = document.getElementById(elId);
  if(!el) return;
  if(!data || !data.length){ el.innerHTML="<div class='empty'>No data in selected window.</div>"; return; }
  let html='';
  data.forEach((d,i)=>{
    const metricArr = d.streams || d.scores || [];
    const latVal = [...metricArr].reverse().find(v=>v!==null) || 0;
    const latRank = [...d.ranks].reverse().find(v=>v!==null);
    const startRank = d.ranks.find(v=>v!==null);
    const rankColor = d.rg>0?'var(--green)':d.rg<0?'var(--red)':'var(--t3)';
    const sgColor = d.sg>0?'var(--blue)':d.sg<0?'var(--red)':'var(--t3)';
    const sgSign = d.sg>0?'+':d.sg<0?'−':'';
    const valFmt = isSpotify ? fmtM(latVal,2) : (latVal||0).toLocaleString();
    const valSub = isSpotify ? `<div class='tv-sub'>${fmtUSD(d.rev)}/day</div>` : '';
    const sgLabel = isSpotify ? fmtM(Math.abs(d.sg),2) : Math.abs(d.sg).toLocaleString();
    const rankBadge = d.rg>0?`<span class='bu'>▲${d.rg}</span>`:d.rg<0?`<span class='bd'>▼${Math.abs(d.rg)}</span>`:`<span class='bn'>—</span>`;
    const heat = (d.accel>0)?` <span class='accel' title='accelerating'>🚀</span>`:'';
    html += `<div class='trk' style='grid-template-columns:24px 1fr 46px 46px 70px 64px 58px'>
      <span class='rn'>${i+1}</span>
      <div style='min-width:0'>
        <div class='tn'>${d.t}</div>
        <div class='ta'>${d.n} ${metaChips(d)}</div>
      </div>
      <span style='font-size:13px;color:var(--t3);text-align:center;font-weight:600'>${startRank||'—'}</span>
      <span style='font-size:13px;color:${rankColor};text-align:center;font-weight:700'>${latRank||'—'}</span>
      <div><div class='tv'>${valFmt}</div>${valSub}</div>
      <span class='tv' style='color:${sgColor}'>${sgSign}${sgLabel}</span>
      <span style='text-align:right'>${rankBadge}${heat}</span>
    </div>`;
  });
  el.innerHTML = html;
}

// ── Heating / New compact list ──
function renderCompact(elId, data, isSpotify, kind){
  const el = document.getElementById(elId);
  if(!el) return;
  if(!data || !data.length){ el.innerHTML=`<div class='empty'>None in selected window.</div>`; return; }
  let html='';
  data.forEach((d,i)=>{
    const latRank = [...d.ranks].reverse().find(v=>v!==null);
    let right;
    if(kind==='heat'){
      const a = isSpotify ? fmtN(d.accel) : (d.accel>0?'+':'')+d.accel.toLocaleString();
      right = `<span class='accel'>🚀 ${a}/day</span>`;
    } else {
      right = d.crossed?`<span class='chip chip-cross'>↑Top ${d.crossed}</span>`:`<span class='chip chip-new'>New</span>`;
    }
    html += `<div class='trk' style='grid-template-columns:22px 1fr auto'>
      <span class='rn'>${i+1}</span>
      <div style='min-width:0'>
        <div class='tn'>${d.t}</div>
        <div class='ta'>${d.n} ${tierChip(d.tier)} <span style='color:var(--t3)'>#${latRank||'—'}</span></div>
      </div>
      <span style='text-align:right;font-size:12px;font-weight:700'>${right}</span>
    </div>`;
  });
  el.innerHTML = html;
}

// ── platform visibility ──
if(!SHOW_SP){['sp-riser-block','sp-faller-block','sp-heat-block','sp-new-block'].forEach(id=>{const e=document.getElementById(id);if(e)e.classList.add('hide');});}
if(!SHOW_IT){['it-riser-block','it-faller-block','it-heat-block','it-new-block'].forEach(id=>{const e=document.getElementById(id);if(e)e.classList.add('hide');});}

// ── render ──
renderKPIs();
if(SHOW_SP){
  renderTable('sp-risers', PAYLOAD.sp_risers, true);
  renderTable('sp-fallers', PAYLOAD.sp_fallers, true);
  renderCompact('sp-heating', PAYLOAD.sp_heating, true, 'heat');
  renderCompact('sp-new', PAYLOAD.sp_new, true, 'new');
}
if(SHOW_IT){
  renderTable('it-risers', PAYLOAD.it_risers, false);
  renderTable('it-fallers', PAYLOAD.it_fallers, false);
  renderCompact('it-heating', PAYLOAD.it_heating, false, 'heat');
  renderCompact('it-new', PAYLOAD.it_new, false, 'new');
}
</script>
</body></html>
""".replace("__DATA__", data_json).replace("__THEME__", theme_css).replace("__RATE__", str(payload.get("per_stream", SPOTIFY_NET_PER_STREAM_USD))).replace("__NEWDAYS__", str(NEW_ON_CHART_DAYS))
