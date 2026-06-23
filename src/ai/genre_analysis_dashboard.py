import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from src.database.connection import get_connection

_THEME_LIGHT = ":root{--bg:#F5F6FA;--bg2:#FFFFFF;--bg3:#F8F9FB;--bg4:#EEF1F7;--border:rgba(148,163,184,.2);--border2:rgba(148,163,184,.35);--t1:#1A1A1A;--t2:#4A5568;--t3:#8A8FA3;--t4:#A0AEC0;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"
_THEME_DARK  = ":root{--bg:#0d1117;--bg2:#161b27;--bg3:#1a2035;--bg4:#1e2740;--border:rgba(41,52,85,.7);--border2:rgba(58,70,97,.8);--t1:#e2e8f0;--t2:#94a3b8;--t3:#8b95ad;--t4:#6b7a99;--green:#34d399;--gd:rgba(52,211,153,.18);--red:#fb7185;--rd:rgba(251,113,133,.18);--blue:#60a5fa;--bd:rgba(96,165,250,.18);--purple:#c4b5fd;--pd:rgba(196,181,253,.18);--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;}"

COUNTRY_FLAGS = {
    "us": "🇺🇸 United States",
    "gb": "🇬🇧 United Kingdom", "uk": "🇬🇧 United Kingdom", "ar": "🇦🇷 Argentina",
    "au": "🇦🇺 Australia", "at": "🇦🇹 Austria", "be": "🇧🇪 Belgium",
    "bo": "🇧🇴 Bolivia", "br": "🇧🇷 Brazil", "bg": "🇧🇬 Bulgaria",
    "ca": "🇨🇦 Canada", "cl": "🇨🇱 Chile", "co": "🇨🇴 Colombia",
    "cr": "🇨🇷 Costa Rica", "cz": "🇨🇿 Czech Republic", "dk": "🇩🇰 Denmark",
    "do": "🇩🇴 Dominican Republic", "ec": "🇪🇨 Ecuador", "eg": "🇪🇬 Egypt",
    "sv": "🇸🇻 El Salvador", "ee": "🇪🇪 Estonia", "fi": "🇫🇮 Finland",
    "fr": "🇫🇷 France", "de": "🇩🇪 Germany", "gr": "🇬🇷 Greece",
    "gt": "🇬🇹 Guatemala", "hn": "🇭🇳 Honduras", "hk": "🇭🇰 Hong Kong",
    "hu": "🇭🇺 Hungary", "is": "🇮🇸 Iceland", "in": "🇮🇳 India",
    "id": "🇮🇩 Indonesia", "ie": "🇮🇪 Ireland", "il": "🇮🇱 Israel",
    "it": "🇮🇹 Italy", "jp": "🇯🇵 Japan", "lv": "🇱🇻 Latvia",
    "lt": "🇱🇹 Lithuania", "lu": "🇱🇺 Luxembourg", "my": "🇲🇾 Malaysia",
    "mx": "🇲🇽 Mexico", "ma": "🇲🇦 Morocco", "nl": "🇳🇱 Netherlands",
    "nz": "🇳🇿 New Zealand", "ni": "🇳🇮 Nicaragua", "ng": "🇳🇬 Nigeria",
    "no": "🇳🇴 Norway", "pa": "🇵🇦 Panama", "py": "🇵🇾 Paraguay",
    "pe": "🇵🇪 Peru", "ph": "🇵🇭 Philippines", "pl": "🇵🇱 Poland",
    "pt": "🇵🇹 Portugal", "ro": "🇷🇴 Romania", "sa": "🇸🇦 Saudi Arabia",
    "sg": "🇸🇬 Singapore", "sk": "🇸🇰 Slovakia", "za": "🇿🇦 South Africa",
    "kr": "🇰🇷 South Korea", "es": "🇪🇸 Spain", "se": "🇸🇪 Sweden",
    "ch": "🇨🇭 Switzerland", "tw": "🇹🇼 Taiwan", "th": "🇹🇭 Thailand",
    "tr": "🇹🇷 Turkey", "ae": "🇦🇪 UAE", "ua": "🇺🇦 Ukraine",
    "uy": "🇺🇾 Uruguay", "vn": "🇻🇳 Vietnam", "ve": "🇻🇪 Venezuela"
}

