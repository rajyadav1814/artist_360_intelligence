"""Artist Spotlight dashboard rendering and data loading."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src.database.connection import get_connection
from src.utils.image_utils import get_artist_image_url, get_fallback_avatar_url
from src.utils.ui import custom_selectbox


@st.cache_data(ttl=300)
def load_artist_spotlight_daily(artist_name: str) -> dict[str, pd.DataFrame]:
    """Load recent daily rows used by the interactive Artist Spotlight dashboard."""
    empty = {
        "spotify_daily": pd.DataFrame(),
        "itunes_daily": pd.DataFrame(),
        "itunes_album": pd.DataFrame(),
    }
    if not artist_name:
        return empty

    like_prefix = f"{artist_name} - %"
    queries = {
        "spotify_daily": """
            SELECT date, country, rank, artist_title, days, peak, streams,
                   streams_change, total_streams, label, rank_change
            FROM spotify_daily
            WHERE artist_title ILIKE %s OR artist_title ILIKE %s
            ORDER BY date ASC, rank ASC
        """,
        "itunes_daily": """
            SELECT date, country, rank, artist_title, days, peak, points,
                   points_change, total_points, label, rank_change
            FROM itunes_daily
            WHERE artist_title ILIKE %s OR artist_title ILIKE %s
            ORDER BY date ASC, rank ASC
        """,
        "itunes_album": """
            SELECT date, country, rank, artist_title, days, peak, points,
                   points_change, total_points, label, rank_change
            FROM itunes_artist_album
            WHERE artist_title ILIKE %s OR artist_title ILIKE %s
            ORDER BY date ASC, rank ASC
        """,
    }

    frames: dict[str, pd.DataFrame] = {}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for key, sql in queries.items():
                try:
                    cur.execute(sql, (artist_name, like_prefix))
                    frames[key] = pd.DataFrame([dict(row) for row in cur.fetchall()])
                except Exception:
                    conn.rollback()
                    frames[key] = pd.DataFrame()
    finally:
        conn.close()

    for df in frames.values():
        if not df.empty and "date" in df:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return {**empty, **frames}



def render_debut_artist_chart(leaderboard: pd.DataFrame) -> None:
    if leaderboard.empty:
        st.warning("No artist data available yet.")
        return

    sorted_artists = leaderboard.sort_values("rank").dropna(subset=["name", "rank"]).copy()
    sorted_artists["display_label"] = sorted_artists["name"].astype(str)
    artist_options = sorted_artists["display_label"].tolist()

    default_artist = st.session_state.get("global_selected_artist", "All artists")
    if default_artist == "All artists" and artist_options:
        default_artist = artist_options[0]
    default_idx = artist_options.index(default_artist) if default_artist in artist_options else 0

    selected_label = custom_selectbox(
        "Select an Artist",
        artist_options,
        index=default_idx if artist_options else 0,
        key="debut_artist_select",
    )

    if selected_label != st.session_state.get("global_selected_artist"):
        st.session_state.global_selected_artist = selected_label
        st.rerun()

    if not selected_label:
        st.info("Please select an artist from the dropdown above.")
        return

    selected_artist = selected_label.split(" - ", 1)[1] if " - " in selected_label else selected_label
    artist_data = leaderboard[leaderboard["name"] == selected_artist]
    if artist_data.empty:
        st.warning(f"No data found for {selected_artist}.")
        return

    row = artist_data.iloc[0]
    daily = load_artist_spotlight_daily(str(row.get("name") or ""))
    sp_daily = daily["spotify_daily"].copy()
    it_daily = daily["itunes_daily"].copy()
    album_daily = daily["itunes_album"].copy()

    def safe_int(value, default: int = 0) -> int:
        return default if value is None or pd.isna(value) else int(float(value))

    def split_items(value) -> list[str]:
        return [item.strip() for item in str(value or "").split("\n") if item.strip()]

    def clean_title(title: str, artist: str) -> str:
        prefix = f"{artist} - "
        return title[len(prefix):] if title.lower().startswith(prefix.lower()) else title

    def date_label(value) -> str:
        parsed = pd.to_datetime(value, errors="coerce")
        return parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else ""

    def aggregate_timeline(df: pd.DataFrame, value_col: str) -> list[dict]:
        if df.empty or value_col not in df:
            return []
        work = df.dropna(subset=["date"]).copy()
        if work.empty:
            return []
        grouped = (
            work.groupby("date", as_index=False)
            .agg(value=(value_col, "sum"), rank=("rank", "min"))
            .sort_values("date")
        )
        return [
            {"date": date_label(item["date"]), "value": safe_int(item["value"]), "rank": safe_int(item["rank"])}
            for _, item in grouped.iterrows()
        ]

    def aggregate_songs(df: pd.DataFrame, value_col: str, change_col: str | None = None) -> list[dict]:
        if df.empty or value_col not in df:
            return []
        work = df.copy()
        work[value_col] = pd.to_numeric(work[value_col], errors="coerce").fillna(0)
        if change_col and change_col in work:
            work[change_col] = pd.to_numeric(work[change_col], errors="coerce").fillna(0)
        grouped = (
            work.groupby("artist_title", as_index=False)
            .agg(
                value=(value_col, "max"),
                peak_rank=("peak", "min"),
                days_on_chart=("days", "max"),
                first_seen=("date", "min"),
                last_seen=("date", "max"),
                regions=("country", "nunique"),
                change=(change_col, "sum") if change_col and change_col in work else (value_col, "sum"),
            )
            .sort_values("value", ascending=False)
            .head(10)
        )
        return [
            {
                "song": clean_title(str(item["artist_title"]), str(row.get("name") or "")),
                "value": safe_int(item["value"]),
                "peak_rank": safe_int(item["peak_rank"]),
                "days_on_chart": safe_int(item["days_on_chart"]),
                "first_seen": date_label(item["first_seen"]),
                "last_seen": date_label(item["last_seen"]),
                "regions": safe_int(item["regions"]),
                "change": safe_int(item["change"]),
            }
            for _, item in grouped.iterrows()
        ]

    sp_timeline = aggregate_timeline(sp_daily, "streams")
    it_timeline = aggregate_timeline(it_daily, "points")
    sp_songs = aggregate_songs(sp_daily, "total_streams" if "total_streams" in sp_daily else "streams", "streams_change")
    it_songs = aggregate_songs(it_daily, "total_points" if "total_points" in it_daily else "points", "points_change")
    albums = aggregate_songs(album_daily, "total_points" if "total_points" in album_daily else "points", "points_change")

    fallback_songs = split_items(row.get("top_songs"))
    if not sp_songs and fallback_songs:
        sp_songs = [{"song": item, "value": 0, "peak_rank": 0, "days_on_chart": 0, "regions": 0, "change": 0} for item in fallback_songs[:8]]
    fallback_albums = split_items(row.get("top_albums"))
    if not albums and fallback_albums:
        albums = [{"song": item, "value": 0, "peak_rank": 0, "days_on_chart": 0, "regions": 0, "change": 0} for item in fallback_albums[:6]]

    trend_raw = str(row.get("rank_change") or "=").strip()
    countries = split_items(row.get("top_countries"))
    if not countries and str(row.get("display_country") or "—") != "—":
        countries = [str(row.get("display_country"))]

    payload = {
        "name": str(row.get("name") or "—"),
        "image": get_artist_image_url(row["name"]) or get_fallback_avatar_url(row["name"]),
        "label": str(row.get("page_title") or row.get("top_country") or "Global chart artist"),
        "rank": safe_int(row.get("rank")),
        "rankChange": trend_raw,
        "primaryMarket": str(row.get("display_country") or row.get("top_country") or "Global"),
        "followers": safe_int(row.get("peak_listeners")),
        "monthlyListeners": safe_int(row.get("monthly_listeners")),
        "spotifySongsCount": safe_int(row.get("songs_count"), len(sp_songs)),
        "itunesSongsCount": len(it_songs),
        "albumsCount": safe_int(row.get("albums_count"), len(albums)),
        "countriesCount": len(countries),
        "countries": countries,
        "totalStreams": sum(item["value"] for item in sp_timeline) or sum(item["value"] for item in sp_songs),
        "totalItunesSales": sum(item["value"] for item in it_timeline) or sum(item["value"] for item in it_songs),
        "bestSpotifyRank": min([item["rank"] for item in sp_timeline if item["rank"]] or [0]),
        "bestItunesRank": min([item["rank"] for item in it_timeline if item["rank"]] or [safe_int(row.get("rank"))]),
        "totalPoints": safe_int(row.get("total_points")),
        "spotifyTimeline": sp_timeline,
        "itunesTimeline": it_timeline,
        "spotifySongs": sp_songs,
        "itunesSongs": it_songs,
        "albums": albums,
    }

    data_json = json.dumps(payload, ensure_ascii=False)
    theme_json = json.dumps({"dark": st.session_state.get("dark_mode", True)})
    html = """
