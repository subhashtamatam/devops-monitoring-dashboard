import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime

# ── Load environment variables from .env file ──
# python-dotenv reads the .env file and loads values into os.environ
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv is not installed, fall back to os.environ only
    pass

# ── Email credentials — read from .env file, never hardcoded ──
SENDER_EMAIL   = os.environ.get("YAHOO_EMAIL",        "subhash6609@yahoo.com")
APP_PASSWORD   = os.environ.get("YAHOO_APP_PASSWORD",  "")
RECEIVER_EMAIL = os.environ.get("YAHOO_EMAIL",        "subhash6609@yahoo.com")

# ── SMTP server settings ──
SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = 587


def send_alert_email(metric, label, current,
                     pred_2min, pred_5min,
                     threshold, unit, severity):
    """
    Send a predictive alert email via Yahoo SMTP.
    Credentials are loaded from the .env file — never hardcoded.
    Called by predictor.py when a metric is forecast to breach its threshold.
    """

    subject = f"[{severity.upper()} ALERT] {label} Risk Detected"

    body = f"""Predictive Monitoring Alert
-----------------------------
Metric       : {label}
Current      : {current}{unit}
In 2 minutes : {pred_2min}{unit}
In 5 minutes : {pred_5min}{unit}
Threshold    : {threshold}{unit}
Severity     : {severity.upper()}
Time         : {datetime.now().strftime("%d %b %Y, %H:%M:%S")}
-----------------------------
Sent by DevOps Monitoring Dashboard
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    if not APP_PASSWORD:
        print("[mailer] WARNING: YAHOO_APP_PASSWORD not set in .env — skipping email send")
        return

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print(f"[mailer] alert sent — {label} ({severity})")
    except Exception as e:
        print(f"[mailer] failed — {e}")