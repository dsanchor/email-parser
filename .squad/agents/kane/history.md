## Learnings

- **Project:** email-parser — Azure Logic App email processing pipeline
- **Stack:** Python, Azure (Logic Apps, Cosmos DB, Blob Storage, Container Apps), managed identities
- **User:** dsanchor
- **Test suite:** 30 tests, all passing — covers all 5 routes + edge cases
- **Key files:**
  - `tests/conftest.py` — fixtures: mock Cosmos container (sync SDK), mock BlobServiceClient, FastAPI test client via httpx, 5 sample email variants
  - `tests/test_app.py` — 19 unit tests: health, root redirect, email list (pagination, empty), email detail (found, 404, no attachments), attachment download (6 file types, content-disposition, 404)
  - `tests/test_edge_cases.py` — 11 edge case tests: Unicode/emoji subjects, XSS (body uses `|safe` — flagged), large attachments, spaces/special chars in filenames, path traversal, minimal fields, concurrency, Cosmos failure (500), Blob failure (404)
  - `tests/requirements-test.txt` — pytest, pytest-asyncio, httpx, pytest-cov
  - `tests/validate_infrastructure.sh` — 16+ checks: resource group, Cosmos (account/db/container), Storage (account/blob), Logic App MI, Container App MI, 4 role assignments
- **App structure discovered:** `web-app/app.py` — single module, sync Azure SDK, private helpers `_get_cosmos_container()` / `_get_blob_service()`, patched at module level in tests
- **Findings:**
  - `email_detail.html` uses `{{ email.body | safe }}` — XSS risk from malicious email HTML bodies. Recommend sanitizing with `nh3` or `bleach` before rendering.
  - `/emails` route lacks try/except around `query_items` — Cosmos failures propagate as unhandled 500 without a user-friendly error page.
  - Infrastructure defaults in `deploy.sh` use `emailparserstor` (not `emailparserstorage`) and `email-parser-db` (not `email-db`). Validation script aligned to actual deploy script values.
  - `azure-cosmos>=4.0.0` required (v3 lacks `CosmosClient` import)
