"""Email service: SMTP or SendGrid (configurable via EMAIL_PROVIDER)."""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp")  # smtp | sendgrid | console
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@arada.fun")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://arada.fun")

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")


class EmailError(Exception):
    """Raised when email delivery fails."""


# ============================================================================
# Templates
# ============================================================================

_BASE_TEMPLATE = """\
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, Arial, sans-serif; background: #f4f4f7; padding: 24px;">
  <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 32px;">
    <h2 style="color: #1a1a2e; margin-top: 0;">{title}</h2>
    <div style="color: #444; font-size: 15px; line-height: 1.6;">
      {body}
    </div>
    {button}
    <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
    <p style="color: #999; font-size: 12px;">
      Arada Intelligence OS — If you didn't request this, you can safely ignore this email.
    </p>
  </div>
</body>
</html>
"""

_BUTTON = """\
<div style="margin: 24px 0;">
  <a href="{url}" style="background: #4f46e5; color: #fff; padding: 12px 24px;
     border-radius: 6px; text-decoration: none; display: inline-block;">{label}</a>
</div>
"""


def _render(title: str, body: str, button_url: Optional[str] = None,
            button_label: str = "Continue") -> str:
    button_html = _BUTTON.format(url=button_url, label=button_label) if button_url else ""
    return _BASE_TEMPLATE.format(title=title, body=body, button=button_html)


# ============================================================================
# Transport
# ============================================================================


async def _send(to_email: str, subject: str, html_body: str) -> None:
    """Send email via configured provider. Raises EmailError on failure."""
    if EMAIL_PROVIDER == "console":
        # Development mode: log instead of sending
        logger.info(f"[EMAIL:console] to={to_email} subject={subject}")
        return

    if EMAIL_PROVIDER == "sendgrid":
        await _send_sendgrid(to_email, subject, html_body)
        return

    _send_smtp(to_email, subject, html_body)


def _send_smtp(to_email: str, subject: str, html_body: str) -> None:
    """Send via SMTP with STARTTLS."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent (smtp): to={to_email} subject={subject}")
    except Exception as e:
        logger.error(f"SMTP send failed: {e}")
        raise EmailError(f"Failed to send email: {e}")


async def _send_sendgrid(to_email: str, subject: str, html_body: str) -> None:
    """Send via SendGrid API."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {SENDGRID_API_KEY}"},
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": EMAIL_FROM},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html_body}],
                },
            )
            resp.raise_for_status()
        logger.info(f"Email sent (sendgrid): to={to_email} subject={subject}")
    except Exception as e:
        logger.error(f"SendGrid send failed: {e}")
        raise EmailError(f"Failed to send email: {e}")


# ============================================================================
# Public API
# ============================================================================


async def send_verification_email(email: str, token: str) -> None:
    """Send email-verification link (token valid 24h)."""
    url = f"{FRONTEND_URL}/verify-email?token={token}"
    html = _render(
        "Verify your email",
        "Welcome to Arada! Please confirm your email address to activate your account. "
        "This link expires in 24 hours.",
        button_url=url,
        button_label="Verify Email",
    )
    await _send(email, "Verify your Arada account", html)


async def send_password_reset_email(email: str, token: str) -> None:
    """Send password-reset link (token valid 24h)."""
    url = f"{FRONTEND_URL}/reset-password?token={token}"
    html = _render(
        "Reset your password",
        "We received a request to reset your password. Click the button below to choose "
        "a new one. This link expires in 24 hours.",
        button_url=url,
        button_label="Reset Password",
    )
    await _send(email, "Reset your Arada password", html)


async def send_welcome_email(email: str, full_name: Optional[str] = None) -> None:
    """Send welcome email after verification."""
    name = full_name or "there"
    html = _render(
        f"Welcome, {name}! 🎉",
        "Your Arada account is ready. Connect your first content source, explore ML "
        "insights, and set up webhooks from your dashboard.",
        button_url=f"{FRONTEND_URL}/dashboard",
        button_label="Open Dashboard",
    )
    await _send(email, "Welcome to Arada Intelligence OS", html)


async def send_login_alert(email: str, ip: str, user_agent: str = "") -> None:
    """Notify user of a new login (security alert)."""
    html = _render(
        "New login to your account",
        f"A new login was detected.<br><br>"
        f"<b>IP address:</b> {ip}<br>"
        f"<b>Device:</b> {user_agent or 'Unknown'}<br><br>"
        "If this was you, no action is needed. If not, reset your password immediately.",
        button_url=f"{FRONTEND_URL}/settings/security",
        button_label="Review Security",
    )
    await _send(email, "New login to your Arada account", html)
