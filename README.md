# SBIR Vector Search Engine

A production-ready hybrid vector search engine for SBIR (Small Business Innovation Research) awards. Combines lexical (exact match) and semantic (meaning-based) search for comprehensive results.

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp config/env.example .env
# Edit .env with your Supabase credentials

# 3. Create database schema
python scripts/create_schema.py

# 4. Load CSV data
python scripts/load_csv_to_supabase.py scripts/award_details.csv

# 5. Index data (generate embeddings)
python scripts/index_data.py --async

# 6. Start API server
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Access the UI at: `http://localhost:8000`

## ✨ Features

- 🔍 **Hybrid Search**: Combines lexical and semantic search for optimal results
- ⚡ **Fast**: Sub-500ms search latency with parallel execution
- 🎯 **Accurate**: Intelligent ranking and deduplication
- 🖱️ **User-Friendly**: Modern web UI with adjustable search parameters
- 📊 **Transparent**: Shows search scores and matching chunks
- 💰 **Free Embeddings**: Uses Sentence Transformers (no API costs)
- 📈 **Scalable**: Handles thousands of awards with batch processing

## 🏗️ Architecture

- **Frontend**: HTML/CSS/JavaScript (vanilla, no frameworks)
- **Backend**: FastAPI (Python)
- **Database**: Supabase (PostgreSQL) + pgvector extension
- **Embeddings**: Sentence Transformers (`all-mpnet-base-v2`)
- **Search**: Parallel lexical + semantic search

## 📚 Documentation

- **[Complete Manual](docs/COMPLETE_MANUAL.md)** - Comprehensive guide covering everything
  - Installation & Setup
  - Architecture & Design
  - Database Schema
  - Search System
  - API Reference
  - Deployment
  - Troubleshooting

## 📖 Key Components

- **Lexical Search**: PostgreSQL Full-Text Search (GIN indexes)
- **Semantic Search**: Vector similarity search (pgvector)
- **Hybrid Search**: Weighted combination: `final_score = (α × semantic) + (β × lexical)`
- **Indexing Pipeline**: Chunking → Embedding → Vector Storage

## 🔧 Configuration

All configuration is done via environment variables. See `config/env.example` for all options.

**Key Settings:**
- `EMBEDDING_PROVIDER`: `sentence-transformers` (default, free) or `openai` (paid)
- `AWARDS_TABLE_NAME`: Table name for awards (default: `awards`)
- `AWARD_CHUNKS_TABLE_NAME`: Table name for chunks (default: `award_chunks`)
- `DEFAULT_AGENCY`: Default agency value (default: `PAMS`)

## 🚀 Deployment

### Local
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

### Tunnel Services (for public access)

**ngrok** (requires free account):
```bash
./scripts/deploy_ngrok.sh
```

**localtunnel** (no signup, free):
```bash
./scripts/deploy_localtunnel.sh
```

**Cloudflare Tunnel** (no signup):
```bash
./scripts/deploy.sh
```

See [Complete Manual - Deployment](docs/COMPLETE_MANUAL.md#11-deployment) for details.

## 📋 Project Structure

```
Search_Engine/
├── docs/
│   └── COMPLETE_MANUAL.md    # Comprehensive documentation
├── scripts/
│   ├── create_schema.py      # Create database schema
│   ├── delete_schema.py       # Delete schema components
│   ├── load_csv_to_supabase.py  # Load CSV data
│   ├── index_data.py         # Index data (chunking + embedding)
│   └── deploy*.sh            # Deployment scripts
├── src/
│   ├── api/                  # FastAPI application
│   ├── core/                 # Core search logic
│   ├── database/             # Database clients
│   └── indexing/             # Indexing pipeline
├── static/                   # Frontend UI
├── config/                   # Configuration templates
└── requirements.txt          # Python dependencies
```

## 🔍 Search Parameters

The UI allows adjusting search parameters:

- **Alpha (α)**: Semantic weight (0.0-1.0, default: 0.5)
  - Higher = more semantic similarity
  - Lower = more exact word matches

- **Beta (β)**: Lexical boost (0.0+, default: 10.0)
  - Higher = stronger boost for exact matches
  - Lower = more balanced with semantic

## 📝 License

Part of the SBIR Vector Search system.

## 🆘 Support

For detailed documentation, troubleshooting, and examples, see:
- **[Complete Manual](docs/COMPLETE_MANUAL.md)** - Full system documentation
