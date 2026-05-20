from flask import Flask, render_template_string, request
from analyzer import run_analysis
from predictor import start_prediction_loop, latest_predictions
from prometheus_client import Counter, Summary, Histogram, generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime
import math, random, time
import threading
import time
import random
import requests

app = Flask(__name__)

REQUEST_COUNT = Counter(
    'app_requests_total',
    'Total number of requests',
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

request_value = 0
error_value   = 0
START_TIME    = time.time()

alert_history     = []
MAX_ALERT_HISTORY = 20


def add_alert(source, name, severity, description):
    alert_history.insert(0, {
        'time':        datetime.now().strftime("%d %b %Y, %H:%M:%S"),
        'source':      source,
        'name':        name,
        'severity':    severity,
        'description': description,
    })
    if len(alert_history) > MAX_ALERT_HISTORY:
        alert_history.pop()


def get_uptime():
    secs = int(time.time() - START_TIME)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


SHARED_CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #f1f5f9;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    header {
      background: #ffffff;
      border-bottom: 1px solid #e2e8f0;
      padding: 0 48px;
      height: 66px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 1px 6px rgba(0,0,0,0.06);
      position: sticky; top: 0; z-index: 100;
    }

    .brand { display: flex; align-items: center; gap: 14px; text-decoration: none; }

    .brand-logo {
      width: 38px; height: 38px;
      background: linear-gradient(135deg, #1d4ed8, #6d28d9);
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 19px;
    }

    .brand-name { font-size: 17px; font-weight: 700; color: #0f172a; }
    .brand-name span { color: #1d4ed8; }

    .header-right { display: flex; align-items: center; gap: 14px; }

    .live-pill {
      display: flex; align-items: center; gap: 8px;
      background: #f0fdf4; border: 1px solid #bbf7d0;
      color: #15803d; padding: 5px 16px;
      border-radius: 999px; font-size: 12px;
      font-weight: 700; letter-spacing: 0.6px;
    }

    .live-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; }

    .time-box {
      font-size: 14px; font-weight: 600; color: #475569;
      background: #f8fafc; border: 1px solid #e2e8f0;
      padding: 6px 16px; border-radius: 8px;
      font-family: 'Courier New', monospace; letter-spacing: 1px;
    }

    .nav-links { display: flex; gap: 8px; }

    .nav-btn {
      padding: 7px 14px; border-radius: 8px;
      border: 1px solid #e2e8f0; background: #f8fafc;
      color: #475569; text-decoration: none;
      font-size: 13px; font-weight: 500; transition: all 0.15s;
    }

    .nav-btn:hover { background: #eff6ff; border-color: #93c5fd; color: #1d4ed8; }
    .nav-btn.active { background: #1d4ed8; border-color: #1d4ed8; color: #ffffff; }

    .box {
      background: #ffffff; border: 1px solid #e2e8f0;
      border-radius: 14px; padding: 24px 26px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }

    .box-title {
      font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1px;
      color: #94a3b8; margin-bottom: 16px;
    }

    footer {
      background: #ffffff; border-top: 1px solid #e2e8f0;
      padding: 14px 48px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 12px; color: #94a3b8;
      margin-top: auto;
    }

    .toast {
      position: fixed;
      top: 80px;
      right: 24px;
      z-index: 9999;
      min-width: 280px;
      max-width: 380px;
      padding: 14px 18px;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.15);
      display: flex;
      align-items: flex-start;
      gap: 12px;
      font-size: 13px;
      font-weight: 500;
      animation: slideIn 0.3s ease, fadeOut 0.5s ease 3.5s forwards;
    }

    @keyframes slideIn {
      from { transform: translateX(120%); opacity: 0; }
      to   { transform: translateX(0);   opacity: 1; }
    }

    @keyframes fadeOut {
      from { opacity: 1; }
      to   { opacity: 0; transform: translateX(120%); }
    }

    .toast-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #15803d; }
    .toast-warning { background: #fffbeb; border: 1px solid #fde68a; color: #b45309; }
    .toast-error   { background: #fef2f2; border: 1px solid #fecaca; color: #dc2626; }
    .toast-info    { background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; }

    .toast-icon { font-size: 18px; flex-shrink: 0; }
    .toast-title { font-weight: 700; margin-bottom: 2px; }
    .toast-msg { font-size: 12px; opacity: 0.85; }
"""

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="{{ refresh_interval }}"/>
  <title>Application Monitoring</title>
  <style>
    """ + SHARED_CSS + """

    .page {
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      padding: 48px 24px; gap: 32px;
    }

    .page-title { text-align: center; }
    .page-title h2 { font-size: 24px; font-weight: 800; color: #0f172a; }
    .page-title p  { font-size: 14px; color: #64748b; margin-top: 6px; }

    .cards { display: grid; grid-template-columns: repeat(5, 220px); gap: 18px; }

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

    .card-status::before  { background: linear-gradient(90deg, #16a34a, #4ade80); }
    .card-uptime::before  { background: linear-gradient(90deg, #1d4ed8, #60a5fa); }
    .card-req::before     { background: linear-gradient(90deg, #7c3aed, #a78bfa); }
    .card-error::before   { background: linear-gradient(90deg, #dc2626, #f87171); }
    .card-rate::before    { background: linear-gradient(90deg, #0891b2, #38bdf8); }

    .card-icon {
      width: 48px; height: 48px; border-radius: 14px;
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; margin-bottom: 20px;
    }

    .icon-green  { background: #f0fdf4; }
    .icon-blue   { background: #eff6ff; }
    .icon-purple { background: #f5f3ff; }
    .icon-red    { background: #fef2f2; }
    .icon-teal   { background: #ecfeff; }

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
    .card-error  .card-value { color: {{ error_color }}; }
    .card-sub { font-size: 12px; color: #94a3b8; margin-top: 8px; }

    .card-watermark {
      position: absolute; bottom: -8px; right: -4px;
      font-size: 72px; opacity: 0.04;
      pointer-events: none; user-select: none;
    }

    .btn-row { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }

    .btn {
      display: inline-block; padding: 12px 28px;
      border-radius: 10px; text-decoration: none;
      font-weight: 700; font-size: 13px; letter-spacing: 0.3px;
      transition: transform 0.15s, box-shadow 0.15s;
    }

    .btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.15); }
    .btn-analyze { background: linear-gradient(135deg,#1d4ed8,#6d28d9); color: white; }
    .btn-predict { background: linear-gradient(135deg,#0891b2,#0e7490); color: white; }
    .btn-alerts  { background: linear-gradient(135deg,#dc2626,#b91c1c); color: white; }
  </style>
</head>
<body>

<header>
  <a class="brand" href="/">
    <div class="brand-logo">📡</div>
    <div class="brand-name">Application <span>Monitoring</span></div>
  </a>
  <div class="header-right">
    <div class="nav-links">
      <a class="nav-btn active" href="/">Home</a>
      <a class="nav-btn" href="/analyze">Root Cause</a>
      <a class="nav-btn" href="/predict">Predictions</a>
      <a class="nav-btn" href="/alerts">Alerts</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <div class="time-box">{{ current_time }}</div>
  </div>
</header>

<div class="page">
  <div class="page-title">
    <h2>Application Control Center</h2>
    <p>Real-Time Application Performance Monitoring Dashboard using DevOps Tools</p>
  </div>

  <div class="cards">
    <div class="card card-status">
      <div class="card-icon icon-green">✅</div>
      <div class="card-label">App Status</div>
      <div class="card-value">● RUNNING</div>
      <div class="card-sub">Flask · port 5000</div>
      <div class="card-watermark">✅</div>
    </div>
    <div class="card card-uptime">
      <div class="card-icon icon-blue">⏱️</div>
      <div class="card-label">Uptime</div>
      <div class="card-value">{{ uptime }}</div>
      <div class="card-sub">since server started</div>
      <div class="card-watermark">⏱</div>
    </div>
    <div class="card card-req">
      <div class="card-icon icon-purple">📨</div>
      <div class="card-label">Total Requests</div>
      <div class="card-value">{{ count }}</div>
      <div class="card-sub">all endpoints combined</div>
      <div class="card-watermark">📨</div>
    </div>
    <div class="card card-error">
      <div class="card-icon icon-red">⚠️</div>
      <div class="card-label">Total Errors</div>
      <div class="card-value">{{ errors }}</div>
      <div class="card-sub">HTTP 500 responses</div>
      <div class="card-watermark">⚠</div>
    </div>
    <div class="card card-rate">
      <div class="card-icon icon-teal">📊</div>
      <div class="card-label">Live Req / sec</div>
      {% if req_rate is none %}
      <div class="card-value" style="font-size:16px; color:#94a3b8;">Prometheus<br>offline</div>
      <div class="card-sub">start Prometheus to enable</div>
      {% else %}
      <div class="card-value" style="color:#0891b2;">{{ "%.3f"|format(req_rate) }}</div>
      <div class="card-sub">from Prometheus · 2m avg</div>
      {% endif %}
      <div class="card-watermark">📊</div>
    </div>
  </div>

  <div style="font-size:11px; color:#94a3b8; text-align:center; margin-top:-16px;">
    📡 <strong style="color:#0891b2;">Live Req/sec</strong> is fetched directly from
    <strong>Prometheus</strong> via PromQL on every page load —
    demonstrating the full <em>Flask → Prometheus → Flask UI</em> monitoring loop.
  </div>

  <div class="btn-row">
    <a href="/analyze" class="btn btn-analyze">🧠 Root Cause Analyzer</a>
    <a href="/predict" class="btn btn-predict">🔮 Predictive Alerts</a>
    <a href="/alerts"  class="btn btn-alerts">🚨 Alert History</a>
  </div>
</div>

<footer>
  <span>Real-Time Application Performance Monitoring Dashboard Using DevOps Tools · PG Final Year Major Project</span>
  <span>Last updated: {{ current_time }}</span>
</footer>

</body>
</html>
"""

ANALYZE_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="15"/>
  <title>Root Cause Analyzer</title>
  <style>
    """ + SHARED_CSS + """

    main {
      flex: 1; max-width: 960px; margin: 0 auto;
      padding: 40px 24px;
      display: flex; flex-direction: column; gap: 24px;
      width: 100%;
    }

    .page-title h2 { font-size: 22px; font-weight: 800; color: #0f172a; }
    .page-title p  { font-size: 13px; color: #64748b; margin-top: 5px; }

    .status-banner {
      padding: 24px 28px; border-radius: 16px; border: 1px solid;
      display: flex; align-items: center; justify-content: space-between;
    }

    .banner-healthy  { background: #f0fdf4; border-color: #bbf7d0; }
    .banner-warning  { background: #fffbeb; border-color: #fde68a; }
    .banner-critical { background: #fef2f2; border-color: #fecaca; }

    .banner-left { display: flex; align-items: center; gap: 16px; }
    .banner-icon { font-size: 40px; }

    .banner-status {
      font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;
    }

    .status-healthy  { color: #15803d; }
    .status-warning  { color: #b45309; }
    .status-critical { color: #dc2626; }

    .banner-cause { font-size: 22px; font-weight: 800; color: #0f172a; }
    .banner-right { text-align: right; }

    .confidence-label {
      font-size: 11px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.8px;
      color: #64748b; margin-bottom: 4px;
    }

    .confidence-value { font-size: 40px; font-weight: 900; color: #0f172a; }
    .explanation-text { font-size: 15px; color: #1e293b; line-height: 1.7; }

    .score-row { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
    .score-row:last-child { margin-bottom: 0; }

    .score-name {
      font-size: 13px; font-weight: 600;
      color: #334155; width: 160px; flex-shrink: 0;
    }

    .bar-track { flex: 1; background: #f1f5f9; border-radius: 999px; height: 10px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #1d4ed8, #7c3aed); }
    .bar-fill-dominant { background: linear-gradient(90deg, #dc2626, #f97316); }

    .score-val {
      font-size: 14px; font-weight: 700;
      color: #0f172a; width: 40px; text-align: right; flex-shrink: 0;
    }

    .metrics-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }

    .metric-card {
      background: #f8fafc; border: 1px solid #e2e8f0;
      border-radius: 12px; padding: 16px; text-align: center;
    }

    .metric-label {
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.8px;
      color: #94a3b8; margin-bottom: 8px;
    }

    .metric-value { font-size: 22px; font-weight: 800; color: #0f172a; }
    .metric-unit  { font-size: 11px; color: #94a3b8; margin-top: 4px; }
  </style>
</head>
<body>

<header>
  <a class="brand" href="/">
    <div class="brand-logo">📡</div>
    <div class="brand-name">Application <span>Monitoring</span></div>
  </a>
  <div class="header-right">
    <div class="nav-links">
      <a class="nav-btn" href="/">Home</a>
      <a class="nav-btn active" href="/analyze">Root Cause</a>
      <a class="nav-btn" href="/predict">Predictions</a>
      <a class="nav-btn" href="/alerts">Alerts</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <div class="time-box">{{ current_time }}</div>
  </div>
</header>

<main>
  <div class="page-title">
    <h2>🧠 Root Cause Analyzer</h2>
    <p>Reads live metrics from Prometheus every 15 seconds and identifies the dominant cause of any performance issue.</p>
  </div>

  <div class="status-banner banner-{{ status }}">
    <div class="banner-left">
      <div class="banner-icon">
        {% if status == 'healthy' %}✅{% elif status == 'warning' %}⚠️{% else %}🔴{% endif %}
      </div>
      <div>
        <div class="banner-status status-{{ status }}">System Status — {{ status|upper }}</div>
        <div class="banner-cause">{{ dominant_cause }}</div>
      </div>
    </div>
    <div class="banner-right">
      <div class="confidence-label">Analysis Confidence</div>
      <div class="confidence-value">{{ confidence }}%</div>
    </div>
  </div>

  <div class="box">
    <div class="box-title">📋 What This Means</div>
    <div class="explanation-text">{{ explanation }}</div>
  </div>

  <div class="box">
    <div class="box-title">📊 Cause Scores — Higher score means more likely cause</div>
    {% for cause, score in scores.items() %}
    <div class="score-row">
      <div class="score-name">{{ cause }}</div>
      <div class="bar-track">
        <div class="bar-fill {% if cause == dominant_cause and score > 0 %}bar-fill-dominant{% endif %}"
             style="width: {{ bar_widths[cause] }}px; max-width: 100%;"></div>
      </div>
      <div class="score-val">{{ score }}</div>
    </div>
    {% endfor %}
  </div>

  <div class="box">
    <div class="box-title">📡 Live Metric Values — Fetched from Prometheus</div>
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">CPU Usage</div>
        <div class="metric-value">{{ "%.1f"|format(metrics.cpu) }}</div>
        <div class="metric-unit">CPU percent</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Memory</div>
        <div class="metric-value">{{ "%.1f"|format(metrics.memory) }}</div>
        <div class="metric-unit">RAM used (MB)</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Avg Latency</div>
        <div class="metric-value">{{ "%.0f"|format(metrics.latency * 1000) }}</div>
        <div class="metric-unit">milliseconds</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Request Rate</div>
        <div class="metric-value">{{ "%.3f"|format(metrics.req_rate) }}</div>
        <div class="metric-unit">requests/sec</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Error Rate</div>
        <div class="metric-value">{{ "%.3f"|format(metrics.error_rate) }}</div>
        <div class="metric-unit">errors/sec</div>
      </div>
    </div>
  </div>
</main>

<footer>
  <span>Root Cause Analyzer · PG Final Year Major Project</span>
  <span>Last analyzed: {{ timestamp }}</span>
</footer>

</body>
</html>
"""

PREDICT_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="15"/>
  <title>Predictive Alert System</title>
  <style>
    """ + SHARED_CSS + """

    main {
      flex: 1; max-width: 1000px; margin: 0 auto;
      padding: 40px 24px;
      display: flex; flex-direction: column; gap: 24px;
      width: 100%;
    }

    .page-title h2 { font-size: 22px; font-weight: 800; color: #0f172a; }
    .page-title p  { font-size: 13px; color: #64748b; margin-top: 5px; }

    .info-banner {
      background: #eff6ff; border: 1px solid #bfdbfe;
      border-radius: 12px; padding: 14px 20px;
      font-size: 13px; color: #1e40af; line-height: 1.6;
    }

    .collection-bar {
      background: #ffffff; border: 1px solid #e2e8f0;
      border-radius: 10px; padding: 12px 20px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 13px;
    }

    .collection-left { display: flex; align-items: center; gap: 10px; }
    .dot-collecting  { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }
    .collection-text { color: #334155; font-weight: 600; }
    .collection-sub  { color: #64748b; font-size: 12px; margin-top: 2px; }

    .predict-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; }

    .predict-card {
      background: #ffffff; border: 1px solid #e2e8f0;
      border-radius: 14px; padding: 22px 24px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.05);
      position: relative; overflow: hidden;
    }

    .predict-card::before {
      content: ''; position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      border-radius: 14px 14px 0 0;
    }

    .predict-safe::before     { background: linear-gradient(90deg,#16a34a,#4ade80); }
    .predict-warning::before  { background: linear-gradient(90deg,#d97706,#fbbf24); }
    .predict-critical::before { background: linear-gradient(90deg,#dc2626,#f97316); }

    .predict-header {
      display: flex; align-items: center;
      justify-content: space-between; margin-bottom: 18px;
    }

    .predict-label { font-size: 15px; font-weight: 700; color: #0f172a; }

    .severity-badge {
      font-size: 11px; font-weight: 700;
      padding: 3px 12px; border-radius: 999px;
      text-transform: uppercase; letter-spacing: 0.5px;
    }

    .badge-safe     { background:#f0fdf4; color:#15803d; border:1px solid #bbf7d0; }
    .badge-warning  { background:#fffbeb; color:#b45309; border:1px solid #fde68a; }
    .badge-critical { background:#fef2f2; color:#dc2626; border:1px solid #fecaca; }

    .time-cols { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; }

    .time-col {
      background: #f8fafc; border: 1px solid #e2e8f0;
      border-radius: 10px; padding: 12px; text-align: center;
    }

    .time-col-label {
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.8px;
      color: #94a3b8; margin-bottom: 6px;
    }

    .time-col-value { font-size: 20px; font-weight: 800; color: #0f172a; }
    .time-col-unit  { font-size: 10px; color: #94a3b8; margin-top: 3px; }
    .col-warning  .time-col-value { color: #d97706; }
    .col-critical .time-col-value { color: #dc2626; }

    .threshold-row {
      display: flex; align-items: center; justify-content: space-between;
      margin-top: 14px; padding-top: 12px;
      border-top: 1px dashed #e2e8f0;
      font-size: 12px; color: #64748b;
    }

    .threshold-val { font-weight: 700; color: #dc2626; }

    .waiting-state { text-align: center; padding: 20px 0; color: #94a3b8; font-size: 13px; }
    .progress-bg   { background: #f1f5f9; border-radius: 999px; height: 6px; overflow: hidden; margin-top:10px; }
    .progress-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg,#22c55e,#16a34a); }
    .progress-label{ font-size: 11px; color: #94a3b8; margin-top: 4px; text-align: right; }
  </style>
</head>
<body>

<header>
  <a class="brand" href="/">
    <div class="brand-logo">📡</div>
    <div class="brand-name">Application <span>Monitoring</span></div>
  </a>
  <div class="header-right">
    <div class="nav-links">
      <a class="nav-btn" href="/">Home</a>
      <a class="nav-btn" href="/analyze">Root Cause</a>
      <a class="nav-btn active" href="/predict">Predictions</a>
      <a class="nav-btn" href="/alerts">Alerts</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <div class="time-box">{{ current_time }}</div>
  </div>
</header>

<main>
  <div class="page-title">
    <h2>🔮 Predictive Alert System</h2>
    <p>Uses linear regression on metric history to forecast values 2 and 5 minutes ahead — sends Yahoo email alert before a breach occurs.</p>
  </div>

  <div class="info-banner">
    💡 <strong>How this works:</strong> Every 10 seconds the system collects metric readings from Prometheus.
    Once 3+ readings exist it applies <strong>linear regression</strong> to forecast future values.
    If a metric is predicted to breach its threshold a <strong>Yahoo email alert is sent automatically</strong> — before the problem happens.
    Alertmanager fires <em>after</em> a breach. This system fires <em>before</em> it.
  </div>

  <div class="collection-bar">
    <div class="collection-left">
      <div class="dot-collecting"></div>
      <div>
        <div class="collection-text">Background Collector Running</div>
        <div class="collection-sub">Collecting every 10s · Linear regression on last {{ data_points }} readings · Alert cooldown: 5 minutes</div>
      </div>
    </div>
    <div style="font-size:12px; color:#64748b; text-align:right;">
      Last updated<br><strong style="color:#0f172a;">{{ timestamp }}</strong>
    </div>
  </div>

  {% if data_points < 3 %}
  <div class="box">
    <div class="box-title">⏳ Collecting Data</div>
    <div class="waiting-state">
      System needs at least 3 data points to run predictions.<br>
      Currently have <strong>{{ data_points }}</strong> of 3 needed readings.<br>
      Wait {{ 3 - data_points }} more cycle(s) — approximately {{ (3 - data_points) * 10 }} seconds.
    </div>
    <div class="progress-bg">
      <div class="progress-fill" style="width: {{ [(data_points / 3 * 100)|int, 100]|min }}%;"></div>
    </div>
    <div class="progress-label">{{ data_points }}/3 readings collected</div>
  </div>

  {% else %}

  <div class="predict-grid">
    {% for metric_key in ['cpu', 'memory', 'latency', 'error_rate'] %}
    {% set p = predictions[metric_key] %}
    <div class="predict-card predict-{{ p.severity }}">
      <div class="predict-header">
        <div class="predict-label">
          {% if metric_key == 'cpu' %}🖥️
          {% elif metric_key == 'memory' %}💾
          {% elif metric_key == 'latency' %}⏱️
          {% else %}⚠️{% endif %}
          {{ p.label }}
        </div>
        <span class="severity-badge badge-{{ p.severity }}">{{ p.severity }}</span>
      </div>
      <div class="time-cols">
        <div class="time-col">
          <div class="time-col-label">Now</div>
          <div class="time-col-value">
            {% if metric_key == 'latency' %}{{ "%.0f"|format(p.current * 1000) }}
            {% else %}{{ "%.2f"|format(p.current) }}{% endif %}
          </div>
          <div class="time-col-unit">
            {% if metric_key == 'latency' %}ms{% else %}{{ p.unit }}{% endif %}
          </div>
        </div>
        <div class="time-col col-{{ p.sev_2min }}">
          <div class="time-col-label">In 2 Minutes</div>
          <div class="time-col-value">
            {% if metric_key == 'latency' %}{{ "%.0f"|format(p.pred_2min * 1000) }}
            {% else %}{{ "%.2f"|format(p.pred_2min) }}{% endif %}
          </div>
          <div class="time-col-unit">
            {% if metric_key == 'latency' %}ms{% else %}{{ p.unit }}{% endif %}
          </div>
        </div>
        <div class="time-col col-{{ p.sev_5min }}">
          <div class="time-col-label">In 5 Minutes</div>
          <div class="time-col-value">
            {% if metric_key == 'latency' %}{{ "%.0f"|format(p.pred_5min * 1000) }}
            {% else %}{{ "%.2f"|format(p.pred_5min) }}{% endif %}
          </div>
          <div class="time-col-unit">
            {% if metric_key == 'latency' %}ms{% else %}{{ p.unit }}{% endif %}
          </div>
        </div>
      </div>
      <div class="threshold-row">
        <span>Alert threshold</span>
        <span class="threshold-val">
          {% if metric_key == 'latency' %}{{ "%.0f"|format(p.threshold * 1000) }}ms
          {% else %}{{ p.threshold }}{{ p.unit }}{% endif %}
        </span>
      </div>
    </div>
    {% endfor %}
  </div>
  {% endif %}
</main>

<footer>
  <span>Predictive Alert System · PG Final Year Major Project</span>
  <span>Last analyzed: {{ timestamp }}</span>
</footer>
</body>
</html>
"""

ALERTS_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="20"/>
  <title>Alert History</title>
  <style>
    """ + SHARED_CSS + """

    main {
      flex: 1; max-width: 960px; margin: 0 auto;
      padding: 40px 24px;
      display: flex; flex-direction: column; gap: 24px;
      width: 100%;
    }

    .page-title h2 { font-size: 22px; font-weight: 800; color: #0f172a; }
    .page-title p  { font-size: 13px; color: #64748b; margin-top: 5px; }

    .trigger-panel {
      background: #ffffff; border: 1px solid #e2e8f0;
      border-radius: 14px; padding: 22px 26px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }

    .trigger-title { font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 6px; }
    .trigger-sub   { font-size: 12px; color: #64748b; margin-bottom: 18px; }
    .trigger-btns  { display: flex; gap: 12px; flex-wrap: wrap; }

    .trigger-form { display: inline; }

    .trigger-btn {
      padding: 9px 20px; border-radius: 8px;
      font-size: 13px; font-weight: 600;
      cursor: pointer; border: none;
      transition: transform 0.15s, box-shadow 0.15s;
    }

    .trigger-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,0.12); }

    .btn-error { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca !important; }
    .btn-slow  { background: #fffbeb; color: #b45309; border: 1px solid #fde68a !important; }
    .btn-load  { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe !important; }
    .btn-test  { background: linear-gradient(135deg,#7c3aed,#6d28d9); color: white; }

    .am-status {
      background: #f8fafc; border: 1px solid #e2e8f0;
      border-radius: 10px; padding: 14px 18px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 13px;
    }

    .am-left { display: flex; align-items: center; gap: 10px; }

    .alert-row {
      display: flex; align-items: flex-start;
      gap: 16px; padding: 14px 0;
      border-bottom: 1px solid #f1f5f9;
    }

    .alert-row:last-child { border-bottom: none; }

    .sev-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
    .dot-critical { background: #dc2626; }
    .dot-warning  { background: #d97706; }
    .dot-info     { background: #1d4ed8; }

    .alert-body { flex: 1; }
    .alert-name { font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 3px; }
    .alert-desc { font-size: 13px; color: #64748b; line-height: 1.5; }

    .alert-meta { display: flex; gap: 10px; margin-top: 6px; flex-wrap: wrap; }

    .meta-tag {
      font-size: 11px; font-weight: 600;
      padding: 2px 10px; border-radius: 999px;
    }

    .tag-source   { background: #f1f5f9; color: #475569; }
    .tag-critical { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
    .tag-warning  { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
    .tag-info     { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }

    .alert-time {
      font-size: 11px; color: #94a3b8;
      font-family: 'Courier New', monospace;
      flex-shrink: 0; padding-top: 2px; white-space: nowrap;
    }

    .empty-state { text-align: center; padding: 48px 0; color: #94a3b8; }
    .empty-icon  { font-size: 48px; margin-bottom: 12px; opacity: 0.4; }
    .empty-text  { font-size: 14px; }
    .empty-sub   { font-size: 12px; margin-top: 6px; }
  </style>
</head>
<body>

<header>
  <a class="brand" href="/">
    <div class="brand-logo">📡</div>
    <div class="brand-name">Application <span>Monitoring</span></div>
  </a>
  <div class="header-right">
    <div class="nav-links">
      <a class="nav-btn" href="/">Home</a>
      <a class="nav-btn" href="/analyze">Root Cause</a>
      <a class="nav-btn" href="/predict">Predictions</a>
      <a class="nav-btn active" href="/alerts">Alerts</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <div class="time-box">{{ current_time }}</div>
  </div>
</header>

{% if toast %}
<div class="toast toast-{{ toast.type }}">
  <div class="toast-icon">{{ toast.icon }}</div>
  <div>
    <div class="toast-title">{{ toast.title }}</div>
    <div class="toast-msg">{{ toast.msg }}</div>
  </div>
</div>
{% endif %}

<main>

  <div class="page-title">
    <h2>🚨 Alert History</h2>
    <p>Live log of all alerts fired from Alertmanager, Predictive System, and manual triggers. Auto-refreshes every 20 seconds.</p>
  </div>

  <div class="am-status">
    <div class="am-left">
      <div class="live-dot"></div>
      <div>
        <strong>Alertmanager</strong> · port 9093 ·
        <a href="http://localhost:9093" target="_blank"
           style="color:#1d4ed8; font-size:12px;">Open UI ↗</a>
      </div>
    </div>
    <div style="font-size:12px; color:#64748b;">
      5 alert rules active · Prometheus evaluating every 15s
    </div>
  </div>

  <div class="trigger-panel">
    <div class="trigger-title">⚡ Trigger Test Scenarios</div>
    <div class="trigger-sub">
      Use these buttons to simulate incidents. Results appear instantly in the alert log below — no page redirect.
    </div>
    <div class="trigger-btns">
      <form class="trigger-form" method="POST" action="/alerts/trigger">
        <input type="hidden" name="action" value="error"/>
        <button class="trigger-btn btn-error" type="submit">💥 Trigger 10 Errors</button>
      </form>
      <form class="trigger-form" method="POST" action="/alerts/trigger">
        <input type="hidden" name="action" value="load"/>
        <button class="trigger-btn btn-load" type="submit">📈 Trigger Traffic Spike</button>
      </form>
      <form class="trigger-form" method="POST" action="/alerts/trigger">
        <input type="hidden" name="action" value="slow"/>
        <button class="trigger-btn btn-slow" type="submit">🐢 Trigger Slow Requests</button>
      </form>
      <form class="trigger-form" method="POST" action="/alerts/trigger">
        <input type="hidden" name="action" value="test"/>
        <button class="trigger-btn btn-test" type="submit">✉️ Send Test Email Alert</button>
      </form>
    </div>
  </div>

  <div class="box">
    <div class="box-title">📋 Alert Log — Last {{ alerts|length }} events</div>

    {% if alerts %}
    <div style="font-size:13px; color:#64748b; margin-bottom:14px;">
      Showing <strong>{{ alerts|length }}</strong> alert(s) · newest first
    </div>

    {% for alert in alerts %}
    <div class="alert-row">
      <div class="sev-dot dot-{{ alert.severity }}"></div>
      <div class="alert-body">
        <div class="alert-name">{{ alert.name }}</div>
        <div class="alert-desc">{{ alert.description }}</div>
        <div class="alert-meta">
          <span class="meta-tag tag-source">{{ alert.source }}</span>
          <span class="meta-tag tag-{{ alert.severity }}">{{ alert.severity|upper }}</span>
        </div>
      </div>
      <div class="alert-time">{{ alert.time }}</div>
    </div>
    {% endfor %}

    {% else %}
    <div class="empty-state">
      <div class="empty-icon">🟢</div>
      <div class="empty-text">No alerts fired yet</div>
      <div class="empty-sub">Use the trigger buttons above to simulate incidents</div>
    </div>
    {% endif %}

  </div>

</main>

<footer>
  <span>Alert History · PG Final Year Major Project</span>
  <span>Last refreshed: {{ current_time }}</span>
</footer>

</body>
</html>
"""


def _fetch_req_rate():
    """Fetch live request rate from Prometheus for the home page."""
    try:
        res = requests.get(
            "http://localhost:9090/api/v1/query",
            params={"query": 'rate(app_requests_total{job="flask-app"}[2m])'},
            timeout=2,
        )
        results = res.json().get("data", {}).get("result", [])
        if results:
            total = sum(float(r["value"][1]) for r in results)
            return round(total, 3)
        return 0.0
    except Exception:
        return None   # None = Prometheus unreachable


@app.route('/')
@REQUEST_TIME.time()
def home():
    global request_value
    start = time.time()
    REQUEST_COUNT.labels(endpoint='/').inc()
    request_value += 1

    error_color = '#dc2626' if error_value > 0 else '#0f172a'
    req_rate    = _fetch_req_rate()   # live from Prometheus

    res = render_template_string(
        HTML_PAGE,
        count            = request_value,
        errors           = error_value,
        current_time     = datetime.now().strftime("%H:%M:%S"),
        uptime           = get_uptime(),
        refresh_interval = random.randint(8, 15),
        error_color      = error_color,
        req_rate         = req_rate,
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
        "uptime": get_uptime(),
        "time":   datetime.now().strftime("%H:%M:%S"),
    }


@app.route('/error')
def error_route():
    global error_value
    REQUEST_COUNT.labels(endpoint='/error').inc()
    ERROR_COUNT.labels(endpoint='/error').inc()
    error_value += 1
    return {"error": "Simulated 500 error"}, 500





@app.route('/analyze')
def analyze():
    result = run_analysis()

    class M:
        pass

    m            = M()
    m.cpu        = result['metrics']['cpu']
    m.memory     = result['metrics']['memory']
    m.latency    = result['metrics']['latency']
    m.req_rate   = result['metrics']['req_rate']
    m.error_rate = result['metrics']['error_rate']

    return render_template_string(
        ANALYZE_PAGE,
        status         = result['status'],
        dominant_cause = result['dominant_cause'],
        confidence     = result['confidence'],
        explanation    = result['explanation'],
        scores         = result['scores'],
        bar_widths     = result['bar_widths'],
        metrics        = m,
        timestamp      = result['timestamp'],
        current_time   = datetime.now().strftime("%H:%M:%S"),
    )


@app.route('/predict')
def predict():
    import predictor as p
    preds = p.latest_predictions
    return render_template_string(
        PREDICT_PAGE,
        predictions  = preds,
        data_points  = preds.get('data_points', 0),
        timestamp    = preds.get('timestamp', datetime.now().strftime("%d %b %Y, %H:%M:%S")),
        current_time = datetime.now().strftime("%H:%M:%S"),
    )


@app.route('/alerts', methods=['GET'])
def alerts():
    return render_template_string(
        ALERTS_PAGE,
        alerts       = alert_history,
        current_time = datetime.now().strftime("%H:%M:%S"),
        toast        = None,
    )


@app.route('/alerts/trigger', methods=['POST'])
def alerts_trigger():
    global request_value, error_value

    action = request.form.get('action', '')
    toast  = None

    if action == 'error':
        for _ in range(10):
            REQUEST_COUNT.labels(endpoint='/error').inc()
            ERROR_COUNT.labels(endpoint='/error').inc()
            error_value += 1
        add_alert('Manual Trigger', 'Error Storm Triggered', 'critical',
                  '10 errors fired simultaneously to simulate an error surge scenario.')
        toast = {'type': 'error', 'icon': '💥',
                 'title': 'Error Storm Triggered', 'msg': '10 errors fired — check alert log below'}

    elif action == 'load':
        def fire():
            global request_value
            for _ in range(100):
                REQUEST_COUNT.labels(endpoint='/').inc()
                request_value += 1
        threading.Thread(target=fire, daemon=True).start()
        add_alert('Manual Trigger', 'Traffic Spike Simulation', 'warning',
                  '100 requests fired in background to simulate high traffic load.')
        toast = {'type': 'warning', 'icon': '📈',
                 'title': 'Traffic Spike Triggered', 'msg': '100 requests firing in background'}

    elif action == 'slow':
        def fire_slow():
            global request_value
            for _ in range(5):
                REQUEST_COUNT.labels(endpoint='/slow').inc()
                request_value += 1
                d = random.uniform(1.0, 2.5)
                time.sleep(d)
                REQUEST_LATENCY.labels(method='GET', endpoint='/slow').observe(d)
        threading.Thread(target=fire_slow, daemon=True).start()
        add_alert('Manual Trigger', 'Slow Request Simulation', 'warning',
                  '5 high-latency requests fired to simulate response time degradation.')
        toast = {'type': 'warning', 'icon': '🐢',
                 'title': 'Slow Requests Triggered', 'msg': '5 slow requests firing in background'}

    elif action == 'test':
        try:
            from mailer import send_alert_email
            send_alert_email('cpu', 'CPU Usage', 45.0, 72.0, 88.0, 80.0, '%', 'warning')
            add_alert('Test Button', 'Test Alert Email Sent', 'info',
                      'Manual test email sent to subhash6609@yahoo.com successfully.')
            toast = {'type': 'success', 'icon': '✉️',
                     'title': 'Test Email Sent', 'msg': 'Check subhash6609@yahoo.com inbox'}
        except Exception as e:
            add_alert('Test Button', 'Test Alert Failed', 'critical',
                      f'Email send failed: {str(e)}')
            toast = {'type': 'error', 'icon': '❌', 'title': 'Email Failed', 'msg': str(e)}

    return render_template_string(
        ALERTS_PAGE,
        alerts       = alert_history,
        current_time = datetime.now().strftime("%H:%M:%S"),
        toast        = toast,
    )

@app.route('/cpu-stress')
def cpu_stress():
    import math
    # Heavier computation — runs 3 times to hold CPU high longer
    total_primes = 0
    for _ in range(3):          # repeat 3x = stays high ~6-9 seconds
        limit = 500000          # bigger sieve than before (was 100000)
        sieve = [True] * limit
        for i in range(2, int(math.sqrt(limit)) + 1):
            if sieve[i]:
                for j in range(i*i, limit, i):
                    sieve[j] = False
        primes = [x for x in range(2, limit) if sieve[x]]
        total_primes += len(primes)
    return {'status': 'done', 'primes_found': total_primes}


@app.route('/memory-stress')
def memory_stress():
    # Allocates ~50MB temporarily — simulates memory leak
    big_list = ['x' * 1000 for _ in range(50000)]
    time.sleep(2)   # hold it for 2 seconds
    result = len(big_list)
    del big_list    # release after
    return {'status': 'done', 'items': result}

@app.route('/slow')
def slow():
    global request_value
    REQUEST_COUNT.labels(endpoint='/slow').inc()
    request_value += 1
    delay = random.uniform(2.0, 3.5)
    time.sleep(delay)
    REQUEST_LATENCY.labels(method=request.method, endpoint='/slow').observe(delay)
    return {'status': 'slow', 'delay_seconds': round(delay, 2)}


@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


if __name__ == '__main__':
    t = threading.Thread(target=start_prediction_loop, daemon=True)
    t.start()
    print("[app] started — predictor running in background")
    app.run(host='0.0.0.0', port=5000, debug=False)