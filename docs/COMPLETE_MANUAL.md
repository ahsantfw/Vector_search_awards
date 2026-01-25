# SBIR Vector Search System - Complete Manual

**Version:** 1.0.0  
**Last Updated:** January 2026  
**Project:** SBIR Vector Search Engine

---

## Table of Contents

1. [Introduction](#introduction)
2. [System Overview](#system-overview)
3. [Architecture](#architecture)
4. [Installation & Setup](#installation--setup)
5. [Configuration](#configuration)
6. [Database Schema](#database-schema)
7. [Data Pipeline](#data-pipeline)
8. [Search System](#search-system)
9. [API Reference](#api-reference)
10. [Frontend UI](#frontend-ui)
11. [Deployment](#deployment)
12. [Troubleshooting](#troubleshooting)
13. [Performance Optimization](#performance-optimization)
14. [Appendix](#appendix)

---

## 1. Introduction

### 1.1 What is This System?

The SBIR Vector Search System is a production-grade hybrid search engine designed specifically for searching Small Business Innovation Research (SBIR) award data. It combines:

- **Lexical Search**: Exact keyword matching using PostgreSQL Full-Text Search (FTS)
- **Semantic Search**: Meaning-based search using vector embeddings
- **Hybrid Search**: Intelligent combination of both approaches for optimal results

### 1.2 Key Features

- ✅ **Hybrid Search**: Combines lexical and semantic search for comprehensive results
- ✅ **Fast Performance**: Sub-500ms search latency with parallel execution
- ✅ **Free Embeddings**: Uses Sentence Transformers (no API costs)
- ✅ **Scalable**: Handles thousands of awards with batch processing
- ✅ **User-Friendly**: Modern web UI with parameter controls
- ✅ **Production Ready**: Comprehensive logging, error handling, and monitoring

### 1.3 Use Cases

- Search SBIR awards by keywords or concepts
- Find related awards even without exact word matches
- Filter and rank results by relevance
- Access award details and abstracts via URLs

---

## 2. System Overview

### 2.1 High-Level Flow

```
┌─────────────┐
│   CSV Data  │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  Load to DB     │  (scripts/load_csv_to_supabase.py)
│  (Supabase)     │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  Index Pipeline │  (scripts/index_data.py)
│  - Chunking     │
│  - Embedding    │
│  - Vector Store │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  API Server     │  (FastAPI)
│  - Search API   │
│  - Health Check │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  Frontend UI    │  (HTML/JS/CSS)
│  - Search Form  │
│  - Results      │
└─────────────────┘
```

### 2.2 Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Database** | Supabase (PostgreSQL) | Stores award metadata, handles lexical search |
| **Vector Store** | pgvector (PostgreSQL extension) | Stores embeddings for semantic search |
| **Embeddings** | Sentence Transformers | Generates vector embeddings (free, local) |
| **API** | FastAPI (Python) | RESTful API for search operations |
| **Frontend** | HTML/CSS/JavaScript | User interface for search |
| **Indexing** | Python scripts | Processes and indexes award data |

---

## 3. Architecture

### 3.1 Database Architecture

#### 3.1.1 Awards Table

Stores the main award records with all metadata:

```sql
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
    agency TEXT DEFAULT 'PAMS',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Indexes:**
- `award_id` (Primary Key)
- `award_number` (Unique)
- GIN indexes on `title` and `public_abstract` for fast full-text search

#### 3.1.2 Award Chunks Table

Stores text chunks with vector embeddings:

```sql
CREATE TABLE award_chunks (
    -- Primary Key
    chunk_id SERIAL PRIMARY KEY,
    
    -- Foreign Key
    award_id TEXT NOT NULL REFERENCES awards(award_id) ON DELETE CASCADE,
    
    -- Chunk Data
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text_hash TEXT NOT NULL UNIQUE,  -- For incremental updates
    
    -- Vector Embedding (using pgvector)
    embedding vector(768),  -- Sentence Transformers dimension
    
    -- Metadata
    token_count INTEGER,
    field_name TEXT DEFAULT 'abstract',
    model_name TEXT DEFAULT 'sentence-transformers/all-mpnet-base-v2',
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT award_chunks_award_id_chunk_index_key UNIQUE (award_id, chunk_index)
);
```

**Indexes:**
- `chunk_id` (Primary Key)
- `award_id` (Foreign Key, indexed for joins)
- `text_hash` (Unique, for deduplication)
- Vector index on `embedding` for similarity search

### 3.2 Search Architecture

#### 3.2.1 Hybrid Search Flow

```
User Query
    │
    ├─► Lexical Search (Supabase)
    │   └─► PostgreSQL FTS
    │       └─► Results with lexical_score
    │
    └─► Semantic Search (pgvector)
        └─► Vector Similarity
            └─► Results with semantic_score
                │
                ▼
        Hybrid Scoring
        final_score = (α × semantic_score) + (β × lexical_score)
                │
                ▼
        Deduplication & Ranking
                │
                ▼
        Final Results
```

#### 3.2.2 Parallel Execution

Both searches run **simultaneously** using `asyncio`:

```python
# Both searches run in parallel
lexical_task = run_lexical_search()
semantic_task = run_semantic_search()

# Wait for both to complete
lexical_results, semantic_results = await asyncio.gather(
    lexical_task,
    semantic_task
)
```

This reduces total search time from `lexical_time + semantic_time` to `max(lexical_time, semantic_time)`.

### 3.3 Indexing Pipeline Architecture

```
CSV File
    │
    ▼
Load to Supabase (awards table)
    │
    ▼
Fetch Awards (with pagination)
    │
    ▼
Parallel Chunking (ThreadPoolExecutor)
    │
    ▼
Batch Embedding (Sentence Transformers)
    │
    ▼
Bulk Insert to pgvector (award_chunks table)
    │
    ▼
Complete
```

---

## 4. Installation & Setup

### 4.1 Prerequisites

- **Python**: 3.10 or higher
- **PostgreSQL**: 14+ (via Supabase)
- **Node.js**: (optional, for localtunnel deployment)
- **Supabase Account**: Free tier is sufficient

### 4.2 Installation Steps

#### Step 1: Clone/Navigate to Project

```bash
cd /path/to/sbir_vector_search/Search_Engine
```

#### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

Or using `uv` (faster):

```bash
uv pip install -r requirements.txt
```

#### Step 3: Configure Environment

```bash
cp config/env.example .env
```

Edit `.env` with your credentials:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
DATABASE_URL=postgresql://user:password@host:port/database

# Embedding Configuration
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
EMBEDDING_DIMENSION=768

# Optional: OpenAI (if using OpenAI embeddings)
# OPENAI_API_KEY=sk-...

# Table Names (optional, defaults shown)
AWARDS_TABLE_NAME=awards
AWARD_CHUNKS_TABLE_NAME=award_chunks

# Default Agency
DEFAULT_AGENCY=PAMS

# Search Configuration
DEFAULT_TOP_K=10
MAX_TOP_K=100
LEXICAL_BOOST=10.0
SEMANTIC_WEIGHT=0.5

# Chunking Configuration
CHUNK_SIZE=400
CHUNK_OVERLAP=40

# Indexing Configuration
INDEXING_BATCH_SIZE=100
INDEXING_MAX_CONCURRENT=1
INDEXING_EMBEDDING_BATCH_SIZE=64
INDEXING_CHUNKING_WORKERS=4
```

#### Step 4: Create Database Schema

```bash
python scripts/create_schema.py
```

This creates:
- `awards` table with all columns
- `award_chunks` table with vector support
- All necessary indexes
- Triggers for `updated_at`

**Options:**
- `--dry-run`: Preview SQL without executing
- `--verify-only`: Check existing schema

#### Step 5: Load CSV Data

```bash
python scripts/load_csv_to_supabase.py scripts/award_details.csv
```

This:
- Reads CSV file
- Validates and cleans data
- Uploads to Supabase in batches
- Handles duplicates using `award_number` as unique key

**Options:**
- `--batch-size N`: Change batch size (default: 100)
- `--table-name NAME`: Use custom table name

#### Step 6: Index Data

```bash
python scripts/index_data.py --async
```

This:
- Fetches all awards from Supabase (with pagination)
- Chunks abstracts into 400-token pieces
- Generates embeddings using Sentence Transformers
- Stores vectors in pgvector

**Options:**
- `--async`: Use async/parallel processing (recommended)
- `--batch-size N`: Awards per batch (default: 100)
- `--max-concurrent N`: Max parallel operations (default: 1)
- `--embedding-batch-size N`: Chunks per embedding batch (default: 64)
- `--chunking-workers N`: Parallel chunking workers (default: 4)

#### Step 7: Start API Server

```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Access:
- **UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

---

## 5. Configuration

### 5.1 Environment Variables

All configuration is done via environment variables or `.env` file. See `config/env.example` for all options.

#### 5.1.1 Database Configuration

```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key
DATABASE_URL=postgresql://...
```

#### 5.1.2 Table Names

```env
AWARDS_TABLE_NAME=awards
AWARD_CHUNKS_TABLE_NAME=award_chunks
```

#### 5.1.3 Embedding Configuration

**Option A: Sentence Transformers (Free, Local)**
```env
# Provider: "sentence-transformers" (free) or "openai" (paid)
EMBEDDING_PROVIDER=sentence-transformers

# Model name
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2

# Dimension: 768 for Sentence Transformers
EMBEDDING_DIMENSION=768
```

**Option B: OpenAI (Paid, Higher Quality)**
```env
# Provider: "openai"
EMBEDDING_PROVIDER=openai

# Model name
EMBEDDING_MODEL=text-embedding-3-large

# Dimension: 3072 for OpenAI (requires schema update)
EMBEDDING_DIMENSION=3072

# API Key (required)
OPENAI_API_KEY=sk-your-key-here
```

**Performance Comparison:**
- **Sentence Transformers**: Free, fast, good quality (Recall@5: ~60-80%)
- **OpenAI 3072**: Paid, excellent quality (Recall@5: ~90-100%), requires API key

#### 5.1.4 Search Configuration

```env
DEFAULT_TOP_K=10          # Default number of results
MAX_TOP_K=100             # Maximum allowed results
LEXICAL_BOOST=10.0        # Beta parameter (lexical weight)
SEMANTIC_WEIGHT=0.5       # Alpha parameter (semantic weight)
```

#### 5.1.5 Chunking Configuration

```env
CHUNK_SIZE=400            # Tokens per chunk
CHUNK_OVERLAP=40          # Overlap between chunks (10%)
```

#### 5.1.6 Indexing Configuration

**For Sentence Transformers (Free):**
```env
INDEXING_BATCH_SIZE=100              # Awards per batch
INDEXING_MAX_CONCURRENT=1            # Max parallel async operations
INDEXING_EMBEDDING_BATCH_SIZE=64     # Chunks per embedding batch
INDEXING_CHUNKING_WORKERS=4          # Parallel chunking workers
```

**For OpenAI Embeddings (Rate Limit Optimized):**
```env
INDEXING_BATCH_SIZE=8                # Awards per batch (smaller for API)
INDEXING_MAX_CONCURRENT=3            # Max concurrent API requests (Tier 1: 2-3, Tier 2+: 4-5)
INDEXING_EMBEDDING_BATCH_SIZE=32     # Chunks per API request (16-64 recommended)
INDEXING_CHUNKING_WORKERS=2          # Parallel chunking workers (safe for 4GB RAM)
```

**OpenAI Rate Limits by Tier:**
- **Free Tier**: 3 RPM, 1M TPM → Use `MAX_CONCURRENT=1`
- **Tier 1**: 500 RPM, 1M TPM → Use `MAX_CONCURRENT=2-3`
- **Tier 2+**: 5000+ RPM, 5M+ TPM → Use `MAX_CONCURRENT=4-5`

**Rate Limit Calculation:**
- Requests/minute = `MAX_CONCURRENT` × (60 / avg_request_time)
- Example: `MAX_CONCURRENT=3` with 2s requests = ~90 RPM (safe for Tier 1)

### 5.2 Configuration File

Configuration is managed in `src/core/config.py` using Pydantic Settings:

```python
from src.core.config import settings

# Access configuration
print(settings.SUPABASE_URL)
print(settings.EMBEDDING_PROVIDER)
print(settings.DEFAULT_TOP_K)
```

---

## 6. Database Schema

### 6.1 Awards Table

**Purpose**: Stores award metadata and abstracts.

**Key Columns:**
- `award_id`: Primary key (usually same as `award_number`)
- `award_number`: Unique identifier (used for deduplication)
- `title`: Award title (indexed for FTS)
- `public_abstract`: Full abstract text (indexed for FTS)
- `public_abstract_url`: Link to award details
- All other metadata columns from CSV

**Indexes:**
- Primary key on `award_id`
- Unique constraint on `award_number`
- GIN index on `title` for fast text search
- GIN index on `public_abstract` for fast text search

### 6.2 Award Chunks Table

**Purpose**: Stores text chunks with vector embeddings.

**Key Columns:**
- `chunk_id`: Primary key
- `award_id`: Foreign key to `awards` table
- `chunk_text`: The actual text chunk
- `chunk_index`: Position of chunk in original text
- `text_hash`: SHA256 hash for deduplication
- `embedding`: Vector embedding (768 dimensions)

**Indexes:**
- Primary key on `chunk_id`
- Unique constraint on `(award_id, chunk_index)`
- Unique constraint on `text_hash`
- Vector index on `embedding` for similarity search

### 6.3 Schema Creation

Run `scripts/create_schema.py` to create the schema:

```bash
python scripts/create_schema.py
```

**What it does:**
1. Drops existing tables (if any)
2. Creates `awards` table with all columns
3. Creates `award_chunks` table with vector support
4. Creates all indexes
5. Creates triggers for `updated_at`
6. Verifies schema creation

### 6.4 Schema Deletion

To delete the schema:

```bash
python scripts/delete_schema.py --all
```

**Options:**
- `--all`: Delete entire schema
- `--table NAME`: Delete specific table
- `--index NAME`: Delete specific index
- `--all-indexes`: Delete all indexes
- `--dry-run`: Preview without executing
- `--list`: List all schema components

---

## 7. Data Pipeline

### 7.1 Data Loading

#### 7.1.1 CSV Format

Expected CSV columns:
- `award_number` (required, unique)
- `title` (required)
- `public_abstract` (required for search)
- `public_abstract_url` (optional, for links)
- All other metadata columns

#### 7.1.2 Loading Process

```bash
python scripts/load_csv_to_supabase.py scripts/award_details.csv
```

**Process:**
1. Reads CSV file
2. Validates required columns
3. Deduplicates by `award_number` (keeps last occurrence)
4. Uploads to Supabase in batches
5. Uses `UPSERT` with `on_conflict="award_number"` to handle duplicates

**Features:**
- Automatic deduplication
- Batch processing (configurable)
- Error handling and retry logic
- Progress logging

### 7.2 Indexing Pipeline

#### 7.2.1 Overview

The indexing pipeline:
1. Fetches awards from Supabase (with pagination)
2. Chunks abstracts into smaller pieces
3. Generates embeddings for each chunk
4. Stores vectors in pgvector

#### 7.2.2 Chunking

**Strategy**: Token-based chunking with overlap

- **Chunk Size**: 400 tokens (default)
- **Overlap**: 40 tokens (10%, default)
- **Method**: Uses Sentence Transformers tokenizer

**Why Overlap?**
- Preserves context at chunk boundaries
- Ensures important phrases aren't split
- Improves search quality

#### 7.2.3 Embedding Generation

**Provider**: Sentence Transformers (default, free)

- **Model**: `all-mpnet-base-v2`
- **Dimension**: 768
- **Speed**: ~100x faster than API calls
- **Cost**: Free (runs locally)

**Alternative**: OpenAI (paid, recommended for production)
- **Model**: `text-embedding-3-large`
- **Dimension**: 3072 (requires schema update)
- **Cost**: ~$0.13 per 1M tokens (3072 dim)
- **Performance**: Recall@5: 90-100% (vs 60-80% for Sentence Transformers)
- **Setup**: Requires API key and rate limit configuration

**Setting Up OpenAI Embeddings:**

1. **Update `.env`:**
```env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSION=3072
OPENAI_API_KEY=sk-your-key-here

# Rate limit optimized settings
INDEXING_BATCH_SIZE=8
INDEXING_MAX_CONCURRENT=3
INDEXING_EMBEDDING_BATCH_SIZE=32
```

2. **Create Schema with 3072 Dimensions:**
```bash
echo "yes" | uv run python scripts/create_schema.py
```
Note: Schema automatically uses HNSW index with `halfvec` casting for 3072 dimensions.

3. **Index Data:**
```bash
uv run python scripts/index_data.py --async --fresh
```

**Rate Limit Optimization:**
- **Tier 1 (500 RPM)**: Use `MAX_CONCURRENT=2-3`, `EMBEDDING_BATCH_SIZE=32`
- **Tier 2+ (5000+ RPM)**: Use `MAX_CONCURRENT=4-5`, `EMBEDDING_BATCH_SIZE=64`
- Code includes automatic exponential backoff retry on rate limits

#### 7.2.4 Vector Storage

Vectors are stored in PostgreSQL using pgvector extension:

```sql
embedding vector(768)   -- For Sentence Transformers
embedding vector(3072)  -- For OpenAI
```

**Indexing:**
- **≤2000 dimensions**: Uses ivfflat index
- **>2000 dimensions**: Uses HNSW index with `halfvec` casting (automatic)
- Supports cosine similarity
- Handles millions of vectors efficiently

#### 7.2.5 Running Indexing

```bash
python scripts/index_data.py --async
```

**Process:**
1. Fetches awards in batches (with pagination)
2. Parallel chunking (4 workers by default)
3. Batch embedding (64 chunks per batch)
4. Bulk insert to pgvector (with deduplication)

**Performance:**
- Processes ~100 awards per batch
- Parallel chunking speeds up processing
- Batch embedding reduces overhead
- Bulk insert is 10x faster than row-by-row

### 7.3 Incremental Updates

The system supports incremental updates via `text_hash`:

- Each chunk has a unique `text_hash` (SHA256)
- Duplicate chunks are skipped during indexing
- Only new or changed chunks are processed

---

## 8. Search System

### 8.1 Search Types

#### 8.1.1 Lexical Search

**Technology**: PostgreSQL Full-Text Search (FTS)

**How it works:**
1. Uses GIN indexes on `title` and `public_abstract`
2. Searches for exact word matches
3. Scores based on term frequency
4. Returns results with `lexical_score`

**Strengths:**
- Fast (uses indexes)
- Precise for exact matches
- Handles typos (with `ilike`)

**Limitations:**
- Doesn't understand synonyms
- Misses semantic matches

#### 8.1.2 Semantic Search

**Technology**: Vector similarity search (pgvector)

**How it works:**
1. Embeds query using Sentence Transformers
2. Searches for similar vectors using cosine similarity
3. Returns results with `semantic_score`

**Strengths:**
- Finds related concepts
- Handles synonyms
- Understands meaning

**Limitations:**
- Slower than lexical (vector operations)
- May miss exact matches

#### 8.1.3 Hybrid Search

**Technology**: Combines lexical + semantic

**Formula:**
```
final_score = (α × semantic_score) + (β × lexical_score)
```

Where:
- `α` (alpha): Semantic weight (0.0 to 1.0, default: 0.5)
- `β` (beta): Lexical boost (0.0+, default: 10.0)

**How it works:**
1. Runs lexical and semantic searches in parallel
2. Combines results using weighted formula
3. Deduplicates by `award_id`
4. Ranks by `final_score`

**Benefits:**
- Best of both worlds
- Configurable weighting
- Handles both exact and semantic matches

### 8.2 Search Parameters

#### 8.2.1 Alpha (α) - Semantic Weight

**Range**: 0.0 to 1.0  
**Default**: 0.5

**Effect:**
- Higher values (0.7-1.0): Emphasizes semantic similarity
- Lower values (0.0-0.3): Reduces semantic influence

**Example:**
- `α=0.8`: Searching "AI" finds "artificial intelligence", "machine learning"
- `α=0.2`: Focuses on exact word matches

#### 8.2.2 Beta (β) - Lexical Boost

**Range**: 0.0 and above  
**Default**: 10.0

**Effect:**
- Higher values (10.0+): Strongly prioritizes exact word matches
- Lower values (1.0-5.0): Reduces boost for exact matches

**Example:**
- `β=15.0`: "quantum computing" heavily favors awards with both words
- `β=5.0`: Makes semantic results more competitive

#### 8.2.3 Top K

**Range**: 1 to 100  
**Default**: 10

Number of results to return.

### 8.3 Search Flow

```
1. User submits query
   │
   ├─► Embed query (Sentence Transformers)
   │
   ├─► Run Lexical Search (Supabase) ──┐
   │                                    │
   └─► Run Semantic Search (pgvector) ─┤ PARALLEL
                                        │
                                        ▼
2. Combine Results
   │
   ├─► Calculate hybrid scores
   │   final_score = (α × semantic) + (β × lexical)
   │
   ├─► Deduplicate by award_id
   │
   ├─► Group chunks under each award
   │
   └─► Sort by final_score
       │
       ▼
3. Return Results
   - hybrid_results (combined)
   - lexical_results (lexical only)
   - semantic_results (semantic only)
```

### 8.4 Deduplication

Results are deduplicated by `award_id`:

- Each award appears only once
- Best score is kept
- All matching chunks are grouped under the award

**Example:**
- Award A matches in chunks 0, 2, 5
- Result shows Award A once with all 3 chunks listed

### 8.5 Filtering

When parameters are set to 0:

- `β=0`: Only shows awards found by semantic search
- `α=0`: Only shows awards found by lexical search

This allows pure semantic or pure lexical search in the Hybrid tab.

---

## 9. API Reference

### 9.1 Endpoints

#### 9.1.1 Search Endpoint

**URL**: `POST /search` or `POST /search/`

**Request Body:**
```json
{
  "query": "quantum computing",
  "top_k": 10,
  "alpha": 0.5,
  "beta": 10.0
}
```

**Parameters:**
- `query` (required): Search query string
- `top_k` (optional): Number of results (default: 10, max: 100)
- `alpha` (optional): Semantic weight (0.0-1.0, default: 0.5)
- `beta` (optional): Lexical boost (0.0+, default: 10.0)

**Response:**
```json
{
  "query": "quantum computing",
  "hybrid_results": [
    {
      "award_id": "DE-SC0023667",
      "award_number": "DE-SC0023667",
      "title": "Quantum Computing Research",
      "final_score": 25.425,
      "lexical_score": 2.5,
      "semantic_score": 0.85,
      "snippet": "...",
      "url": "https://...",
      "chunks": [...]
    }
  ],
  "lexical_results": [...],
  "semantic_results": [...],
  "metadata": {
    "search_time_ms": 150.5,
    "hybrid_count": 10,
    "lexical_count": 10,
    "semantic_count": 10,
    "vector_store": "pgvector"
  }
}
```

#### 9.1.2 Health Check

**URL**: `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "components": {
    "vector_store": "pgvector",
    "supabase_configured": true,
    "supabase_connected": true,
    "vector_store_available": true
  }
}
```

#### 9.1.3 Root Endpoint

**URL**: `GET /`

Returns UI HTML file or API information.

### 9.2 Response Models

#### 9.2.1 SearchResult

```python
{
  "award_id": str,
  "award_number": str,
  "title": str,
  "agency": str,
  "snippet": str,
  "url": str,
  "final_score": float,
  "lexical_score": float,
  "semantic_score": float,
  "chunk_index": int,
  "chunks": [
    {
      "chunk_index": int,
      "chunk_text": str,
      "lexical_score": float,
      "semantic_score": float,
      "final_score": float
    }
  ],
  # All schema columns
  "award_status": str,
  "institution": str,
  "uei": str,
  "duns": str,
  "most_recent_award_date": str,
  "num_support_periods": int,
  "pm": str,
  "current_budget_period": str,
  "current_project_period": str,
  "pi": str,
  "supplement_budget_period": str,
  "public_abstract": str,
  "public_abstract_url": str
}
```

### 9.3 Error Handling

**400 Bad Request:**
- Invalid `top_k` (exceeds max)
- Missing required parameters

**500 Internal Server Error:**
- Database connection issues
- Vector store errors
- Embedding generation failures

---

## 10. Frontend UI

### 10.1 Features

- **Search Interface**: Clean, modern design
- **Parameter Controls**: Adjustable alpha and beta
- **Multiple Tabs**: Hybrid, Lexical, Semantic results
- **Clickable Awards**: Opens award URL in new window
- **Chunk Display**: Shows all matching chunks per award
- **Score Display**: Shows all scores (final, lexical, semantic)
- **Documentation**: Built-in parameter explanation

### 10.2 UI Components

#### 10.2.1 Search Form

- **Search Input**: Text field for query
- **Results Dropdown**: Select number of results (10, 20, 50, 100)
- **Alpha Input**: Semantic weight (0.0-1.0)
- **Beta Input**: Lexical boost (0.0+)

#### 10.2.2 Results Display

- **Tabs**: Switch between Hybrid, Lexical, Semantic
- **Result Cards**: Each award as a card
- **Scores**: Visual score badges
- **Chunks**: Expandable chunk list
- **Links**: Clickable award titles

#### 10.2.3 Documentation Section

- Parameter explanations
- Score calculation formula
- Example calculations
- Search type descriptions

### 10.3 JavaScript Functions

#### 10.3.1 createFetchOptions()

Adds tunnel skip headers for ngrok/localtunnel:

```javascript
function createFetchOptions(options = {}) {
    const headers = new Headers(options.headers || {});
    
    // ngrok
    if (hostname.includes('ngrok-free.app')) {
        headers.set('ngrok-skip-browser-warning', 'true');
    }
    
    // localtunnel
    if (hostname.includes('loca.lt')) {
        headers.set('bypass-tunnel-reminder', 'true');
    }
    
    return { ...options, headers };
}
```

#### 10.3.2 performSearch()

Main search function:
1. Gets parameters from UI
2. Sends request to API
3. Renders results
4. Updates metadata

### 10.4 Styling

Modern CSS with:
- CSS variables for theming
- Responsive design
- Smooth animations
- Highlighted search terms

---

## 11. Deployment

### 11.1 Local Deployment

```bash
# Start API server
uvicorn src.api.app:app --host 0.0.0.0 --port 8000

# Access UI
http://localhost:8000
```

### 11.2 Tunnel Deployment

#### 11.2.1 ngrok

```bash
./scripts/deploy_ngrok.sh
```

**Requirements:**
- ngrok installed
- Free account (signup required)
- Authtoken configured

**Features:**
- Automatic API server management
- URL extraction
- Process monitoring

#### 11.2.2 localtunnel

```bash
./scripts/deploy_localtunnel.sh
```

**Requirements:**
- Node.js installed
- No signup required

**Features:**
- Automatic password display
- No account needed
- Free forever

**Note:** Visitors need tunnel password (public IP) on first visit.

#### 11.2.3 Cloudflare Tunnel

```bash
./scripts/deploy.sh
```

**Requirements:**
- cloudflared installed
- No account needed (for quick tunnels)

**Features:**
- No signup required
- Automatic URL extraction

### 11.3 Production Deployment

For production, consider:

1. **Reverse Proxy**: Nginx or Caddy
2. **Process Manager**: systemd or supervisor
3. **SSL/TLS**: Let's Encrypt certificates
4. **Monitoring**: Prometheus + Grafana
5. **Logging**: Centralized logging (ELK stack)

---

## 12. Validation & Testing

### 12.1 Validation Methodology

The system uses a **Ground Truth** methodology for validating semantic search accuracy, following industry-standard synthetic evaluation practices.

**Process:**
1. **Synthetic Query Generation**: 
   - LLM (Groq Llama 3.3 70B) analyzes indexed awards
   - Generates 5 technical, conceptual questions per award paragraph
   - Questions test semantic understanding (not keyword matching)
   - Uses synonyms and related concepts, avoids exact words from source
   - **No fallback**: If LLM fails, query is skipped (ensures quality)

2. **Retrieval Benchmarking**: 
   - Queries run through semantic-only search (alpha=1.0, beta=0.0)
   - Retrieves top K results (default: K=5)
   - Checks if ground truth award appears in results
   - Records rank position of ground truth

3. **Performance Metrics**: 
   - **Recall@5**: Fraction of queries where ground truth appears in top 5
   - **MRR (Mean Reciprocal Rank)**: Average of 1/rank for ground truth position
   - **Target**: Recall@5 ≥ 0.70 (70%) for production quality

### 12.2 Running Validation

```bash
# Run validation benchmark
uv run python scripts/validation_benchmark.py

# Options:
# --num-awards: Number of awards to generate queries from (default: 20)
# --queries-per-award: Queries per award (default: 5)
# --top-k: Results to check (default: 5)
# --semantic-only: Only test semantic search (default: True)
# --output: Output file (default: validation_report.txt)
```

**Example:**
```bash
uv run python scripts/validation_benchmark.py \
  --num-awards 20 \
  --queries-per-award 5 \
  --top-k 5 \
  --output validation_report.txt
```

### 12.3 Performance Results

**OpenAI Embeddings (text-embedding-3-large, 3072 dimensions):**
- **Recall@5**: 1.000 (100%) ✅
- **MRR**: 0.915
- **Queries with Recall@5**: 100/100
- **Validation Threshold**: PASS (≥0.70)

**Sentence Transformers (all-mpnet-base-v2, 768 dimensions):**
- **Recall@5**: ~0.60-0.80 (60-80%)
- **MRR**: ~0.70-0.85
- **Validation Threshold**: PASS (≥0.70)

### 12.4 Test Complex Queries

```bash
# Test 5 complex queries with ground truth
uv run python scripts/test_complex_queries.py
```

This script tests specific complex queries and validates against known ground truth awards.

### 12.5 Validation Report

The validation generates:
- **Text Report**: `validation_report.txt` - Human-readable results
- **JSON Report**: `validation_report.json` - Machine-readable data

**Report Contents:**
- Performance metrics (Recall@5, MRR)
- Query-by-query results
- Ground truth vs retrieved awards
- Success/failure indicators

---

## 13. Troubleshooting

### 12.1 Common Issues

#### Issue: "OpenAI API key not configured"

**Solution**: Set `EMBEDDING_PROVIDER=sentence-transformers` in `.env` (uses free embeddings)

#### Issue: "Table not found"

**Solution**: Run `python scripts/create_schema.py` to create tables

#### Issue: "No results returned"

**Possible causes:**
- Data not indexed: Run `python scripts/index_data.py --async`
- Empty database: Load CSV data first
- Wrong table names: Check `AWARDS_TABLE_NAME` in config

#### Issue: "Search is slow"

**Solutions:**
- Check indexes are created
- Reduce `top_k` value
- Check database connection
- Monitor resource usage

#### Issue: "Tunnel warning page"

**Solutions:**
- ngrok: Header is added automatically in JavaScript
- localtunnel: Share tunnel password with visitors
- First page load may show warning (limitation of free tiers)

### 12.2 Debugging

#### Enable Debug Logging

```env
LOG_LEVEL=DEBUG
```

#### Check Logs

```bash
tail -f logs/app.log
```

#### Verify Schema

```bash
python scripts/create_schema.py --verify-only
```

#### Test Database Connection

```python
from src.database.supabase import get_supabase_client
client = get_supabase_client()
print(client.health_check())
```

---

## 14. Performance Optimization

### 13.1 Indexing Performance

**Optimizations:**
- Batch processing (100 awards per batch)
- Parallel chunking (4 workers)
- Batch embedding (64 chunks per batch)
- Bulk insert to pgvector

**Tuning:**
```env
INDEXING_BATCH_SIZE=100
INDEXING_CHUNKING_WORKERS=4
INDEXING_EMBEDDING_BATCH_SIZE=64
```

### 13.2 Search Performance

**Optimizations:**
- Parallel lexical and semantic search
- GIN indexes for fast FTS
- Vector indexes for fast similarity search
- Connection pooling

**Expected Performance:**
- Lexical search: ~50-100ms
- Semantic search: ~100-200ms
- Hybrid search: ~150-250ms (parallel execution)

### 13.3 Database Optimization

**Indexes:**
- GIN indexes on `title` and `public_abstract`
- Vector index on `embedding`
- Unique indexes on `award_number` and `text_hash`

**Connection Pooling:**
- Reuse database connections
- Reduce connection overhead

---

## 15. Appendix

### 14.1 File Structure

```
Search_Engine/
├── config/
│   └── env.example          # Environment variable template
├── docs/
│   └── COMPLETE_MANUAL.md   # This file
├── logs/
│   └── app.log             # Application logs
├── scripts/
│   ├── create_schema.py    # Schema creation
│   ├── delete_schema.py    # Schema deletion
│   ├── load_csv_to_supabase.py  # Data loading
│   ├── index_data.py       # Indexing pipeline
│   ├── deploy.sh           # Cloudflare tunnel
│   ├── deploy_ngrok.sh     # ngrok tunnel
│   └── deploy_localtunnel.sh  # localtunnel
├── src/
│   ├── api/
│   │   ├── app.py          # FastAPI application
│   │   └── routes/
│   │       ├── search.py   # Search endpoint
│   │       └── health.py   # Health check
│   ├── core/
│   │   ├── config.py       # Configuration
│   │   ├── logging.py      # Logging setup
│   │   ├── models/
│   │   │   └── search.py   # Pydantic models
│   │   └── search/
│   │       ├── hybrid_search.py  # Hybrid search
│   │       ├── lexical.py       # Lexical search
│   │       ├── semantic.py      # Semantic search
│   │       └── deduplication.py # Deduplication
│   ├── database/
│   │   ├── supabase.py     # Supabase client
│   │   └── pgvector.py     # pgvector manager
│   └── indexing/
│       ├── pipeline.py     # Indexing pipeline
│       ├── chunking.py     # Text chunking
│       ├── embeddings.py   # Embedding service
│       └── embeddings_sentence_transformers.py  # Sentence Transformers
├── static/
│   ├── index.html          # UI HTML
│   ├── app.js              # UI JavaScript
│   └── styles.css          # UI CSS
├── requirements.txt        # Python dependencies
└── README.md               # Quick start guide
```

### 14.2 Key Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `create_schema.py` | Create database schema | `python scripts/create_schema.py` |
| `delete_schema.py` | Delete schema components | `python scripts/delete_schema.py --all` |
| `load_csv_to_supabase.py` | Load CSV data | `python scripts/load_csv_to_supabase.py file.csv` |
| `index_data.py` | Index data | `python scripts/index_data.py --async` |
| `deploy.sh` | Cloudflare tunnel | `./scripts/deploy.sh` |
| `deploy_ngrok.sh` | ngrok tunnel | `./scripts/deploy_ngrok.sh` |
| `deploy_localtunnel.sh` | localtunnel | `./scripts/deploy_localtunnel.sh` |

### 14.3 Configuration Reference

See `src/core/config.py` for all configuration options.

### 14.4 API Examples

#### Example 1: Basic Search

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "quantum computing",
    "top_k": 10
  }'
```

#### Example 2: Semantic-Weighted Search

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "artificial intelligence",
    "top_k": 20,
    "alpha": 0.8,
    "beta": 5.0
  }'
```

#### Example 3: Lexical-Weighted Search

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning",
    "top_k": 10,
    "alpha": 0.2,
    "beta": 15.0
  }'
```

### 14.5 Glossary

- **Lexical Search**: Exact keyword matching using full-text search
- **Semantic Search**: Meaning-based search using vector embeddings
- **Hybrid Search**: Combination of lexical and semantic search
- **Chunking**: Breaking text into smaller pieces for indexing
- **Embedding**: Vector representation of text
- **pgvector**: PostgreSQL extension for vector operations
- **GIN Index**: Generalized Inverted Index for fast text search
- **Alpha (α)**: Semantic weight parameter (0.0-1.0)
- **Beta (β)**: Lexical boost parameter (0.0+)
- **Top K**: Number of results to return

---

## 15. Support & Resources

### 15.1 Documentation Files

- `README.md`: Quick start guide
- `DOCUMENTATION.md`: Technical documentation
- `COMPLETE_SETUP_GUIDE.md`: Setup instructions
- `API_ROUTES_AND_RETRIEVAL.md`: API details
- `TUNNEL_ALTERNATIVES.md`: Deployment options

### 15.2 External Resources

- **Supabase**: https://supabase.com/docs
- **pgvector**: https://github.com/pgvector/pgvector
- **Sentence Transformers**: https://www.sbert.net/
- **FastAPI**: https://fastapi.tiangolo.com/

---

**End of Manual**

For questions or issues, refer to the troubleshooting section or check the logs in `logs/app.log`.

