import base64
import logging
import mimetypes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from jinja2 import Environment, FileSystemLoader

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

_service = None
_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "templates")
)


def _get_service():
    global _service
    if _service is not None:
        return _service

    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    creds = creds.with_subject(settings.GOOGLE_DELEGATED_EMAIL)
    creds.refresh(Request())
    _service = build("gmail", "v1", credentials=creds)
    return _service


def register_watch() -> dict:
    """Register Gmail push notifications via Pub/Sub."""
    service = _get_service()
    body = {
        "topicName": settings.GOOGLE_PUBSUB_TOPIC,
        "labelIds": ["INBOX"],
    }
    result = service.users().watch(userId="me", body=body).execute()
    logger.info("Gmail watch registered: %s", result)
    return result


def get_history(start_history_id: str) -> list[dict]:
    """Fetch message history since a given historyId."""
    service = _get_service()
    messages = []
    try:
        response = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                labelIds=["INBOX"],
            )
            .execute()
        )
        for record in response.get("history", []):
            for msg in record.get("messagesAdded", []):
                messages.append(msg["message"])
    except Exception as e:
        logger.error("Failed to get history: %s", e)
    return messages


def get_message(message_id: str) -> dict:
    """Get a full message by ID."""
    service = _get_service()
    return (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )


def get_thread(thread_id: str) -> dict:
    """Get a full thread by ID."""
    service = _get_service()
    return (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )


def _extract_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def parse_message(message: dict) -> dict:
    """Extract useful fields from a Gmail message."""
    headers = message.get("payload", {}).get("headers", [])
    body_text = _extract_body(message.get("payload", {}))
    return {
        "id": message["id"],
        "threadId": message["threadId"],
        "from": _extract_header(headers, "From"),
        "to": _extract_header(headers, "To"),
        "subject": _extract_header(headers, "Subject"),
        "date": _extract_header(headers, "Date"),
        "message_id": _extract_header(headers, "Message-ID"),
        "in_reply_to": _extract_header(headers, "In-Reply-To"),
        "references": _extract_header(headers, "References"),
        "body": body_text,
        "labels": message.get("labelIds", []),
    }


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body from payload."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


def _render_signature() -> str:
    from app.config_loader import get_config

    template = _jinja_env.get_template("signature.html")
    try:
        config = get_config()
        return template.render(
            company_name=config.business.name,
            phone=config.business.phone,
            website=config.business.website,
            messenger_link=settings.TELEGRAM_BOT_LINK,
        )
    except RuntimeError:
        # Fallback if config not loaded yet (e.g. during tests)
        return template.render(
            company_name=settings.COMPANY_NAME,
            phone=settings.COMPANY_PHONE,
            website=settings.COMPANY_WEBSITE,
            messenger_link=settings.TELEGRAM_BOT_LINK,
        )


def send_reply(
    to: str,
    subject: str,
    body_html: str,
    thread_id: str,
    message_id: str,
    references: str = "",
    attachment_path: str | None = None,
) -> dict:
    """Send an email reply, optionally with an attachment."""
    service = _get_service()

    signature = _render_signature()
    full_html = f"{body_html}<br><br>{signature}"

    msg = MIMEMultipart()
    msg["To"] = to
    msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
    msg["In-Reply-To"] = message_id
    msg["References"] = f"{references} {message_id}".strip()

    msg.attach(MIMEText(full_html, "html", "utf-8"))

    if attachment_path:
        path = Path(attachment_path)
        if path.exists():
            content_type, _ = mimetypes.guess_type(str(path))
            main_type, sub_type = (content_type or "application/octet-stream").split(
                "/", 1
            )
            with open(path, "rb") as f:
                att = MIMEBase(main_type, sub_type)
                att.set_payload(f.read())
            from email import encoders

            encoders.encode_base64(att)
            att.add_header(
                "Content-Disposition", "attachment", filename=path.name
            )
            msg.attach(att)
        else:
            logger.warning("Attachment not found: %s", attachment_path)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    result = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": thread_id})
        .execute()
    )
    logger.info("Sent reply to %s, messageId=%s", to, result.get("id"))
    return result
