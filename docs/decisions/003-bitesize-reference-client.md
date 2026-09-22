# 003: Bitesize as the first Crumbs client

**Status:** Accepted  
**Date:** 2026-09-21

## Context

Crumbs is intended to provide reusable recipe RAG capabilities to more than one
client. Bitesize already has a React/Vite frontend, but its existing Express
backend and recipe data shape are separate from Crumbs' Python RAG and Postgres
schema.

## Decision

Treat Bitesize as the first reference client of Crumbs. Place its frontend at
`clients/bitesize/` in the Crumbs repository. Keep ingestion, recipe storage,
embeddings, retrieval, and response generation in the Crumbs core. Add a shared
API layer between clients and the core later; do not copy Bitesize's Express
backend or seed data into the Crumbs application.

For the MVP, support multiple users against one shared corpus. Defer creator
accounts, independent blog corpora, tenant administration, and corpus
permissions until an explicit corpus or tenant boundary is designed.

## Consequences

- Crumbs can evolve independently of Bitesize's presentation and branding.
- Bitesize provides a concrete, runnable client for validating the future API.
- The frontend and future API can be tested and deployed as separate processes.
- A later multi-blog release will require scoped recipe writes and retrieval.
- The existing Bitesize backend is not a migration source for Crumbs data.

## Alternatives considered

- A root-level `bitesize/` directory was rejected because it makes the client
  look like part of Crumbs core rather than one consumer.
- Copying the full Bitesize repository was rejected because its Express backend
  uses a different recipe schema and persistence flow.
