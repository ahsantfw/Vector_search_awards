# Deploy to Cloud Run from GitHub - Simple Guide

**For users with Cloud Run access only** - No Cloud Build setup needed!

---

## 🎯 Overview

This guide shows you how to deploy your SBIR Vector Search directly to Cloud Run by linking your GitHub repository. Cloud Run will build and deploy automatically.

**Time needed:** 15-20 minutes  
**Prerequisites:** GitHub repo pushed, Cloud Run access

---

## 📋 Before You Start

### 1. Push Code to GitHub

```bash
cd /Users/ahsanaftab/Dmitri/Vector_search_awards

# Add all deployment files
git add .
git commit -m "Add Cloud Run deployment configuration"
git push origin main
```

**✅ Verify:** Your code is on GitHub at your repository

### 2. Collect Required Credentials

Have these ready:

**Supabase (3 items):**
1. Project URL: `https://xxxxx.supabase.co`
2. Anon Key: `eyJhbGci...`
3. Database URL: `postgresql://postgres:[PASSWORD]@db.xxxxx.supabase.co:5432/postgres`

**Get from:** https://app.supabase.com/project/YOUR_PROJECT/settings/api

**OpenAI (1 item):**
4. API Key: `sk-proj-xxxxx...`

**Get from:** https://platform.openai.com/api-keys

**n8n Security (1 item):**
5. Generate API Key:
```bash
openssl rand -hex 32
# Example output: 7f8a9b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0
```

---

## 🚀 Deployment Steps

### Step 1: Open Cloud Run Console

1. Go to: https://console.cloud.google.com/run
2. Make sure project **gen-lang-client-0181108581** is selected (top bar)

![Screenshot placeholder: Cloud Run Console with project selector]

### Step 2: Create New Service

1. Click **"Create Service"** button (blue button at top)

2. Select **"Continuously deploy from a repository"** (first option)

3. Click **"Set up with Cloud Build"** button

![Screenshot placeholder: Create Service page with source options]

### Step 3: Connect GitHub Repository

1. Click **"Connect"** next to "Source repository"

2. In the popup:
   - Select **"GitHub"**
   - Click **"Continue"**
   - Authorize Google Cloud Build (if prompted)
   - Select your repository: **`Vector_search_awards`**
   - Click **"Next"**

![Screenshot placeholder: GitHub repository selection dialog]

3. Configure build:
   - **Branch:** `^main$`
   - **Build type:** Dockerfile
   - **Source location:** `/Dockerfile` (auto-detected)
   - Click **"Save"**

![Screenshot placeholder: Build configuration with Dockerfile option]

### Step 4: Configure Service Settings

**Service name:**
```
sbir-vector-search
```

**Region:**
```
us-central1
```
(Or choose closest to your users)

**Authentication:**
- ✅ **Allow unauthenticated invocations** (checked)

![Screenshot placeholder: Service settings with name and region]

### Step 5: Configure Container Settings

Scroll down to **"Container, Networking, Security"** section:

**Container Port:**
```
8080
```

**Resources:**
- **Memory:** `2 GiB`
- **CPU:** `2`
- **Request timeout:** `300` (seconds)
- **Maximum instances:** `10`
- **Minimum instances:** `1` (keeps service warm, prevents cold starts)

![Screenshot placeholder: Container resource settings]

### Step 6: Set Environment Variables

Still in **"Container, Networking, Security"**, click **"Variables & Secrets"** tab:

Click **"+ Add Variable"** for each of these:

| Name | Value | Notes |
|------|-------|-------|
| `ENVIRONMENT` | `production` | Fixed value |
| `API_HOST` | `0.0.0.0` | Fixed value |
| `API_PORT` | `8080` | Fixed value |
| `SUPABASE_URL` | `https://xxxxx.supabase.co` | From Supabase |
| `SUPABASE_KEY` | `eyJhbGci...` | From Supabase (anon key) |
| `DATABASE_URL` | `postgresql://postgres:...` | From Supabase |
| `OPENAI_API_KEY` | `sk-proj-...` | From OpenAI |
| `EMBEDDING_PROVIDER` | `openai` | Fixed value |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | Fixed value |
| `EMBEDDING_DIMENSION` | `3072` | Fixed value |
| `VECTOR_STORE` | `pgvector` | Fixed value |
| `INDEXING_API_KEY` | `7f8a9b2c3d4e5f6a...` | Generated earlier |

