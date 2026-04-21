# Decision: Test Mock Contract with server.js

**Author:** Kane (Tester)  
**Date:** 2026-04-21  
**Status:** Pending Lambert alignment

## Context

Tests were rewritten from Python/pytest to Node.js/Jest+Supertest ahead of the Express server being built. The mocks assume a specific contract with `web-app/server.js`.

## Assumptions Lambert needs to honor

1. **Export:** `module.exports = { app }` or `module.exports = app` (Express instance)
2. **Cosmos SDK usage:** `container.items.query(querySpec).fetchAll()` returning `{ resources: [...] }`
3. **Blob SDK usage:** `containerClient.getBlockBlobClient(blobPath).download()` returning `{ readableStreamBody, contentType, contentLength }`
4. **Routes:**
   - `GET /health` → `{ status: "healthy" }`
   - `GET /` → redirect to `/emails` or serve SPA (200)
   - `GET /api/emails` → JSON array, supports `?q=` search param
   - `GET /api/emails/:id` → single email JSON, 404 if not found
   - `GET /api/emails/:id/attachments/:filename` → streamed binary, Content-Disposition header
5. **Error handling:** Cosmos failures → 500 or 503; Blob failures → 404
6. **Module init:** Azure clients initialized via `CosmosClient` and `BlobServiceClient` constructors (mockable via `jest.doMock`)

## Impact

If Lambert's server.js deviates from these patterns, the mock layer in `tests/fixtures/mockAzure.js` needs updating. The test assertions themselves should remain stable.
