# 008: Simple Zep recipe experiment

**Status:** Implemented; awaiting user review

Keep the SDK integration small and readable, with three modules:

- `client.py`: construct the Zep client from settings.
- `ingest.py`: serialize/add a recipe and save the current conversation pair.
- `retrieval.py`: recipe/preference searches and full source episode recipe lookup.

## Recipe discovery

Bitesize defaults to Zep graph search and also offers Vector RAG. The selected
backend goes to the existing chat endpoint/orchestrator. The Zep search handler
passes up to ten raw edge facts and complete original episode recipes to the
answer model. A separate helper parses source episode JSON and identifies recipes using
`metadata.recipe_slug` or `document_id`; it never guesses a slug from generated
text. The answer model checks complete ingredient/instruction content against
the user's request and remembered preferences. No application-side ingredient
exclusion matcher, structured exclusion argument, or custom ingredient reranking
is used. Do not offer
recipes that contain avoided ingredients or cannot be verified, even as alternatives.
The same episode recipes supply source cards without any Postgres reads in
discovery. Preserve original ingredient/instruction lists and group boundaries.
Fetch each source UUID once and deduplicate recipe slugs in source order. Skip
invalid JSON, non-recipe content, and mismatched source/body slugs without a
Postgres fallback.
The same answer synthesis call returns answer text and the slugs of recipes offered in that
answer. Return only those known cards, deduplicated and in answer order, for
both Vector and Zep. Do not impose a fixed card count or show every source.
An answer offering no recipes returns no cards. Exact recipe
details continue using the canonical recipe store. No Zep error silently falls
back to vector retrieval.

Use the SDK directly for graph creation, episode/graph inspection, and separate
edge/node/episode/observation searches. Keep a simple vector/Zep comparison loop.
Inspect graph evidence and temporal facts in Zep's managed app. Bulk backfill
should use Zep's `zep-ingest` package rather than a custom importer; installing
or running a bulk import is outside this integration.

## One shared test user

Shared memory is opt-in and uses `ZEP_USER_UUID`. Everyone shares this identity;
there is no login or private ownership. For an enabled chat, create a Zep thread
lazily, retrieve preference facts before answering, and save only the current
user/assistant pair after answering. Assistant messages remain in thread history
but are excluded from extraction. Verify supplied thread UUIDs belong to the
configured test user.

Preference retrieval uses Zep's native date filters: `invalid_at is_null` AND
`expired_at is_null`. Zep/Graphiti owns supersession and invalidation; the app
does not reconcile contradictory facts that remain marked active.

Off prevents personal memory reads/writes; recipe search and local follow-ups
continue. Each toggle change clears the remote thread pointer, so subsequent
enabled messages start a new segment. Disabled turns are never uploaded as
history. The UI offers shared memory in Zep mode; Vector RAG stays the baseline.

Persist the transcript, cards/statuses, thread UUID, backend, and toggle in one
browser local-storage record. Reload restores the same conversation and thread.
New chat clears the transcript and UUID without deleting any Zep thread or shared
memory. Recovery is per browser, not cross-device synchronization. Show a notice
when browser storage is unavailable. Disable chat resets/settings during a send.

Conversation save success is distinct from asynchronous graph extraction. A
failed/unconfirmed save preserves the answer and reports its status. Do not
retry writes automatically or poll processing status.

## Boundaries and verification

No workers, queues, budgets, ledgers, revisions, database migrations, or accounts.
Existing credentials, graph data, canonical recipes, and vector retrieval stay
available. Graphiti and Neo4j remain the later integration.

Tests cover answer/card selection and order, serialization, stable source IDs,
backend routing, shared-user thread
checks, preference context, current-turn-only writes, save failures, and browser
session restoration/reset. Normal tests mock external services. Live checks are
separate and use only the configured shared test identity.
