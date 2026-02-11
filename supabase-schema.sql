-- OpenDomeGA Legislature Videos Schema for Supabase
-- Migrated from SQLite legislature.db

CREATE TABLE IF NOT EXISTS legislature_videos (
    id SERIAL PRIMARY KEY,
    video_id TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    chamber TEXT,  -- 'house', 'senate'
    session_type TEXT,  -- 'regular', 'special', etc.
    session_year INTEGER,
    day_number INTEGER,
    video_date DATE,
    part INTEGER,  -- for multi-part sessions
    time_of_day TEXT,  -- 'morning', 'afternoon', etc.
    duration_seconds INTEGER,
    source TEXT,  -- 'house_floor', 'gpb_lawmakers', 'senate_press'
    raw_text TEXT,  -- original scraped text/metadata
    transcript TEXT,  -- Whisper output
    summary TEXT,  -- Claude-generated summary
    status TEXT DEFAULT 'pending',  -- 'pending', 'processing', 'transcribed', 'summarized', 'error'
    claimed_by TEXT,  -- 'skippy' or 'nagatha' - who's working on it
    claimed_at TIMESTAMPTZ,  -- when the claim was made
    error_message TEXT,  -- if status='error', what went wrong
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient status queries
CREATE INDEX IF NOT EXISTS idx_legislature_videos_status ON legislature_videos(status);

-- Index for filtering by chamber/year
CREATE INDEX IF NOT EXISTS idx_legislature_videos_chamber_year ON legislature_videos(chamber, session_year);

-- Enable Row Level Security (but allow anon access for now)
ALTER TABLE legislature_videos ENABLE ROW LEVEL SECURITY;

-- Policy: Allow all operations for now (both agents need access)
CREATE POLICY "Allow all access" ON legislature_videos
    FOR ALL
    USING (true)
    WITH CHECK (true);
