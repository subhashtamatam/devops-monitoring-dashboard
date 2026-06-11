# Real-Time Application Performance Monitoring Dashboard Using DevOps Tools

**PG Final Year Major Project — Osmania University**

A complete real-time application monitoring system built using industry-standard DevOps tools — Flask, Prometheus, Grafana, and Alertmanager — enhanced with intelligent root cause analysis, predictive alerting, automated failover via Nginx load balancing, live infrastructure health checks, and a fully automated CI/CD pipeline.

---

## Project Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User / Browser                        │
└──────────────────────┬──────────────────────────────────┘
                        │
               ┌────────▼────────┐
               │  Nginx :8080    │  ← Load Balancer (least_conn)
               │  Load Balancer  │     weight 3 (primary) : 1 (backup)
               └────┬───────┬────┘
                    │       │
         ┌──────────▼─┐  ┌──▼──────────┐
         │ Flask :5000 │  │ Flask :5002  │
         │  Primary    │  │   Backup     │
         └──────┬──────┘  └─────┬────────┘
                │               │
         ┌──────▼───────────────▼──────┐
         │     Prometheus :9090         │  ← Scrapes both servers every 2s
         └──────┬───────────────────────┘
                │
         ┌──────▼──────┐    ┌─────────────────┐
         │  Grafana     │    │  Alertmanager   │
         │  :3000       │    │  :9093          │
         │  5 Dashboards│    │  Email Alerts   │
         └──────────────┘    └────────┬────────┘
                │                      │
         ┌──────▼──────────────────────▼──────┐
         │  Root Cause Analyzer (analyzer.py)  │  ← Weighted scoring
         │  Predictive Alert System (predictor.py) │ ← Linear regression
         │  Alertmanager Poller                │  ← Auto-pulls firing alerts
         └──────────────────────────────────────┘
```

---

## Features

### Core Monitoring
- Real-time metric collection every 2 seconds using Prometheus
- 5 interactive Grafana dashboards (dark theme, auto-refresh)
- Application metrics — request rate, latency, error rate
- System metrics — CPU usage, memory consumption
- Both primary and backup Flask servers scraped and monitored

### Intelligent Root Cause Analysis
- Correlates 5 live Prometheus metrics simultaneously
- Weighted scoring algorithm identifies the dominant cause
- Baselines empirically calibrated to actual idle Flask server values
- Causes detected: Traffic Spike, CPU Saturation, Memory Pressure, Latency Anomaly, Error Surge
- Confidence percentage capped at 95%

### Predictive Alert System
- Background thread collects metric history every 10 seconds
- Pure Python linear regression — no external ML libraries
- Forecasts values 2 and 5 minutes ahead
- Sends a Yahoo email alert **before** a threshold is breached
- 5-minute cooldown per metric to avoid alert spam

### Alerting
- 5 Prometheus alert rules — AppDown, HighCPUUsage, HighResponseLatency, HighErrorRate, TrafficSpike
- Alertmanager routes alerts to Yahoo SMTP with a custom HTML email template (red FIRING / green RESOLVED)
- Background poller automatically pulls currently-firing Alertmanager alerts into the Alert History page every 30 seconds
- Alert History page with 4 manual trigger buttons (Error Storm, Traffic Spike, Slow Requests, Test Email)
- POST-Redirect-GET pattern — refreshing the page after a trigger never causes a 405 error

### Infrastructure & Visualization
- `/infrastructure` — live health check of all 6 services with response times and an animated architecture diagram
- `/grafana` — all 5 dashboards embedded directly via tabbed iframes (kiosk mode, dark theme)
- Live "Health Score" card on the home page (0–100, polled every 3 seconds)
- Full dark mode across every page, persisted via localStorage

### High Availability
- Nginx load balancer on port 8080, `least_conn` algorithm
- Primary Flask server (port 5000) — weight 3 (~75% of traffic)
- Backup Flask server (port 5002) — weight 1 (~25% of traffic)
- Automatic failover — if the primary goes down, the backup takes over within milliseconds
- Both servers scraped by Prometheus and visible on the Load Balancer dashboard

### Secure Credential Management
- `python-dotenv` loads Yahoo SMTP credentials from a local `.env` file
- `.env` is excluded from GitHub via `.gitignore`
- `.env.example` committed as a safe template
- Follows the 12-Factor App principle of separating configuration from code

### CI/CD Pipeline
- GitHub Actions workflow runs automatically on every push to `main`
- Installs all dependencies (including `python-dotenv`) and runs 6 automated pytest tests
- Pass/fail status visible directly on GitHub

---

## Tech Stack

| Tool           | Purpose             | Port       |
| -------------- | ------------------- | ---------- |
| Flask (Python) | Application server   | 5000, 5002 |
| Prometheus     | Metrics collection   | 9090       |
| Grafana        | Visualization        | 3000       |
| Alertmanager   | Alert routing        | 9093       |
| Nginx          | Load balancer        | 8080       |
| GitHub Actions | CI/CD pipeline       | —          |

---

## Project Structure

```
devops-monitoring-project/
│
├── app.py                  # Primary Flask application (6 pages + API)
├── app2.py                 # Backup Flask application
├── analyzer.py             # Root Cause Analyzer
├── predictor.py            # Predictive Alert System
├── mailer.py                # Yahoo email alert sender (python-dotenv)
├── stress_test.py           # 7 stress-test scenarios
├── background_load.py       # Gentle background traffic for demos
├── nginx.conf               # Nginx load balancer config (least_conn, 3:1)
├── start_all.sh              # Start all 5 services
├── stop_all.sh               # Stop all services cleanly
│
├── prometheus/
│   ├── prometheus.yml        # Scrapes flask-app (5000) + flask-backup (5002)
│   └── prometheus-2.52.0.linux-amd64/   # (gitignored binary release)
│
├── alertmanager/             # (gitignored binary release)
├── alertmanager.yml          # Alertmanager + Yahoo SMTP config
│
├── tests/
│   └── test_app.py           # 6 automated pytest tests
│
├── logs/                      # Service logs (gitignored, auto-created)
│
├── .env.example               # Safe credential template (committed)
├── .gitignore
│
└── .github/
    └── workflows/
        └── ci.yml              # GitHub Actions CI pipeline
