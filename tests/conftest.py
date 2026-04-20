"""
Pytest fixtures for email-parser web app tests.

Aligned with the actual web-app/app.py implementation:
- Synchronous Cosmos & Blob SDK
- Private helpers: _get_cosmos_container(), _get_blob_service()
- FastAPI app at web-app/app.py
"""

import os
import sys
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure web-app/ is on the import path
WEB_APP_DIR = os.path.join(os.path.dirname(__file__), "..", "web-app")
if WEB_APP_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(WEB_APP_DIR))


# ---------------------------------------------------------------------------
# Sample email data
# ---------------------------------------------------------------------------

SAMPLE_EMAIL_WITH_ATTACHMENTS = {
    "id": "email-001",
    "messageId": "<msg-001@example.com>",
    "subject": "Q4 Financial Report",
    "body": "<html><body><p>Please find the Q4 report attached.</p></body></html>",
    "bodyPreview": "Please find the Q4 report attached.",
    "from": "cfo@example.com",
    "toRecipients": ["team@example.com"],
    "receivedDateTime": "2026-04-20T12:00:00Z",
    "hasAttachments": True,
    "importance": "normal",
    "conversationId": "conv-001",
    "attachments": [
        {
            "name": "report.pdf",
            "contentType": "application/pdf",
            "size": 125000,
            "blobPath": "email-attachments/email-001/report.pdf",
        },
        {
            "name": "summary.docx",
            "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": 45000,
            "blobPath": "email-attachments/email-001/summary.docx",
        },
    ],
    "processedAt": "2026-04-20T12:01:00Z",
}

SAMPLE_EMAIL_NO_ATTACHMENTS = {
    "id": "email-002",
    "messageId": "<msg-002@example.com>",
    "subject": "Team standup notes",
    "body": "<html><body><p>Today's standup went well.</p></body></html>",
    "bodyPreview": "Today's standup went well.",
    "from": "pm@example.com",
    "toRecipients": ["team@example.com"],
    "receivedDateTime": "2026-04-21T09:00:00Z",
    "hasAttachments": False,
    "importance": "normal",
    "conversationId": "conv-002",
    "attachments": [],
    "processedAt": "2026-04-21T09:01:00Z",
}

SAMPLE_EMAIL_MULTIPLE_ATTACHMENTS = {
    "id": "email-003",
    "messageId": "<msg-003@example.com>",
    "subject": "Design assets",
    "body": "<html><body><p>Assets for the new campaign.</p></body></html>",
    "bodyPreview": "Assets for the new campaign.",
    "from": "designer@example.com",
    "toRecipients": ["marketing@example.com"],
    "receivedDateTime": "2026-04-22T14:30:00Z",
    "hasAttachments": True,
    "importance": "high",
    "conversationId": "conv-003",
    "attachments": [
        {
            "name": "logo.png",
            "contentType": "image/png",
            "size": 250000,
            "blobPath": "email-attachments/email-003/logo.png",
        },
        {
            "name": "banner.jpg",
            "contentType": "image/jpeg",
            "size": 500000,
            "blobPath": "email-attachments/email-003/banner.jpg",
        },
        {
            "name": "assets.zip",
            "contentType": "application/zip",
            "size": 2000000,
            "blobPath": "email-attachments/email-003/assets.zip",
        },
        {
            "name": "budget.xlsx",
            "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": 75000,
            "blobPath": "email-attachments/email-003/budget.xlsx",
        },
    ],
    "processedAt": "2026-04-22T14:31:00Z",
}

SAMPLE_EMAIL_SPECIAL_CHARS = {
    "id": "email-004",
    "messageId": "<msg-004@example.com>",
    "subject": "Résumé update 📄 — año 2026 «important»",
    "body": "<html><body><p>Héllo wörld — special chars: &amp; &lt; &gt;</p></body></html>",
    "bodyPreview": "Héllo wörld — special chars: & < >",
    "from": "josé@example.com",
    "toRecipients": ["hr@example.com"],
    "receivedDateTime": "2026-04-23T10:00:00Z",
    "hasAttachments": False,
    "importance": "normal",
    "conversationId": "conv-004",
    "attachments": [],
    "processedAt": "2026-04-23T10:01:00Z",
}

SAMPLE_EMAIL_MINIMAL = {
    "id": "email-005",
    "subject": "Minimal",
    "from": "someone@example.com",
    "receivedDateTime": "2026-04-24T08:00:00Z",
    "processedAt": "2026-04-24T08:01:00Z",
}

ALL_SAMPLE_EMAILS = [
    SAMPLE_EMAIL_WITH_ATTACHMENTS,
    SAMPLE_EMAIL_NO_ATTACHMENTS,
    SAMPLE_EMAIL_MULTIPLE_ATTACHMENTS,
]

SAMPLE_ATTACHMENT_BYTES = b"%PDF-1.4 fake pdf content for testing purposes"


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------

