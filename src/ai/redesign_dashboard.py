from __future__ import annotations

import json
import math
from datetime import timedelta
from html import escape
from typing import Any
import textwrap

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as st_components

from src.scrapers.artist_details_scraper import LATIN_AMERICAN_COUNTRIES

PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}

_PALETTE = {
    "green": "#34d399",
    "blue": "#60a5fa",
    "amber": "#fcd34d",
    "pink": "#fb7185",
    "purple": "#c4b5fd",
    "teal": "#5eead4",
    "red": "#ef4444",
    "slate": "#94a3b8",
}

# ── Theme CSS variables (matching album_movement pattern) ────────────────────
_THEME_DARK = (
    ":root{"
    "--a-bg:#0d1117;--a-bg2:#161b26;--a-bg3:#1f2633;--a-bg4:#283041;"
    "--a-border:rgba(148,163,184,.15);--a-border2:rgba(148,163,184,.28);"
    "--a-t1:#ffffff;--a-t2:#cdd6e4;--a-t3:#8b95ad;--a-t4:#6b7a99;"
    "--a-green:#34d399;--a-gd:rgba(52,211,153,.18);"
    "--a-red:#fb7185;--a-rd:rgba(251,113,133,.18);"
    "--a-blue:#60a5fa;--a-bd:rgba(96,165,250,.18);"
    "--a-amber:#fcd34d;--a-purple:#c4b5fd;"
    "--a-nav-active-bg:rgba(96,165,250,.14);--a-nav-active-text:#dbeafe;--a-nav-active-border:rgba(96,165,250,.36);"
    "--a-brief-good:rgba(52,211,153,.4);--a-brief-bad:rgba(251,113,133,.4);--a-brief-neutral:rgba(96,165,250,.4);"
    "--a-acq-score:#93c5fd;--a-acq-panel:rgba(15,20,35,.92);--a-acq-detail:rgba(15,20,35,.96);"
    "--a-market-bg:rgba(34,197,94,.10);--a-market-border:rgba(34,197,94,.16);--a-market-text:#86efac;"
    "--a-alert-bg:rgba(251,191,36,.10);--a-alert-border:rgba(251,191,36,.30);--a-alert-text:#fcd34d;"
    "}"
)
_THEME_LIGHT = (
    ":root{"
    "--a-bg:#F5F6FA;--a-bg2:#FFFFFF;--a-bg3:#F8F9FB;--a-bg4:#EEF1F7;"
    "--a-border:rgba(148,163,184,.2);--a-border2:rgba(148,163,184,.35);"
    "--a-t1:#1A1A1A;--a-t2:#4A5568;--a-t3:#8A8FA3;--a-t4:#A0AEC0;"
    "--a-green:#16a34a;--a-gd:rgba(22,163,74,.14);"
    "--a-red:#dc2626;--a-rd:rgba(220,38,38,.12);"
    "--a-blue:#2563eb;--a-bd:rgba(37,99,235,.14);"
    "--a-amber:#b45309;--a-purple:#7c3aed;"
    "--a-nav-active-bg:rgba(37,99,235,.10);--a-nav-active-text:#1d4ed8;--a-nav-active-border:rgba(37,99,235,.22);"
    "--a-brief-good:rgba(22,163,74,.5);--a-brief-bad:rgba(220,38,38,.5);--a-brief-neutral:rgba(37,99,235,.5);"
    "--a-acq-score:#1d4ed8;--a-acq-panel:#ffffff;--a-acq-detail:#f8fafc;"
    "--a-market-bg:rgba(22,163,74,.10);--a-market-border:rgba(22,163,74,.16);--a-market-text:#166534;"
    "--a-alert-bg:rgba(180,83,9,.08);--a-alert-border:rgba(180,83,9,.22);--a-alert-text:#92400e;"
    "}"
)


# ── Pure-Python helpers ──────────────────────────────────────────────────────

