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
- **Logic App (Consumption)** — Serverless, no backing app service plan
- Managed identity (system-assigned) for Cosmos DB and Blob Storage
- Office 365 Outlook connector with OAuth2
- Workflow definition embedded in ARM resource (no separate connections.json deployment)

**Note:** Migrated from Logic App Standard (2025-07-20) to enforce zero shared keys per security policy. Standard tier required storage account keys; Consumption is serverless.

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

### Logic App Workflow Fixes — Ripley

**Date:** 2026-04-20 | **Status:** Applied

#### Fix 1: Recursive Inputs Nesting in Run History

**Problem:** Logic App run history showed deeply nested `Inputs > value > Inputs > value...` structures due to Office 365 V3 connector's `body` field being an object (not a string).

**Solution:**
- Removed unused `Compose_Email_Metadata` action
- Changed body reference from `@{triggerBody()?['body']}` to `@{triggerBody()?['body']?['content']}` to extract HTML string only

**Impact:**
- Run history now clean and readable
- Cosmos DB `body` field correctly stores HTML string (not object)

---

#### Fix 2: Cosmos DB BadGateway Error — Expression Type Safety

**Problem:** 502 BadGateway on Cosmos save due to:
1. `from` field string interpolation corrupting JSON object
2. `messageId` partition key null → empty string → Cosmos rejection

**Solution:**
- Changed `from`: `@{triggerBody()?['from']}` → `@triggerBody()?['from']` (raw expression, preserves object)
- Changed `messageId`: Added coalesce fallback to `internetMessageId` or O365 message ID

**Pattern Established:**
- `@{expr}` — string interpolation (only for strings: subject, dates, IDs)
- `@expr` — raw expression (for objects, arrays, booleans: `from`, `toRecipients`, `hasAttachments`)

**Impact:**
- **Cosmos DB:** `from` field now properly typed as `{emailAddress: {name, address}}`
- **Lambert:** Templates must access `email.from.emailAddress.address` instead of treating `from` as string
- **Kane:** Test fixtures should reflect `from` as object, not string

#### Affected Files
- `logic-app/workflow.json` — both fixes applied

---

### Logic App Standard → Consumption Migration — Ripley

**Date:** 2025-07-20 | **Status:** Implemented

**Context:** Standard tier required storage account shared keys (violates security policy). Consumption is serverless and requires no backing storage.

**Changes:**
- Removed App Service Plan (WS1 SKU)
- Removed `az logicapp create` (Standard-specific)
- Added `az resource create --resource-type Microsoft.Logic/workflows` with inline definition
- Workflow definition now embedded in ARM resource body
- `$connections` parameters populated by deploy script
- Storage account: `--allow-shared-key-access false`

**Impact:**
- **Cost:** Reduced — no App Service Plan ($100+/month)
- **Security:** Improved — zero shared keys, all managed identity
- **Deployment:** Simplified — one az resource create

**Affected Files:**
- `infrastructure/deploy.sh`
- `logic-app/workflow.json`
- `logic-app/connections.json` (now reference documentation only)
- `README.md`
- `docs/architecture.md`

---

### User Directive: Security Policy — dsanchor

**Date:** 2026-04-20T19:03:00Z

**Directive:** Never use shared access keys anywhere. Always use managed identity. Storage accounts must have shared key access disabled. Logic App should be Consumption tier, not Standard.

**Rationale:** Security policy enforcement — zero-key architecture.

---

### Design Upgrade — Lambert

**Date:** 2026-04-20 | **Status:** Implemented

**Scope:** All 5 frontend files transformed to DESIGN.md specifications.

**Key Changes:**
- Dark hero sections on Inbox, Detail, and Error pages
- 56px display headlines for email subjects
- Sender avatar initials in circular backgrounds
- File-type SVG icons for attachments
- Hover-lift animations on interactive elements
- Binary dark/light section rhythm throughout
- Responsive across 6 breakpoints (320px–1536px)

**Files Modified:**
- `web-app/templates/base.html`
- `web-app/templates/emails.html`
- `web-app/templates/email_detail.html`
- `web-app/templates/error.html`
- `web-app/static/css/style.css`

**Validation:** All 30 tests passing — no functionality regression.

---

### UI Refresh & Data Model Compatibility — Lambert

**Date:** 2026-04-20 | **Status:** Implemented

**Scope:** Address polymorphic Cosmos DB field types + visual polish + new dashboard route.

**Background:** Ripley's Logic App fixes changed data types: `from` field now arrives as native JSON object `{emailAddress: {name, address}}` instead of string. Templates assuming string types would render incorrectly.

**Decision:** Use Jinja2 template filters to normalize field access patterns across all templates, handling both legacy (string) and new (object) forms transparently. Added new `/dashboard` route for email statistics overview.

**Key Changes:**
- **Template Filters (5 new):**
  - `extract_from` — returns email address from object or string
  - `extract_from_display` — returns sender name for display
  - `extract_from_initial` — returns sender initial for avatar
  - `extract_body` — extracts content from object or returns string as-is
  - `extract_recipients` — normalizes recipient list to display format
- **New Dashboard Route:** `GET /dashboard` — total email count, attachment statistics, 5 most recent emails
- **CSS Polish:**
  - Removed legacy CSS (search-bar, search-input, search-btn, generic card class)
  - Added glass nav border-bottom definition
  - Tightened email card gap: 6px → 2px
  - Added structured metadata display styles
  - New dashboard responsive grid (3-col desktop → 1-col mobile)

