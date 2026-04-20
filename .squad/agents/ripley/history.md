## Learnings

- **Project:** email-parser — Azure Logic App email processing pipeline
- **Stack:** Python, Azure (Logic Apps, Cosmos DB, Blob Storage, Container Apps), managed identities
- **User:** dsanchor
- **Reference:** https://github.com/glory-ub/PDF-Extraction-from-Mail-using-Logic-App

### Session: Logic App Workflow & Deploy Script
- Created `logic-app/workflow.json` — Stateful Logic App Standard workflow
  - Uses splitOn on trigger (required by Office 365 V3 connector for per-message processing)
  - Processes ALL attachment types (no PDF filter)
  - Sequential attachment processing (concurrency: 1) to avoid variable race conditions
  - Stores blobs at `/email-attachments/{emailId}/{filename}`
  - Upserts to Cosmos DB with `x-ms-documentdb-is-upsert: True` header
- Created `logic-app/connections.json` — API connections config
  - Office 365: OAuth (requires interactive consent post-deploy)
  - Blob Storage: ManagedServiceIdentity auth
  - Cosmos DB: ManagedServiceIdentity auth (uses `documentdb` managed API)
- Created `infrastructure/deploy.sh` — Full AZ CLI deployment script
  - Cosmos DB: serverless, NoSQL API, partition key `/messageId`
  - Logic App Standard on WS1 App Service Plan
  - Container Apps with quickstart placeholder image
  - API connections provisioned via `az resource create`
  - Access policies grant Logic App MI access to API connections
- **Cosmos DB Built-in Role IDs:**
  - Data Reader: `00000000-0000-0000-0000-000000000001`
  - Data Contributor: `00000000-0000-0000-0000-000000000002`
- **Key files:** `logic-app/workflow.json`, `logic-app/connections.json`, `infrastructure/deploy.sh`

### Session: ACR to GitHub Packages Migration
- Replaced Azure Container Registry with GitHub Packages (ghcr.io) for container image hosting
- Removed ACR provisioning from `infrastructure/deploy.sh`:
  - Removed ACR_NAME config variable
  - Removed `az acr create` command section
  - Removed ACR_LOGIN_SERVER variable lookup
  - Removed `--registry-server` flag from Container App create
  - Removed AcrPull role assignment for Container App managed identity
- Created `.github/workflows/build-push.yml` — automated Docker build pipeline
  - Triggers on push to `main` when `web-app/` changes
  - Also supports manual trigger via `workflow_dispatch`
  - Builds from `web-app/Dockerfile`
  - Pushes to `ghcr.io/${{ github.repository }}/email-parser-web`
  - Tags with both `latest` and `<branch>-<sha>`
  - Uses built-in `GITHUB_TOKEN` (no secrets needed)
  - Requires `packages: write` and `contents: read` permissions
- Updated documentation:
  - `README.md`: Changed Quick Start step 4 to reference GH Actions workflow
  - `docs/architecture.md`: Updated "Container Registry" references to "GitHub Packages (ghcr.io)"
  - Updated Security Model section (removed ACR pull reference)
  - Updated Deployment Architecture section with workflow details
- **Rationale:** GitHub Packages is free for public repos, integrated with GH Actions, and eliminates one Azure resource to provision/maintain
- **Key files affected:** `infrastructure/deploy.sh`, `.github/workflows/build-push.yml`, `README.md`, `docs/architecture.md`

### Session: Logic App Standard → Consumption Migration
- **Trigger:** Logic App Standard deployment failed because it requires storage account shared keys, and the user's policy mandates `--allow-shared-key-access false`
- Rewrote `infrastructure/deploy.sh`:
  - Removed App Service Plan (WS1) — Consumption doesn't need it
  - Removed `APP_SERVICE_PLAN` config variable
  - Removed `az logicapp create` / `az webapp identity assign` / `az webapp identity show` (Standard-specific commands)
  - Added `az resource create --resource-type Microsoft.Logic/workflows` for Consumption Logic App
  - Deploy script reads `logic-app/workflow.json` and injects it as the definition in the ARM resource body
  - `$connections` parameters (office365, azureblob, cosmosdb) are populated with actual subscription/RG/connection IDs at deploy time
  - System-assigned managed identity enabled via `az resource update --set identity`
  - Changed `--allow-shared-key-access true` → `--allow-shared-key-access false` on storage account
  - Moved API connection creation BEFORE Logic App creation (connections must exist for the workflow definition)
  - Removed `az logicapp show` from summary; Logic App Consumption has no public URL
