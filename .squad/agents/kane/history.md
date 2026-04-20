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
- **Constraint discovered:** `azure-cosmos>=4.0.0` required (v3 lacks `CosmosClient` import)

### Quality Issues Identified — Session 2026-04-20

**🔴 CRITICAL: XSS Risk in email_detail.html**
- **Discovery:** Template uses `{{ email.body | safe }}` flag
- **Root cause:** Email bodies from Office 365 are untrusted user-controlled input
- **Risk:** JavaScript injection, session hijacking, credential theft
- **Recommendation:** Sanitize with `nh3` or `bleach` library before template rendering
- **Assigned to:** Lambert (template owner)
- **Status:** Flagged in decisions.md — awaiting fix

**🟡 HIGH: Missing Error Handling on Route Handlers**
- **Discovery:** `/emails` and `/emails/{id}` routes lack try/except around Cosmos queries
- **Effect:** Cosmos failures propagate as raw 500 errors; no user-friendly error page
- **Cosmos exceptions to handle:**
  - `azure.cosmos.exceptions.CosmosResourceNotFoundError` → 404
  - `azure.cosmos.exceptions.CosmosHttpResponseError` → 500 with error.html
- **Assigned to:** Lambert (route owner)
- **Status:** Flagged in decisions.md — awaiting implementation

### Test Execution Results (2026-04-20)

- ✅ All 30 tests passing
- ✅ Infrastructure validation script ready (16+ Azure resource checks)
- ✅ Edge cases covered (XSS payloads tested, path traversal, Unicode handling)
- ✅ Concurrent request handling verified
- ✅ Blob download with content-disposition headers tested

### Known Constraints

- `azure-cosmos` version constraint: `>=4.0.0` — v3 has incompatible API
- Default storage account name in deploy.sh: `emailparserstor` (not `emailparserstorage`)
- Default Cosmos database: `email-parser-db` (not `email-db`)
- Validation script aligned to actual deploy.sh defaults