![Screenshot placeholder: Environment variables section with Add Variable button]

**🔐 Security Note:** These are secure - only visible to you and the service

### Step 7: Deploy!

1. Scroll to bottom
2. Click **"Create"** button

**⏳ Wait 15-20 minutes** for:
- Building Docker image (~15 min)
- Downloading ML models (~3 min)
- Deploying container (~2 min)

You'll see a progress indicator at the top of the page.

![Screenshot placeholder: Deployment in progress]

### Step 8: Get Your Service URL

Once deployed (green checkmark appears):

1. You'll see your service URL at the top:
   ```
   https://sbir-vector-search-xxxxxxxxxx-uc.a.run.app
   ```

2. **Copy this URL** - you'll need it for testing and n8n

![Screenshot placeholder: Deployed service with URL highlighted]

---

## ✅ Test Your Deployment

### Test 1: Health Check

```bash
# Replace with your actual URL
export SERVICE_URL="https://sbir-vector-search-xxxxxxxxxx-uc.a.run.app"

# Test health
curl $SERVICE_URL/health
```

**Expected response:**
```json
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

### Test 2: Open UI

Open in browser:
```
https://sbir-vector-search-xxxxxxxxxx-uc.a.run.app
```

You should see the search interface!

### Test 3: Search API

```bash
curl -X POST $SERVICE_URL/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "quantum computing",
    "top_k": 5
  }'
```

### Test 4: API Documentation

Open in browser:
```
https://sbir-vector-search-xxxxxxxxxx-uc.a.run.app/docs
```

You should see interactive API documentation!

---

## 🔄 Configure n8n Webhooks

Now that your service is deployed, set up n8n to trigger indexing.

### Step 1: Save Your Credentials

In your notes, save:
- **Service URL:** `https://sbir-vector-search-xxxxxxxxxx-uc.a.run.app`
- **Indexing API Key:** `7f8a9b2c3d4e5f6a...` (from earlier)

### Step 2: Create n8n Workflow

In n8n:

1. Create new workflow
2. Add **HTTP Request** node
3. Configure:

**Method:**
```
POST
```

**URL:**
```
https://sbir-vector-search-xxxxxxxxxx-uc.a.run.app/indexing/trigger
```

**Authentication:**
```
None (we use headers instead)
```

**Headers:**
```json
{
  "X-API-Key": "7f8a9b2c3d4e5f6a...",
  "Content-Type": "application/json"
}
```

**Body (JSON):**
```json
{
  "batch_size": 100,
  "force_reindex": false
}
```

### Step 3: Test n8n Webhook

Click **"Test workflow"** in n8n

**Expected response:**
```json
{
  "job_id": "full_20260201_120000",
  "status": "queued",
  "message": "Full indexing job queued successfully",
  "started_at": "2026-02-01T12:00:00"
}
```

### Step 4: Check Job Status

Add another HTTP Request node:

**Method:** `GET`  
**URL:** `https://YOUR-SERVICE.run.app/indexing/status/{{$json["job_id"]}}`

This tracks the indexing progress!

---

## 🔄 Update Your Service (Future Changes)

When you make code changes:

### Option A: Automatic (Recommended)

Just push to GitHub:

```bash
git add .
git commit -m "Updated search algorithm"
git push origin main
```

Cloud Run will automatically:
1. Detect the push
2. Rebuild the container
3. Deploy the new version
4. Takes ~15-20 minutes

**No manual steps needed!**

### Option B: Manual Rebuild

If automatic doesn't trigger:

1. Go to Cloud Run console
2. Click your service: **sbir-vector-search**
3. Click **"Edit & Deploy New Revision"**
4. Scroll to bottom
5. Click **"Deploy"**

