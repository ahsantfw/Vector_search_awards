#!/usr/bin/env bash

# Cloudflare Tunnel Starter — Stable Version
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

LOG_FILE="/tmp/cloudflare-sbir.log"

echo -e "${BLUE}🌐 Starting Cloudflare Tunnel${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# ------------------------------------------------------------
# Checks
# ------------------------------------------------------------

if ! command -v cloudflared >/dev/null 2>&1; then
    echo -e "${RED}❌ cloudflared not installed${NC}"
    echo "Install: sudo apt install cloudflared"
    exit 1
fi

echo -e "${GREEN}✅ cloudflared found${NC}"
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

# ------------------------------------------------------------
# Cleanup
# ------------------------------------------------------------

cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Stopping tunnel...${NC}"
    if [[ -n "${TUNNEL_PID:-}" ]]; then
        kill "$TUNNEL_PID" 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# Kill old tunnels
pkill -f "cloudflared tunnel.*$API_PORT" 2>/dev/null || true
sleep 1

# ------------------------------------------------------------
# Start tunnel
# ------------------------------------------------------------

echo -e "${BLUE}🚀 Launching cloudflared...${NC}"

rm -f "$LOG_FILE"

cloudflared tunnel --url "http://$API_HOST:$API_PORT" \
    --logfile "$LOG_FILE" \
    --loglevel info &

TUNNEL_PID=$!

echo -e "${BLUE}⏳ Waiting for tunnel to initialize...${NC}"
sleep 8

# ------------------------------------------------------------
# Extract URL
# ------------------------------------------------------------

TUNNEL_URL=""

for _ in {1..5}; do
    TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$LOG_FILE" | head -1 || true)
    [[ -n "$TUNNEL_URL" ]] && break
    sleep 2
done

if [[ -n "$TUNNEL_URL" ]]; then
    echo -e "${GREEN}✅ Tunnel URL:${NC} $TUNNEL_URL"
else
    echo -e "${YELLOW}⚠️ Could not auto-detect URL yet.${NC}"
    echo "Watch logs:"
    echo "tail -f $LOG_FILE"
fi

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}   🎉 Tunnel is running!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

if [[ -n "$TUNNEL_URL" ]]; then
    echo "Docs:   $TUNNEL_URL/docs"
    echo "Health: $TUNNEL_URL/health"
    echo "Search: $TUNNEL_URL/search"
fi

echo ""
echo -e "${BLUE}📋 Logs:${NC} tail -f $LOG_FILE"
echo -e "${YELLOW}🛑 Stop:${NC} Ctrl+C"
echo ""

# ------------------------------------------------------------
# Wait forever on tunnel
# ------------------------------------------------------------

wait "$TUNNEL_PID"
