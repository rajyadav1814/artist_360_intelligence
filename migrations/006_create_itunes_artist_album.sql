-- Migration 006: Add iTunes Worldwide Artist Album daily chart table

CREATE TABLE IF NOT EXISTS itunes_artist_album (
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
    label VARCHAR(255),
    rank_change VARCHAR(50),
    UNIQUE (date, country, rank, artist_title)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_itunes_artist_album_date ON itunes_artist_album(date, country);
CREATE INDEX IF NOT EXISTS idx_itunes_artist_album_label ON itunes_artist_album(label);
