"""
Album Movement dashboard — rich HTML/JS dashboard rendering rank + metric
momentum for iTunes and iTunes top tracks. Pulls dynamic data from the
itunes_artist_album and itunes_artist_album tables.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src.database.connection import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Region scope -> (itunes_country, itunes_country)
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


def _top20_today(df: pd.DataFrame, latest: date) -> list[dict[str, Any]]:
    today = df[df["date"] == latest].copy()
    if today.empty:
        return []
    # Find previous date for change computation
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
        "Rank + metric momentum across iTunes and iTunes daily charts."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Filter bar ────────────────────────────────────────────────
    c1, c2 = st.columns([1.2, 1.2])
    with c1:
        scope_label = st.selectbox("Region", list(SCOPES.keys()), index=0, key="am_scope")
    with c2:
        period_label = st.selectbox("Period", list(PERIOD_DAYS.keys()), index=0, key="am_period")

    sp_country, it_country = SCOPES[scope_label]
    days = PERIOD_DAYS[period_label]

    it_df = _load_window("itunes_artist_album", it_country, days)

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
    rising_count = sum(1 for r in it_records if r["rg"] > 0)

    # Spotlight = top riser per platform
    it_spot = it_risers[0] if it_risers else None

    date_strs = [d.strftime("%b %d") for d in all_dates]
    window_label = f"{all_dates[0].strftime('%b %d')}–{all_dates[-1].strftime('%b %d, %Y')} · {PERIOD_LABELS[period_label]}"

    payload = {
        "dates": date_strs,
        "window_label": window_label,
        "scope": scope_label,
        "it_risers": it_risers,
        "it_fallers": it_fallers,
        "it_top20": it_top20,
        "it_spot": it_spot,
        "kpis": {
            "it_no1": it_no1,
            "big_rank_riser": big_rank_riser,
            "big_faller": big_faller,
            "rising_count": rising_count,
            "tracked": len(it_records),
        },
    }

    html = _build_html(payload)
    st_components.html(html, height=1700, scrolling=True)


# ─────────────────────────── HTML template ───────────────────────────

def _build_html(payload: dict) -> str:
    data_json = json.dumps(payload, default=str)
    return f"""
