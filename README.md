# Real-Time Application Performance Monitoring Dashboard Using DevOps Tools

**PG Final Year Major Project**

A complete real-time application monitoring system built using industry-standard DevOps tools — Flask, Prometheus, Grafana, and Alertmanager — enhanced with intelligent root cause analysis, predictive alerting, and automated failover using Nginx load balancing.

---

## Project Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User / Browser                        │
└──────────────────────┬──────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │  Nginx :8080    │  ← Load Balancer
              │  Load Balancer  │
              └────┬───────┬────┘
                   │       │
        ┌──────────▼─┐  ┌──▼──────────┐
        │ Flask :5000 │  │ Flask :5002  │
        │  Primary    │  │   Backup    │
        └──────┬──────┘  └─────┬───────┘
               │               │
        ┌──────▼───────────────▼──────┐
        │     Prometheus :9090         │  ← Scrapes every 2s
        └──────┬───────────────────────┘
               │
        ┌──────▼──────┐    ┌─────────────────┐
        │  Grafana     │    │  Alertmanager   │
        │  :3000       │    │  :9093          │
        │  Dashboards  │    │  Email Alerts   │
        └─────────────┘    └─────────────────┘
               │
        ┌──────▼──────────────────────┐
        │  Root Cause Analyzer        │  ← Custom Python
        │  Predictive Alert System    │  ← Linear Regression
        └─────────────────────────────┘
```

---

## Features

### Core Monitoring
- Real-time metric collection every 2 seconds using Prometheus
- 5 interactive Grafana dashboards
- Application metrics — request rate, latency, error rate
- System metrics — CPU usage, memory consumption

### Intelligent Analysis (Phase 4A)
- Root Cause Analyzer correlates 5 metrics simultaneously
- Weighted scoring algorithm identifies dominant cause
- Human-readable explanations for every performance change
- Causes detected: Traffic Spike, CPU Saturation, Memory Pressure, Latency Anomaly, Error Surge

### Predictive Alert System (Phase 4B)
- Collects metric history every 10 seconds
- Pure Python linear regression predicts values 2 and 5 minutes ahead
- Sends Yahoo email alert **before** threshold is breached
- Alertmanager fires **after** breach — this system fires **before**

### Alerting (Phase 5)
- 5 Prometheus alert rules — AppDown, HighCPU, HighLatency, HighErrorRate, TrafficSpike
- Alertmanager routes alerts to Yahoo email
- Alert History page with trigger test buttons
- Toast notifications — no page redirect on trigger

### CI/CD Pipeline (Phase 6)
- GitHub Actions workflow runs on every push
- Installs dependencies, runs 6 automated tests
- Pass/fail status visible on GitHub

### High Availability (Phase 7)
- Nginx load balancer on port 8080
- Primary Flask server on port 5000
- Backup Flask server on port 5002
- Automatic failover — if primary goes down, backup takes over instantly
- Both servers monitored in Grafana simultaneously

---

## Tech Stack

| Tool | Purpose | Port |
|---|---|---|
| Flask (Python) | Application server | 5000, 5002 |
| Prometheus | Metrics collection | 9090 |
| Grafana | Visualization | 3000 |
| Alertmanager | Alert routing | 9093 |
| Nginx | Load balancer | 8080 |
| GitHub Actions | CI/CD pipeline | — |

---

## Project Structure

```
devops-monitoring-project/
│
├── app.py                  # Primary Flask application
├── app2.py                 # Backup Flask application
├── analyzer.py             # Root Cause Analyzer
├── predictor.py            # Predictive Alert System
├── mailer.py               # Yahoo email alert sender
├── stress_test.py          # Stress testing scenarios
├── nginx.conf              # Nginx load balancer config
├── start_all.sh            # Start all services
├── stop_all.sh             # Stop all services
│
├── prometheus/
│   └── prometheus-2.52.0.linux-amd64/
│       ├── prometheus.yml  # Prometheus config
│       └── alert.rules.yml # Alert rules (5 rules)
│
├── alertmanager/
│   └── alertmanager.yml    # Alertmanager + Yahoo SMTP
│
├── tests/
│   └── test_app.py         # Automated test suite
│
├── logs/                   # Service logs (auto-created)
│
└── .github/
    └── workflows/
        └── ci.yml          # GitHub Actions pipeline
```

---

## Setup and Run

### Prerequisites
- Ubuntu (WSL on Windows or native Linux)
- Python 3.x
- Nginx installed
- Prometheus 2.52.0 downloaded
- Alertmanager 0.27.0 downloaded

### Install Python dependencies
```bash
pip3 install flask prometheus-client requests
```

### Start all services
```bash
cd ~/devops-monitoring-project
chmod +x start_all.sh stop_all.sh
./start_all.sh
```

### Open in browser
| Service | URL |
|---|---|
| Flask App | http://localhost:5000 |
| Backup Server | http://localhost:5002 |
| Load Balancer | http://localhost:8080 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |

### Stop all services
```bash
./stop_all.sh
```

---

## Stress Testing

```bash
# Show menu
python3 stress_test.py

# Normal load — 5 req/sec for 30 seconds
python3 stress_test.py 1

# Traffic spike — 300 concurrent requests
python3 stress_test.py 2

# Error storm — 60 errors to trigger alert
python3 stress_test.py 3

# Full demo — all 3 scenarios in sequence
python3 stress_test.py 4
```

---

## Grafana Dashboards

| # | Dashboard | What it shows |
|---|---|---|
| 1 | Application Performance | Requests/sec, Total requests, CPU trend |
| 2 | Performance Dashboard | Latency heatmap, 95th percentile, gauge |
| 3 | Traffic Analysis | Real-time traffic, 1m vs 5m comparison |
| 4 | Load Balancer | Primary vs Backup traffic, server health |
| 5 | System Resources | CPU, Memory, Latency for both servers |

---

## Alert Rules

| Alert | Condition | Severity |
|---|---|---|
| AppDown | App unreachable for 15s | Critical |
| HighCPUUsage | CPU > 70% for 30s | Warning |
| HighResponseLatency | Latency > 500ms for 30s | Warning |
| HighErrorRate | Errors > 0.05/sec for 20s | Critical |
| TrafficSpike | Requests > 0.5/sec for 20s | Warning |

---

## CI/CD Pipeline

Every `git push` to `main` branch automatically:
1. Sets up Python 3.11 environment
2. Installs all dependencies
3. Runs 6 automated tests
4. Reports pass/fail status

View pipeline: https://github.com/subhashtamatam/devops-monitoring-dashboard/actions

---

## What Makes This Project Unique

| Feature | Standard Monitoring | This Project |
|---|---|---|
| Metric Collection | ✅ | ✅ |
| Visualization | ✅ | ✅ |
| Alerting | ✅ | ✅ |
| Root Cause Analysis | ❌ | ✅ |
| Predictive Alerts | ❌ | ✅ |
| CI/CD Integration | ❌ | ✅ |
| Load Balancing | ❌ | ✅ |
| Automatic Failover | ❌ | ✅ |
