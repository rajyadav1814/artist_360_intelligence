import json
from datetime import datetime
import pandas as pd
import streamlit as st
from src.database.connection import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)

def classify_label(label_str):
    """Categorize raw label names into one of the 5 major groups."""
    if not label_str:
        return 'Other/Indie'
    
    label_lower = label_str.lower().strip()
    
    # 1. Sony Music
    if any(x in label_lower for x in ['sony', 'columbia', 'epic', 'rca', 'arista', 'bad boy', 'legacy', 'som livre', 'ultra', 'provident', 'clodio music']):
        return 'Sony Music'
        
    # 2. Universal Music
    if any(x in label_lower for x in ['universal', 'umg', 'republic', 'interscope', 'def jam', 'island', 'capitol', 'geffen', 'motown', 'virgin', 'emi', 'bighit', 'hybe', 'mca', 'polydor', 'mercury', 'astralwerks']):
        return 'Universal Music'
        
    # 3. Warner Music
    if any(x in label_lower for x in ['warner', 'wmg', 'atlantic', 'parlophone', 'elektra', 'reprise', 'nonesuch', 'roadrunner', 'asylum', 'spinnin', 'shady']):
        return 'Warner Music'
        
    # 4. Independent
    if any(x in label_lower for x in ['independent', 'indie', 'self-released', 'distrokid', 'tunecore', 'cd baby', 'unitedmasters', 'ditto', 'routenote', 'believe', 'ada', 'ingrooves', 'awal']):
        return 'Independent'
        
    # Default to Other/Indie
    return 'Other/Indie'

def fmt_kpi(val):
    """Format large numbers for display in KPI cards."""
    if val >= 1e9: 
        return f"{val/1e9:.2f}B"
    if val >= 1e6: 
        return f"{val/1e6:.2f}M"
    if val >= 1e3: 
        return f"{val/1e3:.0f}K"
    return str(val)