---

## 📊 Monitor Your Service

### View Logs

**Via Console:**
1. Go to: https://console.cloud.google.com/run
2. Click **sbir-vector-search**
3. Click **"Logs"** tab
4. See real-time logs!

**Via Command Line:**
```bash
gcloud run services logs read sbir-vector-search \
  --region=us-central1 \
  --limit=50
```

### View Metrics

1. In Cloud Run console
2. Click your service
3. Click **"Metrics"** tab

See:
- Request count
- Latency
- Memory usage
- CPU utilization

### Set Up Alerts (Optional)

1. Go to: https://console.cloud.google.com/monitoring/alerting
2. Click **"Create Policy"**
3. Configure alert (e.g., "Alert if latency > 2 seconds")
4. Add notification (email, Slack, etc.)

---

## 🔧 Troubleshooting

### Issue 1: Build Fails

**Check logs:**
1. Cloud Run console → Your service → "Logs" tab
2. Look for error messages during build

**Common causes:**
- Missing dependencies in `requirements.txt`
- Dockerfile syntax error
- Out of memory during build

**Solution:**
```bash
# Test build locally
docker build -t test-build .
```

### Issue 2: Service Won't Start

**Check logs for:**
- `Missing environment variable`
- `Database connection failed`
- `OpenAI API key invalid`

**Solution:**
1. Cloud Run → Service → "Edit & Deploy New Revision"
2. Check **"Variables & Secrets"** tab
3. Verify all 12 environment variables are set correctly

### Issue 3: Health Check Fails

```bash
curl https://YOUR-SERVICE.run.app/health
```

If unhealthy:

**Check database connection:**
1. Verify `DATABASE_URL` is correct
2. Test from Supabase dashboard
3. Check Supabase project is active

**Check OpenAI key:**
1. Verify `OPENAI_API_KEY` is valid
2. Check quota at: https://platform.openai.com/account/usage

### Issue 4: n8n Webhook Returns 401 Unauthorized

**Check:**
1. `X-API-Key` header is set
2. Value matches `INDEXING_API_KEY` environment variable
3. No extra spaces or quotes

### Issue 5: Slow First Request (Cold Start)

If first request takes 20+ seconds:

**Already configured:**
- Minimum instances = 1 (keeps service warm)

**If still slow:**
1. Check logs for startup time
2. Consider increasing CPU to 4

```
Cloud Run → Edit → Resources → CPU: 4
```

### Issue 6: Out of Memory Errors

**In logs:** `Memory limit exceeded`

**Solution:**
1. Edit service
2. Increase memory to `4 GiB`
3. Deploy

---

## 💰 Cost Management

### Current Configuration

**Resources:**
- 2 GB RAM
- 2 vCPU
- 1 minimum instance (always running)

**Estimated cost:** $30-50/month

### Reduce Costs

**If low traffic:**

1. Edit service
2. Change **Minimum instances** to `0`
3. Save

**Trade-off:** First request will be slower (cold start)

**Cost:** $10-20/month

### Monitor Costs

1. Go to: https://console.cloud.google.com/billing
2. View project costs
3. See breakdown by service

---

## 🎯 API Endpoints Reference

Once deployed, your service has these endpoints:

### Public Endpoints (No Auth)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/health` | GET | Health check |
| `/docs` | GET | Interactive API docs |
| `/search` | POST | Search awards |
| `/indexing/status/{id}` | GET | Check indexing job status |
| `/indexing/jobs` | GET | List all jobs |

### Protected Endpoints (Require X-API-Key)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/indexing/trigger` | POST | Full reindex all awards |
| `/indexing/incremental` | POST | Index specific/recent awards |
| `/indexing/single` | POST | Index one award |
| `/indexing/jobs/{id}` | DELETE | Delete job from tracking |

### Example: Full Reindex

```bash
curl -X POST https://YOUR-SERVICE.run.app/indexing/trigger \
  -H "X-API-Key: YOUR_INDEXING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 100,
    "force_reindex": false
  }'
```

