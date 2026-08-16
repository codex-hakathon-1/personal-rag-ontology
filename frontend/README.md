# Index frontend

Desktop-first React, TypeScript, and Vite interface for curating local ontology data.

## Run locally

```sh
cd frontend
npm install --cache /tmp/personal-rag-ontology-npm-cache
npm run dev
```

Without configuration, the app uses an in-memory demo implementation behind the same API
interface as production. Set `VITE_API_BASE_URL` to connect the REST client to a server.

## Frontend contract

The UI imports only the domain types in `src/domain.ts` and the `OntologyApi` interface in
`src/api/client.ts`. It does not depend on the database schema, model provider, extraction
pipeline, or backend framework.

The REST client currently expects:

- `GET /workspace`
- `PATCH /attributes/:attributeId`
- `DELETE /attributes/:attributeId`
- `PATCH /projects/:projectId/attributes/:attributeId`
- `POST /sources/sync`

Use `npm run lint` and `npm run build` before shipping changes.
