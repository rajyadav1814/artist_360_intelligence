-- Migration 007: Add rank_change column to itunes_daily and itunes_artist_album

ALTER TABLE itunes_daily ADD COLUMN IF NOT EXISTS rank_change VARCHAR(50);
ALTER TABLE itunes_artist_album ADD COLUMN IF NOT EXISTS rank_change VARCHAR(50);
