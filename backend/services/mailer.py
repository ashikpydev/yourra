"""
Simple email sender (SMTP).

Used to notify a user when an admin creates their account. If SMTP isn't
configured (SMTP_HOST / SMTP_FROM blank), it does nothing but log the message,
so the rest of the app keeps working in local mode without any email setup.
"""
import smtplib
import ssl
from email.message import EmailMessage

from backend.config import settings


def send_email(to: str, subject: str, body: str) -> bool:
    """Returns True if an email was actually sent, False otherwise."""
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        print(f"[mailer] SMTP not configured — would email {to}: {subject}")
        return False

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[mailer] send failed: {e}")
        return False
