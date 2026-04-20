"""Email Parser Web App — Browse emails from Cosmos DB, download attachments from Blob Storage."""

import logging
import os
import math
from datetime import datetime

import bleach
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from azure.cosmos import CosmosClient
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "email-parser-db")
COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "emails")
COSMOS_KEY = os.environ.get("COSMOS_KEY", "")  # optional – local dev only

STORAGE_ACCOUNT_URL = os.environ.get("STORAGE_ACCOUNT_URL", "")
STORAGE_CONTAINER = os.environ.get("STORAGE_CONTAINER", "email-attachments")
STORAGE_CONNECTION_STRING = os.environ.get("STORAGE_CONNECTION_STRING", "")  # optional – local dev

PAGE_SIZE = 20

# ---------------------------------------------------------------------------
# Azure clients (lazy init)
# ---------------------------------------------------------------------------
_credential = None
_cosmos_client = None
_blob_service = None


def _get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def _get_cosmos_container():
    global _cosmos_client
    if _cosmos_client is None:
        if COSMOS_KEY:
            _cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
        else:
            _cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=_get_credential())
    db = _cosmos_client.get_database_client(COSMOS_DATABASE)
    return db.get_container_client(COSMOS_CONTAINER)


def _get_blob_service():
    global _blob_service
    if _blob_service is None:
        if STORAGE_CONNECTION_STRING:
            _blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
        else:
            _blob_service = BlobServiceClient(STORAGE_ACCOUNT_URL, credential=_get_credential())
    return _blob_service


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Email Parser")

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
def _format_date(value: str) -> str:
    """Turn ISO date string into a friendly display string."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except Exception:
        return value


def _human_size(size_bytes) -> str:
    """Convert bytes to human-readable size."""
    if size_bytes is None:
        return ""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


ALLOWED_TAGS = [
    "p", "br", "strong", "em", "a", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "tr", "td", "th", "thead", "tbody",
    "img", "span", "div", "blockquote", "b", "i", "u",
    "html", "body", "head",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target"],
    "img": ["src", "alt", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    "*": ["style", "class"],
}


def sanitize_html(html: str) -> str:
    """Strip dangerous tags/attributes while preserving safe formatting HTML."""
    import re
    # Remove script/style tags and their content entirely before bleach processing
    cleaned = re.sub(r'<(script|style|iframe|object|embed|form|input|textarea|select|button)\b[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<(script|style|iframe|object|embed|form|input|textarea|select|button)\b[^>]*/>', '', cleaned, flags=re.IGNORECASE)
    return bleach.clean(
        cleaned,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )


templates.env.filters["format_date"] = _format_date
templates.env.filters["human_size"] = _human_size


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return RedirectResponse(url="/emails")


@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy"})


@app.get("/emails", response_class=HTMLResponse)
async def email_list(request: Request, page: int = Query(1, ge=1), q: str = Query("")):
    try:
        container = _get_cosmos_container()

        # Build query
        if q:
            query_text = (
                "SELECT * FROM c WHERE CONTAINS(LOWER(c.subject), LOWER(@q)) "
                "OR CONTAINS(LOWER(c['from']), LOWER(@q)) "
                "ORDER BY c.receivedDateTime DESC"
            )
            params = [{"name": "@q", "value": q}]
        else:
            query_text = "SELECT * FROM c ORDER BY c.receivedDateTime DESC"
            params = []

        items = list(
            container.query_items(query=query_text, parameters=params, enable_cross_partition_query=True)
        )
    except Exception:
        logger.exception("Failed to fetch emails from Cosmos DB")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "code": 503, "message": "Unable to load emails. Please try again later."},
            status_code=503,
        )

    total = len(items)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE
    page_items = items[offset : offset + PAGE_SIZE]

    return templates.TemplateResponse(
        "emails.html",
        {
            "request": request,
            "emails": page_items,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "q": q,
        },
    )


@app.get("/emails/{email_id}", response_class=HTMLResponse)
async def email_detail(request: Request, email_id: str):
    try:
        container = _get_cosmos_container()

        query_text = "SELECT * FROM c WHERE c.id = @id"
        params = [{"name": "@id", "value": email_id}]
        results = list(
            container.query_items(query=query_text, parameters=params, enable_cross_partition_query=True)
        )
    except Exception:
        logger.exception("Failed to fetch email detail from Cosmos DB")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "code": 503, "message": "Unable to load this email. Please try again later."},
            status_code=503,
        )

    if not results:
        raise HTTPException(status_code=404, detail="Email not found")

    email = results[0]
    # Sanitize email body to prevent XSS
    if "body" in email:
        email["body"] = sanitize_html(email["body"])
    return templates.TemplateResponse("email_detail.html", {"request": request, "email": email})


@app.get("/emails/{email_id}/attachments/{filename}")
async def download_attachment(email_id: str, filename: str):
    blob_service = _get_blob_service()
    container_client = blob_service.get_container_client(STORAGE_CONTAINER)
    blob_path = f"{email_id}/{filename}"

    try:
        blob_client = container_client.get_blob_client(blob_path)
        download = blob_client.download_blob()
        properties = download.properties

        content_type = properties.content_settings.content_type or "application/octet-stream"

        return StreamingResponse(
            download.chunks(),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(properties.size),
            },
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Attachment not found")


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse("error.html", {"request": request, "code": 404, "message": "Not Found"}, status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    return templates.TemplateResponse("error.html", {"request": request, "code": 500, "message": "Something went wrong"}, status_code=500)
