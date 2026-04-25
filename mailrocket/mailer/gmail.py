"""Gmail API wrapper. Reads OAuth credentials from settings.secrets paths."""
from __future__ import annotations

import base64
import logging
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from mailrocket.settings import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def get_gmail_credentials() -> Credentials:
    """Load OAuth credentials, refreshing or running the flow as needed."""
    client_secret_path = settings.secrets.gmail_client_secret_path
    token_path = settings.secrets.gmail_token_path

    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secret_path.exists():
                raise FileNotFoundError(
                    f"Missing Gmail client secret at {client_secret_path}. "
                    f"Download it from Google Cloud Console and save there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        with token_path.open("w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def send_email_via_gmail_api(
    subject: str,
    body: str,
    to_email: str,
    from_email: str,
    pdf_file_path: Path | str | None = None,
) -> dict:
    """Send a plaintext (optionally PDF-attached) email through the Gmail API."""
    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)

    if pdf_file_path:
        pdf_path = Path(pdf_file_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        message = MIMEMultipart()
        message["to"] = to_email
        message["subject"] = subject
        if from_email:
            message["From"] = from_email
        message.attach(MIMEText(body, "plain"))

        with pdf_path.open("rb") as pdf_file:
            attachment = MIMEApplication(pdf_file.read(), _subtype="pdf")
            attachment.add_header(
                "Content-Disposition", f'attachment; filename="{pdf_path.name}"'
            )
            message.attach(attachment)
    else:
        message = MIMEText(body)
        message["to"] = to_email
        message["subject"] = subject
        if from_email:
            message["From"] = from_email

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()
