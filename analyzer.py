import requests
from datetime import datetime

PROMETHEUS_URL = "http://localhost:9090"

# thresholds - values above these trigger alerts
THRESHOLDS = {
    'cpu':        80.0,
    'memory':     500.0,
    'latency':    0.5,
    'req_rate':   0.5,
    'error_rate': 0.05,
}

# normal expected values for a healthy flask app
BASELINES = {
    'cpu':        30.0,
    'memory':     30.0,
    'latency':    0.05,
    'req_rate':   0.05,
    'error_rate': 0.0,
}

EXPLANATIONS = {
    'Traffic Spike': (
        "Request volume is significantly above normal. "
        "The application is receiving more traffic than expected, "
        "which is increasing CPU usage and response times."
    ),
    'CPU Saturation': (
        "The processor is under heavy load. "
        "CPU usage is high, causing the application to slow down "
        "while handling incoming requests."
    ),
    'Memory Pressure': (
        "Memory consumption is elevated. "
        "High RAM usage can lead to slower garbage collection "
        "and increased response latency."
    ),
    'Latency Anomaly': (
        "Response time is higher than normal without a clear "
        "CPU or memory cause. This may indicate slow database "
        "queries, external API delays, or I/O bottlenecks."
    ),
    'Error Surge': (
        "The application is returning an unusually high number "
        "of errors. Check recent deployments, endpoint changes, "
        "or dependency failures."
    ),
}

HEALTHY_MESSAGE = (
    "All metrics are within normal ranges. "
    "The application is performing as expected with no "
    "anomalies detected."
)


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
            return 0.0 if val != val else val  # NaN check
        return 0.0
    except Exception:
        return 0.0


def fetch_all_metrics():
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
        'req_rate': fetch_metric(
            'rate(app_requests_total{job="flask-app"}[2m])'
        ),
        'error_rate': fetch_metric(
            'rate(app_errors_total{job="flask-app"}[2m])'
        ),
    }


def calculate_scores(metrics):
    def deviation(name):
        cur = metrics.get(name, 0.0)
        base = BASELINES.get(name, 1.0)
        thresh = THRESHOLDS.get(name, 1.0)
        if thresh == base:
            return 0.0
        raw = (cur - base) / (thresh - base)
        return round(min(max(raw, 0.0), 1.0) * 100, 1)

    return {
        'Traffic Spike': round(
            deviation('req_rate') * 0.60 +
            deviation('cpu')      * 0.20 +
            deviation('latency')  * 0.20, 1
        ),
        'CPU Saturation': round(
            deviation('cpu')      * 0.70 +
            deviation('req_rate') * 0.20 +
            deviation('latency')  * 0.10, 1
        ),
        'Memory Pressure': round(
            deviation('memory') * 0.80 +
            deviation('cpu')    * 0.20, 1
        ),
        'Latency Anomaly': round(
            deviation('latency')  * 0.60 +
            deviation('req_rate') * 0.20 +
            deviation('cpu')      * 0.20, 1
        ),
        'Error Surge': round(
            deviation('error_rate') * 0.80 +
            deviation('req_rate')   * 0.20, 1
        ),
    }


def get_status(metrics):
    t = THRESHOLDS
    if (metrics['cpu']        > t['cpu']          or
        metrics['memory']     > t['memory']        or
        metrics['latency']    > t['latency']       or
        metrics['error_rate'] > t['error_rate'] * 2):
        return 'critical'

    if (metrics['cpu']        > t['cpu']        * 0.7 or
        metrics['memory']     > t['memory']     * 0.7 or
        metrics['latency']    > t['latency']    * 0.7 or
        metrics['error_rate'] > t['error_rate']):
        return 'warning'

    return 'healthy'


def run_analysis():
    metrics = fetch_all_metrics()
    scores  = calculate_scores(metrics)
    status  = get_status(metrics)

    dominant = max(scores, key=scores.get)
    top_score = scores[dominant]

    total = sum(scores.values())
    confidence = round((top_score / total) * 100, 1) if total > 0 else 0.0

    if top_score < 5.0:
        status     = 'healthy'
        dominant   = 'None'
        explanation = HEALTHY_MESSAGE
        confidence  = 100.0
    else:
        explanation = EXPLANATIONS.get(dominant, "Analysis inconclusive.")

    # sanitize NaN values before building bar widths
    scores = {k: (0.0 if s != s else s) for k, s in scores.items()}
    max_s  = max(scores.values()) or 1
    bar_widths = {k: int(round((s / max_s) * 280)) for k, s in scores.items()}

    return {
        'status':         status,
        'dominant_cause': dominant,
        'confidence':     confidence,
        'explanation':    explanation,
        'scores':         scores,
        'bar_widths':     bar_widths,
        'metrics':        metrics,
        'timestamp':      datetime.now().strftime("%d %b %Y, %H:%M:%S"),
    }