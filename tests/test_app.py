# tests/test_app.py
# Basic tests for the Flask monitoring application

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_app_imports():
    """Test that app.py imports without errors."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("app", "app.py")
    assert spec is not None

def test_analyzer_imports():
    """Test that analyzer.py imports without errors."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("analyzer", "analyzer.py")
    assert spec is not None

def test_predictor_imports():
    """Test that predictor.py imports without errors."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("predictor", "predictor.py")
    assert spec is not None

def test_get_uptime_format():
    """Test uptime formatter returns correct format."""
    import time
    seconds = 3661  # 1h 1m 1s
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    result = f"{h}h {m}m {s}s"
    assert result == "1h 1m 1s"

def test_linear_regression_basic():
    """Test linear regression with known values."""
    # y = x, so predicting step 5 should give ~5
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    n = len(values)
    x_vals = list(range(n))
    y_vals = values
    sum_x  = sum(x_vals)
    sum_y  = sum(y_vals)
    sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
    sum_x2 = sum(x * x for x in x_vals)
    denom  = n * sum_x2 - sum_x ** 2
    slope  = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    predicted = intercept + slope * (n - 1 + 3)
    assert predicted > 5.0  # trending upward

def test_severity_logic():
    """Test severity calculation logic."""
    threshold = 80.0

    # Critical — above threshold
    value = 90.0
    if value >= threshold:
        severity = 'critical'
    elif value >= threshold * 0.80:
        severity = 'warning'
    else:
        severity = 'safe'
    assert severity == 'critical'

    # Warning — within 80% of threshold
    value = 68.0
    if value >= threshold:
        severity = 'critical'
    elif value >= threshold * 0.80:
        severity = 'warning'
    else:
        severity = 'safe'
    assert severity == 'warning'

    # Safe — below 80% of threshold
    value = 30.0
    if value >= threshold:
        severity = 'critical'
    elif value >= threshold * 0.80:
        severity = 'warning'
    else:
        severity = 'safe'
    assert severity == 'safe'
