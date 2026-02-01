#!/usr/bin/env bash

# ============================================
# Google Cloud Run Setup Script
# Sets up and deploys SBIR Vector Search to Cloud Run
# ============================================

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="sbir-vector-search"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}Google Cloud Run Setup for SBIR Vector Search${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ============================================
# Step 1: Validate Prerequisites
# ============================================

echo -e "${BLUE}Step 1: Validating prerequisites...${NC}"

# Check if gcloud is installed
if ! command -v gcloud >/dev/null 2>&1; then
    echo -e "${RED}❌ gcloud CLI not found${NC}"
    echo "Install: https://cloud.google.com/sdk/docs/install"
    exit 1
fi
echo -e "${GREEN}✅ gcloud CLI found${NC}"

# Check if project ID is set
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}⚠️  GCP_PROJECT_ID not set${NC}"
    echo "Enter your GCP Project ID:"
    read -r PROJECT_ID
    
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}❌ Project ID is required${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✅ Project ID: ${PROJECT_ID}${NC}"

# Set the project
gcloud config set project "$PROJECT_ID"

echo ""

# ============================================
# Step 2: Enable Required APIs
# ============================================

echo -e "${BLUE}Step 2: Enabling required Google Cloud APIs...${NC}"

gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com

echo -e "${GREEN}✅ APIs enabled${NC}"
echo ""

# ============================================
# Step 3: Build Docker Image
# ============================================

echo -e "${BLUE}Step 3: Building Docker image...${NC}"
echo "This may take 10-15 minutes (downloading ML models)..."

# Build locally or use Cloud Build
echo "Choose build method:"
echo "  1) Cloud Build (recommended, uses GCP infrastructure)"
echo "  2) Local Docker (requires Docker installed)"
read -r -p "Enter choice [1]: " BUILD_METHOD
BUILD_METHOD=${BUILD_METHOD:-1}

if [ "$BUILD_METHOD" = "1" ]; then
    # Use Cloud Build
    echo -e "${BLUE}Building with Cloud Build...${NC}"
    gcloud builds submit --tag "$IMAGE_NAME:latest" --timeout=30m
elif [ "$BUILD_METHOD" = "2" ]; then
    # Local Docker build
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker not found${NC}"
        exit 1
    fi
    
    echo -e "${BLUE}Building locally with Docker...${NC}"
    docker build -t "$IMAGE_NAME:latest" .
    docker push "$IMAGE_NAME:latest"
else
    echo -e "${RED}❌ Invalid choice${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker image built and pushed${NC}"
echo ""

# ============================================
# Step 4: Collect Environment Variables
# ============================================

echo -e "${BLUE}Step 4: Configuring environment variables...${NC}"
echo ""

echo "Enter your environment variables (press Enter to use default):"
echo ""

read -r -p "Supabase URL: " SUPABASE_URL
read -r -p "Supabase Key: " SUPABASE_KEY
read -r -p "Database URL (PostgreSQL): " DATABASE_URL
read -r -p "OpenAI API Key: " OPENAI_API_KEY
read -r -p "Indexing API Key (for n8n, generate random string): " INDEXING_API_KEY

# Build env vars string
ENV_VARS="ENVIRONMENT=production"
ENV_VARS="${ENV_VARS},API_HOST=0.0.0.0"
ENV_VARS="${ENV_VARS},API_PORT=8080"
ENV_VARS="${ENV_VARS},EMBEDDING_PROVIDER=openai"
ENV_VARS="${ENV_VARS},VECTOR_STORE=pgvector"

[ -n "$SUPABASE_URL" ] && ENV_VARS="${ENV_VARS},SUPABASE_URL=${SUPABASE_URL}"
[ -n "$SUPABASE_KEY" ] && ENV_VARS="${ENV_VARS},SUPABASE_KEY=${SUPABASE_KEY}"
[ -n "$DATABASE_URL" ] && ENV_VARS="${ENV_VARS},DATABASE_URL=${DATABASE_URL}"
[ -n "$OPENAI_API_KEY" ] && ENV_VARS="${ENV_VARS},OPENAI_API_KEY=${OPENAI_API_KEY}"
[ -n "$INDEXING_API_KEY" ] && ENV_VARS="${ENV_VARS},INDEXING_API_KEY=${INDEXING_API_KEY}"

echo ""
echo -e "${GREEN}✅ Environment variables configured${NC}"
echo ""

# ============================================
# Step 5: Deploy to Cloud Run
# ============================================

echo -e "${BLUE}Step 5: Deploying to Cloud Run...${NC}"

gcloud run deploy "$SERVICE_NAME" \
    --image="$IMAGE_NAME:latest" \
    --region="$REGION" \
    --platform=managed \
    --allow-unauthenticated \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --max-instances=10 \
    --min-instances=1 \
    --port=8080 \
    --set-env-vars="$ENV_VARS"

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""

# ============================================
# Step 6: Get Service URL
# ============================================

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(status.url)")

echo -e "${BLUE}============================================${NC}"
echo -e "${GREEN}🎉 Deployment Successful!${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "${GREEN}Service URL:${NC} $SERVICE_URL"
echo ""
echo -e "${BLUE}Available Endpoints:${NC}"
echo "  • UI:           $SERVICE_URL"
echo "  • API Docs:     $SERVICE_URL/docs"
echo "  • Health:       $SERVICE_URL/health"
echo "  • Search:       $SERVICE_URL/search"
echo "  • Indexing:     $SERVICE_URL/indexing/trigger"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. Test the deployment:"
echo "   curl $SERVICE_URL/health"
echo ""
echo "2. Test search:"
echo "   curl -X POST $SERVICE_URL/search -H 'Content-Type: application/json' -d '{\"query\": \"quantum computing\", \"top_k\": 5}'"
echo ""
echo "3. Configure n8n webhook to trigger indexing:"
echo "   POST $SERVICE_URL/indexing/trigger"
echo "   Header: X-API-Key: [your INDEXING_API_KEY]"
echo ""
echo -e "${YELLOW}⚠️  Important: Save your INDEXING_API_KEY for n8n configuration${NC}"
echo ""
echo -e "${BLUE}View logs:${NC}"
echo "  gcloud run services logs read $SERVICE_NAME --region=$REGION"
echo ""
echo -e "${BLUE}Update service:${NC}"
echo "  1. Push code to GitHub"
echo "  2. Cloud Build will automatically rebuild and deploy"
echo "  OR run: gcloud builds submit --tag $IMAGE_NAME:latest"
echo ""
echo -e "${GREEN}Done! 🚀${NC}"