NOISE_KEYWORDS = [
    'wsum', 'swim', 'chip', '...', '2026', 'deluxe', 'soty',
    'arirang', 'normal', 'peter', 'it boy', 'right now',
    'edu e marco', 'bmson', 'g-u-a-r-r-o', 'amor-salsa',
    'playlista'
]

def extract_primary_genre(raw_str):
    if not isinstance(raw_str, str):
        return "Unknown"
    
    parts = [p.strip() for p in raw_str.split(',')]
    for p in parts:
        p_lower = p.lower()
        if not p_lower:
            continue
        
        is_noise = False
        for noise in NOISE_KEYWORDS:
            if noise in p_lower:
                is_noise = True
                break
                
        if p_lower.isdigit():
            is_noise = True
            
        if not is_noise:
            # Title-case for display (e.g. "Alternative Rock")
            return p.title()
            
    return "Unknown"

@st.cache_data(ttl=300, show_spinner=False)
def get_genre_analysis_data(days: int = 30):
    conn = get_connection()
    try:
        query_sp = """
            WITH bounds AS (SELECT MAX(date) AS max_d FROM spotify_daily)
            SELECT d.date, d.country, d.rank, d.artist_title, d.streams AS metric, d.genere
            FROM spotify_daily d, bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
              AND d.genere IS NOT NULL AND TRIM(d.genere) != ''
        """
        with conn.cursor() as cur:
            cur.execute(query_sp, (days,))
            sp_rows = cur.fetchall()
        sp_df = pd.DataFrame(sp_rows)
        
        query_it = """
            WITH bounds AS (SELECT MAX(date) AS max_d FROM itunes_daily)
            SELECT d.date, d.country, d.rank, d.artist_title, d.points AS metric, d.genere
            FROM itunes_daily d, bounds b
            WHERE d.date > (b.max_d - %s::int)
              AND d.date <= b.max_d
              AND d.genere IS NOT NULL AND TRIM(d.genere) != ''
        """
        with conn.cursor() as cur:
            cur.execute(query_it, (days,))
            it_rows = cur.fetchall()
        it_df = pd.DataFrame(it_rows)
    finally:
        conn.close()

    if sp_df.empty and it_df.empty:
        return None

    raw_genres_set = set()
    
    if not sp_df.empty:
        sp_df['raw_genere'] = sp_df['genere'].apply(extract_primary_genre)
        sp_df['metric'] = pd.to_numeric(sp_df['metric'], errors='coerce').fillna(0)
        for g_val in sp_df['raw_genere'].dropna():
            if g_val != 'Unknown':
                raw_genres_set.add(g_val.lower())
    else:
        sp_df = pd.DataFrame(columns=['date', 'country', 'rank', 'artist_title', 'metric', 'genere', 'raw_genere'])

    if not it_df.empty:
        it_df['raw_genere'] = it_df['genere'].apply(extract_primary_genre)
        it_df['metric'] = pd.to_numeric(it_df['metric'], errors='coerce').fillna(0)
        for g_val in it_df['raw_genere'].dropna():
            if g_val != 'Unknown':
                raw_genres_set.add(g_val.lower())
    else:
        it_df = pd.DataFrame(columns=['date', 'country', 'rank', 'artist_title', 'metric', 'genere', 'raw_genere'])

    genre_scores = []
    if not it_df.empty:
        it_scores = it_df.groupby('raw_genere')['metric'].sum().reset_index()
        it_scores = it_scores[it_scores['raw_genere'] != 'Unknown'].sort_values('metric', ascending=False)
        genre_scores = [{"g": row['raw_genere'], "s": int(row['metric'])} for _, row in it_scores.iterrows()]

    spotify_streams = []
    if not sp_df.empty:
        sp_global = sp_df[sp_df['country'] == 'global']
        sp_scores = sp_global.groupby('raw_genere')['metric'].sum().reset_index()
        sp_scores = sp_scores[sp_scores['raw_genere'] != 'Unknown'].sort_values('metric', ascending=False)
        spotify_streams = [{"g": row['raw_genere'], "s": int(row['metric'])} for _, row in sp_scores.iterrows()]
        
    perf_data = {}
    if not sp_df.empty:
        sp_global = sp_df[sp_df['country'] == 'global']
        top_raw_genres = sp_global[sp_global['raw_genere'] != 'Unknown'].groupby('raw_genere')['metric'].sum().sort_values(ascending=False).head(10).index.tolist()
        
        for genre in top_raw_genres:
            group = sp_global[sp_global['raw_genere'] == genre]
            track_streams = group.groupby('artist_title')['metric'].sum().reset_index()
            top_tracks = track_streams.sort_values('metric', ascending=False)
            perf_data[genre] = [
                {"name": row['artist_title'], "score": int(row['metric'])}
                for _, row in top_tracks.iterrows()
            ]

    countries = []
    country_genres = []
    if not sp_df.empty:
        sp_countries = sp_df[sp_df['country'] != 'global']
        for country, c_group in sp_countries.groupby('country'):
            c_streams = int(c_group['metric'].sum())
            c_raw_genres = set()
            for g_val in c_group['raw_genere'].dropna():
                if g_val and g_val != 'Unknown':
                    c_raw_genres.add(g_val.lower())
            c_genres = len(c_raw_genres)
            c_name = COUNTRY_FLAGS.get(country.lower(), country.upper())
            countries.append({"name": c_name, "streams": c_streams, "genres": c_genres})
            valid_c_group = c_group[c_group['raw_genere'] != 'Unknown']
            if not valid_c_group.empty:
                dom_series = valid_c_group.groupby('raw_genere')['metric'].sum()
                dom_genre = dom_series.idxmax()
                dom_streams = dom_series.max()
            else:
                dom_genre = 'Unknown'
                dom_streams = 0
            country_genres.append({"country": c_name, "genre": dom_genre, "streams": int(dom_streams)})
            
        countries = sorted(countries, key=lambda x: x['streams'], reverse=True)

    all_genres = list(set([g['g'] for g in genre_scores[:10]] + [g['g'] for g in spotify_streams[:10]]))
    all_genres = all_genres[:10] if all_genres else ['Pop']
    
    spotify_count = []
    itunes_count = []
    
    for g in all_genres:
        sp_c = sp_df[(sp_df['country'] == 'global') & (sp_df['raw_genere'] == g)]['artist_title'].nunique() if not sp_df.empty else 0
        it_c = it_df[(it_df['country'] == 'ww') & (it_df['raw_genere'] == g)]['artist_title'].nunique() if not it_df.empty else 0
        spotify_count.append(sp_c)
        itunes_count.append(it_c)

    genres_tracked = len(raw_genres_set)
    top_genre_score = genre_scores[0]['s'] if genre_scores else 0
    top_genre_name = genre_scores[0]['g'] if genre_scores else "N/A"
    top_streams_val = spotify_streams[0]['s'] if spotify_streams else 0
    top_streams_name = spotify_streams[0]['g'] if spotify_streams else "N/A"
    countries_covered = sp_df['country'].nunique() - (1 if 'global' in sp_df['country'].unique() else 0)

    payload = {
        "genreScores": genre_scores,
        "spotifyStreams": spotify_streams,
        "perfData": perf_data,
        "countries": countries,
        "countryGenres": country_genres,
        "allGenres": all_genres,
        "spotifyCount": spotify_count,
        "itunesCount": itunes_count,
        "kpis": {
            "genresTracked": genres_tracked,
            "topGenreScore": top_genre_score,
            "topGenreName": top_genre_name,
            "topStreamsVal": top_streams_val,
            "topStreamsName": top_streams_name,
            "countriesCovered": countries_covered
        }
    }
    return payload


