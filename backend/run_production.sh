#!/bin/bash

# Production startup script for GTJ Scraper
# Runs FastAPI server and Hatchet worker

set -e

#   Usage:

#   # Start services
#   ./run_production.sh

#   # Stop services
#   ./run_production.sh stop

#   # Cancel a specific Hatchet workflow
#   ./run_production.sh cancel <workflow_run_id>

#   # Cancel all workflows from a file (one ID per line)
#   ./run_production.sh cancel-all workflows.txt

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

# Production API URL
API_URL="http://process.trustjet.ai"

# Function to cancel a single workflow
cancel_workflow() {
    local workflow_id=$1
    echo -e "${YELLOW}Cancelling workflow: $workflow_id${NC}"
    response=$(curl -s -X POST "$API_URL/scoring/batch-verify-cancel/$workflow_id")
    if echo "$response" | grep -q "success\|cancelled"; then
        echo -e "${GREEN}✓ Cancelled: $workflow_id${NC}"
    else
        echo -e "${RED}✗ Failed to cancel: $workflow_id${NC}"
        echo "  Response: $response"
    fi
}

# Function to cancel all workflows from a file
cancel_all_workflows() {
    local file=$1
    if [ ! -f "$file" ]; then
        echo -e "${RED}Error: File '$file' not found${NC}"
        exit 1
    fi
    echo -e "${YELLOW}Cancelling all workflows from: $file${NC}"
    while IFS= read -r workflow_id || [ -n "$workflow_id" ]; do
        # Skip empty lines and comments
        if [ -n "$workflow_id" ] && [[ ! "$workflow_id" =~ ^# ]]; then
            cancel_workflow "$workflow_id"
        fi
    done < "$file"
    echo -e "${GREEN}Done cancelling workflows${NC}"
    exit 0
}

# Handle commands
if [ "$1" = "stop" ]; then
    stop_services
fi

if [ "$1" = "cancel" ]; then
    if [ -z "$2" ]; then
        echo -e "${RED}Error: Please provide a workflow run ID${NC}"
        echo "Usage: ./run_production.sh cancel <workflow_run_id>"
        exit 1
    fi
    cancel_workflow "$2"
    exit 0
fi

if [ "$1" = "cancel-all" ]; then
    if [ -z "$2" ]; then
        echo -e "${RED}Error: Please provide a file with workflow IDs${NC}"
        echo "Usage: ./run_production.sh cancel-all workflows.txt"
        exit 1
    fi
    cancel_all_workflows "$2"
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  GTJ Scraper Production Startup${NC}"
echo -e "${GREEN}========================================${NC}"

# Clear any previous instance before binding the port.
#
# This script starts uvicorn unconditionally, and `stop` only kills the PIDs it
# recorded in logs/*.pid — so a process started by an earlier deploy, or by hand,
# survives every restart. When that happens uvicorn dies with
# "[Errno 98] Address already in use" while the worker starts anyway, leaving a
# live worker and no API. A stale worker is the more dangerous half: it stays
# registered with Hatchet and will happily claim jobs using months-old code.
#
# pkill matches on the command line, so it catches those orphans regardless of
# which deploy started them.
#
# SIGTERM IS NOT ENOUGH ON ITS OWN. Observed 2026-11-20: a uvicorn started on
# Nov 17 was listening with 12 connections queued on the socket but answering
# none of them, and it survived this pkill — only `kill -9` freed port 8000.
# A wedged worker pool does not necessarily act on SIGTERM, so the restart
# appeared to succeed while the old process kept serving pre-fix code.
#
# The pattern is widened slightly (".*" rather than a literal space) to be
# robust to argv spacing, but the substantive fix is the SIGKILL escalation
# and the port check below.
echo -e "\n${YELLOW}Stopping any existing instances...${NC}"
pkill -f "uvicorn.*src\.main" 2>/dev/null && echo -e "${GREEN}Stopped stale FastAPI${NC}" || true
pkill -f "batch_verify_worker" 2>/dev/null && echo -e "${GREEN}Stopped stale Hatchet worker${NC}" || true
sleep 3

# Escalate if anything is still holding the port, then verify it is free.
# Starting uvicorn into an occupied port is the failure this guards.
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ':8000 '; then
    echo -e "${YELLOW}Port 8000 still held — escalating to SIGKILL${NC}"
    pkill -9 -f "uvicorn.*src\.main" 2>/dev/null || true
    sleep 3
fi
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ':8000 '; then
    echo -e "${RED}ERROR: port 8000 is still in use. Not starting a second API.${NC}"
    ss -ltnp 2>/dev/null | grep ':8000 '
    echo -e "${YELLOW}Kill the listed PID by hand, then re-run.${NC}"
    exit 1
fi

# Start FastAPI server
echo -e "\n${YELLOW}Starting FastAPI server...${NC}"
nohup uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4 >> "$FASTAPI_LOG" 2>&1 &
FASTAPI_PID=$!
ln -sf "$FASTAPI_LOG" "$FASTAPI_LATEST"
echo -e "${GREEN}FastAPI server started (PID: $FASTAPI_PID)${NC}"
echo -e "Log: $FASTAPI_LOG"

# Verify it actually SERVES before reporting success.
#
# nohup + & reports a PID whether or not the app survives import, so a startup
# traceback previously produced "All services running" and no API. Worse, a
# process can be alive and listening yet never answer — observed 2026-11-20
# with 12 connections queued on an accepting socket. Only a real response
# proves the API is up.
echo -e "\n${YELLOW}Waiting for the API to respond...${NC}"
API_READY=0
for _ in $(seq 1 30); do
    sleep 2
    if ! kill -0 "$FASTAPI_PID" 2>/dev/null; then
        echo -e "${RED}ERROR: FastAPI exited during startup.${NC}"
        echo -e "${YELLOW}Last 30 log lines:${NC}"
        tail -30 "$FASTAPI_LOG"
        exit 1
    fi
    code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' \
           http://127.0.0.1:8000/docs 2>/dev/null || echo 000)
    if [ "$code" = "200" ]; then
        API_READY=1
        echo -e "${GREEN}API responding (HTTP 200)${NC}"
        break
    fi
done
if [ "$API_READY" != "1" ]; then
    echo -e "${RED}ERROR: API did not respond within 60s.${NC}"
    echo -e "${YELLOW}Last 30 log lines:${NC}"
    tail -30 "$FASTAPI_LOG"
    exit 1
fi

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
