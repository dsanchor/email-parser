#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Email Parser — Azure Infrastructure Deployment
# Provisions: Resource Group, Cosmos DB, Storage, Logic App Standard,
#             Container Registry, Container Apps, Managed Identity roles
###############################################################################

# ── Configuration ────────────────────────────────────────────────────────────
RESOURCE_GROUP="${RESOURCE_GROUP:-email-parser-rg}"
LOCATION="${LOCATION:-swedencentral}"
COSMOS_ACCOUNT="${COSMOS_ACCOUNT:-email-parser-cosmos}"
COSMOS_DB="email-parser-db"
COSMOS_CONTAINER="emails"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-emailparserstor}"
BLOB_CONTAINER="email-attachments"
APP_SERVICE_PLAN="${APP_SERVICE_PLAN:-email-parser-asp}"
LOGIC_APP="${LOGIC_APP:-email-parser-logic}"
ACR_NAME="${ACR_NAME:-emailparseracr}"
CONTAINER_ENV="${CONTAINER_ENV:-email-parser-env}"
CONTAINER_APP="${CONTAINER_APP:-email-parser-app}"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Email Parser — Azure Infrastructure Deployment             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Config:"
echo "  Resource Group:  $RESOURCE_GROUP"
echo "  Location:        $LOCATION"
echo "  Cosmos Account:  $COSMOS_ACCOUNT"
echo "  Storage Account: $STORAGE_ACCOUNT"
echo "  Logic App:       $LOGIC_APP"
echo "  ACR:             $ACR_NAME"
echo "  Container App:   $CONTAINER_APP"
echo ""

# ── Resource Group ───────────────────────────────────────────────────────────
echo "▸ Creating resource group..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# ── Cosmos DB (NoSQL API, Serverless) ────────────────────────────────────────
echo "▸ Creating Cosmos DB account (serverless)..."
az cosmosdb create \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --kind GlobalDocumentDB \
  --capacity-mode Serverless \
  --default-consistency-level Session \
  --locations regionName="$LOCATION" failoverPriority=0 isZoneRedundant=false \
  -o none

echo "▸ Creating Cosmos DB database..."
az cosmosdb sql database create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --name "$COSMOS_DB" \
  --output none

echo "▸ Creating Cosmos DB container (partition key: /messageId)..."
az cosmosdb sql container create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --database-name "$COSMOS_DB" \
  --name "$COSMOS_CONTAINER" \
  --partition-key-path "/messageId" \
  --output none

# ── Storage Account ──────────────────────────────────────────────────────────
echo "▸ Creating storage account..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --output none

echo "▸ Creating blob container..."
az storage container create \
  --name "$BLOB_CONTAINER" \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  --output none

# ── App Service Plan (Logic App Standard requires WS1) ──────────────────────
echo "▸ Creating App Service Plan (WS1)..."
az appservice plan create \
  --name "$APP_SERVICE_PLAN" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku WS1 \
  --output none

# ── Logic App Standard ───────────────────────────────────────────────────────
echo "▸ Creating Logic App Standard..."
az logicapp create \
  --name "$LOGIC_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --plan "$APP_SERVICE_PLAN" \
  --storage-account "$STORAGE_ACCOUNT" \
  --output none

echo "▸ Enabling system-assigned managed identity on Logic App..."
az webapp identity assign \
  --name "$LOGIC_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --output none

LOGIC_APP_PRINCIPAL_ID=$(az webapp identity show \
  --name "$LOGIC_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId --output tsv)

echo "  Logic App MI Principal ID: $LOGIC_APP_PRINCIPAL_ID"

# ── Azure Container Registry ────────────────────────────────────────────────
echo "▸ Creating Azure Container Registry (Basic)..."
az acr create \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --sku Basic \
  --admin-enabled false \
  --output none

# ── Container Apps Environment ───────────────────────────────────────────────
echo "▸ Creating Container Apps Environment..."
az containerapp env create \
  --name "$CONTAINER_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# ── Container App ────────────────────────────────────────────────────────────
ACR_LOGIN_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query loginServer --output tsv)

COSMOS_ENDPOINT=$(az cosmosdb show \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query documentEndpoint --output tsv)

