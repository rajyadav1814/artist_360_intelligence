"""Skeleton loading screen for Artist 360 Intelligence dashboard.

Mirrors the real leaderboard layout from the screenshot:
  - Page header + LIVE badge
  - 4 gradient-topped KPI cards
  - Tab bar (Table / Analysis / Compare / Download)
  - Two-column body: left = Global Chart Positions table,
                     right = two stacked chart cards
"""
from __future__ import annotations

import textwrap

import streamlit as st

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
_CSS = """
<style>
/* ── shimmer keyframe ── */
@keyframes sk-shimmer {
    0%   { background-position: -900px 0; }
    100% { background-position:  900px 0; }
}

/* base animated block */
.sk {
    border-radius: 5px;
    background: linear-gradient(90deg, #1a2236 25%, #243050 50%, #1a2236 75%);
    background-size: 900px 100%;
    animation: sk-shimmer 1.5s infinite linear;
}

/* ── page wrapper ── */
.sk-page {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    padding: 0 0 32px 0;
    background: transparent;
}

/* ── page header ── */
.sk-page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 28px;
}
.sk-page-header-left { display: flex; flex-direction: column; gap: 10px; }
.sk-title  { height: 38px; width: 340px; }
.sk-sub    { height: 14px; width: 500px; }
.sk-live-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    border: 1px solid #22d3a0;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 12px;
    color: #22d3a0;
    white-space: nowrap;
    margin-top: 4px;
}
.sk-live-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #22d3a0;
    animation: sk-pulse 1.2s ease-in-out infinite;
}
@keyframes sk-pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
}

/* ── KPI row ── */
.sk-kpi-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}
.sk-kpi-card {
    background: #111827;
    border: 1px solid #1e2d47;
    border-radius: 12px;
    padding: 20px 18px 14px;
    display: flex;
    flex-direction: column;
    gap: 0;
    position: relative;
    overflow: hidden;
}
/* coloured top accent bar per card */
.sk-kpi-card:nth-child(1) { border-top: 3px solid #4f8ef7; }
.sk-kpi-card:nth-child(2) { border-top: 3px solid #22d3a0; }
.sk-kpi-card:nth-child(3) { border-top: 3px solid #f5a623; }
.sk-kpi-card:nth-child(4) { border-top: 3px solid #e84545; }
.sk-kpi-label  { height: 11px; width: 130px; margin-bottom: 12px; }
.sk-kpi-value  { height: 34px; width: 100px; margin-bottom: 10px; }
.sk-kpi-desc   { height: 11px; width: 160px; margin-bottom: 14px; }
.sk-kpi-bar    { height: 4px;  width: 100%; border-radius: 2px; }

/* ── tab bar ── */
.sk-tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}
.sk-tab {
    height: 38px;
    border-radius: 8px;
    flex: 1;
    min-width: 80px;
}
.sk-tab-active { background: #e84545 !important; animation: none; }
.sk-tab-dl     { background: #22d3a0 !important; animation: none; }

/* ── two-column body ── */
.sk-body {
    display: grid;
    grid-template-columns: 64fr 36fr;
    gap: 16px;
    align-items: start;
}

/* ── left: chart positions card ── */
.sk-card {
    background: #111827;
    border: 1px solid #1e2d47;
    border-radius: 12px;
    padding: 20px 18px;
}
.sk-card-title { height: 18px; width: 220px; margin-bottom: 6px; }
.sk-card-sub   { height: 12px; width: 300px; margin-bottom: 20px; }

/* ── table inside left card ── */
.sk-tbl { width: 100%; border-collapse: collapse; }
.sk-tbl-head tr { border-bottom: 1px solid #1e2d47; }
.sk-tbl th, .sk-tbl td { padding: 9px 10px; }
.sk-cell { height: 14px; border-radius: 4px; }

/* ── right column: stacked chart cards ── */
.sk-right { display: flex; flex-direction: column; gap: 16px; }
.sk-chart-title  { height: 16px; width: 180px; margin-bottom: 16px; }
/* horizontal bar rows */
.sk-bar-rows { display: flex; flex-direction: column; gap: 10px; }
.sk-bar-row  { display: flex; align-items: center; gap: 10px; }
.sk-bar-label { height: 12px; width: 80px; flex-shrink: 0; }
.sk-bar-fill  { height: 18px; border-radius: 4px; }
/* donut */
.sk-donut-wrap {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 12px 0 4px;
}
.sk-donut {
    width: 130px; height: 130px;
    border-radius: 50%;
    background: conic-gradient(#1a2236 0deg, #243050 360deg);
    animation: sk-shimmer 1.5s infinite linear;
    background-size: 900px 100%;
    position: relative;
}
.sk-donut::after {
    content: "";
    position: absolute;
    inset: 28px;
    border-radius: 50%;
    background: #111827;
}
</style>
"""

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------
_HTML = """
{css}
<div class="sk-page">

  <!-- ── Page header ── -->
  <div class="sk-page-header">
    <div class="sk-page-header-left">
      <div class="sk sk-title"></div>
      <div class="sk sk-sub"></div>
    </div>
    <div class="sk-live-badge">
      <div class="sk-live-dot"></div>LIVE
    </div>
  </div>

  <!-- ── KPI cards ── -->
  <div class="sk-kpi-row">
    {kpi_cards}
  </div>

  <!-- ── Tab bar ── -->
  <div class="sk-tabs">
    <div class="sk sk-tab"></div>
    <div class="sk sk-tab"></div>
    <div class="sk sk-tab"></div>
    <div class="sk sk-tab"></div>
  </div>

  <!-- ── Two-column body ── -->
  <div class="sk-body">

    <!-- Left: Global Chart Positions -->
    <div class="sk-card">
      <div class="sk sk-cell sk-card-title"></div>
      <div class="sk sk-cell sk-card-sub"></div>
      <table class="sk-tbl">
        <thead class="sk-tbl-head">
          <tr>{header_cells}</tr>
        </thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>

    <!-- Right: stacked charts -->
    <div class="sk-right">

      <!-- Top Artists bar chart -->
      <div class="sk-card">
        <div class="sk sk-cell sk-chart-title"></div>
        <div class="sk-bar-rows">{bar_rows}</div>
      </div>

      <!-- LATAM Presence donut -->
      <div class="sk-card">
        <div class="sk sk-cell sk-chart-title"></div>
        <div class="sk-donut-wrap">
          <div class="sk-donut"></div>
        </div>
      </div>

    </div>
  </div>

</div>
"""

