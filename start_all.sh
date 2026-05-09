#!/bin/bash
# ─────────────────────────────────────────────────────────────
# start_all.sh
# Real-Time Application Performance Monitoring Dashboard
# PG Final Year Major Project
#
# Starts all services in correct order:
#   1. Flask Primary App      → port 5000
#   2. Flask Backup App       → port 5002
#   3. Prometheus             → port 9090
#   4. Alertmanager           → port 9093
#   5. Nginx Load Balancer    → port 8080
# ─────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMETHEUS_DIR="$PROJECT_DIR/prometheus/prometheus-2.52.0.linux-amd64"
ALERTMANAGER_DIR="$PROJECT_DIR/alertmanager"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     DevOps Monitoring Dashboard — Startup Script         ║${NC}"
echo -e "${CYAN}║     PG Final Year Major Project                          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────
# Verify required files
# ─────────────────────────────────────────────

echo -e "${BLUE}[CHECK]${NC} Verifying project files..."

MISSING=0
[ ! -f "$PROJECT_DIR/app.py" ]                          && echo -e "${RED}[MISSING]${NC} app.py"           && MISSING=1
[ ! -f "$PROJECT_DIR/app2.py" ]                         && echo -e "${RED}[MISSING]${NC} app2.py"          && MISSING=1
[ ! -f "$PROJECT_DIR/nginx.conf" ]                      && echo -e "${RED}[MISSING]${NC} nginx.conf"       && MISSING=1
[ ! -f "$PROMETHEUS_DIR/prometheus" ]                   && echo -e "${RED}[MISSING]${NC} prometheus"       && MISSING=1
[ ! -f "$ALERTMANAGER_DIR/alertmanager" ]               && echo -e "${RED}[MISSING]${NC} alertmanager"     && MISSING=1

if [ $MISSING -eq 1 ]; then
    echo -e "${RED}[ERROR]${NC} Missing files. Please check your project folder."
    exit 1
fi

echo -e "${GREEN}[OK]${NC} All required files found."
echo ""

# ─────────────────────────────────────────────
# Kill existing processes on our ports
# ─────────────────────────────────────────────

echo -e "${YELLOW}[CLEAN]${NC} Stopping any existing services..."
fuser -k 5000/tcp 2>/dev/null && echo -e "  → Cleared port 5000"
fuser -k 5002/tcp 2>/dev/null && echo -e "  → Cleared port 5002"
fuser -k 9090/tcp 2>/dev/null && echo -e "  → Cleared port 9090"
fuser -k 9093/tcp 2>/dev/null && echo -e "  → Cleared port 9093"
fuser -k 8080/tcp 2>/dev/null && echo -e "  → Cleared port 8080"
sleep 1
echo ""

# ─────────────────────────────────────────────
# 1. Start Prometheus
# ─────────────────────────────────────────────

echo -e "${BLUE}[1/5]${NC} Starting Prometheus on port 9090..."
cd "$PROMETHEUS_DIR"
nohup ./prometheus --config.file=prometheus.yml > "$LOG_DIR/prometheus.log" 2>&1 &
echo $! > "$LOG_DIR/prometheus.pid"
sleep 2
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Prometheus running"
else
    echo -e "${YELLOW}[WAIT]${NC} Prometheus still starting — check logs/prometheus.log"
fi

# ─────────────────────────────────────────────
# 2. Start Alertmanager
# ─────────────────────────────────────────────

echo ""
echo -e "${BLUE}[2/5]${NC} Starting Alertmanager on port 9093..."
cd "$ALERTMANAGER_DIR"
nohup ./alertmanager --config.file=alertmanager.yml > "$LOG_DIR/alertmanager.log" 2>&1 &
echo $! > "$LOG_DIR/alertmanager.pid"
sleep 2
if curl -s http://localhost:9093/-/healthy > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Alertmanager running"
else
    echo -e "${YELLOW}[WAIT]${NC} Alertmanager still starting — check logs/alertmanager.log"
fi

# ─────────────────────────────────────────────
# 3. Start Primary Flask App
# ─────────────────────────────────────────────

echo ""
echo -e "${BLUE}[3/5]${NC} Starting Primary Flask App on port 5000..."
cd "$PROJECT_DIR"
nohup python3 app.py > "$LOG_DIR/flask.log" 2>&1 &
echo $! > "$LOG_DIR/flask.pid"
sleep 3
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Primary Flask app running"
else
    echo -e "${YELLOW}[WAIT]${NC} Flask still starting — check logs/flask.log"
fi

# ─────────────────────────────────────────────
# 4. Start Backup Flask App
# ─────────────────────────────────────────────

echo ""
echo -e "${BLUE}[4/5]${NC} Starting Backup Flask App on port 5002..."
cd "$PROJECT_DIR"
nohup python3 app2.py > "$LOG_DIR/flask2.log" 2>&1 &
echo $! > "$LOG_DIR/flask2.pid"
sleep 3
if curl -s http://localhost:5002/health > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Backup Flask app running"
else
    echo -e "${YELLOW}[WAIT]${NC} Backup Flask still starting — check logs/flask2.log"
fi

# ─────────────────────────────────────────────
# 5. Start Nginx Load Balancer
# ─────────────────────────────────────────────

echo ""
echo -e "${BLUE}[5/5]${NC} Starting Nginx Load Balancer on port 8080..."
sudo nginx -c "$PROJECT_DIR/nginx.conf" -t 2>/dev/null
if [ $? -eq 0 ]; then
    sudo nginx -c "$PROJECT_DIR/nginx.conf"
    sleep 1
    if curl -s http://localhost:8080/nginx-health > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} Nginx load balancer running"
    else
        echo -e "${YELLOW}[WARN]${NC} Nginx may still be starting"
    fi
else
    echo -e "${RED}[ERROR]${NC} Nginx config has errors — check nginx.conf"
fi

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                  All Services Started                    ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  Primary App     →  ${GREEN}http://localhost:5000${NC}              ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Backup App      →  ${GREEN}http://localhost:5002${NC}              ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Load Balancer   →  ${GREEN}http://localhost:8080${NC}              ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Prometheus      →  ${GREEN}http://localhost:9090${NC}              ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Alertmanager    →  ${GREEN}http://localhost:9093${NC}              ${CYAN}║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  Logs: ~/devops-monitoring-project/logs/              ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Stop: ./stop_all.sh                                  ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}DEMO TIP:${NC}"
echo -e "  1. Open http://localhost:8080 — traffic goes to primary (port 5000)"
echo -e "  2. Stop primary: ${RED}fuser -k 5000/tcp${NC}"
echo -e "  3. Refresh http://localhost:8080 — now shows BACKUP SERVER"
echo -e "  4. Restart primary: ${GREEN}python3 app.py &${NC}"
echo ""
