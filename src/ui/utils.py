import plotly.graph_objects as go
from src.scrapers.artist_details_scraper import LATIN_AMERICAN_COUNTRIES

CHART_COLORS = ["#4f8ef7", "#22d3a0", "#f5a623", "#7c5cfc", "#e84545", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#a855f7"]
PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}
TRACKER_TOP_ARTISTS = 10
LATAM_COUNTRIES = sorted(LATIN_AMERICAN_COUNTRIES)
LOAD_TIMEOUT_MS = 20000

def style_figure(fig, height: int) -> None:
    fig.update_layout(
        template="plotly_dark",
        height=max(280, int(height)),
        autosize=True,
        margin=dict(l=0, r=0, t=56, b=0, pad=0),
        paper_bgcolor="rgba(18,24,42,1)",
        plot_bgcolor="rgba(18,24,42,1)",
        font=dict(color="#e8eaf6"),
        legend_title_text="",
        title=dict(x=0.03, xanchor="left", font=dict(size=16, color="#eef2ff")),
        hoverlabel=dict(
            bgcolor="rgba(9,17,39,.96)",
            bordercolor="rgba(79,142,247,.45)",
            font=dict(color="#eef2ff"),
        ),
    )
    fig.update_xaxes(
        gridcolor="rgba(151,163,197,.12)",
        zerolinecolor="rgba(151,163,197,.12)",
        tickfont=dict(size=11),
        title_font=dict(size=12),
    )
    fig.update_yaxes(
        gridcolor="rgba(151,163,197,.12)",
        zerolinecolor="rgba(151,163,197,.12)",
        tickfont=dict(size=11),
        title_font=dict(size=12),
    )
