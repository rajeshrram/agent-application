"""Send the manager's daily summary email.

This is the highest-stakes WRITE in the system -- see
graphs/daily_collation.py for the optional human-approval interrupt gating
this call (config.REQUIRE_SUMMARY_APPROVAL).
"""
from datetime import datetime
from typing import Dict, Optional

from src import config


def send_email(to: str, subject: str, body: str, html_body: Optional[str] = None) -> Dict:
    """`body` is the plain-text version (also what's stored as the draft /
    shown in the dashboard). `html_body`, if given, is sent alongside it as
    a multipart/alternative -- most mail clients render the HTML part and
    fall back to plain text automatically."""
    if config.GMAIL_MOCK:
        note = " (+ HTML part)" if html_body else ""
        print(f"[gmail_tool:MOCK] -> {to}{note}\nSubject: {subject}\n\n{body}\n")
        return {"sent_at": datetime.utcnow().isoformat(), "to": to}
    return _send_real(to, subject, body, html_body)


def _send_real(to: str, subject: str, body: str, html_body: Optional[str] = None) -> Dict:
    """TODO (Day 3): one-time `python scripts/gmail_auth.py` to produce
    token.json via the OAuth consent flow (scope: gmail.send), then this
    path works unattended."""
    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(config.GMAIL_TOKEN_PATH, ["https://www.googleapis.com/auth/gmail.send"])
    service = build("gmail", "v1", credentials=creds)

    if html_body:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(body, "plain"))
        message.attach(MIMEText(html_body, "html"))
    else:
        message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
    except Exception as exc:  # noqa: BLE001 -- surface any Gmail API failure
        print(f"[gmail_tool] send failed: {exc}")
        raise
    return {"sent_at": datetime.utcnow().isoformat(), "to": to}
