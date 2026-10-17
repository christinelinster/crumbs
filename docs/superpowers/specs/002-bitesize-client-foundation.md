# 002: Bitesize reference client foundation

**Status:** Implemented\
**Parent project:** [@SPEC.md](../../../SPEC.md)

## Objective

Place the existing Bitesize React/Vite frontend inside the Crumbs repository as
an independently runnable reference client at `clients/bitesize/`.

## Scope

- Preserve the existing Bitesize browsing, recipe-detail, favourites, filtering,
  and ingredient-highlight experience during the copy.
- Keep the client package and JavaScript tooling isolated from the Python RAG
  package.
- Preserve relative `/api` requests so the future Crumbs API can replace the
  current recipe service without coupling the client to a database.
- Establish the repository boundary that later API and chat-panel work will use.

## Out of Scope

- Implementing the shared Crumbs HTTP API.
- Changing the Crumbs database schema or recipe corpus.
- Adding chat, recipe-specific context, authentication, creator accounts, or
  multi-blog corpus isolation.
- Copying Bitesize's Express backend, seed data, or Git metadata.
- Redesigning the existing Bitesize visual language.

## Dependencies

- None. The client foundation can be built and verified independently of a live
  Crumbs API.

## Required Context

- [@docs/architecture.md#system-boundary](../../architecture.md#system-boundary)
- [@docs/decisions/003-bitesize-reference-client.md](../../decisions/003-bitesize-reference-client.md)
- [@docs/bitesize-next-steps.md](../../bitesize-next-steps.md)

## Authoritative Requirement References

- [@docs/product-requirements.md#req-client-001](../../product-requirements.md#req-client-001)
- [@docs/product-requirements.md#req-client-002](../../product-requirements.md#req-client-002)
- [@docs/product-requirements.md#req-client-003](../../product-requirements.md#req-client-003)

## Acceptance Criteria

- The Bitesize React/Vite application exists under `clients/bitesize/` without
  Bitesize Git metadata, dependency directories, or its separate backend.
- The client can install its dependencies and complete its production build from
  its own directory.
- Existing browsing, detail-page, filtering, favourites, and ingredient
  highlighting behavior remains represented in the copied client.
- Client API requests remain relative to `/api` and do not connect directly to
  Postgres or import Crumbs Python modules.
- The Crumbs repository documentation identifies Bitesize as a client rather
  than as part of the RAG core.

## Implementation status

The client foundation is implemented at `clients/bitesize/`. It is verified
with its own `npm ci`, `npm run lint`, and `npm run build` commands. The copied
package now consumes the implemented recipe API described in feature 003. Chat
integration is the next implementation stage described in
[@docs/bitesize-next-steps.md](../../bitesize-next-steps.md).

## Verification Expectations

Verify the client package with its lint and production build commands. Inspect
the copied tree to confirm that only frontend assets and source are included,
then run the existing Crumbs test suite to detect accidental changes to the
Python RAG layer.

## Related ADRs

- [@docs/decisions/003-bitesize-reference-client.md](../../decisions/003-bitesize-reference-client.md)

## Documentation Fallback

Read [@SPEC.md](../../../SPEC.md) as the fallback routing source whenever
additional project documentation is required.
