#!/bin/bash
# ─────────────────────────────────────────────────────────────
# stop_all.sh
# Stops all DevOps Monitoring services cleanly
# ─────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

echo ""
echo -e "${CYAN}[STOP]${NC} Stopping all DevOps Monitoring services..."
echo ""

# Stop using saved PIDs
for service in flask flask2 prometheus alertmanager; do
    PID_FILE="$LOG_DIR/$service.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo -e "${GREEN}[OK]${NC} Stopped $service (PID: $PID)"
        else
            echo -e "  → $service was already stopped"
        fi
        rm -f "$PID_FILE"
    fi
done

# Stop Nginx
sudo nginx -s stop 2>/dev/null && echo -e "${GREEN}[OK]${NC} Stopped Nginx load balancer"

# Kill by port as backup
fuser -k 5000/tcp 2>/dev/null
fuser -k 5002/tcp 2>/dev/null
fuser -k 9090/tcp 2>/dev/null
fuser -k 9093/tcp 2>/dev/null
fuser -k 8080/tcp 2>/dev/null

echo ""
echo -e "${GREEN}All services stopped.${NC}"
echo ""