- Rewrote `logic-app/workflow.json`:
  - Removed `"kind": "Stateful"` wrapper (Consumption doesn't use kind)
  - Changed from Standard format (wrapped in `definition` + `kind`) to bare workflow definition
  - Changed connection references from `"referenceName"` to `"name": "@parameters('$connections')['<name>']['connectionId']"` (Consumption format)
- Rewrote `logic-app/connections.json`:
  - Replaced Standard `managedApiConnections` with `@appsetting()` references → reference-only doc
  - File is now documentation only; Consumption Logic Apps don't use connections.json at runtime
- Updated `README.md`: removed Logic App Standard references, removed separate workflow deploy step
- Updated `docs/architecture.md`: changed all Standard/WS1/ASP references to Consumption
- **Key pattern:** Consumption Logic Apps get their workflow definition + connections embedded in the ARM resource at deploy time, unlike Standard which uses separate deployment
- **User policy:** Zero shared keys anywhere — storage account `--allow-shared-key-access false`
- **Key files:** `infrastructure/deploy.sh`, `logic-app/workflow.json`, `logic-app/connections.json`, `README.md`, `docs/architecture.md`

### Session: Logic App Recursive Input Nesting Fix
- **Issue:** Run history showed infinite recursive `Inputs > value > Inputs > value...` nesting pattern
- **Root cause:** Office 365 V3 connector's `body` field is an object `{ content: "...", contentType: "..." }`, not a string
  - When referenced multiple times in workflow (Compose action + Cosmos action), Logic Apps run history tracking creates nested representations
  - The `Compose_Email_Metadata` action was unused — it composed trigger body but was never referenced downstream
- **Fix applied to `logic-app/workflow.json`:**
  - Removed unused `Compose_Email_Metadata` action (reduced redundant trigger references)
  - Changed Cosmos document body field from `@{triggerBody()?['body']}` → `@{triggerBody()?['body']?['content']}`
  - Now extracts only the HTML/text string content instead of storing the entire object
- **Impact:**
  - Run history is now clean and readable
  - Cosmos DB `body` field correctly stores HTML string (as originally intended)
  - No web app changes needed — Lambert's templates already expected `body` to be a string
  - Performance improvement from removing unused action step
- **Prevention pattern:** Always access `triggerBody()?['body']?['content']` explicitly when using Office 365 V3 connector
- **Key file:** `logic-app/workflow.json`
- **Decision doc:** `.squad/decisions/inbox/ripley-logic-app-recursive-fix.md`

### Session: Cosmos DB BadGateway Fix
- **Issue:** `Create_or_Update_Cosmos_Document` action failing with 502 BadGateway
- **Root causes identified:**
  1. `from` field used string interpolation `@{triggerBody()?['from']}` on a complex object `{emailAddress: {name, address}}` — serializes to garbage, corrupts the Cosmos document body
  2. `messageId` (partition key `/messageId`) used `@{triggerBody()?['internetMessageId']}` with no null fallback — empty partition key value causes BadGateway
- **Fix applied to `logic-app/workflow.json`:**
  - Changed `from` from `@{triggerBody()?['from']}` → `@triggerBody()?['from']` (no string interpolation — preserves JSON object)
  - Changed `messageId` from `@{triggerBody()?['internetMessageId']}` → `@{coalesce(triggerBody()?['internetMessageId'], triggerBody()?['id'])}` (fallback to O365 ID if internetMessageId is null)
- **Pattern:** In Logic App expressions, use `@expr` (no braces) for objects/arrays, use `@{expr}` only for string values. Mixing these up is a common BadGateway source.
- **Key insight:** `toRecipients`, `hasAttachments`, and `attachments` were already correct (no string interpolation on non-string types)
- **Key file:** `logic-app/workflow.json`
- **Decision doc:** `.squad/decisions/inbox/ripley-cosmos-badgateway-fix.md`

### Session: Logic App Workflow Redeploy Script
- Created `infrastructure/redeploy-logic-app.sh` — focused script that ONLY redeploys the Logic App workflow definition
  - Validates Logic App exists before attempting deploy (fail-fast with helpful error)
  - Uses same config variables and naming conventions as `deploy.sh` (RESOURCE_GROUP, LOCATION, LOGIC_APP)
  - Reads `logic-app/workflow.json` and deploys via `az rest --method PUT` (same ARM pattern as deploy.sh)
  - Builds `$connections` parameters from subscription/RG IDs (office365, azureblob with MI, cosmosdb with MI)
  - Preserves SystemAssigned managed identity (PUT is idempotent, won't rotate principal)
  - Writes temp payload to `infrastructure/.redeploy-logic-app-payload.json` (not /tmp) and cleans up after
  - Does NOT create any resources — no RG, Cosmos, Storage, Container App, or API connections
- **Use case:** Quick workflow iteration — edit workflow.json, run redeploy, test in portal
- **Key file:** `infrastructure/redeploy-logic-app.sh`
