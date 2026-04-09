-- Migration 002: store compact artist detail snapshots from kworb profile pages

CREATE TABLE IF NOT EXISTS artist_details (
    id               SERIAL PRIMARY KEY,
    artist_id        INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    page_title       TEXT,
    snapshot_text    VARCHAR(64),
    songs_count      INTEGER NOT NULL DEFAULT 0,
    albums_count     INTEGER NOT NULL DEFAULT 0,
    countries_count  INTEGER NOT NULL DEFAULT 0,
    top_songs        TEXT,
    top_albums       TEXT,
    top_countries    TEXT,
    scraped_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scrape_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE (artist_id, scrape_date)
);

CREATE INDEX IF NOT EXISTS idx_artist_details_scrape_date
    ON artist_details(scrape_date DESC, artist_id);