STORAGE_ACCOUNT_URL="https://${STORAGE_ACCOUNT}.blob.core.windows.net"

echo "▸ Creating Container App..."
az containerapp create \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINER_ENV" \
  --image "mcr.microsoft.com/k8se/quickstart:latest" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 3 \
  --system-assigned \
  --registry-server "$ACR_LOGIN_SERVER" \
  --env-vars \
    "COSMOS_ENDPOINT=${COSMOS_ENDPOINT}" \
    "COSMOS_DATABASE=${COSMOS_DB}" \
    "COSMOS_CONTAINER=${COSMOS_CONTAINER}" \
    "STORAGE_ACCOUNT_URL=${STORAGE_ACCOUNT_URL}" \
    "STORAGE_CONTAINER=${BLOB_CONTAINER}" \
  --output none

CONTAINER_APP_PRINCIPAL_ID=$(az containerapp identity show \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId --output tsv)

echo "  Container App MI Principal ID: $CONTAINER_APP_PRINCIPAL_ID"

# ── Role Assignments ────────────────────────────────────────────────────────
echo ""
echo "▸ Configuring role assignments..."

STORAGE_RESOURCE_ID=$(az storage account show \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query id --output tsv)

COSMOS_RESOURCE_ID=$(az cosmosdb show \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query id --output tsv)

# Logic App MI → Storage Blob Data Contributor
echo "  ▸ Logic App → Storage Blob Data Contributor..."
az role assignment create \
  --assignee-object-id "$LOGIC_APP_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_RESOURCE_ID" \
  --output none 2>/dev/null || echo "    (already assigned)"

# Logic App MI → Cosmos DB Built-in Data Contributor
echo "  ▸ Logic App → Cosmos DB Data Contributor..."
az cosmosdb sql role assignment create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --role-definition-id "00000000-0000-0000-0000-000000000002" \
  --principal-id "$LOGIC_APP_PRINCIPAL_ID" \
  --scope "/" \
  --output none 2>/dev/null || echo "    (already assigned)"

# Container App MI → Storage Blob Data Reader
echo "  ▸ Container App → Storage Blob Data Reader..."
az role assignment create \
  --assignee-object-id "$CONTAINER_APP_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Reader" \
  --scope "$STORAGE_RESOURCE_ID" \
  --output none 2>/dev/null || echo "    (already assigned)"

# Container App MI → Cosmos DB Built-in Data Reader
echo "  ▸ Container App → Cosmos DB Data Reader..."
az cosmosdb sql role assignment create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --role-definition-id "00000000-0000-0000-0000-000000000001" \
  --principal-id "$CONTAINER_APP_PRINCIPAL_ID" \
  --scope "/" \
  --output none 2>/dev/null || echo "    (already assigned)"

# Container App MI → AcrPull (pull images from ACR)
echo "  ▸ Container App → AcrPull..."
ACR_RESOURCE_ID=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id --output tsv)

az role assignment create \
  --assignee-object-id "$CONTAINER_APP_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "AcrPull" \
  --scope "$ACR_RESOURCE_ID" \
  --output none 2>/dev/null || echo "    (already assigned)"

# ── API Connections for Logic App ────────────────────────────────────────────
echo ""
echo "▸ Creating API connections for Logic App..."

SUBSCRIPTION_ID=$(az account show --query id --output tsv)

# Office 365 connection (requires interactive OAuth consent)
echo "  ▸ Office 365 connection..."
az resource create \
  --resource-group "$RESOURCE_GROUP" \
  --resource-type "Microsoft.Web/connections" \
  --name "office365" \
  --location "$LOCATION" \
  --properties "{
    \"api\": {
      \"id\": \"/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Web/locations/$LOCATION/managedApis/office365\"
    },
    \"displayName\": \"Office 365 - Email Parser\"
  }" \
  --output none

# Azure Blob Storage connection (managed identity)
echo "  ▸ Azure Blob Storage connection (managed identity)..."
az resource create \
  --resource-group "$RESOURCE_GROUP" \
  --resource-type "Microsoft.Web/connections" \
  --name "azureblob" \
  --location "$LOCATION" \
  --properties "{
    \"api\": {
      \"id\": \"/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Web/locations/$LOCATION/managedApis/azureblob\"
    },
    \"displayName\": \"Azure Blob Storage - Email Parser\",
    \"parameterValueSet\": {
      \"name\": \"managedIdentityAuth\",
      \"values\": {}
    }
  }" \
  --output none