<div class="dash" id="dash">
  <div id="spotlight"></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const DATA = __DATA__;
const THEME = __THEME__;
const COLORS = ['#1D9E75','#185FA5','#8B5CF6','#E24B4A','#BA7517','#0891B2'];
let charts = {};
const color = COLORS[Math.max(0, DATA.rank - 1) % COLORS.length];

function esc(v){return String(v ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function fmt(n){n=Number(n||0); if(!n) return '—'; if(Math.abs(n)>=1e9)return(n/1e9).toFixed(1)+'B'; if(Math.abs(n)>=1e6)return(n/1e6).toFixed(1)+'M'; if(Math.abs(n)>=1e3)return(n/1e3).toFixed(1)+'K'; return n.toLocaleString();}
function trendIcon(v){v=Number(v||0); return v>0?'<span class="trend-up">↑</span>':v<0?'<span class="trend-dn">↓</span>':'<span class="trend-neu">→</span>';}
function destroyCharts(){Object.values(charts).forEach(c=>{try{c.destroy()}catch(e){}}); charts={};}
function chartText(){return THEME.dark ? '#cdd6e4' : '#475569';}
function gridColor(){return THEME.dark ? 'rgba(255,255,255,0.08)' : 'rgba(15,23,42,0.08)';}
function noData(label){return `<div class="empty">${esc(label)}</div>`;}
function changeCopy(v){
  const token=String(v||'=').trim();
  if(token.toUpperCase()==='NEW')return 'New chart entry';
  const n=Number(token.replace('+',''));
  if(!isNaN(n) && n>0)return `Up ${n} positions`;
  if(!isNaN(n) && n<0)return `Down ${Math.abs(n)} positions`;
  return 'Stable rank';
}
function signalClass(v){
  const token=String(v||'=').trim();
  if(token.toUpperCase()==='NEW')return 'signal-new';
  const n=Number(token.replace('+',''));
  if(!isNaN(n) && n>0)return 'signal-up';
  if(!isNaN(n) && n<0)return 'signal-down';
  return 'signal-flat';
}

function rows(items, valueLabel){
  if(!items.length) return `<tr><td colspan="4" class="empty-cell">No ${esc(valueLabel)} data for this period</td></tr>`;
  return items.map(s=>{
    return `<tr>
      <td><span class="rank-pill" style="background:${color}22;color:${color}">${s.peak_rank ? '#'+s.peak_rank : '—'}</span></td>
      <td class="song-name">${esc(s.song)}</td>
      <td>${esc(s.regions || '—')}</td>
      <td>${trendIcon(s.change)} ${s.change ? fmt(Math.abs(s.change)) : '—'}</td>
    </tr>`;
  }).join('');
}

function buildLine(id, items, label, metric, chartColor, reverse=false){
  const el=document.getElementById(id);
  if(!el || !items.length) return;
  const values=items.map(d=>reverse ? d.rank : d.value);
  const maxRank=Math.max(...values, 10) + 4;
  charts[id]=new Chart(el,{type:'line',data:{labels:items.map(d=>d.date.slice(5)),datasets:[{label,data:values,borderColor:chartColor,backgroundColor:chartColor+'22',fill:true,tension:.38,pointRadius:2,borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>reverse?'Rank #'+c.parsed.y:fmt(c.parsed.y)+' '+metric}}},scales:{x:{grid:{display:false},ticks:{color:chartText(),font:{size:10},maxRotation:0}},y:{reverse,min:reverse?1:undefined,max:reverse?maxRank:undefined,grid:{color:gridColor()},ticks:{color:chartText(),font:{size:10},callback:v=>reverse?'#'+v:fmt(v)}}}}});
}

function buildBar(id, items, label, chartColor){
  const el=document.getElementById(id);
  if(!el || !items.length) return;
  charts[id]=new Chart(el,{type:'bar',data:{labels:items.map(d=>d.date.slice(5)),datasets:[{label,data:items.map(d=>d.value),backgroundColor:chartColor+'44',borderColor:chartColor,borderWidth:1.5,borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{color:chartText(),font:{size:10},maxRotation:0,autoSkip:true,maxTicksLimit:8}},y:{grid:{color:gridColor()},ticks:{color:chartText(),font:{size:10},callback:v=>fmt(v)}}}}});
}

function buildAlbums(){
  const el=document.getElementById('albumChart');
  if(!el || !DATA.albums.length) return;
  charts.albumChart=new Chart(el,{type:'bar',data:{labels:DATA.albums.map(a=>a.song),datasets:[{data:DATA.albums.map(a=>a.value || 1),backgroundColor:'#185FA555',borderColor:'#185FA5',borderWidth:1.5,borderRadius:4}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{display:false},y:{grid:{display:false},ticks:{color:chartText(),font:{size:11}}}}}});
}

function activeTab(panel){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.panel===panel));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id==='panel-'+panel));
  destroyCharts();
  if(panel==='streams'){buildLine('spStreamChart', DATA.spotifyTimeline, 'Streams', 'streams', color); buildBar('itSalesChart', DATA.itunesTimeline, 'Sales', '#185FA5');}
  if(panel==='ranks'){buildLine('spRankChart', DATA.spotifyTimeline, 'Spotify rank', 'rank', color, true); buildLine('itRankChart', DATA.itunesTimeline, 'iTunes rank', 'rank', '#185FA5', true);}
  if(panel==='itunes') buildAlbums();
}

