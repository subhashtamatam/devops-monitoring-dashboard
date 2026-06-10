from dotenv import load_dotenv
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

load_dotenv()

SENDER_EMAIL   = os.environ.get('YAHOO_EMAIL',        'subhash6609@yahoo.com')
APP_PASSWORD   = os.environ.get('YAHOO_APP_PASSWORD', '')
RECEIVER_EMAIL = os.environ.get('YAHOO_EMAIL',        'subhash6609@yahoo.com')

SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = 587


def send_test_email():
    subject = "✅ [TEST] DevOps Monitoring Dashboard — Email Alert Test"

    body = f"""This is a TEST email from your DevOps Monitoring Dashboard.
=============================================================

Hello,

This email was triggered manually using the "Send Test Email Alert"
button on the Alert History page of your monitoring dashboard.

This is NOT a real alert. No action is required.

It confirms that:
  ✅  Email delivery is working correctly
  ✅  Yahoo SMTP connection is active (port 587)
  ✅  Alertmanager email routing is configured
  ✅  Your monitoring system is fully operational

-------------------------------------------------------------
Dashboard URL  : http://localhost:5000
Alerts Page    : http://localhost:5000/alerts
Sent at        : {datetime.now().strftime("%d %b %Y, %H:%M:%S")}
-------------------------------------------------------------

Sent by: Real-Time Application Performance Monitoring Dashboard
Project: PG Final Year Major Project — Osmania University
=============================================================
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    server.starttls()
    server.login(SENDER_EMAIL, APP_PASSWORD)
    server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    server.quit()
    print("[mailer] test email sent successfully")


def send_alert_email(metric, label, current,
                     pred_2min, pred_5min,
                     threshold, unit, severity):

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

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print(f"[mailer] alert sent — {label} ({severity})")
    except Exception as e:
        print(f"[mailer] failed — {e}")