# ---------------------------------------------------------------------------
# KPI card
# ---------------------------------------------------------------------------
_KPI_CARD = """
    <div class="sk-kpi-card">
      <div class="sk sk-cell sk-kpi-label"></div>
      <div class="sk sk-cell sk-kpi-value"></div>
      <div class="sk sk-cell sk-kpi-desc"></div>
      <div class="sk sk-cell sk-kpi-bar"></div>
    </div>"""

# ---------------------------------------------------------------------------
# Table helpers  (#  Artist  Top Song  Top Country  Monthly  Peak  Trend)
# ---------------------------------------------------------------------------
_HEADER_WIDTHS = ["28px", "130px", "120px", "90px", "80px", "80px", "40px"]
_ROW_WIDTHS    = ["22px", "110px", "100px", "80px", "70px", "70px", "30px"]


def _header_cells() -> str:
    return "".join(
        f'<th><div class="sk sk-cell" style="width:{w}"></div></th>'
        for w in _HEADER_WIDTHS
    )


def _body_rows(n: int) -> str:
    row_html = "".join(
        f'<td style="padding:9px 10px"><div class="sk sk-cell" style="width:{w}"></div></td>'
        for w in _ROW_WIDTHS
    )
    return "".join(f"<tr>{row_html}</tr>" for _ in range(n))


# ---------------------------------------------------------------------------
# Horizontal bar rows (right-side chart)
# ---------------------------------------------------------------------------
_BAR_FILL_WIDTHS = ["88%", "82%", "76%", "62%", "56%", "52%", "46%", "40%"]


def _bar_rows() -> str:
    rows = []
    for w in _BAR_FILL_WIDTHS:
        rows.append(
            f'<div class="sk-bar-row">'
            f'<div class="sk sk-cell sk-bar-label"></div>'
            f'<div class="sk sk-cell sk-bar-fill" style="width:{w};flex:1"></div>'
            f'</div>'
        )
    return "\n        ".join(rows)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_dashboard_skeleton(n_rows: int = 10) -> None:
    """Render an animated skeleton that mirrors the Leaderboard layout."""
    html = _HTML.format(
        css=_CSS,
        kpi_cards=_KPI_CARD * 4,
        header_cells=_header_cells(),
        body_rows=_body_rows(n_rows),
        bar_rows=_bar_rows(),
    )
    # st.html() renders raw HTML without Markdown processing, avoiding the
    # "4-space = code block" pitfall of st.markdown.
    st.html(textwrap.dedent(html))
