from flask import Flask, render_template_string, request
from prometheus_client import Counter, Histogram, Summary, generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime
import time
import random
import threading
 
app = Flask(__name__)
 
REQUEST_COUNT = Counter(
    'app_requests_total',
    'Total requests',
    ['endpoint']
)
 
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'Request latency',
    ['method', 'endpoint']
)
 
REQUEST_TIME = Summary(
    'request_processing_seconds',
    'Time spent processing request'
)

ERROR_COUNT = Counter(
    'app_errors_total',
    'Total number of errors',
    ['endpoint']
)

# Pre-register label combinations so Prometheus reports 0 instead of
# "no data" before the first real hit on each endpoint.
REQUEST_COUNT.labels(endpoint='/').inc(0)
REQUEST_COUNT.labels(endpoint='/health').inc(0)
 
request_value = 0
START_TIME    = time.time()
 
 
def get_uptime():
    secs = int(time.time() - START_TIME)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


# ── Backup workload simulation ──

_active_requests = 0
_active_requests_lock = threading.Lock()


def simulate_backup_workload():
    global _active_requests
    with _active_requests_lock:
        _active_requests += 1
        current_load = _active_requests
    try:
        # Natural per-request baseline with jitter (gaussian, not uniform --
        # real-world response times cluster around a mean with occasional
        # outliers, they don't move in a flat random range).
        base_duration = max(0.05, random.gauss(0.095, 0.02))

        # Each additional concurrent request adds a small queuing penalty,
        # simulating limited CPU cores compared to Primary.
        load_penalty = 0.018 * (current_load - 1)
        target_duration = base_duration + load_penalty

        # Burn real CPU cycles for roughly target_duration seconds instead
        # of idling, so the work actually shows up in CPU metrics.
        end_time = time.time() + target_duration
        x = 0
        while time.time() < end_time:
            x = (x * 1103515245 + 12345) % 2147483647
    finally:
        with _active_requests_lock:
            _active_requests -= 1

 
 
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="10"/>
  <title>Backup Server — DevOps Monitor</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
 
    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #f0fdf4;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
 
    header {
      background: #ffffff;
      border-bottom: 3px solid #16a34a;
      padding: 0 48px;
      height: 66px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 1px 6px rgba(0,0,0,0.06);
    }
 
    .brand { display: flex; align-items: center; gap: 14px; }
 
    .brand-logo {
      width: 38px; height: 38px;
      background: linear-gradient(135deg, #16a34a, #15803d);
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 19px;
    }
 
    .brand-name { font-size: 17px; font-weight: 700; color: #0f172a; }
    .brand-name span { color: #16a34a; }
 
    .backup-badge {
      background: #16a34a;
      color: white;
      padding: 4px 16px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 1px;
    }
 
    .time-box {
      font-size: 14px; font-weight: 600; color: #475569;
      background: #f8fafc; border: 1px solid #e2e8f0;
      padding: 6px 16px; border-radius: 8px;
      font-family: 'Courier New', monospace; letter-spacing: 1px;
    }
 
    .alert-banner {
      background: #fef9c3;
      border-bottom: 2px solid #ca8a04;
      padding: 10px 48px;
      font-size: 13px;
      color: #854d0e;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
    }
 
    .page {
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      padding: 48px 24px; gap: 32px;
    }
 
    .page-title { text-align: center; }
    .page-title h2 { font-size: 24px; font-weight: 800; color: #0f172a; }
    .page-title p  { font-size: 14px; color: #64748b; margin-top: 6px; }
 
    .cards { display: grid; grid-template-columns: repeat(3, 260px); gap: 22px; }
 
    .card {
      background: #ffffff; border-radius: 18px;
      padding: 30px 28px; border: 1px solid #e2e8f0;
      box-shadow: 0 2px 12px rgba(0,0,0,0.06);
      position: relative; overflow: hidden;
      transition: box-shadow 0.2s, transform 0.2s;
    }
 
    .card:hover { box-shadow: 0 8px 32px rgba(0,0,0,0.10); transform: translateY(-4px); }
 
    .card::before {
      content: ''; position: absolute;
      top: 0; left: 0; right: 0; height: 4px;
      border-radius: 18px 18px 0 0;
    }
 
    .card-status::before { background: linear-gradient(90deg, #16a34a, #4ade80); }
    .card-uptime::before { background: linear-gradient(90deg, #0891b2, #38bdf8); }
    .card-req::before    { background: linear-gradient(90deg, #7c3aed, #a78bfa); }
 
    .card-icon {
      width: 48px; height: 48px; border-radius: 14px;
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; margin-bottom: 20px;
    }
 
    .icon-green  { background: #f0fdf4; }
    .icon-blue   { background: #eff6ff; }
    .icon-purple { background: #f5f3ff; }
 
    .card-label {
      font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1px;
      color: #94a3b8; margin-bottom: 10px;
    }
 
    .card-value {
      font-size: 36px; font-weight: 900;
      line-height: 1; color: #0f172a; letter-spacing: -1px;
    }
 
    .card-status .card-value { color: #16a34a; font-size: 22px; letter-spacing: 0; }
    .card-sub { font-size: 12px; color: #94a3b8; margin-top: 8px; }
 
    .card-watermark {
      position: absolute; bottom: -8px; right: -4px;
      font-size: 72px; opacity: 0.04;
      pointer-events: none; user-select: none;
    }
 
    .lb-info {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      padding: 20px 28px;
      max-width: 820px;
      width: 100%;
      box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
 
    .lb-title {
      font-size: 13px; font-weight: 700; color: #0f172a;
      margin-bottom: 14px;
      display: flex; align-items: center; gap: 8px;
    }
 
    .lb-row {
      display: flex; align-items: center;
      justify-content: space-between;
      padding: 10px 0;
      border-bottom: 1px solid #f1f5f9;
      font-size: 13px;
    }
 
    .lb-row:last-child { border-bottom: none; }
    .lb-label { color: #64748b; }
    .lb-value { font-weight: 600; color: #0f172a; font-family: monospace; }
 
    .status-dot {
      display: inline-block;
      width: 8px; height: 8px; border-radius: 50%;
      margin-right: 6px;
    }
 
    .dot-green  { background: #22c55e; }
    .dot-yellow { background: #f59e0b; }
 
    footer {
      background: #ffffff; border-top: 1px solid #e2e8f0;
      padding: 14px 48px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 12px; color: #94a3b8;
    }
  </style>
</head>
<body>
 
<header>
  <div class="brand">
    <div class="brand-logo">🔄</div>
    <div class="brand-name">DevOps <span>Monitor</span></div>
  </div>
  <div style="display:flex; align-items:center; gap:16px;">
    <span class="backup-badge">● BACKUP SERVER</span>
    <div class="time-box">{{ current_time }}</div>
  </div>
</header>
 
<div class="alert-banner">
  ⚡ Load Balancer Active — This is the BACKUP server (port 5002).
  Primary server (port 5000) may be down or under heavy load.
  Traffic is being automatically routed here by Nginx.
</div>
 
<div class="page">
 
  <div class="page-title">
    <h2>🔄 Backup Server — Active</h2>
    <p>Secondary application instance · Handling traffic via Nginx load balancer · Port 5002</p>
  </div>
 
  <div class="cards">
 
    <div class="card card-status">
      <div class="card-icon icon-green">✅</div>
      <div class="card-label">Server Status</div>
      <div class="card-value">● ACTIVE</div>
      <div class="card-sub">Backup · port 5002</div>
      <div class="card-watermark">✅</div>
    </div>
 
    <div class="card card-uptime">
      <div class="card-icon icon-blue">⏱️</div>
      <div class="card-label">Uptime</div>
      <div class="card-value">{{ uptime }}</div>
      <div class="card-sub">since backup started</div>
      <div class="card-watermark">⏱</div>
    </div>
 
    <div class="card card-req">
      <div class="card-icon icon-purple">📨</div>
      <div class="card-label">Requests Handled</div>
      <div class="card-value">{{ count }}</div>
      <div class="card-sub">routed via load balancer</div>
      <div class="card-watermark">📨</div>
    </div>
 
  </div>
 
  <div class="lb-info">
    <div class="lb-title">🔀 Load Balancer Configuration</div>
 
    <div class="lb-row">
      <span class="lb-label">Load Balancer</span>
      <span class="lb-value">Nginx · port 8080</span>
    </div>
    <div class="lb-row">
      <span class="lb-label">Primary Server</span>
      <span class="lb-value">
        <span class="status-dot dot-yellow"></span>
        localhost:5000 (may be down)
      </span>
    </div>
    <div class="lb-row">
      <span class="lb-label">Backup Server</span>
      <span class="lb-value">
        <span class="status-dot dot-green"></span>
        localhost:5002 (serving now)
      </span>
    </div>
    <div class="lb-row">
      <span class="lb-label">Strategy</span>
      <span class="lb-value">Least Connections with Health Checks</span>
    </div>
    <div class="lb-row">
      <span class="lb-label">Health Check Interval</span>
      <span class="lb-value">Every 10 seconds</span>
    </div>
    <div class="lb-row">
      <span class="lb-label">Failover</span>
      <span class="lb-value">Automatic — zero manual intervention</span>
    </div>
  </div>
 
</div>
 
<footer>
  <span>Backup Server · Load Balancer Demo · PG Final Year Major Project</span>
  <span>Last updated: {{ current_time }}</span>
</footer>
 
</body>
</html>
"""
 
 
@app.route('/')
@REQUEST_TIME.time()
def home():
    global request_value
    start = time.time()
    REQUEST_COUNT.labels(endpoint='/').inc()
    request_value += 1

    # Backup server intentionally runs on lower-priority hardware in this
    # architecture. simulate_backup_workload() does real CPU-bound work
    # with natural jitter and load-dependent slowdown, so CPU and latency
    # panels move together believably instead of a flat artificial delay.
    simulate_backup_workload()
 
    res = render_template_string(
        HTML_PAGE,
        count        = request_value,
        current_time = datetime.now().strftime("%H:%M:%S"),
        uptime       = get_uptime(),
    )
 
    REQUEST_LATENCY.labels(method=request.method, endpoint='/').observe(time.time() - start)
    return res
 
 
@app.route('/health')
def health():
    global request_value
    REQUEST_COUNT.labels(endpoint='/health').inc()
    request_value += 1
    return {
        "status": "OK",
        "server": "backup",
        "port":   5002,
        "uptime": get_uptime(),
        "time":   datetime.now().strftime("%H:%M:%S"),
    }
 
 
@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
 
 
if __name__ == '__main__':
    print("[backup] starting on port 5002")
    app.run(host='0.0.0.0', port=5002, debug=False)