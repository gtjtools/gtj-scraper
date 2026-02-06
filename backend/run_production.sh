#!/bin/bash

# Production startup script for GTJ Scraper
# Runs FastAPI server and Hatchet worker

set -e

#   Usage:

#   # Start services
#   ./run_production.sh

#   # Stop services
#   ./run_production.sh stop

#   # Check if running
#   ps aux | grep uvicorn
#   ps aux | grep batch_verify

#   # View logs
#   tail -f logs/fastapi_latest.log
#   tail -f logs/hatchet_latest.log

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

# Activate virtual environment (create if doesn't exist)
if [ -d "venv" ]; then
    echo -e "${GREEN}Activating virtual environment${NC}"
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo -e "${GREEN}Activating virtual environment${NC}"
    source .venv/bin/activate
else
    echo -e "${YELLOW}No virtual environment found. Creating one...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    echo -e "${GREEN}Installing dependencies...${NC}"
    pip install -r requirements.txt
    echo -e "${GREEN}Virtual environment created and dependencies installed${NC}"
fi

# Check for required environment variables
if [ -z "$HATCHET_CLIENT_TOKEN" ]; then
    echo -e "${RED}Error: HATCHET_CLIENT_TOKEN is not set${NC}"
    echo "Please set it in your .env file or environment"
    exit 1
fi

# Function to stop services (can be called with: ./run_production.sh stop)
stop_services() {
    echo -e "${YELLOW}Stopping services...${NC}"
    if [ -f "$LOG_DIR/fastapi.pid" ]; then
        kill $(cat "$LOG_DIR/fastapi.pid") 2>/dev/null && echo -e "${GREEN}FastAPI stopped${NC}" || echo -e "${RED}FastAPI not running${NC}"
        rm -f "$LOG_DIR/fastapi.pid"
    fi
    if [ -f "$LOG_DIR/hatchet.pid" ]; then
        kill $(cat "$LOG_DIR/hatchet.pid") 2>/dev/null && echo -e "${GREEN}Hatchet stopped${NC}" || echo -e "${RED}Hatchet not running${NC}"
        rm -f "$LOG_DIR/hatchet.pid"
    fi
    exit 0
}

# Handle stop command
if [ "$1" = "stop" ]; then
    stop_services
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  GTJ Scraper Production Startup${NC}"
echo -e "${GREEN}========================================${NC}"

# Start FastAPI server
echo -e "\n${YELLOW}Starting FastAPI server...${NC}"
nohup uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4 >> "$FASTAPI_LOG" 2>&1 &
FASTAPI_PID=$!
ln -sf "$FASTAPI_LOG" "$FASTAPI_LATEST"
echo -e "${GREEN}FastAPI server started (PID: $FASTAPI_PID)${NC}"
echo -e "Log: $FASTAPI_LOG"

# Save PIDs to file for later management
echo "$FASTAPI_PID" > "$LOG_DIR/fastapi.pid"

# Wait a moment for FastAPI to initialize
sleep 2

# Start Hatchet worker
echo -e "\n${YELLOW}Starting Hatchet worker...${NC}"
nohup python -m src.workers.batch_verify_worker >> "$HATCHET_LOG" 2>&1 &
HATCHET_PID=$!
ln -sf "$HATCHET_LOG" "$HATCHET_LATEST"
echo -e "${GREEN}Hatchet worker started (PID: $HATCHET_PID)${NC}"
echo -e "Log: $HATCHET_LOG"

# Save PIDs to file for later management
echo "$HATCHET_PID" > "$LOG_DIR/hatchet.pid"

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  All services running${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Server:   process.trustjet.ai"
echo -e "FastAPI:  http://process.trustjet.ai:8000"
echo -e "API Docs: http://process.trustjet.ai:8000/docs"
echo -e "\n${YELLOW}Log files:${NC}"
echo -e "  FastAPI: tail -f $FASTAPI_LATEST"
echo -e "  Hatchet: tail -f $HATCHET_LATEST"
echo -e "\n${YELLOW}PID files:${NC}"
echo -e "  FastAPI: $LOG_DIR/fastapi.pid"
echo -e "  Hatchet: $LOG_DIR/hatchet.pid"
echo -e "\n${GREEN}Services will keep running after you close the terminal.${NC}"
echo -e "To stop services: kill \$(cat $LOG_DIR/fastapi.pid) \$(cat $LOG_DIR/hatchet.pid)"
