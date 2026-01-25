-- ============================================================================
-- Create Complete Schema for SBIR Awards (First Time Setup)
-- Creates tables with all CSV columns and optimizes for production
-- ============================================================================

-- Step 1: Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- Step 2: Create Awards Table with all CSV columns
-- ============================================================================

-- Drop table if exists (for fresh start)
-- Note: Table names will be replaced by create_schema.py with configured names
DROP TABLE IF EXISTS award_chunks CASCADE;
DROP TABLE IF EXISTS awards CASCADE;

-- Create Awards Table
-- Table name 'awards' will be replaced with configured AWARDS_TABLE_NAME
CREATE TABLE awards (
    -- Primary Key
    award_id TEXT PRIMARY KEY,
    
    -- Core Fields (from CSV)
    award_number TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    award_status TEXT,
    institution TEXT,
    uei TEXT,
    duns TEXT,
    most_recent_award_date DATE,
    num_support_periods INTEGER,
    pm TEXT,
    current_budget_period TEXT,
    current_project_period TEXT,
    pi TEXT,
    supplement_budget_period TEXT,
    public_abstract TEXT,
    public_abstract_url TEXT,
    
    -- Metadata
    agency TEXT DEFAULT 'PAMS',  -- Default agency value (can be overridden)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================================
-- Step 3: Create Indexes for Awards Table
-- ============================================================================

-- B-Tree Indexes for Fast Filtering
CREATE INDEX idx_awards_award_number ON awards(award_number);
CREATE INDEX idx_awards_agency ON awards(agency);
CREATE INDEX idx_awards_status ON awards(award_status);
CREATE INDEX idx_awards_institution ON awards(institution);
CREATE INDEX idx_awards_date ON awards(most_recent_award_date);
CREATE INDEX idx_awards_pi ON awards(pi);

-- GIN Indexes for Full-Text Search
CREATE INDEX idx_awards_title_gin 
ON awards USING gin(to_tsvector('english', COALESCE(title, '')));

CREATE INDEX idx_awards_abstract_gin 
ON awards USING gin(to_tsvector('english', COALESCE(public_abstract, '')));

-- Trigram Indexes for Fuzzy Matching
CREATE INDEX idx_awards_title_trgm 
ON awards USING gin(title gin_trgm_ops);

CREATE INDEX idx_awards_abstract_trgm 
ON awards USING gin(public_abstract gin_trgm_ops);

-- ============================================================================
-- Step 4: Create Award Chunks Table for Sentence Transformers (768-dim)
-- ============================================================================

-- Table name 'award_chunks' will be replaced with configured AWARD_CHUNKS_TABLE_NAME
CREATE TABLE award_chunks (
    -- Primary Key
    chunk_id SERIAL PRIMARY KEY,
    
    -- Foreign Key
    award_id TEXT NOT NULL REFERENCES awards(award_id) ON DELETE CASCADE,
    
    -- Chunk Data
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text_hash TEXT NOT NULL UNIQUE,  -- For incremental updates
    
    -- Vector Embedding (using pgvector) - Sentence Transformers dimension
    embedding vector(768),
    
    -- Metadata
    token_count INTEGER,
    field_name TEXT DEFAULT 'abstract',
    model_name TEXT DEFAULT 'sentence-transformers/all-mpnet-base-v2',
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Unique constraint
    CONSTRAINT award_chunks_award_id_chunk_index_key UNIQUE (award_id, chunk_index)
);

-- ============================================================================
-- Step 5: Create Indexes for Award Chunks Table
-- ============================================================================

-- B-Tree Indexes
CREATE INDEX idx_chunks_award_id ON award_chunks(award_id);
CREATE INDEX idx_chunks_text_hash ON award_chunks(text_hash);
CREATE INDEX idx_chunks_model ON award_chunks(model_name);

-- Vector Index for Fast Similarity Search (ivfflat for 768 dimensions)
CREATE INDEX idx_chunks_embedding 
ON award_chunks 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- ============================================================================
-- Step 6: Create Update Trigger for updated_at
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for awards table
CREATE TRIGGER update_awards_updated_at
    BEFORE UPDATE ON awards
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Schema Creation Complete
-- ============================================================================

-- Verify schema
DO $$
DECLARE
    awards_cols INTEGER;
    chunks_cols INTEGER;
BEGIN
    SELECT COUNT(*) INTO awards_cols
    FROM information_schema.columns
    WHERE table_name = 'awards';
    
    SELECT COUNT(*) INTO chunks_cols
    FROM information_schema.columns
    WHERE table_name = 'award_chunks';
    
    RAISE NOTICE 'Schema creation complete!';
    RAISE NOTICE 'Awards table has % columns', awards_cols;
    RAISE NOTICE 'Award_chunks table has % columns', chunks_cols;
END $$;

