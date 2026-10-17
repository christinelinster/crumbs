# Recipe Content Arrays Implementation Plan

**Status:** Implemented

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` after the user selects native execution, or `superpowers:subagent-driven-development` after the user selects subagent-driven execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store ordered ingredients and instructions on each recipe row while preserving group headings and retrieval behavior, and expose canonical sections directly in the recipe detail API.

**Architecture:** Raw Markdown parser fields are normalized to ordered ingredient and instruction sections before embedding and persistence. Sections are canonical in the application and in JSONB; every section has `kind`, `name`, and `items`, with `name: null` for ungrouped content. Repository reads, RAG context, and recipe detail API responses retain sections. Bitesize renders sections directly and flattens items locally only for ingredient highlighting. The schema creates the target shape directly.

**Scope clarification (approved):** The existing database is already migrated or can be safely recreated, and future setup runs target a fresh database. Therefore `setup_database()` executes `schema.sql` only. There is no legacy child-table migration in the codebase. Setup assumes the target schema is fresh or already present; it does not alter an existing legacy `recipes` table. The PostgreSQL database itself must already exist.

**Tech Stack:** Python, psycopg, PostgreSQL JSONB, pgvector, `unittest`.

**Spec:** [docs/superpowers/specs/007-recipe-content-arrays.md](../specs/007-recipe-content-arrays.md)

## Global Constraints

- Keep section and item order, vector ranking, threshold, and result limit. The recipe detail API returns only canonical sections for ingredients and instructions.
- The database enforces basic required columns and storage types; do not add duplicate semantic validation for manually reviewed list content or group positions.
- Each loader run embeds and upserts every Markdown file present. It does not delete database recipes when Markdown files are absent.
- Do not add exact ingredient filtering, per-item query/update features, or new embeddings.
- Do not stage, commit, or push without explicit user instruction.

## Review Focus

- Item order, repeated group names, ungrouped content, and unnamed groups round-trip through storage and the direct API response.
- Existing non-content API fields and chat answer behavior remain unchanged.
  The detail API returns canonical section fields; similarity behavior remains
  unchanged.
- Fresh schema setup creates both JSONB fields, omits child tables, and reruns without changing data.
- Setup does not claim to upgrade an existing legacy child-table schema.

## Current Database Query Impact

| Path | Current behavior | Implemented change |
| --- | --- | --- |
| `list_recipe_summaries` | Reads summary fields directly from `recipes`. | No query change. |
| `get_recipe_by_slug` | Aggregates ingredients, instructions, and group markers from child rows. | Returns canonical section arrays directly to the recipe detail API. |
| `find_similar_recipes` | Aggregates child rows alongside vector similarity scoring. | Returns section arrays; the score formula, threshold, ordering, and limit are unchanged. |
| `save_recipe` | Upserts recipe metadata, then deletes and inserts child rows. | Upserts normalized metadata and both canonical JSONB arrays on the recipe row. |
| `setup_database` | Connects to the database selected by `PG_DB` and executes schema SQL in a transaction. | Still executes schema SQL only. It supports a fresh database or one already using the target schema; it does not upgrade a legacy table. |

The new schema removes per-item uniqueness, position, and foreign-key constraints,
as well as the unused normalized ingredient-name index. The loader does not
populate normalized names and current retrieval does not query individual items.
JSONB arrays have non-null empty-array defaults and top-level array checks. The
recipe detail API returns those canonical JSONB sections directly; Bitesize
derives a flat ingredient list only for its highlighting helper.

## File Map

- `src/app/db/schema.sql` defines the target recipe table inside an already-created database.
- `src/app/db/setup.py` runs only that schema SQL in one transaction.
- `src/app/paths.py` provides the central schema path.
- `src/app/ingestion/groups.py` normalizes parser boundaries to canonical sections.
- `src/app/db/recipes.py` upserts canonical arrays and returns them unchanged on reads.
- `src/app/api.py` validates and returns canonical recipe sections in the detail response.
- `tests/test_recipe_content_schema.py` checks fresh-schema DDL and safe reruns in a rolled-back PostgreSQL namespace.
- `tests/test_module_paths.py`, `tests/test_recipe_groups.py`, `tests/test_recipe_api.py`, `tests/test_query.py`, `tests/test_load_embeddings.py`, and `tests/test_chat_api.py` cover setup routing, persistence, projections, API compatibility, and loader behavior.
- `docs/decisions/004-recipe-content-arrays.md` records the storage decision; architecture, corpus, importing, and testing docs describe current behavior.

### Task 1: Define the schema-only setup path

**Files:** `src/app/db/schema.sql`, `src/app/db/setup.py`, `src/app/paths.py`, `tests/test_module_paths.py`, `tests/test_recipe_content_schema.py`

- [x] Assert setup runs only `schema.sql` inside its transaction and exposes no migration SQL path.
- [x] Define `ingredient_sections` and `instruction_sections` as non-null JSONB arrays with empty defaults and top-level array checks. Remove the child-table declarations and normalized-name index.
- [x] Verify fresh schema creation and a data-preserving rerun in a transaction-local PostgreSQL namespace. Roll back the test DDL and data; do not modify persistent application tables.

### Task 2: Normalize and persist canonical sections

**Files:** `src/app/db/recipes.py`, `src/app/ingestion/groups.py`, `src/app/api.py`, `clients/bitesize/src/utils/recipe.js`, `tests/test_recipe_groups.py`, `tests/test_recipe_api.py`, `clients/bitesize/src/utils/recipe.test.js`, `tests/test_load_embeddings.py`, and `tests/test_query.py`

- [x] Test parent-row writes and conversion for ungrouped content, repeated group names, and unnamed groups.
- [x] Normalize raw parser lists and group boundaries to ordered section arrays before embedding and persistence. Every section includes `kind`, `name`, and `items`; `name` is `null` for ungrouped sections.
- [x] Write both section arrays in the recipe upsert and remove the child-table write loops.
- [x] Keep repository detail and similarity reads in canonical section form. Keep list summaries, vector scoring, threshold, ordering, and limit unchanged.
- [x] Return canonical ingredient and instruction sections directly from the recipe detail API and remove the flat lists and group boundary fields.
- [x] Update Bitesize to render section objects directly; derive flat ingredient and instruction items only for existing highlighting behavior.
- [x] Run focused group, API, loader, and query tests. One pre-existing uncommitted corpus-count assertion expects 234 files while 222 Markdown files are present; keep that unrelated edit unchanged.

### Task 3: Verify loader and query behavior across clients

**Files:** `src/app/ingestion/load_embeddings.py`, `tests/test_load_embeddings.py`, `tests/test_query.py`.

- [x] Confirm Markdown parsing is a raw stage, normalization produces sections, and embedding text consumes those sections with the current order and group boundaries.
- [x] Confirm loader runs only upsert present Markdown files and do not delete database recipes whose Markdown is absent.
- [x] Confirm RAG context retains canonical sections and public chat output retains its current fields.

### Task 4: Update durable storage and operating documentation

**Files:** `docs/technical-decisions.md`, `docs/architecture.md`, `docs/recipe-corpus-format.md`, `docs/importing-recipes.md`, `docs/testing.md`, `docs/README.md`, `docs/decisions/004-recipe-content-arrays.md`, and recipe API specifications/plans

- [x] Document JSONB section storage, the direct API contract, and the removed child-table constraints/index.
- [x] Document that setup targets a fresh or already-migrated database and does not upgrade a legacy child-table schema.
- [x] Document loader re-embedding of present files and no deletion for absent files; verify local links.

### Task 5: Run final verification and review the diff

- [x] Search source, tests, and docs for old child-table dependencies. Remaining references are schema absence assertions, historical design docs, and test descriptions; live query/write paths do not depend on child tables.
- [x] Run the PostgreSQL schema check: `env CRUMBS_RUN_PG_SCHEMA_TESTS=1 poetry run python -m unittest tests.test_recipe_content_schema -v` (1 test passed).
- [x] Run `poetry run python -m unittest discover -s tests -v`. Result: 82 tests, 1 known corpus-count failure (`test_parses_all_current_corpus_files`, expects 234 while 222 Markdown files are present), and 1 PostgreSQL schema test skipped unless explicitly enabled. All other tests passed.
- [x] Run `git diff --check`; confirm no files were staged or committed.

## Approved Scope Revision

The user clarified that the current database is already migrated or safe to
recreate and future setup runs target a fresh database. This removed the need
for a compatibility migration. The implementation now runs only `schema.sql`,
and the PostgreSQL integration test verifies fresh schema creation and reruns.

- [x] Remove migration SQL and its path, and change `setup_database()` to run
  only `schema.sql`.
- [x] Replace legacy backfill checks with a fresh-schema test and update the
  specification, ADR, architecture, operating, and testing documentation.
- [x] Re-run unit and PostgreSQL schema checks. The full suite retains only the
  previously recorded corpus-count mismatch.

## Approved Canonical Section Representation

The user specified the canonical data flow as scraper/parser representation,
normalization, ordered sections, then PostgreSQL JSONB. Every section stores
`kind`, `name`, and `items`; ungrouped sections store `name: null`. Repository
reads and model context keep sections. The earlier API design preserved the
flat response contract; that projection was superseded by the direct-section
API revision below.

- [x] Normalize parser output before embedding and persistence.
- [x] Keep database reads in section form and pass those sections to RAG context.
- [x] Update examples and verify the full request and recipe detail paths.

## Superseded API Group-Boundary Revision

The user initially approved replacing per-item `{position, group_position,
group_name}` entries with one `{start, name}` boundary per group. This choice
was later superseded by the approved direct-section API contract below.

- [x] Implement the temporary flat arrays and group boundary response.
- [x] Update Bitesize for the temporary boundary response.

## Approved Direct-Section API Revision

The user approved returning the canonical `ingredient_sections` and
`instruction_sections` as the only ingredient and instruction fields in recipe
detail responses. Each section keeps `kind`, nullable `name`, and ordered
`items`. Bitesize renders the sections directly and derives flat arrays locally
only for its highlighting helper.

- [x] Update the API and storage specifications to define the direct-section contract.
- [x] Update the API response model and endpoint test; remove the API flattening helper.
- [x] Update Bitesize rendering and tests to use direct sections.
- [x] Run Python API/group tests, the full Python suite, and Bitesize tests, lint, and build. The focused tests and client checks pass; the full Python suite has the known corpus-count mismatch above.
