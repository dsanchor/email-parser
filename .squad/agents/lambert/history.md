## Learnings

- **Project:** email-parser — Azure Logic App email processing pipeline
- **Stack:** Python, Azure (Logic Apps, Cosmos DB, Blob Storage, Container Apps), managed identities
- **Design:** Apple-inspired (DESIGN.md)
- **User:** dsanchor

### Web App (v1) — Built 2025-04-20
- **Framework:** FastAPI + Jinja2 templates + uvicorn
- **Key files:** `web-app/app.py`, `web-app/templates/`, `web-app/static/css/style.css`, `web-app/Dockerfile`
- **Auth pattern:** `DefaultAzureCredential` (managed identity in prod), falls back to connection string env vars for local dev (`COSMOS_KEY`, `STORAGE_CONNECTION_STRING`)
- **Config:** All via env vars — `COSMOS_ENDPOINT`, `COSMOS_DATABASE`, `COSMOS_CONTAINER`, `STORAGE_ACCOUNT_URL`, `STORAGE_CONTAINER`
- **Routes:** `GET /` → redirect `/emails`, `GET /emails` (paginated list + search), `GET /emails/{id}` (detail), `GET /emails/{id}/attachments/{filename}` (blob download), `GET /health`
- **Design decisions:** Binary dark/light sections on detail page (dark hero for subject/meta, white for body, light gray for attachments). Card-based inbox list. Search bar with filter-style input. Pagination with pill buttons.
- **Dockerfile:** python:3.12-slim, non-root user, port 8000
- **CSS:** Full DESIGN.md compliance — glass nav, Apple Blue only accent, negative letter-spacing at all sizes, 980px pill radius CTAs, card shadows per spec

### Quality Issues — From Kane Testing (2026-04-20)

**🔴 CRITICAL: XSS Vulnerability in email_detail.html**
- **Location:** `web-app/templates/email_detail.html`
- **Issue:** Template uses `{{ email.body | safe }}` which renders email body HTML unescaped
- **Risk:** Malicious email content from Office 365 could inject JavaScript into rendering
- **Impact:** Session hijacking, credential theft, malware distribution potential
- **Fix:** Sanitize email.body before template rendering using `nh3` or `bleach` library
- **Steps:**
  1. Add sanitizer library to requirements.txt (`nh3>=0.2.0` recommended for performance)
  2. Create sanitize utility: `_sanitize_html(body)` in app.py
  3. Update `/emails/{id}` route to call `_sanitize_html()` on email.body before passing to template
  4. Change template to `{{ email.body }}` (remove | safe filter)
  5. Add test case in tests/test_app.py for XSS attack patterns

**🟡 HIGH: Missing Error Handling in Route Handlers**
- **Location:** `/emails` and `/emails/{id}` routes
- **Issue:** Cosmos DB exceptions not caught — propagate as raw 500 errors
- **Effect:** Users see generic error pages; developers can't distinguish Cosmos failures from app bugs
- **Fix:** Wrap `query_items()` calls in try/except
- **Steps:**
  1. Create error handler middleware in app.py
  2. Catch `azure.cosmos.exceptions.CosmosResourceNotFoundError` for 404 cases
  3. Catch `azure.cosmos.exceptions.CosmosHttpResponseError` for general Cosmos failures
  4. Return appropriate status codes + render error.html with user-friendly messages
  5. Add test cases for query failures

---
