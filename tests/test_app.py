"""
Unit tests for email-parser web app routes.

Tests cover all five routes:
  GET /           → redirect to /emails
  GET /emails     → paginated email list
  GET /emails/{id}          → email detail
  GET /emails/{id}/attachments/{filename} → attachment download
  GET /health     → health check

The app uses synchronous Azure SDK (Cosmos, Blob) inside async FastAPI routes.
Fixtures patch _get_cosmos_container() and _get_blob_service() at module level.
"""

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


# Helper to build an async test client from a patched app fixture
async def _ac(app_fixture):
    return AsyncClient(transport=ASGITransport(app=app_fixture), base_url="http://test")


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    async def test_health_endpoint(self, client):
        """GET /health returns 200 with status healthy."""
        async with await _ac(client) as ac:
            resp = await ac.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

class TestRootRedirect:
    async def test_root_redirect(self, client):
        """GET / redirects to /emails."""
        async with await _ac(client) as ac:
            resp = await ac.get("/", follow_redirects=False)
            assert resp.status_code in (301, 302, 307, 308)
            assert "/emails" in resp.headers.get("location", "")


# ---------------------------------------------------------------------------
# Email list
# ---------------------------------------------------------------------------

class TestEmailsList:
    async def test_emails_list(self, client):
        """GET /emails returns 200 and renders email data."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails")
            assert resp.status_code == 200
            assert "Q4 Financial Report" in resp.text
            assert "Team standup notes" in resp.text
            assert "Design assets" in resp.text

    async def test_emails_list_pagination(self, client):
        """GET /emails?page=2 handles page parameter."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails?page=2")
            assert resp.status_code == 200

    async def test_emails_list_page_one(self, client):
        """GET /emails?page=1 returns first page."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails?page=1")
            assert resp.status_code == 200

    async def test_emails_list_empty(self, client_empty):
        """GET /emails with no emails returns 200 (empty state)."""
        async with await _ac(client_empty) as ac:
            resp = await ac.get("/emails")
            assert resp.status_code == 200
            assert "No emails yet" in resp.text


# ---------------------------------------------------------------------------
# Email detail
# ---------------------------------------------------------------------------

class TestEmailDetail:
    async def test_email_detail(self, client):
        """GET /emails/{id} returns 200 with full email data."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-001")
            assert resp.status_code == 200
            assert "Q4 Financial Report" in resp.text
            assert "cfo@example.com" in resp.text
            assert "report.pdf" in resp.text
            assert "summary.docx" in resp.text

    async def test_email_detail_not_found(self, client):
        """GET /emails/{id} returns 404 for non-existent email."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/nonexistent-id")
            assert resp.status_code == 404

    async def test_email_detail_no_attachments(self, client):
        """GET /emails/{id} handles email without attachments."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-002")
            assert resp.status_code == 200
            assert "Team standup notes" in resp.text
            # Should NOT show attachments section
            assert "Attachments" not in resp.text


# ---------------------------------------------------------------------------
# Attachment download
# ---------------------------------------------------------------------------

class TestAttachmentDownload:
    async def test_attachment_download(self, client):
        """GET /emails/{id}/attachments/{filename} returns binary data."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-001/attachments/report.pdf")
            assert resp.status_code == 200
            assert len(resp.content) > 0

    async def test_attachment_download_not_found(self, client_blob_fail):
        """Attachment download returns 404 when blob doesn't exist."""
        async with await _ac(client_blob_fail) as ac:
            resp = await ac.get("/emails/email-001/attachments/nonexistent.pdf")
            assert resp.status_code == 404

    async def test_attachment_download_email_not_found(self, client_blob_fail):
        """Attachment download returns 404 when blob fetch fails."""
        async with await _ac(client_blob_fail) as ac:
            resp = await ac.get("/emails/nonexistent/attachments/file.pdf")
            assert resp.status_code == 404

    async def test_attachment_content_disposition(self, client):
        """Attachment download sets Content-Disposition header."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-001/attachments/report.pdf")
            assert resp.status_code == 200
            cd = resp.headers.get("content-disposition", "")
            assert "report.pdf" in cd

    async def test_attachment_various_types_pdf(self, client):
        """PDF attachment download works."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-001/attachments/report.pdf")
            assert resp.status_code == 200

    async def test_attachment_various_types_docx(self, client):
        """DOCX attachment download works."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-001/attachments/summary.docx")
            assert resp.status_code == 200

    async def test_attachment_various_types_png(self, client):
        """PNG attachment download works."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-003/attachments/logo.png")
            assert resp.status_code == 200

    async def test_attachment_various_types_jpg(self, client):
        """JPG attachment download works."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-003/attachments/banner.jpg")
            assert resp.status_code == 200

    async def test_attachment_various_types_zip(self, client):
        """ZIP attachment download works."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-003/attachments/assets.zip")
            assert resp.status_code == 200

    async def test_attachment_various_types_xlsx(self, client):
        """XLSX attachment download works."""
        async with await _ac(client) as ac:
            resp = await ac.get("/emails/email-003/attachments/budget.xlsx")
            assert resp.status_code == 200
