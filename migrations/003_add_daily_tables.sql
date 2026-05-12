-- Migration 003: Add daily chart tables and track metadata



CREATE TABLE IF NOT EXISTS spotify_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    country VARCHAR(50) NOT NULL,
    rank INTEGER NOT NULL,
    artist_title VARCHAR(255) NOT NULL,
    days INTEGER,
    peak INTEGER,
    streams BIGINT,
    streams_change BIGINT,
    total_streams BIGINT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (date, country, rank, artist_title)
);

CREATE TABLE IF NOT EXISTS itunes_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    country VARCHAR(50) NOT NULL,
    rank INTEGER NOT NULL,
    artist_title VARCHAR(255) NOT NULL,
    days INTEGER,
    peak INTEGER,
    points INTEGER,
    points_change INTEGER,
    total_points INTEGER,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (date, country, rank, artist_title)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_spotify_daily_date ON spotify_daily(date, country);
CREATE INDEX IF NOT EXISTS idx_itunes_daily_date ON itunes_daily(date, country);

