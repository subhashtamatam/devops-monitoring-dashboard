import smtplib
from email.mime.text import MIMEText
from datetime import datetime

SENDER_EMAIL = "subhash6609@yahoo.com"
APP_PASSWORD = "kzcrklmjtmxawecv"
RECEIVER_EMAIL = "subhash6609@yahoo.com"


def send_alert_email(metric, label, current,
                     pred_2min, pred_5min,
                     threshold, unit, severity):

    subject = f"[{severity.upper()} ALERT] {label} Risk Detected"

    body = f"""
Predictive Monitoring Alert

Metric: {label}
Current Value: {current}{unit}

Prediction after 2 mins: {pred_2min}{unit}
Prediction after 5 mins: {pred_5min}{unit}

Threshold: {threshold}{unit}

Severity: {severity.upper()}
Time: {datetime.now()}
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    try:
        server = smtplib.SMTP("smtp.mail.yahoo.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(
            SENDER_EMAIL,
            RECEIVER_EMAIL,
            msg.as_string()
        )
        server.quit()

        print(f"[EMAIL SENT] {label}")

    except Exception as e:
        print("Email failed:", e)
