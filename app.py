from flask import Flask, render_template_string, request, redirect, url_for, session
from analyzer import run_analysis
from predictor import start_prediction_loop, latest_predictions
from prometheus_client import Counter, Summary, Histogram, generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime
import math, random, time
import threading
import requests
import os
import secrets
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

_secret_key = os.environ.get('FLASK_SECRET_KEY')
if not _secret_key:
    _secret_key = secrets.token_hex(32)
    print(
        "[app] WARNING: FLASK_SECRET_KEY not set in .env — using a random "
        "key generated for this run only. Sessions will not persist across "
        "restarts. Add FLASK_SECRET_KEY=<random value> to your .env file "
        "for a stable key."
    )
app.secret_key = _secret_key

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

# Pre-register label combinations so Prometheus reports 0 instead of
# "no data" before the first real error/hit on each endpoint.
REQUEST_COUNT.labels(endpoint='/').inc(0)
REQUEST_COUNT.labels(endpoint='/health').inc(0)
REQUEST_COUNT.labels(endpoint='/error').inc(0)
REQUEST_COUNT.labels(endpoint='/analyze').inc(0)
ERROR_COUNT.labels(endpoint='/error').inc(0)

request_value = 0
error_value   = 0
START_TIME    = time.time()

alert_history     = []
MAX_ALERT_HISTORY = 50


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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=DM+Mono:wght@400;500;600&display=swap');

    :root {
	  --bg:          #f8fafc;
	  --surface:     #ffffff;
	  --surface-2:   #f1f5f9;
	  --border:      #e2e8f0;
	  --border-2:    #cbd5e1;
	  --text:        #0f172a;
	  --text-muted:  #475569;
	  --text-dim:    #94a3b8;
	  --cyan:        #0ea5e9;
	  --cyan-glow:   rgba(14,165,233,0.15);
	  --cyan-dim:    rgba(14,165,233,0.08);
	  --indigo:      #6366f1;
	  --indigo-glow: rgba(99,102,241,0.12);
	  --green:       #10b981;
	  --green-glow:  rgba(16,185,129,0.12);
	  --amber:       #f59e0b;
	  --amber-glow:  rgba(245,158,11,0.12);
	  --red:         #ef4444;
	  --red-glow:    rgba(239,68,68,0.12);
	  --purple:      #a855f7;
    	}

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    html { scroll-behavior: smooth; }

    body {
      font-family: 'Inter', system-ui, sans-serif;
      background: #f0f4ff;
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background-image:
        radial-gradient(ellipse 80% 50% at 20% 0%, rgba(14,165,233,0.10) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 80% 100%, rgba(99,102,241,0.10) 0%, transparent 60%);
    }

    header {
      background: rgba(255,255,255,0.90);
      border-bottom: 1px solid #e2e8f0;
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      padding: 0 48px;
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky; top: 0; z-index: 100;
      box-shadow: 0 1px 0 #e2e8f0, 0 8px 32px rgba(0,0,0,0.06);
    }

    .brand { display: flex; align-items: center; gap: 12px; text-decoration: none; }

    .brand-logo {
      width: 36px; height: 36px;
      background: linear-gradient(135deg, #0ea5e9, #6366f1);
      border-radius: 9px;
      display: flex; align-items: center; justify-content: center;
      font-size: 17px;
      box-shadow: 0 4px 14px rgba(14,165,233,0.4);
    }

    .brand-name {
      font-size: 15px; font-weight: 700;
      color: var(--text); letter-spacing: -0.2px;
    }
    .brand-name span { color: var(--cyan); }

    .header-right { display: flex; align-items: center; gap: 12px; }

    
    .nav-links { display: flex; gap: 2px; }

    .nav-btn {
      padding: 6px 14px; border-radius: 7px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--text-muted); text-decoration: none;
      font-size: 13px; font-weight: 500;
      transition: all 0.18s; letter-spacing: 0.1px;
    }

    .nav-btn:hover {
      background: var(--surface-2);
      border-color: var(--border-2);
      color: var(--text);
    }

    .nav-btn.active {
      background: var(--cyan-dim);
      border-color: rgba(14,165,233,0.3);
      color: var(--cyan);
      font-weight: 600;
    }

    
    .live-pill {
      display: flex; align-items: center; gap: 7px;
      background: var(--green-glow);
      border: 1px solid rgba(16,185,129,0.3);
      color: var(--green);
      padding: 4px 14px; border-radius: 999px;
      font-size: 11px; font-weight: 700;
      letter-spacing: 0.8px;
    }

    .live-dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: var(--green);
      animation: pulse-dot 1.5s ease infinite;
      transform-origin: center;
      flex-shrink: 0;
    }

    @keyframes pulse-dot {
      0%   { transform: scale(1);   box-shadow: 0 0 0 0 rgba(16,185,129,0.6); }
      50%  { transform: scale(1.2); box-shadow: 0 0 0 6px rgba(16,185,129,0); }
      100% { transform: scale(1);   box-shadow: 0 0 0 0 rgba(16,185,129,0); }
    }

    
    .time-box {
      font-family: 'DM Mono', monospace;
      font-size: 13px; font-weight: 500;
      color: var(--text-muted);
      background: var(--surface-2);
      border: 1px solid var(--border);
      padding: 5px 14px; border-radius: 7px;
      letter-spacing: 1px;
    }

    
    .box {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px; padding: 22px 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.03);
      transition: box-shadow 0.2s;
    }
    .box:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.06), 0 12px 32px rgba(99,102,241,0.08);
        border-color: #c7d2fe;
    }

    .box-title {
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1.2px;
      color: var(--text-dim); margin-bottom: 16px;
    }

    
    footer {
      background: var(--surface);
      border-top: 1px solid var(--border);
      padding: 12px 48px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 11px; color: var(--text-dim);
      margin-top: auto;
      font-family: 'DM Mono', monospace;
    }

    .toast {
      position: fixed;
      top: 76px; right: 22px;
      z-index: 9999;
      min-width: 280px; max-width: 380px;
      padding: 14px 18px; border-radius: 12px;
      backdrop-filter: blur(20px);
      box-shadow: 0 8px 40px rgba(0,0,0,0.5);
      display: flex; align-items: flex-start; gap: 12px;
      font-size: 13px; font-weight: 500;
      animation: slideIn 0.3s ease, fadeOut 0.5s ease 3.5s forwards;
      border: 1px solid;
    }

    @keyframes slideIn {
      from { transform: translateX(120%); opacity: 0; }
      to   { transform: translateX(0);   opacity: 1; }
    }

    @keyframes fadeOut {
      from { opacity: 1; }
      to   { opacity: 0; transform: translateX(120%); }
    }

    .toast-success { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
    .toast-warning { background: #fffbeb; border-color: #fde68a; color: #b45309; }
    .toast-error   { background: #fef2f2; border-color: #fecaca; color: #dc2626; }
    .toast-info    { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }

    .toast-icon  { font-size: 18px; flex-shrink: 0; }
    .toast-title { font-weight: 700; margin-bottom: 2px; }
    .toast-msg   { font-size: 12px; opacity: 0.8; }

    a, button, input { transition: border-color 0.2s, background 0.15s; }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 99px; }
    ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

    /* ── Dark mode variable overrides ── */
    html.dark {
      --bg:          #0a0f1e;
      --surface:     #111827;
      --surface-2:   #1f2937;
      --border:      #1e293b;
      --border-2:    #334155;
      --text:        #f1f5f9;
      --text-muted:  #94a3b8;
      --text-dim:    #475569;
    }

    html.dark body {
      background: #0a0f1e;
      background-image:
        radial-gradient(ellipse 80% 50% at 20% 0%, rgba(14,165,233,0.08) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 80% 100%, rgba(99,102,241,0.08) 0%, transparent 60%);
    }

    html.dark header {
      background: rgba(17,24,39,0.92);
      border-bottom-color: #1e293b;
      box-shadow: 0 1px 0 #1e293b, 0 8px 32px rgba(0,0,0,0.3);
    }

    html.dark footer {
      background: #111827;
      border-top-color: #1e293b;
    }

    html.dark .card,
    html.dark .box,
    html.dark .predict-card,
    html.dark .infra-card,
    html.dark .trigger-panel,
    html.dark .am-status,
    html.dark .collection-bar,
    html.dark .summary-bar,
    html.dark .lb-info,
    html.dark .tab-bar {
      background: var(--surface);
      border-color: var(--border);
    }

    html.dark .box:hover { border-color: #2d3f6e; }

    html.dark .nav-btn:hover  { background: var(--surface-2); border-color: var(--border-2); }
    html.dark .nav-btn.active { background: rgba(14,165,233,0.12); }

    html.dark .time-box {
      background: var(--surface-2);
      border-color: var(--border);
    }

    html.dark .dark-toggle {
      background: var(--surface-2);
      border-color: var(--border);
      color: #f1f5f9;
    }
    html.dark .dark-toggle:hover {
      background: var(--border);
    }

    html.dark .card-value {
      color: #f1f5f9 !important;
      -webkit-text-fill-color: #f1f5f9 !important;
    }

    html.dark .card-status .card-value {
      color: #34d399 !important;
      -webkit-text-fill-color: #34d399 !important;
    }

    html.dark .card-error .card-value {
      -webkit-text-fill-color: unset !important;
    }

    html.dark #health-score-val {
      -webkit-text-fill-color: unset !important;
    }

    html.dark .card-label { color: #64748b; }
    html.dark .card-sub   { color: var(--text-dim); }

    html.dark .metric-card {
      background: var(--surface-2);
      border-color: var(--border);
    }

    html.dark .score-bar-wrap { background: #1e293b; }
    html.dark .bar-track       { background: #1e293b; border-color: var(--border); }
    html.dark .time-col        { background: var(--surface-2); border-color: var(--border); }

    html.dark .info-banner {
      background: #0f172a;
      border-color: #1e3a5f;
      color: #7dd3fc;
    }
    html.dark .info-banner strong { color: #38bdf8; }

    html.dark .prom-note { color: var(--text-dim); }

    html.dark .tab-btn        { color: var(--text-muted); }
    html.dark .tab-btn:hover  { background: var(--surface-2); border-color: var(--border-2); color: var(--text); }
    html.dark .tab-btn.active { color: var(--cyan); background: rgba(14,165,233,0.1); border-color: rgba(14,165,233,0.25); }

    html.dark .iframe-wrap { background: var(--surface); border-color: var(--border); }

    /* dark mode toggle button */
    .dark-toggle {
      width: 34px; height: 34px; border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--surface-2);
      display: flex; align-items: center; justify-content: center;
      font-size: 16px; cursor: pointer;
      transition: background 0.18s, transform 0.18s;
      flex-shrink: 0;
    }
    .dark-toggle:hover { background: var(--border-2); transform: scale(1.08); }
"""

# Dark mode flash prevention — runs before first paint on every page
DARK_MODE_SCRIPT = """
<script>
  (function() {
    var dm = localStorage.getItem('devops-dark-mode');
    if (dm === 'true') {
      document.documentElement.classList.add('dark');
    }
  })();
</script>
"""

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <script>if(localStorage.getItem('devops-dark-mode')==='true')document.documentElement.classList.add('dark');</script>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="{{ refresh_interval }}"/>
  <title>Application Monitoring</title>
<style>
    """ + SHARED_CSS + """
    
    .page {
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      padding: 48px 24px; gap: 36px;
    }

    .page-title { text-align: center; }
    .page-title h2 {
      font-size: 32px; font-weight: 800; color: #0f172a;
      letter-spacing: -1px;
      background: linear-gradient(135deg, #0f172a 40%, #6366f1);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .page-title p { font-size: 13px; color: var(--text-muted); margin-top: 8px; }

    html.dark .page-title h2 {
      background: linear-gradient(135deg, #f1f5f9 40%, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    
     .cards { display: grid; grid-template-columns: repeat(6, 175px); gap: 14px; }

    .card {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 16px; padding: 26px 24px;
      position: relative; overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.07), 0 10px 30px -5px rgba(0,0,0,0.07);
      opacity: 0; /* start hidden */
      transition: box-shadow 0.3s, transform 0.3s;
      cursor: default;
      animation: slideCard 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }

    .card:nth-child(1) { animation-delay: 0.05s; }
    .card:nth-child(2) { animation-delay: 0.15s; }
    .card:nth-child(3) { animation-delay: 0.25s; }
    .card:nth-child(4) { animation-delay: 0.35s; }
    .card:nth-child(5) { animation-delay: 0.45s; }
    .card:nth-child(6) { animation-delay: 0.55s; }


    .card:hover {
      box-shadow: 0 20px 40px -8px rgba(0,0,0,0.12);
      transform: translateY(-6px);
    }

    
    .card::after {
      content: '';
      position: absolute;
      top: 0; left: -100%; width: 60%; height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.5), transparent);
      transform: skewX(-20deg);
      pointer-events: none;
      z-index: 1;
    }

    .card:hover::after {
      animation: shimmer 0.6s ease forwards;
     }
    .card::before {
  	content: '';
  	position: absolute; top: 0; left: 0; right: 0;
  	height: 3px; border-radius: 16px 16px 0 0;
     }

    .card-status::before { background: linear-gradient(90deg, #10b981, #34d399); }
    .card-uptime::before { background: linear-gradient(90deg, #0ea5e9, #38bdf8); }
    .card-req::before    { background: linear-gradient(90deg, #6366f1, #a78bfa); }
    .card-error::before  { background: linear-gradient(90deg, #ef4444, #f87171); }
    .card-rate::before   { background: linear-gradient(90deg, #0ea5e9, #06b6d4); }

    .card-status::after  { background: var(--green);  box-shadow: 2px 0 12px var(--green-glow); }
    .card-uptime::after  { background: var(--cyan);   box-shadow: 2px 0 12px var(--cyan-glow);  }
    .card-req::after     { background: var(--indigo); box-shadow: 2px 0 12px var(--indigo-glow);}
    .card-error::after   { background: var(--red);    box-shadow: 2px 0 12px var(--red-glow);   }
    .card-rate::after    { background: var(--cyan);   box-shadow: 2px 0 12px var(--cyan-glow);  }

    .card-status:hover { box-shadow: 0 12px 40px var(--green-glow); }
    .card-uptime:hover { box-shadow: 0 12px 40px var(--cyan-glow); }
    .card-req:hover    { box-shadow: 0 12px 40px var(--indigo-glow); }
    .card-error:hover  { box-shadow: 0 12px 40px var(--red-glow); }
    .card-rate:hover   { box-shadow: 0 12px 40px var(--cyan-glow); }

    .card-label {
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1.5px;
      color: #94a3b8; margin-bottom: 16px;
    }

    .card-value {
      font-family: 'DM Mono', monospace;
      font-size: 34px; font-weight: 700;
      line-height: 1; color: #0f172a;
      letter-spacing: -2px;
      margin-bottom: 4px;
    }

    .card-status .card-value {
      font-family: 'Inter', sans-serif;
      color: #10b981; font-size: 18px;
      letter-spacing: 0.5px; font-weight: 700;
    }

    .card-error .card-value { color: {{ error_color }}; }

    .card-sub {
      font-size: 11px; color: var(--text-dim);
      margin-top: 10px;
    }

    /* subtle bg glow behind the number */
    .card-bg-glow {
      position: absolute; bottom: -20px; right: -20px;
      width: 80px; height: 80px; border-radius: 50%;
      pointer-events: none;
    }
    .card-status .card-bg-glow  { background: radial-gradient(circle, var(--green-glow) 0%, transparent 70%); }
    .card-uptime .card-bg-glow  { background: radial-gradient(circle, var(--cyan-glow)  0%, transparent 70%); }
    .card-req    .card-bg-glow  { background: radial-gradient(circle, var(--indigo-glow)0%, transparent 70%); }
    .card-error  .card-bg-glow  { background: radial-gradient(circle, var(--red-glow)   0%, transparent 70%); }
    .card-rate   .card-bg-glow  { background: radial-gradient(circle, var(--cyan-glow)  0%, transparent 70%); }

    /* prometheus note */
    .prom-note {
      font-size: 11px; color: var(--text-dim); text-align: center;
      margin-top: -20px;
      font-family: 'DM Mono', monospace;
    }
    .prom-note strong { color: var(--cyan); }

    /* nav buttons */
    .btn-row { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }

    .btn {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 11px 26px; border-radius: 10px;
      text-decoration: none; font-weight: 600;
      font-size: 13px; letter-spacing: 0.2px;
      transition: all 0.2s; border: 1px solid;
      position: relative; overflow: hidden;
    }
    
    .btn::after {
  	content: '';
  	position: absolute;
  	width: 0; height: 0;
  	border-radius: 50%;
  	background: rgba(255,255,255,0.4);
  	transform: translate(-50%, -50%);
  	transition: width 0.5s ease, height 0.5s ease, opacity 0.5s ease;
  	opacity: 0;
  	left: 50%; top: 50%;
     }

     .btn:active::after {
 	 width: 200px; height: 200px;
 	 opacity: 0;
 	 transition: 0s;
      }

    .btn:hover { transform: translateY(-2px); }

    .btn-analyze {
      background: linear-gradient(135deg, #eef2ff, #e0e7ff);
      color: #4338ca; border-color: #c7d2fe;
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(99,102,241,0.15);
    }
    .btn-analyze:hover {
      background: linear-gradient(135deg, #e0e7ff, #c7d2fe);
      box-shadow: 0 8px 24px rgba(99,102,241,0.25);
      transform: translateY(-3px);
    }

    .btn-predict {
      background: linear-gradient(135deg, #ecfeff, #cffafe);
      color: #0369a1; border-color: #7dd3fc;
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(14,165,233,0.15);
    }
    .btn-predict:hover {
      background: linear-gradient(135deg, #cffafe, #bae6fd);
      box-shadow: 0 8px 24px rgba(14,165,233,0.25);
      transform: translateY(-3px);
    }

    .btn-alerts {
      background: linear-gradient(135deg, #fff1f2, #fee2e2);
      color: #be123c; border-color: #fecdd3;
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(239,68,68,0.15);
    }
    .btn-alerts:hover {
      background: linear-gradient(135deg, #fee2e2, #fecdd3);
      box-shadow: 0 8px 24px rgba(239,68,68,0.25);
      transform: translateY(-3px);
    }

     .btn-infra {
      background: linear-gradient(135deg, #f0fdf4, #dcfce7);
      color: #15803d; border-color: #86efac;
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(16,185,129,0.15);
    }

    .btn-infra:hover {
      background: linear-gradient(135deg, #dcfce7, #bbf7d0);
      box-shadow: 0 8px 24px rgba(16,185,129,0.25);
      transform: translateY(-3px);
    }

    .btn-grafana {
      background: linear-gradient(135deg, #fdf4ff, #f3e8ff);
      color: #7c3aed; border-color: #e9d5ff;
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(168,85,247,0.15);
    }

    .btn-grafana:hover {
      background: linear-gradient(135deg, #f3e8ff, #e9d5ff);
      box-shadow: 0 8px 24px rgba(168,85,247,0.25);
      transform: translateY(-3px);
    }

    @keyframes countUp {
  	from { opacity: 0; transform: translateY(8px); }
  	to   { opacity: 1; transform: translateY(0); }
    }
    .card-value {
  	animation: countUp 0.5s ease both;
    }
	.card:nth-child(1) .card-value { animation-delay: 0.05s; }
	.card:nth-child(2) .card-value { animation-delay: 0.12s; }
	.card:nth-child(3) .card-value { animation-delay: 0.19s; }
	.card:nth-child(4) .card-value { animation-delay: 0.26s; }
	.card:nth-child(5) .card-value { animation-delay: 0.33s; }
	.card:nth-child(6) .card-value { animation-delay: 0.40s; }

     @keyframes ripple {
 	 to { transform: scale(1); opacity: 0; }
     }
     
     @keyframes slideCard {
  	from {
    		opacity: 0;
    		transform: translateY(32px) scale(0.97);
        }
  	to {
    		opacity: 1;
    		transform: translateY(0) scale(1);
        }
      }


      /* Magnetic-feel scale */
      .card {
  		transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1),
              box-shadow 0.3s ease,
              border-color 0.2s ease !important;
       }
       .card:hover {
  		transform: translateY(-8px) scale(1.02) !important;
       }

    .card-health::before { background: linear-gradient(90deg, #10b981, #34d399); }
    .card-health:hover   { box-shadow: 0 20px 40px -8px rgba(16,185,129,0.18) !important; }
    .card-health .card-bg-glow { background: radial-gradient(circle, rgba(16,185,129,0.12) 0%, transparent 70%); }

    .score-bar-wrap {
      width: 100%; max-width: 1140px;
      background: #e2e8f0; border-radius: 999px;
      height: 6px; overflow: hidden;
      margin-top: -24px;
    }
    #health-bar-fill {
      height: 100%; border-radius: 999px;
      transition: width 0.9s cubic-bezier(0.4,0,0.2,1), background 0.4s ease;
    }
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
      <a class="nav-btn" href="/infrastructure">Infrastructure</a>
      <a class="nav-btn" href="/grafana">Grafana</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <button class="dark-toggle" id="darkToggle" title="Toggle dark mode" onclick="toggleDark()">🌙</button>
    <div class="time-box">{{ current_time }}</div>
  </div>
</header>

<div class="page">
  <div class="page-title">
    <h2>Application Control Center</h2>
    <p>Real-Time Application Performance Monitoring Dashboard using DevOps Tools</p>
  </div>

  <div class="cards">
    <!-- Status -->
    <div class="card card-status">
      <div class="card-label">App Status</div>
      <div class="card-value">● RUNNING</div>
      <div class="card-sub">Flask · port 5000</div>
      <div class="card-bg-glow"></div>
    </div>
    <!-- Uptime -->
    <div class="card card-uptime">
      <div class="card-label">Uptime</div>
      <div class="card-value">{{ uptime }}</div>
      <div class="card-sub">since server started</div>
      <div class="card-bg-glow"></div>
    </div>
    <!-- Requests -->
    <div class="card card-req">
      <div class="card-label">Total Requests</div>
      <div class="card-value">{{ count }}</div>
      <div class="card-sub">all endpoints combined</div>
      <div class="card-bg-glow"></div>
    </div>
    <!-- Errors -->
    <div class="card card-error">
      <div class="card-label">Total Errors</div>
      <div class="card-value">{{ errors }}</div>
      <div class="card-sub">HTTP 500 responses</div>
      <div class="card-bg-glow"></div>
    </div>
    <!-- Live rate -->
    <div class="card card-rate">
      <div class="card-label">Live Req / sec</div>
      {% if req_rate is none %}
      <div class="card-value" style="font-size:14px; color:var(--text-dim); font-family:'DM Sans';">Prometheus<br>offline</div>
      <div class="card-sub">start Prometheus to enable</div>
      {% else %}
      <div class="card-value">{{ "%.3f"|format(req_rate) }}</div>
      <div class="card-sub">from Prometheus · 2m avg</div>
      {% endif %}
      <div class="card-bg-glow"></div>
    </div>
    <!-- Health Score card -->
    <div class="card card-health" id="health-card" style="animation-delay:0.55s;">
      <div class="card-label">Health Score</div>
      <div class="card-value" id="health-score-val"
           style="color:{{ initial_color }}; font-size:30px; letter-spacing:-1px;">
        {% if initial_score is not none %}{{ initial_score }}{% else %}—{% endif %}
      </div>
      <div class="card-sub">/100 · live</div>
      <div class="card-bg-glow"></div>
    </div>
  </div>
  
  <div class="score-bar-wrap">
    <div id="health-bar-fill" style="
      width:{% if initial_score is not none %}{{ initial_score }}{% else %}0{% endif %}%;
      background:{{ initial_color }};
    "></div>
  </div>

  <div class="prom-note">
    📡 <strong>Live Req/sec</strong> fetched from Prometheus via PromQL on every load
    &mdash; demonstrating the full <em>Flask → Prometheus → Flask UI</em> loop
  </div>

  <div class="btn-row">
    <a href="/analyze" class="btn btn-analyze">🧠 Root Cause Analyzer</a>
    <a href="/predict" class="btn btn-predict">🔮 Predictive Alerts</a>
    <a href="/alerts"  class="btn btn-alerts">🚨 Alert History</a>
    <a href="/infrastructure" class="btn btn-infra">🖥️ Infrastructure</a>
    <a href="/grafana" class="btn btn-grafana">📊 Grafana Dashboards</a>
  </div>
</div>

<footer>
  <span>Real-Time Application Performance Monitoring Dashboard Using DevOps Tools &middot; PG Final Year Major Project</span>
  <span>Last updated: {{ current_time }}</span>
</footer>

<script>
  // Animate numbers counting up
  function animateCount(el, target, isFloat, decimals) {
    const duration = 800;
    const start = performance.now();
    const from = 0;
    function update(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = from + (target - from) * ease;
      if (isFloat) {
        el.textContent = current.toFixed(decimals);
      } else {
        el.textContent = Math.floor(current);
      }
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  window.addEventListener('load', () => {
    // Total Requests
    const reqEl = document.querySelector('.card-req .card-value');
    if (reqEl) animateCount(reqEl, {{ count }}, false, 0);

    // Total Errors
    const errEl = document.querySelector('.card-error .card-value');
    if (errEl) animateCount(errEl, {{ errors }}, false, 0);

    // Live Req/sec
    {% if req_rate is not none %}
    const rateEl = document.querySelector('.card-rate .card-value');
    if (rateEl) animateCount(rateEl, {{ req_rate }}, true, 3);
    {% endif %}
  });
  
  {% if initial_score is not none %}
    const hsEl = document.getElementById('health-score-val');
    if (hsEl) animateCount(hsEl, {{ initial_score }}, true, 1);
    {% endif %}

</script>

<script>
  document.querySelectorAll('.btn').forEach(btn => {
    btn.addEventListener('click', function(e) {
      const ripple = document.createElement('span');
      const rect = this.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 2;
      ripple.style.cssText = `
        position: absolute;
        width: ${size}px; height: ${size}px;
        border-radius: 50%;
        background: rgba(255,255,255,0.35);
        left: ${e.clientX - rect.left - size/2}px;
        top: ${e.clientY - rect.top - size/2}px;
        transform: scale(0);
        animation: ripple 0.55s ease-out forwards;
        pointer-events: none;
      `;
      this.appendChild(ripple);
      setTimeout(() => ripple.remove(), 600);
    });
  });
</script>

<script>
document.querySelectorAll('.card').forEach(card => {
  card.addEventListener('mousemove', e => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const rotateX = ((y - cy) / cy) * -8;
    const rotateY = ((x - cx) / cx) * 8;
    card.style.transform =
      `translateY(-8px) perspective(600px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.02)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
    card.style.transition =
      'transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)';
  });
});
</script>

<script>
  // ── Health Score live polling ──
  let _hsCurrent = {{ initial_score if initial_score is not none else 'null' }};

  function _hsAnimate(from, to) {
    const el = document.getElementById('health-score-val');
    if (!el || to === null) { if (el) el.textContent = '—'; return; }
    if (from === null) from = to;
    const dur = 700, t0 = performance.now();
    function tick(now) {
      const p = Math.min((now - t0) / dur, 1);
      const ease = 1 - Math.pow(1 - p, 3);
      el.textContent = (from + (to - from) * ease).toFixed(1);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function _hsUpdate(score, color) {
    const bar = document.getElementById('health-bar-fill');
    const val = document.getElementById('health-score-val');

    _hsAnimate(_hsCurrent, score);
    _hsCurrent = score;

    if (score !== null) {
      if (val)  val.style.color      = color;
      if (bar) { bar.style.width      = score + '%';
                 bar.style.background = color; }
    }
  }

  setInterval(() => {
    fetch('/api/health-score')
      .then(r => r.json())
      .then(d => _hsUpdate(d.score, d.color))
      .catch(() => {});
  }, 3000);
</script>

<script>
  // Dark mode toggle
  function toggleDark() {
    var html = document.documentElement;
    var btn  = document.getElementById('darkToggle');
    if (html.classList.contains('dark')) {
      html.classList.remove('dark');
      localStorage.setItem('devops-dark-mode', 'false');
      if (btn) btn.textContent = '🌙';
    } else {
      html.classList.add('dark');
      localStorage.setItem('devops-dark-mode', 'true');
      if (btn) btn.textContent = '☀️';
    }
  }
  // Set correct icon on load
  (function() {
    var btn = document.getElementById('darkToggle');
    if (btn && document.documentElement.classList.contains('dark')) {
      btn.textContent = '☀️';
    }
  })();
</script>

</body>
</html>
"""

# ─────────────────────────────────────────────────────────
#  ANALYZE PAGE
# ─────────────────────────────────────────────────────────
ANALYZE_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <script>if(localStorage.getItem('devops-dark-mode')==='true')document.documentElement.classList.add('dark');</script>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="15"/>
  <title>Root Cause Analyzer</title>
  <style>
    """ + SHARED_CSS + """

    main {
      flex: 1; max-width: 960px; margin: 0 auto;
      padding: 36px 24px;
      display: flex; flex-direction: column; gap: 20px;
      width: 100%;
    }

    .page-title h2 { font-size: 22px; font-weight: 800; color: var(--text); letter-spacing: -0.3px; }
    .page-title p  { font-size: 13px; color: var(--text-muted); margin-top: 5px; }

    /* status banner */
    .status-banner {
      padding: 28px 32px; border-radius: 16px; border: 1px solid;
      display: flex; align-items: center; justify-content: space-between;
      position: relative; overflow: hidden;
      min-height: 100px;
    }

    .status-banner::before {
      content: '';
      position: absolute; inset: 0;
      background: radial-gradient(ellipse at left center, var(--banner-glow) 0%, transparent 60%);
      pointer-events: none;
    }

    .banner-healthy  {
      background: linear-gradient(135deg, #f0fdf4, #dcfce7);
      border-color: #86efac;
      --banner-glow: rgba(16,185,129,0.1);
    }
    .banner-warning  {
      background: linear-gradient(135deg, #fffbeb, #fef3c7);
      border-color: #fcd34d;
      --banner-glow: rgba(245,158,11,0.1);
    }
    .banner-critical {
      background: linear-gradient(135deg, #fef2f2, #fee2e2);
      border-color: #fca5a5;
      --banner-glow: rgba(239,68,68,0.1);
    }

    .banner-left { display: flex; align-items: center; gap: 18px; }
    .banner-icon { font-size: 48px; }

    .banner-status {
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 5px;
    }
    .status-healthy  { color: var(--green); }
    .status-warning  { color: var(--amber); }
    .status-critical { color: var(--red); }

    .banner-cause {
      font-size: 26px; font-weight: 800; color: var(--text);
    }
    .banner-right { text-align: right; }

    .confidence-label {
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1px;
      color: var(--text-dim); margin-bottom: 5px;
    }

    .confidence-value {
      font-family: 'DM Mono', monospace;
      font-size: 56px; font-weight: 700; color: var(--text);
      letter-spacing: -3px;
      line-height: 1;
    }

    .explanation-text {
      font-size: 14px; color: var(--text-muted);
      line-height: 1.75;
    }

    /* score bars */
    .score-row {
      display: flex; align-items: center; gap: 14px;
      margin-bottom: 14px;
    }
    .score-row:last-child { margin-bottom: 0; }

    .score-name {
      font-size: 12px; font-weight: 600;
      color: var(--text-muted); width: 155px; flex-shrink: 0;
    }

    .bar-track {
      flex: 1; background: #f1f5f9;
      border: 1px solid #e2e8f0;
      border-radius: 999px; height: 10px; overflow: hidden;
    }

    .bar-fill {
      height: 100%; border-radius: 999px;
      background: linear-gradient(90deg, #6366f1, #0ea5e9);
      animation: barGrow 1.2s cubic-bezier(0.4, 0, 0.2, 1) both;
      animation-delay: var(--delay, 0s);
    }

    .bar-fill-dominant {
      background: linear-gradient(90deg, #ef4444, #f59e0b) !important;
      box-shadow: 0 0 12px rgba(239,68,68,0.3);
    }

    .score-val {
      font-family: 'DM Mono', monospace;
      font-size: 13px; font-weight: 600;
      color: var(--text-muted); width: 38px;
      text-align: right; flex-shrink: 0;
    }

    /* metrics grid */
    .metrics-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }

    .metric-card {
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 12px; padding: 16px; text-align: center;
      transition: transform 0.2s, box-shadow 0.2s;
    }

    .metric-card:hover {
  	transform: translateY(-3px);
  	box-shadow: 0 8px 24px rgba(99,102,241,0.12);
        border-color: #c7d2fe;
     }

    .metric-label {
      font-size: 9px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1px;
      color: var(--text-dim); margin-bottom: 10px;
    }

    .metric-value {
      font-family: 'DM Mono', monospace;
      font-size: 22px; font-weight: 600; color: var(--text);
    }

    @keyframes fadeUp {
  	from { opacity: 0; transform: translateY(14px); }
  	to   { opacity: 1; transform: translateY(0); }
    }
    main > * {
  	animation: fadeUp 0.4s ease both;
    }
	main > *:nth-child(1) { animation-delay: 0s; }
	main > *:nth-child(2) { animation-delay: 0.07s; }
	main > *:nth-child(3) { animation-delay: 0.14s; }
	main > *:nth-child(4) { animation-delay: 0.21s; }
	main > *:nth-child(5) { animation-delay: 0.28s; }

    .metric-unit { font-size: 10px; color: var(--text-dim); margin-top: 5px; }

    @keyframes barGrow {
  		from { width: 0; }
  		to   { width: var(--bar-w); }
    }

    /* ── Dark mode: analyze page ── */
    html.dark .banner-healthy {
      background: linear-gradient(135deg, #052e16, #14532d);
      border-color: #166534;
    }
    html.dark .banner-warning {
      background: linear-gradient(135deg, #1c1008, #292000);
      border-color: #854d0e;
    }
    html.dark .banner-critical {
      background: linear-gradient(135deg, #1c0505, #290000);
      border-color: #991b1b;
    }
    html.dark .banner-cause  { color: #f1f5f9; }
    html.dark .confidence-value { color: #f1f5f9; }
    html.dark .confidence-label { color: var(--text-dim); }
    html.dark .score-val    { color: var(--text-muted); }
    html.dark .score-name   { color: var(--text-muted); }
    html.dark .metric-value { color: var(--text); }

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
      <a class="nav-btn" href="/infrastructure">Infrastructure</a>
      <a class="nav-btn" href="/grafana">Grafana</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <button class="dark-toggle" id="darkToggle" title="Toggle dark mode" onclick="toggleDark()">🌙</button>
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
     		style="--bar-w: {{ bar_widths[cause] }}px; animation-delay: {{ loop.index * 0.12 }}s;"></div>
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
  <span>Root Cause Analyzer &middot; PG Final Year Major Project</span>
  <span>Last analyzed: {{ timestamp }}</span>
</footer>

<script>
document.querySelectorAll('.metric-card').forEach(card => {
  card.addEventListener('mousemove', e => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const rX = ((y - cy) / cy) * -6;
    const rY = ((x - cx) / cx) * 6;
    card.style.transform =
      `translateY(-3px) perspective(400px) rotateX(${rX}deg) rotateY(${rY}deg)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
  });
});
</script>

<script>
  // Dark mode toggle
  function toggleDark() {
    var html = document.documentElement;
    var btn  = document.getElementById('darkToggle');
    if (html.classList.contains('dark')) {
      html.classList.remove('dark');
      localStorage.setItem('devops-dark-mode', 'false');
      if (btn) btn.textContent = '🌙';
    } else {
      html.classList.add('dark');
      localStorage.setItem('devops-dark-mode', 'true');
      if (btn) btn.textContent = '☀️';
    }
  }
  // Set correct icon on load
  (function() {
    var btn = document.getElementById('darkToggle');
    if (btn && document.documentElement.classList.contains('dark')) {
      btn.textContent = '☀️';
    }
  })();
</script>

</body>
</html>
"""

# ─────────────────────────────────────────────────────────
#  PREDICT PAGE
# ─────────────────────────────────────────────────────────
PREDICT_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <script>if(localStorage.getItem('devops-dark-mode')==='true')document.documentElement.classList.add('dark');</script>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="15"/>
  <title>Predictive Alert System</title>
  <style>
    """ + SHARED_CSS + """

    main {
      flex: 1; max-width: 1000px; margin: 0 auto;
      padding: 36px 24px;
      display: flex; flex-direction: column; gap: 20px;
      width: 100%;
    }

    .page-title h2 { font-size: 22px; font-weight: 800; color: var(--text); letter-spacing: -0.3px; }
    .page-title p  { font-size: 13px; color: var(--text-muted); margin-top: 5px; }

    
    .info-banner {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 12px; padding: 14px 20px;
      font-size: 13px; color: #1e40af; line-height: 1.65;
    }
    .info-banner strong { color: #1d4ed8; }

    /* collector bar */
    .collection-bar {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 20px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 13px;
    }
    .collection-left { display: flex; align-items: center; gap: 10px; }
    .collection-text { color: var(--text); font-weight: 600; font-size: 13px; }
    .collection-sub  { color: var(--text-dim); font-size: 11px; margin-top: 2px; font-family: 'DM Mono', monospace; }

    /* predict grid */
    .predict-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }

    .predict-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px; padding: 22px;
      position: relative; overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      transition: box-shadow 0.25s, transform 0.25s, border-color 0.25s;
    }

    .predict-card::before {
      content: ''; position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      border-radius: 14px 14px 0 0;
      filter: blur(0px);	
    }

    .predict-safe::before     { background: linear-gradient(90deg, #10b981, #34d399);
				box-shadow: 0 2px 12px rgba(16,185,129,0.4); }
    .predict-warning::before  { background: linear-gradient(90deg, #f59e0b, #fcd34d);
				box-shadow: 0 2px 12px rgba(245,158,11,0.4); }
    .predict-critical::before { background: linear-gradient(90deg, #ef4444, #fb923c);
				box-shadow: 0 2px 12px rgba(239,68,68,0.4); }

    .predict-card:hover { transform: translateY(-3px); }
    .predict-safe:hover    { border-color: #86efac; box-shadow: 0 8px 28px var(--green-glow); }
    .predict-warning:hover { border-color: #fcd34d; box-shadow: 0 8px 28px var(--amber-glow); }
    .predict-critical:hover{ border-color: #fca5a5; box-shadow: 0 8px 28px var(--red-glow); }

    .predict-header {
      display: flex; align-items: center;
      justify-content: space-between; margin-bottom: 18px;
    }

    .predict-label {
      font-size: 14px; font-weight: 700; color: var(--text);
    }

    .severity-badge {
      font-size: 10px; font-weight: 700;
      padding: 3px 11px; border-radius: 999px;
      text-transform: uppercase; letter-spacing: 0.6px;
      border: 1px solid;
    }

    .badge-safe     { background: #f0fdf4; color: #15803d; border-color: #86efac; }
    .badge-warning  { background: #fffbeb; color: #b45309; border-color: #fcd34d; }
    .badge-critical { background: #fef2f2; color: #dc2626; border-color: #fca5a5; }

    .time-cols { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; }

    .time-col {
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 10px; padding: 12px; text-align: center;
      transition: background 0.2s, transform 0.2s, box-shadow 0.2s;
    }
   
    .time-col:not(.col-warning):not(.col-critical):hover {
    		background: #ffffff;
    		transform: translateY(-2px);
    		box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }

    .time-col-label {
      font-size: 9px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.8px;
      color: var(--text-dim); margin-bottom: 8px;
    }

    .time-col-value {
      font-family: 'DM Mono', monospace;
      font-size: 20px; font-weight: 600; color: var(--text);
    }

    .time-col-unit  { font-size: 10px; color: var(--text-dim); margin-top: 4px; }
    .time-col.col-warning  { background: #fffbeb; border-color: #fde68a; }
    .time-col.col-critical { background: #fef2f2; border-color: #fecaca; }

    .threshold-row {
      display: flex; align-items: center; justify-content: space-between;
      margin-top: 14px; padding-top: 12px;
      border-top: 1px solid var(--border);
      font-size: 11px; color: var(--text-dim);
    }
    .threshold-val {
      font-family: 'DM Mono', monospace;
      font-weight: 600; color: var(--red);
    }

    @keyframes fadeUp {
  	from { opacity: 0; transform: translateY(14px); }
  	to   { opacity: 1; transform: translateY(0); }
    }
    main > * {
  	animation: fadeUp 0.4s ease both;
    }
	main > *:nth-child(1) { animation-delay: 0s; }
	main > *:nth-child(2) { animation-delay: 0.07s; }
	main > *:nth-child(3) { animation-delay: 0.14s; }
	main > *:nth-child(4) { animation-delay: 0.21s; }
	main > *:nth-child(5) { animation-delay: 0.28s; }

    .waiting-state { text-align: center; padding: 20px 0; color: var(--text-muted); font-size: 13px; }
    .progress-bg   { background: rgba(255,255,255,0.06); border-radius: 999px; height: 5px; overflow: hidden; margin-top:10px; }
    .progress-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--cyan), var(--green)); }
    .progress-label{ font-size: 11px; color: var(--text-dim); margin-top: 5px; text-align: right; font-family:'JetBrains Mono',monospace; }


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
      <a class="nav-btn" href="/infrastructure">Infrastructure</a>
      <a class="nav-btn" href="/grafana">Grafana</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <button class="dark-toggle" id="darkToggle" title="Toggle dark mode" onclick="toggleDark()">🌙</button>
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
      <div class="live-dot"></div>
      <div>
        <div class="collection-text">Background Collector Running</div>
        <div class="collection-sub">Collecting every 10s · Linear regression on last {{ data_points }} readings · Alert cooldown: 5 minutes</div>
      </div>
    </div>
    <div style="font-size:11px; color:var(--text-dim); text-align:right; font-family:'JetBrains Mono',monospace;">
      Last updated<br><strong style="color:var(--text);">{{ timestamp }}</strong>
    </div>
  </div>

  {% if data_points < 3 %}
  <div class="box">
    <div class="box-title">⏳ Collecting Data</div>
    <div class="waiting-state">
      System needs at least 3 data points to run predictions.<br>
      Currently have <strong style="color:var(--cyan);">{{ data_points }}</strong> of 3 needed readings.<br>
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
  <span>Predictive Alert System &middot; PG Final Year Major Project</span>
  <span>Last analyzed: {{ timestamp }}</span>
</footer>

<script>
document.querySelectorAll('.predict-card').forEach(card => {
  card.addEventListener('mousemove', e => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const rX = ((y - cy) / cy) * -5;
    const rY = ((x - cx) / cx) * 5;
    card.style.transform =
      `translateY(-4px) perspective(500px) rotateX(${rX}deg) rotateY(${rY}deg)`;
    card.style.transition = 'transform 0.1s ease';
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
    card.style.transition = 'transform 0.4s cubic-bezier(0.34,1.56,0.64,1)';
  });
});
</script>

<script>
  // Dark mode toggle
  function toggleDark() {
    var html = document.documentElement;
    var btn  = document.getElementById('darkToggle');
    if (html.classList.contains('dark')) {
      html.classList.remove('dark');
      localStorage.setItem('devops-dark-mode', 'false');
      if (btn) btn.textContent = '🌙';
    } else {
      html.classList.add('dark');
      localStorage.setItem('devops-dark-mode', 'true');
      if (btn) btn.textContent = '☀️';
    }
  }
  // Set correct icon on load
  (function() {
    var btn = document.getElementById('darkToggle');
    if (btn && document.documentElement.classList.contains('dark')) {
      btn.textContent = '☀️';
    }
  })();
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────
#  ALERTS PAGE
# ─────────────────────────────────────────────────────────
ALERTS_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <script>if(localStorage.getItem('devops-dark-mode')==='true')document.documentElement.classList.add('dark');</script>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="20"/>
  <title>Alert History</title>
  <style>
    """ + SHARED_CSS + """

    main {
      flex: 1; max-width: 960px; margin: 0 auto;
      padding: 36px 24px;
      display: flex; flex-direction: column; gap: 20px;
      width: 100%;
    }

    .page-title h2 { font-size: 22px; font-weight: 800; color: var(--text); letter-spacing: -0.3px; }
    .page-title p  { font-size: 13px; color: var(--text-muted); margin-top: 5px; }

    /* trigger panel */
    .trigger-panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px; padding: 20px 24px;
    }

    .trigger-title { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
    .trigger-sub   { font-size: 12px; color: var(--text-dim); margin-bottom: 16px; }
    .trigger-btns  { display: flex; gap: 10px; flex-wrap: wrap; }
    .trigger-form  { display: inline; }

    .trigger-btn {
      padding: 10px 20px; border-radius: 10px;	
      font-size: 13px; font-weight: 700;
      cursor: pointer; border: 1px solid;
      transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
      letter-spacing: 0.3px;
      font-family: 'Inter', sans-serif;
      position: relative; overflow: hidden;
    }

    .trigger-btn:hover { transform: translateY(-3px) scale(1.04); }

    .trigger-btn:active {
  	transform: translateY(0px) scale(0.97);
  	transition: transform 0.1s ease;
     }

    .btn-error {
      background: #fef2f2; color: #dc2626;
      border-color: #fecaca;
    }
    .btn-error:hover { background: #fee2e2; box-shadow: 0 4px 14px var(--red-glow); }

    .btn-slow {
      background: #fffbeb; color: #b45309;
      border-color: #fde68a;
    }
    .btn-slow:hover { background: #fef3c7; box-shadow: 0 4px 14px var(--amber-glow); }


    .btn-load {
      background: #eff6ff; color: #1d4ed8;
      border-color: #bfdbfe;
    }
    .btn-load:hover { background: #dbeafe; box-shadow: 0 4px 14px var(--cyan-glow); }

    .btn-test {
      background: #faf5ff; color: #7c3aed;
      border-color: #e9d5ff;
    }
    .btn-test:hover { background: #ede9fe; box-shadow: 0 4px 14px rgba(168,85,247,0.2); }

    /* alertmanager status */
    .am-status {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 18px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 13px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .am-left { display: flex; align-items: center; gap: 10px; }
    .am-left strong { color: var(--text); }
    .am-left a { color: var(--cyan); font-size: 12px; text-decoration: none; }
    .am-left a:hover { text-decoration: underline; }

    /* alert rows */
    .alert-row {
      display: flex; align-items: flex-start;
      gap: 14px; padding: 14px 0;
      border-bottom: 1px solid var(--border);
      animation: slideInLeft 0.35s ease both;
    }
    .alert-row:last-child { border-bottom: none; }

    .alert-row:nth-child(1) { animation-delay: 0.05s; }
    .alert-row:nth-child(2) { animation-delay: 0.10s; }
    .alert-row:nth-child(3) { animation-delay: 0.15s; }
    .alert-row:nth-child(4) { animation-delay: 0.20s; }
    .alert-row:nth-child(5) { animation-delay: 0.25s; }

    .sev-dot {
      width: 8px; height: 8px; border-radius: 50%;
      flex-shrink: 0; margin-top: 5px;
    }
    .dot-critical { background: var(--red);   box-shadow: 0 0 6px var(--red-glow); }
    .dot-warning  { background: var(--amber); box-shadow: 0 0 6px var(--amber-glow); }
    .dot-info     { background: var(--cyan);  box-shadow: 0 0 6px var(--cyan-glow); }

    .alert-body { flex: 1; }
    .alert-name { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 3px; }
    .alert-desc { font-size: 12px; color: var(--text-muted); line-height: 1.5; }

    .alert-meta { display: flex; gap: 8px; margin-top: 7px; flex-wrap: wrap; }

    .meta-tag {
      font-size: 10px; font-weight: 600;
      padding: 2px 10px; border-radius: 999px;
      border: 1px solid;
    }

    .tag-source   { background: var(--surface-2); color: var(--text-dim); border-color: var(--border); }
    .tag-critical { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
    .tag-warning  { background: #fffbeb; color: #b45309; border-color: #fde68a; }
    .tag-info     { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }

    .alert-time {
      font-family: 'DM Mono', monospace;
      font-size: 10px; color: var(--text-dim);
      flex-shrink: 0; padding-top: 3px; white-space: nowrap;
    }

    @keyframes fadeUp {
  	from { opacity: 0; transform: translateY(14px); }
  	to   { opacity: 1; transform: translateY(0); }
    }
    main > * {
  	animation: fadeUp 0.4s ease both;
    }
	main > *:nth-child(1) { animation-delay: 0s; }
	main > *:nth-child(2) { animation-delay: 0.07s; }
	main > *:nth-child(3) { animation-delay: 0.14s; }
	main > *:nth-child(4) { animation-delay: 0.21s; }
	main > *:nth-child(5) { animation-delay: 0.28s; }

    .empty-state { text-align: center; padding: 48px 0; color: var(--text-dim); }
    .empty-icon  { font-size: 44px; margin-bottom: 14px; opacity: 0.3; }
    .empty-text  { font-size: 14px; color: var(--text-muted); }
    .empty-sub   { font-size: 12px; margin-top: 6px; }

    @keyframes btnPulse {
  	0%   { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); transform: translateY(-3px) scale(1.04); }
  	70%  { box-shadow: 0 0 0 8px rgba(239,68,68,0); transform: translateY(-3px) scale(1.04); }
  	100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); transform: translateY(-3px) scale(1.04); }
    }
    .btn-error:hover { animation: btnPulse 1s ease infinite; }

    @keyframes btnPulseAmber {
 	 0%   { box-shadow: 0 0 0 0 rgba(245,158,11,0.4); transform: translateY(-3px) scale(1.04); }
  	70%  { box-shadow: 0 0 0 8px rgba(245,158,11,0); transform: translateY(-3px) scale(1.04); }
  	100% { box-shadow: 0 0 0 0 rgba(245,158,11,0); transform: translateY(-3px) scale(1.04); }
    }
    .btn-slow:hover { animation: btnPulseAmber 1s ease infinite; }

    @keyframes btnPulseCyan {
 	 0%   { box-shadow: 0 0 0 0 rgba(14,165,233,0.4); transform: translateY(-3px) scale(1.04); }
 	 70%  { box-shadow: 0 0 0 8px rgba(14,165,233,0); transform: translateY(-3px) scale(1.04); }
 	 100% { box-shadow: 0 0 0 0 rgba(14,165,233,0); transform: translateY(-3px) scale(1.04); }
    }
    .btn-load:hover { animation: btnPulseCyan 1s ease infinite; }

    @keyframes emptyPulse {
  	0%, 100% { box-shadow: 0 0 0 0 rgba(16,185,129,0.3); }
 	50%       { box-shadow: 0 0 0 12px rgba(16,185,129,0); }
    }

    @keyframes slideInLeft {
  	from { opacity: 0; transform: translateX(-16px); }
  	to   { opacity: 1; transform: translateX(0); }
    }


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
      <a class="nav-btn" href="/infrastructure">Infrastructure</a>
      <a class="nav-btn" href="/grafana">Grafana</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <button class="dark-toggle" id="darkToggle" title="Toggle dark mode" onclick="toggleDark()">🌙</button>
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
        <strong>Alertmanager</strong> &middot; port 9093 &middot;
        <a href="http://localhost:9093" target="_blank">Open UI ↗</a>
      </div>
    </div>
    <div style="font-size:11px; color:var(--text-dim); font-family:'JetBrains Mono',monospace;">
      5 alert rules active &middot; Prometheus evaluating every 15s
    </div>
  </div>

  <div class="trigger-panel">
    <div class="trigger-title">⚡ Trigger Test Scenarios</div>
    <div class="trigger-sub">Simulate incidents — results appear instantly in the alert log below.</div>
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
    <div style="font-size:12px; color:var(--text-dim); margin-bottom:14px; font-family:'JetBrains Mono',monospace;">
      {{ alerts|length }} alert(s) &middot; newest first
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
       <div style="
    		width: 64px; height: 64px; border-radius: 50%;
    		background: linear-gradient(135deg, #f0fdf4, #dcfce7);
    		border: 2px solid #86efac;
    		display: flex; align-items: center; justify-content: center;
    		font-size: 28px; margin: 0 auto 16px;
    		animation: emptyPulse 2s ease infinite;
  		">🟢</div>
      <div class="empty-text" style="font-weight:600; color:#475569;">All systems healthy</div>
      <div class="empty-sub">No alerts fired · Use the trigger buttons above to simulate incidents</div>
    </div>
    {% endif %}

  </div>

</main>

<footer>
  <span>Alert History &middot; PG Final Year Major Project</span>
  <span>Last refreshed: {{ current_time }}</span>
</footer>

<script>
  // Dark mode toggle
  function toggleDark() {
    var html = document.documentElement;
    var btn  = document.getElementById('darkToggle');
    if (html.classList.contains('dark')) {
      html.classList.remove('dark');
      localStorage.setItem('devops-dark-mode', 'false');
      if (btn) btn.textContent = '🌙';
    } else {
      html.classList.add('dark');
      localStorage.setItem('devops-dark-mode', 'true');
      if (btn) btn.textContent = '☀️';
    }
  }
  // Set correct icon on load
  (function() {
    var btn = document.getElementById('darkToggle');
    if (btn && document.documentElement.classList.contains('dark')) {
      btn.textContent = '☀️';
    }
  })();
</script>

</body>
</html>
"""


GRAFANA_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <script>if(localStorage.getItem('devops-dark-mode')==='true')document.documentElement.classList.add('dark');</script>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Grafana Dashboards</title>
  <style>
    """ + SHARED_CSS + """

    main {
      flex: 1; max-width: 1200px; margin: 0 auto;
      padding: 36px 24px;
      display: flex; flex-direction: column; gap: 20px;
      width: 100%;
    }

    .page-title h2 { font-size: 22px; font-weight: 800; color: var(--text); letter-spacing: -0.3px; }
    .page-title p  { font-size: 13px; color: var(--text-muted); margin-top: 5px; }

    .tab-bar {
      display: flex; gap: 6px; flex-wrap: wrap;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px; padding: 8px;
    }

    .tab-btn {
      padding: 8px 18px; border-radius: 8px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--text-muted);
      font-size: 13px; font-weight: 500;
      cursor: pointer; font-family: 'Inter', sans-serif;
      transition: all 0.18s; letter-spacing: 0.1px;
      white-space: nowrap;
    }

    .tab-btn:hover {
      background: var(--surface-2);
      border-color: var(--border-2);
      color: var(--text);
    }

    .tab-btn.active {
      background: var(--cyan-dim);
      border-color: rgba(14,165,233,0.3);
      color: var(--cyan);
      font-weight: 600;
    }

    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    .iframe-wrap {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.03);
    }

    .iframe-wrap iframe {
      width: 100%; height: 620px;
      border: none; display: block;
    }

    .grafana-note {
      font-size: 12px; color: var(--text-dim);
      text-align: center;
      font-family: 'DM Mono', monospace;
    }
    .grafana-note a { color: var(--cyan); text-decoration: none; }
    .grafana-note a:hover { text-decoration: underline; }

    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(14px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    main > * { animation: fadeUp 0.4s ease both; }
    main > *:nth-child(1) { animation-delay: 0s;    }
    main > *:nth-child(2) { animation-delay: 0.07s; }
    main > *:nth-child(3) { animation-delay: 0.14s; }
    main > *:nth-child(4) { animation-delay: 0.21s; }
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
      <a class="nav-btn" href="/alerts">Alerts</a>
      <a class="nav-btn" href="/infrastructure">Infrastructure</a>
      <a class="nav-btn active" href="/grafana">Grafana</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <button class="dark-toggle" id="darkToggle" title="Toggle dark mode" onclick="toggleDark()">🌙</button>
    <div class="time-box">{{ current_time }}</div>
  </div>
</header>

<main>
  <div class="page-title">
    <h2>📊 Grafana Dashboards</h2>
    <p>All 5 live dashboards embedded directly — data refreshes every 10 seconds from Prometheus.</p>
  </div>

  <div class="tab-bar">
    <button class="tab-btn active" onclick="showTab('app-perf', this)">📈 Application Performance</button>
    <button class="tab-btn" onclick="showTab('load-balancer', this)">⚖️ Load Balancer</button>
    <button class="tab-btn" onclick="showTab('performance', this)">⏱️ Performance</button>
    <button class="tab-btn" onclick="showTab('system', this)">🖥️ System Resources</button>
    <button class="tab-btn" onclick="showTab('traffic', this)">🚦 Traffic Analysis</button>
  </div>

  <div id="tab-app-perf" class="tab-panel active">
    <div class="iframe-wrap">
      <iframe src="http://localhost:3000/d/adcs6xf/application-performance-dashboard?orgId=1&kiosk=tv&theme=dark&refresh=10s&from=now-30m&to=now"></iframe>
    </div>
  </div>

  <div id="tab-load-balancer" class="tab-panel">
    <div class="iframe-wrap">
      <iframe src="http://localhost:3000/d/adg9vlj/load-balancer-dashboard?orgId=1&kiosk=tv&theme=dark&refresh=10s&from=now-15m&to=now"></iframe>
    </div>
  </div>

  <div id="tab-performance" class="tab-panel">
    <div class="iframe-wrap">
      <iframe src="http://localhost:3000/d/adq8njc/performance-dashboard?orgId=1&kiosk=tv&theme=dark&refresh=10s&from=now-6h&to=now"></iframe>
    </div>
  </div>

  <div id="tab-system" class="tab-panel">
    <div class="iframe-wrap">
      <iframe src="http://localhost:3000/d/adnswq7/system-resources-dashboard?orgId=1&kiosk=tv&theme=dark&refresh=10s&from=now-6h&to=now"></iframe>
    </div>
  </div>

  <div id="tab-traffic" class="tab-panel">
    <div class="iframe-wrap">
      <iframe src="http://localhost:3000/d/adfwrdr/traffic-analysis-dashboard?orgId=1&kiosk=tv&theme=dark&refresh=10s&from=now-15m&to=now"></iframe>
    </div>
  </div>

  <div class="grafana-note">
    📊 Powered by Grafana · Full controls at
    <a href="http://localhost:3000" target="_blank">localhost:3000 ↗</a>
    &middot; Anonymous viewer access enabled
  </div>

</main>

<footer>
  <span>Grafana Dashboards &middot; PG Final Year Major Project</span>
  <span>Last loaded: {{ current_time }}</span>
</footer>

<script>
function showTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}
</script>

<script>
  // Dark mode toggle
  function toggleDark() {
    var html = document.documentElement;
    var btn  = document.getElementById('darkToggle');
    if (html.classList.contains('dark')) {
      html.classList.remove('dark');
      localStorage.setItem('devops-dark-mode', 'false');
      if (btn) btn.textContent = '🌙';
    } else {
      html.classList.add('dark');
      localStorage.setItem('devops-dark-mode', 'true');
      if (btn) btn.textContent = '☀️';
    }
  }
  // Set correct icon on load
  (function() {
    var btn = document.getElementById('darkToggle');
    if (btn && document.documentElement.classList.contains('dark')) {
      btn.textContent = '☀️';
    }
  })();
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────
#  HELPERS + ROUTES  (unchanged logic, identical to original)
# ─────────────────────────────────────────────────────────

def _fetch_req_rate():
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
        return None

def _calculate_health_score(metrics):
    cpu        = metrics.get('cpu', 0.0)
    memory     = metrics.get('memory', 0.0)
    latency    = metrics.get('latency', 0.0)
    error_rate = metrics.get('error_rate', 0.0)

    cpu_score     = 100 - min(100, (cpu / 80) * 100)
    memory_score  = 100 - min(100, (memory / 500) * 100)
    latency_score = 100 - min(100, (latency / 0.5) * 100)
    error_score   = 100 - min(100, (error_rate / 0.05) * 100)
    uptime_score  = 100.0

    score = round(
        cpu_score     * 0.25 +
        memory_score  * 0.20 +
        latency_score * 0.25 +
        error_score   * 0.15 +
        uptime_score  * 0.15,
        1
    )

    if score >= 80:
        color = '#10b981'
    elif score >= 60:
        color = '#f59e0b'
    else:
        color = '#ef4444'

    return score, color


@app.route('/')
@REQUEST_TIME.time()
def home():
    global request_value
    start = time.time()
    REQUEST_COUNT.labels(endpoint='/').inc()
    request_value += 1

    error_color = '#dc2626' if error_value > 0 else '#0f172a'
    req_rate    = _fetch_req_rate()

    try:
        from analyzer import fetch_all_metrics
        _hs_metrics = fetch_all_metrics()
        initial_score, initial_color = _calculate_health_score(_hs_metrics)
    except Exception:
        initial_score, initial_color = None, '#94a3b8'

    res = render_template_string(
        HTML_PAGE,
        count            = request_value,
        errors           = error_value,
        current_time     = datetime.now().strftime("%H:%M:%S"),
        uptime           = get_uptime(),
        refresh_interval = random.randint(8, 15),
        error_color      = error_color,
        req_rate         = req_rate,
 	initial_score = initial_score,
	initial_color = initial_color,
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
    toast = session.pop('toast', None)
    return render_template_string(
        ALERTS_PAGE,
        alerts       = alert_history,
        current_time = datetime.now().strftime("%H:%M:%S"),
        toast        = toast,
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

    session['toast'] = toast
    return redirect(url_for('alerts'))


@app.route('/cpu-stress')
def cpu_stress():
    import math
    total_primes = 0
    for _ in range(3):
        limit = 500000
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
    big_list = ['x' * 1000 for _ in range(50000)]
    time.sleep(2)
    result = len(big_list)
    del big_list
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

@app.route('/api/health-score')
def api_health_score():
    try:
        from analyzer import fetch_all_metrics
        metrics = fetch_all_metrics()
        score, color = _calculate_health_score(metrics)
        return {
            'score':      score,
            'color':      color,
            'cpu':        metrics.get('cpu', 0.0),
            'memory':     metrics.get('memory', 0.0),
            'latency':    metrics.get('latency', 0.0),
            'error_rate': metrics.get('error_rate', 0.0),
        }
    except Exception:
        return {'score': None, 'color': '#94a3b8'}

INFRA_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <script>if(localStorage.getItem('devops-dark-mode')==='true')document.documentElement.classList.add('dark');</script>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta http-equiv="refresh" content="15"/>
  <title>Infrastructure Status</title>
  <style>
    """ + SHARED_CSS + """

    main {
      flex: 1; max-width: 960px; margin: 0 auto;
      padding: 36px 24px;
      display: flex; flex-direction: column; gap: 20px;
      width: 100%;
    }

    .page-title h2 { font-size: 22px; font-weight: 800; color: var(--text); letter-spacing: -0.3px; }
    .page-title p  { font-size: 13px; color: var(--text-muted); margin-top: 5px; }

    .infra-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
    }

    .infra-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px; padding: 22px 20px;
      position: relative; overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      transition: box-shadow 0.25s, transform 0.25s, border-color 0.2s;
      opacity: 0;
      animation: slideCard 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }

    .infra-card:nth-child(1) { animation-delay: 0.05s; }
    .infra-card:nth-child(2) { animation-delay: 0.12s; }
    .infra-card:nth-child(3) { animation-delay: 0.19s; }
    .infra-card:nth-child(4) { animation-delay: 0.26s; }
    .infra-card:nth-child(5) { animation-delay: 0.33s; }
    .infra-card:nth-child(6) { animation-delay: 0.40s; }

    @keyframes slideCard {
      from { opacity: 0; transform: translateY(28px) scale(0.97); }
      to   { opacity: 1; transform: translateY(0)   scale(1);    }
    }

    .infra-card::before {
      content: ''; position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      border-radius: 14px 14px 0 0;
    }

    .infra-card.up::before   { background: linear-gradient(90deg, #10b981, #34d399); }
    .infra-card.down::before { background: linear-gradient(90deg, #ef4444, #f87171); }

    .infra-card:hover { transform: translateY(-5px); }
    .infra-card.up:hover   { border-color: #86efac; box-shadow: 0 10px 28px rgba(16,185,129,0.15); }
    .infra-card.down:hover { border-color: #fca5a5; box-shadow: 0 10px 28px rgba(239,68,68,0.15); }

    .infra-header {
      display: flex; align-items: center;
      justify-content: space-between; margin-bottom: 16px;
    }

    .infra-icon { font-size: 28px; }

    .status-badge {
      font-size: 11px; font-weight: 700;
      padding: 4px 12px; border-radius: 999px;
      text-transform: uppercase; letter-spacing: 0.8px;
      border: 1px solid;
    }
    .badge-up   { background: #f0fdf4; color: #15803d; border-color: #86efac; }
    .badge-down { background: #fef2f2; color: #dc2626; border-color: #fca5a5; }

    .infra-name {
      font-size: 15px; font-weight: 700; color: var(--text);
      margin-bottom: 4px;
    }

    .infra-port {
      font-family: 'DM Mono', monospace;
      font-size: 11px; color: var(--text-dim);
      margin-bottom: 14px;
    }

    .infra-row {
      display: flex; align-items: center;
      justify-content: space-between;
      padding: 7px 0; border-bottom: 1px solid var(--border);
      font-size: 12px;
    }
    .infra-row:last-child { border-bottom: none; padding-bottom: 0; }

    .infra-row-label { color: var(--text-muted); }
    .infra-row-val   { font-family: 'DM Mono', monospace; font-weight: 600; color: var(--text); }
    .infra-row-val.val-up   { color: var(--green); }
    .infra-row-val.val-down { color: var(--red); }

    .summary-bar {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px; padding: 14px 22px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 13px;
    }
    .summary-left { display: flex; align-items: center; gap: 10px; }
    .summary-count { font-size: 22px; font-weight: 800; color: var(--text); }
    .summary-label { font-size: 12px; color: var(--text-dim); }

    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(14px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    main > * { animation: fadeUp 0.4s ease both; }
    main > *:nth-child(1) { animation-delay: 0s;    }
    main > *:nth-child(2) { animation-delay: 0.07s; }
    main > *:nth-child(3) { animation-delay: 0.14s; }
    main > *:nth-child(4) { animation-delay: 0.21s; }
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
      <a class="nav-btn" href="/alerts">Alerts</a>
      <a class="nav-btn active" href="/infrastructure">Infrastructure</a>
      <a class="nav-btn" href="/grafana">Grafana</a>
    </div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <button class="dark-toggle" id="darkToggle" title="Toggle dark mode" onclick="toggleDark()">🌙</button>
    <div class="time-box">{{ current_time }}</div>
  </div>
</header>

<main>
  <div class="page-title">
    <h2>🖥️ Infrastructure Status</h2>
    <p>Live health check of all services — pinged on every page load with a 2-second timeout.</p>
  </div>

  <div class="summary-bar">
    <div class="summary-left">
      <div class="live-dot"></div>
      <div>
        <div style="font-weight:700; color:var(--text); font-size:14px;">
          {{ up_count }} / {{ total_count }} Services Online
        </div>
        <div style="font-size:11px; color:var(--text-dim); margin-top:2px; font-family:'DM Mono',monospace;">
          Checked at {{ current_time }} · auto-refresh every 15s
        </div>
      </div>
    </div>
    {% if up_count == total_count %}
    <span style="font-size:12px; font-weight:700; color:var(--green); background:#f0fdf4; border:1px solid #86efac; padding:4px 14px; border-radius:999px;">
      ✅ ALL SYSTEMS GO
    </span>
    {% else %}
    <span style="font-size:12px; font-weight:700; color:#dc2626; background:#fef2f2; border:1px solid #fca5a5; padding:4px 14px; border-radius:999px;">
      ⚠️ {{ total_count - up_count }} SERVICE(S) DOWN
    </span>
    {% endif %}
  </div>

  <div class="infra-grid">
    {% for svc in services %}
    <div class="infra-card {{ 'up' if svc.up else 'down' }}">
      <div class="infra-header">
        <div class="infra-icon">{{ svc.icon }}</div>
        <span class="status-badge {{ 'badge-up' if svc.up else 'badge-down' }}">
          {{ '● UP' if svc.up else '● DOWN' }}
        </span>
      </div>
      <div class="infra-name">{{ svc.name }}</div>
      <div class="infra-port">{{ svc.url }}</div>

      <div class="infra-row">
        <span class="infra-row-label">Status</span>
        <span class="infra-row-val {{ 'val-up' if svc.up else 'val-down' }}">
          {{ 'Reachable' if svc.up else 'Unreachable' }}
        </span>
      </div>
      <div class="infra-row">
        <span class="infra-row-label">Response Time</span>
        <span class="infra-row-val">
          {% if svc.response_ms is not none %}{{ svc.response_ms }} ms{% else %}— ms{% endif %}
        </span>
      </div>
      <div class="infra-row">
        <span class="infra-row-label">Role</span>
        <span class="infra-row-val" style="color:var(--text-muted); font-family:'Inter',sans-serif;">{{ svc.role }}</span>
      </div>
    </div>
    {% endfor %}
  </div>

  </div>

  <div class="box" style="padding: 28px 28px 24px;">
    <div class="box-title">🗺️ Architecture Topology Diagram</div>
    <div style="overflow-x: auto;">
      <svg viewBox="0 0 900 420" xmlns="http://www.w3.org/2000/svg"
           style="width:100%; max-width:900px; display:block; margin:0 auto; font-family:'Inter',sans-serif;">

        <!-- ── Arrowhead marker ── -->
        <defs>
          <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#94a3b8"/>
          </marker>
          <marker id="arr-blue" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#0ea5e9"/>
          </marker>
          <marker id="arr-green" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#10b981"/>
          </marker>
          <marker id="arr-amber" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#f59e0b"/>
          </marker>
        </defs>

        <!-- ══ ROW 1 — User ══ -->
        <!-- User/Browser node -->
        <rect x="370" y="10" width="160" height="52" rx="12" fill="#eff6ff" stroke="#bfdbfe" stroke-width="1.5"/>
        <text x="450" y="31" text-anchor="middle" font-size="13" font-weight="700" fill="#1d4ed8">👤 User / Browser</text>
        <text x="450" y="50" text-anchor="middle" font-size="10" fill="#64748b">HTTP Request</text>

        <!-- User → Nginx arrow -->
        <line x1="450" y1="62" x2="450" y2="100" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4,3" marker-end="url(#arr)"/>
        <rect x="400" y="74" width="100" height="16" rx="4" fill="white" opacity="0.9"/>
        <text x="450" y="86" text-anchor="middle" font-size="10" fill="#64748b" font-weight="600">HTTP :8080</text>

        <!-- ══ ROW 2 — Nginx ══ -->
        <rect x="330" y="100" width="240" height="56" rx="12" fill="#f0fdf4" stroke="#86efac" stroke-width="1.5"/>
        <text x="450" y="123" text-anchor="middle" font-size="13" font-weight="700" fill="#15803d">⚖️ Nginx Load Balancer</text>
        <text x="450" y="143" text-anchor="middle" font-size="10" fill="#64748b">Least Connections · port 8080</text>

        <!-- Nginx → Flask Primary (left arrow) -->
        <path d="M370,156 L220,200" stroke="#0ea5e9" stroke-width="1.5" fill="none" marker-end="url(#arr-blue)"/>
        <rect x="255" y="164" width="90" height="16" rx="4" fill="white" opacity="0.9"/>
        <text x="300" y="176" text-anchor="middle" font-size="10" fill="#0369a1" font-weight="600">weight=2 (67%)</text>

        <!-- Nginx → Flask Backup (right arrow) -->
        <path d="M530,156 L680,200" stroke="#94a3b8" stroke-width="1.5" fill="none" marker-end="url(#arr)"/>
        <rect x="558" y="164" width="90" height="16" rx="4" fill="white" opacity="0.9"/>
        <text x="603" y="176" text-anchor="middle" font-size="10" fill="#64748b" font-weight="600">weight=1 (33%)</text>

        <!-- ══ ROW 3 — Flask Primary ══ -->
        <rect x="80" y="200" width="200" height="60" rx="12" fill="#eff6ff" stroke="#c7d2fe" stroke-width="1.5"/>
        <text x="180" y="224" text-anchor="middle" font-size="13" font-weight="700" fill="#4338ca">🐍 Flask Primary</text>
        <text x="180" y="244" text-anchor="middle" font-size="10" fill="#64748b">Dashboard UI · port 5000</text>
        <text x="180" y="257" text-anchor="middle" font-size="9" fill="#94a3b8" font-family="DM Mono, monospace">app.py</text>

        <!-- Flask Backup -->
        <rect x="620" y="200" width="200" height="60" rx="12" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1.5"/>
        <text x="720" y="224" text-anchor="middle" font-size="13" font-weight="700" fill="#475569">🔄 Flask Backup</text>
        <text x="720" y="244" text-anchor="middle" font-size="10" fill="#64748b">Standby · port 5002</text>
        <text x="720" y="257" text-anchor="middle" font-size="9" fill="#94a3b8" font-family="DM Mono, monospace">app2.py</text>

        <!-- Flask Primary → Prometheus (scrape, downward) -->
        <line x1="180" y1="260" x2="180" y2="310" stroke="#10b981" stroke-width="1.5" stroke-dasharray="4,3" marker-end="url(#arr-green)"/>
        <rect x="118" y="276" width="122" height="16" rx="4" fill="white" opacity="0.9"/>
        <text x="180" y="288" text-anchor="middle" font-size="10" fill="#15803d" font-weight="600">scrape /metrics 2s</text>

        <!-- ══ ROW 4 — Prometheus ══ -->
        <rect x="80" y="310" width="200" height="56" rx="12" fill="#fff7ed" stroke="#fed7aa" stroke-width="1.5"/>
        <text x="180" y="333" text-anchor="middle" font-size="13" font-weight="700" fill="#c2410c">📊 Prometheus</text>
        <text x="180" y="353" text-anchor="middle" font-size="10" fill="#64748b">Time-series DB · port 9090</text>
        <text x="180" y="364" text-anchor="middle" font-size="9" fill="#94a3b8" font-family="DM Mono, monospace">prometheus.yml · alert.rules.yml</text>

        <!-- Prometheus → Grafana (right arrow) -->
        <path d="M280,338 L380,338" stroke="#10b981" stroke-width="1.5" fill="none" marker-end="url(#arr-green)"/>
        <rect x="285" y="326" width="90" height="16" rx="4" fill="white" opacity="0.9"/>
        <text x="330" y="338" text-anchor="middle" font-size="10" fill="#15803d" font-weight="600">PromQL queries</text>

        <!-- Grafana -->
        <rect x="380" y="310" width="180" height="56" rx="12" fill="#fdf4ff" stroke="#e9d5ff" stroke-width="1.5"/>
        <text x="470" y="333" text-anchor="middle" font-size="13" font-weight="700" fill="#7c3aed">📈 Grafana</text>
        <text x="470" y="353" text-anchor="middle" font-size="10" fill="#64748b">5 Dashboards · port 3000</text>
        <text x="470" y="364" text-anchor="middle" font-size="9" fill="#94a3b8" font-family="DM Mono, monospace">dark theme · 5s refresh</text>

        <!-- Prometheus → Alertmanager (right arrow further) -->
        <path d="M280,356 L610,370" stroke="#f59e0b" stroke-width="1.5" fill="none" marker-end="url(#arr-amber)"/>
        <rect x="390" y="356" width="110" height="16" rx="4" fill="white" opacity="0.9"/>
        <text x="445" y="368" text-anchor="middle" font-size="10" fill="#b45309" font-weight="600">firing alerts</text>

        <!-- Alertmanager -->
        <rect x="610" y="310" width="210" height="56" rx="12" fill="#fffbeb" stroke="#fde68a" stroke-width="1.5"/>
        <text x="715" y="333" text-anchor="middle" font-size="13" font-weight="700" fill="#b45309">🔔 Alertmanager</text>
        <text x="715" y="353" text-anchor="middle" font-size="10" fill="#64748b">Alert routing · port 9093</text>
        <text x="715" y="364" text-anchor="middle" font-size="9" fill="#94a3b8" font-family="DM Mono, monospace">alertmanager.yml</text>

        <!-- Alertmanager → Email (downward) -->
        <line x1="715" y1="366" x2="715" y2="400" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4,3" marker-end="url(#arr-amber)"/>
        <rect x="655" y="380" width="120" height="16" rx="4" fill="white" opacity="0.9"/>
        <text x="715" y="392" text-anchor="middle" font-size="10" fill="#b45309" font-weight="600">SMTP :587 → Yahoo</text>

        <!-- Email icon node -->
        <rect x="655" y="400" width="120" height="16" rx="6" fill="#fffbeb" stroke="#fde68a" stroke-width="1"/>
        <text x="715" y="412" text-anchor="middle" font-size="10" fill="#b45309" font-weight="700">📧 subhash6609@yahoo.com</text>

      </svg>
    </div>
    <div style="display:flex; flex-wrap:wrap; gap:20px; margin-top:18px; padding-top:16px; border-top:1px solid var(--border); font-size:11px;">
      <span style="display:flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:24px;height:2px;background:#0ea5e9;border-radius:1px;"></span>
        <span style="color:var(--text-muted);">Traffic flow (HTTP proxy)</span>
      </span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:24px;height:2px;background:#10b981;border-radius:1px;border-bottom:2px dashed #10b981;background:none;border-top:none;border-left:none;border-right:none;"></span>
        <span style="color:var(--text-muted);">Prometheus scrape / PromQL</span>
      </span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:24px;height:2px;background:#f59e0b;border-radius:1px;"></span>
        <span style="color:var(--text-muted);">Alert routing (firing → email)</span>
      </span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:24px;height:2px;background:#94a3b8;border-radius:1px;"></span>
        <span style="color:var(--text-muted);">Backup / fallback path</span>
      </span>
    </div>
  </div>
</main>

<footer>
  <span>Infrastructure Status &middot; PG Final Year Major Project</span>
</main>

<footer>
  <span>Infrastructure Status &middot; PG Final Year Major Project</span>
  <span>Last checked: {{ current_time }}</span>
</footer>

<script>
document.querySelectorAll('.infra-card').forEach(card => {
  card.addEventListener('mousemove', e => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const rX = ((y - rect.height/2) / rect.height) * -6;
    const rY = ((x - rect.width/2)  / rect.width)  *  6;
    card.style.transform =
      `translateY(-5px) perspective(500px) rotateX(${rX}deg) rotateY(${rY}deg)`;
    card.style.transition = 'transform 0.1s ease';
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
    card.style.transition = 'transform 0.45s cubic-bezier(0.34,1.56,0.64,1)';
  });
});
</script>

<script>
  // Dark mode toggle
  function toggleDark() {
    var html = document.documentElement;
    var btn  = document.getElementById('darkToggle');
    if (html.classList.contains('dark')) {
      html.classList.remove('dark');
      localStorage.setItem('devops-dark-mode', 'false');
      if (btn) btn.textContent = '🌙';
    } else {
      html.classList.add('dark');
      localStorage.setItem('devops-dark-mode', 'true');
      if (btn) btn.textContent = '☀️';
    }
  }
  // Set correct icon on load
  (function() {
    var btn = document.getElementById('darkToggle');
    if (btn && document.documentElement.classList.contains('dark')) {
      btn.textContent = '☀️';
    }
  })();
</script>

</body>
</html>
"""


def _check_service(url, timeout=2):
    """Ping a service URL. Returns (is_up, response_ms)."""
    try:
        t0  = time.time()
        res = requests.get(url, timeout=timeout)
        ms  = round((time.time() - t0) * 1000)
        return res.status_code < 500, ms
    except Exception:
        return False, None


@app.route('/infrastructure')
def infrastructure():
    services_config = [
        {'name': 'Flask Primary',  'url': 'http://localhost:5000/health', 'display': 'localhost:5000', 'icon': '🐍', 'role': 'Monitored app + Dashboard UI'},
        {'name': 'Flask Backup',   'url': 'http://localhost:5002/health', 'display': 'localhost:5002', 'icon': '🔄', 'role': 'High-availability backup server'},
        {'name': 'Prometheus',     'url': 'http://localhost:9090/-/healthy','display': 'localhost:9090','icon': '📊', 'role': 'Metrics collection & alert rules'},
        {'name': 'Grafana',        'url': 'http://localhost:3000/api/health','display': 'localhost:3000','icon': '📈', 'role': '5 live dashboards & visualization'},
        {'name': 'Alertmanager',   'url': 'http://localhost:9093/-/healthy','display': 'localhost:9093','icon': '🔔', 'role': 'Alert routing & email delivery'},
        {'name': 'Nginx LB',       'url': 'http://localhost:8080/nginx-health','display': 'localhost:8080','icon': '⚖️', 'role': 'Least-connections load balancer'},
    ]

    services = []
    for svc in services_config:
        up, ms = _check_service(svc['url'])
        services.append({
            'name':        svc['name'],
            'url':         svc['display'],
            'icon':        svc['icon'],
            'role':        svc['role'],
            'up':          up,
            'response_ms': ms,
        })

    up_count = sum(1 for s in services if s['up'])

    return render_template_string(
        INFRA_PAGE,
        services     = services,
        up_count     = up_count,
        total_count  = len(services),
        current_time = datetime.now().strftime("%H:%M:%S"),
    )


@app.route('/grafana')
def grafana():
    return render_template_string(
        GRAFANA_PAGE,
        current_time = datetime.now().strftime("%H:%M:%S"),
    )


@app.route('/sustained-errors')
def sustained_errors():
    """Fires 20 errors with a short delay between each — produces a visible
    rate spike in Grafana's rate(app_errors_total[1m]) panel."""
    global error_value
    for _ in range(20):
        REQUEST_COUNT.labels(endpoint='/error').inc()
        ERROR_COUNT.labels(endpoint='/error').inc()
        error_value += 1
        time.sleep(0.3)
    return {'status': 'done', 'errors_fired': 20}


def _poll_alertmanager():
    """Background thread — polls Alertmanager API every 30 seconds and
    pushes any currently-firing alerts into the in-memory alert_history."""
    import requests as _req
    while True:
        try:
            res = _req.get(
                'http://localhost:9093/api/v2/alerts',
                params={'active': 'true', 'silenced': 'false'},
                timeout=3
            )
            if res.status_code == 200:
                for a in res.json():
                    name     = a.get('labels', {}).get('alertname', 'Unknown')
                    severity = a.get('labels', {}).get('severity', 'warning')
                    desc     = a.get('annotations', {}).get('description', 'Alert is firing.')
                    if not any(h['name'] == name and h['source'] == 'Alertmanager'
                               for h in alert_history[:5]):
                        add_alert('Alertmanager', name, severity, desc)
        except Exception:
            pass
        time.sleep(30)


if __name__ == '__main__':
    t = threading.Thread(target=start_prediction_loop, daemon=True)
    t.start()
    t2 = threading.Thread(target=_poll_alertmanager, daemon=True)
    t2.start()
    print("[app] started — predictor + alertmanager poller running in background")
    app.run(host='0.0.0.0', port=5000, debug=False)