def _build_mock_cosmos_container(emails):
    """Build a MagicMock Cosmos container whose query_items returns *emails*."""
    container = MagicMock()

    def _query_items(query, parameters=None, **kwargs):
        # Simulate filtering for detail queries (WHERE c.id = @id)
        if parameters:
            for p in parameters:
                if p["name"] == "@id":
                    return [e for e in emails if e["id"] == p["value"]]
                if p["name"] == "@q":
                    q = p["value"].lower()
                    return [
                        e for e in emails
                        if q in e.get("subject", "").lower() or q in e.get("from", "").lower()
                    ]
        return list(emails)

    container.query_items = _query_items
    return container


def _build_mock_blob_service(should_fail=False):
    """Build a MagicMock BlobServiceClient.

    When *should_fail* is True, download_blob raises an exception.
    """
    blob_service = MagicMock()
    container_client = MagicMock()

    if should_fail:
        blob_client = MagicMock()
        blob_client.download_blob.side_effect = Exception("BlobNotFound")
        container_client.get_blob_client.return_value = blob_client
    else:
        blob_client = MagicMock()
        download_stream = MagicMock()

        # Simulate properties
        content_settings = MagicMock()
        content_settings.content_type = "application/pdf"
        props = MagicMock()
        props.content_settings = content_settings
        props.size = len(SAMPLE_ATTACHMENT_BYTES)
        download_stream.properties = props
        download_stream.chunks.return_value = iter([SAMPLE_ATTACHMENT_BYTES])

        blob_client.download_blob.return_value = download_stream
        container_client.get_blob_client.return_value = blob_client

    blob_service.get_container_client.return_value = container_client
    return blob_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cosmos_container():
    return _build_mock_cosmos_container(ALL_SAMPLE_EMAILS)


@pytest.fixture
def mock_cosmos_container_all():
    """Contains ALL sample emails including special chars and minimal."""
    return _build_mock_cosmos_container(
        ALL_SAMPLE_EMAILS + [SAMPLE_EMAIL_SPECIAL_CHARS, SAMPLE_EMAIL_MINIMAL]
    )


@pytest.fixture
def mock_cosmos_container_empty():
    return _build_mock_cosmos_container([])


@pytest.fixture
def mock_blob_service():
    return _build_mock_blob_service(should_fail=False)


@pytest.fixture
def mock_blob_service_failing():
    return _build_mock_blob_service(should_fail=True)


@pytest.fixture
def mock_credential():
    return MagicMock()


# ---------------------------------------------------------------------------
# App + client helpers
# ---------------------------------------------------------------------------

def _import_app():
    """Import (or reimport) the FastAPI app with patches already in place."""
    # Force re-import to pick up patches on module-level globals
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_module
    return app_module.app


def _make_patches(cosmos_container, blob_service, credential):
    """Return a list of context managers that patch the app's Azure clients."""
    return [
        patch("app._get_cosmos_container", return_value=cosmos_container),
        patch("app._get_blob_service", return_value=blob_service),
        patch("app._get_credential", return_value=credential),
    ]


@pytest.fixture
def client(mock_cosmos_container, mock_blob_service, mock_credential):
    """Synchronous-style fixture that yields an async client (used with pytest-asyncio)."""
    import app as app_module

    with patch.object(app_module, "_get_cosmos_container", return_value=mock_cosmos_container), \
         patch.object(app_module, "_get_blob_service", return_value=mock_blob_service), \
         patch.object(app_module, "_get_credential", return_value=mock_credential):
        yield app_module.app


@pytest.fixture
def client_all_emails(mock_cosmos_container_all, mock_blob_service, mock_credential):
    """Client with all sample emails including special chars and minimal."""
    import app as app_module

    with patch.object(app_module, "_get_cosmos_container", return_value=mock_cosmos_container_all), \
         patch.object(app_module, "_get_blob_service", return_value=mock_blob_service), \
         patch.object(app_module, "_get_credential", return_value=mock_credential):
        yield app_module.app


@pytest.fixture
def client_empty(mock_cosmos_container_empty, mock_blob_service, mock_credential):
    """Client with empty Cosmos DB."""
    import app as app_module

    with patch.object(app_module, "_get_cosmos_container", return_value=mock_cosmos_container_empty), \
         patch.object(app_module, "_get_blob_service", return_value=mock_blob_service), \
         patch.object(app_module, "_get_credential", return_value=mock_credential):
        yield app_module.app


@pytest.fixture
def client_blob_fail(mock_cosmos_container, mock_blob_service_failing, mock_credential):
    """Client where blob downloads always fail."""
    import app as app_module

    with patch.object(app_module, "_get_cosmos_container", return_value=mock_cosmos_container), \
         patch.object(app_module, "_get_blob_service", return_value=mock_blob_service_failing), \
         patch.object(app_module, "_get_credential", return_value=mock_credential):
        yield app_module.app
