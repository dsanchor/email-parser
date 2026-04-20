# Squad Decisions

## Active Decisions

### Architecture Decisions — Dallas

**Date:** 2025-07-17 | **Status:** Approved

#### Cosmos DB Schema
- **Database:** `email-parser-db`, **Container:** `emails`, **Partition Key:** `/messageId`
- Serverless capacity mode — pay-per-request for bursty workloads
- Attachments embedded as array to avoid cross-document joins
- `bodyPreview` stored separately from `body` for fast list rendering
- `processedAt` tracks Logic App processing time

#### Blob Storage Convention
- **Container:** `email-attachments`
- **Path format:** `email-attachments/{emailId}/{original-filename}`
- `emailId` = Cosmos document id (GUID)
- All file types accepted — no content-type filtering

#### Logic App Type
- **Logic App Standard** (kind: `functionapp,workflowapp`) on WS1 App Service Plan
- Stateful workflow for reliable delivery and retry support
- System-assigned managed identity for Cosmos DB and Blob Storage
- Office 365 Outlook connector with OAuth2

#### Managed Identity Roles
| Service | Target | Role | Role ID |
|---------|--------|------|---------|
| Logic App | Storage | Storage Blob Data Contributor | ba92f5b4-2d11-453d-a403-e96b0029c9fe |
| Logic App | Cosmos DB | Cosmos DB Built-in Data Contributor | 00000000-0000-0000-0000-000000000002 |
| Container App | Storage | Storage Blob Data Reader | 2a2b9908-6ea1-4ae2-8e65-a410df84e7d1 |
| Container App | Cosmos DB | Cosmos DB Built-in Data Reader | 00000000-0000-0000-0000-000000000001 |
| Container App | ghcr.io | (pull via GHCR credentials on Container App) | — |

#### Web Framework
- **Recommendation: FastAPI** (Python 3.12)
- Async-native for concurrent Cosmos DB and Blob Storage calls
- Jinja2 templates for server-rendered HTML (Apple design system)
- `azure-identity` `DefaultAzureCredential` for managed identity
- `azure-cosmos` and `azure-storage-blob` SDKs

#### Security Model
- Zero connection strings — all managed identity
- No SAS tokens, no storage keys, no Cosmos DB master keys
- HTTPS everywhere
- O365 connector is the only interactive auth

---

### Infrastructure Architecture — Ripley

**Date:** 2025-01-20 | **Status:** Approved

#### Key Decisions
1. **Cosmos DB partition key is `/messageId`** — unique distribution, thread lookups
2. **Managed identity everywhere** — no connection strings in app config
3. **Cosmos DB serverless** — cost-effective for sporadic email arrival
4. **splitOn retained on trigger** — webhook reliability, independent email processing
5. **Sequential attachment processing** — ForEach concurrency = 1 to prevent race conditions
6. **All attachment types processed** — no content filtering

#### Affected Files
- `logic-app/workflow.json`
- `logic-app/connections.json`
- `infrastructure/deploy.sh`

---

### Web App Architecture — Lambert

**Date:** 2025-04-20 | **Status:** Approved

#### Decision
FastAPI + Jinja2 server-rendered app (no SPA framework). Containerized with python:3.12-slim.

#### Rationale
- Server-rendered HTML keeps stack simple (no JS build step)
- FastAPI enables async route handlers and auto-generated /docs
- Jinja2 templates are standard Python templating
- Blob attachments stream directly (managed identity, no pre-signed URLs)

#### Key Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| COSMOS_ENDPOINT | Cosmos DB URI | (required) |
| COSMOS_DATABASE | Database name | email-parser-db |
| COSMOS_CONTAINER | Container name | emails |
| STORAGE_ACCOUNT_URL | Blob storage URI | (required) |
| STORAGE_CONTAINER | Blob container name | email-attachments |
| COSMOS_KEY | Local dev only | (optional) |
| STORAGE_CONNECTION_STRING | Local dev only | (optional) |

#### Impact
Ripley must configure Container Apps with these env vars and assign managed identity roles (Cosmos DB Data Reader, Storage Blob Data Reader).

---

### Test Suite and Quality Findings — Kane

**Date:** 2025-07-18 | **Status:** Approved

#### Test Architecture
- 30 tests all passing
- Tests patch `_get_cosmos_container()` and `_get_blob_service()` at module level
- Sync SDK mocks match actual app
- Run with: `cd web-app && python -m pytest ../tests/ -v`

#### Quality Findings — ACTION REQUIRED

**🔴 Critical — XSS Risk**
- **Issue:** `email_detail.html` uses `{{ email.body | safe }}` — malicious HTML renders unescaped
- **Root Cause:** Email bodies from Office 365 are untrusted input
- **Recommendation:** Sanitize with `nh3` or `bleach` before passing to template
- **Assign To:** Lambert (template owner) or Ripley (email ingestion owner)
- **Priority:** CRITICAL — fix before production deployment

**🟡 High — Missing Error Handling**
- **Issue:** `/emails` and `/emails/{id}` routes do not catch `query_items()` exceptions
- **Effect:** Cosmos failures propagate as raw 500 errors without user-friendly pages
- **Recommendation:** Wrap queries in try/except, render error.html with context
- **Assign To:** Lambert (route owner)
- **Priority:** HIGH — implement before release

**ℹ️ Technical Constraint**
- `azure-cosmos` must be `>=4.0.0` — v3 has completely different API
- Verify in `web-app/requirements.txt`

#### Affected Files
- `web-app/app.py` — error handling needed
- `web-app/templates/email_detail.html` — XSS sanitization needed
- `web-app/requirements.txt` — azure-cosmos version constraint

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- Quality findings and action items tracked in decision records