def _fmt_n(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "0"
    value = float(value)
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(int(value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


def _percentile(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=float)
    return series.rank(pct=True, method="average").fillna(0.0)


def _parse_rank_change(value: Any) -> float:
    raw = str(value or "").strip().upper()
    if not raw or raw in {"=", "—", "-", "0"}:
        return 0.0
    if raw == "NEW":
        return 12.0
    cleaned = raw.replace("▲", "").replace("▼", "").replace("+", "").replace("-", "")
    try:
        amount = float(cleaned)
    except ValueError:
        return 0.0
    if raw.startswith("-") or "▼" in raw:
        return -abs(amount)
    return abs(amount)


def _sparkline_svg(
    values: list,
    *,
    width: int = 180,
    height: int = 54,
    color: str = "#60a5fa",
    reverse: bool = False,
) -> str:
    clean = [float(v) for v in values if v is not None and pd.notna(v)]
    if not clean:
        clean = [0.0, 0.0]
    if len(clean) == 1:
        clean = clean * 2
    min_v, max_v = min(clean), max(clean)
    span = max(max_v - min_v, 1.0)
    px, py = 4, 5
    uw = max(width - px * 2, 1)
    uh = max(height - py * 2, 1)
    fill_pts, line_pts = [], []
    for idx, raw in enumerate(clean):
        x = px + (idx / max(len(clean) - 1, 1)) * uw
        norm = (raw - min_v) / span
        if reverse:
            norm = 1.0 - norm
        y = py + (1.0 - norm) * uh
        pt = f"{x:.1f},{y:.1f}"
        line_pts.append(pt)
        fill_pts.append(pt)
    sid = f"sp-{abs(hash(tuple(round(v, 2) for v in clean)))}"
    return (
        f"<svg viewBox='0 0 {width} {height}' style='width:100%;height:100%' role='img'>"
        f"<defs><linearGradient id='{sid}' x1='0' x2='0' y1='0' y2='1'>"
        f"<stop offset='0%' stop-color='{color}' stop-opacity='.28'/>"
        f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/></linearGradient></defs>"
        f"<polygon points='{' '.join(fill_pts)} {width-px},{height-py} {px},{height-py}' fill='url(#{sid})' opacity='.8'></polygon>"
        f"<polyline points='{' '.join(line_pts)}' fill='none' stroke='{color}' stroke-width='2.4' stroke-linejoin='round' stroke-linecap='round'></polyline>"
        "</svg>"
    )


def _build_history_profiles(history: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if history.empty:
        return {}
    df = history.copy()
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    df = df.dropna(subset=["scraped_at", "name", "rank"])
    if df.empty:
        return {}
    latest_allowed = df["scraped_at"].max() - timedelta(days=45)
    df = df[df["scraped_at"] >= latest_allowed]
    profiles: dict[str, dict[str, Any]] = {}
    for artist, group in df.groupby("name"):
        ordered = group.sort_values("scraped_at")
        by_day = (
            ordered.assign(day=ordered["scraped_at"].dt.date)
            .groupby("day", as_index=False)["rank"].min()
            .sort_values("day")
        )
        if by_day.empty:
            continue
        ranks = by_day["rank"].astype(float).tolist()
        first_rank, last_rank = float(ranks[0]), float(ranks[-1])
        slope = 0.0
        if len(ranks) >= 2:
            x = np.arange(len(ranks), dtype=float)
            try:
                slope = float(np.polyfit(x, np.asarray(ranks, dtype=float), 1)[0])
            except Exception:
                pass
        profiles[artist] = {
            "rank_delta": first_rank - last_rank,
            "rank_slope": slope,
            "rank_series": ranks,
            "rank_span": len(ranks),
        }
    return profiles


def _prep_frame(leaderboard: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()
    df = leaderboard.copy()
    numeric_cols = [
        "rank", "monthly_listeners", "peak_listeners", "total_points",
        "itunes_points", "spotify_points", "apple_music_points", "shazam_points",
        "youtube_points", "other_points", "songs_count", "albums_count",
        "countries_count", "times_on_chart", "weeks_on_chart", "times_at_top",
        "max_countries", "best_rank",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "top_country" not in df.columns:
        df["top_country"] = "—"
    if "display_country" not in df.columns:
        df["display_country"] = df["top_country"].fillna("—")

    profiles = _build_history_profiles(history)
    df["rank_delta_45d"] = df["name"].map(lambda n: profiles.get(n, {}).get("rank_delta", 0.0))
    df["rank_slope_45d"] = df["name"].map(lambda n: profiles.get(n, {}).get("rank_slope", 0.0))
    df["rank_span_45d"] = df["name"].map(lambda n: profiles.get(n, {}).get("rank_span", 0))
    df["rank_series"] = df["name"].map(lambda n: profiles.get(n, {}).get("rank_series", []))
    df["rank_change_num"] = (
        df["rank_change"].map(_parse_rank_change) if "rank_change" in df.columns else 0.0
    )

    rank_base = df["rank"].fillna(df["rank"].max() + 1) if "rank" in df.columns and df["rank"].notna().any() else pd.Series(0, index=df.index)
    df["rank_score"] = 1.0 - _percentile(rank_base) if df["rank"].notna().any() else 0.0
    df["listener_score"] = _percentile(df["monthly_listeners"]) if "monthly_listeners" in df.columns and df["monthly_listeners"].notna().any() else 0.0
    df["point_score"] = _percentile(df["total_points"]) if "total_points" in df.columns and df["total_points"].notna().any() else 0.0
    df["coverage_score"] = _percentile(df["countries_count"]) if "countries_count" in df.columns and df["countries_count"].notna().any() else 0.0

    momentum_raw = df["rank_delta_45d"].fillna(0.0) + df["rank_change_num"].fillna(0.0)
    max_mom = momentum_raw.abs().max()
    df["momentum_score"] = (momentum_raw / max_mom).clip(-1, 1) if max_mom > 0 else 0.0

    df["acq_score"] = (100 * (
        0.35 * df["listener_score"] + 0.25 * df["point_score"]
        + 0.20 * df["coverage_score"] + 0.20 * df["rank_score"]
    )).round(0)
    df["hold_score"] = (100 * (
        0.40 * df["listener_score"] + 0.35 * df["point_score"]
        + 0.15 * df["coverage_score"] + 0.10 * (1 - df["momentum_score"].abs().clip(0, 1))
    )).round(0)
    df["fatigue_alert"] = (
        df["listener_score"] * 0.65 + df["coverage_score"] * 0.20
        + (-df["momentum_score"]).clip(lower=0, upper=1) * 0.35
    ) * 100
    df["hold_alert"] = (df["hold_score"] + (1 - df["momentum_score"].abs().clip(0, 1)) * 20).round(0)

    def _classify(row: pd.Series) -> str:
        mom = float(row.get("momentum_score") or 0.0)
        rd = float(row.get("rank_delta_45d") or 0.0)
        if rd <= -5 or mom <= -0.2:
            return "slipping"
        if rd >= 5 or mom >= 0.2:
            return "rising"
        return "holding"

    df["verdict"] = df.apply(_classify, axis=1)
    for col in ["songs_count", "albums_count", "countries_count"]:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    return df


def _filter_acq_rows(df: pd.DataFrame, *, latam_only: bool, independent_only: bool) -> pd.DataFrame:
    out = df.copy()
    if latam_only:
        if "latam_signal" in out.columns:
            out = out[out["latam_signal"].fillna(False)]
        else:
            out = out[out["display_country"].isin(LATIN_AMERICAN_COUNTRIES)]
    if independent_only and "label" in out.columns:
        lbl = out["label"].fillna("").astype(str).str.lower()
        out = out[lbl.str.contains("independent") | lbl.str.contains("indie") | lbl.eq("ind")]
    return out


# ── HTML/JS dashboard builder ────────────────────────────────────────────────

def _build_dashboard_html(
    focus_pool: pd.DataFrame,
    *,
    dark_mode: bool,
    active_mode: str,          # "Track" | "Album" | "Artist"
    latam_only: bool,
    independent_only: bool,
    last_run_label: str,
    window_label: str,
) -> str:
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT

    # ── Compute all data needed for all panels ───────────────────────────
    # Today's brief
    brief_acq = (
        focus_pool[focus_pool["verdict"] == "rising"]
        .sort_values("acq_score", ascending=False)
        .head(3)
    )
    brief_fatigue = (
        focus_pool[focus_pool["verdict"] == "slipping"]
        .sort_values("fatigue_alert", ascending=False)
        .head(3)
    )
    brief_hold = focus_pool.sort_values("hold_alert", ascending=False).head(3)

    # Acquisition radar
    score_col = "hold_score" if active_mode == "Album" else ("fatigue_alert" if active_mode == "Artist" else "acq_score")
    score_formula = (
        "Score = listeners + catalog depth + stability."
        if active_mode == "Album"
        else "Score = listeners + momentum + coverage."
        if active_mode == "Artist"
        else "Score = 20% iTunes + 20% Spotify entries + 30% Spotify + 30% iTunes streams."
    )
    acq_rows = _filter_acq_rows(focus_pool, latam_only=latam_only, independent_only=independent_only)
    acq_rows = acq_rows.sort_values([score_col, "rank"], ascending=[False, True]).reset_index(drop=True)
    acq_list = _acq_rows_to_json(acq_rows, score_col=score_col, mode=active_mode)

    # Fatigue map (Plotly rendered separately via st, just need the alert data)
    slipping = focus_pool[focus_pool["verdict"] == "slipping"]
    fatigue_alert_html = ""
    if not slipping.empty:
        worst = slipping.sort_values("monthly_listeners", ascending=False).iloc[0]
        wname = escape(str(worst.get("name") or "Artist"))
        wmarket = escape(str(worst.get("display_country") or worst.get("top_country") or "Unknown"))
        wlisteners = escape(_fmt_n(worst.get("monthly_listeners")))
        wdelta = float(worst.get("rank_delta_45d") or 0.0)
        wdelta_text = f"{wdelta:+.1f}%"
        fatigue_alert_html = (
            f"<div class='a360-fatigue-alert'>"
            f"<span class='fa-icon'>⚠</span>"
            f"<span>{len(slipping)} artists in the fatigue zone this week. "
            f"Largest concern: <b>{wname} {escape(wdelta_text)} in {wmarket}</b> "
            f"at {wlisteners} listeners — biggest audience showing the steepest decline.</span>"
            f"</div>"
        )

    # Roster health cards
    roster_pool = focus_pool.sort_values(["hold_alert", "monthly_listeners"], ascending=[False, False])
    roster_cards_html = _build_roster_cards_html(roster_pool.head(8))

    # KPI strip
    snapshot_total = len(focus_pool)
    snapshot_risers = int((focus_pool["verdict"] == "rising").sum())
    snapshot_fatigue_count = int((focus_pool["verdict"] == "slipping").sum())
    snapshot_avg = _fmt_n(
        focus_pool["monthly_listeners"].dropna().mean()
        if focus_pool["monthly_listeners"].notna().any() else 0
    )

    # Generate the fatigue plot HTML block
    fatigue_fig = _make_fatigue_figure(focus_pool, dark_mode=dark_mode)
    if fatigue_fig.data:
        fatigue_fig.update_layout(
            template="plotly_dark" if dark_mode else "plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fatigue_chart_html = pio.to_html(
            fatigue_fig,
            config=PLOTLY_CONFIG,
            full_html=False,
            include_plotlyjs="cdn",
            default_width="100%",
            default_height="460px",
        )
        fatigue_chart_html = f"<div class='fatigue-chart-container'>{fatigue_chart_html}</div>"
    else:
        fatigue_chart_html = "<div class='empty-msg'>No fatigue map data available for the current slice.</div>"

    payload = {
        "kpis": {
            "total": snapshot_total,
            "risers": snapshot_risers,
            "fatigue": snapshot_fatigue_count,
            "avg_listeners": snapshot_avg,
            "last_run": last_run_label,
        },
        "window_label": window_label,
        "acq_list": acq_list,
        "score_formula": score_formula,
        "active_mode": active_mode,
        "latam_only": latam_only,
        "independent_only": independent_only,
        "brief_acq": _brief_rows_to_json(brief_acq),
        "brief_fatigue": _brief_rows_to_json(brief_fatigue, band="fatigue"),
        "brief_hold": _brief_rows_to_json(brief_hold),
        "fatigue_alert_html": fatigue_alert_html,
        "roster_cards_html": roster_cards_html,
    }

    data_json = json.dumps(payload, default=str)
    return (
        _HTML_TEMPLATE.replace("__THEME__", theme_css)
        .replace("__DATA__", data_json)
        .replace("__FATIGUE_CHART__", fatigue_chart_html)
    )


def _brief_rows_to_json(rows: pd.DataFrame, band: str = "acquire") -> list[dict]:
    out = []
    for _, row in rows.head(3).iterrows():
        mom = float(row.get("rank_delta_45d") or 0.0)
        label_str = str(row.get("label") or "").strip()
        if "independent" in label_str.lower() or "indie" in label_str.lower():
            label_type = "ind"
        elif label_str and label_str != "—":
            label_type = "small"
        else:
            label_type = ""
        out.append({
            "name": str(row.get("name") or "Unknown"),
            "genre": str(row.get("top_song") or ""),
            "mom": mom,
            "market": str(row.get("display_country") or row.get("top_country") or "—"),
            "listeners": _fmt_n(row.get("monthly_listeners")),
            "label_str": label_str,
            "label_type": label_type,
            "band": band,
        })
    return out


def _acq_rows_to_json(rows: pd.DataFrame, *, score_col: str, mode: str) -> list[dict]:
    out = []
    for i, (_, row) in enumerate(rows.head(12).iterrows()):
        if mode == "Album":
            display_name = str(row.get("top_album") or row.get("name") or "Unknown")
        elif mode == "Artist":
            display_name = str(row.get("name") or "Unknown")
        else:
            display_name = str(row.get("top_song") or row.get("name") or "Unknown")

        market = str(row.get("display_country") or row.get("top_country") or "—")
        mom = float(row.get("rank_delta_45d") or 0.0)
        score = int(round(float(row.get(score_col) or 0)))
        rank = row.get("rank")
        rank_text = f"#{int(rank)}" if pd.notna(rank) else "—"
        label_str = str(row.get("label") or "").strip()
        if "independent" in label_str.lower() or "indie" in label_str.lower():
            label_type = "ind"
        elif label_str and label_str != "—":
            label_type = "small"
        else:
            label_type = ""
        sub_parts = [market]
        if mode == "Artist":
            sub_parts.append(f"{_fmt_n(row.get('monthly_listeners'))} listeners")
        elif mode == "Album":
            sub_parts.append(str(row.get("top_album") or "—"))
        else:
            if label_str and label_str != "—":
                sub_parts.append(label_str)
            else:
                sub_parts.append(str(row.get("top_song") or "—"))
        verdict = str(row.get("verdict") or "holding")
        listeners = _fmt_n(row.get("monthly_listeners"))
        points = _fmt_n(row.get("total_points"))
        countries = _fmt_n(row.get("countries_count"))
        top_song = str(row.get("top_song") or "—")
        top_album = str(row.get("top_album") or "—")
        signals = _build_signals(row, rank_text=rank_text, listeners=listeners, countries=countries, top_song=top_song, mom=mom)
        out.append({
            "idx": i,
            "display_name": display_name,
            "sub": " · ".join(sub_parts),
            "market": market,
            "mom": mom,
            "score": score,
            "rank": rank_text,
            "label_type": label_type,
            "label_str": label_str,
            "verdict": verdict,
            "listeners": listeners,
            "points": points,
            "countries": countries,
            "top_song": top_song,
            "top_album": top_album,
            "signals": signals,
            "score_rank": i + 1,
            "total": len(rows),
        })
    return out


def _build_signals(row: pd.Series, *, rank_text: str, listeners: str, countries: str, top_song: str, mom: float) -> list[str]:
    sigs = []
    if mom > 0:
        sigs.append(f"🚀 Strong volume acceleration across the window ({mom:+.1f}%).")
    elif mom < 0:
        sigs.append(f"⚠ Momentum risk across the window ({mom:+.1f}%).")
    else:
        sigs.append("→ Momentum is flat across the window.")
    ml = float(row.get("monthly_listeners") or 0)
    if ml >= 1_000_000:
        sigs.append(f"🎧 Strong audience scale with {listeners} monthly listeners.")
    rank = row.get("rank")
    if pd.notna(rank) and int(rank) <= 25:
        sigs.append(f"📈 Chart presence is still live at {rank_text}.")
    cc = float(row.get("countries_count") or 0)
    if cc >= 5:
        sigs.append(f"🌎 Broad footprint across {countries} markets.")
    if top_song and top_song != "—":
        sigs.append("💡 Spotify-native momentum without iTunes chart entry.")
    if len(sigs) < 3:
        sigs.append("✓ Independent — clean candidate, limited major-label competition.")
    return sigs[:4]


def _build_roster_cards_html(rows: pd.DataFrame) -> str:
    cards = []
    for _, row in rows.iterrows():
        name = escape(str(row.get("name") or "Unknown"))
        verdict = str(row.get("verdict") or "holding")
        verdict_label = {"rising": "Rising", "slipping": "Slipping", "holding": "Holding"}.get(verdict, "Holding")
        verdict_class = {"rising": "good", "slipping": "bad", "holding": "neutral"}.get(verdict, "neutral")
        delta = float(row.get("rank_delta_45d") or 0.0)
        rank = row.get("rank")
        rank_text = f"#{int(rank)}" if pd.notna(rank) else "—"
        listeners = escape(_fmt_n(row.get("monthly_listeners")))
        points = escape(_fmt_n(row.get("total_points")))
        delta_text = f"{delta:+.0f}" if abs(delta) >= 0.5 else "0"
        country = str(row.get("display_country") or row.get("top_country") or "—")
        top_song = escape(str(row.get("top_song") or "—"))
        spark_color = {"rising": "#34d399", "slipping": "#fb7185", "holding": "#60a5fa"}.get(verdict, "#60a5fa")
        spark = _sparkline_svg(row.get("rank_series") or [], color=spark_color, reverse=True)
        listeners_delta = float(row.get("rank_delta_45d") or 0.0)
        ld_text = f"listeners {listeners_delta:+.1f}%" if abs(listeners_delta) >= 0.1 else "listeners flat"
        ld_class = "up" if listeners_delta > 0 else ("dn" if listeners_delta < 0 else "")
        if verdict == "slipping":
            country_note = f"weak in {country}"
            cn_class = "bad"
        elif verdict == "rising":
            country_note = "all markets steady"
            cn_class = "good"
        else:
            country_note = f"steady {country}"
            cn_class = "neutral"
        cards.append(
            f"<article class='rc rc-{verdict_class}'>"
            f"<div class='rc-head'>"
            f"<div><div class='rc-name'>{name}</div>"
            f"<div class='rc-sub'>{rank_text} · {listeners} listeners</div></div>"
            f"<span class='rc-status rc-{verdict_class}-status'>{escape(verdict_label)}</span>"
            f"</div>"
            f"<div class='rc-spark'>{spark}<span class='rc-spark-label'>30d rank trend</span></div>"
            f"<div class='rc-metrics'>"
            f"<div><span>Momentum</span><b class='delta-{verdict_class}'>{escape(delta_text)}</b></div>"
            f"<div><span>Listeners</span><b>{listeners}</b></div>"
            f"<div><span>Points</span><b>{points}</b></div>"
            f"</div>"
            f"<div class='rc-footer'>"
            f"<span class='rc-ld {ld_class}'>{escape(ld_text)}</span>"
            f"<span class='cn-note cn-{cn_class}'>{escape(country_note)}</span>"
            f"</div>"
            f"</article>"
        )
    if not cards:
        return "<div class='empty-msg'>No roster rows available.</div>"
    return "<div class='roster-grid'>" + "".join(cards) + "</div>"


# ── Plotly fatigue figure ───────────────────────────────────────────────────

def _make_fatigue_figure(df: pd.DataFrame, *, dark_mode: bool) -> go.Figure:
    plot_df = df.dropna(subset=["monthly_listeners"]).copy()
    if plot_df.empty:
        return go.Figure()
    # Limit to top 20 records
    plot_df = plot_df.sort_values("monthly_listeners", ascending=False).head(20)
    plot_df["fatigue_state"] = np.select(
        [plot_df["rank_delta_45d"] <= -5, plot_df["rank_delta_45d"] >= 5],
        ["fatigue", "climbing"], default="stable",
    )
    plot_df["bubble"] = np.log10(plot_df["total_points"].fillna(1).clip(lower=1)) * 18 + 10
    fig = px.scatter(
        plot_df, x="rank_delta_45d", y="monthly_listeners",
        size="bubble",
        color="fatigue_state",
        color_discrete_map={"fatigue": "#fb7185", "stable": "#94a3b8", "climbing": "#34d399"},
        hover_name="name",
        custom_data=["rank", "total_points", "countries_count", "display_country", "rank_delta_45d", "fatigue_state"],
        size_max=44,
        title=None,
    )
    fig.update_traces(
        marker=dict(opacity=0.88, line=dict(width=1.1, color="rgba(255,255,255,.28)" if dark_mode else "rgba(0,0,0,.12)")),
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "Rank: #%{customdata[0]}<br>Monthly listeners: %{y:,.0f}<br>"
            "Total points: %{customdata[1]:,.0f}<br>Markets: %{customdata[2]}<br>"
            "Primary market: %{customdata[3]}<br>Momentum: %{x:+.0f}<br>"
            "State: %{customdata[5]}<extra></extra>"
        ),
    )
    x_abs = max(8.0, float(plot_df["rank_delta_45d"].fillna(0).abs().max() or 0)) * 1.15
    y_min = float(plot_df["monthly_listeners"].min()) * 0.85
    y_max = float(plot_df["monthly_listeners"].max()) * 1.08

    fig.add_shape(type="rect", xref="x", yref="paper", x0=-x_abs, x1=0, y0=0, y1=1, fillcolor="rgba(251,113,133,.10)", line=dict(width=0), layer="below")
    fig.add_shape(type="rect", xref="x", yref="paper", x0=0, x1=x_abs, y0=0, y1=1, fillcolor="rgba(52,211,153,.08)", line=dict(width=0), layer="below")
    
    fig.add_annotation(x=-x_abs * 0.72, y=0.96, yref="paper", text="Fatigue — big & declining", showarrow=False, font=dict(size=12, color="#fb7185"))
    fig.add_annotation(x=x_abs * 0.72, y=0.96, yref="paper", text="Rising", showarrow=False, font=dict(size=12, color="#34d399"))
    
    fig.update_layout(
        height=440, margin=dict(l=6, r=8, t=24, b=6),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        xaxis_title="7-day momentum (%)", yaxis_title="Monthly listeners (M)",
        xaxis=dict(range=[-x_abs, x_abs], gridcolor="rgba(148,163,184,.12)" if dark_mode else "rgba(148,163,184,.18)"),
        yaxis=dict(range=[y_min, y_max], tickformat="~s", gridcolor="rgba(148,163,184,.12)" if dark_mode else "rgba(148,163,184,.18)"),
    )
    return fig


# ── Main render entry point ─────────────────────────────────────────────────

def render_redesign_dashboard(
    leaderboard: pd.DataFrame,
    history: pd.DataFrame,
    last_run_label: str = "n/a",
) -> None:
    if leaderboard.empty:
        st.warning("No leaderboard data available yet. Run the scraper first.")
        return

    is_dark = st.session_state.get("dark_mode", True)

    df = _prep_frame(leaderboard, history)
    if df.empty:
        st.warning("No leaderboard data available for the redesign dashboard.")
        return

    # Read filter state from URL query parameters (set by HTML/JS)
    mode = st.query_params.get("mode", "Track")
    if mode not in ["Track", "Album", "Artist"]:
        mode = "Track"
    latam_only = st.query_params.get("latam", "false").lower() == "true"
    independent_only = st.query_params.get("ind", "false").lower() == "true"

    # ── Window label ─────────────────────────────────────────────────────
    if not history.empty and "scraped_at" in history.columns:
        hist_dates = pd.to_datetime(history["scraped_at"], errors="coerce").dropna()
        window_label = (
            f"{hist_dates.min():%b %d} – {hist_dates.max():%b %d}"
            if not hist_dates.empty else last_run_label
        )
    else:
        window_label = last_run_label

    # ── Build and render the big HTML dashboard ──────────────────────────
    html = _build_dashboard_html(
        df,
        dark_mode=is_dark,
        active_mode=mode,
        latam_only=latam_only,
        independent_only=independent_only,
        last_run_label=last_run_label,
        window_label=window_label,
    )
    st_components.html(html, height=1120, scrolling=True)


# ── Big HTML template ────────────────────────────────────────────────────────
_HTML_TEMPLATE = """
<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
__THEME__
body {
  background: var(--a-bg);
  font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--a-t1);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
.dash{padding:14px 4px 18px}

/* HTML Filter Bar */
.filter-bar {
  display: flex;
  gap: 20px;
  align-items: center;
  margin-bottom: 24px;
  padding: 12px 20px;
  background: var(--a-bg2);
  border: 1px solid var(--a-border);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.02);
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 10px;
}
.filter-group label {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--a-t2);
  cursor: pointer;
}
.filter-group select {
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--a-border);
  background: var(--a-bg);
  color: var(--a-t1);
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
  outline: none;
  transition: border-color 0.2s;
}
.filter-group select:focus, .filter-group select:hover {
  border-color: var(--a-blue);
}
.filter-group input[type="checkbox"] {
  cursor: pointer;
  width: 16px;
  height: 16px;
  accent-color: var(--a-blue);
}

/* KPI strip */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.kpi {
  background: var(--a-bg2);
  border: 1px solid var(--a-border);
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.25s, box-shadow 0.25s;
}
.kpi:hover {
  transform: translateY(-2px);
  border-color: var(--a-blue);
  box-shadow: 0 8px 20px rgba(0,0,0,0.12);
}
.kpi-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.kpi-label {
  font-size: .68rem;
  font-weight: 800;
  letter-spacing: .15em;
  text-transform: uppercase;
  color: var(--a-t3);
  margin-bottom: 0;
}
.kpi-icon {
  width: 2.2rem;
  height: 2.2rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border-radius: 999px;
  border: 1px solid var(--a-border);
  background: var(--a-bg3);
  color: var(--a-t1);
  font-size: 1rem;
  line-height: 1;
}
.kpi-icon.up {
  background: rgba(52,211,153,.12);
  border-color: rgba(52,211,153,.22);
  color: var(--a-green);
}
.kpi-icon.dn {
  background: rgba(251,113,133,.12);
  border-color: rgba(251,113,133,.22);
  color: var(--a-red);
}
.kpi-icon.neutral {
  background: rgba(96,165,250,.10);
  border-color: rgba(96,165,250,.18);
  color: var(--a-blue);
}
.kpi-value {
  font-size: 1.2rem;
  font-weight: 900;
  color: var(--a-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Top nav tabs */
.tab-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 24px;
  padding: 0 0 16px;
  overflow-x: auto;
  align-items: center;
}
.tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-width: 154px;
  padding: 10px 18px;
  font-size: .84rem;
  font-weight: 800;
  background: var(--a-bg2);
  border: 1px solid rgba(148,163,184,.18);
  border-radius: 99px;
  cursor: pointer;
  color: var(--a-t2);
  white-space: nowrap;
  text-align: center;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px rgba(15,23,42,.04);
}
.tab:hover {
  background: var(--a-nav-active-bg);
  color: var(--a-nav-active-text);
  border-color: var(--a-nav-active-border);
  transform: translateY(-1px);
}
.tab.active {
  background: #e31d2d;
  color: #fff;
  border-color: #e31d2d;
  font-weight: 800;
  box-shadow: 0 8px 18px rgba(227,29,45,.22);
}
.tab-icon,
.title-icon,
.band-icon,
.section-kicker-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border-radius: 999px;
  border: 1px solid var(--a-border);
  background: var(--a-bg3);
  color: var(--a-t1);
  line-height: 1;
}
.tab-icon {
  width: 1.8rem;
  height: 1.8rem;
  font-size: .88rem;
  background: rgba(255,255,255,.92);
  border-color: rgba(148,163,184,.22);
  color: var(--a-t1);
}
.tab.active .tab-icon {
  background: rgba(255,255,255,.18);
  border-color: rgba(255,255,255,.30);
  color: #fff;
}
.title-icon {
  width: 2rem;
  height: 2rem;
  font-size: .92rem;
  background: rgba(96,165,250,.10);
  border-color: rgba(96,165,250,.20);
  color: var(--a-blue);
}
.band-icon {
  width: 1.45rem;
  height: 1.45rem;
  font-size: .75rem;
  background: rgba(96,165,250,.10);
  border-color: rgba(96,165,250,.18);
  color: var(--a-blue);
}
.section-kicker-icon {
  width: 1.2rem;
  height: 1.2rem;
  font-size: .62rem;
  margin-right: 6px;
  background: rgba(148,163,184,.10);
  border-color: rgba(148,163,184,.20);
  color: var(--a-t2);
}
.panel{display:none}.panel.active{display:block}
/* Section headers */
.screen-kicker {
  font-size: .68rem;
  font-weight: 800;
  letter-spacing: .22em;
  text-transform: uppercase;
  color: var(--a-t3);
  margin-bottom: 6px;
}
.screen-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.35rem;
  font-weight: 850;
  color: var(--a-t1);
  margin: 0 0 4px;
}
.screen-sub {
  font-size: .88rem;
  color: var(--a-t2);
  line-height: 1.5;
  margin: 0 0 16px;
}

/* Today's brief bands */
.brief-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 12px;
}
.brief-band {
  border-radius: 16px;
  border: 1px solid var(--a-border);
  background: var(--a-bg2);
  padding: 18px;
  border-left: 4px solid transparent;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.brief-band:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 24px rgba(0,0,0,0.12);
}
.brief-good   {border-left-color:var(--a-brief-good)}
.brief-bad    {border-left-color:var(--a-brief-bad)}
.brief-neutral{border-left-color:var(--a-brief-neutral)}
.band-title-row{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.band-title{font-size:1.02rem;font-weight:850;color:var(--a-t1)}
.band-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: .7rem;
  font-weight: 800;
  border: 1px solid transparent;
}
.chip-g{background:rgba(52,211,153,.14);color:var(--a-green);border-color:rgba(52,211,153,.24)}
.chip-r{background:var(--a-rd);color:var(--a-red);border-color:rgba(251,113,133,.24)}
.chip-b{background:var(--a-bd);color:var(--a-blue);border-color:rgba(96,165,250,.24)}
.band-sub{font-size:.84rem;color:var(--a-t2);line-height:1.45;margin:0 0 10px}
.artist-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  border-top: 1px solid var(--a-border);
}
.artist-row:first-child{border-top:none}
.ar-left{display:flex;flex-direction:column;gap:2px;min-width:0}
.ar-name{color:var(--a-t1);font-size:.92rem;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ar-genre{color:var(--a-t3);font-size:.76rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ar-mom{font-size:.82rem;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap}
.up{color:var(--a-green)}.dn{color:var(--a-red)}
.ar-market{color:var(--a-t3);font-size:.78rem;white-space:nowrap}
.ar-listeners{color:var(--a-t3);font-size:.78rem;font-variant-numeric:tabular-nums;white-space:nowrap}
.lbl-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 99px;
  font-size: .68rem;
  font-weight: 700;
  border: 1px solid transparent;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.lbl-ind {
  background: rgba(252, 211, 77, 0.1);
  color: var(--a-amber);
  border-color: rgba(252, 211, 77, 0.25);
}
.lbl-small {
  background: rgba(96, 165, 250, 0.1);
  color: var(--a-blue);
  border-color: rgba(96, 165, 250, 0.25);
}
.band-drill {
  display: inline-flex;
  align-items: center;
  margin-top: auto;
  padding-top: 12px;
  font-size: .8rem;
  font-weight: 700;
  color: var(--a-blue);
  cursor: pointer;
  background: none;
  border: none;
  transition: color 0.15s ease, transform 0.15s ease;
}
.band-drill:hover {
  color: var(--a-t1);
  transform: translateX(4px);
}
.empty-band{color:var(--a-t3);font-size:.84rem;padding:10px 0}

/* Acquisition radar */
.acq-header{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.acq-title{display:flex;align-items:center;gap:10px;font-size:1.8rem;font-weight:850;color:var(--a-t1);margin:0}
.acq-sub{font-size:.88rem;color:var(--a-t2);margin-top:3px;max-width:66ch;line-height:1.45}
.acq-meta{font-size:.82rem;color:var(--a-t3);text-align:right;line-height:1.4;min-width:150px}
.acq-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(300px, 0.95fr);
  gap: 16px;
  align-items: start;
}
.acq-panel {
  background: var(--a-bg2);
  border: 1px solid var(--a-border);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.06);
}
.acq-thead, .acq-row {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) 80px 70px 50px;
  gap: 8px;
  align-items: center;
}
.acq-thead {
  padding: 12px 16px;
  color: var(--a-t3);
  font-size: .7rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: .15em;
  border-bottom: 1px solid var(--a-border);
  background: rgba(0,0,0,0.02);
}
.acq-row {
  padding: 12px 16px;
  border-bottom: 1px solid var(--a-border);
  cursor: pointer;
  transition: all 0.2s ease;
  text-decoration: none;
  color: inherit;
}
.acq-row:last-child {
  border-bottom: none;
}
.acq-row:hover {
  background: rgba(96, 165, 250, 0.08);
  transform: translateX(4px);
}
.acq-row.selected {
  background: rgba(96, 165, 250, 0.12);
  border-color: rgba(96, 165, 250, 0.3);
  box-shadow: inset 3px 0 0 var(--a-blue);
}
.acq-pos{color:var(--a-acq-score);font-size:.9rem;font-weight:800;font-variant-numeric:tabular-nums}
.acq-name-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.acq-name{color:var(--a-t1);font-size:.94rem;font-weight:800;line-height:1.2}
.acq-sub-text{color:var(--a-t3);font-size:.76rem;margin-top:2px}
.acq-mkt {
  justify-self: start;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--a-market-bg);
  border: 1px solid var(--a-market-border);
  color: var(--a-market-text);
  font-size: .7rem;
  font-weight: 800;
}
.acq-mom{text-align:right;font-variant-numeric:tabular-nums;font-weight:800;font-size:.88rem;color:var(--a-t3)}
.acq-score{text-align:right;color:var(--a-acq-score);font-size:.94rem;font-weight:900;font-variant-numeric:tabular-nums}

/* Detail pane */
.acq-detail {
  background: var(--a-bg2);
  border: 1px solid var(--a-border);
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.06);
}
.det-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:10px}
.det-title{color:var(--a-t1);font-size:1.25rem;font-weight:900;line-height:1.15}
.det-sub{margin-top:3px;color:var(--a-t3);font-size:.86rem;line-height:1.4}
.det-scorebox{text-align:right;min-width:80px}
.det-score{color:var(--a-acq-score);font-size:2.2rem;line-height:1;font-weight:950}
.det-score-sub{margin-top:4px;color:var(--a-t3);font-size:.75rem}
.chip-row{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 12px}
.chip{display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;font-size:.72rem;font-weight:800;border:1px solid transparent}
.chip-country{background:rgba(34,197,94,.10);color:#86efac;border-color:rgba(34,197,94,.18)}
.chip-rising {background:rgba(52,211,153,.12);color:#86efac;border-color:rgba(52,211,153,.18)}
.chip-holding{background:var(--a-bd);color:#bfdbfe;border-color:rgba(96,165,250,.18)}
.chip-slipping{background:var(--a-rd);color:#fda4af;border-color:rgba(251,113,133,.18)}
.chip-muted{background:var(--a-bg3);color:var(--a-t3);border-color:var(--a-border)}
.metric-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:10px}
.mini-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:10px}
.metric-cell, .mini-cell {
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--a-bg3);
  border: 1px solid var(--a-border);
  transition: border-color 0.15s ease;
}
.metric-cell:hover, .mini-cell:hover {
  border-color: var(--a-border2);
}
.metric-cell span,.mini-cell span{display:block;color:var(--a-t3);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;margin-bottom:4px;font-weight:800}
.metric-cell b,.mini-cell b{display:block;color:var(--a-t1);font-size:.94rem;line-height:1.2;font-weight:800}
.signals{margin-top:10px;padding-top:10px;border-top:1px solid rgba(148,163,184,.12)}
.sig-hdr{color:var(--a-t3);font-size:.7rem;text-transform:uppercase;letter-spacing:.14em;font-weight:850;margin-bottom:8px}
.signals ul{list-style:none;padding:0;margin:0;display:grid;gap:6px}
.signals li{color:var(--a-t2);font-size:.84rem;line-height:1.45}

/* Fatigue map panel */
.fatigue-panel{padding:0}
.fatigue-chart-container {
  padding: 12px;
  border-radius: 16px;
  border: 1px solid var(--a-border);
  background: var(--a-bg2);
  margin-bottom: 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.06);
}
.a360-fatigue-alert {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--a-alert-border);
  background: var(--a-alert-bg);
  color: var(--a-t1);
  font-size: .88rem;
  line-height: 1.5;
  box-shadow: 0 4px 12px rgba(251, 191, 36, 0.05);
}
.fa-icon{font-size:1.05rem;flex-shrink:0;color:var(--a-alert-text)}
.a360-fatigue-alert b{color:var(--a-alert-text)}

/* Roster health */
.roster-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.rc {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid var(--a-border);
  background: var(--a-bg2);
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.rc:hover {
  transform: translateY(-3px);
  border-color: var(--a-border2);
}
.rc-good:hover {
  border-color: rgba(52, 211, 153, 0.4);
  box-shadow: 0 12px 24px rgba(52, 211, 153, 0.1);
}
.rc-bad:hover {
  border-color: rgba(251, 113, 133, 0.4);
  box-shadow: 0 12px 24px rgba(251, 113, 133, 0.1);
}
.rc-neutral:hover {
  border-color: rgba(96, 165, 250, 0.4);
  box-shadow: 0 12px 24px rgba(96, 165, 250, 0.1);
}
.rc-good   {box-shadow:inset 0 1px 0 rgba(52,211,153,.16)}
.rc-bad    {box-shadow:inset 0 1px 0 rgba(251,113,133,.16)}
.rc-neutral{box-shadow:inset 0 1px 0 rgba(96,165,250,.16)}
.rc-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:10px}
.rc-name{color:var(--a-t1);font-size:1.02rem;font-weight:850}
.rc-sub{margin-top:3px;color:var(--a-t3);font-size:.82rem}
.rc-status {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: .68rem;
  font-weight: 850;
  letter-spacing: .1em;
  text-transform: uppercase;
  white-space: nowrap;
}
.rc-good-status   {color:#34d399;background:rgba(52,211,153,.12);border:1px solid rgba(52,211,153,.22)}
.rc-bad-status    {color:#fb7185;background:rgba(251,113,133,.12);border:1px solid rgba(251,113,133,.22)}
.rc-neutral-status{color:#60a5fa;background:rgba(96,165,250,.12);border:1px solid rgba(96,165,250,.22)}
.rc-spark {
  position: relative;
  height: 48px;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--a-border);
  background: rgba(255,255,255,.01);
  padding: 2px 4px;
  margin-bottom: 10px;
}
.rc-spark-label{position:absolute;bottom:3px;right:7px;font-size:.6rem;color:var(--a-t4);pointer-events:none;opacity:.7}
.rc-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 10px;
}
.rc-metrics div {
  padding: 8px;
  border-radius: 10px;
  background: rgba(255,255,255,.02);
  border: 1px solid var(--a-border);
}
.rc-metrics span{display:block;color:var(--a-t3);font-size:.66rem;text-transform:uppercase;letter-spacing:.12em;margin-bottom:3px;font-weight:800}
.rc-metrics b{display:block;color:var(--a-t1);font-size:.9rem;line-height:1.2;font-weight:800}
.delta-good{color:#34d399}.delta-bad{color:#fb7185}.delta-neutral{color:#60a5fa}
.rc-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-top:8px;border-top:1px solid var(--a-border)}
.rc-ld{font-size:.8rem;font-variant-numeric:tabular-nums;font-weight:700;color:var(--a-t3)}
.rc-ld.up{color:#34d399}.rc-ld.dn{color:#fb7185}
.cn-note{font-size:.8rem;font-weight:700;padding:3px 8px;border-radius:999px;border:1px solid transparent}
.cn-good   {color:#34d399;background:rgba(52,211,153,.10);border-color:rgba(52,211,153,.18)}
.cn-bad    {color:#fb7185;background:rgba(251,113,133,.10);border-color:rgba(251,113,133,.18)}
.cn-neutral{color:#60a5fa;background:rgba(96,165,250,.10);border-color:rgba(96,165,250,.16)}

/* What changes */
.spec-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.spec-card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid var(--a-border);
  background: var(--a-bg2);
  box-shadow: 0 4px 12px rgba(0,0,0,0.04);
}
.spec-card h3{margin:0 0 6px;color:var(--a-t1);font-size:1rem;font-weight:850}
.spec-card p{margin:0 0 10px;color:var(--a-t2);font-size:.86rem;line-height:1.5}
.spec-list{list-style:none;padding:0;margin:0;display:grid;gap:6px}
.spec-list li{padding:6px 10px;border-radius:8px;border:1px solid var(--a-border);background:rgba(255,255,255,.01);color:var(--a-t1);font-size:.86rem;line-height:1.45}
.spec-kept{margin-top:12px;padding:12px 14px;border-radius:12px;border:1px solid rgba(96,165,250,.18);background:rgba(96,165,250,.07);color:var(--a-t1);line-height:1.6;font-size:.88rem}
.spec-kept strong{color:var(--a-t1)}
.final-note{margin-top:12px;color:var(--a-t3);font-size:.86rem;line-height:1.55}
.empty-msg{color:var(--a-t3);font-size:.88rem;padding:12px 0}
@media(max-width:900px){
  .brief-grid,.acq-grid,.roster-grid,.spec-grid,.kpi-strip{grid-template-columns:1fr}
  .tab-bar{overflow-x:auto}
}
</style></head><body>
<div class='dash'>

  <div class='kpi-strip' id='kpi-strip'></div>

  <div class='tab-bar'>
    <button class='tab active' onclick="showTab(event,'brief')"><span class='tab-icon' aria-hidden='true'>▣</span>Today's Brief</button>
    <button class='tab' onclick="showTab(event,'radar')"><span class='tab-icon' aria-hidden='true'>♫</span>Acquisition Radar</button>
    <button class='tab' onclick="showTab(event,'fatigue')"><span class='tab-icon' aria-hidden='true'>♪</span>Fatigue Map</button>
    <button class='tab' onclick="showTab(event,'roster')"><span class='tab-icon' aria-hidden='true'>◔</span>Roster Health</button>
  </div>

  <!-- SCREEN 1: Today's Brief -->
  <div class='panel active' id='panel-brief'>
    <h2 class='screen-title'><span class='title-icon' aria-hidden='true'>✦</span>Today's brief</h2>
    <p class='screen-sub'>Three decisions, equal weight. Read the verdict, scan the three, click to open the evidence.</p>
    <div class='brief-grid' id='brief-grid'></div>
  </div>

  <!-- SCREEN 2: Acquisition Radar -->
  <div class='panel' id='panel-radar'>
    <div class='acq-header'>
      <div>
        <h2 class='acq-title'><span class='title-icon' aria-hidden='true'>⌁</span>Acquisition radar</h2>
        <div class='acq-sub' id='acq-sub-text'></div>
      </div>
    </div>
    <div class='acq-grid'>
      <div class='acq-panel'>
        <div class='acq-thead'><div>#</div><div id='entity-col-label'>Artist / Track</div><div>Market</div><div>Mom.</div><div>Score</div></div>
        <div id='acq-rows'></div>
      </div>
      <div class='acq-detail' id='acq-detail'></div>
    </div>
  </div>

  <!-- SCREEN 3: Fatigue Map -->
  <div class='panel' id='panel-fatigue'>
    <h2 class='screen-title'><span class='title-icon' aria-hidden='true'>↘</span>Fatigue map</h2>
    <p class='screen-sub'>Verdict: top-left is fatigue - large audience, falling momentum. Hover any point for its weakest country.</p>
    __FATIGUE_CHART__
    <div id='fatigue-alert-slot'></div>
  </div>

  <!-- SCREEN 4: Roster Health -->
  <div class='panel' id='panel-roster'>
    <h2 class='screen-title'><span class='title-icon' aria-hidden='true'>◉</span>Roster health</h2>
    <p class='screen-sub'>One card per signed artist — holding, rising, or slipping, with rank trend and weakest market. Signed artists · 30-day window.</p>
    <div id='roster-cards'></div>
    <div style='margin-top:24px'>
      <div class='screen-kicker'><span class='section-kicker-icon' aria-hidden='true'>⚙</span>Dependencies</div>
      <h2 class='screen-title' style='margin-bottom:4px'><span class='title-icon' aria-hidden='true'>⚙</span>What changes, and what it depends on</h2>
      <p class='screen-sub'>Which KPIs are cut, which stay decision-grade, and what data must land before the filters stop being visual only.</p>
      <div class='spec-grid'>
        <div class='spec-card'>
          <h3>KPIs cut (knowing, not deciding)</h3>
          <p>Useful reference metrics — none directly support a decision in the new story.</p>
          <ul class='spec-list'>
            <li>Total Points — composite, no decision attached</li>
            <li>Position Strength Score + its bar chart</li>
            <li>Stream Signal (970.8M) as a hero number</li>
            <li>iTunes Points (1.1M) as a headline KPI</li>
            <li>Duplicate listener cards: 5 instances → 1</li>
            <li>Track / Album / Artist Movement as its own module</li>
            <li>Label Power Score — demoted to appendix</li>
          </ul>
        </div>
        <div class='spec-card'>
          <h3>Two data fields required (task zero)</h3>
          <p>The radar, fatigue, and roster views need both before they can be production-ready.</p>
          <ul class='spec-list'>
            <li>Per-artist / per-track country trend — at minimum each entity's weakest market and trend.</li>
            <li>Signed vs independent status plus the label name, so filters stop relying on proxies.</li>
          </ul>
          <div class='spec-kept' style='margin-top:10px'><strong>Why it matters:</strong> without these two fields, the LATAM filter, the independent filter, and the fatigue/roster "where" stay decorative.</div>
        </div>
      </div>
      <div class='spec-kept' style='margin-top:10px'>
        <strong>KPIs kept (each drives a decision):</strong>
        <ul class='spec-list' style='margin-top:8px'>
          <li>30-day momentum — acquire + fatigue</li>
          <li>Acquisition Score — acquire ranking</li>
          <li>Rank + movement chip — hold / fatigue</li>
          <li>Monthly listeners (one instance) — fatigue axis</li>
        </ul>
      </div>
      <p class='final-note'>Once per-country artist trajectories and a confirmed signed/independent flag land in the model, the radar and roster views can split cleanly by market and roster type. Until then, this page is intentionally framed as a prototype so the missing data is obvious, not hidden.</p>
    </div>
  </div>

</div>

<script>
const D = __DATA__;

function showTab(evt, id){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  evt.currentTarget.classList.add('active');
  document.getElementById('panel-'+id).classList.add('active');
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 50);
}

// KPI strip
(function(){
  const k = D.kpis;
  const strip = document.getElementById('kpi-strip');
  const kpis = [
    {label:'Artists scored', value: k.total,        icon:'✦', tone:'neutral'},
    {label:'Rising now',     value: k.risers,      cls:'up', icon:'↗', tone:'up'},
    {label:'Fatigue watch',  value: k.fatigue,     cls:'dn', icon:'↘', tone:'dn'},
    {label:'Avg listeners',  value: k.avg_listeners,           icon:'◔', tone:'neutral'},
    {label:'Last run',       value: k.last_run,               icon:'⏱', tone:'neutral'},
  ];
  strip.innerHTML = kpis.map(k=>`<div class='kpi'><div class='kpi-head'><div class='kpi-label'>${k.label}</div><span class='kpi-icon ${k.tone||'neutral'}' aria-hidden='true'>${k.icon}</span></div><div class='kpi-value ${k.cls||''}'>${k.value}</div></div>`).join('');
})();

// ── Today's brief ──────────────────────────────────────────────
function labelBadge(type, str){
  if(!type) return '';
  if(type==='ind') return `<span class='lbl-badge lbl-ind'>Independent</span>`;
  return `<span class='lbl-badge lbl-small'>${str}</span>`;
}
function briefArtistRow(r){
  const momCls = r.mom>0?'up':r.mom<0?'dn':'';
  const momText = Math.abs(r.mom)>=0.1?(r.mom>0?'+':'')+r.mom.toFixed(1)+'% streams':'flat';
  const listenersHtml = r.band==='fatigue' ? `<span class='ar-listeners'>${r.listeners} streams</span>` : '';
  return `<div class='artist-row'>
    <div class='ar-left'><span class='ar-name'>${r.name}</span>${r.genre?`<span class='ar-genre'>${r.genre}</span>`:''}</div>
    <span class='ar-mom ${momCls}'>${momText}</span>
    <span class='ar-market'>@ ${r.market}</span>
    ${listenersHtml}
    ${labelBadge(r.label_type, r.label_str)}
  </div>`;
}
function briefBand(rows, title, icon, chip, chipCls, sub, drillLabel, drillScreen){
  const cls = chipCls==='chip-g'?'brief-good':chipCls==='chip-r'?'brief-bad':'brief-neutral';
  const items = rows.length
    ? rows.map(briefArtistRow).join('')
    : "<div class='empty-band'>No signals available.</div>";
  return `<article class='brief-band ${cls}'>
    <div class='band-title-row'><span class='band-icon' aria-hidden='true'>${icon}</span><span class='band-title'>${title}</span><span class='band-chip ${chipCls}'>${chip}</span></div>
    <p class='band-sub'>${sub}</p>
    <div>${items}</div>
    <button class='band-drill' onclick="showTabById('${drillScreen}')">${drillLabel} →</button>
  </article>`;
}
document.getElementById('brief-grid').innerHTML = [
  briefBand(D.brief_acq, 'Acquire now', '↗', D.brief_acq.length+' clean risers', 'chip-g',
    'Rising, acquirable, in a market we want — verdict: move on these before a major does.',
    'Open acquisition radar', 'radar'),
  briefBand(D.brief_fatigue, 'Watch — fatigue', '↘', D.brief_fatigue.length+' cooling', 'chip-r',
    'Large audience, declining momentum — verdict: demand softening, see where before it spreads.',
    'Open fatigue map', 'fatigue'),
  briefBand(D.brief_hold, 'Our roster status', '◉', D.brief_hold.length+' signed artists', 'chip-b',
    'Are our top artists holding up — verdict per artist: holding, rising, or slipping.',
    'Open roster health', 'roster'),
].join('');

function showTabById(id){
  const tabs = document.querySelectorAll('.tab');
  const map = {brief:0,radar:1,fatigue:2,roster:3};
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  tabs[map[id]].classList.add('active');
  document.getElementById('panel-'+id).classList.add('active');
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 50);
}

// ── Acquisition radar ──────────────────────────────────────────
(function(){
  document.getElementById('acq-sub-text').textContent = 'Verdict: rising + acquirable + in a market we want. '+D.score_formula;
  const modeLabel = {Track:'Artist / Track', Album:'Artist / Album', Artist:'Artist'}[D.active_mode] || 'Artist / Track';
  document.getElementById('entity-col-label').textContent = modeLabel;

  let selectedIdx = 0;
  function renderRows(){
    document.getElementById('acq-rows').innerHTML = D.acq_list.map((r,i)=>{
      const momCls = r.mom>0?' up':r.mom<0?' dn':'';
      const momText = Math.abs(r.mom)>=0.1?(r.mom>0?'+':'')+r.mom.toFixed(1)+'%':'0.0%';
      const lbl = r.label_type==='ind'?`<span class='lbl-badge lbl-ind'>Independent</span>`:
                  r.label_type==='small'?`<span class='lbl-badge lbl-small'>${r.label_str}</span>`:'';
      return `<div class='acq-row${i===selectedIdx?' selected':''}' onclick='selectAcq(${i})'>
        <div class='acq-pos'>${i+1}</div>
        <div><div class='acq-name-row'><span class='acq-name'>${r.display_name}</span>${lbl}</div><div class='acq-sub-text'>${r.sub}</div></div>
        <div class='acq-mkt'>${r.market}</div>
        <div class='acq-mom${momCls}'>${momText}</div>
        <div class='acq-score'>${r.score}</div>
      </div>`;
    }).join('');
  }
  function renderDetail(){
    const r = D.acq_list[selectedIdx];
    if(!r){document.getElementById('acq-detail').innerHTML='';return;}
    const verdictChip = `<span class='chip chip-${r.verdict}'>${r.verdict.charAt(0).toUpperCase()+r.verdict.slice(1)}</span>`;
    const countryChip = `<span class='chip chip-country'>${r.market}</span>`;
    const muted = D.active_mode==='Album'?r.top_album:D.active_mode==='Artist'?r.listeners+' listeners':r.top_song;
    document.getElementById('acq-detail').innerHTML = `
      <div class='det-head'>
        <div><div class='det-title'>${r.display_name}</div><div class='det-sub'>${r.sub}</div></div>
        <div class='det-scorebox'><div class='det-score'>${r.score}</div><div class='det-score-sub'>acq. score · #${r.score_rank} of ${r.total}</div></div>
      </div>
      <div class='chip-row'>${countryChip}${verdictChip}<span class='chip chip-muted'>${muted}</span></div>
      <div class='metric-grid'>
        <div class='metric-cell'><span>Latest streams</span><b>${r.listeners}</b></div>
        <div class='metric-cell'><span>Best rank</span><b>${r.rank}</b></div>
        <div class='metric-cell'><span>Countries</span><b>${r.countries}</b></div>
        <div class='metric-cell'><span>Points</span><b>${r.points}</b></div>
      </div>
      <div class='signals'>
        <div class='sig-hdr'>why now — acquisition signals</div>
        <ul>${r.signals.map(s=>`<li>${s}</li>`).join('')}</ul>
      </div>
      <div class='mini-grid'>
        <div class='mini-cell'><span>Top song</span><b>${r.top_song}</b></div>
        <div class='mini-cell'><span>Top album</span><b>${r.top_album}</b></div>
      </div>`;
  }
  window.selectAcq = function(i){
    selectedIdx = i;
    renderRows();
    renderDetail();
  };
  renderRows();
  renderDetail();
})();

// Fatigue alert
document.getElementById('fatigue-alert-slot').innerHTML = D.fatigue_alert_html || '';

// Roster cards
document.getElementById('roster-cards').innerHTML = D.roster_cards_html || "<div class='empty-msg'>No roster rows available.</div>";
</script>
</body></html>
"""
