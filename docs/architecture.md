# Email Parser — Architecture

## Solution Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Azure Resource Group                             │
│                                                                         │
│  ┌──────────────┐       ┌──────────────┐       ┌──────────────────────┐ │
│  │              │       │              │       │                      │ │
│  │   Microsoft  │──────▶│  Logic App   │──────▶│   Azure Blob Storage │ │
│  │   365 Email  │ trigger│  (Standard)  │ upload│  email-attachments/  │ │
│  │              │       │              │       │  {emailId}/{filename}│ │
│  └──────────────┘       └──────┬───────┘       └──────────┬───────────┘ │
│                                │ store metadata            │ read       │
│                                ▼                           │            │
│                         ┌──────────────┐                   │            │
│                         │              │                   │            │
│                         │  Cosmos DB   │                   │            │
│                         │  (NoSQL API) │                   │            │
│                         │  serverless  │                   │            │
│                         └──────┬───────┘                   │            │
│                                │ query                     │            │
│                                ▼                           ▼            │
│                         ┌────────────────────────────────────┐          │
│                         │                                    │          │
│                         │     Azure Container Apps           │          │
│                         │     (Web App — Python/FastAPI)     │          │
│                         │                                    │          │
│                         └────────────────────────────────────┘          │
│                                         │                               │
│                                         ▼                               │
│                                    End Users                            │
│                                   (Browser)                             │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Interaction Flow

```
1. New email arrives ──▶ Office 365 connector triggers Logic App
2. Logic App extracts email metadata (subject, from, body, etc.)
3. Logic App writes email document to Cosmos DB
4. Logic App iterates over each attachment:
   a. Gets attachment content
   b. Uploads to Blob Storage at: email-attachments/{emailId}/{filename}
   c. Updates Cosmos DB document with attachment blob path
5. Web App queries Cosmos DB for email list / detail
6. Web App generates SAS-free download URLs via managed identity for attachments
```

---

## Cosmos DB Schema

**Database:** `email-parser-db`
**Container:** `emails`
**Partition Key:** `/messageId`

### Email Document

```json
{
  "id": "<unique-guid>",
  "messageId": "<office365-message-id>",
  "subject": "Quarterly Report Q4 2024",
  "body": "<full HTML body>",
  "bodyPreview": "Hi team, please find the quarterly report attached...",
  "from": {
    "name": "Jane Smith",
    "address": "jane.smith@contoso.com"
  },
  "toRecipients": [
    {
      "name": "David Sancho",
      "address": "dsanchor@microsoft.com"
    }
  ],
  "receivedDateTime": "2024-12-15T14:30:00Z",
  "hasAttachments": true,
  "isRead": true,
  "importance": "normal",
  "conversationId": "<office365-conversation-id>",
  "attachments": [
    {
      "name": "Q4-Report.pdf",
      "contentType": "application/pdf",
      "size": 245760,
      "blobPath": "email-attachments/abc123/Q4-Report.pdf"
    },
    {
      "name": "Budget.xlsx",
      "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "size": 102400,
      "blobPath": "email-attachments/abc123/Budget.xlsx"
    }
  ],
  "processedAt": "2024-12-15T14:30:05Z",
  "_ts": 1702650605
}
```

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| Partition key: `/messageId` | Each email is a unique conversation anchor; queries are per-email |
| Serverless capacity mode | Cost-efficient for bursty email workloads — pay per request |
| Attachments embedded in document | Avoids cross-document joins; single read returns full email context |
| `bodyPreview` separate from `body` | Enables fast list views without loading full HTML bodies |
| `processedAt` timestamp | Tracks when Logic App processed the email vs. when it was received |

---

## Blob Storage Structure

**Storage Account:** Standard_LRS (locally redundant)
**Container:** `email-attachments`

```
email-attachments/
├── <emailId-1>/
│   ├── Q4-Report.pdf
│   └── Budget.xlsx
├── <emailId-2>/
│   └── presentation.pptx
└── <emailId-3>/
    ├── photo.jpg
    ├── notes.docx
    └── data.csv
```

**Path Convention:** `email-attachments/{emailId}/{original-filename}`

- `emailId` is the Cosmos DB document `id` (GUID), ensuring uniqueness
- Original filename is preserved for user-friendly downloads
- All file types are accepted — no filtering by content type

---

## Logic App Workflow Design

**Type:** Logic App Standard (kind: `functionapp,workflowapp`)
**Workflow:** Stateful (reliable delivery, retry support)
**Location:** Deployed on App Service Plan (WS1 SKU)

### Workflow Steps

```
┌─────────────────────────────────────┐
│ Trigger: When a new email arrives   │
│ (Office 365 Outlook connector)      │
│ Folder: Inbox                       │
│ Include Attachments: Yes            │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Compose: Build email metadata       │
│ Extract: subject, body, bodyPreview,│
│ from, toRecipients, receivedDateTime│
│ hasAttachments, isRead, importance, │
│ conversationId                      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Create or Update Document           │
│ (Cosmos DB connector)               │
│ Database: email-parser-db           │
│ Container: emails                   │
│ Document: email metadata + empty    │
│ attachments array                   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Condition: hasAttachments == true    │
│                                     │
│ ┌─ True ──────────────────────────┐ │
│ │ For Each: attachment             │ │
│ │  ├─ Get Attachment (O365)       │ │
│ │  ├─ Create Blob                 │ │
│ │  │  Container: email-attachments│ │
│ │  │  Path: {emailId}/{name}      │ │
│ │  │  Content: attachment bytes   │ │
│ │  └─ Append to attachments array │ │
│ │     (name, contentType, size,   │ │
│ │      blobPath)                  │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─ False ─────────────────────────┐ │
│ │ (skip attachment processing)    │ │
│ └─────────────────────────────────┘ │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Update Document (Cosmos DB)         │
│ Write final document with           │
│ attachments[] and processedAt       │
└─────────────────────────────────────┘
```

