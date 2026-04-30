-- Migration 005: Add label columns to daily tables

ALTER TABLE spotify_daily ADD COLUMN IF NOT EXISTS label VARCHAR(255);
ALTER TABLE itunes_daily ADD COLUMN IF NOT EXISTS label VARCHAR(255);
ALTER TABLE youtube_daily ADD COLUMN IF NOT EXISTS label VARCHAR(255);

-- Create indexes on label columns for better searching
CREATE INDEX IF NOT EXISTS idx_spotify_daily_label ON spotify_daily(label);
CREATE INDEX IF NOT EXISTS idx_itunes_daily_label ON itunes_daily(label);
CREATE INDEX IF NOT EXISTS idx_youtube_daily_label ON youtube_daily(label);
