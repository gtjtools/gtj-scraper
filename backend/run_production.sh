#!/bin/bash

# Production startup script for GTJ Scraper
# Runs FastAPI server and Hatchet worker

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create logs directory
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Log files with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FASTAPI_LOG="$LOG_DIR/fastapi_$TIMESTAMP.log"
HATCHET_LOG="$LOG_DIR/hatchet_$TIMESTAMP.log"

# Also create symlinks to latest logs
FASTAPI_LATEST="$LOG_DIR/fastapi_latest.log"
HATCHET_LATEST="$LOG_DIR/hatchet_latest.log"

# Load environment variables if .env exists
if [ -f .env ]; then
    echo -e "${GREEN}Loading environment variables from .env${NC}"
    export $(grep -v '^#' .env | xargs)
fi

# Check for required environment variables
if [ -z "$HATCHET_CLIENT_TOKEN" ]; then
    echo -e "${RED}Error: HATCHET_CLIENT_TOKEN is not set${NC}"
    echo "Please set it in your .env file or environment"
    exit 1
fi

# Function to cleanup background processes on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down services...${NC}"
    if [ ! -z "$FASTAPI_PID" ]; then
        kill $FASTAPI_PID 2>/dev/null || true
    fi
    if [ ! -z "$HATCHET_PID" ]; then
        kill $HATCHET_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}Services stopped${NC}"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup SIGINT SIGTERM EXIT

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  GTJ Scraper Production Startup${NC}"
echo -e "${GREEN}========================================${NC}"

# Start FastAPI server
echo -e "\n${YELLOW}Starting FastAPI server...${NC}"
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4 2>&1 | tee "$FASTAPI_LOG" &
FASTAPI_PID=$!
ln -sf "$FASTAPI_LOG" "$FASTAPI_LATEST"
echo -e "${GREEN}FastAPI server started (PID: $FASTAPI_PID)${NC}"
echo -e "Log: $FASTAPI_LOG"

# Wait a moment for FastAPI to initialize
sleep 2

# Start Hatchet worker
echo -e "\n${YELLOW}Starting Hatchet worker...${NC}"
python -m src.workers.batch_verify_worker 2>&1 | tee "$HATCHET_LOG" &
HATCHET_PID=$!
ln -sf "$HATCHET_LOG" "$HATCHET_LATEST"
echo -e "${GREEN}Hatchet worker started (PID: $HATCHET_PID)${NC}"
echo -e "Log: $HATCHET_LOG"

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  All services running${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Server:   process.trustjet.ai"
echo -e "FastAPI:  http://process.trustjet.ai:8000"
echo -e "API Docs: http://process.trustjet.ai:8000/docs"
echo -e "\n${YELLOW}Log files:${NC}"
echo -e "  FastAPI: tail -f $FASTAPI_LATEST"
echo -e "  Hatchet: tail -f $HATCHET_LATEST"
echo -e "\nPress Ctrl+C to stop all services"

# Wait for both processes
wait $FASTAPI_PID $HATCHET_PID