<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0d1117;--bg2:#161b26;--bg3:#1f2633;--bg4:#283041;
  --border:#2a3446;--border2:#3a4661;
  --t1:#ffffff;--t2:#cdd6e4;--t3:#8b95ad;--t4:#5b657d;
  --green:#34d399;--gd:rgba(52,211,153,.18);
  --red:#fb7185;--rd:rgba(251,113,133,.18);
  --blue:#60a5fa;--bd:rgba(96,165,250,.18);
  --purple:#c4b5fd;--pd:rgba(196,181,253,.18);
  --amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;
}}
body{{background:var(--bg);font-family:'Inter',system-ui,sans-serif;color:var(--t1);font-size:15px;line-height:1.55}}
.hdr{{background:linear-gradient(180deg,#1a2235 0%,var(--bg2) 100%);border-bottom:1px solid var(--border);padding:20px 24px 16px}}
.hdr-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:10px}}
.brand{{font-size:11px;color:var(--t3);letter-spacing:1.4px;text-transform:uppercase;display:flex;align-items:center;gap:7px;margin-bottom:6px;font-weight:600}}
.live{{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:blink 2s infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.dash-title{{font-size:26px;font-weight:700;letter-spacing:-.5px;color:#fff}}
.dash-sub{{font-size:12px;color:var(--t2);letter-spacing:.3px;margin-top:4px;font-weight:500}}
.kpi-bar{{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--border);border-bottom:1px solid var(--border)}}
.kpi{{background:var(--bg2);padding:16px 18px;transition:.15s}}
.kpi:hover{{background:var(--bg3)}}
.kpi-lbl{{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px;font-weight:600}}
.kpi-val{{font-size:24px;font-weight:700;letter-spacing:-.5px;line-height:1.15;color:#fff}}
.kpi-sub{{font-size:11px;color:var(--t2);margin-top:5px;font-weight:500}}
.kpi-val.g{{color:var(--green)}}.kpi-val.r{{color:var(--red)}}.kpi-val.p{{color:var(--purple)}}.kpi-val.a{{color:var(--amber)}}.kpi-val.b{{color:var(--blue)}}
.body{{padding:20px 22px;display:flex;flex-direction:column;gap:20px}}
.sh{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}}
.sh-l{{font-size:16px;font-weight:600;color:#fff;letter-spacing:-.2px}}
.sh-r{{font-size:11px;color:var(--t2);background:var(--bg3);padding:5px 12px;border-radius:5px;border:1px solid var(--border2);font-weight:500}}
.r2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.card{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px 20px}}
.card-ttl{{font-size:12px;color:var(--t2);text-transform:uppercase;letter-spacing:.7px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border);font-weight:600}}
.trk-hdr{{display:grid;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2);margin-bottom:4px}}
.trk-hdr span{{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;font-weight:600}}
.trk{{display:grid;gap:8px;padding:11px 0;border-bottom:1px solid var(--border);align-items:center;cursor:pointer;transition:.1s}}
.trk:hover{{background:var(--bg3);margin:0 -8px;padding:11px 8px;border-radius:6px}}
.trk:last-child{{border-bottom:none}}
.rn{{font-size:13px;color:var(--t3);text-align:center;min-width:20px;font-weight:600}}
.tn{{font-size:14px;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-.1px}}
.ta{{font-size:11px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px;font-weight:500}}
.tv{{font-size:13px;color:var(--t1);text-align:right;white-space:nowrap;font-weight:600;font-variant-numeric:tabular-nums}}
.dual-bar{{display:flex;gap:4px;margin-top:6px;height:5px}}
.dual-seg{{flex:1;border-radius:3px;position:relative;overflow:hidden;background:var(--bg4)}}
.dual-fill{{height:5px;border-radius:3px;position:absolute;top:0;left:0}}
.bu{{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--gd);color:var(--green);min-width:42px;border:1px solid rgba(52,211,153,.35)}}
.bd{{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--rd);color:var(--red);min-width:42px;border:1px solid rgba(251,113,133,.35)}}
.bn{{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;padding:4px 9px;border-radius:5px;background:var(--bg3);color:var(--t2);min-width:42px;border:1px solid var(--border2)}}
.bh{{display:inline-flex;font-size:11px;font-weight:700;padding:5px 10px;border-radius:5px;background:rgba(252,211,77,.15);color:var(--amber);border:1px solid rgba(252,211,77,.4);letter-spacing:.4px}}
.bp{{display:inline-flex;font-size:11px;font-weight:700;padding:5px 10px;border-radius:5px;background:var(--pd);color:var(--purple);border:1px solid rgba(196,181,253,.4);letter-spacing:.4px}}
.spot{{background:linear-gradient(135deg,#1a2235 0%,var(--bg2) 100%);border:1px solid var(--border2);border-radius:12px;padding:20px 22px;position:relative;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.3)}}
.spot::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--green),var(--teal))}}
.sp-tag{{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px;font-weight:600}}
.sp-name{{font-size:22px;font-weight:700;letter-spacing:-.5px;line-height:1.2;margin-bottom:6px;color:#fff}}
.sp-meta{{font-size:12px;color:var(--t2);margin-bottom:16px;font-weight:500}}
.sp-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.sp-s{{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px 14px}}
.sp-s-l{{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;font-weight:600}}
.sp-s-v{{font-size:20px;font-weight:700;color:#fff;letter-spacing:-.4px;font-variant-numeric:tabular-nums}}
.cw{{position:relative;width:100%}}
.hide{{display:none !important}}
.section-label{{font-size:13px;font-weight:700;letter-spacing:.5px;margin-bottom:14px;display:flex;align-items:center;gap:8px;text-transform:uppercase}}
.section-dot{{width:10px;height:10px;border-radius:50%;display:inline-block;box-shadow:0 0 6px currentColor}}
</style></head><body>

<div class='hdr'>
  <div class='hdr-top'>
    <div>
      <div class='brand'><span class='live'></span>Chromadata · Album Movement Intelligence · <span id='hdr-window'></span></div>
      <div class='dash-title'>Album Momentum Dashboard</div>
      <div class='dash-sub' id='hdr-sub'></div>
    </div>
  </div>
</div>

<div class='kpi-bar' id='kpi-bar'></div>

<div class='body'>

  <div class='r2' id='spot-row'></div>

  <div id='risers-section'>
    <div class='sh'><span class='sh-l'>📈 Top Risers — rank + metric composite</span><span class='sh-r' id='riser-period'></span></div>
    <div class='r2'>
      <div id='it-riser-block'>
        <div class='section-label' style='color:var(--purple)'>
          <span class='section-dot' style='background:var(--purple)'></span>ITUNES — Rank + Score
        </div>
        <div class='trk-hdr' style='grid-template-columns:24px 1fr 50px 50px 64px 64px 60px'>
          <span></span><span>Album · Artist</span><span style='text-align:center'>Start</span><span style='text-align:center'>Now</span><span style='text-align:right'>Score</span><span style='text-align:right'>+Score</span><span style='text-align:right'>Δ Rank</span>
        </div>
        <div id='it-risers'></div>
      </div>
    </div>
  </div>

  <div id='fallers-section'>
    <div class='sh'><span class='sh-l'>📉 Top Fallers — rank + metric composite</span><span class='sh-r' id='faller-period'></span></div>
    <div class='r2'>
      <div id='it-faller-block'>
        <div class='section-label' style='color:var(--red)'>
          <span class='section-dot' style='background:var(--red)'></span>ITUNES — Rank + Score lost
        </div>
        <div class='trk-hdr' style='grid-template-columns:24px 1fr 50px 50px 64px 64px 60px'>
          <span></span><span>Album · Artist</span><span style='text-align:center'>Start</span><span style='text-align:center'>Now</span><span style='text-align:right'>Score</span><span style='text-align:right'>Lost</span><span style='text-align:right'>Δ Rank</span>
        </div>
        <div id='it-fallers'></div>
      </div>
    </div>
  </div>

  <div class='card' id='it-traj-card' style='display:none'>
    <div class='card-ttl'>iTunes — top 8 risers score trajectory (higher = better)</div>
    <div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px' id='it-traj-leg'></div>
    <div class='cw' style='height:220px'><canvas id='itTrajChart'></canvas></div>
  </div>

  <div class='card' id='it-scatter-card' style='display:none'>
    <div class='card-ttl'>iTunes — score gain vs rank gain</div>
    <div class='cw' style='height:240px'><canvas id='itScatterChart'></canvas></div>
  </div>

  <div class='card' id='it-top20-card' style='display:none'>
    <div class='card-ttl'>iTunes top 20 today · colour = daily score change</div>
    <div class='cw' style='height:310px'><canvas id='it20Chart'></canvas></div>
  </div>

</div>

<script src='https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js'></script>
<script>
const PAYLOAD = {data_json};

function fmtN(n,dec=1){{if(n===null||n===undefined||isNaN(n))return'—';n=parseFloat(n);const a=Math.abs(n),sign=n<0?'−':n>0?'+':'';if(a>=1e6)return sign+(a/1e6).toFixed(dec)+'M';if(a>=1e3)return sign+(a/1e3).toFixed(0)+'K';return sign+a.toFixed(0);}}
function fmtM(n,dec=2,signed=false){{if(n===null||n===undefined||isNaN(n))return'—';n=parseFloat(n);const a=Math.abs(n);const sign=signed?(n<0?'−':n>0?'+':''):(n<0?'−':'');return sign+(a/1e6).toFixed(dec)+'M';}}
const DATES = PAYLOAD.dates;

// Header
document.getElementById('hdr-window').textContent = PAYLOAD.window_label;
document.getElementById('hdr-sub').textContent = `${{PAYLOAD.scope}} · iTunes`;
document.getElementById('riser-period').textContent = PAYLOAD.window_label;
document.getElementById('faller-period').textContent = PAYLOAD.window_label;

// KPI bar
function kpiCard(lbl, val, sub, cls){{
  return `<div class='kpi'><div class='kpi-lbl'>${{lbl}}</div><div class='kpi-val ${{cls||''}}' style='${{val&&val.length>10?'font-size:12px;margin-top:3px':''}}'>${{val||'—'}}</div><div class='kpi-sub'>${{sub||''}}</div></div>`;
}}
const k = PAYLOAD.kpis;
const kpiHtml = [
  kpiCard('iTunes #1 today', k.it_no1?k.it_no1.a:'—', k.it_no1?`${{k.it_no1.t}} · ${{(k.it_no1.s).toLocaleString()}} pts`:''),
  kpiCard('Biggest rank riser', k.big_rank_riser?'+'+k.big_rank_riser.rg:'—', k.big_rank_riser?`${{k.big_rank_riser.n}} · ${{k.big_rank_riser.t}}`:'', 'g'),
  kpiCard('Biggest faller', k.big_faller?k.big_faller.rg:'—', k.big_faller?`${{k.big_faller.n}} · ${{k.big_faller.t}}`:'', 'r'),
  kpiCard('Albums rising', k.rising_count, `of ${{k.tracked}} tracked`, 'a'),
].join('');
document.getElementById('kpi-bar').innerHTML = kpiHtml;

// Spotlights
function spotCard(d, kind){{
  if (!d) return '';
  const tag = "<span class='bp'>🔥 ITUNES TOP RISER</span>";
  const accent = 'var(--purple)';
  const metricArr = d.scores || [];
  const startRank = d.ranks.find(v=>v!==null);
  const endRank = [...d.ranks].reverse().find(v=>v!==null);
  const startMet = metricArr.find(v=>v!==null) || 0;
  const endMet = [...metricArr].reverse().find(v=>v!==null) || 0;
  const metLabel = 'Score gain';
  const style = "style='--green:#a78bfa;--teal:#60a5fa'";
  return `<div class='spot' ${{style}}>
    <div class='sp-tag'>${{tag}}</div>
    <div class='sp-name'>${{d.n}} — ${{d.t}}</div>
    <div class='sp-meta'>${{d.lbl}} · #${{startRank}} → #${{endRank}}</div>
    <div class='sp-grid'>
      <div class='sp-s'><div class='sp-s-l'>Start rank</div><div class='sp-s-v'>#${{startRank}}</div></div>
      <div class='sp-s'><div class='sp-s-l'>Now</div><div class='sp-s-v' style='color:${{accent}}'>#${{endRank}}</div></div>
      <div class='sp-s'><div class='sp-s-l'>Rank gain</div><div class='sp-s-v' style='color:var(--amber)'>+${{d.rg}}</div></div>
      <div class='sp-s'><div class='sp-s-l'>${{metLabel}}</div><div class='sp-s-v' style='color:var(--blue)'>${{fmtN(d.sg,0)}}</div></div>
    </div>
  </div>`;
}}
const spotHtml = [
  spotCard(PAYLOAD.it_spot, 'it')
].filter(Boolean).join('');
document.getElementById('spot-row').innerHTML = spotHtml;
document.getElementById('spot-row').style.gridTemplateColumns = '1fr';

// Riser/faller table renderer
function renderTable(elId, data){{
  const el = document.getElementById(elId);
  if (!el) return;
  if (!data || !data.length) {{ el.innerHTML = "<div style='color:#444;font-size:10px;padding:14px 0'>No data in selected window.</div>"; return; }}
  el.innerHTML = '';
  const maxRg = Math.max(...data.map(d=>Math.abs(d.rg)),1);
  const maxSg = Math.max(...data.map(d=>Math.abs(d.sg)),1);
  data.forEach((d,i)=>{{
    const metricArr = d.scores || [];
    const latVal = [...metricArr].reverse().find(v=>v!==null) || 0;
    const latRank = [...d.ranks].reverse().find(v=>v!==null);
    const startRank = d.ranks.find(v=>v!==null);
    const rankPct = Math.min(Math.abs(d.rg)/maxRg*100, 100);
    const sgPct = Math.min(Math.abs(d.sg)/maxSg*100, 100);
    const isPos = d.rg > 0;
    const rankColor = isPos?'var(--green)':d.rg<0?'var(--red)':'var(--t3)';
    const sgColor = d.sg>0?'var(--blue)':d.sg<0?'var(--red)':'var(--t3)';
    const sgSign = d.sg>0?'+':d.sg<0?'−':'';
    const valFmt = (latVal||0).toLocaleString();
    const sgLabel = Math.abs(d.sg).toLocaleString();
    const rankBadge = isPos ? `<span class='bu'>▲${{d.rg}}</span>` : d.rg<0 ? `<span class='bd'>▼${{Math.abs(d.rg)}}</span>` : `<span class='bn'>—</span>`;
    el.innerHTML += `<div class='trk' style='grid-template-columns:24px 1fr 50px 50px 64px 64px 60px'>
      <span class='rn'>${{i+1}}</span>
      <div>
        <div class='tn'>${{d.t}}</div>
        <div class='ta'>${{d.n}}</div>
        <div class='dual-bar'>
          <div class='dual-seg'><div class='dual-fill' style='width:${{rankPct}}%;background:${{rankColor}}'></div></div>
          <div class='dual-seg'><div class='dual-fill' style='width:${{sgPct}}%;background:${{sgColor}}'></div></div>
        </div>
      </div>
      <span style='font-size:13px;color:var(--t3);text-align:center;font-weight:600'>#${{startRank||'—'}}</span>
      <span style='font-size:13px;color:${{rankColor}};text-align:center;font-weight:700'>#${{latRank||'—'}}</span>
      <span class='tv'>${{valFmt}}</span>
      <span class='tv' style='color:${{sgColor}}'>${{sgSign}}${{sgLabel.replace('+','').replace('−','')}}</span>
      <span style='text-align:right'>${{rankBadge}}</span>
    </div>`;
  }});
}}
renderTable('it-risers', PAYLOAD.it_risers);
renderTable('it-fallers', PAYLOAD.it_fallers);

</script>
</body></html>
"""
