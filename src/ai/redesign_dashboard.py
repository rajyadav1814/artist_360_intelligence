from __future__ import annotations

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

_ROSTER_ACCENTS = [
    "#f97316",
    "#38bdf8",
    "#10b981",
    "#8b5cf6",
    "#f59e0b",
    "#fb7185",
    "#60a5fa",
    "#22c55e",
    "#a78bfa",
    "#fbbf24",
]


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
    except Exception:  # noqa: BLE001
        return default


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    raw = hex_color.lstrip("#")
    if len(raw) != 6:
        return f"rgba(96,165,250,{alpha})"
    r = int(raw[0:2], 16)
    g = int(raw[2:4], 16)
    b = int(raw[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _percentile(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=float)
    ranks = series.rank(pct=True, method="average")
    return ranks.fillna(0.0)


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


def _sparkline_svg(values: list[float | int | None], *, width: int = 180, height: int = 54, color: str = "#60a5fa", reverse: bool = False) -> str:  # type: ignore[no-redef]
    clean = [float(v) for v in values if v is not None and pd.notna(v)]
    if not clean:
        clean = [0.0, 0.0]
    if len(clean) == 1:
        clean = clean * 2

    min_v = min(clean)
    max_v = max(clean)
    span = max(max_v - min_v, 1.0)
    pad_x = 4
    pad_y = 5
    usable_w = max(width - pad_x * 2, 1)
    usable_h = max(height - pad_y * 2, 1)
    fill_points: list[str] = []
    line_points: list[str] = []

    for idx, raw in enumerate(clean):
        x = pad_x + (idx / max(len(clean) - 1, 1)) * usable_w
        norm = (raw - min_v) / span
        if reverse:
            norm = 1.0 - norm
        y = pad_y + (1.0 - norm) * usable_h
        point = f"{x:.1f},{y:.1f}"
        line_points.append(point)
        fill_points.append(point)

    safe_id = f"spark-{abs(hash(tuple(round(v, 2) for v in clean)))}"
    return (
        f"<svg viewBox='0 0 {width} {height}' class='a360-spark' role='img' aria-label='trend sparkline'>"
        f"<defs><linearGradient id='{safe_id}' x1='0' x2='0' y1='0' y2='1'>"
        f"<stop offset='0%' stop-color='{color}' stop-opacity='.28'/>"
        f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/></linearGradient></defs>"
        f"<polygon points='{' '.join(fill_points)} {width - pad_x},{height - pad_y} {pad_x},{height - pad_y}' fill='url(#{safe_id})' opacity='0.8'></polygon>"
        f"<polyline points='{' '.join(line_points)}' fill='none' stroke='{color}' stroke-width='2.4' stroke-linejoin='round' stroke-linecap='round'></polyline>"
        "</svg>"
    )


def _render_plotly_html(fig: go.Figure, *, height: int | None = None, dark_mode: bool | None = None) -> None:
    if dark_mode is None:
        dark_mode = st.session_state.get("dark_mode", True)

    chart_height = height or (int(fig.layout.height) if fig.layout.height else 520)
    fig.update_layout(
        template="plotly_dark" if dark_mode else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    chart_html = pio.to_html(
        fig,
        config=PLOTLY_CONFIG,
        full_html=False,
        include_plotlyjs="cdn",
        default_width="100%",
        default_height=f"{chart_height}px",
    )
    bg_color = "rgba(10, 14, 24, 0.96)" if dark_mode else "#FFFFFF"
    border_color = "rgba(148, 163, 184, 0.18)" if dark_mode else "rgba(226, 232, 240, 1)"
    shadow_color = "rgba(0, 0, 0, 0.24)" if dark_mode else "rgba(15, 23, 42, 0.06)"

    st_components.html(
        f"""
        <div class="graph-card">
            <div class="plotly-html-chart">{chart_html}</div>
        </div>
        <style>
            body {{ margin: 0; background: transparent; }}
            .graph-card {{
                width: 100%;
                box-sizing: border-box;
                padding: 6px;
                border-radius: 18px;
                border: 1px solid {border_color};
                background: {bg_color};
                box-shadow: 0 4px 12px {shadow_color};
            }}
            .plotly-html-chart {{ width: 100%; }}
            .plotly-html-chart .js-plotly-plot,
            .plotly-html-chart .plot-container,
            .plotly-html-chart .svg-container {{ width: 100% !important; }}
        </style>
        <script>
            setTimeout(() => {{ window.dispatchEvent(new Event('resize')); }}, 300);
            setTimeout(() => {{ window.dispatchEvent(new Event('resize')); }}, 1000);
        </script>
        """,
        height=chart_height + 32,
        scrolling=False,
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
            .groupby("day", as_index=False)["rank"]
            .min()
            .sort_values("day")
        )
        if by_day.empty:
            continue

        ranks = by_day["rank"].astype(float).tolist()
        days = by_day["day"].tolist()
        first_rank = float(ranks[0])
        last_rank = float(ranks[-1])
        delta = first_rank - last_rank
        slope = 0.0
        if len(ranks) >= 2:
            x = np.arange(len(ranks), dtype=float)
            y = np.asarray(ranks, dtype=float)
            try:
                slope = float(np.polyfit(x, y, 1)[0])
            except Exception:  # noqa: BLE001
                slope = 0.0

        profiles[artist] = {
            "rank_delta": delta,
            "rank_slope": slope,
            "rank_series": ranks,
            "rank_dates": days,
            "rank_span": len(ranks),
        }

    return profiles


def _prep_frame(leaderboard: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()

    df = leaderboard.copy()
    numeric_cols = [
        "rank",
        "monthly_listeners",
        "peak_listeners",
        "total_points",
        "itunes_points",
        "spotify_points",
        "apple_music_points",
        "shazam_points",
        "youtube_points",
        "other_points",
        "songs_count",
        "albums_count",
        "countries_count",
        "times_on_chart",
        "weeks_on_chart",
        "times_at_top",
        "max_countries",
        "best_rank",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "top_country" not in df.columns:
        df["top_country"] = "—"
    if "display_country" not in df.columns:
        df["display_country"] = df["top_country"].fillna("—")

    profiles = _build_history_profiles(history)
    df["rank_delta_45d"] = df["name"].map(lambda name: profiles.get(name, {}).get("rank_delta", 0.0))
    df["rank_slope_45d"] = df["name"].map(lambda name: profiles.get(name, {}).get("rank_slope", 0.0))
    df["rank_span_45d"] = df["name"].map(lambda name: profiles.get(name, {}).get("rank_span", 0))
    df["rank_change_num"] = df["rank_change"].map(_parse_rank_change) if "rank_change" in df.columns else 0.0

    if "rank" in df.columns and df["rank"].notna().any():
        rank_base = df["rank"].fillna(df["rank"].max() + 1)
        df["rank_score"] = 1.0 - _percentile(rank_base)
    else:
        df["rank_score"] = 0.0

    if "monthly_listeners" in df.columns and df["monthly_listeners"].notna().any():
        df["listener_score"] = _percentile(df["monthly_listeners"])
    else:
        df["listener_score"] = 0.0

    if "total_points" in df.columns and df["total_points"].notna().any():
        df["point_score"] = _percentile(df["total_points"])
    else:
        df["point_score"] = 0.0

    if "countries_count" in df.columns and df["countries_count"].notna().any():
        df["coverage_score"] = _percentile(df["countries_count"])
    else:
        df["coverage_score"] = 0.0

    momentum_raw = df["rank_delta_45d"].fillna(0.0) + df["rank_change_num"].fillna(0.0)
    if momentum_raw.abs().max() > 0:
        df["momentum_score"] = (momentum_raw / momentum_raw.abs().max()).clip(-1, 1)
    else:
        df["momentum_score"] = 0.0

    df["acq_score"] = (
        100
        * (
            0.35 * df["listener_score"]
            + 0.25 * df["point_score"]
            + 0.20 * df["coverage_score"]
            + 0.20 * df["rank_score"]
        )
    ).round(0)

    df["hold_score"] = (
        100
        * (
            0.40 * df["listener_score"]
            + 0.35 * df["point_score"]
            + 0.15 * df["coverage_score"]
            + 0.10 * (1 - df["momentum_score"].abs().clip(0, 1))
        )
    ).round(0)

    df["fatigue_score"] = (
        100
        * (
            0.45 * df["listener_score"]
            + 0.20 * df["point_score"]
            + 0.15 * df["coverage_score"]
            + 0.20 * (-df["momentum_score"]).clip(lower=0, upper=1)
        )
    ).round(0)

    def classify(row: pd.Series) -> str:
        momentum = float(row.get("momentum_score") or 0.0)
        rank_delta = float(row.get("rank_delta_45d") or 0.0)
        if rank_delta <= -5 or momentum <= -0.2:
            return "slipping"
        if rank_delta >= 5 or momentum >= 0.2:
            return "rising"
        return "holding"

    df["verdict"] = df.apply(classify, axis=1)
    df["fatigue_alert"] = (
        df["listener_score"] * 0.65
        + df["coverage_score"] * 0.20
        + (-df["momentum_score"]).clip(lower=0, upper=1) * 0.35
    ) * 100
    df["hold_alert"] = (
        df["hold_score"] + (1 - df["momentum_score"].abs().clip(0, 1)) * 20
    ).round(0)

    if "songs_count" in df.columns:
        df["songs_count"] = df["songs_count"].fillna(0)
    if "albums_count" in df.columns:
        df["albums_count"] = df["albums_count"].fillna(0)
    if "countries_count" in df.columns:
        df["countries_count"] = df["countries_count"].fillna(0)

    return df


def _lens_filter(df: pd.DataFrame, lens: str) -> pd.DataFrame:
    if df.empty:
        return df

    if lens == "Momentum risers":
        return df[df["verdict"].eq("rising")].copy()
    if lens == "Fatigue watch":
        return df[df["verdict"].eq("slipping")].copy()
    if lens == "Holding roster":
        return df[df["verdict"].eq("holding")].copy()
    if lens == "LATAM signal":
        if "latam_signal" in df.columns:
            return df[df["latam_signal"].fillna(False)].copy()
        return df[df["display_country"].ne("—")].copy()
    return df.copy()


def _band_card(title: str, subtitle: str, chip: str, color: str, rows: pd.DataFrame, score_col: str, verdict_col: str, cta: str) -> str:
    if rows.empty:
        items = "<li class='a360-empty-row'>No rows available for this lens.</li>"
    else:
        items = ""
        for _, row in rows.head(3).iterrows():
            score = _fmt_n(row.get(score_col))
            rank = row.get("rank")
            rank_html = f"#{int(rank)}" if pd.notna(rank) else "—"
            country = str(row.get("display_country") or row.get("top_country") or "—")
            momentum = float(row.get("rank_delta_45d") or 0.0)
            delta = f"{momentum:+.0f}" if abs(momentum) >= 0.5 else "0"
            items += (
                "<li>"
                f"<div class='a360-band-row-top'><b>{escape(str(row.get('name') or 'Unknown'))}</b><span>{escape(rank_html)}</span></div>"
                f"<div class='a360-band-row-sub'>{escape(country)} · {escape(delta)} rank delta · {escape(score)} score</div>"
                "</li>"
            )

    return textwrap.dedent(
        f"""
        <article class="a360-band a360-{color}">
            <div class="a360-band-top">
                <div>
                    <div class="a360-band-chip">{escape(chip)}</div>
                    <h3>{escape(title)}</h3>
                    <p>{escape(subtitle)}</p>
                </div>
                <div class="a360-chip-ghost">{escape(cta)}</div>
            </div>
            <ul class="a360-band-list">{items}</ul>
        </article>
        """
    ).strip()


def _acq_score_label(mode: str) -> tuple[str, str, str]:
    if mode == "Album":
        return "hold_score", "Album acquisition", "Roster health through catalog depth and stability."
    if mode == "Artist":
        return "fatigue_alert", "Artist health", "Are the biggest artists holding up or starting to tire?"
    return "acq_score", "Acquisition radar", "Verdict: rising + acquirable + in a market we want."


def _acq_display_name(row: pd.Series, mode: str) -> str:
    if mode == "Album":
        return str(row.get("top_album") or row.get("name") or "Unknown")
    if mode == "Artist":
        return str(row.get("name") or "Unknown")
    return str(row.get("top_song") or row.get("name") or "Unknown")


def _acq_display_subtitle(row: pd.Series, mode: str) -> str:
    market = str(row.get("display_country") or row.get("top_country") or "—")
    if mode == "Album":
        album = str(row.get("top_album") or "—")
        return f"{market} · {album}"
    if mode == "Artist":
        listener_text = _fmt_n(row.get("monthly_listeners"))
        return f"{market} · {listener_text} listeners"
    track = str(row.get("top_song") or "—")
    label = str(row.get("label") or "").strip()
    if label:
        return f"{market} · {label}"
    return f"{market} · {track}"


def _acq_badges(row: pd.Series, mode: str, latam_only: bool, independent_only: bool) -> list[tuple[str, str]]:
    badges: list[tuple[str, str]] = []
    market = str(row.get("display_country") or row.get("top_country") or "—")
    if market and market != "—":
        badges.append((market, "badge-country"))
    if latam_only:
        badges.append(("LATAM only", "badge-latam"))
    if independent_only:
        badges.append(("Independent only", "badge-ind"))
    verdict = str(row.get("verdict") or "holding").title()
    badges.append((verdict, f"badge-{verdict.lower()}"))
    if mode == "Album":
        badges.append((str(row.get("top_album") or "Album"), "badge-muted"))
    elif mode == "Artist":
        badges.append((str(row.get("songs_count") or 0) and f"{int(row.get('songs_count') or 0)} songs" or "Catalog", "badge-muted"))
    else:
        badges.append((str(row.get("top_song") or "Track"), "badge-muted"))
    return badges[:4]


def _filter_acq_rows(df: pd.DataFrame, *, latam_only: bool, independent_only: bool) -> pd.DataFrame:
    filtered = df.copy()
    if latam_only:
        if "latam_signal" in filtered.columns:
            filtered = filtered[filtered["latam_signal"].fillna(False)]
        else:
            filtered = filtered[filtered["display_country"].isin(LATIN_AMERICAN_COUNTRIES)]

    if independent_only:
        if "label" in filtered.columns:
            label_series = filtered["label"].fillna("").astype(str).str.lower()
            filtered = filtered[
                label_series.str.contains("independent")
                | label_series.str.contains("indie")
                | label_series.eq("ind")
            ]
        else:
            # If we don't have a reliable roster flag yet, keep the list usable rather than empty.
            filtered = filtered.copy()

    return filtered


def _render_acq_row(
    row: pd.Series,
    *,
    idx: int,
    mode: str,
    score_col: str,
    selected: bool,
) -> str:
    name = escape(_acq_display_name(row, mode))
    subtitle = escape(_acq_display_subtitle(row, mode))
    market = escape(str(row.get("display_country") or row.get("top_country") or "—"))
    momentum_val = float(row.get("rank_delta_45d") or 0.0)
    momentum_text = f"{momentum_val:+.1f}%" if abs(momentum_val) >= 0.1 else "0.0%"
    score = int(round(float(row.get(score_col) or 0)))
    rank = row.get("rank")
    rank_text = f"#{int(rank)}" if pd.notna(rank) else "—"
    row_class = " active" if selected else ""
    momentum_class = " up" if momentum_val > 0 else (" down" if momentum_val < 0 else "")
    return textwrap.dedent(
        f"""
        <div class="a360-acq-row{row_class}">
            <div class="a360-acq-pos">{idx}</div>
            <div class="a360-acq-main">
                <div class="a360-acq-name">{name}</div>
                <div class="a360-acq-sub">{subtitle}</div>
            </div>
            <div class="a360-acq-market">{market}</div>
            <div class="a360-acq-mom{momentum_class}">{escape(momentum_text)}</div>
            <div class="a360-acq-score">{score}</div>
        </div>
        """
    ).strip()


def _render_acq_detail(row: pd.Series, *, mode: str, score_col: str, score_rank: int, total_rows: int) -> str:
    name = escape(str(row.get("name") or "Unknown"))
    subtitle = escape(_acq_display_subtitle(row, mode))
    score = int(round(float(row.get(score_col) or 0)))
    rank = row.get("rank")
    rank_text = f"#{int(rank)}" if pd.notna(rank) else "—"
    momentum_val = float(row.get("rank_delta_45d") or 0.0)
    listener_text = _fmt_n(row.get("monthly_listeners"))
    points_text = _fmt_n(row.get("total_points"))
    songs_text = _fmt_n(row.get("songs_count"))
    albums_text = _fmt_n(row.get("albums_count"))
    countries_text = _fmt_n(row.get("countries_count"))
    top_song = escape(str(row.get("top_song") or "—"))
    top_album = escape(str(row.get("top_album") or "—"))
    market = escape(str(row.get("display_country") or row.get("top_country") or "—"))
    verdict = str(row.get("verdict") or "holding").lower()
    verdict_label = {"rising": "rising", "slipping": "slipping", "holding": "holding"}.get(verdict, "holding")

    badge_nodes = []
    for label, klass in _acq_badges(row, mode, bool(row.get("latam_signal")), False):
        badge_nodes.append(f"<span class='a360-chip a360-chip-{klass}'>{escape(label)}</span>")

    signal_nodes = []
    momentum_caption = (
        f"Strong volume acceleration across the window ({momentum_val:+.1f}%)." if momentum_val > 0
        else f"Momentum risk across the window ({momentum_val:+.1f}%)." if momentum_val < 0
        else "Momentum is flat across the window."
    )
    signal_nodes.append(f"<li>{escape(momentum_caption)}</li>")
    if row.get("monthly_listeners") and float(row.get("monthly_listeners") or 0) >= 1_000_000:
        signal_nodes.append(f"<li>Strong audience scale with {escape(listener_text)} monthly listeners.</li>")
    if pd.notna(rank) and int(rank) <= 25:
        signal_nodes.append(f"<li>Chart presence is still live at {rank_text}.</li>")
    if float(row.get("countries_count") or 0) >= 5:
        signal_nodes.append(f"<li>Broad footprint across {escape(countries_text)} markets.</li>")
    if top_song != "—":
        signal_nodes.append(f"<li>Lead track signal: {top_song}.</li>")
    if len(signal_nodes) < 4:
        signal_nodes.append("<li>Clean candidate for deeper acquisition review.</li>")

    signal_html = "".join(signal_nodes[:4])

    return textwrap.dedent(
        f"""
        <article class="a360-acq-detail">
            <div class="a360-acq-detail-head">
                <div>
                    <div class="a360-acq-detail-title">{name}</div>
                    <div class="a360-acq-detail-sub">{subtitle}</div>
                </div>
                <div class="a360-acq-detail-scorebox">
                    <div class="a360-acq-detail-score">{score}</div>
                    <div class="a360-acq-detail-score-sub">acq. score · #{score_rank} of {total_rows}</div>
                </div>
            </div>
            <div class="a360-acq-chip-row">
                {''.join(badge_nodes)}
            </div>
            <div class="a360-acq-metric-grid">
                <div class="a360-acq-metric"><span>Listeners</span><b>{escape(listener_text)}</b></div>
                <div class="a360-acq-metric"><span>Best rank</span><b>{escape(rank_text)}</b></div>
                <div class="a360-acq-metric"><span>Countries</span><b>{escape(countries_text)}</b></div>
                <div class="a360-acq-metric"><span>Points</span><b>{escape(points_text)}</b></div>
            </div>
            <div class="a360-acq-signals">
                <div class="a360-acq-signals-hdr">why now</div>
                <ul>{signal_html}</ul>
            </div>
            <div class="a360-acq-mini-grid">
                <div class="a360-acq-mini">
                    <span>Top song</span>
                    <b>{top_song}</b>
                </div>
                <div class="a360-acq-mini">
                    <span>Top album</span>
                    <b>{top_album}</b>
                </div>
            </div>
        </article>
        """
    ).strip()


def _make_fatigue_figure(df: pd.DataFrame, *, dark_mode: bool) -> go.Figure:
    plot_df = df.copy()
    plot_df = plot_df.dropna(subset=["monthly_listeners"])
    if plot_df.empty:
        return go.Figure()

    plot_df["fatigue_state"] = np.select(
        [
            plot_df["rank_delta_45d"] <= -5,
            plot_df["rank_delta_45d"] >= 5,
        ],
        ["fatigue", "climbing"],
        default="stable",
    )
    plot_df["bubble"] = np.log10(plot_df["total_points"].fillna(1).clip(lower=1)) * 18 + 10

    fig = px.scatter(
        plot_df,
        x="rank_delta_45d",
        y="monthly_listeners",
        size="bubble",
        color="fatigue_state",
        color_discrete_map={"fatigue": "#fb7185", "stable": "#94a3b8", "climbing": "#34d399"},
        hover_name="name",
        custom_data=["rank", "total_points", "countries_count", "display_country", "rank_delta_45d", "fatigue_state"],
        hover_data={
            "rank": True,
            "total_points": ":,.0f",
            "countries_count": True,
            "display_country": True,
            "rank_delta_45d": ":.0f",
            "bubble": False,
            "fatigue_state": True,
        },
        size_max=44,
        title="Fatigue Map",
    )
    fig.update_traces(
        marker=dict(opacity=0.88, line=dict(width=1.1, color="rgba(255,255,255,.28)" if dark_mode else "rgba(0,0,0,.12)")),
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "Rank: #%{customdata[0]}<br>"
            "Monthly listeners: %{y:,.0f}<br>"
            "Total points: %{customdata[1]:,.0f}<br>"
            "Markets: %{customdata[2]}<br>"
            "Primary market: %{customdata[3]}<br>"
            "Momentum: %{x:+.0f}<br>"
            "State: %{customdata[5]}<extra></extra>"
        ),
    )

    x_abs = max(8.0, float(abs(plot_df["rank_delta_45d"].fillna(0).abs().max()) or 0))
    y_med = float(plot_df["monthly_listeners"].median())
    y_max = float(plot_df["monthly_listeners"].max()) * 1.08

    fig.add_shape(
        type="rect",
        x0=-x_abs,
        x1=0,
        y0=y_med,
        y1=y_max,
        fillcolor="rgba(251,113,133,.10)",
        line=dict(width=0),
        layer="below",
    )
    fig.add_shape(
        type="rect",
        x0=0,
        x1=x_abs,
        y0=y_med,
        y1=y_max,
        fillcolor="rgba(52,211,153,.08)",
        line=dict(width=0),
        layer="below",
    )
    fig.add_annotation(x=-x_abs * 0.72, y=y_max * 0.96, text="Fatigue zone", showarrow=False, font=dict(size=12, color="#fb7185"))
    fig.add_annotation(x=x_abs * 0.72, y=y_max * 0.96, text="Climbing", showarrow=False, font=dict(size=12, color="#34d399"))
    fig.add_annotation(x=0, y=y_med * 1.02, text="Pivot line", showarrow=False, font=dict(size=11, color="#94a3b8"))
    fig.update_layout(
        height=440,
        margin=dict(l=6, r=8, t=42, b=6),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="Momentum (positive = improving)",
        yaxis_title="Audience size",
        xaxis=dict(gridcolor="rgba(148,163,184,.12)" if dark_mode else "rgba(148,163,184,.18)"),
        yaxis=dict(tickformat="~s", gridcolor="rgba(148,163,184,.12)" if dark_mode else "rgba(148,163,184,.18)"),
    )
    return fig


def _brief_sentence(prefix: str, rows: pd.DataFrame, score_col: str) -> str:
    if rows.empty:
        return f"No {prefix.lower()} signals available in the current slice."

    top = rows.sort_values(score_col, ascending=False).head(3)
    names = [str(name) for name in top["name"].tolist() if str(name).strip()]
    if not names:
        return f"No {prefix.lower()} signals available in the current slice."
    if len(names) == 1:
        return f"{names[0]} is the clearest {prefix.lower()} candidate right now."
    if len(names) == 2:
        return f"{names[0]} and {names[1]} are the clearest {prefix.lower()} candidates right now."
    return f"{names[0]}, {names[1]}, and {names[2]} lead the {prefix.lower()} list."


def _roster_card(row: pd.Series, idx: int) -> str:
    name = escape(str(row.get("name") or "Unknown"))
    verdict = str(row.get("verdict") or "holding")
    verdict_class = {"rising": "good", "slipping": "bad", "holding": "neutral"}.get(verdict, "neutral")
    delta = float(row.get("rank_delta_45d") or 0.0)
    rank = row.get("rank")
    points = _fmt_n(row.get("total_points"))
    listeners = _fmt_n(row.get("monthly_listeners"))
    songs = _fmt_n(row.get("songs_count"))
    albums = _fmt_n(row.get("albums_count"))
    country = str(row.get("display_country") or row.get("top_country") or "—")
    markets_count = int(max(_safe_float(row.get("countries_count")), _safe_float(row.get("max_countries"))))
    if markets_count <= 0 and country != "—":
        markets_count = 1
    rank_text = f"#{int(rank)}" if pd.notna(rank) else "—"
    if verdict == "rising":
        status_text = f"▲ {abs(int(round(delta))) or 1}"
    elif verdict == "slipping":
        status_text = f"▼ {abs(int(round(delta))) or 1}"
    else:
        status_text = "Stable"
    accent = _ROSTER_ACCENTS[(max(idx, 1) - 1) % len(_ROSTER_ACCENTS)]
    accent_soft = _hex_to_rgba(accent, 0.15)
    accent_border = _hex_to_rgba(accent, 0.26)
    accent_strong = _hex_to_rgba(accent, 0.9)
    return textwrap.dedent(
        f"""
        <article class="a360-roster-card a360-card-{verdict_class}" style="--a360-card-accent:{accent}; --a360-card-accent-soft:{accent_soft}; --a360-card-accent-border:{accent_border}; --a360-card-accent-strong:{accent_strong};">
            <div class="a360-roster-head">
                <div class="a360-roster-head-left">
                    <div class="a360-roster-rank">{rank_text}</div>
                    <div class="a360-roster-name">{name}</div>
                </div>
                <span class="a360-status a360-status-{verdict_class}">{escape(status_text)}</span>
            </div>
            <div class="a360-roster-metrics">
                <div class="a360-roster-metric"><span>Points</span><b>{escape(points)}</b></div>
                <div class="a360-roster-metric"><span>Listeners</span><b>{escape(listeners)}</b></div>
                <div class="a360-roster-metric"><span>Songs</span><b>{escape(songs)}</b></div>
                <div class="a360-roster-metric"><span>Albums</span><b>{escape(albums)}</b></div>
            </div>
            <div class="a360-roster-footer">
                <span>Top market: <strong>{escape(country)}</strong></span>
                <span>{markets_count} market{'s' if markets_count != 1 else ''}</span>
            </div>
        </article>
        """
    ).strip()


def render_redesign_dashboard(leaderboard: pd.DataFrame, history: pd.DataFrame, last_run_label: str = "n/a") -> None:
    if leaderboard.empty:
        st.warning("No leaderboard data available yet. Run the scraper first.")
        return

    is_dark = st.session_state.get("dark_mode", True)
    if is_dark:
        theme_vars = """
        :root {
            --a360-bg: linear-gradient(180deg, rgba(14, 18, 29, .96), rgba(11, 14, 24, .98));
            --a360-surface: rgba(16, 22, 35, .92);
            --a360-surface2: rgba(24, 31, 49, .95);
            --a360-border: rgba(148,163,184,.16);
            --a360-text: #e2e8f0;
            --a360-soft: #94a3b8;
            --a360-shadow: 0 24px 60px rgba(0,0,0,.28);
            --a360-acq-shell-bg: linear-gradient(180deg, rgba(11,16,28,.98), rgba(13,18,31,.96));
            --a360-acq-shell-border: rgba(148,163,184,.16);
            --a360-acq-shell-shadow: 0 24px 60px rgba(0,0,0,.28);
            --a360-acq-tab-bg: rgba(255,255,255,.03);
            --a360-acq-tab-border: rgba(148,163,184,.10);
            --a360-acq-tab-text: var(--a360-soft);
            --a360-acq-tab-active-bg: rgba(96,165,250,.18);
            --a360-acq-tab-active-text: #dbeafe;
            --a360-acq-tab-active-border: rgba(96,165,250,.4);
            --a360-acq-title: #f8fafc;
            --a360-acq-panel-bg: rgba(15,20,35,.92);
            --a360-acq-panel-border: rgba(148,163,184,.14);
            --a360-acq-panel-shadow: inset 0 1px 0 rgba(255,255,255,.03);
            --a360-acq-row-hover-bg: rgba(96,165,250,.08);
            --a360-acq-row-active-bg: rgba(12,35,61,.98);
            --a360-acq-row-active-border: rgba(96,165,250,.38);
            --a360-acq-row-active-shadow: inset 0 0 0 1px rgba(96,165,250,.18), 0 8px 24px rgba(59,130,246,.10);
            --a360-acq-market-bg: rgba(34,197,94,.10);
            --a360-acq-market-border: rgba(34,197,94,.16);
            --a360-acq-market-text: #86efac;
            --a360-acq-chip-bg: rgba(255,255,255,.04);
            --a360-acq-chip-text: #cbd5e1;
            --a360-acq-chip-border: rgba(148,163,184,.14);
            --a360-acq-detail-bg: linear-gradient(180deg, rgba(15,20,35,.96), rgba(17,24,39,.96));
            --a360-acq-detail-border: rgba(148,163,184,.12);
            --a360-acq-detail-score: #93c5fd;
            --a360-acq-metric-bg: rgba(255,255,255,.03);
            --a360-acq-metric-border: rgba(148,163,184,.10);
            --a360-acq-mini-bg: rgba(255,255,255,.03);
            --a360-acq-mini-border: rgba(148,163,184,.10);
            --a360-acq-signal-text: #cbd5e1;
        }
        """
    else:
        theme_vars = """
        :root {
            --a360-bg: linear-gradient(180deg, rgba(255,255,255,1), rgba(247,249,252,1));
            --a360-surface: rgba(255,255,255,.97);
            --a360-surface2: rgba(247,249,252,.98);
            --a360-border: rgba(148,163,184,.18);
            --a360-text: #1f2937;
            --a360-soft: #64748b;
            --a360-shadow: 0 24px 60px rgba(15,23,42,.08);
            --a360-acq-shell-bg: linear-gradient(180deg, rgba(255,255,255,1), rgba(247,249,252,1));
            --a360-acq-shell-border: rgba(148,163,184,.18);
            --a360-acq-shell-shadow: 0 24px 60px rgba(15,23,42,.08);
            --a360-acq-tab-bg: rgba(248,250,252,1);
            --a360-acq-tab-border: rgba(148,163,184,.18);
            --a360-acq-tab-text: #475569;
            --a360-acq-tab-active-bg: rgba(59,130,246,.12);
            --a360-acq-tab-active-text: #1d4ed8;
            --a360-acq-tab-active-border: rgba(59,130,246,.22);
            --a360-acq-title: #1f2937;
            --a360-acq-panel-bg: #ffffff;
            --a360-acq-panel-border: rgba(226,232,240,1);
            --a360-acq-panel-shadow: inset 0 1px 0 rgba(255,255,255,.85);
            --a360-acq-row-hover-bg: rgba(59,130,246,.05);
            --a360-acq-row-active-bg: rgba(239,246,255,.98);
            --a360-acq-row-active-border: rgba(59,130,246,.28);
            --a360-acq-row-active-shadow: inset 0 0 0 1px rgba(59,130,246,.14), 0 10px 24px rgba(59,130,246,.05);
            --a360-acq-market-bg: rgba(34,197,94,.10);
            --a360-acq-market-border: rgba(34,197,94,.16);
            --a360-acq-market-text: #166534;
            --a360-acq-chip-bg: rgba(248,250,252,1);
            --a360-acq-chip-text: #475569;
            --a360-acq-chip-border: rgba(148,163,184,.18);
            --a360-acq-detail-bg: linear-gradient(180deg, rgba(255,255,255,1), rgba(248,250,252,1));
            --a360-acq-detail-border: rgba(226,232,240,1);
            --a360-acq-detail-score: #2563eb;
            --a360-acq-metric-bg: rgba(248,250,252,1);
            --a360-acq-metric-border: rgba(226,232,240,1);
            --a360-acq-mini-bg: rgba(248,250,252,1);
            --a360-acq-mini-border: rgba(226,232,240,1);
            --a360-acq-signal-text: #334155;
        }
        """
    st.markdown(
        "<style>\n"
        + theme_vars
        + """
        .a360-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 16px;
        }
        .a360-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 9px 12px;
            border-radius: 999px;
            border: 1px solid var(--a360-border);
            background: rgba(255,255,255,.04);
            color: var(--a360-text);
            font-size: 12px;
            font-weight: 700;
        }
        .a360-chip b {
            font-variant-numeric: tabular-nums;
            color: var(--a360-text);
        }
        .a360-live-strip {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 8px;
            margin: 10px 0 12px;
        }
        .a360-live-metric {
            padding: 10px 12px;
            border-radius: 12px;
            border: 1px solid var(--a360-border);
            background: var(--a360-surface);
            box-shadow: var(--a360-shadow);
        }
        .a360-live-metric span {
            display: block;
            color: var(--a360-soft);
            font-size: .68rem;
            font-weight: 850;
            letter-spacing: .12em;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        .a360-live-metric b {
            display: block;
            color: var(--a360-text);
            font-size: 1.05rem;
            line-height: 1.1;
            font-weight: 900;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .a360-note {
            margin: 8px 0 12px;
            padding: 10px 12px;
            border-radius: 14px;
            border: 1px solid rgba(251, 191, 36, .35);
            background: rgba(251, 191, 36, .10);
            color: var(--a360-text);
            font-size: .9rem;
            line-height: 1.5;
        }
        .a360-section {
            margin-top: 12px;
            padding: 12px;
            border-radius: 16px;
            border: 1px solid var(--a360-border);
            background: var(--a360-surface);
            box-shadow: var(--a360-shadow);
        }
        .a360-section-head {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 8px;
        }
        .a360-kicker {
            color: var(--a360-soft);
            font-size: 11px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .18em;
            margin-bottom: 6px;
        }
        .a360-section h2 {
            margin: 0;
            color: var(--a360-text);
            font-size: 1.5rem;
            letter-spacing: 0;
        }
        .a360-section-sub {
            margin-top: 4px;
            color: var(--a360-soft);
            font-size: .96rem;
            line-height: 1.5;
        }
        .a360-band-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
        }
        .a360-band {
            border-radius: 14px;
            border: 1px solid var(--a360-border);
            background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.015));
            padding: 12px;
            min-height: 100%;
        }
        .a360-band.good { box-shadow: inset 0 1px 0 rgba(52,211,153,.18); }
        .a360-band.bad { box-shadow: inset 0 1px 0 rgba(251,113,133,.18); }
        .a360-band.neutral { box-shadow: inset 0 1px 0 rgba(96,165,250,.18); }
        .a360-band-top {
            display: flex;
            justify-content: space-between;
            gap: 8px;
            align-items: flex-start;
        }
        .a360-band h3 {
            margin: 0;
            color: var(--a360-text);
            font-size: 1.12rem;
            letter-spacing: 0;
        }
        .a360-band p {
            margin: 6px 0 0;
            color: var(--a360-soft);
            font-size: .93rem;
            line-height: 1.45;
        }
        .a360-band-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 9px;
            border-radius: 999px;
            background: rgba(255,255,255,.06);
            border: 1px solid var(--a360-border);
            font-size: 10px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .14em;
            color: var(--a360-soft);
            margin-bottom: 6px;
        }
        .a360-chip-ghost {
            padding: 6px 8px;
            border-radius: 12px;
            border: 1px solid var(--a360-border);
            background: rgba(255,255,255,.04);
            color: var(--a360-text);
            font-size: .8rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .a360-band-list {
            list-style: none;
            padding: 0;
            margin: 10px 0 0;
        }
        .a360-band-list li {
            padding: 7px 0;
            border-top: 1px solid var(--a360-border);
        }
        .a360-band-list li:first-child { border-top: none; padding-top: 0; }
        .a360-band-row-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }
        .a360-band-row-top b {
            color: var(--a360-text);
            font-size: .96rem;
        }
        .a360-band-row-top span {
            color: var(--a360-soft);
            font-size: .88rem;
            font-variant-numeric: tabular-nums;
        }
        .a360-band-row-sub {
            margin-top: 4px;
            color: var(--a360-soft);
            font-size: .84rem;
            line-height: 1.45;
        }
        .a360-empty-row {
            color: var(--a360-soft);
            font-size: .9rem;
        }
        .a360-grid-two {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }
        .a360-roster-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }
        .a360-roster-card {
            padding: 16px;
            border-radius: 12px;
            border: 15px solid var(--a360-border);
            background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.015));
        }
        .a360-card-good { box-shadow: inset 0 1px 0 rgba(52,211,153,.16); }
        .a360-card-bad { box-shadow: inset 0 1px 0 rgba(251,113,133,.16); }
        .a360-card-neutral { box-shadow: inset 0 1px 0 rgba(96,165,250,.16); }
        .a360-roster-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 8px;
        }
        .a360-roster-name {
            color: var(--a360-text);
            font-size: 1.02rem;
            font-weight: 850;
            letter-spacing: 0;
        }
        .a360-roster-sub {
            margin-top: 3px;
            color: var(--a360-soft);
            font-size: .85rem;
        }
        .a360-status {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 5px 8px;
            border-radius: 999px;
            font-size: 10px;
            font-weight: 850;
            letter-spacing: .12em;
            text-transform: uppercase;
            white-space: nowrap;
        }
        .a360-status-good { color: #22c55e; background: rgba(34,197,94,.12); border: 1px solid rgba(34,197,94,.22); }
        .a360-status-bad { color: #fb7185; background: rgba(251,113,133,.12); border: 1px solid rgba(251,113,133,.22); }
        .a360-status-neutral { color: #64748b; background: rgba(100,116,139,.10); border: 1px solid rgba(100,116,139,.20); }
        .a360-roster-metrics {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 4px;
            margin-top: 4px;
        }
        .a360-roster-metric {
            padding: 5px 6px 6px;
            border-radius: 7px;
            background: rgba(255,255,255,.04);
            border: 1px solid var(--a360-border);
            min-height: 30px;
        }
        .a360-roster-metric span {
            display: block;
            color: var(--a360-soft);
            font-size: 6px;
            text-transform: uppercase;
            letter-spacing: .1em;
            margin-bottom: 1px;
            font-weight: 800;
        }
        .a360-roster-metric b {
            display: block;
            color: var(--a360-text);
            font-size: .68rem;
            line-height: 1;
            font-weight: 850;
        }
        .a360-roster-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 6px;
            margin-top: 6px;
            color: var(--a360-soft);
            font-size: .55rem;
            font-weight: 700;
            line-height: 1.1;
        }
        .a360-roster-footer strong {
            color: var(--a360-text);
            font-size: .68rem;
            font-weight: 850;
        }
        .a360-roster-footer span {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .a360-final-note {
            margin-top: 10px;
            color: var(--a360-soft);
            font-size: .88rem;
            line-height: 1.55;
        }
        .a360-spec-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }
        .a360-spec-card {
            padding: 12px;
            border-radius: 14px;
            border: 1px solid var(--a360-border);
            background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.015));
        }
        .a360-spec-card h3 {
            margin: 0;
            color: var(--a360-text);
            font-size: 1.08rem;
            letter-spacing: 0;
        }
        .a360-spec-card p {
            margin: 6px 0 0;
            color: var(--a360-soft);
            font-size: .92rem;
            line-height: 1.55;
        }
        .a360-spec-list {
            margin: 10px 0 0;
            padding: 0;
            list-style: none;
            display: grid;
            gap: 8px;
        }
        .a360-spec-list li {
            padding: 8px 10px;
            border-radius: 10px;
            border: 1px solid var(--a360-border);
            background: rgba(255,255,255,.03);
            color: var(--a360-text);
            font-size: .92rem;
            line-height: 1.45;
        }
        .a360-spec-kept {
            margin-top: 10px;
            padding: 10px 12px;
            border-radius: 12px;
            border: 1px solid rgba(96,165,250,.18);
            background: rgba(96,165,250,.08);
            color: var(--a360-text);
            line-height: 1.6;
        }
        .a360-spec-kept strong {
            color: var(--a360-text);
        }
        .a360-acq-shell {
            margin-top: 12px;
            padding: 12px;
            border-radius: 16px;
            border: 1px solid var(--a360-acq-shell-border);
            background: var(--a360-acq-shell-bg);
            box-shadow: var(--a360-acq-shell-shadow);
        }
        .a360-acq-header {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 8px;
        }
        .a360-acq-control-shell {
            margin: 8px 0 12px;
            padding: 0 2px;
        }
        .a360-acq-switch-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            flex-wrap: wrap;
            margin: 0;
        }
        .a360-acq-tabs,
        .a360-acq-filter-pills {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
        }
        .a360-acq-tab,
        .a360-acq-filter-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 8px;
            border: 1px solid var(--a360-acq-tab-border);
            background: var(--a360-acq-tab-bg);
            color: var(--a360-acq-tab-text);
            font-size: .78rem;
            font-weight: 750;
            line-height: 1;
            min-height: 30px;
            padding: 8px 14px;
            text-decoration: none !important;
            box-shadow: none;
            transition: transform .15s ease, border-color .15s ease, background .15s ease, color .15s ease;
        }
        .a360-acq-tab:hover,
        .a360-acq-filter-pill:hover {
            transform: translateY(-1px);
            border-color: var(--a360-acq-tab-active-border);
            color: var(--a360-acq-tab-active-text);
            text-decoration: none !important;
        }
        .a360-acq-tab.active,
        .a360-acq-filter-pill.active {
            border-color: var(--a360-acq-tab-active-border);
            background: var(--a360-acq-tab-active-bg);
            color: var(--a360-acq-tab-active-text);
            box-shadow: inset 0 0 0 1px rgba(96,165,250,.16);
        }
        .a360-acq-filter-pill {
            padding: 8px 12px;
        }
        .a360-acq-kicker {
            color: var(--a360-soft);
            font-size: 10px;
            letter-spacing: .28em;
            text-transform: uppercase;
            font-weight: 800;
            margin-bottom: 6px;
        }
        .a360-acq-title {
            color: var(--a360-acq-title);
            font-size: clamp(1.7rem, 2.4vw, 2.35rem);
            font-weight: 850;
            letter-spacing: 0;
            margin: 0;
        }
        .a360-acq-subtitle {
            color: var(--a360-soft);
            font-size: .95rem;
            line-height: 1.45;
            margin-top: 4px;
            max-width: 74ch;
        }
        .a360-acq-meta {
            color: var(--a360-soft);
            font-size: .85rem;
            text-align: right;
            line-height: 1.45;
            min-width: 180px;
        }
        .a360-acq-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.05fr) minmax(360px, .9fr);
            gap: 14px;
            align-items: start;
        }
        .a360-acq-panel {
            background: var(--a360-acq-panel-bg);
            border: 1px solid var(--a360-acq-panel-border);
            border-radius: 14px;
            padding: 0;
            box-shadow: var(--a360-acq-panel-shadow);
            overflow: hidden;
        }
        .a360-acq-panel-head {
            display: flex;
            justify-content: space-between;
            gap: 8px;
            align-items: flex-end;
            margin-bottom: 6px;
        }
        .a360-acq-panel-head h3 {
            color: var(--a360-acq-title);
            margin: 0;
            font-size: 1rem;
            font-weight: 800;
            letter-spacing: 0;
        }
        .a360-acq-panel-head p {
            color: var(--a360-soft);
            margin: 4px 0 0;
            font-size: .84rem;
            line-height: 1.4;
            text-align: right;
            min-width: 72px;
            white-space: nowrap;
        }
        .a360-acq-table-head,
        .a360-acq-row {
            display: grid;
            grid-template-columns: 34px minmax(0, 1fr) 72px 72px 52px;
            gap: 8px;
            align-items: center;
        }
        .a360-acq-table-head {
            padding: 9px 14px 8px;
            color: var(--a360-soft);
            font-size: .72rem;
            text-transform: uppercase;
            letter-spacing: .14em;
            border-bottom: 1px solid var(--a360-acq-panel-border);
        }
        .a360-acq-row {
            padding: 12px 14px;
            border-radius: 0;
            border-bottom: 1px solid var(--a360-acq-panel-border);
            transition: transform .15s ease, background .15s ease, border-color .15s ease;
            text-decoration: none !important;
            color: inherit !important;
            cursor: default;
        }
        .a360-acq-row *,
        .a360-acq-row:hover *,
        .a360-acq-row:visited *,
        .a360-acq-row:focus * {
            text-decoration: none !important;
        }
        .a360-acq-row:hover {
            background: var(--a360-acq-row-hover-bg);
            transform: translateX(2px);
        }
        .a360-acq-row.active {
            background: var(--a360-acq-row-active-bg);
            border-color: var(--a360-acq-row-active-border);
            box-shadow: var(--a360-acq-row-active-shadow);
        }
        .a360-acq-pos {
            color: var(--a360-acq-detail-score);
            font-size: .92rem;
            font-weight: 800;
            font-variant-numeric: tabular-nums;
        }
        .a360-acq-name {
            color: var(--a360-acq-title);
            font-size: .96rem;
            font-weight: 800;
            letter-spacing: 0;
            line-height: 1.2;
        }
        .a360-acq-sub {
            color: var(--a360-soft);
            font-size: .79rem;
            margin-top: 2px;
            line-height: 1.25;
        }
        .a360-acq-market {
            justify-self: start;
            padding: 3px 7px;
            border-radius: 999px;
            background: var(--a360-acq-market-bg);
            border: 1px solid var(--a360-acq-market-border);
            color: var(--a360-acq-market-text);
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .02em;
        }
        .a360-acq-mom {
            text-align: right;
            font-variant-numeric: tabular-nums;
            font-weight: 800;
            font-size: .9rem;
            color: var(--a360-acq-tab-text);
        }
        .a360-acq-mom.up { color: #34d399; }
        .a360-acq-mom.down { color: #fb7185; }
        .a360-acq-score {
            text-align: right;
            color: var(--a360-acq-detail-score);
            font-size: .95rem;
            font-weight: 900;
            font-variant-numeric: tabular-nums;
        }
        .a360-acq-detail {
            background: var(--a360-acq-detail-bg);
            border: 1px solid var(--a360-acq-detail-border);
            border-radius: 14px;
            padding: 12px;
            min-height: 100%;
        }
        .a360-acq-detail-head {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 8px;
            margin-bottom: 8px;
        }
        .a360-acq-detail-title {
            color: var(--a360-acq-title);
            font-size: 1.3rem;
            font-weight: 900;
            letter-spacing: 0;
            line-height: 1.1;
        }
        .a360-acq-detail-sub {
            margin-top: 3px;
            color: var(--a360-soft);
            font-size: .88rem;
            line-height: 1.4;
        }
        .a360-acq-detail-scorebox {
            text-align: right;
            min-width: 96px;
        }
        .a360-acq-detail-score {
            color: var(--a360-acq-detail-score);
            font-size: 2.25rem;
            line-height: 1;
            font-weight: 950;
            letter-spacing: 0;
        }
        .a360-acq-detail-score-sub {
            margin-top: 3px;
            color: var(--a360-soft);
            font-size: .78rem;
            line-height: 1.3;
        }
        .a360-acq-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 6px 0 10px;
        }
        .a360-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 5px 8px;
            border-radius: 999px;
            font-size: .73rem;
            font-weight: 800;
            border: 1px solid transparent;
        }
        .a360-chip-badge,
        .a360-chip-muted,
        .a360-chip-badge-muted {
            background: var(--a360-acq-chip-bg);
            color: var(--a360-acq-chip-text);
            border-color: var(--a360-acq-chip-border);
        }
        .a360-chip-badge-country { background: rgba(34,197,94,.10); color: #86efac; border-color: rgba(34,197,94,.18); }
        .a360-chip-badge-latam { background: rgba(96,165,250,.10); color: #bfdbfe; border-color: rgba(96,165,250,.18); }
        .a360-chip-badge-ind { background: rgba(245,158,11,.12); color: #fcd34d; border-color: rgba(245,158,11,.20); }
        .a360-chip-badge-rising { background: rgba(52,211,153,.12); color: #86efac; border-color: rgba(52,211,153,.18); }
        .a360-chip-badge-holding { background: rgba(96,165,250,.12); color: #bfdbfe; border-color: rgba(96,165,250,.18); }
        .a360-chip-badge-slipping { background: rgba(251,113,133,.12); color: #fda4af; border-color: rgba(251,113,133,.18); }
        .a360-acq-metric-grid,
        .a360-acq-mini-grid {
            display: grid;
            gap: 8px;
        }
        .a360-acq-metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-bottom: 8px;
        }
        .a360-acq-mini-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-top: 8px;
        }
        .a360-acq-metric,
        .a360-acq-mini {
            padding: 8px;
            border-radius: 10px;
            background: var(--a360-acq-metric-bg);
            border: 1px solid var(--a360-acq-metric-border);
        }
        .a360-acq-metric span,
        .a360-acq-mini span {
            display: block;
            color: var(--a360-soft);
            font-size: .72rem;
            text-transform: uppercase;
            letter-spacing: .12em;
            margin-bottom: 4px;
            font-weight: 800;
        }
        .a360-acq-metric b,
        .a360-acq-mini b {
            display: block;
            color: var(--a360-acq-title);
            font-size: .96rem;
            line-height: 1.2;
            font-weight: 800;
        }
        .a360-acq-signals {
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid rgba(148,163,184,.12);
        }
        .a360-acq-signals-hdr {
            color: var(--a360-soft);
            font-size: .75rem;
            text-transform: uppercase;
            letter-spacing: .14em;
            font-weight: 800;
            margin-bottom: 6px;
        }
        .a360-acq-signals ul {
            list-style: none;
            padding: 0;
            margin: 0;
            display: grid;
            gap: 6px;
        }
        .a360-acq-signals li {
            color: var(--a360-acq-signal-text);
            font-size: .86rem;
            line-height: 1.45;
            padding-left: 1px;
        }
        @media (max-width: 1100px) {
            .a360-band-grid,
            .a360-grid-two,
            .a360-acq-grid,
            .a360-live-strip {
                grid-template-columns: 1fr;
            }
            .a360-roster-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        @media (max-width: 720px) {
            .a360-roster-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    df = _prep_frame(leaderboard, history)
    if df.empty:
        st.warning("No leaderboard data available for the redesign dashboard.")
        return

    focus_pool = df.copy()

    snapshot_total = len(focus_pool)
    snapshot_risers = int((focus_pool["verdict"] == "rising").sum())
    snapshot_fatigue = int((focus_pool["verdict"] == "slipping").sum())
    snapshot_avg = _fmt_n(focus_pool["monthly_listeners"].dropna().mean() if focus_pool["monthly_listeners"].notna().any() else 0)
    st.markdown(
        f"""
        <div class="a360-live-strip">
            <div class="a360-live-metric"><span>Artists scored</span><b>{snapshot_total}</b></div>
            <div class="a360-live-metric"><span>Rising now</span><b>{snapshot_risers}</b></div>
            <div class="a360-live-metric"><span>Fatigue watch</span><b>{snapshot_fatigue}</b></div>
            <div class="a360-live-metric"><span>Avg listeners</span><b>{escape(snapshot_avg)}</b></div>
            <div class="a360-live-metric"><span>Last run</span><b>{escape(last_run_label)}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    brief_acq = focus_pool.sort_values("acq_score", ascending=False).head(3)
    brief_fatigue = focus_pool.sort_values("fatigue_alert", ascending=False).head(3)
    brief_hold = focus_pool.sort_values("hold_alert", ascending=False).head(3)
    if not history.empty and "scraped_at" in history.columns:
        hist_dates = pd.to_datetime(history["scraped_at"], errors="coerce").dropna()
        if not hist_dates.empty:
            window_label = f"{hist_dates.min():%b %d} - {hist_dates.max():%b %d}"
        else:
            window_label = last_run_label
    else:
        window_label = last_run_label

    st.markdown(
        """
        <section class="a360-section">
            <div class="a360-section-head">
                <div>
                    <h2>Today's Brief</h2>
                    <div class="a360-section-sub">Three equal bands, three plain-language verdicts. This is the page an exec should be able to read in fifteen seconds.</div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="a360-band-grid">
            {_band_card("Who to sign while rising", _brief_sentence("Acquire", brief_acq, "acq_score"), "ACQUIRE", "good", brief_acq, "acq_score", "verdict", "Drill into the radar")}
            {_band_card("Who's tiring, and where", _brief_sentence("Fatigue", brief_fatigue, "fatigue_alert"), "FATIGUE", "bad", brief_fatigue, "fatigue_alert", "verdict", "Inspect the map")}
            {_band_card("Are our signed artists holding up", _brief_sentence("Hold", brief_hold, "hold_alert"), "HOLD", "neutral", brief_hold, "hold_alert", "verdict", "Open roster health")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get("redesign_acq_mode") not in {"Track", "Album", "Artist"}:
        st.session_state.redesign_acq_mode = "Track"
    if "redesign_acq_latam" not in st.session_state:
        st.session_state.redesign_acq_latam = False
    if "redesign_acq_independent" not in st.session_state:
        st.session_state.redesign_acq_independent = False
    if "redesign_acq_index" not in st.session_state:
        st.session_state.redesign_acq_index = 0

    query_mode = st.query_params.get("redesign_acq_mode")
    if query_mode in {"Track", "Album", "Artist"}:
        st.session_state.redesign_acq_mode = query_mode

    query_latam = st.query_params.get("redesign_acq_latam")
    if query_latam in {"0", "1"}:
        st.session_state.redesign_acq_latam = query_latam == "1"

    query_independent = st.query_params.get("redesign_acq_independent")
    if query_independent in {"0", "1"}:
        st.session_state.redesign_acq_independent = query_independent == "1"

    query_index = st.query_params.get("redesign_acq_index")
    if query_index is not None:
        try:
            st.session_state.redesign_acq_index = max(0, int(query_index))
        except (TypeError, ValueError):
            pass

    for query_key in ("redesign_acq_mode", "redesign_acq_latam", "redesign_acq_independent", "redesign_acq_index"):
        if query_key in st.query_params:
            del st.query_params[query_key]

    mode = st.session_state.redesign_acq_mode
    latam_only = bool(st.session_state.redesign_acq_latam)
    independent_only = bool(st.session_state.redesign_acq_independent)
    score_col, _mode_title, mode_subtitle = _acq_score_label(mode)
    acq_rows = _filter_acq_rows(focus_pool, latam_only=latam_only, independent_only=independent_only)
    acq_rows = acq_rows.sort_values([score_col, "rank"], ascending=[False, True]).reset_index(drop=True)
    if not acq_rows.empty:
        acq_rows[f"{score_col}_rank"] = acq_rows[score_col].rank(ascending=False, method="min").astype(int)

    st.markdown(
        textwrap.dedent(
            f"""
        <section class="a360-acq-shell">
            <div class="a360-acq-header">
                <div>
                    <h2 class="a360-acq-title">Acquisition radar</h2>
                    <div class="a360-acq-subtitle">{escape(mode_subtitle)} Score = listeners + points + market breadth, tuned to the data available in this workspace.</div>
                </div>
                <div class="a360-acq-meta">{escape(window_label)} · {len(acq_rows)} artists scored</div>
            </div>
        </section>
        """
        ).strip(),
        unsafe_allow_html=True,
    )

    control_col_1, control_col_2, control_col_3 = st.columns([1.7, 1.0, 1.15], gap="small")
    with control_col_1:
        st.radio(
            "Acquisition mode",
            ["Track", "Album", "Artist"],
            horizontal=True,
            key="redesign_acq_mode",
        )
    with control_col_2:
        st.toggle("LATAM only", key="redesign_acq_latam")
    with control_col_3:
        st.toggle("Independent only", key="redesign_acq_independent")

    latam_only = bool(st.session_state.redesign_acq_latam)
    independent_only = bool(st.session_state.redesign_acq_independent)

    if acq_rows.empty:
        st.info("No rows match the current acquisition filters.")
    else:
        visible_rows = acq_rows.head(12).copy()
        entity_label = {"Track": "Artist / Track", "Album": "Artist / Album", "Artist": "Artist"}.get(mode, "Artist / Track")
        st.session_state.redesign_acq_index = max(0, min(int(st.session_state.redesign_acq_index), len(visible_rows) - 1))
        selected_idx = st.selectbox(
            "Spotlight row",
            options=list(range(len(visible_rows))),
            format_func=lambda idx: f"{idx + 1}. {_acq_display_name(visible_rows.iloc[idx], mode)}",
            key="redesign_acq_index",
        )
        selected_idx = max(0, min(selected_idx, len(visible_rows) - 1))
        row = visible_rows.iloc[selected_idx]
        score_rank = int(row.get(f"{score_col}_rank") or selected_idx + 1)
        table_head = textwrap.dedent(
            f"""
            <div class="a360-acq-table-head">
                <div>#</div>
                <div>{escape(entity_label)}</div>
                <div>Market</div>
                <div>Mom.</div>
                <div>Score</div>
            </div>
            """
        ).strip()
        rows_html = "".join(
            _render_acq_row(
                row,
                idx=i + 1,
                mode=mode,
                score_col=score_col,
                selected=i == selected_idx,
            )
            for i, (_, row) in enumerate(visible_rows.iterrows())
        )
        detail_html = _render_acq_detail(
            row,
            mode=mode,
            score_col=score_col,
            score_rank=score_rank,
            total_rows=len(acq_rows),
        )
        table_col, detail_col = st.columns([1.1, 0.95], gap="medium")
        with table_col:
            st.markdown(
                f"""
                <div class="a360-acq-panel">
                    {table_head}
                    {rows_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
        with detail_col:
            st.markdown(detail_html, unsafe_allow_html=True)

    st.markdown(
        """
        <section class="a360-section">
            <div class="a360-section-head">
                <div>
                    <h2>Fatigue Map</h2>
                    <div class="a360-section-sub">Momentum on the x-axis, audience on the y-axis, bubble size = importance. The top-left is the red zone: big audience, falling fast.</div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    fatigue_fig = _make_fatigue_figure(focus_pool, dark_mode=is_dark)
    if fatigue_fig.data:
        _render_plotly_html(fatigue_fig, height=460, dark_mode=is_dark)
    else:
        st.info("No fatigue map rows available for the current slice.")

    roster_pool = focus_pool.copy()
    roster_pool = roster_pool.sort_values(["hold_alert", "monthly_listeners"], ascending=[False, False])
    focus_row = roster_pool.head(1)

    st.markdown(
        """
        <section class="a360-section">
            <div class="a360-section-head">
                <div>
                    <h2>Roster Health</h2>
                    <div class="a360-section-sub">One compact card per artist, with a rank label, verdict chip, four KPI tiles, and a market footer. This is the page for asking whether the roster is still holding.</div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if not focus_row.empty:
        row = focus_row.iloc[0]
        st.markdown(
            f"""
            <div class="a360-note">
                <b>{escape(str(row.get('name') or 'Artist'))}</b> is the current focus. The dashboard uses the latest ranking and the current market footprint as the working proxy for roster health until confirmed roster flags arrive.
            </div>
            """,
            unsafe_allow_html=True,
        )

    roster_cards = roster_pool.head(8)
    if roster_cards.empty:
        st.info("No roster rows available for the current slice.")
    else:
        cards_html = "".join(_roster_card(row, idx=i + 1) for i, (_, row) in enumerate(roster_cards.iterrows()))
        st.markdown(f"<div class='a360-roster-grid'>{cards_html}</div>", unsafe_allow_html=True)

    cuts_html = "".join(
        f"<li>{escape(item)}</li>"
        for item in [
            "Total Points - composite, no decision attached",
            "Position Strength Score + its bar chart",
            "Stream Signal (970.8M) as a hero number",
            "iTunes Points (1.1M) as a headline KPI",
            "Duplicate listener cards: 5 instances -> 1",
            "Track / Album / Artist Movement as its own module",
            "Label Power Score - demoted to appendix",
        ]
    )
    kept_html = "".join(
        f"<li>{escape(item)}</li>"
        for item in [
            "30-day momentum - acquire + fatigue",
            "Acquisition Score - acquire ranking",
            "Rank + movement chip - hold / fatigue",
            "Monthly listeners (one instance) - fatigue axis",
        ]
    )
    deps_html = "".join(
        f"<li>{escape(item)}</li>"
        for item in [
            "Per-artist / per-track country trend, at minimum each entity's weakest market and trend.",
            "Signed vs independent status plus the label name, so the acquire and roster views stop relying on proxies.",
        ]
    )

    st.markdown(
        f"""
        <section class="a360-section">
            <div class="a360-section-head">
                <div>
                    <div class="a360-kicker">Dependencies</div>
                    <h2>What changes, and what it depends on</h2>
                    <div class="a360-section-sub">This closes the loop from the deck: which KPIs are cut, which ones stay decision-grade, and what data must land before the filters stop being visual only.</div>
                </div>
            </div>
            <div class="a360-spec-grid">
                <article class="a360-spec-card">
                    <h3>KPI cuts (knowing, not deciding)</h3>
                    <p>These are useful reference metrics, but they do not directly support a decision in the new story.</p>
                    <ul class="a360-spec-list">{cuts_html}</ul>
                </article>
                <article class="a360-spec-card">
                    <h3>Two data fields required (task zero)</h3>
                    <p>The deck calls these out because the radar, fatigue, and roster views need them before they can be truly production-ready.</p>
                    <ul class="a360-spec-list">{deps_html}</ul>
                    <div class="a360-spec-kept"><strong>Why it matters:</strong> without these two fields, the LATAM filter, the independent filter, and the fatigue/roster "where" stay decorative.</div>
                </article>
            </div>
            <div class="a360-spec-kept" style="margin-top:16px;">
                <strong>KPIs kept (each drives a decision):</strong>
                <ul class="a360-spec-list" style="margin-top:12px;">{kept_html}</ul>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="a360-final-note">
            Once per-country artist trajectories and a confirmed signed or independent flag land in the model, the radar and roster views can split cleanly by market and roster type.
            Until then, this page is intentionally framed as a prototype so the missing data is obvious, not hidden.
        </div>
        """,
        unsafe_allow_html=True,
    )
