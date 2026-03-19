import os
import json
import time
import uuid
from typing import List, Dict, Any

try:
    import mlflow
    _MLFLOW_AVAILABLE = True
except ImportError:
    _MLFLOW_AVAILABLE = False

import httpx
import smtplib
from email.message import EmailMessage
from celery import shared_task

ALERTS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'alerts.json')


def _ensure_file():
    d = os.path.dirname(ALERTS_FILE)
    os.makedirs(d, exist_ok=True)
    if not os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, 'w') as f:
            json.dump([], f)


def load_alerts() -> List[Dict[str, Any]]:
    _ensure_file()
    with open(ALERTS_FILE, 'r') as f:
        return json.load(f)


def save_alerts(alerts: List[Dict[str, Any]]):
    _ensure_file()
    with open(ALERTS_FILE, 'w') as f:
        json.dump(alerts, f, indent=2)


def add_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    alerts = load_alerts()
    alert_id = str(uuid.uuid4())
    alert['id'] = alert_id
    alert.setdefault('created_at', int(time.time()))
    alert.setdefault('last_triggered', None)
    alert.setdefault('cooldown_seconds', 3600)
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def delete_alert(alert_id: str) -> bool:
    alerts = load_alerts()
    new = [a for a in alerts if a.get('id') != alert_id]
    if len(new) == len(alerts):
        return False
    save_alerts(new)
    return True


def _notify(alert: Dict[str, Any], value: float):
    notify_url = alert.get('notify_url')
    payload = {
        'alert_id': alert.get('id'),
        'run_id': alert.get('run_id'),
        'metric_key': alert.get('metric_key'),
        'value': value,
        'timestamp': int(time.time()),
    }
    # webhook notification
    if notify_url:
        try:
            httpx.post(notify_url, json=payload, timeout=5.0)
        except Exception:
            pass

    # email notification (notify_email field)
    notify_email = alert.get('notify_email')
    if notify_email:
        try:
            smtp_host = os.getenv('SMTP_HOST')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_user = os.getenv('SMTP_USER')
            smtp_pass = os.getenv('SMTP_PASSWORD')
            smtp_from = os.getenv('SMTP_FROM', smtp_user)
            if not smtp_host or not smtp_user:
                # SMTP not configured
                return
            msg = EmailMessage()
            msg['Subject'] = f"Alert triggered: {alert.get('metric_key')}"
            msg['From'] = smtp_from
            msg['To'] = notify_email
            msg.set_content(f"Alert {alert.get('id')} triggered.\n\nMetric: {alert.get('metric_key')}\nValue: {value}\nRun: {alert.get('run_id')}\nTimestamp: {payload['timestamp']}")

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        except Exception:
            pass


def _check_condition(value: float, operator: str, threshold: float) -> bool:
    if value is None:
        return False
    if operator == 'gt':
        return value > threshold
    if operator == 'ge':
        return value >= threshold
    if operator == 'lt':
        return value < threshold
    if operator == 'le':
        return value <= threshold
    return False


def check_alerts() -> List[Dict[str, Any]]:
    """Check all alerts and notify if conditions met. Returns list of triggered alerts."""
    if not _MLFLOW_AVAILABLE:
        return []
    alerts = load_alerts()
    triggered = []
    client = mlflow.tracking.MlflowClient()
    now = int(time.time())
    for alert in alerts:
        try:
            run_id = alert.get('run_id')
            metric = alert.get('metric_key')
            operator = alert.get('operator', 'gt')
            threshold = float(alert.get('threshold', 0))
            history = client.get_metric_history(run_id, metric)
            if not history:
                continue
            latest = history[-1].value
            last_trig = alert.get('last_triggered')
            cooldown = int(alert.get('cooldown_seconds', 3600))
            if _check_condition(latest, operator, threshold):
                if not last_trig or (now - int(last_trig) > cooldown):
                    _notify(alert, latest)
                    alert['last_triggered'] = now
                    triggered.append({'alert': alert, 'value': latest})
        except Exception:
            continue
    if triggered:
        save_alerts(alerts)
    return triggered


@shared_task
def run_alerts_check_task():
    return check_alerts()