**Rationale:**
1. Filters keep templates clean and DRY (reusable across all templates)
2. Both field types supported transparently — no fixture rewrites needed
3. Dashboard provides new value-add without duplicating inbox functionality
4. CSS cleanup removes technical debt while maintaining design fidelity

**Impact:**
- **Kane:** Test suite unaffected — filters handle existing string-form fixtures. Consider adding object-form fixtures for full coverage.
- **Ripley:** No infrastructure changes needed. Dashboard uses existing Cosmos query.
- **Test Status:** All 30 tests passing — no regression.

**Files Modified:**
- `web-app/app.py` — 5 new template filters, dashboard route
- `web-app/templates/base.html` — Dashboard nav link
- `web-app/templates/emails.html` — Uses filters for `from` extraction
- `web-app/templates/email_detail.html` — Structured metadata with filters
- `web-app/templates/dashboard.html` — New template
- `web-app/static/css/style.css` — Polish and dashboard styles

---

### Container Registry Migration — Ripley

**Date:** 2025-01-20 | **Status:** Approved

#### Decision
Migrate from Azure Container Registry (ACR) to GitHub Packages (ghcr.io) for container image hosting.

#### Rationale
1. **Cost Efficiency**: ghcr.io free for public repos; eliminates ACR Basic tier (~$5/month)
2. **Integrated CI/CD**: GitHub Actions natively supports ghcr.io via `GITHUB_TOKEN`
3. **Simplified Infrastructure**: One less Azure resource to provision and maintain
4. **Developer Experience**: Automated builds on push to main
5. **Public Visibility**: Publicly accessible container images when needed

#### Implementation
- Removed ACR provisioning from `infrastructure/deploy.sh`
- Created `.github/workflows/build-push.yml` for automated Docker builds and pushes
- Updated `README.md` with new workflow instructions
- Updated `docs/architecture.md` registry references

#### Impact
- **Ripley**: Deploy script simplified; Container App no longer needs AcrPull role
- **Lambert**: No changes to web-app code or environment variables
- **Kane**: No changes to test suite

#### Security
- Public images accessible if repo is public (matching Docker Hub model)
- Private repos keep images private with authentication
- GITHUB_TOKEN auto-rotated and scoped

#### Affected Files
- `infrastructure/deploy.sh` — removed ACR provisioning
- `.github/workflows/build-push.yml` — new workflow
- `README.md` — updated Quick Start
- `docs/architecture.md` — updated registry and deployment sections

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

### API Connection Endpoint Resolution Fix — Ripley

**Date:** 2026-04-20 | **Status:** Applied

**Problem:**
Both managed API connections (Blob Storage and Cosmos DB) failed:
- **Blob:** Unauthorized errors — connector didn't know which storage account to target
- **Cosmos DB:** 502 BadGateway (timeout) — connector couldn't resolve the Cosmos account

**Root Cause:**
`workflow.json` used the literal placeholder `AccountNameFromSettings` in the action paths for both connectors. Managed API connectors resolve the **target account from the action path** (not from connection resource properties). When deployed programmatically, the placeholder was never substituted with actual account names.

**Solution:**
1. **`logic-app/workflow.json`** — Replaced hardcoded placeholder with deploy-time tokens:
   - Blob path: `AccountNameFromSettings` → `__STORAGE_ACCOUNT__`
   - Cosmos path: `AccountNameFromSettings` → `__COSMOS_ACCOUNT__`

2. **`infrastructure/deploy.sh`** — Added `sed` substitution after reading workflow template:
   - `sed "s/__STORAGE_ACCOUNT__/$STORAGE_ACCOUNT/g"` before deployment
   - `sed "s/__COSMOS_ACCOUNT__/$COSMOS_ACCOUNT/g"` before deployment

3. **`infrastructure/redeploy-logic-app.sh`** — Applied same `sed` substitution pattern:
   - Added `COSMOS_ACCOUNT` and `STORAGE_ACCOUNT` config variables
   - Enables quick workflow iteration with correct account resolution

**Pattern Established for Consumption Logic Apps:**
- **Connection resource:** Minimal — just `api` ID + `displayName`. No account parameters needed.
- **MI authentication:** Declared in Logic App `$connections` block via `connectionProperties.authentication.type: ManagedServiceIdentity`
- **Account targeting:** Handled by the **action path** in the workflow definition (the account name in the URL path)
- **Template strategy:** Use `__PLACEHOLDER__` tokens, substitute at deploy time with `sed`

**Impact:**
- ✅ Blob Storage actions now correctly target the storage account
- ✅ Cosmos DB actions now correctly target the Cosmos account — resolves 502 BadGateway
- ✅ No changes to connection resources, role assignments, or `$connections` config
- ✅ Deployment script is now idempotent and repeatable
- ✅ Future workflow iterations (via redeploy script) use same pattern

**Files Modified:**
- `logic-app/workflow.json` — Replaced placeholders with tokens
- `infrastructure/deploy.sh` — Added sed substitution logic
- `infrastructure/redeploy-logic-app.sh` — Added same substitution + config variables

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- Quality findings and action items tracked in decision records
