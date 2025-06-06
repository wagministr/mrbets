-- SQL schema for Quick Patch Generator prediction impact tracking
-- Execute this in Supabase SQL Editor

-- Create table for tracking prediction impact events
CREATE TABLE IF NOT EXISTS prediction_impact_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Reference to original prediction that was affected
    original_prediction_id UUID REFERENCES ai_predictions(id),
    fixture_id BIGINT REFERENCES fixtures(fixture_id),
    
    -- Breaking news content that triggered the impact
    breaking_news_content TEXT NOT NULL,
    source_type TEXT DEFAULT 'twitter', -- twitter, bbc_sport, etc.
    
    -- Impact analysis results from LLM
    impact_analysis JSONB NOT NULL,
    impact_level TEXT CHECK (impact_level IN ('HIGH', 'MEDIUM', 'LOW')),
    requires_update BOOLEAN DEFAULT FALSE,
    confidence_score DECIMAL(3,2), -- 0.00 to 1.00
    
    -- Telegram notification tracking
    telegram_post_generated BOOLEAN DEFAULT FALSE,
    telegram_post_content TEXT,
    telegram_post_sent BOOLEAN DEFAULT FALSE,
    telegram_post_sent_at TIMESTAMP WITH TIME ZONE,
    
    -- Entity linking results
    affected_teams JSONB DEFAULT '[]'::jsonb,
    affected_players JSONB DEFAULT '[]'::jsonb,
    
    -- System tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_duration_seconds DECIMAL(6,2),
    
    -- Additional metadata
    meta_data JSONB DEFAULT '{}'::jsonb
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_prediction_impact_events_fixture_id 
ON prediction_impact_events(fixture_id);

CREATE INDEX IF NOT EXISTS idx_prediction_impact_events_created_at 
ON prediction_impact_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_prediction_impact_events_impact_level 
ON prediction_impact_events(impact_level);

CREATE INDEX IF NOT EXISTS idx_prediction_impact_events_requires_update 
ON prediction_impact_events(requires_update);

-- Add composite index for telegram processing
CREATE INDEX IF NOT EXISTS idx_prediction_impact_events_telegram_pending 
ON prediction_impact_events(telegram_post_generated, telegram_post_sent) 
WHERE telegram_post_generated = TRUE AND telegram_post_sent = FALSE;

-- Add RLS policies
ALTER TABLE prediction_impact_events ENABLE ROW LEVEL SECURITY;

-- Allow public read access for frontend
CREATE POLICY "Allow public read access to prediction_impact_events" 
ON prediction_impact_events FOR SELECT 
USING (true);

-- Allow authenticated users to insert
CREATE POLICY "Allow authenticated insert to prediction_impact_events" 
ON prediction_impact_events FOR INSERT 
TO authenticated 
WITH CHECK (true);

-- Allow authenticated users to update
CREATE POLICY "Allow authenticated update to prediction_impact_events" 
ON prediction_impact_events FOR UPDATE 
TO authenticated 
USING (true);

-- Add comments for documentation
COMMENT ON TABLE prediction_impact_events IS 'Tracks breaking news impact on AI predictions and Telegram notifications';
COMMENT ON COLUMN prediction_impact_events.impact_analysis IS 'JSON containing LLM analysis of news impact on prediction';
COMMENT ON COLUMN prediction_impact_events.affected_teams IS 'Array of team entities mentioned in breaking news';
COMMENT ON COLUMN prediction_impact_events.affected_players IS 'Array of player entities mentioned in breaking news';

-- Create view for dashboard/monitoring
CREATE OR REPLACE VIEW prediction_impact_events_summary AS
SELECT 
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as total_events,
    COUNT(*) FILTER (WHERE impact_level = 'HIGH') as high_impact_events,
    COUNT(*) FILTER (WHERE requires_update = TRUE) as updates_triggered,
    COUNT(*) FILTER (WHERE telegram_post_sent = TRUE) as telegram_posts_sent,
    AVG(processing_duration_seconds) as avg_processing_time,
    AVG(confidence_score) as avg_confidence
FROM prediction_impact_events 
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY hour DESC;

-- Grant access to view
GRANT SELECT ON prediction_impact_events_summary TO authenticated;
GRANT SELECT ON prediction_impact_events_summary TO anon; 