```

---

## Setup and Run

### Prerequisites
- Ubuntu (WSL on Windows or native Linux)
- Python 3.11+
- Nginx installed
- Prometheus 2.52.0
- Alertmanager 0.27.0

### Install Python dependencies
```bash
pip3 install flask prometheus-client requests python-dotenv --break-system-packages
```

### Configure credentials
```bash
cp .env.example .env
nano .env   # add your Yahoo email and app password
```

### Start all services
```bash
cd ~/devops-monitoring-project
chmod +x start_all.sh stop_all.sh
./start_all.sh
```

### Open in browser

| Service       | URL                       |
| -------------- | ------------------------- |
| Flask Dashboard | http://localhost:5000     |
| Backup Server   | http://localhost:5002     |
| Load Balancer   | http://localhost:8080     |
| Grafana         | http://localhost:3000     |
| Prometheus      | http://localhost:9090     |
| Alertmanager    | http://localhost:9093     |

### Stop all services
```bash
./stop_all.sh
```

---

## Dashboard Pages

| Route             | Description                                              |
| ------------------ | --------------------------------------------------------- |
| `/`                 | Home — live status cards, request/error counts, Health Score |
| `/analyze`          | Root Cause Analyzer — dominant cause, confidence, score bars |
| `/predict`          | Predictive Alerts — 2-minute and 5-minute forecasts        |
| `/alerts`           | Alert History — Alertmanager + predictive + manual alerts  |
| `/infrastructure`   | Live health check of all 6 services + architecture diagram |
| `/grafana`          | All 5 Grafana dashboards embedded via tabs                 |

---

## Stress Testing

```bash
# Show menu
python3 stress_test.py

# Normal load — 5 req/sec for 30 seconds
python3 stress_test.py 1

# Traffic spike — 300 concurrent requests
python3 stress_test.py 2

# Error storm — 60 errors to trigger HighErrorRate alert
python3 stress_test.py 3

# CPU stress — heavy prime-sieve computation
python3 stress_test.py 4

# Memory stress — large allocations
python3 stress_test.py 5

# Latency stress — slow 2-3.5s responses
python3 stress_test.py 6

# Full viva demo — all scenarios in sequence
python3 stress_test.py 7
```

---

## Grafana Dashboards

| # | Dashboard               | What it shows                              |
| --- | ------------------------ | -------------------------------------------- |
| 1 | Application Performance  | Requests/sec, total requests, CPU trend       |
| 2 | Performance Dashboard    | Latency heatmap, 95th percentile, gauge       |
| 3 | Traffic Analysis         | Real-time traffic, 1m vs 5m comparison        |
| 4 | Load Balancer            | Primary vs backup traffic, server health      |
| 5 | System Resources         | CPU, memory, latency for both servers         |

---

## Alert Rules

| Alert                | Condition                    | Severity |
| --------------------- | ------------------------------ | -------- |
| AppDown               | App unreachable for 15s         | Critical |
| HighCPUUsage           | CPU > 70% for 30s                | Warning  |
| HighResponseLatency    | Latency > 500ms for 30s          | Warning  |
| HighErrorRate          | Errors > 0.05/sec for 20s         | Critical |
| TrafficSpike           | Requests > 0.5/sec for 20s        | Warning  |

---

## CI/CD Pipeline

Every `git push` to `main` automatically:

1. Sets up Python 3.11
2. Installs all dependencies (flask, prometheus-client, requests, pytest, python-dotenv)
3. Runs 6 automated tests
4. Reports pass/fail status

View pipeline runs: [Actions tab](https://github.com/subhashtamatam/devops-monitoring-dashboard/actions)

---

## What Makes This Project Unique

| Feature              | Standard Monitoring | This Project |
| --------------------- | -------------------- | -------------- |
| Metric Collection      | ✅                    | ✅              |
| Visualization          | ✅                    | ✅              |
| Alerting                | ✅                    | ✅              |
| Root Cause Analysis     | ❌                    | ✅              |
| Predictive Alerts       | ❌                    | ✅              |
| Auto Alert Aggregation  | ❌                    | ✅              |
| CI/CD Integration       | ❌                    | ✅              |
| Load Balancing          | ❌                    | ✅              |
| Automatic Failover      | ❌                    | ✅              |
| Live Infrastructure View | ❌                  | ✅              |
| Secure Credential Mgmt  | ❌                    | ✅              |
