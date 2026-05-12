from flask import Flask, render_template_string
from prometheus_client import Counter, Summary, generate_latest, CONTENT_TYPE_LATEST
from flask import Flask, request
from prometheus_client import Histogram
from datetime import datetime
import time

app = Flask(__name__)

# Prometheus Metrics
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

request_value = 0

# Light UI Dashboard
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>DevOps Monitoring Dashboard</title>
    <style>
    body {
        font-family: 'Segoe UI', sans-serif;
        background: linear-gradient(135deg, #dbeafe, #eef2ff);
        margin: 0;
        color: #0f172a;
    }

    .main {
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    h1 {
        text-align: center;
        color: #0369a1;
        margin-bottom: 20px;
    }

    .dashboard {
        display: flex;
        justify-content: center;
        gap: 25px;
        flex-wrap: wrap;
    }

    .card {
        background: white;
        padding: 25px;
        border-radius: 14px;
        width: 220px;
        text-align: center;
        box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        border: 1px solid #e2e8f0;
        transition: 0.2s;
    }

    /* 🔥 Improved hover */
    .card:hover {
        transform: translateY(-6px) scale(1.02);
    }

    /* 🔥 STATUS highlight */
    .status-card {
        border: 2px solid #22c55e;
        box-shadow: 0 10px 30px rgba(34,197,94,0.25);
    }

    .label {
        font-size: 13px;
        color: #64748b;
        letter-spacing: 0.5px;
    }

    .value {
        font-size: 30px;
        font-weight: bold;
        margin-top: 10px;
    }

    .green { color: #16a34a; }
    .blue { color: #0284c7; }

    .refresh {
        text-align: center;
        margin-top: 30px;
    }

    /* 🔥 Gradient button */
    .btn {
        background: linear-gradient(90deg, #0284c7, #38bdf8);
        padding: 10px 22px;
        border: none;
        border-radius: 8px;
        color: white;
        cursor: pointer;
        transition: 0.2s;
    }

    /* 🔥 Button hover */
    .btn:hover {
        transform: scale(1.05);
        background: linear-gradient(90deg, #0369a1, #0ea5e9);
    }
</style>

    <script>
        setTimeout(() => {
            location.reload();
        }, 5000);
    </script>
</head>

<body>

<div class="main">

    <h1>DevOps Monitoring Dashboard</h1>

    <div class="dashboard">

        <div class="card status-card">
            <div class="label">STATUS</div>
            <div class="value green">RUNNING</div>
        </div>

        <div class="card">
            <div class="label">TOTAL REQUESTS</div>
            <div class="value blue">{{count}}</div>
        </div>

        <div class="card">
            <div class="label">LAST UPDATED</div>
            <div class="value">{{time}}</div>
        </div>

    </div>

    <div class="refresh">
        <button class="btn" onclick="location.reload()">Refresh</button>
    </div>

</div>

</body>
</html>
"""

# Routes

@app.route('/')
@REQUEST_TIME.time()
def home():
    global request_value

    start_time = time.time()

    # existing logic
    REQUEST_COUNT.labels(endpoint='/').inc()
    request_value += 1

    current_time = datetime.now().strftime("%H:%M:%S")

    response = render_template_string(
        HTML_PAGE,
        count=request_value,
        time=current_time
    )

    # ✅ latency calculation
    duration = time.time() - start_time
    REQUEST_LATENCY.labels(method=request.method, endpoint=request.path).observe(duration)

    return response


@app.route('/health')
def health():
    global request_value
    REQUEST_COUNT.labels(endpoint='/health').inc()
    request_value += 1
    return {"status": "OK"}


@app.route('/error')
def error():
    REQUEST_COUNT.labels(endpoint='/error').inc()
    return "Error occurred", 500


@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