### Connector Authentication

| Connector | Auth Method |
|-----------|-------------|
| Office 365 Outlook | OAuth2 interactive consent (user's mailbox) |
| Azure Cosmos DB | Managed Identity (System-Assigned) |
| Azure Blob Storage | Managed Identity (System-Assigned) |

---

## Managed Identity Roles

All service-to-service communication uses Azure Managed Identities. **Zero connection strings** in the solution.

### Logic App (System-Assigned Managed Identity)

| Target Resource | Role | Purpose |
|----------------|------|---------|
| Storage Account | **Storage Blob Data Contributor** | Upload attachment blobs |
| Cosmos DB Account | **Cosmos DB Built-in Data Contributor** | Create and update email documents |

### Container App (System-Assigned Managed Identity)

| Target Resource | Role | Purpose |
|----------------|------|---------|
| Storage Account | **Storage Blob Data Reader** | Read/download attachment blobs |
| Cosmos DB Account | **Cosmos DB Built-in Data Reader** | Query email documents |

### Role Assignment Reference

| Role Name | Role Definition ID |
|-----------|--------------------|
| Storage Blob Data Contributor | `ba92f5b4-2d11-453d-a403-e96b0029c9fe` |
| Storage Blob Data Reader | `2a2b9908-6ea1-4ae2-8e65-a410df84e7d1` |
| Cosmos DB Built-in Data Contributor | `00000000-0000-0000-0000-000000000002` |
| Cosmos DB Built-in Data Reader | `00000000-0000-0000-0000-000000000001` |

> **Note:** Cosmos DB built-in roles use data-plane RBAC and require `az cosmosdb sql role assignment create`, not the standard `az role assignment create`.

---

## Web Application Architecture

**Runtime:** Python 3.12 + FastAPI
**Deployment:** Azure Container Apps (with system-assigned managed identity)
**Container Registry:** Azure Container Registry (ACR)

### Pages

| Route | View | Description |
|-------|------|-------------|
| `GET /` | `emails.html` | Paginated email list with preview cards |
| `GET /emails/{id}` | `email_detail.html` | Full email with body and attachment downloads |
| `GET /emails/{id}/attachments/{filename}` | — | Stream attachment from Blob Storage |
| `GET /health` | — | Health check endpoint |

### SDK Usage

- **Cosmos DB:** `azure-cosmos` SDK with `DefaultAzureCredential`
- **Blob Storage:** `azure-storage-blob` SDK with `DefaultAzureCredential`
- **Auth:** `azure-identity` for managed identity

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `COSMOS_ENDPOINT` | Cosmos DB account endpoint | `https://ep-cosmos-xxx.documents.azure.com:443/` |
| `COSMOS_DATABASE` | Database name | `email-parser-db` |
| `COSMOS_CONTAINER` | Container name | `emails` |
| `STORAGE_ACCOUNT_URL` | Blob Storage endpoint | `https://epstorxxx.blob.core.windows.net` |
| `STORAGE_CONTAINER` | Blob container name | `email-attachments` |

---

## Security Model

```
┌──────────────────────────────────────────────┐
│              Security Principles              │
├──────────────────────────────────────────────┤
│ ✓ All Azure service auth via Managed Identity│
│ ✓ Zero connection strings in config/code     │
│ ✓ Cosmos DB data-plane RBAC (not keys)       │
│ ✓ Blob Storage data-plane RBAC (not keys)    │
│ ✓ ACR pull via managed identity              │
│ ✓ HTTPS everywhere                           │
│ ✓ O365 connector: OAuth2 user consent only   │
│ ✗ No shared access signatures (SAS)          │
│ ✗ No storage account keys                    │
│ ✗ No Cosmos DB master keys                   │
└──────────────────────────────────────────────┘
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Deployment Pipeline                           │
│                                                                  │
│  infrastructure/deploy.sh                                        │
│  ├── Resource Group                                              │
│  ├── Cosmos DB Account (serverless) + Database + Container       │
│  ├── Storage Account + Blob Container                            │
│  ├── App Service Plan (WS1) + Logic App Standard                 │
│  ├── Azure Container Registry                                    │
│  ├── Container Apps Environment + Container App                  │
│  └── Managed Identity Role Assignments (4 assignments)           │
│                                                                  │
│  Post-deploy (manual):                                           │
│  ├── Deploy Logic App workflow (logic-app/workflow.json)         │
│  ├── Configure O365 connector (interactive OAuth consent)        │
│  └── Build & push web-app Docker image to ACR                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
email-parser/
├── README.md                    # Project overview and setup guide
├── DESIGN.md                    # Apple-inspired design system
├── docs/
│   └── architecture.md          # This document
├── infrastructure/
│   └── deploy.sh                # AZ CLI deployment script
├── logic-app/
│   └── workflow.json            # Logic App Standard workflow definition
├── web-app/
│   ├── app.py                   # FastAPI application
│   ├── requirements.txt         # Python dependencies
│   ├── Dockerfile               # Container build
│   ├── templates/
│   │   ├── base.html            # Base layout (Apple design system)
│   │   ├── emails.html          # Email list view
│   │   └── email_detail.html    # Email detail view
│   └── static/
│       └── css/
│           └── style.css        # Apple-inspired styles
└── tests/
    ├── test_app.py              # Web app tests
    └── conftest.py              # Pytest fixtures
```
