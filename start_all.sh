#!/bin/bash
# ─────────────────────────────────────────────────────────────
# start_all.sh
# Real-Time Application Performance Monitoring Dashboard
# PG Final Year Major Project
#
# Starts all services in correct order:
#   1. Flask Application       → port 5000
#   2. Prometheus              → port 9090
#   3. Alertmanager            → port 9093
#
# Usage:
#   chmod +x start_all.sh   (run once to make executable)
#   ./start_all.sh
# ─────────────────────────────────────────────────────────────

# Text colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Project root — folder where this script lives
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

PROMETHEUS_DIR="$PROJECT_DIR/prometheus/prometheus-2.52.0.linux-amd64"
ALERTMANAGER_DIR="$PROJECT_DIR/alertmanager"
APP_FILE="$PROJECT_DIR/app.py"

# Log files — so you can check output if needed
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     DevOps Monitoring Dashboard — Startup Script         ║${NC}"
echo -e "${CYAN}║     PG Final Year Major Project                          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────
# Check: make sure required files exist
# ─────────────────────────────────────────────

echo -e "${BLUE}[CHECK]${NC} Verifying project files..."

if [ ! -f "$APP_FILE" ]; then
    echo -e "${RED}[ERROR]${NC} app.py not found at: $APP_FILE"
    exit 1
fi

if [ ! -f "$PROMETHEUS_DIR/prometheus" ]; then
    echo -e "${RED}[ERROR]${NC} Prometheus binary not found at: $PROMETHEUS_DIR/prometheus"
    exit 1
fi

if [ ! -f "$ALERTMANAGER_DIR/alertmanager" ]; then
    echo -e "${RED}[ERROR]${NC} Alertmanager binary not found at: $ALERTMANAGER_DIR/alertmanager"
    exit 1
fi

echo -e "${GREEN}[OK]${NC} All required files found."
echo ""

# ─────────────────────────────────────────────
# Kill any existing processes on our ports
# ─────────────────────────────────────────────

echo -e "${YELLOW}[CLEAN]${NC} Stopping any existing services on ports 5000, 9090, 9093..."

fuser -k 5000/tcp 2>/dev/null && echo -e "  → Stopped process on port 5000"
fuser -k 9090/tcp 2>/dev/null && echo -e "  → Stopped process on port 9090"
fuser -k 9093/tcp 2>/dev/null && echo -e "  → Stopped process on port 9093"

sleep 1
echo ""

# ─────────────────────────────────────────────
# Start Prometheus
# ─────────────────────────────────────────────

echo -e "${BLUE}[1/3]${NC} Starting Prometheus on port 9090..."

cd "$PROMETHEUS_DIR"
nohup ./prometheus --config.file=prometheus.yml \
    > "$LOG_DIR/prometheus.log" 2>&1 &

PROMETHEUS_PID=$!
echo $PROMETHEUS_PID > "$LOG_DIR/prometheus.pid"

sleep 2

# Verify Prometheus started
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Prometheus running — PID: $PROMETHEUS_PID"
else
    echo -e "${RED}[WARN]${NC} Prometheus may still be starting — check logs/prometheus.log"
fi

# ─────────────────────────────────────────────
# Start Alertmanager
# ─────────────────────────────────────────────

echo ""
echo -e "${BLUE}[2/3]${NC} Starting Alertmanager on port 9093..."

cd "$ALERTMANAGER_DIR"
nohup ./alertmanager --config.file=alertmanager.yml \
    > "$LOG_DIR/alertmanager.log" 2>&1 &

ALERTMANAGER_PID=$!
echo $ALERTMANAGER_PID > "$LOG_DIR/alertmanager.pid"

sleep 2

# Verify Alertmanager started
if curl -s http://localhost:9093/-/healthy > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Alertmanager running — PID: $ALERTMANAGER_PID"
else
    echo -e "${RED}[WARN]${NC} Alertmanager may still be starting — check logs/alertmanager.log"
fi

# ─────────────────────────────────────────────
# Start Flask Application
# ─────────────────────────────────────────────

echo ""
echo -e "${BLUE}[3/3]${NC} Starting Flask Application on port 5000..."

cd "$PROJECT_DIR"
nohup python3 app.py \
    > "$LOG_DIR/flask.log" 2>&1 &

FLASK_PID=$!
echo $FLASK_PID > "$LOG_DIR/flask.pid"

sleep 3

# Verify Flask started
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Flask app running — PID: $FLASK_PID"
else
    echo -e "${RED}[WARN]${NC} Flask may still be starting — check logs/flask.log"
fi

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                  All Services Started                    ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  Flask App      →  ${GREEN}http://localhost:5000${NC}              ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Prometheus     →  ${GREEN}http://localhost:9090${NC}              ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Alertmanager   →  ${GREEN}http://localhost:9093${NC}              ${CYAN}║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  Logs saved to: $LOG_DIR          ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Run ./stop_all.sh to stop everything                ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Tip:${NC} Open http://localhost:5000 in your Windows browser"
echo ""
