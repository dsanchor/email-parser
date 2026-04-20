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
