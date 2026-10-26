# Native Zep and Graphiti comparison

State: Implemented

## Intent

Make Crumbs a simple way to inspect native Zep and Graphiti ingestion and
retrieval using identical recipe Markdown and one shared answer model.
Christine will provide fresh recipe and user graphs. User graphs start empty;
no synthetic preferences or previous conversation history are imported.

## Chosen approach

Use each backend's native extraction and retrieval. Identical fact-only search
was considered and rejected because it would hide Zep's context assembly.
Neither backend is required to return the same context types or results.
JSON recipe snapshots and card construction are unnecessary for this experiment.

## Ingestion and storage inspection

- Both recipe ingestion functions accept a Markdown path and submit its exact
  UTF-8 content as a text episode using native default extraction.
- Remove Zep recipe JSON serialization, revision hashes, and application-level
  revision resolution. Keep simple source identity and provenance.
- Ingestion and graph inspection return native results without writing local
  Markdown reports. Request traces are the only local Markdown captures.
- Graphiti ingestion returns graph results immediately. Zep submission and
  completed extraction are separate: provide an explicit later inspection step,
  without background workers or automatic polling.
- Include Zep ingestion diagnostics when explicitly requested and available.
  Do not enable debug mode automatically. Missing diagnostics remain unavailable.
- Explain entity summaries, user summaries, saga/thread summaries, and community
  summaries where supported. Distinguish API exposure from actual stored content;
  do not manufacture summaries or claim hidden Zep implementation details.

## Retrieval and answers

- Zep retrieves Christine's user context with its default `thread.get_context()`
  flow after adding the current user message to that thread. Zep manages its own
  query window and relevance selection; Crumbs sets no conversation turn count.
- The Zep recipe tool searches only the configured shared recipe graph with the
  router's concise search query and preserves Zep's native context and results.
- Graphiti keeps its native active-fact search against the recipe and user groups.
  It returns relevant facts, not entire episodes or all saga histories.
- Keep user context distinct from recipe context through retrieval, traces, and
  answer synthesis. User preferences are not recipe facts.
- Follow selected recipe provenance to original Markdown episodes, deduplicating
  source fetches. Identify this source supplementation separately from native
  search results. Do not parse Markdown into recipe JSON or consult Postgres for
  graph recipe details.
- Do not inject summaries merely because they exist. Only context returned by
  the chosen retrieval path, plus clearly identified recipe sources, reaches the
  answer model. Available summaries can be inspected separately.
- Graph backends expose one native search tool for discovery, recipe details,
  and preference questions. Return chat answers and empty recipe-card lists.
  Vector retrieval and its cards retain their existing behavior.
- Keep one configured answer model and common grounding instructions, with only
  the adaptations needed to interpret each backend's returned context.

## API and conversation memory

- Move Zep-specific thread preparation, ownership validation, and conversation
  writes into its backend module so the chat handler coordinates the request.
- Preserve request/response fields and frontend thread continuity. Selecting Zep
  automatically saves each current user message before context retrieval, then
  saves the assistant response after generation. Graphiti saves the current turn
  as before; Vector RAG saves to neither graph.
- Zep sends no browser-supplied conversation history to the model. It supplies
  user memory through its managed thread context. Graphiti sends at most six
  conversation messages (five prior plus current) and supplies relevant facts
  from its user group. Assistant text remains context, not preference evidence.
- Preserve Graphiti's existing explicit saga-summary refresh and Zep's managed
  summary behavior. Creating a summary does not automatically inject it into retrieval.

## Request reports

Use `.zep/requests/` and `.graphiti/requests/` only when that backend is called.
Each readable Markdown report contains:

1. The original user query and the actual model-selected search query.
2. Every retrieval request with graph identity, filters, limits, and exposed
   configuration; mark settings managed internally by Zep as unexposed.
3. Native results separated by user/recipe origin, and supplemental source fetches.
4. Router request/response and tool-call linkage, followed by the exact final
   answer-model request, including Zep's context and no browser-supplied history,
   or Graphiti's bounded history and retrieved context.
5. Final model output and application response.

Render clear text sections with real line breaks and explicit empty-result messages.
Do not duplicate request data as JSON. Traces describe what was actually
retrieved and sent, not hypothetical capabilities. Partial failures retain
completed stages.

## Scope and validation

Update the affected backend modules, API orchestration, tools, answer synthesis,
capture writer, tests, and usage documentation. No new dependencies, comparison
dashboard, forced summary retrieval, graph deletion, or automatic corpus migration.
Do not provision or populate live graphs during implementation.

Use mocked SDK tests to verify exact Markdown submission, separate graph reads,
source provenance, native-context preservation, opt-in writes and thread ownership,
graph-only recipe detail behavior, empty cards, and complete backend-specific
reports. Run affected existing tests and show the scoped diff before committing.

## Confirmation

Christine approved this design in the conversation before implementation.

## Verification

152 Python tests run with no failures (one database integration test skipped);
41 client tests passed; client production build passed. Independent review found
three issues, now covered by passing reproductions: empty Graphiti fact listings,
generated episode IDs in reports, and unsent results in partial-failure traces.
No live graph calls, provisioning, ingestion, or deletion were performed.
