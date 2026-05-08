import requests
from datetime import datetime

# ──────────────────────────────────────────────
# Prometheus connection
# ──────────────────────────────────────────────

PROMETHEUS_URL = "http://localhost:9090"

# ──────────────────────────────────────────────
# Thresholds — what counts as "high"
# ──────────────────────────────────────────────

THRESHOLDS = {
    'cpu':      80.0,   # CPU % above this is high
    'memory':   500.0,   # Memory % above this is high
    'latency':  0.5,    # Seconds above this is slow
    'req_rate': 0.5,    # Requests/sec above this is high traffic
    'error_rate': 0.05, # Errors/sec above this is high
}

# ──────────────────────────────────────────────
# Baselines — normal expected values
# ──────────────────────────────────────────────

BASELINES = {
    'cpu':      30.0,
    'memory':   30.0,
    'latency':  0.05,
    'req_rate': 0.05,
    'error_rate': 0.0,
}


# ──────────────────────────────────────────────
# Step 1 — Fetch a single metric from Prometheus
# ──────────────────────────────────────────────

def fetch_metric(promql_query):
    """
    Sends a PromQL query to Prometheus and returns the float value.
    Returns 0.0 if Prometheus is unreachable or metric not found.
    """
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql_query},
            timeout=3
        )
        data = response.json()

        results = data.get("data", {}).get("result", [])

        if results:
            value = float(results[0]["value"][1])
            # NaN or Inf from Prometheus division by zero → return 0
            if value != value:  # NaN check in pure Python
                return 0.0
            return value
        return 0.0

    except Exception:
        # Prometheus not reachable — return 0
        return 0.0


# ──────────────────────────────────────────────
# Step 2 — Fetch all 5 metrics at once
# ──────────────────────────────────────────────

def fetch_all_metrics():
    """
    Fetches all relevant metrics from Prometheus.
    Returns a dictionary of metric name → current float value.
    """
    metrics = {
        # CPU usage percent of the system
        'cpu': fetch_metric(
            'rate(process_cpu_seconds_total{job="flask-app"}[2m]) * 100'
        ),

        # Memory in use as percentage
        'memory': fetch_metric(
            'process_resident_memory_bytes{job="flask-app"} / 1048576'
        ),

        # Average request latency in seconds over last 2 minute
        'latency': fetch_metric(
            'rate(http_request_duration_seconds_sum{job="flask-app"}[2m])'
            ' / rate(http_request_duration_seconds_count{job="flask-app"}[2m])'
        ),

        # Request rate — requests per second over last 2 minute
        'req_rate': fetch_metric(
            'rate(app_requests_total{job="flask-app"}[2m])'
        ),

        # Error rate — errors per second over last 2 minute
        'error_rate': fetch_metric(
            'rate(app_errors_total{job="flask-app"}[2m])'
        ),
    }

    return metrics


# ──────────────────────────────────────────────
# Step 3 — Score each possible cause
# ──────────────────────────────────────────────

def calculate_scores(metrics):
    """
    Each cause gets a score from 0 to 100 based on how much
    each metric deviates from its baseline, with different weights.

    Weights explain which metrics matter most for each cause:
      - Traffic Spike   → req_rate matters most
      - CPU Saturation  → cpu matters most
      - Memory Pressure → memory matters most
      - Latency Anomaly → latency matters most
      - Error Surge     → error_rate matters most
    """

    def deviation(metric_name):
        """How far above baseline is this metric, as a 0-100 score."""
        current  = metrics.get(metric_name, 0.0)
        baseline = BASELINES.get(metric_name, 1.0)
        threshold = THRESHOLDS.get(metric_name, 1.0)

        if threshold == baseline:
            return 0.0

        # Score scales from 0 (at baseline) to 100 (at threshold and above)
        raw = (current - baseline) / (threshold - baseline)
        return round(min(max(raw, 0.0), 1.0) * 100, 1)

    scores = {
        'Traffic Spike': round(
            deviation('req_rate') * 0.60 +
            deviation('cpu')      * 0.20 +
            deviation('latency')  * 0.20,
            1
        ),
        'CPU Saturation': round(
            deviation('cpu')      * 0.70 +
            deviation('req_rate') * 0.20 +
            deviation('latency')  * 0.10,
            1
        ),
        'Memory Pressure': round(
            deviation('memory')   * 0.80 +
            deviation('cpu')      * 0.20,
            1
        ),
        'Latency Anomaly': round(
            deviation('latency')  * 0.60 +
            deviation('req_rate') * 0.20 +
            deviation('cpu')      * 0.20,
            1
        ),
        'Error Surge': round(
            deviation('error_rate') * 0.80 +
            deviation('req_rate')   * 0.20,
            1
        ),
    }

    return scores


# ──────────────────────────────────────────────
# Step 4 — Determine overall system status
# ──────────────────────────────────────────────

def get_status(metrics):
    """
    Returns:
      'critical' — if any metric is well above threshold
      'warning'  — if any metric is approaching threshold
      'healthy'  — everything is normal
    """
    if (metrics['cpu']        > THRESHOLDS['cpu']        or
        metrics['memory']     > THRESHOLDS['memory']     or
        metrics['latency']    > THRESHOLDS['latency']    or
        metrics['error_rate'] > THRESHOLDS['error_rate'] * 2):
        return 'critical'

    if (metrics['cpu']        > THRESHOLDS['cpu']        * 0.7 or
        metrics['memory']     > THRESHOLDS['memory']     * 0.7 or
        metrics['latency']    > THRESHOLDS['latency']    * 0.7 or
        metrics['error_rate'] > THRESHOLDS['error_rate']):
        return 'warning'

    return 'healthy'


# ──────────────────────────────────────────────
# Step 5 — Build human-readable explanation
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# Step 6 — Main function: run full analysis
# ──────────────────────────────────────────────

def run_analysis():
    """
    Main entry point called by app.py.
    Returns a dictionary with everything needed to render the /analyze page.
    """
    metrics = fetch_all_metrics()
    scores  = calculate_scores(metrics)
    status  = get_status(metrics)

    # Find which cause has the highest score
    dominant_cause = max(scores, key=scores.get)
    dominant_score = scores[dominant_cause]

    # Confidence = dominant score as % of total scores
    total_score = sum(scores.values())
    if total_score > 0:
        confidence = round((dominant_score / total_score) * 100, 1)
    else:
        confidence = 0.0

    # If all scores are very low → system is healthy, no dominant cause
    if dominant_score < 5.0:
        status         = 'healthy'
        dominant_cause = 'None'
        explanation    = HEALTHY_MESSAGE
        confidence     = 100.0
    else:
        explanation = EXPLANATIONS.get(dominant_cause, "Analysis inconclusive.")

    # Build progress bar widths for HTML (max bar = 300px wide)
    # Clean all scores — replace any NaN with 0.0
    scores = {
        cause: (0.0 if (s != s) else s)
        for cause, s in scores.items()
    }

    max_score = max(scores.values()) if max(scores.values()) > 0 else 1
    bar_widths = {
        cause: int(round((score / max_score) * 280))
        for cause, score in scores.items()
    }

    return {
        'status':         status,
        'dominant_cause': dominant_cause,
        'confidence':     confidence,
        'explanation':    explanation,
        'scores':         scores,
        'bar_widths':     bar_widths,
        'metrics':        metrics,
        'timestamp':      datetime.now().strftime("%d %b %Y, %H:%M:%S"),
    }
