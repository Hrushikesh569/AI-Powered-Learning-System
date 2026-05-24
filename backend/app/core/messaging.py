"""Email and SMS helpers used by auth and notifications."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import smtplib
from email.message import EmailMessage
from typing import Optional

import httpx

_OTP_SALT = os.getenv("OTP_SALT", "ai-learning-otp-salt")


def generate_otp(length: int = 6) -> str:
    lower = 10 ** (length - 1)
    upper = (10 ** length) - 1
    return str(secrets.randbelow(upper - lower + 1) + lower)


def hash_otp(code: str) -> str:
    return hashlib.sha256(f"{_OTP_SALT}:{code}".encode("utf-8")).hexdigest()


def verify_otp(code: str, code_hash: str) -> bool:
    return hash_otp(code) == code_hash


def _smtp_ready() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"))


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not _smtp_ready():
        return False

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user:
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        server.starttls()
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    return True


async def send_sms(phone_number: str, body: str) -> bool:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    if not (account_sid and auth_token and from_number and phone_number):
        return False

    payload = {"From": from_number, "To": phone_number, "Body": body}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            data=payload,
            auth=(account_sid, auth_token),
        )
        return response.status_code < 400


def phone_normalize(value: Optional[str]) -> str:
    cleaned = re.sub(r"[^0-9+]", "", value or "")
    return cleaned
