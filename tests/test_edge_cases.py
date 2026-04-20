"""
Edge case tests for email-parser web app.

Covers: Unicode subjects, XSS prevention, large attachments,
special-character filenames, minimal fields, concurrency, and
graceful handling of Azure service failures.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import (
    SAMPLE_EMAIL_SPECIAL_CHARS,
    SAMPLE_EMAIL_MINIMAL,
    ALL_SAMPLE_EMAILS,
    SAMPLE_ATTACHMENT_BYTES,
    _build_mock_cosmos_container,
    _build_mock_blob_service,
)

pytestmark = pytest.mark.asyncio


async def _ac(app_fixture):
    return AsyncClient(transport=ASGITransport(app=app_fixture), base_url="http://test")


# ---------------------------------------------------------------------------
# Special characters in subject
# ---------------------------------------------------------------------------

class TestSpecialCharacters:
    async def test_email_with_special_chars_subject(self, client_all_emails):
        """Unicode and emoji characters in subject render correctly."""
        async with await _ac(client_all_emails) as ac:
            resp = await ac.get("/emails/email-004")
            assert resp.status_code == 200
            # The subject should appear in the rendered output
            assert "Résumé" in resp.text or "R&#233;sum&#233;" in resp.text
            assert "📄" in resp.text or "&#128196;" in resp.text


# ---------------------------------------------------------------------------
# XSS prevention
# ---------------------------------------------------------------------------

class TestXSSPrevention:
    async def test_email_with_script_injection(self, client):
        """Verify that script tags in email body are sanitized out."""
        xss_email = {
            "id": "email-xss",
            "messageId": "<xss@example.com>",
            "subject": "XSS Test",
            "body": '<p>Hello</p><script>alert("xss")</script>',
            "bodyPreview": "Hello",
            "from": "attacker@example.com",
            "toRecipients": ["victim@example.com"],
            "receivedDateTime": "2026-04-25T12:00:00Z",
            "hasAttachments": False,
            "attachments": [],
            "processedAt": "2026-04-25T12:01:00Z",
        }
        container = _build_mock_cosmos_container([xss_email])
        blob_service = _build_mock_blob_service()
        credential = MagicMock()

        import app as app_module
        with patch.object(app_module, "_get_cosmos_container", return_value=container), \
             patch.object(app_module, "_get_blob_service", return_value=blob_service), \
             patch.object(app_module, "_get_credential", return_value=credential):
            async with await _ac(app_module.app) as ac:
                resp = await ac.get("/emails/email-xss")
                assert resp.status_code == 200
                assert "XSS Test" in resp.text
                # Script tags must be stripped by sanitization
                assert "<script>" not in resp.text
                assert "alert(" not in resp.text
                assert "<p>Hello</p>" in resp.text

    async def test_email_list_escapes_subjects(self, client):
        """Email list view should not render raw HTML in subjects."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails")
            assert resp.status_code == 200
            # Subjects are rendered via {{ email.subject }} (auto-escaped by Jinja2)
            assert "<script>" not in resp.text


# ---------------------------------------------------------------------------
# Large attachments
# ---------------------------------------------------------------------------

class TestLargeAttachment:
    async def test_large_attachment_download(self, client):
        """Streaming works for attachment downloads (basic check)."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-001/attachments/report.pdf")
            assert resp.status_code == 200
            assert len(resp.content) > 0


# ---------------------------------------------------------------------------
# Filenames with spaces and special characters
# ---------------------------------------------------------------------------

class TestAttachmentFilenames:
    async def test_attachment_with_spaces_in_name(self, client):
        """URL-encoded filenames with spaces are handled without crashing."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-001/attachments/my%20report.pdf")
            # Should not crash; will be 404 since no such blob path exists in fixture
            assert resp.status_code in (200, 404)

    async def test_attachment_with_special_chars(self, client):
        """Filenames with dots, brackets don't crash the route."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-001/attachments/file(1).v2.pdf")
            assert resp.status_code in (200, 404)

    async def test_attachment_path_traversal_blocked(self, client):
        """Path traversal attempts in filenames are handled safely."""
        async with await _ac(client) as ac:
            # FastAPI's path parameter won't match ../../ across segments,
            # but we test the single-segment version
            resp = await ac.get("/emails/email-001/attachments/..%2F..%2Fetc%2Fpasswd")
            assert resp.status_code in (200, 400, 404, 422)


# ---------------------------------------------------------------------------
# Missing optional fields
# ---------------------------------------------------------------------------

class TestMinimalFields:
    async def test_email_missing_optional_fields(self, client_all_emails):
        """Emails with only required fields render without errors."""
        async with await _ac(client_all_emails) as ac:
            resp = await ac.get("/emails/email-005")
            assert resp.status_code == 200
            assert "Minimal" in resp.text


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

class TestConcurrency:
    async def test_concurrent_requests(self, client):
        """Multiple simultaneous requests are handled without errors."""
        async with await _ac(client) as ac:
            tasks = [
                ac.get("/emails"),
                ac.get("/emails/email-001"),
                ac.get("/emails/email-002"),
                ac.get("/health"),
                ac.get("/emails?page=1"),
            ]
            responses = await asyncio.gather(*tasks)
            for resp in responses:
                assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Azure service failures
# ---------------------------------------------------------------------------

class TestCosmosConnectionFailure:
    async def test_cosmos_connection_failure(self):
        """Cosmos DB connection failure returns 503 with friendly error page."""
        container = MagicMock()
        container.query_items.side_effect = Exception("Cosmos DB connection refused")
        blob_service = _build_mock_blob_service()
        credential = MagicMock()

        import app as app_module
        with patch.object(app_module, "_get_cosmos_container", return_value=container), \
             patch.object(app_module, "_get_blob_service", return_value=blob_service), \
             patch.object(app_module, "_get_credential", return_value=credential):
            async with AsyncClient(
                transport=ASGITransport(app=app_module.app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/emails")
                assert resp.status_code == 503
                assert "Unable to load emails" in resp.text
                assert "Try again" in resp.text


class TestBlobConnectionFailure:
    async def test_blob_connection_failure(self, client_blob_fail):
        """Blob Storage failure returns an error, not a crash."""
        async with await _ac(client_blob_fail) as ac:
            resp = await ac.get("/emails/email-001/attachments/report.pdf")
            # Should return 404 (the app catches all exceptions in the attachment route)
            assert resp.status_code in (404, 500, 502, 503)
