# Email Parser

An Azure-native email processing pipeline that automatically captures incoming emails and their attachments, stores structured metadata in Cosmos DB, and serves everything through a beautiful Apple-inspired web interface.

## Architecture

```
  Microsoft 365 ──▶ Logic App ──▶ Cosmos DB + Blob Storage ◀── Web App ◀── Users
```

The Logic App triggers on new emails, extracts metadata, stores attachments in Blob Storage, and writes structured documents to Cosmos DB. A Node.js web app (Express + React) on Azure Container Apps reads from both stores and presents emails with a clean, modern UI.

**Full architecture details:** [`docs/architecture.md`](docs/architecture.md)
**Design system:** [`DESIGN.md`](DESIGN.md)

## Prerequisites

- **Azure Subscription** with permissions to create resources
- **Microsoft 365 Account** (for email access via Office 365 connector)
- **Azure CLI** (`az`) v2.50+ — [Install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- **Docker** — [Install](https://docs.docker.com/get-docker/)
- **Node.js 20+** (for local development)

## Quick Start

### 1. Deploy Infrastructure

```bash
# Log in to Azure
az login

# Run the deployment script
chmod +x infrastructure/deploy.sh
./infrastructure/deploy.sh
```

The script creates all Azure resources: Cosmos DB (serverless), Storage Account (shared key access disabled), Logic App (Consumption), Container Apps, API connections, and all managed identity role assignments.

### 2. Configure the Office 365 Connection

The deploy script creates the Logic App (Consumption) with the workflow definition already embedded. After deployment, you need to authorize the Office 365 API connection:

1. In the Azure Portal, navigate to your **Resource Group**
2. Open the **API Connections** resource named **office365**
3. In the left menu, click **Edit API connection**
4. Click the **Authorize** button
5. Sign in with your Microsoft 365 account to grant email access
6. Click **Save**

### 3. Build and Deploy the Web App

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
│   ├── workflow.json            # Logic App workflow definition (Consumption)
│   └── connections.json         # Connection reference (documentation only)
├── web-app/
│   ├── server.js                # Express API server
│   ├── package.json             # Node.js dependencies
│   ├── vite.config.js           # Vite build configuration
│   ├── index.html               # Vite entry point
│   ├── Dockerfile               # Multi-stage container image build
│   ├── .dockerignore             # Docker build exclusions
│   └── src/
│       ├── main.jsx             # React entry point
│       ├── App.jsx              # React Router + layout
│       ├── App.css              # Apple-inspired stylesheet
│       ├── pages/
│       │   ├── EmailList.jsx    # Email list view
│       │   ├── EmailDetail.jsx  # Single email detail view
│       │   └── ErrorPage.jsx    # Error boundary page
│       └── components/
│           └── Layout.jsx       # Shared layout wrapper
└── tests/
    ├── app.test.js              # Web app route tests (Jest + Supertest)
    ├── edgeCases.test.js        # Edge case tests
    ├── setup.js                 # Test setup (env vars)
    ├── jest.config.js           # Jest configuration
    └── fixtures/
        ├── sampleEmails.js      # Sample email data
        └── mockAzure.js         # Azure SDK mocks
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

- **Backend:** Express.js API server serving a React SPA and providing JSON endpoints
- **Frontend:** React + Vite single-page application with React Router
- **Email List** (`/`): Sortable, searchable table showing sender, subject, date, and attachment count
- **Email Detail** (`/emails/{id}`): Full email body (sanitized HTML) with attachment download links
- **Attachment Download** (`/api/emails/{id}/attachments/{filename}`): Streams files from Blob Storage via managed identity
- **Design:** Apple-inspired UI following the design system in `DESIGN.md`
- **Sanitization:** Server-side via `sanitize-html`, client-side via `DOMPurify` (defense in depth)

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

The only interactive authentication is the **Office 365 OAuth consent** — a one-time step in the Azure Portal under **API Connections → office365 → Edit API connection → Authorize**.

## Local Development

```bash
cd web-app

# Install dependencies
npm install

# Set environment variables
export COSMOS_ENDPOINT="https://your-cosmos.documents.azure.com:443/"
export COSMOS_DATABASE="email-parser-db"
export COSMOS_CONTAINER="emails"
export STORAGE_ACCOUNT_URL="https://yourstorage.blob.core.windows.net"
export STORAGE_CONTAINER="email-attachments"

# Run the app (API + Vite dev server with hot reload)
npm run dev

# Or run only the API server (serves pre-built React from dist/)
npm start
```

> **Note:** For local development, ensure your Azure CLI identity (`az login`) has the required Cosmos DB and Storage roles assigned.

## Building for Production

```bash
cd web-app

# Build the React frontend
npm run build

# Start the production server
npm start
```

## Running Tests

```bash
cd tests
npm install
npm test
```

## License

MIT
