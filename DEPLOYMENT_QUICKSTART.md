# Cloud Run Deployment - Quick Start

🚀 **Your SBIR Vector Search is ready for Google Cloud Run!**

## What Was Created

### Core Files
- ✅ **`Dockerfile`** - Optimized container for Cloud Run
- ✅ **`.dockerignore`** - Reduces image size by 50%
- ✅ **`cloudbuild.yaml`** - Automated CI/CD from GitHub
- ✅ **`config/env.production.template`** - Production config template

### New API Features
- ✅ **`src/api/routes/indexing.py`** - n8n webhook endpoints
  - `POST /indexing/trigger` - Full reindex
  - `POST /indexing/incremental` - Update specific awards
  - `POST /indexing/single` - Index one award
  - `GET /indexing/status/{job_id}` - Check progress

### Performance Optimizations
- ✅ **`src/core/startup.py`** - Lazy loading & connection pooling
- ✅ **Enhanced health checks** - Memory, uptime, response time monitoring

### Documentation
- ✅ **`docs/CLOUD_RUN_DEPLOYMENT.md`** - Complete deployment guide (45+ pages)
- ✅ **`scripts/setup_cloudrun.sh`** - Automated setup script

## Deploy in 5 Minutes

### Prerequisites
```bash
# 1. Install gcloud CLI
brew install google-cloud-sdk  # macOS
# OR: https://cloud.google.com/sdk/docs/install

# 2. Set your GCP project
export GCP_PROJECT_ID="your-project-id"

# 3. Have these ready:
# - Supabase URL & Key
# - OpenAI API Key
# - Database URL (from Supabase)
```

### Option A: Automated Setup (Recommended)

```bash
# Run the setup script - it does everything!
./scripts/setup_cloudrun.sh
```

The script will:
1. Enable required GCP APIs
2. Build Docker image (~15 mins)
3. Collect your credentials
4. Deploy to Cloud Run
5. Give you the service URL

### Option B: Manual Setup

```bash
# 1. Enable APIs
gcloud services enable cloudbuild.googleapis.com run.googleapis.com

# 2. Build image
gcloud builds submit --tag gcr.io/$GCP_PROJECT_ID/sbir-vector-search:latest

# 3. Deploy
gcloud run deploy sbir-vector-search \
  --image gcr.io/$GCP_PROJECT_ID/sbir-vector-search:latest \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1

# 4. Set environment variables (replace with your values)
gcloud run services update sbir-vector-search \
  --region us-central1 \
  --set-env-vars="SUPABASE_URL=https://xxx.supabase.co,SUPABASE_KEY=xxx,DATABASE_URL=postgresql://...,OPENAI_API_KEY=sk-xxx,INDEXING_API_KEY=xxx"
```

## Test Your Deployment

```bash
# Get your service URL
SERVICE_URL=$(gcloud run services describe sbir-vector-search \
  --region us-central1 --format="value(status.url)")

# Test health
curl $SERVICE_URL/health

# Test search
curl -X POST $SERVICE_URL/search \
  -H "Content-Type: application/json" \
  -d '{"query": "quantum computing", "top_k": 5}'

# Open UI in browser
open $SERVICE_URL
```

## Setup n8n Webhooks

### Generate API Key
```bash
# Generate secure random key for n8n authentication
openssl rand -hex 32
# Save this as INDEXING_API_KEY in Cloud Run
```

### n8n HTTP Request Node Configuration

**Trigger Full Reindex:**
```
Method: POST
URL: https://YOUR-SERVICE.run.app/indexing/trigger
Headers:
  X-API-Key: [YOUR_INDEXING_API_KEY]
  Content-Type: application/json
Body:
  {
    "batch_size": 100,
    "force_reindex": false
  }
```

**Check Status:**
```
Method: GET
URL: https://YOUR-SERVICE.run.app/indexing/status/{{$json["job_id"]}}
```

## Connect GitHub for Auto-Deploy

1. Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Click "Connect Repository" → Select GitHub
3. Authorize and select `Vector_search_awards`
4. Create trigger:
   - Event: Push to branch `main`
   - Configuration: `cloudbuild.yaml`

Now every `git push` automatically deploys! 🎉

## Environment Variables Reference

**Required in Cloud Run:**
```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbGci...
DATABASE_URL=postgresql://postgres:...
OPENAI_API_KEY=sk-proj-...
INDEXING_API_KEY=abc123...  # Generate with: openssl rand -hex 32
```

**Optional (good defaults):**
```bash
ENVIRONMENT=production
EMBEDDING_PROVIDER=openai
VECTOR_STORE=pgvector
API_PORT=8080
```

## Monitoring & Logs

```bash
# View real-time logs
gcloud run services logs tail sbir-vector-search --region=us-central1

# View metrics in console
open "https://console.cloud.google.com/run/detail/us-central1/sbir-vector-search/metrics"
```

## Cost Estimate

**Cloud Run:**
- Free tier: 2M requests/month
- With 1 min instance: **$5-20/month**
- With traffic: **$30-50/month**

**OpenAI Embeddings:**
- $0.13 per 1M tokens
- 10,000 awards ≈ **$1.30**

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
gcloud run services logs read sbir-vector-search --region=us-central1 --limit=50

# Common issues:
# - Missing environment variables
# - Invalid database URL
# - OpenAI key not set
```

### Slow first request (cold start)
```bash
# Keep 1 instance warm (costs ~$10/month but eliminates cold starts)
gcloud run services update sbir-vector-search --min-instances=1
```

### Out of memory
```bash
# Increase to 4GB
gcloud run services update sbir-vector-search --memory=4Gi
```

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   GitHub    │────▶│ Cloud Build  │────▶│  Cloud Run  │
│ (Push Code) │     │ (Build Image)│     │  (Service)  │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │
                    ┌────────────────────────────┼────────────────────┐
                    │                            │                    │
                    ▼                            ▼                    ▼
              ┌──────────┐               ┌─────────────┐       ┌──────────┐
              │ Supabase │               │ OpenAI API  │       │   n8n    │
              │   (DB)   │               │ (Embeddings)│       │(Webhooks)│
              └──────────┘               └─────────────┘       └──────────┘
```

## API Endpoints

Once deployed, you have these endpoints:

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/` | GET | Web UI | No |
| `/docs` | GET | API documentation | No |
| `/health` | GET | Health check | No |
| `/search` | POST | Search awards | No |
| `/indexing/trigger` | POST | Full reindex | X-API-Key |
| `/indexing/incremental` | POST | Update awards | X-API-Key |
| `/indexing/status/{id}` | GET | Job status | No |

## Next Steps

1. ✅ Deploy to Cloud Run (use script above)
2. ✅ Test all endpoints
3. ✅ Configure n8n webhooks
4. ✅ Connect GitHub for auto-deploy
5. ✅ Set up monitoring alerts
6. ✅ Test indexing workflow

## Full Documentation

For detailed instructions with screenshots:
- **📖 [Complete Deployment Guide](docs/CLOUD_RUN_DEPLOYMENT.md)**

## Support

**Issues?**
- Check logs: `gcloud run services logs read sbir-vector-search`
- Review health: `curl YOUR_URL/health`
- See full guide: `docs/CLOUD_RUN_DEPLOYMENT.md`

---

**Ready to deploy? Run:** `./scripts/setup_cloudrun.sh` 🚀
