# Email Parser

An Azure-native email processing pipeline that automatically captures incoming emails and their attachments, stores structured metadata in Cosmos DB, and serves everything through a beautiful Apple-inspired web interface.

## Architecture

```
  Microsoft 365 ──▶ Logic App ──▶ Cosmos DB + Blob Storage ◀── Web App ◀── Users
```

The Logic App triggers on new emails, extracts metadata, stores attachments in Blob Storage, and writes structured documents to Cosmos DB. A Python web app (FastAPI) on Azure Container Apps reads from both stores and presents emails with a clean, modern UI.

**Full architecture details:** [`docs/architecture.md`](docs/architecture.md)
**Design system:** [`DESIGN.md`](DESIGN.md)

## Prerequisites

- **Azure Subscription** with permissions to create resources
- **Microsoft 365 Account** (for email access via Office 365 connector)
- **Azure CLI** (`az`) v2.50+ — [Install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- **Docker** — [Install](https://docs.docker.com/get-docker/)
- **Python 3.12+** (for local development)

## Quick Start

### 1. Deploy Infrastructure

```bash
# Log in to Azure
az login

# Run the deployment script
chmod +x infrastructure/deploy.sh
./infrastructure/deploy.sh
```

The script creates all Azure resources: Cosmos DB (serverless), Storage Account, Logic App Standard, Container Apps, and all managed identity role assignments.

### 2. Deploy the Logic App Workflow

After infrastructure is up, deploy the Logic App workflow:

```bash
# Navigate to the logic-app directory
cd logic-app

# Deploy via Azure CLI (or use VS Code Logic App extension)
az logicapp deployment source config-zip \
  --resource-group rg-email-parser \
  --name <your-logic-app-name> \
  --src workflow.zip
```

### 3. Configure the Office 365 Connection

1. Open the Logic App in the Azure Portal
2. Go to **Workflows** → **email-processor**
3. Open the **Designer**
4. Click the Office 365 Outlook trigger
5. Sign in with your Microsoft 365 account to authorize email access
6. Select the inbox folder to monitor
7. Save the workflow

### 4. Build and Deploy the Web App

The web app is automatically built and pushed to GitHub Packages (ghcr.io) via GitHub Actions whenever changes to `web-app/` are pushed to `main`.

**Option A: Automatic Build (recommended)**

```bash
# Make changes to web-app/, commit, and push to main
git add web-app/
git commit -m "Update web app"
git push origin main

# GitHub Actions will build and push ghcr.io/<owner>/<repo>/email-parser-web:latest
```

**Option B: Manual Trigger**

Go to the **Actions** tab in GitHub, select **Build and Push Container Image**, and click **Run workflow**.

**After the build completes, update the Container App:**

```bash
az containerapp update \
  --resource-group email-parser-rg \
  --name <your-container-app-name> \
  --image ghcr.io/<owner>/<repo>/email-parser-web:latest
```

> **Note:** Replace `<owner>/<repo>` with your GitHub repository path (e.g., `dsanchor/email-parser`).

## Project Structure

```
email-parser/
├── README.md                    # This file
├── DESIGN.md                    # Apple-inspired design system
├── docs/
│   └── architecture.md          # Full architecture documentation
├── infrastructure/
│   └── deploy.sh                # AZ CLI deployment (all resources)
├── logic-app/
│   └── workflow.json            # Logic App workflow definition
├── web-app/
│   ├── app.py                   # FastAPI application
│   ├── requirements.txt         # Python dependencies
│   ├── Dockerfile               # Container image build
│   ├── templates/               # Jinja2 HTML templates
│   │   ├── base.html            # Base layout (Apple design system)
│   │   ├── emails.html          # Email list view
│   │   └── email_detail.html    # Single email detail view
│   └── static/
│       └── css/
│           └── style.css        # Apple-inspired stylesheet
└── tests/
    ├── test_app.py              # Web app unit tests
    └── conftest.py              # Pytest fixtures and test config
```

## How It Works

### Logic App — Email Processing Pipeline

1. **Trigger:** The Office 365 Outlook connector watches your inbox for new emails
2. **Extract:** Email metadata (subject, body, from, recipients, timestamps) is parsed
3. **Store Metadata:** A structured document is written to Cosmos DB
4. **Process Attachments:** Each attachment is:
   - Downloaded from Office 365
   - Uploaded to Blob Storage at `email-attachments/{emailId}/{filename}`
   - Recorded in the Cosmos DB document with its blob path
5. **All file types** are processed — PDFs, images, spreadsheets, documents, archives, etc.

### Web App — Email Viewer

- **Email List** (`/`): Paginated cards showing sender, subject, preview, timestamp, and attachment count
- **Email Detail** (`/emails/{id}`): Full email body with attachment download links
- **Attachment Download** (`/emails/{id}/attachments/{filename}`): Streams files from Blob Storage via managed identity
- **Design:** Apple-inspired UI following the design system in `DESIGN.md`

## Environment Variables

The web app requires these environment variables (set automatically by the deploy script on Container Apps):

| Variable | Description | Example |
|----------|-------------|---------|
| `COSMOS_ENDPOINT` | Cosmos DB account URI | `https://ep-cosmos-xxx.documents.azure.com:443/` |
| `COSMOS_DATABASE` | Database name | `email-parser-db` |
| `COSMOS_CONTAINER` | Container name | `emails` |
| `STORAGE_ACCOUNT_URL` | Blob Storage endpoint | `https://epstorxxx.blob.core.windows.net` |
| `STORAGE_CONTAINER` | Blob container name | `email-attachments` |

## Security

This solution uses **zero connection strings**. All service-to-service authentication is handled by Azure Managed Identities:

| Service | Target | Role |
|---------|--------|------|
| Logic App | Blob Storage | Storage Blob Data Contributor |
| Logic App | Cosmos DB | Cosmos DB Built-in Data Contributor |
| Container App | Blob Storage | Storage Blob Data Reader |
| Container App | Cosmos DB | Cosmos DB Built-in Data Reader |

The only interactive authentication is the **Office 365 OAuth consent** for the Logic App email connector — this is a one-time setup step in the Azure Portal.

## Local Development

```bash
cd web-app

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export COSMOS_ENDPOINT="https://your-cosmos.documents.azure.com:443/"
export COSMOS_DATABASE="email-parser-db"
export COSMOS_CONTAINER="emails"
export STORAGE_ACCOUNT_URL="https://yourstorage.blob.core.windows.net"
export STORAGE_CONTAINER="email-attachments"

# Run the app
uvicorn app:app --reload --port 8000
```

> **Note:** For local development, ensure your Azure CLI identity (`az login`) has the required Cosmos DB and Storage roles assigned.

## Running Tests

```bash
cd tests
pytest -v
```

## License

MIT
