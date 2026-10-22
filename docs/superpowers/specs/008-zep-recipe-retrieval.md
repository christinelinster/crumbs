# 008: Simple Zep recipe experiment

**Status:** Implemented; approved for commit and push

Keep the SDK integration small and readable:

- `client.py`: construct the Zep client from settings.
- `ingest.py`: serialize/add a versioned recipe snapshot and save the current conversation pair.
- `retrieval.py`: current/history searches and full source episode resolution.
- `app/chat_capture.py`: one ordered local Markdown file per handled chat request.

## Recipe discovery

Bitesize defaults to Zep graph search and also offers Vector RAG. The selected
backend goes to the existing chat endpoint/orchestrator. The Zep search handler
uses `graph.get_context(max_characters=5000, include_results=True)` and passes
its unchanged context block plus complete source recipes to the answer model.
The native response includes selected edges, nodes, observations, and thread summaries.
Source episode UUIDs on edges, nodes, and observations identify full recipes. A separate helper parses source episode JSON and identifies recipes using
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

Recipe episodes retain their complete JSON snapshot, use the stable recipe slug
as `document_id`, and record `recipe_slug` plus a content fingerprint in
metadata. Current searches filter active facts and resolve each candidate slug
to its newest ingested snapshot. Explicit recipe-history searches can include
superseded facts and source episodes.

Use the SDK directly for graph creation, episode/graph inspection, and separate
edge/node/episode/observation searches. Keep a simple vector/Zep comparison loop.
Inspect graph evidence and temporal facts in Zep's managed app. Bulk backfill
should use Zep's `zep-ingest` package rather than a custom importer; installing
or running a bulk import is outside this integration.

## One shared test user

Shared memory is opt-in and uses `ZEP_USER_UUID`. Everyone shares this identity;
there is no login or private ownership. For an enabled chat, create a Zep thread
lazily, retrieve a native user context block before routing, and save only the current
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

## Native context inspection

Use Zep's `include_results=True` to inspect the unchanged context block and
selected result arrays. `/api/chat` has no custom trace flag or trace response.
The final model receives that native context and full recipe JSON as tool data.
Retrieved content is data, never system or developer instructions.

Every valid `/api/chat` request writes a separate timestamped Markdown file in
the Git-ignored `.zep/requests/` directory, ordered as user query, exact Zep
requests/materialized blocks/results, complete final model input, and final
model/application output. Direct answers capture the router as the final call.
Failures preserve partial captures and the error type; disk-write errors are
logged without changing answer delivery. Validation failures before the handler
do not create files. Capture files include full conversation/source content and
remain locally until deleted. Capture state is isolated between requests.

The chat question is not added to the recipe graph before searching. Shared
memory retrieves user context before routing and saves the current chat pair
after answering. Use Zep's UI or episode debug APIs for asynchronous extraction
inspection. Debug Mode must be enabled before ingestion and requires plan support.

## Boundaries and verification

No workers, queues, budgets, ledgers, database migrations, or accounts. Recipe
revision metadata is a content fingerprint; it does not add a recipe database
or migration.
Existing credentials, graph data, canonical recipes, and vector retrieval stay
available. Graphiti and Neo4j remain the later integration.

Tests cover answer/card selection and order, serialization, stable source IDs,
backend routing, shared-user thread
checks, preference context, current-turn-only writes, save failures, and browser
session restoration/reset. They also cover current recipe version selection,
history retrieval, and native context reaching the final model input.
Normal tests mock external services. Live checks are separate and use only the
configured shared test identity.
