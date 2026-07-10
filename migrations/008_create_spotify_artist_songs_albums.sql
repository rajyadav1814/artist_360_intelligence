-- Migration 008: Create tables for Spotify artist songs and albums

CREATE TABLE IF NOT EXISTS spotify_artist_songs (
    id              SERIAL PRIMARY KEY,
    artist_id       INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    song_title      TEXT NOT NULL,
    total_streams   BIGINT,
    daily_streams   BIGINT,
    scrape_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (artist_id, song_title, scrape_date)
);

CREATE TABLE IF NOT EXISTS spotify_artist_albums (
    id              SERIAL PRIMARY KEY,
    artist_id       INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    album_title     TEXT NOT NULL,
    total_streams   BIGINT,
    daily_streams   BIGINT,
    scrape_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (artist_id, album_title, scrape_date)
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_spotify_artist_songs_artist  ON spotify_artist_songs(artist_id, scrape_date);
CREATE INDEX IF NOT EXISTS idx_spotify_artist_albums_artist ON spotify_artist_albums(artist_id, scrape_date);