function render(){
  const countries = DATA.countries.length ? DATA.countries.map(c=>`<span class="country-pill">${esc(c)}</span>`).join('') : '<span class="muted">Global presence</span>';
  const marketLabel = DATA.primaryMarket && DATA.primaryMarket !== '—' ? DATA.primaryMarket : 'Global';
  const rankText = DATA.rank ? `#${esc(DATA.rank)}` : '—';
  document.getElementById('spotlight').innerHTML = `
    <div class="header">
      <img class="avatar" src="${esc(DATA.image)}" alt="${esc(DATA.name)}">
      <div class="head-copy">
        <div class="eyebrow">Artist Spotlight</div>
        <div class="artist-name">${esc(DATA.name)}</div>
        <div class="artist-meta">${esc(DATA.label)}</div>
        <div class="badges">
          <span class="badge badge-rank">Current rank ${rankText}</span>
          <span class="badge ${signalClass(DATA.rankChange)}">${changeCopy(DATA.rankChange)}</span>
          <span class="badge badge-world">${esc(marketLabel)}</span>
        </div>
      </div>
    </div>
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-head"><span class="summary-icon audience-icon">◉</span><div class="summary-label">Audience</div></div>
        <div class="summary-value">${fmt(DATA.monthlyListeners)}</div>
        <div class="summary-note">Monthly listeners with ${fmt(DATA.followers)} peak listener history.</div>
      </div>
      <div class="summary-card">
        <div class="summary-head"><span class="summary-icon catalog-icon">♪</span><div class="summary-label">Catalog Signal</div></div>
        <div class="summary-value">${esc(DATA.spotifySongsCount)} songs · ${esc(DATA.albumsCount)} albums</div>
        <div class="summary-note">Active chart footprint across Spotify, iTunes songs, and albums.</div>
      </div>
      <div class="summary-card">
        <div class="summary-head"><span class="summary-icon market-icon">◆</span><div class="summary-label">Market Reach</div></div>
        <div class="summary-value">${esc(DATA.countriesCount || '—')} markets</div>
        <div class="summary-note">Primary market: ${esc(marketLabel)}.</div>
      </div>
    </div>
    <div class="kpi-grid">
      <div class="kpi"><div class="kpi-label"><span class="ico">◉</span> Peak listeners</div><div class="kpi-val">${fmt(DATA.followers)}</div><div class="kpi-sub">Highest observed audience</div></div>
      <div class="kpi"><div class="kpi-label"><span class="ico">◌</span> Monthly listeners</div><div class="kpi-val">${fmt(DATA.monthlyListeners)}</div><div class="kpi-sub">Current Spotify audience</div></div>
      <div class="kpi"><div class="kpi-label"><span class="ico">≋</span> Stream signal</div><div class="kpi-val">${fmt(DATA.totalStreams)}</div><div class="kpi-sub">Recent Spotify volume</div></div>
      <div class="kpi kpi-rank"><div class="kpi-label"><span class="ico">#</span> Artist rank</div><div class="kpi-val" style="color:${color}">${rankText}</div><div class="kpi-sub">${changeCopy(DATA.rankChange)}</div></div>
      <div class="kpi"><div class="kpi-label"><span class="ico">◆</span> iTunes points</div><div class="kpi-val">${fmt(DATA.totalItunesSales || DATA.totalPoints)}</div><div class="kpi-sub">Best rank #${esc(DATA.bestItunesRank || DATA.rank)}</div></div>
      <div class="kpi"><div class="kpi-label"><span class="ico">◎</span> Market reach</div><div class="kpi-val">${esc(DATA.countriesCount || '—')}</div><div class="kpi-sub">Tracked LATAM markets</div></div>
    </div>
    <div style="--accent:${color}">
      <div class="tabs">
        <button class="tab active" data-panel="streams"><span class="ico">▰</span> Streams</button>
        <button class="tab" data-panel="ranks"><span class="ico">↕</span> Rank Trend</button>
        <button class="tab" data-panel="songs"><span class="ico">♪</span> Song Deep Dive</button>
        <button class="tab" data-panel="itunes"><span class="ico">◆</span> iTunes Detail</button>
      </div>
      <div id="panel-streams" class="panel active">
        <div class="two-col">
          <div class="card"><div class="sec-title"><span class="ico">▰</span> Daily streams · Spotify global</div><div class="sec-desc">Daily Spotify stream volume across the current tracking window, showing short-term demand shifts.</div>${DATA.spotifyTimeline.length?'<div class="chart-wrap"><canvas id="spStreamChart"></canvas></div>':noData('No Spotify daily rows found for this artist.')}</div>
          <div class="card"><div class="sec-title"><span class="ico">▥</span> Daily sales · iTunes worldwide</div><div class="sec-desc">Worldwide iTunes sales points by date, highlighting purchase-driven momentum during the same period.</div>${DATA.itunesTimeline.length?'<div class="chart-wrap"><canvas id="itSalesChart"></canvas></div>':noData('No iTunes daily rows found for this artist.')}</div>
        </div>
      </div>
      <div id="panel-ranks" class="panel">
        <div class="two-col">
          <div class="card"><div class="sec-title"><span class="ico">↕</span> Spotify chart rank over time <span>(lower = better)</span></div><div class="sec-desc">Best daily Spotify chart position for the artist, inverted so upward movement means a stronger rank.</div>${DATA.spotifyTimeline.length?'<div class="chart-wrap"><canvas id="spRankChart"></canvas></div>':noData('No Spotify rank history found.')}</div>
          <div class="card"><div class="sec-title"><span class="ico">↕</span> iTunes chart rank over time <span>(lower = better)</span></div><div class="sec-desc">Daily iTunes rank trajectory, useful for spotting sales spikes and post-release rank stability.</div>${DATA.itunesTimeline.length?'<div class="chart-wrap"><canvas id="itRankChart"></canvas></div>':noData('No iTunes rank history found.')}</div>
        </div>
      </div>
      <div id="panel-songs" class="panel">
        <div class="two-col">
          <div class="card"><div class="sec-title"><span class="ico">♪</span> Spotify song performance</div><div class="sec-desc">Tracks with the strongest Spotify footprint, summarized by peak rank, market coverage, and recent change.</div><div class="table-scroll"><table class="song-table"><thead><tr><th><span class="ico">#</span> Peak</th><th><span class="ico">♪</span> Song</th><th><span class="ico">◎</span> Regions</th><th><span class="ico">↕</span> Change</th></tr></thead><tbody>${rows(DATA.spotifySongs,'Spotify song')}</tbody></table></div></div>
          <div class="card"><div class="sec-title"><span class="ico">♪</span> iTunes song performance</div><div class="sec-desc">Songs charting on iTunes worldwide, focused on peak performance, regions, and latest movement.</div><div class="table-scroll"><table class="song-table"><thead><tr><th><span class="ico">#</span> Peak</th><th><span class="ico">♪</span> Song</th><th><span class="ico">◎</span> Regions</th><th><span class="ico">↕</span> Change</th></tr></thead><tbody>${rows(DATA.itunesSongs,'iTunes song')}</tbody></table></div></div>
        </div>
      </div>
      <div id="panel-itunes" class="panel">
        <div class="two-col">
          <div class="card"><div class="sec-title"><span class="ico">▣</span> Albums on iTunes</div><div class="sec-desc">Album-level iTunes activity ranked by the strongest available charting signal for this artist.</div>${DATA.albums.length?'<div class="chart-wrap tall"><canvas id="albumChart"></canvas></div>':noData('No iTunes album rows found.')}</div>
          <div class="card"><div class="sec-title"><span class="ico">◎</span> Top markets</div><div class="sec-desc">Country and catalog coverage showing where the artist has the broadest chart presence.</div><div class="countries">${countries}</div><div class="market-lines"><div><span><span class="ico">▶</span> Spotify songs</span><strong>${esc(DATA.spotifySongsCount)}</strong></div><div><span><span class="ico"></span> iTunes songs</span><strong>${esc(DATA.itunesSongsCount)}</strong></div><div><span><span class="ico">▣</span> Albums</span><strong>${esc(DATA.albumsCount)}</strong></div></div></div>
        </div>
      </div>
    </div>`;
  document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>activeTab(btn.dataset.panel)));
  activeTab('streams');
}
render();
</script>
<style>
*{box-sizing:border-box} html,body{margin:0;background:transparent;overflow-x:hidden}
.dash{--color-background-primary:__BG1__;--color-background-secondary:__BG2__;--color-border-tertiary:__BORDER__;--color-text-primary:__TEXT1__;--color-text-secondary:__TEXT2__;--color-text-tertiary:__TEXT3__;padding:.35rem 0 1rem;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--color-text-primary)}
.header{display:grid;grid-template-columns:116px minmax(0,1fr);align-items:center;gap:1.35rem;margin-bottom:1rem;padding:1.15rem;border:1px solid var(--color-border-tertiary);border-radius:8px;background:var(--color-background-primary)}
.avatar{width:116px;height:116px;border-radius:8px;object-fit:cover;flex-shrink:0;border:1px solid var(--color-border-tertiary);background:var(--color-background-secondary)}
.head-copy{min-width:0}.eyebrow{font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.08em;color:var(--color-text-tertiary);margin-bottom:5px}.artist-name{font-size:36px;font-weight:760;color:var(--color-text-primary);line-height:1.04;letter-spacing:0}.artist-meta{font-size:14px;color:var(--color-text-secondary);margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:760px}
.badges{display:flex;gap:8px;margin-top:13px;flex-wrap:wrap}.badge{display:inline-flex;align-items:center;gap:5px;font-size:12px;padding:6px 11px;border-radius:999px;font-weight:700;border:1px solid var(--color-border-tertiary);background:var(--color-background-secondary);color:var(--color-text-secondary)}.badge-rank{background:rgba(24,95,165,.12);color:#185FA5;border-color:rgba(24,95,165,.32)}.badge-world{background:rgba(139,92,246,.10);color:#8B5CF6;border-color:rgba(139,92,246,.28)}.signal-up{background:rgba(29,158,117,.12);color:#0f8a64;border-color:rgba(29,158,117,.32)}.signal-down{background:rgba(226,75,74,.12);color:#c63a3a;border-color:rgba(226,75,74,.32)}.signal-new{background:rgba(24,95,165,.12);color:#185FA5;border-color:rgba(24,95,165,.32)}.signal-flat{background:var(--color-background-secondary);color:var(--color-text-secondary)}
.summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 1rem}.summary-card{background:var(--color-background-secondary);border:1px solid var(--color-border-tertiary);border-radius:8px;padding:14px 16px;min-width:0}.summary-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}.summary-icon{width:22px;height:22px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;flex:0 0 auto}.audience-icon{background:rgba(29,158,117,.13);color:#1D9E75}.catalog-icon{background:rgba(24,95,165,.13);color:#185FA5}.market-icon{background:rgba(139,92,246,.13);color:#8B5CF6}.summary-label{font-size:11px;text-transform:uppercase;letter-spacing:.07em;font-weight:760;color:var(--color-text-tertiary)}.summary-value{font-size:18px;font-weight:780;color:var(--color-text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.summary-note{font-size:12px;color:var(--color-text-secondary);line-height:1.4;margin-top:5px}
.ico{display:inline-flex;align-items:center;justify-content:center;line-height:1;font-style:normal;font-weight:750;color:var(--accent,#1D9E75)}
.kpi-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin-bottom:1.15rem}.kpi{background:var(--color-background-primary);border:1px solid var(--color-border-tertiary);border-radius:8px;padding:1rem;min-height:112px;min-width:0}.kpi-rank{border-color:rgba(24,95,165,.35)}.kpi-label{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--color-text-secondary);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;font-weight:750}.kpi-val{font-size:28px;font-weight:790;color:var(--color-text-primary);line-height:1.02;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.kpi-sub{font-size:12px;color:var(--color-text-tertiary);margin-top:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tabs{display:flex;gap:8px;margin-bottom:1rem;padding-bottom:11px;border-bottom:1px solid var(--color-border-tertiary);overflow-x:auto}.tab{display:inline-flex;align-items:center;gap:8px;padding:9px 16px 9px 10px;font-size:15px;border:1px solid var(--color-border-tertiary);border-radius:999px;background:var(--color-background-primary);cursor:pointer;color:var(--color-text-secondary);white-space:nowrap;transition:background .15s ease,border-color .15s ease,color .15s ease}.tab .ico{width:25px;height:25px;border-radius:999px;background:var(--color-background-secondary);border:1px solid var(--color-border-tertiary);font-size:12px}.tab.active{color:var(--color-text-primary);font-weight:720;border-color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,var(--color-background-primary))}.tab.active .ico{background:var(--accent);border-color:var(--accent);color:#fff}
.panel{display:none}.panel.active{display:block}.two-col{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;margin-bottom:1rem}.card,.full-card{background:var(--color-background-primary);border:1px solid var(--color-border-tertiary);border-radius:8px;padding:1rem 1.1rem;min-width:0}.full-card{margin-bottom:1rem}.sec-title{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:760;color:var(--color-text-primary);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}.sec-title span:not(.ico){font-size:10px;color:var(--color-text-tertiary);font-weight:500;text-transform:none;letter-spacing:0}.sec-desc{min-height:34px;color:var(--color-text-secondary);font-size:12px;line-height:1.4;margin-bottom:12px}
.chart-wrap{position:relative;height:320px;min-width:0;overflow:hidden}.chart-wrap canvas{max-width:100%!important}.chart-wrap.tall{height:340px}.empty{height:300px;display:flex;align-items:center;justify-content:center;color:var(--color-text-tertiary);font-size:13px;text-align:center}.table-scroll{overflow-x:auto}.song-table{width:100%;border-collapse:collapse;font-size:13px}.song-table th{font-size:11px;font-weight:750;color:var(--color-text-secondary);text-align:left;padding:8px 8px 10px;border-bottom:1px solid var(--color-border-tertiary);white-space:nowrap}.song-table td{padding:10px 8px;border-bottom:1px solid var(--color-border-tertiary);color:var(--color-text-primary);vertical-align:middle;white-space:nowrap}.song-table tr:last-child td{border-bottom:none}.song-table tr:hover td{background:var(--color-background-secondary)}.song-name{max-width:320px;overflow:hidden;text-overflow:ellipsis}.rank-pill{display:inline-block;font-size:11px;padding:3px 8px;border-radius:999px;font-weight:750}.trend-up{color:#1D9E75}.trend-dn{color:#E24B4A}.trend-neu{color:var(--color-text-secondary)}.bar-cell{display:flex;align-items:center;gap:6px}.mini-bar-bg{flex:1;height:4px;background:var(--color-background-secondary);border-radius:2px;min-width:44px}.mini-bar{height:4px;border-radius:2px}.empty-cell{text-align:center;color:var(--color-text-tertiary)!important;padding:18px!important}.country-pill{font-size:12px;padding:6px 10px;border-radius:999px;background:var(--color-background-secondary);color:var(--color-text-secondary);border:1px solid var(--color-border-tertiary);display:inline-block;margin:3px}.muted{color:var(--color-text-tertiary);font-size:13px}.countries{margin-bottom:14px}.market-lines{border-top:1px solid var(--color-border-tertiary);padding-top:12px}.market-lines div{display:flex;justify-content:space-between;font-size:13px;margin-bottom:9px;gap:16px}.market-lines span{color:var(--color-text-secondary)}.market-lines strong{color:var(--color-text-primary);font-weight:780}
@media(max-width:980px){.header{grid-template-columns:96px minmax(0,1fr);align-items:start}.avatar{width:96px;height:96px}.summary-grid{grid-template-columns:1fr}.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.artist-name{font-size:28px}.song-name{max-width:180px}}
@media(max-width:640px){.two-col{grid-template-columns:1fr}}
</style>
"""
    colors = {
        "__BG1__": "#161b26" if st.session_state.get("dark_mode", True) else "#FFFFFF",
        "__BG2__": "#1f2633" if st.session_state.get("dark_mode", True) else "#F8F9FB",
        "__BORDER__": "rgba(148,163,184,.15)" if st.session_state.get("dark_mode", True) else "#E9ECF2",
        "__TEXT1__": "#ffffff" if st.session_state.get("dark_mode", True) else "#1A1A1A",
        "__TEXT2__": "#cdd6e4" if st.session_state.get("dark_mode", True) else "#667085",
        "__TEXT3__": "#8a94a6" if st.session_state.get("dark_mode", True) else "#98A2B3",
    }
    html = html.replace("__DATA__", data_json).replace("__THEME__", theme_json)
    for key, value in colors.items():
        html = html.replace(key, value)
    st_components.html(html, height=1120, width=None, scrolling=True)
