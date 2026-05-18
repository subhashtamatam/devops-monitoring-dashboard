import smtplib
from email.mime.text import MIMEText
from datetime import datetime

SENDER_EMAIL   = "subhash6609@yahoo.com"
APP_PASSWORD   = "REDACTED_ROTATED_PASSWORD"
RECEIVER_EMAIL = "subhash6609@yahoo.com"

SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = 587


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