# Bitesize reference client

This directory contains the Bitesize React/Vite frontend used as Crumbs'
reference client. It owns the browsing, filtering, favourites, recipe detail,
and ingredient-highlighting experience. It does not contain Bitesize's former
Express backend or a direct database connection.

## Run locally

From this directory:

```bash
npm ci
npm run dev
```

The Vite development server proxies relative `/api` requests to
`http://localhost:3001`. A Crumbs-compatible API must be running there for
recipes to load. The API boundary is intentionally kept relative so the proxy
target can be changed when the shared Crumbs API is added.

## Verify the client

```bash
npm run lint
npm run build
```

The build output is written to the ignored `dist/` directory.
