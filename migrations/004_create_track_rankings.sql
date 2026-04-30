-- Migration 004: Create track_rankings table for weekly track chart data

CREATE TABLE IF NOT EXISTS track_rankings (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    streams BIGINT,
    week_number INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    chart_date DATE NOT NULL,
    scrape_date DATE NOT NULL DEFAULT CURRENT_DATE,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (track_id, chart_date)
);

CREATE INDEX IF NOT EXISTS idx_track_rankings_chart_date ON track_rankings(chart_date);
CREATE INDEX IF NOT EXISTS idx_track_rankings_track_id ON track_rankings(track_id);