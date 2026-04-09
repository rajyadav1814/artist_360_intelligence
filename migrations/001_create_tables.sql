-- Migration 001: Create core tables for kworb scraper

CREATE TABLE IF NOT EXISTS artists (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    profile_url         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS itunes_artist_rankings (
    id                  SERIAL PRIMARY KEY,
    artist_id           INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    rank                INTEGER NOT NULL,
    rank_change         VARCHAR(20),          -- e.g. '+3', '-1', '=', 'NEW'
    total_points        INTEGER,
    itunes_points       INTEGER,
    spotify_points      INTEGER,
    apple_music_points  INTEGER,
    shazam_points       INTEGER,
    youtube_points      INTEGER,
    other_points        INTEGER,
    top_country         VARCHAR(100),
    num_countries       INTEGER,
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scrape_date         DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS spotify_artists (
    id                  SERIAL PRIMARY KEY,
    artist_id           INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    monthly_listeners   BIGINT,
    peak_listeners      BIGINT,
    peak_date           DATE,
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scrape_date         DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS trending_artists_monthly (
    id                  SERIAL PRIMARY KEY,
    artist_id           INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    source              VARCHAR(50) NOT NULL,   -- 'itunes_global', 'spotify'
    rank                INTEGER NOT NULL,
    rank_change         VARCHAR(20),
    total_points        INTEGER,
    top_country         VARCHAR(100),
    month               CHAR(7) NOT NULL,       -- 'YYYY-MM'
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (artist_id, source, month)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id          SERIAL PRIMARY KEY,
    source      VARCHAR(100) NOT NULL,
    status      VARCHAR(20)  NOT NULL DEFAULT 'started',  -- 'started','success','failed'
    rows_upserted INTEGER DEFAULT 0,
    error_msg   TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_itunes_rank_date   ON itunes_artist_rankings(scrape_date, rank);
CREATE INDEX IF NOT EXISTS idx_trending_month     ON trending_artists_monthly(month, rank);
CREATE INDEX IF NOT EXISTS idx_artist_name        ON artists(name);
