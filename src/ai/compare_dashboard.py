"""Artist Comparison Dashboard"""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from src.utils.ui import custom_multiselect


def fmt_short(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"


def render_compare_dashboard(filtered: pd.DataFrame) -> None:
    """Renders the artist comparison dashboard."""
    st.markdown(
        """
        <style>
        .cmp-note {
            margin-top: -20px;
            margin-bottom: 0.9rem;
            padding: 0.75rem 0.9rem;
            border-radius: 12px;
            border: 1px solid rgba(251,113,133,.35);
            background: rgba(251,113,133,.12);
            color: var(--text);
            font-size: 0.9rem;
            font-weight: 600;
        }
        .cmp-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.85rem;
            margin: 0.75rem 0 1rem;
        }
        .cmp-card {
            background: linear-gradient(180deg, var(--surface2) 0%, var(--surface) 100%);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            box-shadow: 0 12px 26px rgba(0,0,0,.08);
        }
        .cmp-artist {
            color: var(--text);
            font-size: 1rem;
            font-weight: 800;
            margin-bottom: 0.6rem;
            letter-spacing: .01em;
        }
        .cmp-metric {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 0.5rem;
            padding: 0.3rem 0;
            border-bottom: 1px solid var(--border);
            font-size: 0.84rem;
        }
        .cmp-metric:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }
        .cmp-metric-label {
            color: var(--text2);
            font-weight: 600;
        }
        .cmp-metric-value {
            color: var(--text);
            font-weight: 800;
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        .cmp-warning {
            margin-top: -1.8rem;
            border: 1px solid rgba(245,166,35,.45);
            background: rgba(245,166,35,.14);
            color: var(--text);
            border-radius: 12px;
            padding: 0.72rem 0.88rem;
            font-size: 0.88rem;
            font-weight: 600;
        }
        </style>
        <div class='cmp-note'>Select 2-5 artists to compare their leaderboard metrics.
        <div >Side-by-side performance benchmarking for head-to-head artist analysis. Compare multiple acts across primary metrics including audience scale, catalog depth, and global market penetration.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    available_artists = filtered["name"].dropna().tolist()[:20]
    selected_for_comparison = custom_multiselect(
        "Select artists to compare",
        available_artists,
        default=available_artists[:2] if len(available_artists) >= 2 else available_artists,
        max_selections=5,
        key="comparison_artists"
    )

    if len(selected_for_comparison) < 2:
        st.markdown(
            "<div class='cmp-warning'>Please select at least 2 artists to compare.</div>",
            unsafe_allow_html=True,
        )
        return

    # The rest of the logic from the original `show_compare_page` will go here.
    # For now, this sets up the structure.