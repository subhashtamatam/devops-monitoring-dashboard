import requests
import time
from datetime import datetime
from collections import deque

PROMETHEUS_URL      = "http://localhost:9090"
COLLECTION_INTERVAL = 10   # seconds between each reading
MAX_HISTORY         = 10
PREDICT_2MIN        = 12   # 12 steps x 10s = 2 minutes
PREDICT_5MIN        = 30

ALERT_THRESHOLDS = {
    'cpu':        80.0,
    'memory':     500.0,
    'latency':    0.5,
    'error_rate': 0.05,
}

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

# rolling history for each metric
history = {
    'cpu':        deque(maxlen=MAX_HISTORY),
    'memory':     deque(maxlen=MAX_HISTORY),
    'latency':    deque(maxlen=MAX_HISTORY),
    'error_rate': deque(maxlen=MAX_HISTORY),
}

last_alert_sent  = {}
ALERT_COOLDOWN   = 300  # 5 minutes between repeated alerts
latest_predictions = {}


def fetch_metric(query):
    try:
        res = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=3
        )
        results = res.json().get("data", {}).get("result", [])
        if results:
            val = float(results[0]["value"][1])
            return 0.0 if val != val else val
        return 0.0
    except Exception:
        return 0.0


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


def linear_regression_predict(values, steps_ahead):
    # need at least 3 points to draw a meaningful trend line
    n = len(values)
    if n < 3:
        return values[-1] if values else 0.0

    xs = list(range(n))
    ys = list(values)

    sx  = sum(xs)
    sy  = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sx2 = sum(x * x for x in xs)

    denom = n * sx2 - sx ** 2
    if denom == 0:
        return ys[-1]

    slope     = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    predicted = intercept + slope * ((n - 1) + steps_ahead)

    return max(0.0, predicted)


def get_severity(predicted, threshold):
    if predicted >= threshold:
        return 'critical'
    elif predicted >= threshold * 0.80:
        return 'warning'
    return 'safe'


def run_predictions():
    global latest_predictions

    current = fetch_current_metrics()
    now = time.time()

    for metric, value in current.items():
        history[metric].append((now, value))

    predictions = {}

    for metric in ['cpu', 'memory', 'latency', 'error_rate']:
        vals      = [v for (_, v) in history[metric]]
        cur_val   = current[metric]
        threshold = ALERT_THRESHOLDS[metric]

        if len(vals) >= 3:
            p2 = linear_regression_predict(vals, PREDICT_2MIN)
            p5 = linear_regression_predict(vals, PREDICT_5MIN)
        else:
            p2 = cur_val
            p5 = cur_val

        s2 = get_severity(p2, threshold)
        s5 = get_severity(p5, threshold)

        if s2 == 'critical' or s5 == 'critical':
            overall = 'critical'
        elif s2 == 'warning' or s5 == 'warning':
            overall = 'warning'
        else:
            overall = 'safe'

        predictions[metric] = {
            'current':     round(cur_val, 4),
            'pred_2min':   round(p2, 4),
            'pred_5min':   round(p5, 4),
            'threshold':   threshold,
            'severity':    overall,
            'sev_2min':    s2,
            'sev_5min':    s5,
            'label':       METRIC_LABELS[metric],
            'unit':        METRIC_UNITS[metric],
            'history_len': len(vals),
        }

    predictions['timestamp']   = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    predictions['data_points'] = len(history['cpu'])
    latest_predictions         = predictions

    _check_and_alert(predictions)
    return predictions


def _check_and_alert(predictions):
    from mailer import send_alert_email

    now = time.time()
    for metric in ['cpu', 'memory', 'latency', 'error_rate']:
        pred     = predictions.get(metric, {})
        severity = pred.get('severity', 'safe')

        if severity == 'safe':
            continue

        if now - last_alert_sent.get(metric, 0) < ALERT_COOLDOWN:
            continue

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

            # Also log into the Flask dashboard alert history
            try:
                import app as flask_app
                unit   = pred['unit']
                cur    = pred['current']
                p2     = pred['pred_2min']
                thresh = pred['threshold']
                flask_app.add_alert(
                    source      = 'Predictive System',
                    name        = f"Predicted {pred['label']} Breach",
                    severity    = severity,
                    description = (
                        f"Linear regression forecasts {pred['label']} reaching "
                        f"{p2:.2f}{unit} in 2 min (threshold: {thresh}{unit}). "
                        f"Current value: {cur:.2f}{unit}. "
                        f"Proactive email alert sent."
                    ),
                )
            except Exception:
                pass   # app not yet loaded — skip history entry

        except Exception as e:
            print(f"[mailer] failed for {metric}: {e}")


def start_prediction_loop():
    print("[predictor] started — collecting every 10s")
    while True:
        try:
            run_predictions()
        except Exception as e:
            print(f"[predictor] error: {e}")
        time.sleep(COLLECTION_INTERVAL)