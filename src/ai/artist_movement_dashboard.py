"""Artist Movement dashboard for rank trend tracking."""
from __future__ import annotations

from html import escape
import json

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as st_components

from src.utils.ui import custom_selectbox


PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}
TRACKER_TOP_ARTISTS = 10


def render_plotly_html(fig: go.Figure, *, height: int | None = None, dark_mode: bool | None = None) -> None:
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
    bg_color = "rgba(13, 17, 23, 0.95)" if dark_mode else "#FFFFFF"
    border_color = "rgba(108, 92, 231, 0.2)" if dark_mode else "rgba(108, 92, 231, 0.15)"
    shadow_color = "rgba(0, 0, 0, 0.22)" if dark_mode else "rgba(108, 92, 231, 0.05)"

    st_components.html(
        f"""
        <div class="graph-card">
            <div class="plotly-html-chart">{chart_html}</div>
        </div>
        <style>
            body {{ margin: 0; background: transparent; }}
            .graph-card {{
                width: 100%; box-sizing: border-box; padding: 10px 10px 6px 10px;
                border-radius: 20px; border: 1px solid {border_color};
                background: {bg_color}; box-shadow: 0 4px 12px {shadow_color};
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


def style_figure(fig, height: int, dark_mode: bool | None = None) -> None:
    if dark_mode is None:
        dark_mode = st.session_state.get("dark_mode", True)

    text_color = "#cdd6e4" if dark_mode else "#1A1A1A"
    grid_color = "rgba(255,255,255,0.06)" if dark_mode else "rgba(0,0,0,0.06)"
    line_color = "rgba(255,255,255,0.1)" if dark_mode else "rgba(0,0,0,0.1)"

    fig.update_layout(
        template="plotly_dark" if dark_mode else "plotly_white",
        height=max(280, int(height)),
        margin=dict(l=4, r=20, t=56, b=8, pad=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=text_color, family="Inter, ui-sans-serif, system-ui, sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(gridcolor=grid_color, linecolor=line_color, zerolinecolor=line_color)
    fig.update_yaxes(gridcolor=grid_color, linecolor=line_color, zerolinecolor=line_color)


def resample_tracker_pattern(pattern: list[int], days: int) -> list[int]:
    if not pattern:
        return [1] * max(days, 1)
    if days <= 1:
        return [int(pattern[-1])]
    if len(pattern) == days:
        return [int(value) for value in pattern]

    resampled: list[int] = []
    last_index = len(pattern) - 1
    for step in range(days):
        scaled_index = (step / (days - 1)) * last_index
        lower = int(scaled_index)
        upper = min(lower + 1, last_index)
        blend = scaled_index - lower
        interpolated = pattern[lower] + (pattern[upper] - pattern[lower]) * blend
        resampled.append(int(round(interpolated)))
    return resampled


def build_tracker_demo_data(leaderboard: pd.DataFrame, days: int = 14, limit: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "rank" in leaderboard.columns and leaderboard["rank"].notna().any():
        top = leaderboard.dropna(subset=["rank"]).sort_values("rank").head(limit).copy()
    else:
        top = leaderboard.dropna(subset=["monthly_listeners"]).nlargest(limit, "monthly_listeners").copy()

    if top.empty:
        top = leaderboard.head(limit).copy()

    top = top.reset_index(drop=True)
    date_range = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days)
    date_labels = date_range.strftime("%b %-d").tolist()
    base_patterns = [
        [3, 2, 2, 1, 1, 2, 3, 2, 1, 1, 2, 1, 1, 1],
        [5, 4, 3, 3, 2, 2, 1, 2, 3, 2, 2, 3, 2, 2],
        [8, 7, 6, 5, 4, 3, 4, 3, 3, 4, 3, 3, 3, 3],
        [10, 9, 8, 7, 6, 5, 6, 5, 4, 5, 4, 4, 4, 4],
        [15, 12, 10, 9, 8, 7, 8, 7, 6, 5, 5, 5, 5, 5],
    ]

    max_rank = int(top["rank"].max()) if "rank" in top.columns and top["rank"].notna().any() else limit + 8
    max_rank = max(limit + 2, max_rank)

    records = []
    best_rows = []
    for idx, row in top.iterrows():
        pattern = resample_tracker_pattern(base_patterns[idx % len(base_patterns)], days)
        current_rank = int(row["rank"]) if pd.notna(row.get("rank")) else idx + 1
        current_rank = max(1, min(max_rank, current_rank))
        shift = current_rank - pattern[-1]
        series = [max(1, min(max_rank, point + shift)) for point in pattern]

        for day_label, plot_date, pos in zip(date_labels, date_range, series):
            records.append({"day": day_label, "date": plot_date, "artist": row["name"], "position": pos})

        best_rows.append({
            "artist": row["name"],
            "best_position": min(series),
        })

    return pd.DataFrame(records), pd.DataFrame(best_rows).sort_values("best_position")


def render_chart_tracker(history: pd.DataFrame, leaderboard: pd.DataFrame) -> None:
    if history.empty and leaderboard.empty:
        st.warning("Not enough ranking data available yet.")
        return

    # ── Inject Chart Tracker styles (scoped) ─────────────────────────
    st.markdown(
        """
        <style>
        .ct-hero{
            background:linear-gradient(135deg,var(--surface2) 0%,var(--surface) 100%);
            border:1px solid var(--border);border-radius:14px;padding:22px 26px;
            position:relative;overflow:hidden;margin-bottom:18px;
            box-shadow:0 4px 24px rgba(0,0,0,.12);
        }
        .ct-hero::before{
            content:'';position:absolute;top:0;left:0;right:0;height:3px;
            background:linear-gradient(90deg,#34d399,#60a5fa,#c4b5fd);
        }
        .ct-tag{
            font-size:11px;color:var(--text2);letter-spacing:1.4px;text-transform:uppercase;
            font-weight:700;display:flex;align-items:center;gap:8px;margin-bottom:8px;
        }
        .ct-live{
            width:8px;height:8px;border-radius:50%;background:#34d399;
            box-shadow:0 0 8px #34d399;animation:ctblink 2s infinite;
        }
        @keyframes ctblink{0%,100%{opacity:1}50%{opacity:.4}}
        .ct-title{font-size:26px;font-weight:700;letter-spacing:-.5px;color:var(--text);margin-bottom:4px}
        .ct-sub{font-size:13px;color:var(--text2);font-weight:500}

        .ct-kpi-row{
            display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px;
        }
        .ct-kpi{
            background:var(--surface);border:1px solid var(--border);border-radius:12px;
            padding:6px 18px;transition:.15s;position:relative;overflow:hidden;
            box-shadow:0 2px 8px rgba(0,0,0,.06);
        }
        .ct-kpi:hover{transform:translateY(-2px);border-color:var(--accent);
            box-shadow:0 6px 18px rgba(251,113,133,.15)}
        .ct-kpi::before{content:'';position:absolute;top:0;left:0;width:3px;height:100%;
            background:var(--accent,#60a5fa)}
        .ct-kpi-lbl{font-size:10px;color:var(--text2);text-transform:uppercase;
            letter-spacing:.7px;font-weight:600;margin-bottom:6px}
        .ct-kpi-val{font-size:24px;font-weight:700;color:var(--text);
            letter-spacing:-.4px;line-height:1.15;font-variant-numeric:tabular-nums}
        .ct-kpi-sub{font-size:11px;color:var(--text2);margin-top:4px;font-weight:500}
        .ct-kpi.up{--accent:#34d399}.ct-kpi.up .ct-kpi-val{color:#059669}
        .ct-kpi.down{--accent:#fb7185}.ct-kpi.down .ct-kpi-val{color:#e11d48}
        .ct-kpi.purple{--accent:#c4b5fd}.ct-kpi.purple .ct-kpi-val{color:#7c3aed}
        .ct-kpi.amber{--accent:#fcd34d}.ct-kpi.amber .ct-kpi-val{color:#d97706}

        .ct-section{
            background:var(--surface);border:1px solid var(--border);border-radius:12px;
            padding:8px 8px 4px;margin-bottom:18px;
        }
        .ct-section-ttl{
            font-size:13px;color:var(--text);font-weight:600;text-transform:uppercase;
            letter-spacing:.6px;padding:10px 14px 8px;border-bottom:1px solid var(--border);
            display:flex;align-items:center;gap:8px;margin-bottom:6px;
        }
        .ct-section-desc{
            font-size:12px;color:var(--text2);line-height:1.5;padding:0 14px 12px;
        }
        .ct-chart-note{
            background:var(--surface);border:1px solid var(--border);border-radius:12px;
            padding:14px 16px;margin:12px 0 12px;
        }
        .ct-chart-note-title{
            font-size:14px;font-weight:700;color:var(--text);margin-bottom:5px;
            display:flex;align-items:center;gap:8px;
        }
        .ct-chart-note-copy{
            font-size:12px;color:var(--text2);line-height:1.5;
        }

        /* Movement table */
        .ct-mv-tbl{width:100%;border-collapse:collapse;font-size:13px}
        .ct-mv-tbl thead th{
            font-size:10px;color:var(--text2);text-transform:uppercase;letter-spacing:.6px;
            font-weight:600;padding:10px 14px;border-bottom:1px solid var(--border);text-align:left;
        }
        .ct-mv-tbl tbody td{
            padding:12px 14px;border-bottom:1px solid var(--border);color:var(--text);
        }
        .ct-mv-tbl tbody tr:hover{background:var(--surface2)}
        .ct-mv-tbl tbody tr:last-child td{border-bottom:none}
        .ct-rank-cell{font-weight:600;font-variant-numeric:tabular-nums;color:var(--text2)}
        .ct-artist{font-weight:600;color:var(--text)}
        .ct-pill{display:inline-flex;align-items:center;gap:4px;
            font-size:11px;font-weight:700;padding:4px 10px;border-radius:5px;
            font-variant-numeric:tabular-nums}
        .ct-pill-up{background:rgba(52,211,153,.15);color:#059669;border:1px solid rgba(52,211,153,.4)}
        .ct-pill-down{background:rgba(251,113,133,.15);color:#e11d48;border:1px solid rgba(251,113,133,.4)}
        .ct-pill-flat{background:var(--surface2);color:var(--text2);border:1px solid var(--border)}
        </style>
        """,
        unsafe_allow_html=True,
    )

    unique_runs = int(history["scraped_at"].nunique()) if not history.empty else 0

    col_text, col1, col2, col3 = st.columns([1.5, 1, 1, 1])
    with col_text:
        st.markdown(
            "<div style='font-size: 0.92rem; color: var(--t2); margin: 0 0 14px; line-height: 1.5; font-weight: 500;'>"
            "Rank momentum across iTunes worldwide artist rankings."
            "</div>",
            unsafe_allow_html=True,
        )
    with col1:
        time_range = custom_selectbox("📅 Time Range", ["7 days", "14 days", "30 days"], index=2, key="ct_range")
    with col2:
        view_mode = custom_selectbox("👁️ View Mode", ["Line Chart", "Area Chart"], index=0, key="ct_view")
    with col3:
        num_artists = int(custom_selectbox("👥 Number of Artists", ["10", "20", "30", "40", "50"], index=0, key="ct_num_artists"))

    time_window_days = int(time_range.split()[0])
    using_demo = unique_runs < 3
    if using_demo:
        line_df, best_df = build_tracker_demo_data(leaderboard, days=time_window_days, limit=num_artists)
    else:
        history = history.copy()
        history["scraped_at"] = pd.to_datetime(history["scraped_at"], errors="coerce")
        history = history.dropna(subset=["scraped_at", "rank", "name"]).sort_values(["scraped_at", "rank"])

        latest_scraped_at = None
        window_start = None
        if not history.empty:
            latest_scraped_at = history["scraped_at"].max().normalize()
            window_start = latest_scraped_at - pd.Timedelta(days=time_window_days - 1)
            history = history[history["scraped_at"] >= window_start]

        if history.empty:
            st.info("📊 Limited long-range history is available. Showing an interpolated top-artist trend instead.", icon="ℹ️")
            line_df, best_df = build_tracker_demo_data(leaderboard, days=time_window_days)
            using_demo = True
        else:
            history["day"] = history["scraped_at"].dt.strftime("%b %-d")
            line_df = history.rename(columns={"name": "artist", "rank": "position", "scraped_at": "date"})[
                ["day", "date", "artist", "position"]
            ]

            if latest_scraped_at is not None and window_start is not None:
                target_dates = pd.date_range(start=window_start.normalize(), end=latest_scraped_at.normalize(), freq="D")
                has_sparse_days = line_df["date"].dt.normalize().nunique() < len(target_dates)
                if has_sparse_days:
                    daily_parts = []
                    for artist_name, artist_rows in line_df.groupby("artist", sort=False):
                        artist_daily = artist_rows.copy()
                        artist_daily["date"] = artist_daily["date"].dt.normalize()
                        artist_daily = (
                            artist_daily.sort_values("date")
                            .drop_duplicates(subset=["date"], keep="last")
                            .set_index("date")
                            .reindex(target_dates)
                        )
                        artist_daily["artist"] = artist_name
                        artist_daily["position"] = pd.to_numeric(artist_daily["position"], errors="coerce")
                        artist_daily["position"] = artist_daily["position"].interpolate(method="linear").ffill().bfill()
                        artist_daily = artist_daily.reset_index().rename(columns={"index": "date"})
                        artist_daily["day"] = artist_daily["date"].dt.strftime("%b %-d")
                        daily_parts.append(artist_daily[["day", "date", "artist", "position"]])

                    if daily_parts:
                        line_df = pd.concat(daily_parts, ignore_index=True) 

            best_df = (
                history.groupby("name", as_index=False)["rank"]
                .min()
                .rename(columns={"name": "artist", "rank": "best_position"})
                .sort_values("best_position")
            )

    if using_demo and "rank" in leaderboard.columns and leaderboard["rank"].notna().any():
        artists_tracked = leaderboard.dropna(subset=["rank"]).sort_values("rank")["name"].head(num_artists).tolist()
    else:
        artists_tracked = (
            line_df.sort_values(["position", "artist"])["artist"].drop_duplicates().tolist()[:num_artists]
        )

    line_df = line_df[line_df["artist"].isin(artists_tracked)]
    best_df = best_df[best_df["artist"].isin(artists_tracked)].sort_values("best_position", ascending=False)

    # ── Build movement insights & KPIs ───────────────────────────────
    movement_rows: list[dict] = []
    for artist in artists_tracked:
        sub = line_df[line_df["artist"] == artist].sort_values("date")
        if len(sub) >= 2:
            first_pos = int(sub.iloc[0]["position"])
            last_pos = int(sub.iloc[-1]["position"])
            change = first_pos - last_pos
            best_pos = int(sub["position"].min())
            movement_rows.append({
                "artist": artist,
                "start": first_pos,
                "current": last_pos,
                "best": best_pos,
                "change": change,
            })

    if movement_rows:
        big_riser = max(movement_rows, key=lambda r: r["change"])
        big_faller = min(movement_rows, key=lambda r: r["change"])
        avg_pos = sum(r["current"] for r in movement_rows) / len(movement_rows)
        leader = min(movement_rows, key=lambda r: r["current"])

        kpi_html = f"""
        <div class='ct-kpi-row'>
          <div class='ct-kpi purple'>
            <div class='ct-kpi-lbl'>Current</div>
            <div class='ct-kpi-val' style='font-size:18px'>{escape(leader['artist'])}</div>
            <div class='ct-kpi-sub'>Position {leader['current']} · best {leader['best']}</div>
          </div>
          <div class='ct-kpi up'>
            <div class='ct-kpi-lbl'>Biggest riser</div>
            <div class='ct-kpi-val'>{'+' if big_riser['change']>0 else ''}{big_riser['change']}</div>
            <div class='ct-kpi-sub'>{escape(big_riser['artist'])} · {big_riser['start']} → {big_riser['current']}</div>
          </div>
          <div class='ct-kpi down'>
            <div class='ct-kpi-lbl'>Biggest faller</div>
            <div class='ct-kpi-val'>{big_faller['change']}</div>
            <div class='ct-kpi-sub'>{escape(big_faller['artist'])} · {big_faller['start']} → {big_faller['current']}</div>
          </div>
          <div class='ct-kpi amber'>
            <div class='ct-kpi-lbl'>Avg position</div>
            <div class='ct-kpi-val'>{avg_pos:.1f}</div>
            <div class='ct-kpi-sub'>across {len(movement_rows)} tracked artists · {time_range}</div>
          </div>
        </div>
        """
        st.markdown(kpi_html, unsafe_allow_html=True)


    # Brighter palette for charts matching screenshot style more closely
    BRIGHT_PALETTE = ["#3b82f6", "#8b5cf6", "#ef4444", "#ec4899", "#10b981",
                      "#d97706", "#65a30d", "#737373", "#e11d48", "#0f766e"]

    is_dark = st.session_state.get("dark_mode", True)
    
    import json
    unique_dates = line_df["date"].dt.strftime("%b %d").unique().tolist()
    start_date_str = unique_dates[0] if unique_dates else ""
    end_date_str = unique_dates[-1] if unique_dates else ""
    datasets = []
    
    for idx, artist in enumerate(artists_tracked):
        sub = line_df[line_df["artist"] == artist]
        date_pos = dict(zip(sub["date"].dt.strftime("%b %d"), sub["position"]))
        data_points = [date_pos.get(d, None) for d in unique_dates]
        color = BRIGHT_PALETTE[idx % len(BRIGHT_PALETTE)]
        datasets.append({
            "label": artist,
            "data": data_points,
            "borderColor": color,
            "backgroundColor": color,
            "pointBackgroundColor": color,
            "pointBorderColor": "#1c1c1c" if is_dark else "#ffffff",
            "pointRadius": 4,
            "pointHoverRadius": 6,
            "borderWidth": 2.5,
            "tension": 0.4 if view_mode != "Area Chart" else 0.0,
            "fill": "origin" if view_mode == "Area Chart" else False,
            "spanGaps": True
        })

    # Calculate dynamic heights to prevent extra blank space
    dynamic_chart_height = 450
    # Legend wraps, approx 40px per row of ~6 artists, plus ~130px for headers/padding
    legend_height = ((num_artists // 6) + 1) * 40
    dynamic_iframe_height = dynamic_chart_height + legend_height + 130

    chart_payload = {
        "labels": unique_dates,
        "datasets": datasets,
        "title": f"📈 Top {num_artists} artist position trend",
        "theme": "dark" if is_dark else "light",
    }
    
    chart_payload_json = json.dumps(chart_payload)
    
    html_template = f"""
    <!DOCTYPE html><html><head><meta charset='utf-8'>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
    <style>
      body {{ margin: 0; font-family: 'Inter', system-ui, sans-serif; background: transparent; }}
      .chart-card {{
        background: {'#1c1c1c' if is_dark else '#ffffff'};
        border: 1px solid {'rgba(255,255,255,0.08)' if is_dark else 'rgba(0,0,0,0.1)'};
        border-radius: 12px;
        padding: 24px 28px;
        color: {'#ffffff' if is_dark else '#1f2328'};
        box-shadow: 0 8px 30px rgba(0,0,0,0.15);
      }}
      .hdr {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }}
      .title {{ font-size: 19px; font-weight: 600; margin-bottom: 6px; letter-spacing: -0.2px; }}
      .subtitle {{ font-size: 13.5px; color: {'#9B9EAA' if is_dark else '#656d76'}; font-weight: 400; }}
      .btn {{
        background: transparent;
        border: 1px solid {'rgba(255,255,255,0.2)' if is_dark else 'rgba(0,0,0,0.2)'};
        color: {'#e2e8f0' if is_dark else '#24292f'};
        padding: 7px 16px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: 0.2s;
      }}
      .btn:hover {{ background: {'rgba(255,255,255,0.08)' if is_dark else 'rgba(0,0,0,0.05)'}; }}
      .legend-container {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 28px; }}
      .leg-btn {{
        background: transparent;
        border: 1px solid {'rgba(255,255,255,0.2)' if is_dark else 'rgba(0,0,0,0.2)'};
        color: {'#e2e8f0' if is_dark else '#24292f'};
        border-radius: 999px;
        padding: 5px 14px;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-size: 12.5px;
        font-weight: 500;
        cursor: pointer;
        transition: 0.2s;
      }}
      .leg-btn:hover {{ border-color: {'rgba(255,255,255,0.4)' if is_dark else 'rgba(0,0,0,0.4)'}; background: {'rgba(255,255,255,0.04)' if is_dark else 'rgba(0,0,0,0.02)'}; }}
      .leg-btn.hidden {{ opacity: 0.4; border-color: transparent; }}
      .dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
      .chart-wrap {{ position: relative; height: {dynamic_chart_height}px; width: 100%; }}
    </style>
    </head><body>
      <div class="chart-card">
        <div class="hdr">
          <div>
            <div class="title" id="d-title"></div>
            <div class="subtitle" id="d-subtitle"></div>
          </div>
        </div>
        <div class="legend-container" id="legend"></div>
        <div class="chart-wrap">
          <canvas id="myChart"></canvas>
        </div>
      </div>
      <script>
        const payload = {chart_payload_json};
        document.getElementById('d-title').innerText = payload.title;
        document.getElementById('d-subtitle').innerText = "Visual tracking of daily rank movement and chart stability for the top-performing artists in the selected window.";
        
        const isDark = payload.theme === 'dark';
        const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
        const tickColor = isDark ? '#8b949e' : '#656d76';
        
        const ctx = document.getElementById('myChart').getContext('2d');
        const myChart = new Chart(ctx, {{
          type: 'line',
          data: {{
            labels: payload.labels,
            datasets: payload.datasets
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            interaction: {{ mode: 'index', intersect: false }},
            plugins: {{
              legend: {{ display: false }},
              tooltip: {{
                backgroundColor: isDark ? 'rgba(28,28,30,0.95)' : 'rgba(255,255,255,0.95)',
                titleColor: isDark ? '#fff' : '#24292f',
                bodyColor: isDark ? '#e2e8f0' : '#475569',
                borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
                borderWidth: 1,
                padding: 12,
                titleFont: {{ size: 13, weight: 'bold' }},
                bodyFont: {{ size: 13 }},
                boxPadding: 6,
                callbacks: {{
                  label: function(context) {{
                    return context.dataset.label + ': #' + context.parsed.y;
                  }}
                }}
              }}
            }},
            scales: {{
              y: {{
                reverse: true,
                grid: {{ color: gridColor, drawBorder: false }},
                ticks: {{
                  color: tickColor,
                  callback: function(val) {{ return val === 0 ? '' : '' + val; }},
                  stepSize: 1,
                  font: {{ size: 11.5 }}
                }},
                title: {{
                  display: true,
                  text: 'Movement Chart for the Artist',
                  color: tickColor,
                  font: {{ size: 12.5, weight: '500' }},
                  padding: {{ bottom: 10 }}
                }},
                min: 0
              }},
              x: {{
                grid: {{ color: gridColor, drawBorder: false }},
                ticks: {{ color: tickColor, font: {{ size: 11.5 }} }}
              }}
            }}
          }}
        }});

        let highlightedIndex = null;

        function renderLegend() {{
          const leg = document.getElementById('legend');
          leg.innerHTML = '';
          myChart.data.datasets.forEach((ds, i) => {{
            if (!ds.originalBorderColor) {{
               ds.originalBorderColor = ds.borderColor;
               ds.originalBackgroundColor = ds.backgroundColor;
            }}
            const isOtherHighlighted = highlightedIndex !== null && highlightedIndex !== i;
            
            const btn = document.createElement('button');
            btn.className = 'leg-btn' + (isOtherHighlighted ? ' hidden' : '');
            btn.onclick = () => {{
              if (highlightedIndex === i) {{
                highlightedIndex = null; // Toggle off
              }} else {{
                highlightedIndex = i; // Highlight this one
              }}
              
              myChart.data.datasets.forEach((dataset, j) => {{
                if (highlightedIndex === null) {{
                   dataset.borderWidth = 2.5;
                   dataset.borderColor = dataset.originalBorderColor;
                   dataset.backgroundColor = dataset.originalBackgroundColor;
                   dataset.order = j;
                }} else if (highlightedIndex === j) {{
                   dataset.borderWidth = 4;
                   dataset.borderColor = dataset.originalBorderColor;
                   dataset.backgroundColor = dataset.originalBackgroundColor;
                   dataset.order = -1; // Draw on top
                }} else {{
                   dataset.borderWidth = 1.5;
                   // Add transparency (33 in hex is ~20% opacity)
                   dataset.borderColor = dataset.originalBorderColor + '33';
                   dataset.backgroundColor = dataset.originalBackgroundColor + '11';
                   dataset.order = j;
                }}
              }});
              myChart.update();
              renderLegend();
            }};
            btn.innerHTML = `<span class="dot" style="background: ${{ds.originalBorderColor}}"></span> ${{ds.label}}`;
            leg.appendChild(btn);
          }});
        }}

        let allHidden = false;
        function toggleAll() {{
          allHidden = !allHidden;
          myChart.data.datasets.forEach((ds, i) => {{
            const meta = myChart.getDatasetMeta(i);
            meta.hidden = allHidden;
          }});
          myChart.update();
          renderLegend();
        }}

        renderLegend();
      </script>
    </body></html>
    """
    st_components.html(html_template, height=dynamic_iframe_height)
    st.markdown("</div>", unsafe_allow_html=True)

    text_color = "#fff" if is_dark else "#1A1A1A"
    tick_color = "#cdd6e4" if is_dark else "#4A5568"

    if not best_df.empty:
        best_df_plot = best_df.copy()
        max_best_position = int(best_df_plot["best_position"].max())
        best_df_plot["position_score"] = max_best_position + 1 - best_df_plot["best_position"]
        max_position_score = max(float(best_df_plot["position_score"].max()), 1.0)
        best_df_plot["position_strength"] = (best_df_plot["position_score"] / max_position_score * 7800).round(0)
        best_df_plot = best_df_plot.sort_values("best_position", ascending=True)
        best_df_plot["artist_tick"] = best_df_plot["artist"].map(
            lambda v: v if len(str(v)) <= 20 else f"{str(v)[:18]}..."
        )

        st.markdown(
            """
            <div class='ct-chart-note'>
              <div class='ct-chart-note-title'>🏆 Best Recent Positions</div>
              <div class='ct-chart-note-copy'>
                This chart highlights each artist's strongest chart rank within the selected time window.
                A longer bar means a stronger recent peak position. Hover over any bar to see the actual best rank reached.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        blue_scale = [
            "#0f5ea8", "#1469b6", "#1d76c8", "#2f86d8", "#4299e8",
            "#5aa8ee", "#73b6f2", "#8bc3f6", "#9cccf8", "#add6fb",
        ]
        bar_colors = [blue_scale[min(idx, len(blue_scale) - 1)] for idx in range(len(best_df_plot))]
        fig_best = go.Figure(
            data=[
                go.Bar(
                    x=best_df_plot["position_strength"],
                    y=best_df_plot["artist"],
                    orientation="h",
                    marker=dict(color=bar_colors, line=dict(width=0)),
                    cliponaxis=False,
                    customdata=best_df_plot[["artist", "best_position"]].to_numpy(),
                    hovertemplate="<b>%{customdata[0]}</b><br>Best recent rank: #%{customdata[1]}<br>Position strength: %{x:,.0f}<extra></extra>",
                )
            ]
        )
        style_figure(fig_best, max(380, 34 * len(best_df) + 80), dark_mode=is_dark)
        try:
            fig_best.update_traces(marker_cornerradius=4)
        except Exception:  # noqa: BLE001
            pass
        fig_best.update_layout(
            title=dict(text="", x=0.03, xanchor="left", font=dict(size=18, color=text_color)),
            showlegend=False,
            yaxis_title="",
            margin=dict(l=134, r=24, t=8, b=46),
            bargap=0.28,
        )
        fig_best.update_xaxes(
            dtick=1000,
            showgrid=True,
            range=[0, 8200],
            showticklabels=True,
            tickformat=",",
            title=dict(text="Position strength score", font=dict(color=tick_color, size=11)),
        )
        fig_best.update_yaxes(
            autorange="reversed",
            categoryorder="array",
            categoryarray=best_df_plot["artist"].tolist(),
            tickmode="array",
            tickvals=best_df_plot["artist"].tolist(),
            ticktext=best_df_plot["artist_tick"].tolist(),
            ticklabelstandoff=10,
            tickfont=dict(color=text_color, size=12),
        )
        render_plotly_html(fig_best)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Styled HTML movement table (replaces st.dataframe) ───────────
        if movement_rows:
            # Sort by 'current' position ascending (best rank first)
            movement_rows_sorted = sorted(movement_rows, key=lambda r: r["current"])
            rows_html = []
            for r in movement_rows_sorted:
                ch = r["change"]
                if ch > 0:
                    pill = f"<span class='ct-pill ct-pill-up'>▲ +{ch}</span>"
                    trend = "<span style='color:#34d399;font-weight:600'>📈 Rising</span>"
                elif ch < 0:
                    pill = f"<span class='ct-pill ct-pill-down'>▼ {abs(ch)}</span>"
                    trend = "<span style='color:#fb7185;font-weight:600'>📉 Falling</span>"
                else:
                    pill = "<span class='ct-pill ct-pill-flat'>—</span>"
                    trend = "<span style='color:var(--text2);font-weight:600'>➡️ Stable</span>"
                rows_html.append(
                    f"<tr><td class='ct-artist'>{escape(r['artist'])}</td>"
                    f"<td class='ct-rank-cell'>{r['start']}</td>"
                    f"<td class='ct-rank-cell'>{r['current']}</td>"
                    f"<td class='ct-rank-cell'>{r['best']}</td>"
                    f"<td>{pill}</td>"
                    f"<td>{trend}</td></tr>"
                )
            table_html = (
                 "<div class='ct-section'>"
                 "<div class='ct-section-ttl'>📊 Detailed Movement Analysis</div>"
                 "<div class='ct-section-desc'>This table shows tracks with significant movement in their chart positions, displaying starting position, current position, best position achieved, change in rank, and movement trend (rising/falling/stable).</div>"
                 "<table class='ct-mv-tbl'><thead><tr>"
                "<th>Artist</th><th>Start</th><th>Current</th><th>Best</th><th>Change</th><th>Trend</th>"
                "</tr></thead><tbody>"
                + "".join(rows_html)
                + "</tbody></table></div>"
            )
            st.markdown(table_html, unsafe_allow_html=True)

            movement_df = pd.DataFrame([
                {
                    "Artist": r["artist"],
                    "Starting Position": r["start"],
                    "Current Position": r["current"],
                    "Best Position": r["best"],
                    "Change": (f"+{r['change']}" if r["change"] > 0 else str(r["change"])),
                    "Trend": ("Rising" if r["change"] > 0 else "Falling" if r["change"] < 0 else "Stable"),
                }
                for r in movement_rows_sorted
            ])
            st.download_button(
                "⬇️ Download Detailed Movement Analysis",
                data=movement_df.to_csv(index=False).encode("utf-8"),
                file_name="detailed_movement_analysis.csv",
                mime="text/csv",
                key="download_detailed_movement_analysis",
            )
