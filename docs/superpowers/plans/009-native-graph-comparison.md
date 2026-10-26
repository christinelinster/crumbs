# Native Graph Comparison Implementation Plan

State: Implemented - approved context-flow update

> Execute inline, preserving existing workspace edits. No staging or commits.

**Goal:** Compare native Zep and Graphiti using identical Markdown with observable ingestion and retrieval.

**Architecture:** Thin backend ingestion/retrieval modules, one answer model, and shared local Markdown rendering. Keep backend graph results distinct rather than normalizing away native capabilities.

**Tech stack:** Existing Python, FastAPI, Zep v4 SDK, Graphiti, unittest.

**Spec:** `docs/superpowers/specs/009-native-graph-comparison.md`

## Global constraints

No live provisioning, ingestion, deletion, new dependencies, or recipe cards for graph backends. Preserve vector behavior, native summary selection, opt-in memory writes, and thread ownership validation.

## Review focus

Empty user graphs; asynchronous Zep processing; source lookup failures; partial traces; summary availability without forced injection.

## Tasks

- [x] 1. Markdown ingestion and inspection: update `zep/ingest.py`, `graphiti/ingest.py`, add backend `inspect.py` modules and shared ingestion report writer in `chat_capture.py`. Test exact Unicode/newline preservation, status reporting, summary inspection, and unavailable debug diagnostics in `test_zep.py`, `test_graphiti.py`, and report tests.
- [x] 2. Native graph retrieval: replace Zep JSON/revision resolution with `search_recipes(query)` and provenance source fetches; update `rag/tools.py` and `rag/query.py` so both graph backends search user/recipe scopes and return chat-only answers without Postgres detail tools. Test empty results, deduplicated sources, distinct user data, native context, and unchanged vector behavior.
- [x] 3. API and request tracing: move thread ownership/preparation and writes to `zep/memory.py`; retain optional cross-backend user-memory behavior while avoiding duplicate Zep reads in graph mode. Record router calls, native requests/results, supplemental sources, and final model calls. Update API/memory/capture tests.
- [x] 4. Document runnable ingestion/inspection commands, stored summary differences, and retrieval settings. Run affected Python tests, then the full Python suite and relevant client tests; inspect the scoped diff. Mark spec/plan implemented only after checks pass.

## Execution notes

The user approved implementation; execute in the current checkout because its existing uncommitted integration is the starting point. Do not relocate or discard it. No additional design approval is needed.

Final validation: `poetry run python -m unittest discover -s tests` ran 152 tests with no failures and one skipped database integration check. `npm --prefix clients/bitesize test`: 41 passed. `npm --prefix clients/bitesize run build`: passed. `git diff --check`: passed.

Review fixes: use Graphiti namespace edge listing for empty graphs; serialize generated stored-node fields in ingestion reports; record whether an answer-model call was attempted rather than claiming unsent retrieval results were delivered. All three have passing regression tests.

Ruling: graph answers use plain text rather than the vector card-selection schema, because graph cards are out of scope. Existing vector behavior is preserved; stale assertions referring to removed prompt wording and settings were updated to assert actual current behavior.

No commits, staging, live service calls, or graph mutations. The final diff excludes pre-existing workspace changes.

## Implemented follow-up: Zep thread context and bounded model history

- [x] 5. Replace Zep user-graph `graph.get_context` calls with the default thread flow: append the current user message, call `thread.get_context`, and save the assistant reply after generation. Keep recipe `graph.get_context` search in the shared graph.
- [x] 6. Keep the UI transcript intact. Zep manages thread context without browser-supplied history; Graphiti keeps bounded recent history and fact search. Do not inject saga summaries or fetch whole conversation episodes. Update request traces and usage docs to describe both retrieval paths.
- [x] 7. Run syntax/diff checks and review the scoped diff. Existing tests were updated but not run per the no-test-run instruction.

## Implemented follow-up: Zep-managed conversation memory

- [x] Remove browser-supplied history from Zep requests and ignore API history in Zep model calls; let `thread.get_context()` choose context. Keep Graphiti's five-message window.
- [x] Update request prompt wording, traces, and docs. Tests were not run per the no-test-run instruction.


Follow-up verification: Python and JavaScript syntax checks and `git diff --check` passed. Tests were not run at Christine's instruction. No live graph calls or mutations were made.

## Implemented follow-up: Zep-managed conversation history

- [x] Do not send browser conversation history in Zep-mode model requests; rely on `thread.get_context()` for conversation memory. Keep Graphiti's existing five-message window.
- [x] Update request-building behavior and docs. Tests were not run per the no-test-run instruction.
