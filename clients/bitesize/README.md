# Bitesize reference client

This directory contains the Bitesize React/Vite frontend used as Crumbs'
reference client. It owns the browsing, filtering, favourites, recipe detail,
ingredient-highlighting, and Crumbs chat-panel experience. It does not contain
Bitesize's former Express backend or a direct database connection.

The chat panel opens from the fixed "Ask Crumbs" launcher in the lower-right
corner, inset from the page edge. Its history lives in React memory for the current application session;
recipe references navigate to detail pages without closing the panel.

## Run locally

Start the Crumbs API from the repository root in one terminal:

```bash
poetry run uvicorn app.api:app --reload --port 3001
```

Then run the client from this directory in another terminal:

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
npm test
npm run build
```

The build output is written to the ignored `dist/` directory.
