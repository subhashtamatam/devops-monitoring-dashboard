# predictor.py
# Phase 4B — Predictive Alert System
# Collects metric readings over time and uses linear regression
# to predict future values — sends email if breach is coming
# Pure Python — no numpy, no extra libraries needed

import requests
import time
from datetime import datetime
from collections import deque

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

PROMETHEUS_URL   = "http://localhost:9090"
COLLECTION_INTERVAL = 10    # collect a reading every 10 seconds
MAX_HISTORY      = 10       # keep last 10 readings for regression
PREDICT_2MIN     = 12       # 2 minutes ahead = 12 steps of 10s
PREDICT_5MIN     = 30       # 5 minutes ahead = 30 steps of 10s

# Thresholds — if predicted value will cross these, send alert
ALERT_THRESHOLDS = {
    'cpu':        80.0,   # percent
    'memory':     500.0,   # percent
    'latency':    0.5,    # seconds
    'error_rate': 0.05,   # errors/sec
}

# Friendly names for email alerts
METRIC_LABELS = {
    'cpu':        'CPU Usage',
    'memory':     'Memory Usage',
    'latency':    'Response Latency',
    'error_rate': 'Error Rate',
}

METRIC_UNITS = {
    'cpu':        '%',
    'memory':     ' MB',
    'latency':    's',
    'error_rate': ' errors/sec',
}

# ──────────────────────────────────────────────
# In-memory history — stores last 10 readings
# per metric as (timestamp, value) pairs
# ──────────────────────────────────────────────

history = {
    'cpu':        deque(maxlen=MAX_HISTORY),
    'memory':     deque(maxlen=MAX_HISTORY),
    'latency':    deque(maxlen=MAX_HISTORY),
    'error_rate': deque(maxlen=MAX_HISTORY),
}

# Track which alerts already sent — avoid spamming
# Key: metric name, Value: timestamp of last alert sent
last_alert_sent = {}
ALERT_COOLDOWN = 300   # seconds — don't resend same alert within 5 minutes

# Store latest predictions for the /predict page
latest_predictions = {}


# ──────────────────────────────────────────────
# Fetch one metric from Prometheus
# ──────────────────────────────────────────────

def fetch_metric(promql_query):
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql_query},
            timeout=3
        )
        data    = response.json()
        results = data.get("data", {}).get("result", [])
        if results:
            value = float(results[0]["value"][1])
            if value != value:   # NaN check
                return 0.0
            return value
        return 0.0
    except Exception:
        return 0.0


# ──────────────────────────────────────────────
# Fetch all 4 metrics we want to predict
# ──────────────────────────────────────────────

def fetch_current_metrics():
    return {
        'cpu': fetch_metric(
            'rate(process_cpu_seconds_total{job="flask-app"}[2m]) * 100'
        ),
        'memory': fetch_metric(
            'process_resident_memory_bytes{job="flask-app"} / 1048576'
        ),
        'latency': fetch_metric(
            'rate(http_request_duration_seconds_sum{job="flask-app"}[2m])'
            ' / rate(http_request_duration_seconds_count{job="flask-app"}[2m])'
        ),
        'error_rate': fetch_metric(
            'rate(app_errors_total{job="flask-app"}[2m])'
        ),
    }


# ──────────────────────────────────────────────
# Pure Python Linear Regression
# Finds the best-fit line through the history points
# and uses it to predict a future value
# ──────────────────────────────────────────────

def linear_regression_predict(values, steps_ahead):
    """
    Takes a list of float values (equally spaced in time)
    and predicts the value 'steps_ahead' steps into the future.

    Uses the least squares method:
      slope = (n * sum(x*y) - sum(x) * sum(y)) / (n * sum(x^2) - sum(x)^2)
      intercept = (sum(y) - slope * sum(x)) / n

    This is standard linear regression — no libraries needed.
    """
    n = len(values)

    if n < 3:
        # Not enough data to predict — return last known value
        return values[-1] if values else 0.0

    # x = time steps: 0, 1, 2, ... n-1
    x_vals = list(range(n))
    y_vals = list(values)

    sum_x  = sum(x_vals)
    sum_y  = sum(y_vals)
    sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
    sum_x2 = sum(x * x for x in x_vals)

    denominator = (n * sum_x2 - sum_x ** 2)

    if denominator == 0:
        # All x values are same — flat line
        return y_vals[-1]

    slope     = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n

    # Predict at step n + steps_ahead - 1
    future_x = (n - 1) + steps_ahead
    predicted = intercept + slope * future_x

    # Never predict negative values
    return max(0.0, predicted)


