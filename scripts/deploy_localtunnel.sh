#!/usr/bin/env bash

# localtunnel Deployment Script for SBIR Vector Search
# Free, no signup required alternative

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

echo -e "${BLUE}🌐 Starting localtunnel${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Check if npx/node is installed
if ! command -v npx >/dev/null 2>&1; then
    echo -e "${RED}❌ npx/node not installed${NC}"
    echo ""
    echo "Install Node.js: https://nodejs.org/"
    echo "Or: sudo apt install nodejs npm"
    exit 1
fi

echo -e "${GREEN}✅ Node.js found${NC}"
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
    if [[ -n "${TUNNEL_PID:-}" ]]; then
        kill "$TUNNEL_PID" 2>/dev/null || true
    fi
    pkill -f "lt --port" 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Kill old localtunnel processes
pkill -f "lt --port.*$API_PORT" 2>/dev/null || true
sleep 1

# Start localtunnel
echo -e "${BLUE}🚀 Starting localtunnel...${NC}"

# Start localtunnel in background
npx -y localtunnel --port "$API_PORT" > /tmp/localtunnel.log 2>&1 &
TUNNEL_PID=$!

echo -e "${BLUE}⏳ Waiting for tunnel to initialize...${NC}"
sleep 8

# Extract URL from log
TUNNEL_URL=""

for i in {1..10}; do
    TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.loca\.lt' /tmp/localtunnel.log 2>/dev/null | head -1 || echo "")
    
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
    # Get tunnel password (public IP)
    echo -e "${BLUE}🔑 Getting tunnel password (public IP)...${NC}"
    TUNNEL_PASSWORD=$(curl -s https://loca.lt/mytunnelpassword 2>/dev/null || echo "")
    
    echo -e "${GREEN}🌐 Public URL:${NC}"
    echo -e "   $TUNNEL_URL"
    echo ""
    
    if [[ -n "$TUNNEL_PASSWORD" ]]; then
        echo -e "${GREEN}🔑 Tunnel Password (Public IP):${NC}"
        echo -e "   $TUNNEL_PASSWORD"
        echo ""
        echo -e "${YELLOW}ℹ️  Share this password with visitors to bypass the warning page${NC}"
        echo ""
    else
        echo -e "${YELLOW}⚠️  Could not get tunnel password automatically${NC}"
        echo -e "${YELLOW}   Get it manually: curl https://loca.lt/mytunnelpassword${NC}"
        echo ""
    fi
    
    echo -e "${GREEN}🔗 Access Points:${NC}"
    echo -e "   UI:        $TUNNEL_URL"
    echo -e "   API Docs:  $TUNNEL_URL/docs"
    echo -e "   Health:    $TUNNEL_URL/health"
    echo -e "   Search:    $TUNNEL_URL/search"
    echo ""
    echo -e "${BLUE}📋 Note:${NC}"
    echo -e "   Visitors will see a warning page on first visit"
    echo -e "   They need to enter the tunnel password above"
    echo -e "   After that, the warning won't appear for 7 days"
    echo ""
else
    echo -e "${YELLOW}⚠️ Could not extract URL automatically${NC}"
    echo -e "${YELLOW}   Check logs: tail -f /tmp/localtunnel.log${NC}"
    echo ""
fi

echo -e "${YELLOW}🛑 To stop tunnel:${NC} Press Ctrl+C"
echo ""

# Wait for tunnel process
wait "$TUNNEL_PID"

