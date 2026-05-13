import urllib.request
from bs4 import BeautifulSoup
import pandas as pd
import sys
import os

# Add root project dir to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.database.connection import execute_query, get_connection

def create_unified_table():
    query = """
    CREATE TABLE IF NOT EXISTS kworb_unified_data (
        id SERIAL PRIMARY KEY,
        platform VARCHAR(50),
        artist_name VARCHAR(255),
        song_name VARCHAR(500),
        rank INT,
        daily_count BIGINT,
        total_count BIGINT,
        label_name VARCHAR(255),
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_kworb_unified UNIQUE (platform, artist_name, song_name)
    );
    """
    execute_query(query)
    print("Unified table 'kworb_unified_data' is ready.")

def save_to_unified_db(df):
    if df is None or df.empty:
        return
        
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    query = """
                    INSERT INTO kworb_unified_data 
                    (platform, artist_name, song_name, rank, daily_count, total_count, label_name, scraped_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (platform, artist_name, song_name) DO UPDATE SET
                    rank = EXCLUDED.rank,
                    daily_count = EXCLUDED.daily_count,
                    total_count = EXCLUDED.total_count,
                    scraped_at = CURRENT_TIMESTAMP
                    """
                    cur.execute(query, (
                        row['platform'],
                        row['artist_name'],
                        row['song_name'],
                        row.get('rank', None),
                        row.get('daily_count', None),
                        row.get('total_count', None),
                        row.get('label_name', 'N/A')
                    ))
        print(f"Successfully inserted/updated {len(df)} rows for {df['platform'].iloc[0]}.")
    except Exception as e:
        print(f"Database insertion error: {e}")
    finally:
        conn.close()

def scrape_spotify():
    url = 'https://kworb.net/spotify/country/global_daily.html'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        html = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(html, 'html.parser')
        data = []
        for row in soup.find('tbody').find_all('tr')[:50]:
            cols = row.find_all('td')
            artist_song = cols[2].text.strip()
            if ' - ' in artist_song:
                artist, song = artist_song.split(' - ', 1)
            else:
                artist, song = artist_song, artist_song
                
            daily = cols[6].text.strip().replace(',', '')
            total = cols[10].text.strip().replace(',', '')
            
            data.append({
                'platform': 'Spotify',
                'artist_name': artist,
                'song_name': song,
                'rank': None,
                'daily_count': int(daily) if daily.isdigit() else 0,
                'total_count': int(total) if total.isdigit() else 0,
                'label_name': 'N/A'
            })
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Error Spotify: {e}")
        return None

def scrape_youtube():
    url = 'https://kworb.net/youtube/'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        html = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(html, 'html.parser')
        data = []
        for row in soup.find('tbody').find_all('tr')[:50]:
            cols = row.find_all('td')
            video_title = cols[2].text.strip()
            daily = cols[3].text.strip().replace(',', '')
            
            data.append({
                'platform': 'YouTube',
                'artist_name': 'Unknown Artist', # YouTube mixes them in the title
                'song_name': video_title,
                'rank': None,
                'daily_count': int(daily) if daily.isdigit() else 0,
                'total_count': 0,
                'label_name': 'N/A'
            })
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Error YouTube: {e}")
        return None

def scrape_apple_or_itunes(url, platform_name):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        html = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(html, 'html.parser')
        data = []
        for row in soup.find('tbody').find_all('tr')[:50]:
            cols = row.find_all('td')
            rank = cols[0].text.strip()
            artist_song = cols[2].text.strip()
            if ' - ' in artist_song:
                artist, song = artist_song.split(' - ', 1)
            else:
                artist, song = artist_song, artist_song
                
            data.append({
                'platform': platform_name,
                'artist_name': artist,
                'song_name': song,
                'rank': int(rank) if rank.isdigit() else None,
                'daily_count': None,
                'total_count': None,
                'label_name': 'N/A'
            })
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Error {platform_name}: {e}")
        return None

if __name__ == "__main__":
    create_unified_table()
    
    platforms = [
        ('Spotify', scrape_spotify),
        ('YouTube', scrape_youtube),
        ('Apple Music', lambda: scrape_apple_or_itunes('https://kworb.net/apple_songs/', 'Apple Music')),
        ('iTunes', lambda: scrape_apple_or_itunes('https://kworb.net/ww/', 'iTunes'))
    ]
    
    for name, func in platforms:
        print(f"Scraping {name}...")
        df = func()
        if df is not None:
            save_to_unified_db(df)
            
    print("Unified process completed!")