# ──────────────────────────────────────────────
# Determine alert severity
# ──────────────────────────────────────────────

def get_severity(predicted, threshold):
    """
    Returns severity level based on how close prediction is to threshold.
      'critical' — predicted value will exceed threshold
      'warning'  — predicted value within 80% of threshold
      'safe'     — no issue predicted
    """
    if predicted >= threshold:
        return 'critical'
    elif predicted >= threshold * 0.80:
        return 'warning'
    else:
        return 'safe'


# ──────────────────────────────────────────────
# Run predictions for all 4 metrics
# ──────────────────────────────────────────────

def run_predictions():
    """
    Called by the background thread every COLLECTION_INTERVAL seconds.
    1. Fetches current metric values
    2. Appends to history
    3. Runs linear regression to predict 2min and 5min ahead
    4. Returns prediction results for the /predict page
    5. Triggers email alerts if breach predicted
    """
    global latest_predictions

    # Step 1 — fetch current values
    current = fetch_current_metrics()

    # Step 2 — append to history with timestamp
    now = time.time()
    for metric, value in current.items():
        history[metric].append((now, value))

    # Step 3 — predict for each metric
    predictions = {}

    for metric in ['cpu', 'memory', 'latency', 'error_rate']:
        values    = [v for (_, v) in history[metric]]
        current_v = current[metric]
        threshold = ALERT_THRESHOLDS[metric]

        if len(values) >= 3:
            pred_2min = linear_regression_predict(values, PREDICT_2MIN)
            pred_5min = linear_regression_predict(values, PREDICT_5MIN)
        else:
            # Not enough history yet
            pred_2min = current_v
            pred_5min = current_v

        severity_2min = get_severity(pred_2min, threshold)
        severity_5min = get_severity(pred_5min, threshold)

        # Overall severity = worst of the two
        if severity_2min == 'critical' or severity_5min == 'critical':
            overall = 'critical'
        elif severity_2min == 'warning' or severity_5min == 'warning':
            overall = 'warning'
        else:
            overall = 'safe'

        predictions[metric] = {
            'current':      round(current_v, 4),
            'pred_2min':    round(pred_2min, 4),
            'pred_5min':    round(pred_5min, 4),
            'threshold':    threshold,
            'severity':     overall,
            'sev_2min':     severity_2min,
            'sev_5min':     severity_5min,
            'label':        METRIC_LABELS[metric],
            'unit':         METRIC_UNITS[metric],
            'history_len':  len(values),
        }

    predictions['timestamp'] = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    predictions['data_points'] = len(history['cpu'])

    # Step 4 — store for /predict page
    latest_predictions = predictions

    # Step 5 — trigger email alerts if needed
    _check_and_alert(predictions)

    return predictions


# ──────────────────────────────────────────────
# Check predictions and send alerts
# ──────────────────────────────────────────────

def _check_and_alert(predictions):
    """
    For each metric, if severity is critical or warning
    and cooldown has passed, send an email alert.
    """
    from mailer import send_alert_email   # imported here to avoid circular import

    now = time.time()

    for metric in ['cpu', 'memory', 'latency', 'error_rate']:
        pred = predictions.get(metric, {})
        severity = pred.get('severity', 'safe')

        if severity == 'safe':
            continue

        # Check cooldown — don't spam
        last_sent = last_alert_sent.get(metric, 0)
        if now - last_sent < ALERT_COOLDOWN:
            continue

        # Send alert
        try:
            send_alert_email(
                metric    = metric,
                label     = pred['label'],
                current   = pred['current'],
                pred_2min = pred['pred_2min'],
                pred_5min = pred['pred_5min'],
                threshold = pred['threshold'],
                unit      = pred['unit'],
                severity  = severity,
            )
            last_alert_sent[metric] = now
        except Exception as e:
            print(f"[Mailer Error] {metric}: {e}")


# ──────────────────────────────────────────────
# Background thread runner
# Called from app.py on startup
# ──────────────────────────────────────────────

def start_prediction_loop():
    """
    Runs in a background thread.
    Collects metrics and runs predictions every 10 seconds.
    """
    print("[Predictor] Background prediction loop started.")
    while True:
        try:
            run_predictions()
        except Exception as e:
            print(f"[Predictor Error] {e}")
        time.sleep(COLLECTION_INTERVAL)
