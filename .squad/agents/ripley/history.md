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