**Response:**
```json
{
  "job_id": "full_20260201_150000",
  "status": "queued",
  "message": "Full indexing job queued successfully",
  "started_at": "2026-02-01T15:00:00"
}
```

### Example: Check Status

```bash
curl https://YOUR-SERVICE.run.app/indexing/status/full_20260201_150000
```

**Response:**
```json
{
  "job_id": "full_20260201_150000",
  "status": "running",
  "started_at": "2026-02-01T15:00:00",
  "progress": {
    "total": 1000,
    "processed": 450
  }
}
```

---

## 📸 Screenshots Checklist

**For your client walkthrough, take screenshots of:**

1. ✅ Cloud Run console - Create Service button
2. ✅ Source selection - "Continuously deploy" option
3. ✅ GitHub authorization dialog
4. ✅ Repository selection
5. ✅ Build configuration with Dockerfile
6. ✅ Service settings (name, region)
7. ✅ Container resources configuration
8. ✅ Environment variables section
9. ✅ Deployment in progress
10. ✅ Deployed service with URL
11. ✅ Logs viewer
12. ✅ Metrics dashboard

---

## 🎓 Share with Your Client

Once deployed, share with your client:

### 1. Service URL
```
https://sbir-vector-search-xxxxxxxxxx-uc.a.run.app
```

### 2. API Endpoints for n8n
```
POST /indexing/trigger           - Full reindex
POST /indexing/incremental       - Update specific awards
GET  /indexing/status/{job_id}   - Check progress
```

### 3. Indexing API Key (Secure!)
```
7f8a9b2c3d4e5f6a... (keep private!)
```

### 4. Show Them How To:

**View logs:**
- Console → Cloud Run → sbir-vector-search → Logs tab

**Trigger indexing from n8n:**
- HTTP Request → URL with X-API-Key header

**Check service health:**
- Browser → https://YOUR-SERVICE.run.app/health

**Monitor costs:**
- Console → Billing

---

## ✅ Deployment Checklist

### Pre-Deployment
- [ ] Code pushed to GitHub
- [ ] Supabase URL & Key collected
- [ ] Database URL collected
- [ ] OpenAI API Key obtained
- [ ] Indexing API Key generated

### During Deployment
- [ ] Cloud Run service created
- [ ] GitHub repository connected
- [ ] Branch set to `main`
- [ ] Build type set to Dockerfile
- [ ] Service name: `sbir-vector-search`
- [ ] Region selected
- [ ] Memory set to 2 GiB
- [ ] CPU set to 2
- [ ] Minimum instances set to 1
- [ ] All 12 environment variables added
- [ ] Service deployed (wait ~15-20 min)

### Post-Deployment
- [ ] Service URL copied
- [ ] Health check tested (200 OK)
- [ ] UI accessible in browser
- [ ] Search API tested
- [ ] n8n webhook configured
- [ ] n8n test successful
- [ ] Logs visible in console
- [ ] Client notified with URL and API key

---

## 🚀 You're Done!

Your SBIR Vector Search is now running on Cloud Run!

**Key Points:**
- ✅ Every push to GitHub auto-deploys
- ✅ Service auto-scales based on traffic
- ✅ n8n can trigger indexing via API
- ✅ Logs and metrics in Cloud Run console
- ✅ Estimated cost: $30-50/month

**For more details:**
- Full documentation: `docs/CLOUD_RUN_DEPLOYMENT.md`
- Quick reference: `DEPLOYMENT_QUICKSTART.md`

---

## 🆘 Need Help?

**Quick checks:**
```bash
# Test health
curl https://YOUR-SERVICE.run.app/health

# View logs
gcloud run services logs read sbir-vector-search --region=us-central1
```

**Common issues:**
- **401 Unauthorized:** Check X-API-Key header
- **503 Unavailable:** Check environment variables
- **Slow response:** Increase CPU or set min instances to 1
- **Build fails:** Check Dockerfile and requirements.txt

**Success!** 🎉
