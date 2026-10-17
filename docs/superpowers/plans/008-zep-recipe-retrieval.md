# 008: Simple Zep recipe experiment

**Status:** Implemented; awaiting user review

Specification: [008-zep-recipe-retrieval.md](../specs/008-zep-recipe-retrieval.md).

- [x] Keep three thin SDK modules. Remove the earlier worker/ledger/revision
  infrastructure without deleting existing data or credentials.
- [x] Add a Vector/Zep selector to Bitesize, defaulting to Zep, and route chat
  discovery to the selected backend. Keep raw graph facts as Zep evidence.
- [x] Map source episode slugs to existing recipe cards in a separate helper.
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
- [x] Verify the final code:
  - `poetry run python -m unittest discover -s tests -v`: 113 tests, one skipped;
    exit 0.
  - `npm --prefix clients/bitesize test`: 35 passed.
  - `npm --prefix clients/bitesize run build`: passed.
  - `npm --prefix clients/bitesize run lint`: passed with the existing
    `useRecipes.jsx` Fast Refresh warning.
  - `git diff --check`: passed.
  - Live chat returned HTTP 200, a successful save status, and three cards. A
    separate SDK read confirmed both conversation messages in the created thread.
    The initial smoke assertion assumed their listing order; Zep gives this pair
    identical creation timestamps and listed assistant before user. Browser
    recovery preserves local send order and does not depend on that listing.
  - Browser reload/reset is covered by storage/request tests, not an interactive
    browser check. No extraction polling or automatic retries were added.
- [ ] User approval of the uncommitted diff. Nothing staged, committed, or pushed.

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