def _build_html(payload: dict, dark_mode: bool) -> str:
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    payload_json = json.dumps(payload)
    
    box_shadow = "0 4px 20px rgba(0,0,0,0.25)" if dark_mode else "0 2px 10px rgba(0,0,0,0.04)"
    
    return f"""
<style>
{theme_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--t1);padding:1.25rem 0}}
.db{{width:100%;max-width:1400px;margin:0 auto;display:flex;flex-direction:column;gap:1.5rem}}

/* --- KPIs --- */
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.kpi{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.15rem;box-shadow:{box_shadow};transition:transform 0.2s ease, box-shadow 0.2s ease}}
.kpi:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,0.12)}}
.kpi-label{{font-size:12px;font-weight:600;color:var(--t2);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.kpi-label i{{color:var(--blue);font-size:16px}}
.kpi-value{{font-size:26px;font-weight:700;color:var(--t1);letter-spacing:-0.02em}}
.kpi-sub{{font-size:12px;color:var(--t3);margin-top:6px;font-weight:500}}

/* --- Cards --- */
.charts-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.card, .full-card{{background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:1.25rem;box-shadow:{box_shadow}}}
.card-title{{font-size:14px;font-weight:600;color:var(--t1);margin-bottom:16px;display:flex;align-items:center;gap:8px}}
.card-title i{{color:var(--t3);font-size:18px}}

/* --- Progress Bars --- */
.genre-bar{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.genre-label{{font-size:12px;font-weight:500;color:var(--t1);width:120px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar-track{{flex:1;background:var(--bg4);border-radius:6px;height:10px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:6px;transition:width 0.8s cubic-bezier(0.4, 0, 0.2, 1)}}
.genre-val{{font-size:12px;font-weight:600;color:var(--t2);width:55px;text-align:right;flex-shrink:0}}

/* --- Tabs --- */
.tabs{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;border-bottom:1px solid var(--border);padding-bottom:8px}}
.tab{{font-size:12px;font-weight:600;padding:6px 14px;border-radius:20px;border:1px solid var(--border);background:var(--bg3);color:var(--t2);cursor:pointer;transition:all 0.2s ease}}
.tab:hover{{background:var(--bg4);color:var(--t1)}}
.tab.active{{background:var(--bd);color:var(--blue);border-color:var(--blue)}}

/* --- Performance List --- */
.perf-row{{display:flex;align-items:center;gap:12px;padding:10px 8px;border-bottom:1px dashed var(--border);border-radius:6px;transition:background 0.2s ease}}
.perf-row:hover{{background:var(--bg3)}}
.perf-row:last-child{{border-bottom:none}}
.rank-circle{{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;box-shadow:inset 0 0 0 1px rgba(0,0,0,0.05)}}
.perf-name{{font-size:13px;font-weight:500;color:var(--t1);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.perf-score{{font-size:13px;font-weight:600;color:var(--t2);text-align:right;min-width:70px}}

/* --- Lists --- */
.country-row{{display:flex;align-items:center;justify-content:space-between;padding:8px 8px;border-bottom:1px solid var(--border);border-radius:6px;transition:background 0.2s ease}}
.country-row:hover{{background:var(--bg3)}}
.country-row:last-child{{border-bottom:none}}
.country-name{{font-size:13px;font-weight:600;color:var(--t1)}}
.country-genres{{font-size:11px;color:var(--t3);margin-top:2px;font-weight:500}}
.country-streams{{font-size:13px;font-weight:700;color:var(--t2)}}

/* --- Badges --- */
.badge{{font-size:10px;padding:4px 8px;border-radius:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;display:inline-block}}
.badge-pop{{background:var(--bd);color:var(--blue)}}
.badge-latin{{background:var(--rd);color:var(--red)}}
.badge-indie{{background:var(--pd);color:var(--purple)}}
.badge-rock{{background:var(--gd);color:var(--green)}}
.badge-country{{background:rgba(252,211,77,0.2);color:#d97706}}
.badge-altrock{{background:var(--pd);color:var(--purple)}}
.badge-rnb{{background:rgba(94,234,212,0.2);color:#0f766e}}
.badge-newwave{{background:var(--border2);color:var(--t2)}}

.legend-row{{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:12px}}
.legend-item{{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:500;color:var(--t2)}}
.legend-dot{{width:12px;height:12px;border-radius:3px;flex-shrink:0}}

/* Custom Scrollbar for lists */
::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:4px}}
::-webkit-scrollbar-thumb:hover{{background:var(--t3)}}
</style>

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.44.0/tabler-icons.min.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

<div class="db">

<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label"><i class="ti ti-music"></i> genres tracked</div>
    <div class="kpi-value" id="kpi-genresTracked"></div>
    <div class="kpi-sub">across iTunes + Spotify</div>
  </div>
  <div class="kpi">
    <div class="kpi-label"><i class="ti ti-chart-bar"></i> top genre score</div>
    <div class="kpi-value" id="kpi-topGenreScore"></div>
    <div class="kpi-sub"><span id="kpi-topGenreName" style="color:var(--blue);font-weight:600;"></span> — combined platforms</div>
  </div>
  <div class="kpi">
    <div class="kpi-label"><i class="ti ti-headphones"></i> top streams genre</div>
    <div class="kpi-value" id="kpi-topStreamsVal"></div>
    <div class="kpi-sub"><span id="kpi-topStreamsName" style="color:var(--green);font-weight:600;"></span> on Spotify</div>
  </div>
  <div class="kpi">
    <div class="kpi-label"><i class="ti ti-world"></i> countries covered</div>
    <div class="kpi-value" id="kpi-countriesCovered"></div>
    <div class="kpi-sub">Spotify regional data</div>
  </div>
</div>

<div class="charts-row">
  <div class="card">
    <div class="card-title"><i class="ti ti-chart-bar"></i> Genre Score (All Platforms)</div>
    <div id="score-bars"></div>
    <div style="margin-top:16px; position:relative; height:160px;">
      <canvas id="pieChart" role="img" aria-label="Genre score distribution pie chart"></canvas>
    </div>
  </div>

  <div class="card">
    <div class="card-title"><i class="ti ti-headphones"></i> Spotify Streams by Genre</div>
    <div id="stream-bars"></div>
    <div style="margin-top:16px; position:relative; height:160px;">
      <canvas id="pieChart2" role="img" aria-label="Spotify streams distribution pie chart"></canvas>
    </div>
  </div>
</div>

<div class="full-card">
  <div class="card-title"><i class="ti ti-trending-up"></i> Genre Performance — Top Tracks</div>
  <div class="tabs" id="genre-tabs"></div>
  <div id="perf-list" style="max-height:400px;overflow-y:auto;padding-right:8px;"></div>
</div>

<div class="charts-row">
  <div class="card">
    <div class="card-title"><i class="ti ti-world"></i> Listeners by Country (Spotify Streams)</div>
    <div id="country-list" style="max-height:300px;overflow-y:auto;padding-right:8px;"></div>
  </div>

  <div class="card">
    <div class="card-title"><i class="ti ti-map-pin"></i> Genre Dominance by Country</div>
    <div id="country-genre" style="max-height:300px;overflow-y:auto;padding-right:8px;"></div>
  </div>
</div>

<div class="full-card">
  <div class="card-title"><i class="ti ti-chart-line"></i> Genre Track Distribution — iTunes vs Spotify</div>
  <div class="legend-row" id="platform-legend"></div>
  <div style="position:relative;height:240px">
    <canvas id="barChart" role="img" aria-label="Genre track count bar chart comparing iTunes and Spotify"></canvas>
  </div>
</div>

</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const dashData = {payload_json};
const rootStyles = getComputedStyle(document.documentElement);
const cssVar = (name) => rootStyles.getPropertyValue(name).trim();

// Use CSS variables for chart elements to adapt to light/dark
const textColor = cssVar('--t2');
const gridColor = cssVar('--border');

const GENRE_COLORS = {{
  'Pop':'#378ADD','Indie':'#7F77DD','Country':'#BA7517','Rock':'#639922',
  'Alternative Rock':'#D4537E','Latin':'#D85A30','New Wave':'#888780',
  'R&b':'#1D9E75','Folk':'#3B6D11','Pop Rock':'#185FA5','Pop Rap':'#854F0B','Hip Hop':'#533b4a',
  'Electronic':'#fcd34d'
}};

function getColor(g) {{
  if(GENRE_COLORS[g]) return GENRE_COLORS[g];
  let hash = 0;
  for(let i = 0; i < g.length; i++) {{
    hash = g.charCodeAt(i) + ((hash << 5) - hash);
  }}
  const h = Math.abs(hash) % 360;
  return `hsl(${{h}}, 65%, 50%)`;
}}

const genreScores = dashData.genreScores;
const spotifyStreams = dashData.spotifyStreams;
const perfData = dashData.perfData;
const countries = dashData.countries;
const countryGenres = dashData.countryGenres;
const allGenres = dashData.allGenres;
const spotifyCount = dashData.spotifyCount;
const itunesCount = dashData.itunesCount;
const kpis = dashData.kpis;

function fmtScore(v){{
  if(v>=1e9) return (v/1e9).toFixed(1)+'B';
  if(v>=1e6) return (v/1e6).toFixed(1)+'M';
  if(v>=1e3) return (v/1e3).toFixed(0)+'K';
  return v;
}}

// Update KPIs
document.getElementById('kpi-genresTracked').innerText = kpis.genresTracked;
document.getElementById('kpi-topGenreScore').innerText = fmtScore(kpis.topGenreScore);
document.getElementById('kpi-topGenreName').innerText = kpis.topGenreName;
document.getElementById('kpi-topStreamsVal').innerText = fmtScore(kpis.topStreamsVal);
document.getElementById('kpi-topStreamsName').innerText = kpis.topStreamsName;
document.getElementById('kpi-countriesCovered').innerText = kpis.countriesCovered;

function renderBars(containerId, data, colorFn){{
  const el = document.getElementById(containerId);
  if(data.length === 0) {{ el.innerHTML = "<div style='color:var(--t3);padding:20px;text-align:center;'>No data available</div>"; return; }}
  const max = Math.max(...data.map(d=>d.s));
  el.innerHTML = data.slice(0,8).map(d=>`
    <div class="genre-bar">
      <span class="genre-label" title="${{d.g}}">${{d.g}}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${{Math.max(2, Math.round(d.s/max*100))}}%;background:${{colorFn(d.g)}}"></div></div>
      <span class="genre-val">${{fmtScore(d.s)}}</span>
    </div>`).join('');
}}

renderBars('score-bars', genreScores, getColor);
renderBars('stream-bars', spotifyStreams, getColor);

const top6 = genreScores.slice(0,6);
if(top6.length > 0) {{
    new Chart(document.getElementById('pieChart'),{{
      type:'doughnut',
      data:{{
        labels:top6.map(d=>d.g),
        datasets:[{{
            data:top6.map(d=>d.s),
            backgroundColor:top6.map(d=>getColor(d.g)),
            borderWidth: 2,
            borderColor: cssVar('--bg2')
        }}]
      }},
      options:{{
        responsive:true,
        maintainAspectRatio:false,
        cutout:'65%',
        plugins:{{
          legend:{{
            position: 'right',
            labels: {{ color: textColor, boxWidth: 12, padding: 15, font: {{size: 11, family: 'Inter'}} }}
          }},
          tooltip:{{
            backgroundColor: cssVar('--bg3'),
            titleColor: cssVar('--t1'),
            bodyColor: cssVar('--t2'),
            borderColor: cssVar('--border'),
            borderWidth: 1,
            callbacks:{{label:ctx=>' '+ctx.label+': '+fmtScore(ctx.raw)}}
          }}
        }}
      }}
    }});
}}

const top6Streams = spotifyStreams.slice(0,6);
if(top6Streams.length > 0) {{
    new Chart(document.getElementById('pieChart2'),{{
      type:'doughnut',
      data:{{
        labels:top6Streams.map(d=>d.g),
        datasets:[{{
            data:top6Streams.map(d=>d.s),
            backgroundColor:top6Streams.map(d=>getColor(d.g)),
            borderWidth: 2,
            borderColor: cssVar('--bg2')
        }}]
      }},
      options:{{
        responsive:true,
        maintainAspectRatio:false,
        cutout:'65%',
        plugins:{{
          legend:{{
            position: 'right',
            labels: {{ color: textColor, boxWidth: 12, padding: 15, font: {{size: 11, family: 'Inter'}} }}
          }},
          tooltip:{{
            backgroundColor: cssVar('--bg3'),
            titleColor: cssVar('--t1'),
            bodyColor: cssVar('--t2'),
            borderColor: cssVar('--border'),
            borderWidth: 1,
            callbacks:{{label:ctx=>' '+ctx.label+': '+fmtScore(ctx.raw)}}
          }}
        }}
      }}
    }});
}}

const genres = Object.keys(perfData);
const tabsEl = document.getElementById('genre-tabs');
if(genres.length > 0) {{
    tabsEl.innerHTML = genres.map((g,i)=>`<button class="tab${{i===0?' active':''}}" data-g="${{g}}">${{g}}</button>`).join('');
}} else {{
    tabsEl.innerHTML = "<div style='color:var(--t3);'>No performance data</div>";
}}

function renderPerf(genre){{
  const rows = perfData[genre]||[];
  const colors=['#378ADD','#7F77DD','#BA7517','#639922','#D4537E','#1D9E75'];
  document.getElementById('perf-list').innerHTML = rows.map((r,i)=>{{
    const c = colors[i%colors.length];
    return `<div class="perf-row">
      <div class="rank-circle" style="background:${{c}}22;color:${{c}}">${{i+1}}</div>
      <span class="perf-name" title="${{r.name}}">${{r.name}}</span>
      <span class="perf-score">${{fmtScore(r.score)}}</span>
    </div>`;
  }}).join('');
}}

if(genres.length > 0) {{
    renderPerf(genres[0]);
    tabsEl.addEventListener('click',e=>{{
      const btn=e.target.closest('.tab');
      if(!btn) return;
      tabsEl.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      renderPerf(btn.dataset.g);
    }});
}}

document.getElementById('country-list').innerHTML = countries.map(c=>`
  <div class="country-row">
    <div><div class="country-name">${{c.name}}</div><div class="country-genres">${{c.genres}} genres tracked</div></div>
    <div class="country-streams">${{fmtScore(c.streams)}}</div>
  </div>`).join('');

document.getElementById('country-genre').innerHTML = countryGenres.map(c=>`
  <div class="country-row" style="align-items: center; justify-content: space-between;">
    <span class="country-name" style="flex: 1;">${{c.country}}</span>
    <div style="display: flex; align-items: center; gap: 12px;">
      <span class="badge" style="background-color: ${{getColor(c.genre)}}; color: #fff; padding: 4px 8px; border-radius: 12px; font-size: 10px; font-weight: 600; text-transform: uppercase;">${{c.genre}}</span>
      <span class="country-streams" style="width: 45px; text-align: right; font-size: 12px; color: var(--t2); font-weight: 600;">${{fmtScore(c.streams)}}</span>
    </div>
  </div>`).join('');

document.getElementById('platform-legend').innerHTML = `
  <span class="legend-item"><span class="legend-dot" style="background:var(--blue)"></span>Spotify</span>
  <span class="legend-item"><span class="legend-dot" style="background:var(--pink)"></span>iTunes</span>`;

const bh = Math.max(240, allGenres.length * 35 + 40);
document.querySelector('#barChart').parentElement.style.height = bh+'px';

if(allGenres.length > 0) {{
    new Chart(document.getElementById('barChart'),{{
      type:'bar',
      data:{{
        labels:allGenres,
        datasets:[
          {{
            label:'Spotify',
            data:spotifyCount,
            backgroundColor: 'rgba(96,165,250,0.8)',
            borderColor: 'rgb(96,165,250)',
            borderWidth:1,
            borderRadius: 4
          }},
          {{
            label:'iTunes',
            data:itunesCount,
            backgroundColor: 'rgba(249,168,212,0.8)',
            borderColor: 'rgb(249,168,212)',
            borderWidth:1,
            borderRadius: 4
          }}
        ]
      }},
      options:{{
        indexAxis:'y',
        responsive:true,
        maintainAspectRatio:false,
        plugins:{{
          legend:{{display:false}},
          tooltip:{{
            backgroundColor: cssVar('--bg3'),
            titleColor: cssVar('--t1'),
            bodyColor: cssVar('--t2'),
            borderColor: cssVar('--border'),
            borderWidth: 1,
            callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.raw}} tracks`}}
          }}
        }},
        scales:{{
          x:{{
            grid:{{color: gridColor}},
            ticks:{{color: textColor, font:{{size:11, family:'Inter'}}}}
          }},
          y:{{
            grid:{{display:false}},
            ticks:{{color: textColor, font:{{size:12, family:'Inter'}}}}
          }}
        }}
      }}
    }});
}}
</script>
"""

def render_genre_analysis():
    data_payload = get_genre_analysis_data(30)
    
    if not data_payload:
        st.warning("No data available for Genre Analysis.")
        return
        
    dark_mode = st.session_state.get("dark_mode", False)
    html_content = _build_html(data_payload, dark_mode)
    
    components.html(html_content, height=1350, scrolling=True)
