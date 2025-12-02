-- Create charter_operators table in the gtj schema
-- Run this SQL in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS gtj.charter_operators (
    charter_operator_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company VARCHAR(255) NOT NULL,
    locations JSONB NOT NULL DEFAULT '[]'::jsonb,
    url VARCHAR(512),
    part135_cert VARCHAR(100),
    score INTEGER DEFAULT 0,
    faa_data JSONB,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_charter_operators_company ON gtj.charter_operators(company);
CREATE INDEX IF NOT EXISTS idx_charter_operators_score ON gtj.charter_operators(score DESC);
CREATE INDEX IF NOT EXISTS idx_charter_operators_locations ON gtj.charter_operators USING GIN(locations);
CREATE INDEX IF NOT EXISTS idx_charter_operators_data ON gtj.charter_operators USING GIN(data);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION gtj.update_charter_operators_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_charter_operators_updated_at
    BEFORE UPDATE ON gtj.charter_operators
    FOR EACH ROW
    EXECUTE FUNCTION gtj.update_charter_operators_updated_at();

-- Add comment to table
COMMENT ON TABLE gtj.charter_operators IS 'Charter operator companies with certifications and scores from enriched data';

-- Grant permissions (adjust as needed for your setup)
GRANT SELECT, INSERT, UPDATE, DELETE ON gtj.charter_operators TO authenticated;
GRANT SELECT ON gtj.charter_operators TO anon;
