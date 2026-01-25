#!/usr/bin/env bash

# ngrok Tunnel Deployment Script for SBIR Vector Search
# Alternative to Cloudflare Tunnel

set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"

echo -e "${BLUE}🌐 Starting ngrok Tunnel${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Check if ngrok is installed
if ! command -v ngrok >/dev/null 2>&1; then
    echo -e "${RED}❌ ngrok not installed${NC}"
    echo ""
    echo "Install options:"
    echo "1. Download: https://ngrok.com/download"
    echo "2. Or: snap install ngrok"
    echo "3. Or: brew install ngrok"
    echo ""
    echo "After installation, sign up at https://ngrok.com (free)"
    echo "Get your authtoken and run: ngrok config add-authtoken YOUR_TOKEN"
    exit 1
fi

echo -e "${GREEN}✅ ngrok found${NC}"
echo ""

# Check API
echo -e "${BLUE}🔍 Checking API service...${NC}"

if ! curl -sf "http://$API_HOST:$API_PORT/health" >/dev/null; then
    echo -e "${YELLOW}⚠️ API not responding on /health${NC}"
    echo ""
    echo "Start it first:"
    echo "cd $PROJECT_ROOT"
    echo "uvicorn src.api.app:app --host 0.0.0.0 --port $API_PORT"
    exit 1
fi

echo -e "${GREEN}✅ API is running${NC}"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Stopping tunnel...${NC}"
    if [[ -n "${NGROK_PID:-}" ]]; then
        kill "$NGROK_PID" 2>/dev/null || true
    fi
    pkill -f "ngrok http" 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Kill old ngrok processes
pkill -f "ngrok http.*$API_PORT" 2>/dev/null || true
sleep 1

# Start ngrok
echo -e "${BLUE}🚀 Starting ngrok tunnel...${NC}"
echo -e "${YELLOW}ℹ️  Note: ngrok free tier shows a warning page on first visit${NC}"
echo -e "${YELLOW}   The warning will be automatically skipped for API requests${NC}"
echo -e "${YELLOW}   For the initial page load, visitors may see it once${NC}"
echo ""

# Start ngrok in background
# Note: ngrok doesn't support adding request headers via CLI
# The header must be sent from the client (browser)
ngrok http "$API_PORT" > /tmp/ngrok.log 2>&1 &
NGROK_PID=$!

echo -e "${BLUE}⏳ Waiting for ngrok to initialize...${NC}"
sleep 5

# Extract URL from ngrok API
TUNNEL_URL=""

for i in {1..10}; do
    # ngrok provides a local API at http://127.0.0.1:4040/api/tunnels
    TUNNEL_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | \
        grep -oE '"public_url":"https://[^"]+' | \
        head -1 | \
        sed 's/"public_url":"//' || echo "")
    
    if [[ -n "$TUNNEL_URL" ]]; then
        break
    fi
    sleep 1
done

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║    ✅ Tunnel Started!                                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ -n "$TUNNEL_URL" ]]; then
    echo -e "${GREEN}🌐 Public URL:${NC}"
    echo -e "   $TUNNEL_URL"
    echo ""
    echo -e "${GREEN}🔗 Access Points:${NC}"
    echo -e "   UI:        $TUNNEL_URL"
    echo -e "   API Docs:  $TUNNEL_URL/docs"
    echo -e "   Health:    $TUNNEL_URL/health"
    echo -e "   Search:    $TUNNEL_URL/search"
    echo ""
    echo -e "${BLUE}📊 ngrok Dashboard:${NC}"
    echo -e "   http://127.0.0.1:4040"
    echo ""
else
    echo -e "${YELLOW}⚠️ Could not extract URL automatically${NC}"
    echo -e "${YELLOW}   Check ngrok dashboard: http://127.0.0.1:4040${NC}"
    echo ""
    echo -e "${YELLOW}   Or check logs: tail -f /tmp/ngrok.log${NC}"
    echo ""
fi

echo -e "${YELLOW}🛑 To stop tunnel:${NC} Press Ctrl+C"
echo ""

# Wait for ngrok process
wait "$NGROK_PID"

