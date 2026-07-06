# tests/test_app.py
# Tests for the Flask monitoring application.

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyzer
import predictor
import app as app_module


def test_app_module_loads_and_has_flask_instance():
    """app.py must import cleanly and expose a real Flask app object."""
    assert hasattr(app_module, "app")
    assert app_module.app.name == "app"


def test_analyzer_module_loads_and_has_expected_config():
    """analyzer.py must import cleanly and expose its threshold config."""
    assert hasattr(analyzer, "THRESHOLDS")
    assert hasattr(analyzer, "BASELINES")
    assert set(analyzer.THRESHOLDS.keys()) == {
        "cpu", "memory", "latency", "req_rate", "error_rate"
    }


def test_predictor_module_loads_and_has_expected_config():
    """predictor.py must import cleanly and expose its alert thresholds."""
    assert hasattr(predictor, "ALERT_THRESHOLDS")
    assert set(predictor.ALERT_THRESHOLDS.keys()) == {
        "cpu", "memory", "latency", "error_rate"
    }


# ── app.py: get_uptime() ──

def test_get_uptime_format():
    """Calls the real get_uptime() function with a known elapsed time."""
    original_start_time = app_module.START_TIME
    try:
        # Simulate the server having started exactly 1h 1m 1s ago.
        app_module.START_TIME = time.time() - 3661
        assert app_module.get_uptime() == "1h 1m 1s"
    finally:
        # Restore the real start time so other tests aren't affected.
        app_module.START_TIME = original_start_time


# ── predictor.py: linear_regression_predict() ──

def test_linear_regression_predict_upward_trend():
    """Feeds a clearly increasing series into the real prediction function."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    predicted = predictor.linear_regression_predict(values, steps_ahead=3)
    assert predicted == 8.0


def test_linear_regression_predict_insufficient_data():
    """With fewer than 3 points, the real function should fall back to the
    last known value instead of trying to fit a line."""
    result = predictor.linear_regression_predict([42.0], steps_ahead=5)
    assert result == 42.0


# ── predictor.py: get_severity() ──

def test_get_severity_critical():
    assert predictor.get_severity(predicted=90.0, threshold=80.0) == "critical"


def test_get_severity_warning():
    # 68 is within 80% of threshold (80*0.8=64) but below the threshold itself
    assert predictor.get_severity(predicted=68.0, threshold=80.0) == "warning"


def test_get_severity_safe():
    assert predictor.get_severity(predicted=30.0, threshold=80.0) == "safe"


# ── analyzer.py: calculate_scores() and get_status() ──

def test_calculate_scores_identifies_traffic_spike():
    """A metrics snapshot dominated by request rate should score highest
    on 'Traffic Spike', using the REAL weighted-scoring function."""
    metrics = {
        "cpu": 20.0,
        "memory": 100.0,
        "latency": 0.01,
        "req_rate": 0.5,     # at threshold — should dominate the score
        "error_rate": 0.0,
    }
    scores = analyzer.calculate_scores(metrics)
    dominant = max(scores, key=scores.get)
    assert dominant == "Traffic Spike"


def test_calculate_scores_identifies_error_surge():
    """A metrics snapshot dominated by error rate should score highest
    on 'Error Surge'."""
    metrics = {
        "cpu": 5.0,
        "memory": 100.0,
        "latency": 0.01,
        "req_rate": 0.01,
        "error_rate": 0.05,  # at threshold — should dominate the score
    }
    scores = analyzer.calculate_scores(metrics)
    dominant = max(scores, key=scores.get)
    assert dominant == "Error Surge"


def test_get_status_critical_when_over_hard_threshold():
    metrics = {
        "cpu": 90.0,          # above THRESHOLDS['cpu'] = 80.0
        "memory": 100.0,
        "latency": 0.01,
        "req_rate": 0.01,
        "error_rate": 0.0,
    }
    assert analyzer.get_status(metrics, top_score=0.0) == "critical"


def test_get_status_healthy_when_all_metrics_near_baseline():
    metrics = {
        "cpu": 0.1,
        "memory": 100.0,
        "latency": 0.005,
        "req_rate": 0.005,
        "error_rate": 0.0,
    }
    assert analyzer.get_status(metrics, top_score=0.0) == "healthy"