# Cosmos DB connection (managed identity)
echo "  ▸ Cosmos DB connection (managed identity)..."
COSMOS_ENDPOINT=$(az cosmosdb show \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query documentEndpoint --output tsv)

az resource create \
  --resource-group "$RESOURCE_GROUP" \
  --resource-type "Microsoft.Web/connections" \
  --name "cosmosdb" \
  --location "$LOCATION" \
  --properties "{
    \"api\": {
      \"id\": \"/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Web/locations/$LOCATION/managedApis/documentdb\"
    },
    \"displayName\": \"Cosmos DB - Email Parser\",
    \"parameterValueSet\": {
      \"name\": \"managedIdentityAuth\",
      \"values\": {
        \"databaseAccount\": {
          \"value\": \"$COSMOS_ACCOUNT\"
        }
      }
    }
  }" \
  --output none

# Grant Logic App access to API connections
echo "  ▸ Granting Logic App access to API connections..."
for CONN_NAME in office365 azureblob cosmosdb; do
  CONN_ID=$(az resource show \
    --resource-group "$RESOURCE_GROUP" \
    --resource-type "Microsoft.Web/connections" \
    --name "$CONN_NAME" \
    --query id --output tsv)

  az resource create \
    --resource-group "$RESOURCE_GROUP" \
    --resource-type "Microsoft.Web/connections/accessPolicies" \
    --name "$CONN_NAME/$LOGIC_APP" \
    --properties "{
      \"principal\": {
        \"type\": \"ActiveDirectory\",
        \"identity\": {
          \"tenantId\": \"$(az account show --query tenantId --output tsv)\",
          \"objectId\": \"$LOGIC_APP_PRINCIPAL_ID\"
        }
      }
    }" \
    --output none 2>/dev/null || true
done

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Deployment Complete                                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

LOGIC_APP_URL=$(az logicapp show \
  --name "$LOGIC_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query defaultHostName --output tsv 2>/dev/null || echo "N/A")

CONTAINER_APP_URL=$(az containerapp show \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn --output tsv 2>/dev/null || echo "N/A")

echo "Resources:"
echo "  Resource Group:      $RESOURCE_GROUP"
echo "  Cosmos DB Account:   $COSMOS_ACCOUNT"
echo "  Cosmos DB Endpoint:  ${COSMOS_ENDPOINT:-N/A}"
echo "  Cosmos Database:     $COSMOS_DB"
echo "  Cosmos Container:    $COSMOS_CONTAINER (partition: /messageId)"
echo "  Storage Account:     $STORAGE_ACCOUNT"
echo "  Blob Container:      $BLOB_CONTAINER"
echo "  Logic App:           $LOGIC_APP"
echo "  Logic App URL:       https://$LOGIC_APP_URL"
echo "  ACR:                 $ACR_LOGIN_SERVER"
echo "  Container App:       $CONTAINER_APP"
echo "  Container App URL:   https://$CONTAINER_APP_URL"
echo ""
echo "Managed Identity Roles:"
echo "  Logic App MI ($LOGIC_APP_PRINCIPAL_ID):"
echo "    → Storage Blob Data Contributor on $STORAGE_ACCOUNT"
echo "    → Cosmos DB Built-in Data Contributor (00000000-0000-0000-0000-000000000002)"
echo "  Container App MI ($CONTAINER_APP_PRINCIPAL_ID):"
echo "    → Storage Blob Data Reader on $STORAGE_ACCOUNT"
echo "    → Cosmos DB Built-in Data Reader (00000000-0000-0000-0000-000000000001)"
echo ""
echo "⚠  Next steps:"
echo "  1. Authorize the Office 365 API connection in the Azure Portal"
echo "     (requires interactive OAuth consent)"
echo "  2. Deploy the Logic App workflow from logic-app/"
echo "  3. Build and push the container image to $ACR_LOGIN_SERVER"
echo "  4. Update the Container App image reference"