@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    """Load latest 14 days of data from database."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Load Spotify global data
            spotify_query = """
                SELECT date, rank, artist_title, streams, label 
                FROM spotify_daily
                WHERE country = 'global'
                  AND date >= (SELECT MAX(date) FROM spotify_daily WHERE country = 'global') - INTERVAL '13 days'
            """
            cur.execute(spotify_query)
            rows_sp = cur.fetchall()
            df_spotify = pd.DataFrame([dict(r) for r in rows_sp]) if rows_sp else pd.DataFrame(columns=['date', 'rank', 'artist_title', 'streams', 'label'])
            
            # Load iTunes worldwide data
            itunes_query = """
                SELECT date, rank, artist_title, points, label 
                FROM itunes_daily
                WHERE country = 'ww'
                  AND date >= (SELECT MAX(date) FROM itunes_daily WHERE country = 'ww') - INTERVAL '13 days'
            """
            cur.execute(itunes_query)
            rows_it = cur.fetchall()
            df_itunes = pd.DataFrame([dict(r) for r in rows_it]) if rows_it else pd.DataFrame(columns=['date', 'rank', 'artist_title', 'points', 'label'])
            
            return df_spotify, df_itunes
    except Exception as e:
        logger.error(f"Error loading label analysis data: {e}")
        return pd.DataFrame(), pd.DataFrame()
    finally:
        conn.close()


def render_label_analysis():
    """Render the Label Analysis dashboard with dynamic data."""
    df_spotify, df_itunes = load_data()
    
    if df_spotify.empty and df_itunes.empty:
        st.info("ℹ️ No daily data found in spotify_daily and itunes_daily tables. Please run the scrapers to populate these tables.")
        return

    # Map labels
    if not df_spotify.empty:
        df_spotify['label_group'] = df_spotify['label'].apply(classify_label)
        df_spotify['date'] = pd.to_datetime(df_spotify['date']).dt.date
    else:
        df_spotify = pd.DataFrame(columns=['date', 'rank', 'artist_title', 'streams', 'label', 'label_group'])

    if not df_itunes.empty:
        df_itunes['label_group'] = df_itunes['label'].apply(classify_label)
        df_itunes['date'] = pd.to_datetime(df_itunes['date']).dt.date
    else:
        df_itunes = pd.DataFrame(columns=['date', 'rank', 'artist_title', 'points', 'label', 'label_group'])

    # Determine unique dates
    unique_dates_sorted = sorted(list(set(df_spotify['date'].unique()).union(set(df_itunes['date'].unique()))))
    if not unique_dates_sorted:
        st.info("ℹ️ No daily data found. Please run the scrapers to populate the tables.")
        return
        
    dates_js = [d.strftime('%b %d') for d in unique_dates_sorted]
    
    # Split dates into Wk A and Wk B
    mid = len(unique_dates_sorted) // 2
    wkA_dates = unique_dates_sorted[:mid]
    wkB_dates = unique_dates_sorted[mid:]
    
    # Standard label order and colors
    LABELS_ORDER = ['Other/Indie', 'Independent', 'Universal Music', 'Sony Music', 'Warner Music']
    LABEL_COLORS = {
      'Sony Music': '#fb7185',
      'Universal Music': '#c4b5fd',
      'Warner Music': '#fcd34d',
      'Independent': '#34d399',
        'Other/Indie': '#60a5fa'
    }
    
    # ── SP_DATA & IT_DATA ─────────────────────────────
    sp_data = {}
    total_sp_streams = int(df_spotify['streams'].sum()) if not df_spotify.empty else 0
    for lg in LABELS_ORDER:
        lg_df = df_spotify[df_spotify['label_group'] == lg] if not df_spotify.empty else pd.DataFrame()
        if not lg_df.empty:
            streams = int(lg_df['streams'].sum())
            tracks = int(lg_df['artist_title'].nunique())
            best_rank = int(lg_df['rank'].min())
            wkA = int(lg_df[lg_df['date'].isin(wkA_dates)]['streams'].sum())
            wkB = int(lg_df[lg_df['date'].isin(wkB_dates)]['streams'].sum())
            share = round((streams / total_sp_streams) * 100, 1) if total_sp_streams > 0 else 0.0
        else:
            streams, tracks, best_rank, wkA, wkB, share = 0, 0, 100, 0, 0, 0.0
            
        sp_data[lg] = {
            "streams": streams,
            "tracks": tracks,
            "bestRank": best_rank,
            "wkA": wkA,
            "wkB": wkB,
            "share": share
        }
        
    it_data = {}
    total_it_score = int(df_itunes['points'].sum()) if not df_itunes.empty else 0
    for lg in LABELS_ORDER:
        lg_df = df_itunes[df_itunes['label_group'] == lg] if not df_itunes.empty else pd.DataFrame()
        if not lg_df.empty:
            score = int(lg_df['points'].sum())
            tracks = int(lg_df['artist_title'].nunique())
            best_rank = int(lg_df['rank'].min())
            share = round((score / total_it_score) * 100, 1) if total_it_score > 0 else 0.0
        else:
            score, tracks, best_rank, share = 0, 0, 100, 0.0
            
        it_data[lg] = {
            "score": score,
            "tracks": tracks,
            "bestRank": best_rank,
            "share": share
        }

    # ── DAILY Streams ───────────────────────────────
    daily = {}
    for lg in LABELS_ORDER:
        daily[lg] = []
        lg_df = df_spotify[df_spotify['label_group'] == lg] if not df_spotify.empty else pd.DataFrame()
        daily_group = lg_df.groupby('date')['streams'].sum() if not lg_df.empty else {}
        for d in unique_dates_sorted:
            val = daily_group.get(d, 0)
            daily[lg].append(int(val))
            
    # ── SP_TRACKS ───────────────────────────────────
    sp_tracks = {}
    for lg in LABELS_ORDER:
        lg_df = df_spotify[df_spotify['label_group'] == lg] if not df_spotify.empty else pd.DataFrame()
        if lg_df.empty:
            sp_tracks[lg] = []
            continue
            
        track_stats = lg_df.groupby('artist_title').agg(
            total_streams=('streams', 'sum'),
            best_rank=('rank', 'min'),
            days_charted=('date', 'nunique')
        ).reset_index()
        
        top_tracks = track_stats.sort_values('total_streams', ascending=False).head(15)
        
        tracks_list = []
        for _, row in top_tracks.iterrows():
            t_title = row['artist_title']
            parts = t_title.split(' - ', 1)
            artist = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else t_title
            
            # Remove parenthetical info if title gets too long (aesthetic cleanup)
            if len(title) > 28 and '(' in title:
                title = title.split('(')[0].strip()
            
            track_df = lg_df[lg_df['artist_title'] == t_title]
            latest_date = track_df['date'].max()
            latest_streams = int(track_df[track_df['date'] == latest_date]['streams'].sum())
            
            wkA_str = track_df[track_df['date'].isin(wkA_dates)]['streams'].sum()
            wkB_str = track_df[track_df['date'].isin(wkB_dates)]['streams'].sum()
            
            len_wkA = len(wkA_dates)
            len_wkB = len(wkB_dates)
            avg_wkA = wkA_str / len_wkA if len_wkA > 0 else 0
            avg_wkB = wkB_str / len_wkB if len_wkB > 0 else 0
            
            if avg_wkA > 0:
                growth = round(((avg_wkB - avg_wkA) / avg_wkA) * 100, 1)
            else:
                growth = 100.0 if avg_wkB > 0 else 0.0
                
            tracks_list.append({
                "t": title,
                "a": artist,
                "s": int(row['total_streams']),
                "r": int(row['best_rank']),
                "l": latest_streams,
                "g": growth,
                "d": int(row['days_charted'])
            })
        sp_tracks[lg] = tracks_list
        
    # ── IT_TRACKS ───────────────────────────────────
    it_tracks = {}
    for lg in LABELS_ORDER:
        lg_df = df_itunes[df_itunes['label_group'] == lg] if not df_itunes.empty else pd.DataFrame()
        if lg_df.empty:
            it_tracks[lg] = []
            continue
            
        track_stats = lg_df.groupby('artist_title').agg(
            total_score=('points', 'sum'),
            best_rank=('rank', 'min')
        ).reset_index()
        
        top_tracks = track_stats.sort_values('total_score', ascending=False).head(10)
        
        tracks_list = []
        for _, row in top_tracks.iterrows():
            t_title = row['artist_title']
            parts = t_title.split(' - ', 1)
            artist = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else t_title
            
            if len(title) > 28 and '(' in title:
                title = title.split('(')[0].strip()
                
            track_df = lg_df[lg_df['artist_title'] == t_title]
            latest_date = track_df['date'].max()
            latest_score = int(track_df[track_df['date'] == latest_date]['points'].sum())
            
            tracks_list.append({
                "t": title,
                "a": artist,
                "s": int(row['total_score']),
                "r": int(row['best_rank']),
                "l": latest_score
            })
        it_tracks[lg] = tracks_list

    # ── KPI DATA Calculations ───────────────────────
    # 1. Total streams
    total_streams_str = fmt_kpi(total_sp_streams)
    total_streams_sub = f"All label groups · {len(unique_dates_sorted)} days"
    
    # 2. Top label (streams)
    sp_totals = {lg: sp_data[lg]["streams"] for lg in LABELS_ORDER}
    top_lg = max(sp_totals, key=sp_totals.get)
    top_lg_streams = sp_totals[top_lg]
    top_lg_share = sp_data[top_lg]["share"]
    top_label_str = top_lg
    top_label_color = LABEL_COLORS[top_lg]
    top_label_sub = f"{fmt_kpi(top_lg_streams)} · {top_lg_share}% share"
    
    # 3. Best rank (Spotify)
    if not df_spotify.empty:
        best_sp_row = df_spotify.loc[df_spotify['rank'].idxmin()]
        best_sp_label = best_sp_row['label_group']
        parts = best_sp_row['artist_title'].split(' - ', 1)
        best_sp_artist = parts[0].strip()
        best_rank_label = best_sp_label
        best_rank_sub = f"#{best_sp_row['rank']} · {best_sp_artist}"
    else:
        best_rank_label = "—"
        best_rank_sub = "No rank data"
        
    # 4. iTunes #1 label
    if not df_itunes.empty:
        it_track_sums = df_itunes.groupby(['artist_title', 'label_group'])['points'].sum().reset_index()
        top_it_row = it_track_sums.loc[it_track_sums['points'].idxmax()]
        itunes_no1_label = top_it_row['label_group']
        parts = top_it_row['artist_title'].split(' - ', 1)
        itunes_artist = parts[0].strip()
        itunes_title = parts[1].strip() if len(parts) > 1 else top_it_row['artist_title']
        itunes_no1_sub = f"{itunes_artist} {itunes_title[:14]}... · {fmt_kpi(top_it_row['points'])} score"
    else:
        itunes_no1_label = "—"
        itunes_no1_sub = "No iTunes data"
        
    # 5. Fastest growing label
    growths = {}
    for lg in LABELS_ORDER:
        lg_df = df_spotify[df_spotify['label_group'] == lg] if not df_spotify.empty else pd.DataFrame()
        wkA = lg_df[lg_df['date'].isin(wkA_dates)]['streams'].sum() if not lg_df.empty else 0
        wkB = lg_df[lg_df['date'].isin(wkB_dates)]['streams'].sum() if not lg_df.empty else 0
        avg_wkA = wkA / len(wkA_dates) if len(wkA_dates) > 0 else 0
        avg_wkB = wkB / len(wkB_dates) if len(wkB_dates) > 0 else 0
        growths[lg] = ((avg_wkB - avg_wkA) / avg_wkA) * 100 if avg_wkA > 0 else -999.0
        
    fastest_lg = max(growths, key=growths.get)
    fastest_growth = growths[fastest_lg]
    if fastest_growth > -999.0:
        fastest_growing_label = fastest_lg
        fastest_growing_color = LABEL_COLORS[fastest_lg]
        fastest_growing_sub = f"{'+' if fastest_growth >= 0 else ''}{fastest_growth:.1f}% Wk A→B streams"
    else:
        fastest_growing_label = "—"
        fastest_growing_color = "#ffffff"
        fastest_growing_sub = "No growth data"
        
    kpi_data = {
        "totalStreams": total_streams_str,
        "totalStreamsSub": total_streams_sub,
        "topLabel": top_label_str,
        "topLabelColor": top_label_color,
        "topLabelSub": top_label_sub,
        "bestRankLabel": best_rank_label,
        "bestRankSub": best_rank_sub,
        "itunesNo1Label": itunes_no1_label,
        "itunesNo1Sub": itunes_no1_sub,
        "fastestGrowingLabel": fastest_growing_label,
        "fastestGrowingColor": fastest_growing_color,
        "fastestGrowingSub": fastest_growing_sub
    }
    
    # Date Range text details
    min_date_str = min(unique_dates_sorted).strftime("%b %d")
    max_date_str = max(unique_dates_sorted).strftime("%b %d, %Y")
    date_range_label = f"Chromadata · Label Intelligence"
    
    # Week buttons text
    if wkA_dates:
      wkA_range_label = f"Wk A · {min(wkA_dates).strftime('%b %d')}–{max(wkA_dates).strftime('%b %d')}"
    else:
      wkA_range_label = "Wk A · No data"

    if wkB_dates:
      wkB_range_label = f"Wk B · {min(wkB_dates).strftime('%b %d')}–{max(wkB_dates).strftime('%b %d')}"
    else:
      wkB_range_label = "Wk B · No data"
    
    # ── HTML TEMPLATE ─────────────────────────────────
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Label Market Dashboard</title>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap">
        <style>
        *{box-sizing:border-box;margin:0;padding:0}
        :root{
          --bg:#0d1117;
          --bg2:#161b26;
          --bg3:#1f2633;
          --bg4:#283041;
          --border:rgba(148,163,184,.15);
          --border2:rgba(148,163,184,.28);
          --t1:#ffffff;
          --t2:#cdd6e4;
          --t3:#8b95ad;
          
          --green:#34d399;--gd:rgba(52,211,153,.18);
          --red:#fb7185;--rd:rgba(251,113,133,.18);
          --blue:#60a5fa;--bd:rgba(96,165,250,.18);
          --purple:#c4b5fd;--amber:#fcd34d;--teal:#5eead4;--pink:#f9a8d4;
          --sony:#fb7185;--umg:#c4b5fd;--wmg:#fcd34d;--indie:#34d399;--other:#60a5fa;
        }
        body{
          background: linear-gradient(180deg,#0d1117 0%,#161b26 100%);
          font-family:'Inter',system-ui,sans-serif;
          color:var(--t1);
          font-size:13px;
          overflow-x:hidden;
          padding-bottom:30px;
          animation: fadeIn 0.5s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

          .hdr {
            margin: 14px 18px 0;
            padding: 0;
          }
        .hdr-row{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;position:relative;z-index:2;}
        .brand{
          font-size:10px;
          font-weight:800;
          color:var(--t3);
          letter-spacing:2px;
          text-transform:uppercase;
          display:flex;
          align-items:center;
          gap:6px;
          margin-bottom:8px;
        }
        .live{
          width:8px;
          height:8px;
          border-radius:50%;
          background:var(--green);
          box-shadow: 0 0 0 3px rgba(34,211,160,.15), 0 0 10px rgba(34,211,160,.5);
          animation: blink 2s infinite;
        }
        @keyframes blink{
          0%,100%{opacity:1; box-shadow: 0 0 0 3px rgba(34,211,160,.15), 0 0 10px rgba(34,211,160,.5);}
          50%{opacity:.3; box-shadow: 0 0 0 6px rgba(34,211,160,.05), 0 0 16px rgba(34,211,160,.7);}
        }
        .title{font-size:24px;font-weight:900;letter-spacing:-.03em;color:#ffffff;line-height:1.15;}
        .sub{font-size:11px;color:var(--t2);font-weight:500;margin-top:5px;letter-spacing:.02em;}
        
        .controls{display:flex;gap:6px;align-items:center;flex-wrap:wrap;position:relative;z-index:2;}
        .pill-grp{
          display:flex;
          gap:4px;
          background:rgba(13,17,23,.55);
          padding:4px;
          border-radius:12px;
          border:1px solid var(--border);
          backdrop-filter:blur(10px);
        }
        .fp{
          font-size:10px;
          font-weight:700;
          padding:7px 14px;
          border:1px solid transparent;
          border-radius:8px;
          cursor:pointer;
          background:transparent;
          color:var(--t2);
          transition:all .2s ease;
          letter-spacing:.3px;
        }
        .fp:hover{color:var(--t1);background:rgba(255,255,255,0.05);}
        .fp.on{
          color:var(--t1);
          background:linear-gradient(135deg, rgba(96,165,250,.22), rgba(196,181,253,.22));
          border-color:rgba(96,165,250,.55);
          box-shadow:0 10px 20px rgba(0,0,0,.22);
        }
        
        .plat-bar{
          display:flex;
          gap:10px;
          margin-top:0;
          padding:8px 0 12px;
          border-bottom:1px solid rgba(148,163,184,.1);
          position:relative;
          z-index:2;
        }
        .pt{
          flex:1;
          min-width:0;
          display:flex;
          align-items:center;
          justify-content:center;
          gap:8px;
          font-size:12px;
          font-weight:800;
          letter-spacing:.9px;
          text-transform:uppercase;
          padding:11px 16px;
          border:1px solid rgba(56,189,248,.25);
          border-radius:12px;
          background:linear-gradient(135deg, rgba(12,24,48,.88), rgba(20,25,66,.88));
          color:rgba(226,232,240,.92);
          cursor:pointer;
          transition:all .22s ease;
          box-shadow:inset 0 0 0 1px rgba(15,23,42,.45);
        }
        .pt-ic{
          width:16px;
          text-align:center;
          color:rgba(186,230,253,.96);
          font-size:12px;
          line-height:1;
        }
        .pt:hover{
          color:var(--t1);
          border-color:rgba(56,189,248,.55);
          background:linear-gradient(135deg, rgba(26,46,87,.9), rgba(27,38,90,.9));
          box-shadow:0 0 0 1px rgba(56,189,248,.16), 0 8px 22px rgba(3,10,22,.45);
        }
        .pt.on{
          color:var(--t1);
          border-color:rgba(56,189,248,.88);
          background:linear-gradient(135deg, rgba(27,52,94,.95), rgba(35,43,102,.92));
          box-shadow:0 0 0 1px rgba(56,189,248,.28), inset 0 -2px 0 rgba(125,211,252,.7);
        }

        .kpi-bar{
          display:grid;
          grid-template-columns:repeat(5,1fr);
          gap:12px;
          margin: 14px 18px 0;
        }
        .kpi{
          position:relative;
          background:var(--bg2);
          border:1px solid var(--border);
          border-radius:16px;
          padding:18px 18px 16px 22px;
          box-shadow:0 12px 24px rgba(0,0,0,.18);
          overflow:hidden;
          transition:all .2s ease;
        }
        .kpi:hover{transform:translateY(-2px);border-color:rgba(148,163,184,.3);box-shadow:0 16px 32px rgba(0,0,0,.22);}
        .kpi::before{
          content:"";position:absolute;left:0;top:14%;bottom:14%;width:4px;
          border-radius:0 4px 4px 0;
          background:var(--blue);
        }
        .kpi.k-blue::before{background:var(--blue);}
        .kpi.k-green::before{background:var(--green);}
        .kpi.k-purple::before{background:var(--purple);}
        .kpi.k-amber::before{background:var(--amber);}
        .kpi.k-pink::before{background:var(--pink);}
        
        .kpi-lbl{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.12em;font-weight:800;margin-bottom:10px;}
        .kpi-val{font-size:26px;font-weight:900;letter-spacing:-.02em;line-height:1.1;color:#ffffff;}
        .kpi.k-blue .kpi-val{color:var(--blue);}
        .kpi.k-green .kpi-val{color:var(--green);}
        .kpi.k-purple .kpi-val{color:var(--purple);}
        .kpi.k-amber .kpi-val{color:var(--amber);}
        .kpi.k-pink .kpi-val{color:var(--pink);}
        
        .kpi-sub{font-size:12px;color:var(--t2);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}

        .body{padding:14px 18px;display:flex;flex-direction:column;gap:14px}
        .r2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
        .r3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
        .r24{display:grid;grid-template-columns:1.6fr 1fr;gap:12px}
        .r42{display:grid;grid-template-columns:1fr 1.6fr;gap:12px}

        .card{
          background:linear-gradient(180deg, var(--bg2) 0%, var(--bg3) 100%);
          border:1px solid var(--border);
          border-radius:18px;
          padding:16px 18px;
          box-shadow:0 14px 30px rgba(0,0,0,.22);
          transition:all .25s ease;
        }
        .card:hover{
          border-color:rgba(96,165,250,.4);
          box-shadow:0 22px 40px rgba(0,0,0,.32);
          transform:translateY(-2px);
        }
        .card-ttl{
          font-size:10px;
          color:var(--t3);
          text-transform:uppercase;
          letter-spacing:1px;
          font-weight:800;
          margin-bottom:12px;
          padding-bottom:8px;
          border-bottom:1px solid var(--border);
        }

        .sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;padding:0 2px;}
        .sh-l{font-size:13px;font-weight:700;color:var(--t1);letter-spacing:-.01em;}
        .sh-r{font-size:9.5px;font-weight:700;color:var(--t2);background:rgba(13,17,23,.65);padding:3px 10px;border-radius:999px;border:1px solid var(--border);}

        .cw{position:relative;width:100%}

        /* Label selector cards */
        .label-cards{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;}
        .lc{
          background:var(--bg2);
          border:1px solid var(--border);
          border-radius:16px;
          padding:14px 16px;
          cursor:pointer;
          transition:all .25s cubic-bezier(0.4, 0, 0.2, 1);
          position:relative;
          overflow:hidden;
          box-shadow:0 12px 24px rgba(0,0,0,.18);
        }
        .lc:hover{
          border-color:var(--accent-color) !important;
          background:linear-gradient(180deg, var(--bg2) 0%, var(--bg3) 100%);
          transform:translateY(-3px);
          box-shadow:0 18px 36px rgba(0,0,0,.28);
        }
        .lc.on{
          background:linear-gradient(180deg, rgba(22,27,38,1) 0%, rgba(31,38,51,1) 100%);
          border-color:var(--accent-color) !important;
          box-shadow: 0 14px 32px rgba(0, 0, 0, 0.35);
        }
        .lc::before{
          content:'';position:absolute;top:0;left:0;right:0;height:3px;
          background:var(--accent-color);
        }
        .lc-name{font-size:11px;font-weight:800;color:var(--accent-color);letter-spacing:.5px;margin-bottom:4px;}
        .lc-streams{font-size:18px;font-weight:900;letter-spacing:-.02em;margin-bottom:3px;color:#ffffff;}
        .lc-sub{font-size:10px;color:var(--t2);margin-bottom:6px;}
        .lc-share{font-size:11.5px;font-weight:800;margin-top:6px;display:flex;align-items:center;gap:4px;}

        /* Track list */
        .trk-hdr{display:grid;gap:6px;padding:4px 6px;border-bottom:1px solid var(--border);margin-bottom:4px}
        .trk-hdr span{font-size:8.5px;color:var(--t3);text-transform:uppercase;letter-spacing:.8px;font-weight:700;}
        .trk{display:grid;gap:6px;padding:8px 10px;border-bottom:1px solid rgba(148,163,184,.04);align-items:center;cursor:pointer;transition:all 0.15s ease;border-radius:8px;}
        .trk:hover{background:rgba(96,165,250,.08);transform:scale(1.005);}
        .trk:last-child{border-bottom:none}
        .rn{font-size:11px;color:var(--t3);text-align:center;font-weight:700;}
        .tn{font-size:12px;font-weight:600;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .ta{font-size:10px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
        .tv{font-size:11.5px;color:var(--t2);text-align:right;white-space:nowrap;font-weight:600;}
        .g{color:var(--green)}.r{color:var(--red)}.a{color:var(--amber)}.b{color:var(--blue)}.p{color:var(--purple)}

        /* Growth badge */
        .gb{display:inline-flex;align-items:center;justify-content:center;font-size:8.5px;font-weight:800;padding:3px 6px;border-radius:4px;min-width:44px;letter-spacing:0.2px;}
        .gb-up{background:var(--gd);color:var(--green);border:1px solid rgba(52,211,153,.22);}
        .gb-dn{background:var(--rd);color:var(--red);border:1px solid rgba(251,113,133,.22);}

        /* vel bar */
        .vb{height:3.5px;background:rgba(255,255,255,0.03);border-radius:2px;margin-top:4px;overflow:hidden;}
        .vbf{height:100%;border-radius:2px}
        /* Scrollable track list */
        #sp-track-list::-webkit-scrollbar,#it-track-list::-webkit-scrollbar{width:4px}
        #sp-track-list::-webkit-scrollbar-track,#it-track-list::-webkit-scrollbar-track{background:var(--bg3);border-radius:2px}
        #sp-track-list::-webkit-scrollbar-thumb,#it-track-list::-webkit-scrollbar-thumb{background:rgba(148,163,184,.2);border-radius:2px}
        #sp-track-list::-webkit-scrollbar-thumb:hover,#it-track-list::-webkit-scrollbar-thumb:hover{background:rgba(148,163,184,.4)}

        /* Label market share bar */
        .mkt-row{display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.01);}
        .mkt-row:last-child{border-bottom:none;}
        .mkt-label{font-size:11px;color:var(--t1);min-width:95px;font-weight:600;}
        .mkt-bar-bg{flex:1;height:6px;background:var(--bg4);border-radius:3px;overflow:hidden}
        .mkt-bar-fg{height:100%;border-radius:3px}
        .mkt-pct{font-size:11.5px;font-weight:700;min-width:38px;text-align:right}
        .mkt-tracks{font-size:9.5px;color:var(--t3);min-width:54px;text-align:right;font-weight:600;}

        /* WoW change row */
        .wk-row{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid rgba(148,163,184,.06);}
        .wk-row:last-child{border-bottom:none}

        /* Platform pane */
        .pane{display:none}
        .pane.on{display:flex;flex-direction:column;gap:14px}

        /* Week over week arrows */
        .arr-up{color:var(--green);font-size:10px}
        .arr-dn{color:var(--red);font-size:10px}
        </style>
    </head>
    <body>

    <div class="plat-bar" style="margin:14px 18px 0">
      <button class="pt on" onclick="setPlatform('spotify',this)"><span class="pt-ic">&#9835;</span><span>SPOTIFY GLOBAL</span></button>
      <button class="pt" onclick="setPlatform('itunes',this)"><span class="pt-ic">&#9679;</span><span>ITUNES WW</span></button>
      <button class="pt" onclick="setPlatform('compare',this)"><span class="pt-ic">&#9673;</span><span>CROSS-PLATFORM</span></button>
    </div>

    <!-- KPI bar -->
    <div class="kpi-bar" id="kpi-bar">
      <div class="kpi k-blue"><div class="kpi-lbl">Total streams tracked</div><div class="kpi-val" id="kpi-val-1">...</div><div class="kpi-sub" id="kpi-sub-1">...</div></div>
      <div class="kpi k-pink"><div class="kpi-lbl">Top label (streams)</div><div class="kpi-val" id="kpi-val-2">...</div><div class="kpi-sub" id="kpi-sub-2">...</div></div>
      <div class="kpi k-green"><div class="kpi-lbl">Best rank (Spotify)</div><div class="kpi-val" id="kpi-val-3" style="font-size:13px;margin-top:3px">...</div><div class="kpi-sub" id="kpi-sub-3">...</div></div>
      <div class="kpi k-purple"><div class="kpi-lbl">iTunes #1 label</div><div class="kpi-val" id="kpi-val-4" style="font-size:13px;margin-top:3px">...</div><div class="kpi-sub" id="kpi-sub-4">...</div></div>
      <div class="kpi k-amber"><div class="kpi-lbl">Fastest growing label</div><div class="kpi-val" id="kpi-val-5">...</div><div class="kpi-sub" id="kpi-sub-5">...</div></div>
    </div>

    <div class="body">

      <!-- Label selector -->
      <div class="label-cards" id="label-cards"></div>

      <!-- SPOTIFY pane -->
      <div id="pane-spotify" class="pane on">
        <div class="r24">
          <div class="card">
            <div class="card-ttl">Spotify global — daily streams by label group <span style="float:right;font-size:9px;font-weight:700;color:var(--t2);background:rgba(13,17,23,.65);padding:2px 8px;border-radius:999px;border:1px solid var(--border)">Live Window</span></div>
            <div class="cw" style="height:240px"><canvas id="spTrendChart"></canvas></div>
          </div>
          <div class="card">
            <div class="card-ttl">Market share — streams <span style="float:right;font-size:9px;font-weight:700;color:var(--t2);background:rgba(13,17,23,.65);padding:2px 8px;border-radius:999px;border:1px solid var(--border)">Total window</span></div>
            <div style="margin-bottom:10px" id="mkt-share-sp"></div>
            <div style="border-top:1px solid var(--border);padding-top:12px;margin-top:4px">
              <div class="card-ttl" style="margin-bottom:8px">Week-over-week shift</div>
              <div id="wow-sp"></div>
            </div>
          </div>
        </div>

        <div class="r2">
          <div class="card">
            <div class="card-ttl" id="sp-roster-title">Selected label — Spotify top tracks</div>
            <div class="trk-hdr" style="grid-template-columns:18px 1fr 64px 56px 56px 46px">
              <span></span><span>Track</span><span style="text-align:right">Streams</span><span style="text-align:right">Best Rank</span><span style="text-align:right">Growth</span><span style="text-align:right">Days</span>
            </div>
            <div id="sp-track-list" style="max-height:480px;overflow-y:auto;padding-right:4px;"></div>
          </div>
          <div class="card">
            <div class="card-ttl">Label stream comparison — Latest Snapshot <span style="float:right;font-size:9px;font-weight:700;color:var(--t2);background:rgba(13,17,23,.65);padding:2px 8px;border-radius:999px;border:1px solid var(--border)">Daily snapshot</span></div>
            <div class="cw" style="height:280px"><canvas id="spBarChart"></canvas></div>
            <div style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px">
              <div class="card-ttl" style="margin-bottom:8px">Track count by label</div>
              <div class="cw" style="height:200px"><canvas id="trackCountChart"></canvas></div>
            </div>
          </div>
        </div>
      </div>

      <!-- ITUNES pane -->
      <div id="pane-itunes" class="pane">
        <div class="r24">
          <div class="card">
            <div class="card-ttl">iTunes WW — cumulative score by label group <span style="float:right;font-size:9px;font-weight:700;color:var(--t2);background:rgba(13,17,23,.65);padding:2px 8px;border-radius:999px;border:1px solid var(--border)">Total window</span></div>
            <div class="cw" style="height:240px"><canvas id="itTrendChart"></canvas></div>
          </div>
          <div class="card">
            <div class="card-ttl">iTunes market share — score <span style="float:right;font-size:9px;font-weight:700;color:var(--t2);background:rgba(13,17,23,.65);padding:2px 8px;border-radius:999px;border:1px solid var(--border)">Live Window</span></div>
            <div id="mkt-share-it"></div>
          </div>
        </div>

        <div class="r2">
          <div class="card">
            <div class="card-ttl" id="it-roster-title">Selected label — iTunes WW top tracks</div>
            <div class="trk-hdr" style="grid-template-columns:18px 1fr 70px 56px 56px">
              <span></span><span>Track</span><span style="text-align:right">Total Score</span><span style="text-align:right">Best Rank</span><span style="text-align:right">Latest Score</span>
            </div>
            <div id="it-track-list" style="max-height:480px;overflow-y:auto;padding-right:4px;"></div>
          </div>
          <div class="card">
            <div class="card-ttl">iTunes label scorecard — tracks × avg score</div>
            <div class="cw" style="height:260px"><canvas id="itBubbleChart"></canvas></div>
          </div>
        </div>
      </div>

      <!-- COMPARE pane -->
      <div id="pane-compare" class="pane">
        <div class="r2">
          <div class="card">
            <div class="card-ttl">Cross-platform index — Spotify streams vs iTunes score (normalised)</div>
            <div class="cw" style="height:260px"><canvas id="crossChart"></canvas></div>
          </div>
          <div class="card">
            <div class="card-ttl">Label health matrix <span style="float:right;font-size:9px;font-weight:700;color:var(--t2);background:rgba(13,17,23,.65);padding:2px 8px;border-radius:999px;border:1px solid var(--border)">Both platforms</span></div>
            <div id="health-matrix"></div>
          </div>
        </div>
        <div class="r3">
          <div class="card"><div class="card-ttl">Sony Music — top 5 cross-platform</div><div id="cross-sony"></div></div>
          <div class="card"><div class="card-ttl">Universal Music — top 5 cross-platform</div><div id="cross-umg"></div></div>
          <div class="card"><div class="card-ttl">Warner Music — top 5 cross-platform</div><div id="cross-wmg"></div></div>
        </div>
      </div>

    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
    <script>
    // ── Real data ─────────────────────────────────────────
    const LABEL_COLORS={
      'Sony Music':'#fb7185','Universal Music':'#c4b5fd',
      'Warner Music':'#fcd34d','Independent':'#34d399','Other/Indie':'#60a5fa'
    };
    const LABELS_ORDER=['Other/Indie','Independent','Universal Music','Sony Music','Warner Music'];

    const SP_DATA = __SP_DATA__;
    const IT_DATA = __IT_DATA__;
    const DATES = __DATES__;
    const DAILY = __DAILY__;
    const SP_TRACKS = __SP_TRACKS__;
    const IT_TRACKS = __IT_TRACKS__;
    const KPI_DATA = __KPI_DATA__;

    // ── State ────────────────────────────────────────────
    let activePlatform='spotify';
    let activePeriod='all';
    let activeLabel=null;
    let spTrendChart=null,itTrendChart=null,spBarChart=null,trackCountChart=null,crossChart=null,itBubbleChart=null;

    function fmtN(n,d=1){if(!n&&n!==0)return'—';const a=Math.abs(n);if(a>=1e9)return(n/1e9).toFixed(d)+'B';if(a>=1e6)return(n/1e6).toFixed(d)+'M';if(a>=1e3)return(n/1e3).toFixed(0)+'K';return Math.round(n).toLocaleString();}
    function gbadge(g){const cls=g>=0?'gb-up':'gb-dn';return`<span class="gb ${cls}">${g>=0?'+':''}${g}%</span>`;}

    const CDARK={responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(255, 255, 255, 0.04)'},ticks:{color:'#8b95ad',font:{size:9}}},y:{grid:{color:'rgba(255, 255, 255, 0.04)'},ticks:{color:'#8b95ad',font:{size:9}}}}};

    // ── Label selector cards ──────────────────────────────
    function buildLabelCards(){
      const el=document.getElementById('label-cards');
      el.innerHTML='';
      const isIt=activePlatform==='itunes';
      LABELS_ORDER.forEach(lg=>{
        const d=isIt?IT_DATA[lg]:SP_DATA[lg];
        const col=LABEL_COLORS[lg];
        const wowPct=!isIt&&SP_DATA[lg].wkA?((SP_DATA[lg].wkB-SP_DATA[lg].wkA)/SP_DATA[lg].wkA*100).toFixed(1):null;
        const on=activeLabel===lg?'on':'';
        el.innerHTML+=`<div class="lc ${on}" style="border-color:${on?col:'var(--border)'}; --accent-color:${col};"
          onclick="selectLabel('${lg}')">
          <div class="lc-name">${lg}</div>
          <div class="lc-streams">${isIt?fmtN(d.score):fmtN(d.streams)}</div>
          <div class="lc-sub">${isIt?d.tracks+' tracks · Best #'+d.bestRank:d.tracks+' tracks · Best #'+d.bestRank}</div>
          ${!isIt&&wowPct?`<div class="lc-share" style="color:${parseFloat(wowPct)>=0?'var(--green)':'var(--red)'}">${parseFloat(wowPct)>=0?'▲':'▼'}${Math.abs(wowPct)}% WkA→WkB</div>`:''}
          <div class="lc-share" style="color:${col};font-weight:600;margin-top:3px">${d.share}% share</div>
        </div>`;
      });
    }

    function selectLabel(lg){
      activeLabel=lg;
      buildLabelCards();
      renderSpTracks(lg);
      renderItTracks(lg);
    }

    // ── Market share bars ─────────────────────────────────
    function buildMktShare(elId,data,key){
      const el=document.getElementById(elId);
      const total=Object.values(data).reduce((s,d)=>s+(d[key]||0),0);
      el.innerHTML='';
      LABELS_ORDER.forEach(lg=>{
        const d=data[lg]||{};
        const v=d[key]||0;
        const pct=total > 0 ? (v/total*100).toFixed(1) : "0.0";
        const col=LABEL_COLORS[lg];
        el.innerHTML+=`<div class="mkt-row">
          <span class="mkt-label" style="color:${col};font-size:10px;font-weight:600">${lg}</span>
          <div class="mkt-bar-bg"><div class="mkt-bar-fg" style="width:${pct}%;background:${col}"></div></div>
          <span class="mkt-pct" style="color:${col}">${pct}%</span>
          <span class="mkt-tracks">${d.tracks||0} tracks</span>
        </div>`;
      });
    }

    // ── WoW ──────────────────────────────────────────────
    function buildWoW(){
      const el=document.getElementById('wow-sp');
      el.innerHTML='';
      LABELS_ORDER.forEach(lg=>{
        const d=SP_DATA[lg];
        const pct=d.wkA?((d.wkB-d.wkA)/d.wkA*100).toFixed(1):null;
        if(!pct)return;
        const up=parseFloat(pct)>=0;
        el.innerHTML+=`<div class="wk-row">
          <span style="font-size:11px;color:${LABEL_COLORS[lg]};font-weight:600;min-width:110px">${lg}</span>
          <span style="font-size:10px;color:var(--t3);flex:1">WkA: ${fmtN(d.wkA)} → WkB: ${fmtN(d.wkB)}</span>
          <span style="font-size:11px;font-weight:700;color:${up?'var(--green)':'var(--red)'}">${up?'▲':'▼'}${Math.abs(pct)}%</span>
        </div>`;
      });
    }

    // ── Spotify trend chart ───────────────────────────────
    function buildSpTrend(){
      if(spTrendChart)spTrendChart.destroy();
      const ctx=document.getElementById('spTrendChart').getContext('2d');
      spTrendChart=new Chart(ctx,{type:'line',data:{labels:DATES,datasets:LABELS_ORDER.map(lg=>({
        label:lg,data:DAILY[lg],borderColor:LABEL_COLORS[lg],
        backgroundColor:LABEL_COLORS[lg]+'18',
        borderWidth:1.5,tension:.4,fill:false,pointRadius:0,
        pointHoverRadius:4,spanGaps:true,
      }))},options:{...CDARK,interaction:{mode:'index',intersect:false},
        plugins:{legend:{display:true,position:'top',labels:{color:'#8b95ad',font:{size:9},boxWidth:10,padding:8}}},
        scales:{x:{...CDARK.scales.x},y:{...CDARK.scales.y,ticks:{...CDARK.scales.y.ticks,callback:v=>fmtN(v,0).replace('+','')}}}}});
    }

    // ── Spotify bar chart ─────────────────────────────────
    function buildSpBar(){
      if(spBarChart)spBarChart.destroy();
      const ctx=document.getElementById('spBarChart').getContext('2d');
      const latestStreams={};
      LABELS_ORDER.forEach(lg => {
        const vals = DAILY[lg];
        latestStreams[lg] = vals && vals.length > 0 ? vals[vals.length - 1] : 0;
      });
      
      spBarChart=new Chart(ctx,{type:'bar',data:{labels:LABELS_ORDER,datasets:[{data:LABELS_ORDER.map(l=>latestStreams[l]),backgroundColor:LABELS_ORDER.map(l=>LABEL_COLORS[l]),borderRadius:4}]},options:{...CDARK,indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>fmtN(c.raw)+' streams'}}},scales:{x:{...CDARK.scales.x,ticks:{...CDARK.scales.x.ticks,callback:v=>fmtN(v,0).replace('+','')}},y:{...CDARK.scales.y}}}});
    }

    // ── Track count chart ─────────────────────────────────
    function buildTrackCount(){
      if(trackCountChart)trackCountChart.destroy();
      const ctx=document.getElementById('trackCountChart').getContext('2d');
      trackCountChart=new Chart(ctx,{type:'bar',data:{labels:LABELS_ORDER,datasets:[
        {label:'Spotify',data:LABELS_ORDER.map(l=>SP_DATA[l]?.tracks||0),backgroundColor:LABELS_ORDER.map(l=>LABEL_COLORS[l]+'99'),borderRadius:3},
        {label:'iTunes',data:LABELS_ORDER.map(l=>IT_DATA[l]?.tracks||0),backgroundColor:LABELS_ORDER.map(l=>LABEL_COLORS[l]+'44'),borderRadius:3},
      ]},options:{...CDARK,plugins:{legend:{display:true,position:'top',labels:{color:'#8b95ad',font:{size:9},boxWidth:8,padding:6}}},scales:{x:{...CDARK.scales.x,ticks:{...CDARK.scales.x.ticks,maxRotation:0}},y:{...CDARK.scales.y}}}});
    }

    // ── iTunes trend chart ────────────────────────────────
    function buildItTrend(){
      if(itTrendChart)itTrendChart.destroy();
      const ctx=document.getElementById('itTrendChart').getContext('2d');
      itTrendChart=new Chart(ctx,{type:'bar',data:{labels:LABELS_ORDER,datasets:[{data:LABELS_ORDER.map(l=>IT_DATA[l]?.score||0),backgroundColor:LABELS_ORDER.map(l=>LABEL_COLORS[l]),borderRadius:4}]},options:{...CDARK,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>'Score: '+c.raw.toLocaleString()}}},scales:{x:{...CDARK.scales.x},y:{...CDARK.scales.y,ticks:{...CDARK.scales.y.ticks,callback:v=>fmtN(v,0).replace('+','')}}}}});
    }

    // ── iTunes bubble chart ───────────────────────────────
    function buildItBubble(){
      if(itBubbleChart)itBubbleChart.destroy();
      const ctx=document.getElementById('itBubbleChart').getContext('2d');
      const pts=LABELS_ORDER.map(lg=>{
        const d=IT_DATA[lg];
        const avg = d.tracks > 0 ? Math.round(d.score/d.tracks) : 0;
        return{x:d.tracks,y:avg,r:Math.max(6,Math.min(20,d.score/60000)),label:lg,color:LABEL_COLORS[lg]};
      });
      itBubbleChart=new Chart(ctx,{type:'bubble',data:{datasets:pts.map(p=>({label:p.label,data:[{x:p.x,y:p.y,r:p.r}],backgroundColor:p.color+'80',borderColor:p.color}))},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${c.raw.y.toLocaleString()} avg score · ${c.raw.x} tracks`}}},scales:{x:{grid:{color:'rgba(255, 255, 255, 0.04)'},ticks:{color:'#8b95ad',font:{size:9}},title:{display:true,text:'Track count',color:'#8b95ad',font:{size:9}}},y:{grid:{color:'rgba(255, 255, 255, 0.04)'},ticks:{color:'#8b95ad',font:{size:9}},title:{display:true,text:'Avg score per track',color:'#8b95ad',font:{size:9}}}}}});
    }

    // ── Cross-platform radar ──────────────────────────────
    function buildCross(){
      if(crossChart)crossChart.destroy();
      const ctx=document.getElementById('crossChart').getContext('2d');
      const dims=['Sp Streams','It Score','Track Count','Best Rank','Growth'];
      
      const maxSp = Math.max(...LABELS_ORDER.map(lg => SP_DATA[lg].streams)) || 1;
      const maxIt = Math.max(...LABELS_ORDER.map(lg => IT_DATA[lg].score)) || 1;
      const maxTk = Math.max(...LABELS_ORDER.map(lg => SP_DATA[lg].tracks)) || 1;
      
      crossChart=new Chart(ctx,{
        type:'radar',
        data:{
          labels:dims,
          datasets:LABELS_ORDER.map(lg=>({
            label:lg,
            data:[
              Math.round(SP_DATA[lg].streams/maxSp*100),
              Math.round(IT_DATA[lg].score/maxIt*100),
              Math.round(SP_DATA[lg].tracks/maxTk*100),
              Math.round((200-SP_DATA[lg].bestRank)/200*100),
              Math.round(Math.max(0,SP_DATA[lg].wkB-SP_DATA[lg].wkA)/(SP_DATA[lg].wkA || 1)*100+50),
            ],
            borderColor:LABEL_COLORS[lg],
            backgroundColor:LABEL_COLORS[lg]+'18',
            borderWidth:1.5,
            pointBackgroundColor:LABEL_COLORS[lg],
            pointRadius:3,
          }))
        },
        options:{
          responsive:true,
          maintainAspectRatio:false,
          plugins:{
            legend:{
              display:true,
              position:'bottom',
              labels:{
                color:'#8b95ad',
                font:{size:9},
                boxWidth:10
              }
            }
          },
          scales:{
            r:{
              grid:{color:'rgba(255, 255, 255, 0.08)'},
              ticks:{display:false},
              pointLabels:{
                color:'#8b95ad',
                font:{size:9}
              },
              min:0,
              max:100
            }
          }
        }
      });

    }

    // ── Health matrix ─────────────────────────────────────
    function buildHealthMatrix(){
      const el=document.getElementById('health-matrix');
      
      const data=LABELS_ORDER.map(lg => {
        const spSh = SP_DATA[lg].share;
        const itSh = IT_DATA[lg].share;
        const wkA = SP_DATA[lg].wkA;
        const wkB = SP_DATA[lg].wkB;
        
        let wow = "0.0%";
        let wowVal = 0.0;
        if (wkA > 0) {
          wowVal = ((wkB - wkA) / wkA * 100);
          wow = (wowVal >= 0 ? "+" : "") + wowVal.toFixed(1) + "%";
        }
        
        let rating = "Stable";
        if (wowVal > 5.0) rating = "Growing";
        else if (wowVal < -5.0) rating = "Declining";
        if (spSh > 25.0 && wowVal < -10.0) rating = "Mixed";
        if (spSh < 5.0 && wowVal < -10.0) rating = "Declining";
        
        return {
          lg: lg,
          spSh: spSh.toFixed(1) + "%",
          itSh: itSh.toFixed(1) + "%",
          wow: wow,
          tracks: SP_DATA[lg].tracks + "/" + IT_DATA[lg].tracks,
          rating: rating
        };
      });
      
      el.innerHTML='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11px">'
        +'<tr style="border-bottom:1px solid var(--border2)">'
        +'<th style="text-align:left;padding:6px 8px;color:var(--t3);font-size:9px;text-transform:uppercase;letter-spacing:.4px">Label</th>'
        +'<th style="text-align:right;padding:6px 8px;color:var(--t3);font-size:9px;text-transform:uppercase;letter-spacing:.4px">Sp Share</th>'
        +'<th style="text-align:right;padding:6px 8px;color:var(--t3);font-size:9px;text-transform:uppercase;letter-spacing:.4px">It Share</th>'
        +'<th style="text-align:right;padding:6px 8px;color:var(--t3);font-size:9px;text-transform:uppercase;letter-spacing:.4px">WkA→B</th>'
        +'<th style="text-align:right;padding:6px 8px;color:var(--t3);font-size:9px;text-transform:uppercase;letter-spacing:.4px">Tracks</th>'
        +'<th style="text-align:right;padding:6px 8px;color:var(--t3);font-size:9px;text-transform:uppercase;letter-spacing:.4px">Status</th>'
        +'</tr>';
      data.forEach(d=>{
        const col=LABEL_COLORS[d.lg];
        const wowUp=d.wow.startsWith('+');
        const statusColor={'Growing':'var(--green)','Declining':'var(--red)','Stable':'var(--blue)','Mixed':'var(--amber)'}[d.rating];
        el.innerHTML+=`<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:7px 8px;color:${col};font-weight:600">${d.lg}</td>
          <td style="padding:7px 8px;text-align:right;color:var(--t2)">${d.spSh}</td>
          <td style="padding:7px 8px;text-align:right;color:var(--t2)">${d.itSh}</td>
          <td style="padding:7px 8px;text-align:right;color:${wowUp?'var(--green)':'var(--red)'};">${d.wow}</td>
          <td style="padding:7px 8px;text-align:right;color:var(--t3)">${d.tracks}</td>
          <td style="padding:7px 8px;text-align:right;"><span style="font-size:9px;font-weight:700;color:${statusColor}">${d.rating}</span></td>
        </tr>`;
      });
      el.innerHTML+='</table></div>';
    }

    // ── Cross track lists ──────────────────────────────────
    function buildCrossTrackList(elId,label,key){
      const el=document.getElementById(elId);
      const tracks=SP_TRACKS[key]||[];
      el.innerHTML='';
      if(tracks.length === 0){
        el.innerHTML = '<div style="padding:10px;text-align:center;color:var(--t3)">No tracks available</div>';
        return;
      }
      tracks.slice(0,5).forEach((t,i)=>{
        const col=LABEL_COLORS[key];
        el.innerHTML+=`<div class="trk" style="grid-template-columns:16px 1fr 56px 40px">
          <span class="rn">${i+1}</span>
          <div><div class="tn">${t.t}</div><div class="ta">${t.a}</div></div>
          <span class="tv">${fmtN(t.s)}</span>
          <span class="tv ${t.g>=0?'g':'r'}">${t.g>=0?'+':''}${t.g}%</span>
        </div>`;
      });
    }

    // ── Render track lists ────────────────────────────────
    function renderSpTracks(lg){
      const el=document.getElementById('sp-track-list');
      const ttl=document.getElementById('sp-roster-title');
      const tracks=(lg?SP_TRACKS[lg]:SP_TRACKS['Sony Music'])||[];
      ttl.textContent=`${lg||'Sony Music'} — Spotify top tracks`;
      el.innerHTML='';
      if(tracks.length === 0){
        el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--t3)">No tracks charting on Spotify for this period</div>';
        return;
      }
      const maxS=tracks.reduce((m,t)=>Math.max(m,t.s),0);
      tracks.forEach((t,i)=>{
        const pct=maxS > 0 ? Math.round(t.s/maxS*100) : 0;
        const col=lg?LABEL_COLORS[lg]:'#fb7185';
        el.innerHTML+=`<div class="trk" style="grid-template-columns:18px 1fr 64px 56px 56px 46px">
          <span class="rn">${i+1}</span>
          <div>
            <div class="tn">${t.t}</div>
            <div class="ta">${t.a}</div>
            <div class="vb"><div class="vbf" style="width:${pct}%;background:${col}"></div></div>
          </div>
          <span class="tv">${fmtN(t.s)}</span>
          <span class="tv">${t.r}</span>
          <span>${gbadge(t.g)}</span>
          <span class="tv">${t.d}d</span>
        </div>`;
      });
    }

    function renderItTracks(lg){
      const el=document.getElementById('it-track-list');
      const ttl=document.getElementById('it-roster-title');
      const tracks=(lg?IT_TRACKS[lg]:IT_TRACKS['Universal Music'])||[];
      ttl.textContent=`${lg||'Universal Music'} — iTunes WW top tracks`;
      el.innerHTML='';
      if(tracks.length === 0){
        el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--t3)">No tracks charting on iTunes for this period</div>';
        return;
      }
      tracks.forEach((t,i)=>{
        const col=lg?LABEL_COLORS[lg]:'#c4b5fd';
        el.innerHTML+=`<div class="trk" style="grid-template-columns:18px 1fr 70px 56px 56px">
          <span class="rn">${i+1}</span>
          <div><div class="tn">${t.t}</div><div class="ta">${t.a}</div></div>
          <span class="tv">${fmtN(t.s,0)}</span>
          <span class="tv">#${t.r}</span>
          <span class="tv">${fmtN(t.l,0)}</span>
        </div>`;
      });
    }

    // ── Platform switch ───────────────────────────────────
    function setPlatform(p,el){
      activePlatform=p;
      document.querySelectorAll('.pt').forEach(b=>b.classList.remove('on'));
      el.classList.add('on');
      ['spotify','itunes','compare'].forEach(id=>{
        document.getElementById('pane-'+id).classList.toggle('on',id===p);
      });
      buildLabelCards();
      if(p==='itunes'){buildMktShare('mkt-share-it',IT_DATA,'score');buildItTrend();buildItBubble();}
      if(p==='compare'){buildCross();buildHealthMatrix();buildCrossTrackList('cross-sony','Sony Music','Sony Music');buildCrossTrackList('cross-umg','Universal Music','Universal Music');buildCrossTrackList('cross-wmg','Warner Music','Warner Music');}
    }

    function setP(p,el){
      activePeriod=p;
      document.querySelectorAll('.fp').forEach(b=>b.classList.remove('on'));
      el.classList.add('on');
    }

    // ── Init ─────────────────────────────────────────────
    buildLabelCards();
    buildSpTrend();
    buildSpBar();
    buildTrackCount();
    buildMktShare('mkt-share-sp',SP_DATA,'streams');
    buildWoW();
    
    // Inject KPI dynamic data
    document.getElementById('kpi-val-1').textContent = KPI_DATA.totalStreams;
    document.getElementById('kpi-sub-1').textContent = KPI_DATA.totalStreamsSub;

    document.getElementById('kpi-val-2').textContent = KPI_DATA.topLabel;
    document.getElementById('kpi-val-2').style.color = KPI_DATA.topLabelColor;
    document.getElementById('kpi-sub-2').textContent = KPI_DATA.topLabelSub;

    document.getElementById('kpi-val-3').textContent = KPI_DATA.bestRankLabel;
    document.getElementById('kpi-sub-3').textContent = KPI_DATA.bestRankSub;

    document.getElementById('kpi-val-4').textContent = KPI_DATA.itunesNo1Label;
    document.getElementById('kpi-sub-4').textContent = KPI_DATA.itunesNo1Sub;

    document.getElementById('kpi-val-5').textContent = KPI_DATA.fastestGrowingLabel;
    document.getElementById('kpi-val-5').style.color = KPI_DATA.fastestGrowingColor;
    document.getElementById('kpi-sub-5').textContent = KPI_DATA.fastestGrowingSub;
    
    // Select first active label
    const initialLabel = 'Sony Music';
    activeLabel=initialLabel;
    buildLabelCards();
    renderSpTracks(initialLabel);
    renderItTracks(initialLabel);
    </script>
    </body>
    </html>
    """
    
    # Perform standard placeholder replacement
    html_code = html_template \
        .replace('__DATE_RANGE_LABEL__', date_range_label) \
        .replace('__LEN_UNIQUE_DATES__', str(len(unique_dates_sorted))) \
        .replace('__WKA_RANGE_LABEL__', wkA_range_label) \
        .replace('__WKB_RANGE_LABEL__', wkB_range_label) \
        .replace('__SP_DATA__', json.dumps(sp_data)) \
        .replace('__IT_DATA__', json.dumps(it_data)) \
        .replace('__DATES__', json.dumps(dates_js)) \
        .replace('__DAILY__', json.dumps(daily)) \
        .replace('__SP_TRACKS__', json.dumps(sp_tracks)) \
        .replace('__IT_TRACKS__', json.dumps(it_tracks)) \
        .replace('__KPI_DATA__', json.dumps(kpi_data))
    
    # Render with Streamlit Components
    st.components.v1.html(html_code, height=1320, scrolling=True)


def prefetch_label_data() -> None:
    """Warms up the cache for the label analysis dashboard."""
    try:
        load_data()
    except Exception as e:
        logger.error(f"Error prefetching label analysis data: {e}")

__all__ = ["render_label_analysis", "prefetch_label_data"]
