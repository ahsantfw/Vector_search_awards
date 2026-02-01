# Google Cloud Run Deployment Guide

Complete step-by-step guide to deploy SBIR Vector Search to Google Cloud Run with GitHub integration and n8n webhook support.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Detailed Setup](#detailed-setup)
4. [GitHub Integration](#github-integration)
5. [Environment Variables](#environment-variables)
6. [n8n Webhook Integration](#n8n-webhook-integration)
7. [Monitoring & Logs](#monitoring--logs)
8. [Troubleshooting](#troubleshooting)
9. [Cost Optimization](#cost-optimization)

---

## Prerequisites

### Required Accounts & Access

- ✅ **Google Cloud Platform Account** with billing enabled
- ✅ **GitHub Repository** with your code (already set up)
- ✅ **Supabase Project** with awards data indexed
- ✅ **OpenAI API Key** for embeddings
- ✅ **GCP Project** with Owner or Editor role

### Required Tools

```bash
# Install Google Cloud SDK
# macOS
brew install google-cloud-sdk

# Linux
curl https://sdk.cloud.google.com | bash

# Verify installation
gcloud version
```

### API Keys Needed

1. **Supabase**:
   - URL: `https://app.supabase.com/project/YOUR_PROJECT/settings/api`
   - Copy: `Project URL` and `anon/public key`

2. **OpenAI**:
   - URL: `https://platform.openai.com/api-keys`
   - Create new API key

3. **Generate Indexing API Key**:
   ```bash
   openssl rand -hex 32
   # Save this for n8n webhook authentication
   ```

---

## Quick Start

For experienced users, use our automated setup script:

```bash
# 1. Clone your repository
git clone https://github.com/YOUR_USERNAME/Vector_search_awards.git
cd Vector_search_awards

# 2. Set your GCP project ID
export GCP_PROJECT_ID="your-gcp-project-id"

# 3. Run setup script
./scripts/setup_cloudrun.sh
```

The script will:
- ✅ Enable required GCP APIs
- ✅ Build Docker image
- ✅ Collect environment variables
- ✅ Deploy to Cloud Run
- ✅ Provide service URL

---

## Detailed Setup

### Step 1: GCP Project Setup

#### 1.1 Create or Select Project

**Via Console:**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click project dropdown → "New Project"
3. Enter project name: `sbir-vector-search`
4. Click "Create"

**Screenshot placeholder:**
```
[Screenshot: GCP Console - New Project Dialog]
- Show project creation form
- Highlight "Create" button
```

**Via CLI:**
```bash
# Create new project
gcloud projects create sbir-vector-search --name="SBIR Vector Search"

# Set as active project
gcloud config set project sbir-vector-search

# Verify
gcloud config get-value project
```

#### 1.2 Enable Billing

1. Go to [Billing](https://console.cloud.google.com/billing)
2. Link a billing account to your project
3. Verify billing is enabled

**Screenshot placeholder:**
```
[Screenshot: GCP Console - Billing Setup]
- Show billing account linking
```

#### 1.3 Enable Required APIs

```bash
# Enable Cloud Run, Cloud Build, and Container Registry
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Verify
gcloud services list --enabled | grep -E "cloudbuild|run|container"
```

**Expected output:**
```
cloudbuild.googleapis.com          Cloud Build API
containerregistry.googleapis.com   Container Registry API
run.googleapis.com                 Cloud Run Admin API
```

---

### Step 2: GitHub Repository Setup

#### 2.1 Connect GitHub to Cloud Build

**Via Console:**
1. Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Click "Connect Repository"
3. Select "GitHub"
4. Authenticate and authorize Google Cloud Build
5. Select your repository: `YOUR_USERNAME/Vector_search_awards`
6. Click "Connect"

**Screenshot placeholder:**
```
[Screenshot: Cloud Build - Connect Repository]
- Show GitHub authentication dialog
- Highlight repository selection
```

#### 2.2 Create Build Trigger (Optional - for Auto-Deploy)

1. In Cloud Build Triggers, click "Create Trigger"
2. Configure:
   - **Name**: `deploy-on-push`
   - **Event**: Push to a branch
   - **Source**: `^main$` (regex for main branch)
   - **Configuration**: Cloud Build configuration file
   - **Location**: `/cloudbuild.yaml`
3. Click "Create"

**Screenshot placeholder:**
```
[Screenshot: Cloud Build - Create Trigger]
- Show trigger configuration form
- Highlight branch pattern and config location
```

Now, every push to `main` branch will automatically rebuild and deploy!

---

### Step 3: Build Docker Image

#### Option A: Cloud Build (Recommended)

```bash
# Set variables
export PROJECT_ID="your-gcp-project-id"
export IMAGE_NAME="gcr.io/${PROJECT_ID}/sbir-vector-search"

# Build using Cloud Build (handles everything in cloud)
gcloud builds submit --tag ${IMAGE_NAME}:latest --timeout=30m

# This will:
# - Upload your code to GCP
# - Build Docker image in cloud
# - Push to Container Registry
# - Takes ~15-20 minutes (downloads ML models)
```

**Screenshot placeholder:**
```
[Screenshot: Terminal - Cloud Build Progress]
- Show build steps executing
- Highlight "BUILD SUCCESS" message
```

#### Option B: Local Docker Build

```bash
# Build locally (requires Docker installed)
docker build -t ${IMAGE_NAME}:latest .

# Push to Container Registry
docker push ${IMAGE_NAME}:latest
```

---

### Step 4: Configure Environment Variables

Create a file with your production environment variables:

```bash
# Copy template
cp config/env.production.template config/env.production.local

# Edit with your values
nano config/env.production.local
```

**Required variables:**

```bash
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# PostgreSQL (from Supabase)
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.xxxxx.supabase.co:5432/postgres

# OpenAI
OPENAI_API_KEY=sk-proj-xxxxx...

# Security (generate random key)
INDEXING_API_KEY=abc123def456...  # Use: openssl rand -hex 32
```

**Where to find these:**

1. **Supabase Credentials**:
   - Go to: https://app.supabase.com/project/YOUR_PROJECT/settings/api
   - Copy: Project URL → `SUPABASE_URL`
   - Copy: Project API keys → `anon` key → `SUPABASE_KEY`

2. **Database URL**:
   - Go to: https://app.supabase.com/project/YOUR_PROJECT/settings/database
   - Copy: Connection string → URI format
   - Replace `[YOUR-PASSWORD]` with your database password

**Screenshot placeholder:**
```
[Screenshot: Supabase Dashboard - API Settings]
- Show Project URL and API keys
- Highlight anon/public key
```

---

### Step 5: Deploy to Cloud Run

#### 5.1 Initial Deployment

```bash
# Set variables
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"  # Or your preferred region
export SERVICE_NAME="sbir-vector-search"
export IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Deploy
gcloud run deploy ${SERVICE_NAME} \
  --image=${IMAGE_NAME}:latest \
  --region=${REGION} \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --max-instances=10 \
  --min-instances=1 \
  --port=8080 \
  --set-env-vars="ENVIRONMENT=production,API_HOST=0.0.0.0,API_PORT=8080,EMBEDDING_PROVIDER=openai,VECTOR_STORE=pgvector"
```

**Parameters explained:**
- `--memory=2Gi`: 2GB RAM (enough for API + model)
- `--cpu=2`: 2 vCPUs for fast processing
- `--timeout=300`: 5 minutes (for long-running indexing)
- `--max-instances=10`: Auto-scale up to 10 instances
- `--min-instances=1`: Keep 1 warm (faster first request)
- `--allow-unauthenticated`: Public access (change if needed)

#### 5.2 Set Environment Variables

After initial deployment, add your secrets:

```bash
# Update with all environment variables
gcloud run services update ${SERVICE_NAME} \
  --region=${REGION} \
  --set-env-vars="SUPABASE_URL=https://xxx.supabase.co,SUPABASE_KEY=eyJhbGci...,DATABASE_URL=postgresql://postgres:...,OPENAI_API_KEY=sk-proj-...,INDEXING_API_KEY=abc123..."
```

**Or via Console (Recommended for secrets):**

1. Go to [Cloud Run Services](https://console.cloud.google.com/run)
2. Click your service: `sbir-vector-search`
3. Click "Edit & Deploy New Revision"
4. Scroll to "Variables & Secrets"
5. Click "+ Add Variable" for each:

**Screenshot placeholder:**
```
[Screenshot: Cloud Run Console - Environment Variables]
- Show environment variables section
- Highlight "+ Add Variable" button
```

**Add these variables:**
| Name | Value |
|------|-------|
| `SUPABASE_URL` | Your Supabase URL |
| `SUPABASE_KEY` | Your Supabase anon key |
| `DATABASE_URL` | PostgreSQL connection string |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `INDEXING_API_KEY` | Random generated key |
| `ENVIRONMENT` | `production` |
| `EMBEDDING_PROVIDER` | `openai` |
| `VECTOR_STORE` | `pgvector` |

6. Click "Deploy"

#### 5.3 Get Service URL

```bash
# Get your service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
  --region=${REGION} \
  --format="value(status.url)")

echo "Service URL: ${SERVICE_URL}"
```

**Example output:**
```
Service URL: https://sbir-vector-search-abc123-uc.a.run.app
```

---

### Step 6: Test Deployment

#### 6.1 Health Check

```bash
# Check if service is healthy
curl ${SERVICE_URL}/health

# Expected response (status: 200)
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production",
  "components": {
    "database": "connected",
    "vector_store": "configured",
    "embeddings": "openai_configured"
  }
}
```

#### 6.2 Test Search

```bash
# Test search endpoint
curl -X POST ${SERVICE_URL}/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "quantum computing",
    "top_k": 5
  }'
```

#### 6.3 Access UI

Open in browser:
```
https://sbir-vector-search-abc123-uc.a.run.app
```

**Screenshot placeholder:**
```
[Screenshot: Browser - SBIR Search UI]
- Show the web interface
- Highlight search box and results
```

---

## GitHub Integration

### Automatic Deployment on Git Push

With Cloud Build trigger configured (Step 2.2), deployments are automatic:

```bash
# 1. Make code changes
git add .
git commit -m "Updated search algorithm"
git push origin main

# 2. Cloud Build automatically:
#    - Detects push to main
#    - Builds Docker image
#    - Deploys to Cloud Run
#    - Takes ~15-20 minutes

# 3. Monitor build
gcloud builds list --limit=5
```

**View build logs:**
1. Go to [Cloud Build History](https://console.cloud.google.com/cloud-build/builds)
2. Click latest build
3. View real-time logs

**Screenshot placeholder:**
```
[Screenshot: Cloud Build History]
- Show build list with status
- Highlight successful build
```

### Manual Deployment

If you want to deploy manually:

```bash
# Build and deploy in one command
gcloud builds submit --config cloudbuild.yaml
```

---

## Environment Variables

### Complete List

All environment variables that can be configured:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | No | `production` | Environment name |
| `DEBUG` | No | `false` | Enable debug mode |
| `SUPABASE_URL` | **Yes** | - | Supabase project URL |
| `SUPABASE_KEY` | **Yes** | - | Supabase anon key |
| `DATABASE_URL` | **Yes** | - | PostgreSQL connection string |
| `VECTOR_STORE` | No | `pgvector` | Vector store type |
| `EMBEDDING_PROVIDER` | No | `openai` | Embedding provider |
| `OPENAI_API_KEY` | **Yes** | - | OpenAI API key |
| `EMBEDDING_MODEL` | No | `text-embedding-3-large` | OpenAI model name |
| `EMBEDDING_DIMENSION` | No | `3072` | Embedding dimensions |
| `INDEXING_API_KEY` | **Yes** | - | API key for indexing endpoints |
| `DEFAULT_TOP_K` | No | `10` | Default search results |
| `MAX_TOP_K` | No | `100` | Maximum search results |
| `LEXICAL_BOOST` | No | `10.0` | Lexical search boost |
| `SEMANTIC_WEIGHT` | No | `0.5` | Semantic search weight |
| `API_HOST` | No | `0.0.0.0` | API host |
| `API_PORT` | No | `8080` | API port (Cloud Run uses 8080) |

### Setting Environment Variables

**Method 1: Via gcloud CLI**
```bash
gcloud run services update sbir-vector-search \
  --region=us-central1 \
  --set-env-vars="KEY1=value1,KEY2=value2"
```

**Method 2: Via Console** (Recommended)
1. Cloud Run → Service → Edit & Deploy New Revision
2. Variables & Secrets → Add Variable
3. Deploy

**Method 3: Via cloudbuild.yaml**
Edit the `--set-env-vars` line in `cloudbuild.yaml`

---

## n8n Webhook Integration

### Overview

The deployed service provides API endpoints for n8n to trigger indexing jobs:

```
POST /indexing/trigger       - Full reindex
POST /indexing/incremental   - Incremental update
POST /indexing/single        - Index one award
GET  /indexing/status/{job_id} - Check job status
```

### Setup in n8n

#### Step 1: Create Webhook Node

1. In n8n, create new workflow
2. Add **Webhook** node (trigger)
3. Configure:
   - **Method**: `POST`
   - **Path**: `trigger-indexing`

#### Step 2: Add HTTP Request Node

1. Add **HTTP Request** node
2. Configure:

```
Method: POST
URL: https://YOUR-SERVICE.run.app/indexing/trigger
Authentication: None (using headers)

Headers:
  Content-Type: application/json
  X-API-Key: [YOUR_INDEXING_API_KEY]

Body (JSON):
{
  "batch_size": 100,
  "force_reindex": false
}
```

**Screenshot placeholder:**
```
[Screenshot: n8n - HTTP Request Node Configuration]
- Show URL field with Cloud Run endpoint
- Highlight X-API-Key header
```

#### Step 3: Add Status Check (Optional)

To monitor job progress:

1. Add **HTTP Request** node
2. Configure:

```
Method: GET
URL: https://YOUR-SERVICE.run.app/indexing/status/{{$json["job_id"]}}
```

### Example Workflows

#### Workflow 1: Trigger on Supabase Insert

```
[Supabase Trigger] → [Get New Records] → [HTTP: Incremental Index]
```

#### Workflow 2: Scheduled Full Reindex

```
[Schedule: Daily 3AM] → [HTTP: Full Reindex] → [Slack: Notify]
```

#### Workflow 3: Manual Trigger with Status

```
[Manual Trigger] → [HTTP: Start Index] → [Wait 10s] → [HTTP: Check Status] → [Loop if Running]
```

### API Examples

#### Trigger Full Reindex

```bash
curl -X POST https://YOUR-SERVICE.run.app/indexing/trigger \
  -H "X-API-Key: YOUR_INDEXING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 100,
    "force_reindex": true
  }'

# Response:
{
  "job_id": "full_20260201_120000",
  "status": "queued",
  "message": "Full indexing job queued successfully",
  "started_at": "2026-02-01T12:00:00"
}
```

#### Incremental Update

```bash
curl -X POST https://YOUR-SERVICE.run.app/indexing/incremental \
  -H "X-API-Key: YOUR_INDEXING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "award_ids": ["award123", "award456"]
  }'
```

#### Check Job Status

```bash
curl https://YOUR-SERVICE.run.app/indexing/status/full_20260201_120000

# Response:
{
  "job_id": "full_20260201_120000",
  "status": "running",
  "started_at": "2026-02-01T12:00:00",
  "progress": {
    "total": 1000,
    "processed": 450
  }
}
```

---

## Monitoring & Logs

### View Logs

**Via Console:**
1. Go to [Cloud Run Services](https://console.cloud.google.com/run)
2. Click your service
3. Click "Logs" tab

**Screenshot placeholder:**
```
[Screenshot: Cloud Run Console - Logs Tab]
- Show log entries
- Highlight filter options
```

**Via gcloud CLI:**
```bash
# Tail logs in real-time
gcloud run services logs tail sbir-vector-search --region=us-central1

# View recent logs
gcloud run services logs read sbir-vector-search \
  --region=us-central1 \
  --limit=100

# Filter by severity
gcloud run services logs read sbir-vector-search \
  --region=us-central1 \
  --log-filter="severity>=ERROR"
```

### Metrics & Monitoring

**View Metrics:**
1. Cloud Run → Service → Metrics tab

**Available metrics:**
- Request count
- Request latency
- Container instance count
- CPU utilization
- Memory utilization
- Billable container time

**Screenshot placeholder:**
```
[Screenshot: Cloud Run - Metrics Dashboard]
- Show request count and latency graphs
```

### Set Up Alerts

1. Go to [Monitoring](https://console.cloud.google.com/monitoring)
2. Alerting → Create Policy
3. Configure conditions:
   - **Metric**: Cloud Run → Request latency
   - **Condition**: > 2 seconds
   - **Duration**: 5 minutes
4. Add notification channel (email, Slack, etc.)

---

## Troubleshooting

### Common Issues

#### Issue 1: Container fails to start

**Symptoms:**
- Service shows "Service Unavailable"
- Logs show container exits immediately

**Solutions:**
```bash
# Check logs for startup errors
gcloud run services logs read sbir-vector-search --region=us-central1 --limit=50

# Common causes:
# 1. Missing environment variables
# 2. Database connection failure
# 3. OpenAI API key invalid

# Verify environment variables are set
gcloud run services describe sbir-vector-search \
  --region=us-central1 \
  --format="yaml(spec.template.spec.containers[0].env)"
```

#### Issue 2: Slow first request (Cold Start)

**Symptoms:**
- First request takes 30+ seconds
- Subsequent requests are fast

**Solutions:**
```bash
# Increase minimum instances to keep container warm
gcloud run services update sbir-vector-search \
  --region=us-central1 \
  --min-instances=1

# This costs more but eliminates cold starts
```

#### Issue 3: Out of Memory

**Symptoms:**
- Logs show "Memory limit exceeded"
- Container restarts frequently

**Solutions:**
```bash
# Increase memory allocation
gcloud run services update sbir-vector-search \
  --region=us-central1 \
  --memory=4Gi

# Also check for memory leaks in logs
```

#### Issue 4: Database Connection Timeout

**Symptoms:**
- Health check shows "database: disconnected"
- Search returns 503 errors

**Solutions:**
1. Verify DATABASE_URL is correct
2. Check Supabase project is active
3. Verify network access (Cloud Run → Supabase)
4. Check connection pool settings

```bash
# Test database connection
gcloud run services logs read sbir-vector-search \
  --region=us-central1 \
  --log-filter="database"
```

#### Issue 5: OpenAI API Rate Limiting

**Symptoms:**
- Indexing fails with rate limit errors
- Logs show "429 Too Many Requests"

**Solutions:**
- Reduce `INDEXING_BATCH_SIZE` in environment
- Add retry logic (already implemented)
- Upgrade OpenAI plan for higher limits

### Debug Mode

Enable debug logging:

```bash
gcloud run services update sbir-vector-search \
  --region=us-central1 \
  --set-env-vars="LOG_LEVEL=DEBUG"
```

---

## Cost Optimization

### Cloud Run Pricing (as of 2026)

**Free Tier (per month):**
- 2 million requests
- 360,000 GB-seconds memory
- 180,000 vCPU-seconds

**Paid Usage:**
- Memory: $0.0000025 per GB-second
- CPU: $0.00002400 per vCPU-second
- Requests: $0.40 per million

### Estimated Monthly Costs

**Scenario 1: Low Usage (within free tier)**
- 1M requests/month
- 1 min instance (always warm)
- **Cost: $0-5/month**

**Scenario 2: Medium Usage**
- 10M requests/month
- 2 min instances
- **Cost: $30-50/month**

**Scenario 3: High Usage**
- 100M requests/month
- 5 min instances, 10 max instances
- **Cost: $200-300/month**

### Optimization Tips

1. **Reduce minimum instances** when not in use:
```bash
# During off-hours
gcloud run services update sbir-vector-search --min-instances=0

# During business hours
gcloud run services update sbir-vector-search --min-instances=1
```

2. **Use Sentence Transformers instead of OpenAI** (free embeddings):
```bash
gcloud run services update sbir-vector-search \
  --set-env-vars="EMBEDDING_PROVIDER=sentence-transformers"
```

3. **Enable request throttling** for indexing endpoints

4. **Monitor costs** in [GCP Billing](https://console.cloud.google.com/billing)

### OpenAI Costs

**Embedding costs:**
- text-embedding-3-large: $0.13 per 1M tokens
- Average award: ~1000 tokens
- 10,000 awards: ~$1.30

**Optimization:**
- Cache embeddings (already implemented)
- Use incremental indexing
- Consider Sentence Transformers for large datasets

---

## Additional Resources

### Documentation
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Build Documentation](https://cloud.google.com/build/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

### Support
- **GCP Issues**: [Cloud Run Issue Tracker](https://issuetracker.google.com/issues?q=componentid:187143)
- **Application Issues**: Check logs and health endpoints

### Next Steps

1. ✅ Deploy to Cloud Run
2. ✅ Test all endpoints
3. ✅ Configure n8n webhooks
4. ✅ Set up monitoring alerts
5. ✅ Enable automatic backups (Supabase)
6. ✅ Document your indexing workflow

---

**Congratulations! Your SBIR Vector Search is now running on Cloud Run! 🎉**
