# 008: Simple Zep recipe experiment

**Status:** Superseded in part by [009-native-graph-comparison.md](009-native-graph-comparison.md).

Historical implementation: the JSON ingestion, revision resolution, graph recipe
cards, and tracing requirements below are replaced by specification 009.

Specification: [008-zep-recipe-retrieval.md](../specs/008-zep-recipe-retrieval.md).

- [x] Keep three thin SDK modules. Remove the earlier worker/ledger/revision
  infrastructure without deleting existing data or credentials.
- [x] Add a Vector/Zep selector to Bitesize, defaulting to Zep, and route chat
  discovery to the selected backend. Preserve Zep's native assembled context.
- [x] Resolve full source recipe snapshots and use them for recipe cards.
- [x] Add one configured shared test user, lazy per-chat thread creation,
  preference retrieval, and direct current-turn-only message writes.
- [x] Validate supplied threads against the configured shared user. Exclude
  assistant messages from extraction while retaining them in Zep history.
- [x] Add the opt-in shared-memory toggle, shared-user notice, and conversation
  save status distinct from asynchronous graph processing.
- [x] Persist the transcript/cards/statuses, toggle, backend, and thread UUID in
  one browser record. New chat clears the transcript and thread pointer while
  preserving shared graph memory. Handle unavailable browser storage.
- [x] Document configuration, SDK inspection, bulk-backfill boundaries, and
  manual memory/reload/new-chat testing.
- [x] Save one local Markdown capture per handled chat request, ordered as query,
  native context/results, complete final LLM input, and final output. Isolate
  concurrent captures, retain partial failures, and keep files out of Git.
- [x] Verify the final code:
  - `.venv/bin/python -m unittest discover -s tests -q`: 127 tests, one skipped;
    exit 0.
  - `npm --prefix clients/bitesize test`: 35 passed.
  - `npm --prefix clients/bitesize run build`: passed.
  - `npm --prefix clients/bitesize run lint`: passed with the existing
    `useRecipes.jsx` Fast Refresh warning.
  - `git diff --check`: passed.
  - A live recipe query wrote a Markdown capture. The materialized Zep context
    matched the final tool output exactly, and the captured model answer matched
    the application answer. The file contained no configured API keys and was
    confirmed ignored by Git.
  - Live chat returned HTTP 200, a successful save status, and three cards. A
    separate SDK read confirmed both conversation messages in the created thread.
    The initial smoke assertion assumed their listing order; Zep gives this pair
    identical creation timestamps and listed assistant before user. Browser
    recovery preserves local send order and does not depend on that listing.
  - Browser reload/reset is covered by storage/request tests, not an interactive
    browser check. No extraction polling or automatic retries were added.
- [x] User authorized commit and push of the current uncommitted changes.

## Enforced ingredient exclusions

**Status:** Superseded by user request

Application-side ingredient exclusions were removed at the user's request.
The matcher, exclusion tool arguments, and matcher-specific tests are removed.
Full episode recipe content and raw graph facts reach the answer model for
preference assessment; native temporal preference filters remain in place.
Regression coverage confirms there is no application ingredient filtering.

## Answer/card alignment

- [x] Reproduce: all retrieved cards are returned even when the answer selects fewer.
- [x] Add regression coverage for one/three/six/no selections in both backends,
  ordering, duplicates, unknown slugs, and missing parsed output.
- [x] Return answer text and selected slugs from the same synthesis call; use
  only those known cards, in answer order.
- [x] Update tests/docs/label and verify the final diff.
  The final Python suite passed (113 tests, one skipped); frontend tests passed
  (35), build passed, lint retained only the existing warning.
  `poetry run python /tmp/crumbs-card-selection-smoke.py` passed: HTTP 200, three
  numbered recommendations, three matching cards in answer order. Shared-memory
  writes were off for that check.

## Ingredient verification and temporal preference retrieval

**Status:** Superseded in part by [009-native-graph-comparison.md](009-native-graph-comparison.md).

Historical implementation: the JSON ingestion, revision resolution, graph recipe
cards, and tracing requirements below are replaced by specification 009.

- [x] Supply full original source episode recipes to the Zep answer model and
  build cards from those same records, without Postgres reads in discovery.
  Preserve ingredient/instruction lists and groups, deduplicate sources and
  recipe slugs, and skip invalid/non-recipe/mismatched source content.
- [x] Require checking every ingredient/instruction section against explicit
  exclusions and remembered avoidance preferences; exclude violating or
  unverifiable candidates instead of offering them as imperfect matches.
- [x] Use Zep's native `invalid_at is_null` AND `expired_at is_null` date filters
  for preference retrieval. Leave invalidation and active contradictions to Zep.
- [x] Add regression coverage for ingredients missing from graph facts, direct
  episode JSON parsing, malformed sources, discovery without Postgres, and the
  native filter payload emitted by the actual SDK.
- [x] Verify the updated Python suite and diff:
  `poetry run python -m unittest discover -s tests` passed, 119 tests with one
  skipped; `git diff --check` passed.
- [x] Verify live ingredient exclusions using full recipes retrieved from Zep:
  `poetry run python /private/tmp/crumbs-ingredient-smoke.py` passed. Discovery
  returned nine full episode recipes and matching cards with Postgres access
  prohibited. The model selected the onion/garlic-free alternative and returned
  no selections when all candidates contained avoided ingredients. Native date
  filters remained accepted. No graph or conversation writes were made.
- [x] Review the final Zep-only discovery changes. No blocking issues found;
  fixed null categories/tags in episode-derived cards with a regression test.
- [x] User authorized commit and push of the remaining code/test diff.
