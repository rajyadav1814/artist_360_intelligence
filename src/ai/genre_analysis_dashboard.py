import json
import unicodedata
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

LATAM_COUNTRIES = {"ar", "bo", "br", "cl", "co", "cr", "do", "ec", "sv", "gt", "hn", "mx", "ni", "pa", "py", "pe", "uy", "ve", "pr"}

def get_region(country_code: str) -> str:
    c = country_code.lower()
    if c == "global": return "global"
    if c in LATAM_COUNTRIES: return "latam"
    if c in {"us", "ca"}: return "americas"
    return "other"

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
            # Normalize accents (Reggaetón → Reggaeton) then title-case
            normalized = unicodedata.normalize('NFKD', p).encode('ascii', 'ignore').decode('ascii')
            return normalized.title()
            
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

    regional_data = []
    regional_kpis = {
        "countriesAnalyzed": 0,
        "topCountryStreams": "N/A",
        "topCountryStreamsVal": "0",
        "dominantGenreLatam": "N/A",
        "dominantGenreLatamCount": "0",
        "usaTopGenre": "N/A",
        "usaTopGenreStreams": "0"
    }

    if not sp_df.empty:
        # Group by country for regional data
        latam_genres = {}
        usa_top = ("N/A", 0)
        
        for country, c_group in sp_df.groupby('country'):
            c_code = country.lower()
            region = get_region(c_code)
            c_name = "Global" if c_code == "global" else COUNTRY_FLAGS.get(c_code, country.upper())
            flag = "🌐" if c_code == "global" else (c_name.split()[0] if " " in c_name else "")
            name_only = c_name.split(" ", 1)[1] if " " in c_name and c_code != "global" else c_name
            
            c_total = int(c_group['metric'].sum())
            
            # Top 5 genres
            c_valid = c_group[c_group['raw_genere'] != 'Unknown']
            top_g = c_valid.groupby('raw_genere')['metric'].sum().sort_values(ascending=False).head(5)
            
            genres_list = []
            for g_name, g_val in top_g.items():
                genres_list.append({"g": g_name, "s": int(g_val)})
            
            regional_data.append({
                "country": name_only,
                "region": region,
                "flag": flag,
                "total": c_total,
                "genres": genres_list
            })
            
            # KPI logic — accumulate total streams per genre across LATAM
            # (same basis as heatmap: absolute stream volume, not just #1 rank)
            if region == "latam":
                for g in genres_list:
                    latam_genres[g['g']] = latam_genres.get(g['g'], 0) + g['s']
            if c_code == "us" and len(genres_list) > 0:
                usa_top = (genres_list[0]['g'], genres_list[0]['s'])
                
        regional_data = sorted(regional_data, key=lambda x: x['total'], reverse=True)
        
        # Calculate regional KPIs
        non_global = [d for d in regional_data if d['region'] != 'global']
        regional_kpis["countriesAnalyzed"] = len(non_global)
        if non_global:
            regional_kpis["topCountryStreams"] = non_global[0]['country']
            regional_kpis["topCountryStreamsVal"] = non_global[0]['total']
        if latam_genres:
            dom_latam = max(latam_genres.items(), key=lambda x: x[1])
            regional_kpis["dominantGenreLatam"] = dom_latam[0]
            regional_kpis["dominantGenreLatamCount"] = f"{dom_latam[1]:,} streams across LATAM"
        if usa_top[0] != "N/A":
            regional_kpis["usaTopGenre"] = usa_top[0]
            regional_kpis["usaTopGenreStreams"] = usa_top[1]

    payload = {
        "genreScores": genre_scores,
        "spotifyStreams": spotify_streams,
        "perfData": perf_data,
        "countries": countries,
        "countryGenres": country_genres,
        "allGenres": all_genres,
        "spotifyCount": spotify_count,
        "itunesCount": itunes_count,
        "regionalData": regional_data,
        "regionalKpis": regional_kpis,
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


def _build_html(payloads: dict, dark_mode: bool) -> str:
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    payload_json = json.dumps(payloads)
    
    box_shadow = "0 4px 20px rgba(0,0,0,0.25)" if dark_mode else "0 2px 10px rgba(0,0,0,0.04)"
    
    return f"""
<style>
{theme_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--t1);padding:1.25rem 0}}
.db{{width:100%;max-width:1400px;margin:0 auto;display:flex;flex-direction:column;gap:1.5rem}}

/* --- Time Filter Pills --- */
.time-filter-row {{
  display: flex;
  gap: 10px;
  margin-bottom: 0.25rem;
  align-items: center;
}}
.tpill {{
  font-size: 13px;
  font-weight: 500;
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid var(--border2);
  background: var(--bg2);
  color: var(--t2);
  cursor: pointer;
  transition: all 0.2s ease;
}}
.tpill:hover {{
  background: var(--bg4);
  color: var(--t1);
}}
.tpill.active {{
  background: var(--rd);
  color: var(--red);
  border-color: var(--red);
  font-weight: 600;
}}

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

<div class="time-filter-row">
  <button class="tpill active" data-days="7">Last week</button>
  <button class="tpill" data-days="15">Last 15 days</button>
  <button class="tpill" data-days="30">Last month</button>
</div>

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
  </div>

  <div class="card">
    <div class="card-title"><i class="ti ti-headphones"></i> Spotify Streams by Genre</div>
    <div id="stream-bars"></div>
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

</div>

<script>
const combinedData = {payload_json};
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

function fmtScore(v){{
  if(v>=1e9) return (v/1e9).toFixed(1)+'B';
  if(v>=1e6) return (v/1e6).toFixed(1)+'M';
  if(v>=1e3) return (v/1e3).toFixed(0)+'K';
  return v;
}}

function renderBars(containerId, data, colorFn){{
  const el = document.getElementById(containerId);
  if(!data || data.length === 0) {{ el.innerHTML = "<div style='color:var(--t3);padding:20px;text-align:center;'>No data available</div>"; return; }}
  const max = Math.max(...data.map(d=>d.s));
  el.innerHTML = data.slice(0,8).map(d=>`
    <div class="genre-bar">
      <span class="genre-label" title="${{d.g}}">${{d.g}}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${{Math.max(2, Math.round(d.s/max*100))}}%;background:${{colorFn(d.g)}}"></div></div>
      <span class="genre-val">${{fmtScore(d.s)}}</span>
    </div>`).join('');
}}

function updateDashboard(days) {{
  const dashData = combinedData[days];
  if(!dashData) return;

  const genreScores = dashData.genreScores || [];
  const spotifyStreams = dashData.spotifyStreams || [];
  const perfData = dashData.perfData || {{}};
  const countries = dashData.countries || [];
  const countryGenres = dashData.countryGenres || [];
  const kpis = dashData.kpis || {{}};

  // Update KPIs
  document.getElementById('kpi-genresTracked').innerText = kpis.genresTracked || 0;
  document.getElementById('kpi-topGenreScore').innerText = fmtScore(kpis.topGenreScore || 0);
  document.getElementById('kpi-topGenreName').innerText = kpis.topGenreName || 'N/A';
  document.getElementById('kpi-topStreamsVal').innerText = fmtScore(kpis.topStreamsVal || 0);
  document.getElementById('kpi-topStreamsName').innerText = kpis.topStreamsName || 'N/A';
  document.getElementById('kpi-countriesCovered').innerText = kpis.countriesCovered || 0;

  renderBars('score-bars', genreScores, getColor);
  renderBars('stream-bars', spotifyStreams, getColor);

  const genres = Object.keys(perfData);
  const tabsEl = document.getElementById('genre-tabs');
  if(genres.length > 0) {{
      tabsEl.innerHTML = genres.map((g,i)=>`<button class="tab${{i===0?' active':''}}" data-g="${{g}}">${{g}}</button>`).join('');
  }} else {{
      tabsEl.innerHTML = "<div style='color:var(--t3);'>No performance data</div>";
  }}

  window.renderPerf = function(genre) {{
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
  }};

  if(genres.length > 0) {{
      window.renderPerf(genres[0]);
  }} else {{
      document.getElementById('perf-list').innerHTML = "";
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
}}

// Initialize Dashboard
const activePill = document.querySelector('.tpill.active');
const defaultDays = activePill ? activePill.dataset.days : "7";
updateDashboard(defaultDays);

// Time filter click listeners
document.querySelectorAll('.tpill').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tpill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    updateDashboard(btn.dataset.days);
  }});
}});

// Tab switching click listener (delegated)
document.getElementById('genre-tabs').addEventListener('click', e => {{
  const btn = e.target.closest('.tab');
  if(!btn) return;
  document.querySelectorAll('#genre-tabs .tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (typeof window.renderPerf === 'function') {{
    window.renderPerf(btn.dataset.g);
  }}
}});

</script>
"""

def _build_regional_html(payloads: dict, dark_mode: bool) -> str:
    theme_css = _THEME_DARK if dark_mode else _THEME_LIGHT
    payload_json = json.dumps(payloads)
    box_shadow = "0 4px 20px rgba(0,0,0,0.25)" if dark_mode else "0 2px 10px rgba(0,0,0,0.04)"
    
    return f"""
<style>
{theme_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--t1);padding:1.25rem 0}}
.db{{width:100%;max-width:1400px;margin:0 auto;display:flex;flex-direction:column;gap:1.5rem}}

/* --- Time Filter Pills --- */
.time-filter-row {{
  display: flex;
  gap: 10px;
  margin-bottom: 0.25rem;
  align-items: center;
}}
.tpill {{
  font-size: 13px;
  font-weight: 500;
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid var(--border2);
  background: var(--bg2);
  color: var(--t2);
  cursor: pointer;
  transition: all 0.2s ease;
}}
.tpill:hover {{
  background: var(--bg4);
  color: var(--t1);
}}
.tpill.active {{
  background: var(--rd);
  color: var(--red);
  border-color: var(--red);
  font-weight: 600;
}}

/* --- KPIs --- */
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.kpi{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.15rem;box-shadow:{box_shadow};transition:transform 0.2s ease, box-shadow 0.2s ease}}
.kpi-label{{font-size:12px;font-weight:600;color:var(--t2);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.kpi-value{{font-size:26px;font-weight:700;color:var(--t1);letter-spacing:-0.02em}}
.kpi-sub{{font-size:12px;color:var(--t3);margin-top:6px;font-weight:500}}
.tooltip-icon{{color:var(--t3);cursor:help;margin-left:auto;font-size:15px;transition:color 0.2s}}
.tooltip-icon:hover{{color:var(--blue)}}

.full-card{{background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:1.25rem;box-shadow:{box_shadow}}}
.card-title{{font-size:14px;font-weight:600;color:var(--t1);margin-bottom:16px;display:flex;align-items:center;gap:8px}}

.filter-row{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:0.75rem;align-items:center}}
.filter-label{{font-size:14px;font-weight:600;color:var(--t2);margin-right:4px;text-transform:uppercase;letter-spacing:0.04em}}
.fbtn{{font-size:13px;font-weight:600;padding:8px 18px;border-radius:20px;border:1px solid var(--border);background:var(--bg3);color:var(--t2);cursor:pointer;transition:all 0.2s ease}}
.fbtn:hover{{background:var(--bg4);color:var(--t1)}}
.fbtn.active{{background:var(--bd);color:var(--blue);border-color:var(--blue)}}

.country-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.ccard{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.15rem;box-shadow:{box_shadow}}}
.ccard-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}}
.ccard-name{{font-size:14px;font-weight:600;color:var(--t1);display:flex;align-items:center;gap:8px}}
.ccard-total{{font-size:12px;font-weight:500;color:var(--t3)}}

.genre-row{{margin-bottom:8px}}
.genre-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}}
.genre-name{{font-size:12px;font-weight:500;color:var(--t1);display:flex;align-items:center}}
.genre-pct{{font-size:11px;font-weight:600;color:var(--t2)}}
.bar-bg{{width:100%;height:8px;background:var(--bg4);border-radius:4px;overflow:hidden}}
.bar-fg{{height:100%;border-radius:4px}}

.top-badge{{font-size:10px;padding:2px 6px;border-radius:10px;font-weight:600;margin-right:6px}}

.leg-row{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:12px}}
.leg-item{{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:500;color:var(--t2)}}
.leg-sq{{width:12px;height:12px;border-radius:3px}}

::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:4px}}
::-webkit-scrollbar-thumb:hover{{background:var(--t3)}}
</style>

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.44.0/tabler-icons.min.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

<div class="db">

<div class="time-filter-row">
  <button class="tpill active" data-days="7">Last week</button>
  <button class="tpill" data-days="15">Last 15 days</button>
  <button class="tpill" data-days="30">Last month</button>
</div>

<div class="kpi-grid">
  <div class="kpi"><div class="kpi-label"><i class="ti ti-world"></i> countries analyzed <i class="ti ti-info-circle tooltip-icon" title="Total number of distinct geographic regions tracked in the daily stream data."></i></div><div class="kpi-value" id="kpi-analyzed"></div><div class="kpi-sub">Spotify regional data</div></div>
  <div class="kpi"><div class="kpi-label"><i class="ti ti-chart-bar"></i> top country (streams) <i class="ti ti-info-circle tooltip-icon" title="The single highest-streaming country across all genres."></i></div><div class="kpi-value" id="kpi-top-country"></div><div class="kpi-sub" id="kpi-top-streams"></div></div>
  <div class="kpi"><div class="kpi-label"><i class="ti ti-map-pin"></i> dominant genre (LATAM) <i class="ti ti-info-circle tooltip-icon" title="The single genre that holds the #1 ranking in the highest number of Latin American countries."></i></div><div class="kpi-value" id="kpi-latam"></div><div class="kpi-sub" id="kpi-latam-sub"></div></div>
  <div class="kpi"><div class="kpi-label"><i class="ti ti-flag"></i> USA #1 genre <i class="ti ti-info-circle tooltip-icon" title="The most streamed genre currently within the United States."></i></div><div class="kpi-value" id="kpi-usa"></div><div class="kpi-sub" id="kpi-usa-sub"></div></div>
</div>

<div class="full-card">
  <div class="card-title"><i class="ti ti-layout-grid"></i> Genre Strength Heatmap — Streams by Country</div>
  <div class="leg-row" id="hm-legend"></div>
  <div style="overflow-x:auto">
    <div id="heatmap"></div>
  </div>
</div>

<div class="filter-row">
  <span class="filter-label"><i class="ti ti-filter"></i> filter by region:</span>
  <button class="fbtn active" data-region="all">All countries</button>
  <button class="fbtn" data-region="global">Global</button>
  <button class="fbtn" data-region="americas">North America</button>
  <button class="fbtn" data-region="latam">Latin America</button>
</div>

<div class="country-grid" id="country-grid"></div>

</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const combinedData = {payload_json};
const rootStyles = getComputedStyle(document.documentElement);
const cssVar = (name) => rootStyles.getPropertyValue(name).trim();

// Use CSS variables for chart elements to adapt to light/dark
const textColor = cssVar('--t2');
const gridColor = cssVar('--border');

function fmt(v){{
  if(v>=1e9) return (v/1e9).toFixed(1)+'B';
  if(v>=1e6) return (v/1e6).toFixed(1)+'M';
  if(v>=1e3) return (v/1e3).toFixed(0)+'K';
  return v;
}}

const GENRE_COLORS = {{
  'Pop':'#378ADD','Indie':'#7F77DD','Country':'#BA7517','Rock':'#639922',
  'Alternative Rock':'#D4537E','Latin':'#D85A30','New Wave':'#888780',
  'R&B':'#1D9E75','Folk':'#3B6D11','Pop Rock':'#185FA5','Pop Rap':'#854F0B','Hip Hop':'#533b4a',
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

const labelW = 148, cellW = 88, cellH = 32;

function hexToRgb(hex) {{
  const r = parseInt(hex.slice(1,3),16), g2 = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
  return [r,g2,b];
}}
function luminance(hex) {{
  try {{
    const [r,g2,b] = hexToRgb(hex);
    return (0.299*r + 0.587*g2 + 0.114*b) / 255;
  }} catch(e) {{ return 0.5; }}
}}
function textOn(hex, alpha) {{
  if (alpha < 0.25) return cssVar('--t3');
  return luminance(hex) > 0.45 ? '#1a1a1a' : '#ffffff';
}}

let currentGenresHm = [];

function updateRegionalDashboard(days) {{
  const dashData = combinedData[days];
  if (!dashData) return;

  const DATA = dashData.regionalData || [];
  const kpis = dashData.regionalKpis || {{}};

  // Update KPIs
  document.getElementById('kpi-analyzed').innerText = kpis.countriesAnalyzed || 0;
  document.getElementById('kpi-top-country').innerText = kpis.topCountryStreams || 'N/A';
  document.getElementById('kpi-top-streams').innerText = fmt(kpis.topCountryStreamsVal || 0) + ' streams';
  document.getElementById('kpi-latam').innerText = kpis.dominantGenreLatam || 'N/A';
  document.getElementById('kpi-latam-sub').innerText = kpis.dominantGenreLatamCount || '';
  document.getElementById('kpi-usa').innerText = kpis.usaTopGenre || 'N/A';
  document.getElementById('kpi-usa-sub').innerText = fmt(kpis.usaTopGenreStreams || 0) + ' streams';

  window.renderCards = function(region) {{
    const filtered = region==='all' ? DATA : (region==='global' ? DATA.filter(d=>d.region==='global') : DATA.filter(d=>d.region===region));
    const grid = document.getElementById('country-grid');
    grid.innerHTML = filtered.map(d=>{{
      const max = d.genres.length > 0 ? d.genres[0].s : 0;
      const bars = d.genres.map((g,i)=>{{
        const pct = Math.round(g.s/d.total*100);
        const w = Math.round(g.s/max*100);
        const c = getColor(g.g);
        return `<div class="genre-row">
          <div class="genre-top">
            <span class="genre-name">${{i===0?`<span class="top-badge" style="background:${{c}}18;color:${{c}};border:0.5px solid ${{c}}44">★</span>`:''}}${{g.g}}</span>
            <span class="genre-pct">${{fmt(g.s)}} · ${{pct}}%</span>
          </div>
          <div class="bar-bg"><div class="bar-fg" style="width:${{w}}%;background:${{c}}"></div></div>
        </div>`;
      }}).join('');
      return `<div class="ccard">
        <div class="ccard-header">
          <span class="ccard-name"><span style="font-size:18px">${{d.flag}}</span>${{d.country}}</span>
          <span class="ccard-total">${{fmt(d.total)}} total</span>
        </div>
        ${{bars}}
      </div>`;
    }}).join('');
  }};

  const activeRegionBtn = document.querySelector('.fbtn.active');
  const activeReg = activeRegionBtn ? activeRegionBtn.dataset.region : 'all';
  window.renderCards(activeReg);

  // ── Heatmap ──────────────────────────────────────────────────
  const genreTotals = {{}};
  DATA.forEach(d => {{
    if (d.region !== 'global') {{
      d.genres.forEach(g => {{
        genreTotals[g.g] = (genreTotals[g.g] || 0) + g.s;
      }});
    }}
  }});
  const GENRES_HM = Object.entries(genreTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([g]) => g);

  currentGenresHm = GENRES_HM;

  const hmLegend = document.getElementById('hm-legend');
  hmLegend.innerHTML = GENRES_HM.map((g, i) => `
    <span class="leg-item hm-chip" data-gi="${{i}}" style="
      padding:4px 10px 4px 6px;border-radius:20px;border:1.5px solid ${{getColor(g)}}33;
      background:${{getColor(g)}}18;transition:all 0.18s;user-select:none"
    >
      <span class="leg-sq" style="background:${{getColor(g)}};border-radius:3px"></span>${{g}}
    </span>`).join('');

  const countries_hm = DATA.filter(d => d.country !== 'Global');
  const hmEl = document.getElementById('heatmap');

  const cols = GENRES_HM.length;
  const totalW = labelW + cols * cellW + (cols + 1) * 3;

  window.buildHeatmap = function(activeGi) {{
    let html = `<div style="display:grid;grid-template-columns:${{labelW}}px repeat(${{cols}},${{cellW}}px);gap:3px;min-width:${{totalW}}px">`;
    html += `<div></div>`;
    GENRES_HM.forEach((gn, gi) => {{
      const isDim = activeGi !== null && gi !== activeGi;
      const baseC = getColor(gn);
      html += `<div style="
        font-size:9px;font-weight:700;text-align:center;
        padding:3px 2px;border-radius:4px;
        color:${{isDim ? cssVar('--t4') : baseC}};
        background:${{isDim ? 'transparent' : baseC+'18'}};
        opacity:${{isDim ? 0.35 : 1}};
        letter-spacing:0.03em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
        transition:opacity 0.2s"
        title="${{gn}}"
      >${{gn}}</div>`;
    }});

    countries_hm.forEach(d => {{
      const maxS = d.genres.length > 0 ? Math.max(...d.genres.map(g2 => g2.s)) : 1;
      const label = d.flag + ' ' + (d.country.length > 14 ? d.country.substring(0,14)+'…' : d.country);
      html += `<div style="font-size:11px;font-weight:600;color:var(--t1);display:flex;align-items:center;padding:0 4px;height:${{cellH}}px;white-space:nowrap">${{label}}</div>`;
      GENRES_HM.forEach((gn, gi) => {{
        const found = d.genres.find(g2 => g2.g === gn);
        const s = found ? found.s : 0;
        const intensity = s > 0 ? Math.max(0.15, Math.min(1, s / maxS)) : 0;
        const baseC = getColor(gn);
        const isDim = activeGi !== null && gi !== activeGi;
        let bgStyle, txtColor;
        if (s > 0) {{
          const r = parseInt(baseC.slice(1,3)||'60',16);
          const g2 = parseInt(baseC.slice(3,5)||'a5',16);
          const b  = parseInt(baseC.slice(5,7)||'fa',16);
          const alpha = isDim ? 0.06 : intensity;
          bgStyle = `rgba(${{r}},${{g2}},${{b}},${{alpha}})`;
          txtColor = isDim ? 'transparent' : textOn(baseC, intensity);
        }} else {{
          bgStyle = cssVar('--bg4');
          txtColor = isDim ? 'transparent' : cssVar('--t4');
        }}
        const dimBorder = isDim ? '' : (s > 0 ? `1.5px solid ${{baseC}}44` : '');
        html += `<div
          style="height:${{cellH}}px;background:${{bgStyle}};border-radius:5px;
                 display:flex;align-items:center;justify-content:center;
                 font-size:10px;font-weight:700;color:${{txtColor}};
                 border:${{dimBorder || 'none'}};
                 transition:opacity 0.2s,background 0.2s;"
          title="${{gn}} – ${{d.country}}: ${{s>0?fmt(s):'–'}}"
        >${{s>0?fmt(s):'–'}}</div>`;
      }});
    }});
    html += '</div>';
    return html;
  }};

  window.activeGi = null;
  hmEl.innerHTML = window.buildHeatmap(null);
}}

// Initialize Dashboard
const activePill = document.querySelector('.tpill.active');
const defaultDays = activePill ? activePill.dataset.days : "7";
updateRegionalDashboard(defaultDays);

// Time filter click listeners
document.querySelectorAll('.tpill').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tpill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    updateRegionalDashboard(btn.dataset.days);
  }});
}});

// Region filter click listener (setup once)
document.querySelectorAll('.fbtn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (typeof window.renderCards === 'function') {{
      window.renderCards(btn.dataset.region);
    }}
  }});
}});

// Heatmap Legend click listener (setup once)
const hmLegend = document.getElementById('hm-legend');
hmLegend.style.cursor = 'pointer';
hmLegend.addEventListener('click', e => {{
  const chip = e.target.closest('.hm-chip');
  if (!chip) return;
  const gi = parseInt(chip.dataset.gi);
  const hmEl = document.getElementById('heatmap');
  if (window.activeGi === gi) {{
    window.activeGi = null;
    hmLegend.querySelectorAll('.hm-chip').forEach(c => {{
      c.style.opacity = '1';
      c.style.boxShadow = 'none';
    }});
  }} else {{
    window.activeGi = gi;
    hmLegend.querySelectorAll('.hm-chip').forEach((c, i) => {{
      c.style.opacity = i === gi ? '1' : '0.35';
      c.style.boxShadow = i === gi ? `0 0 0 2px ${{getColor(currentGenresHm[gi])}}` : 'none';
    }});
  }}
  if (typeof window.buildHeatmap === 'function') {{
    hmEl.innerHTML = window.buildHeatmap(window.activeGi);
  }}
}});

</script>
"""

def render_genre_analysis():
    # Fetch all payloads eagerly to allow instant interactive switching in HTML/JS
    payload_7 = get_genre_analysis_data(7)
    payload_15 = get_genre_analysis_data(15)
    payload_30 = get_genre_analysis_data(30)

    if not payload_7 and not payload_15 and not payload_30:
        st.warning("No data available for Genre Analysis.")
        return

    payloads = {
        "7": payload_7 or {},
        "15": payload_15 or {},
        "30": payload_30 or {}
    }

    tab1, tab2 = st.tabs(["Overview", "Regional Analysis"])
    dark_mode = st.session_state.get("dark_mode", False)

    with tab1:
        html_content = _build_html(payloads, dark_mode)
        components.html(html_content, height=1400, scrolling=True)

    with tab2:
        regional_html_content = _build_regional_html(payloads, dark_mode)
        components.html(regional_html_content, height=850, scrolling=True)

