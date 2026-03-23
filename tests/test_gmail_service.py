"""Tests for Gmail service helper functions."""

from app.routers.gmail_webhook import _extract_email, _extract_name


def test_extract_email_with_name():
    assert _extract_email("John Doe <john@example.com>") == "john@example.com"


def test_extract_email_plain():
    assert _extract_email("john@example.com") == "john@example.com"


def test_extract_email_empty():
    assert _extract_email("no email here") == ""


def test_extract_name_with_brackets():
    assert _extract_name("John Doe <john@example.com>") == "John Doe"


def test_extract_name_quoted():
    assert _extract_name('"John Doe" <john@example.com>') == "John Doe"


def test_extract_name_no_brackets():
    assert _extract_name("john@example.com") == ""


def test_parse_message_body():
    """Test body extraction from a Gmail message payload."""
    import base64

    from app.services.gmail_service import parse_message

    body_text = "Привет, интересует мебель"
    encoded = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("utf-8")

    message = {
        "id": "msg1",
        "threadId": "thread1",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Test <test@example.com>"},
                {"name": "To", "value": "me@company.com"},
                {"name": "Subject", "value": "Re: Мебель"},
                {"name": "Date", "value": "Mon, 23 Mar 2026 12:00:00 +0300"},
                {"name": "Message-ID", "value": "<abc@example.com>"},
                {"name": "In-Reply-To", "value": ""},
                {"name": "References", "value": ""},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded},
        },
    }

    parsed = parse_message(message)
    assert parsed["from"] == "Test <test@example.com>"
    assert parsed["subject"] == "Re: Мебель"
    assert parsed["body"] == body_text
    assert parsed["threadId"] == "thread1"
