# Recipe API Implementation Plan

**Status:** Implemented

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Crumbs recipe summaries and complete slug-addressed details through a tested FastAPI boundary and connect the Bitesize client to it.

**Architecture:** Add a small FastAPI app factory with an injected database pool and a production lifespan that manages the existing pool. Keep SQL in `src/app/db/recipes.py`, expose canonical Crumbs JSON fields, and update Bitesize to use slugs and the separate detail endpoint.

**Tech Stack:** FastAPI, Pydantic, psycopg pool, React 19, Vite 8, Python `unittest`.

**Spec:** `docs/superpowers/specs/003-recipe-api-design.md`

## Global Constraints

- The API is read-only in this task: no schema, corpus, ingestion, or embedding changes.
- The public recipe identifier is the persisted `slug`; do not expose database IDs or embeddings.
- List responses contain summary metadata; detail responses contain complete stored ingredient and instruction sections directly.
- Bitesize must use relative `/api` requests and must not import Python modules or connect to Postgres.
- Chat, authentication, creator accounts, and multi-corpus isolation remain out of scope.
- Do not stage, commit, or push; leave the diff for user approval.

## Review Focus

- A recipe with a missing slug returns 404 rather than an unrelated recipe.
- A recipe with null `source_url`, optional nutrition, or no groups serializes valid JSON.
- Full detail responses preserve every stored ingredient and instruction in order.
- List requests do not require embeddings, since browsing should work before vector loading.
- The Bitesize detail route fetches the requested slug instead of assuming the summary list contains full instructions.

---

### Task 1: Add database read projections

**Files:**
- Modify: `src/app/db/recipes.py`
- Test: `tests/test_recipe_api.py`

**Interfaces:**
- Consumes: Existing `recipes`, `recipe_ingredients`, and `recipe_steps` tables.
- Produces: `list_recipe_summaries(conn) -> list[dict[str, object]]` and `get_recipe_by_slug(conn, slug) -> dict[str, object] | None`.

- [x] **Step 1: Write failing projection tests**

  Add fake connection tests that expect `list_recipe_summaries` to return canonical metadata without `id`, `ingredients`, `instructions`, or `embedding`, and expect `get_recipe_by_slug` to return complete ordered arrays and group markers while passing the requested slug as the query parameter.

- [x] **Step 2: Run the projection tests and verify the expected failure**

  Run:

  ```bash
  poetry run python -m unittest tests.test_recipe_api.RecipeProjectionTests -v
  ```

  Expected: FAIL because the two database projection functions do not exist yet.

- [x] **Step 3: Implement the minimal SQL projections**

  Add dedicated field tuples and read functions in `src/app/db/recipes.py`. The summary query must use `ORDER BY r.title, r.slug` and no embedding predicate. The detail query must use `WHERE r.slug = %s`, order child arrays by `position`, and return empty arrays for recipes without group markers.

- [x] **Step 4: Run the projection tests and verify they pass**

  Run the same focused command. Expected: PASS.

### Task 1 follow-up: Compose shared projection field tuples

**Files:**
- Modify: `src/app/db/recipes.py`
- Test: `tests/test_recipe_api.py`

**Interfaces:**
- Consumes: The completed projection field tuples from Task 1.
- Produces: Shared metadata and source-field tuples composed into the summary
  and detail field tuples without changing their order.

- [x] **Step 1: Add a failing composition test**

  Assert that the public projection tuples are composed from shared metadata and
  source-field tuples, while preserving the existing field order.

- [x] **Step 2: Run the focused test and verify it fails**

  Run:

  ```bash
  poetry run python -m unittest tests.test_recipe_api.RecipeProjectionFieldTests -v
  ```

  Expected: FAIL because the shared tuple constants do not exist yet.

- [x] **Step 3: Compose the field tuples**

  Define `RECIPE_METADATA_FIELDS` and `RECIPE_SOURCE_FIELDS`, then build the
  existing projection tuples by concatenating those shared tuples with their
  projection-specific fields.

- [x] **Step 4: Run the focused test and the projection tests**

  Run both focused test classes. Expected: all tests pass and the SQL mapping
  behavior remains unchanged.

### Task 1 follow-up: Narrow the browse summary projection

**Files:**
- Modify: `src/app/db/recipes.py`
- Modify: `tests/test_recipe_api.py`
- Modify: `docs/superpowers/specs/003-recipe-api-design.md`

**Interfaces:**
- Consumes: The existing summary and detail projections.
- Produces: A lightweight `list_recipe_summaries` payload containing only the
  slug, title, category, tags, time, and nutrition fields needed by the
  Bitesize home-page cards. Detail and RAG projections retain full metadata.

- [x] **Step 1: Update the projection tests first**

  Require the list projection to return only the home-page card fields while
  keeping the full detail and RAG field tuples unchanged.

- [x] **Step 2: Run the focused tests and verify the expected failure**

  Run:

  ```bash
  poetry run python -m unittest tests.test_recipe_api -v
  ```

  Expected: FAIL because the list SQL and field tuples still include the old
  full summary metadata.

- [x] **Step 3: Narrow only the list projection**

  Define the summary field tuple, update `list_recipe_summaries`'s `SELECT`,
  and preserve the complete metadata tuple used by detail and similarity
  context.

- [x] **Step 4: Update the recipe API contract documentation**

  Document the reduced `GET /api/recipes` response and distinguish it from
  the complete detail response and chat recipe-card response.

- [x] **Step 5: Run focused and full verification**

  Run the recipe API tests, the full Python suite, and `git diff --check`.

### Task 2: Create the FastAPI recipe application

**Files:**
- Create: `src/app/api.py`
- Modify: `tests/test_recipe_api.py`
- Modify: `pyproject.toml`
- Modify: `poetry.lock`

**Interfaces:**
- Consumes: `list_recipe_summaries` and `get_recipe_by_slug` from Task 1.
- Produces: `create_app(database_pool=pool) -> FastAPI` and module-level `app` for `uvicorn app.api:app`.

- [x] **Step 1: Write failing endpoint tests**

  Add a fake pool context manager and FastAPI `TestClient` tests for `GET /api/recipes`, `GET /api/recipes/steamed-eggs`, and a missing-slug response. Assert that the list and detail JSON use canonical fields, that detail includes complete arrays and group markers, and that a missing recipe returns status 404 with a clear detail message.

- [x] **Step 2: Run the endpoint tests and verify the expected failure**

  Run:

  ```bash
  poetry run python -m unittest tests.test_recipe_api.RecipeApiTests -v
  ```

  Expected: FAIL because `app.api` and its routes do not exist yet.

- [x] **Step 3: Add response models, lifespan, and routes**

  Implement `create_app(database_pool=pool)` with Pydantic response models, a lifespan that enters the injected pool, synchronous read-only routes, and `HTTPException(status_code=404, detail=...)` for unknown slugs. Keep SQL out of route functions. Add `uvicorn` as the runtime dependency so the documented app entry point is runnable.

- [x] **Step 4: Run the endpoint tests and verify they pass**

  Run the same focused command. Expected: PASS.

### Task 3: Adapt Bitesize to the canonical recipe API

**Files:**
- Modify: `clients/bitesize/src/hooks/useRecipes.jsx`
- Create: `clients/bitesize/src/hooks/useRecipe.js`
- Modify: `clients/bitesize/src/pages/Home.jsx`
- Modify: `clients/bitesize/src/pages/RecipeDetail.jsx`
- Modify: `clients/bitesize/src/components/RecipeCard.jsx`
- Modify: `clients/bitesize/src/components/Filters.jsx`
- Modify: `clients/bitesize/src/index.css`
- Modify: `clients/bitesize/README.md`

**Interfaces:**
- Consumes: `GET /api/recipes` summary objects and `GET /api/recipes/{slug}` detail objects from Task 2.
- Produces: Bitesize browsing and detail pages that use `slug`, `title`, category and tag arrays, `total_time_minutes`, nutrition fields, and complete detail arrays.

- [x] **Step 1: Update client data loading and route identity**

  Change list filtering, favourites, card links, and route lookup to use `slug`. Add a cached `useRecipe(slug)` hook that fetches the detail endpoint and exposes loading, error, retry, and recipe state independently from the summary list.

- [x] **Step 2: Render canonical fields and preserved group markers**

  Render the list-card fields (`title`, category, tags, `total_time_minutes`,
  calories, protein, carbs, and fat), display category arrays safely, and add
  group headings before the matching ingredient and instruction positions. Keep
  the existing ingredient highlighting functions operating on the raw string
  arrays.

- [x] **Step 3: Run the client lint and build checks**

  Run from `clients/bitesize/`:

  ```bash
  npm run lint
  npm run build
  ```

  Expected: both commands exit successfully; the existing Fast Refresh warning may remain non-fatal.

- [x] **Step 4: Update client run instructions**

  Document the Crumbs API command `poetry run uvicorn app.api:app --reload --port 3001` from the repository root and keep the client command in the client README.

### Task 4: Update documentation and run the full verification suite

**Files:**
- Modify: `SPEC.md`
- Modify: `docs/README.md`
- Modify: `docs/bitesize-next-steps.md`
- Modify: `docs/superpowers/specs/003-recipe-api-design.md`
- Test: `tests/**`

**Interfaces:**
- Consumes: The implemented API and client behavior from Tasks 1 through 3.
- Produces: Documentation that marks the recipe API stage complete and records the next stage as chat.

- [x] **Step 1: Mark the API stage and route the next stage**

  Add feature 003 to `SPEC.md`, link it from `docs/README.md`, mark the API design as implemented, and update `docs/bitesize-next-steps.md` so chat is the next implementation stage.

- [x] **Step 2: Run the full Python suite**

  ```bash
  poetry run python -m unittest discover -s tests -v
  ```

  Expected: all existing and new tests pass.

- [x] **Step 3: Run final client verification and inspect the diff**

  Run `npm run lint`, `npm run build`, and `git diff --check`; review `git status --short` without staging or committing.

## Superseded API group-boundary revision

The user initially approved replacing per-item `{position, group_position,
group_name}` fields with one `{start, name}` entry per group. The user later
approved returning the canonical section objects directly; this boundary
revision is superseded.

- [x] Implement the temporary boundary response.
- [x] Update Bitesize for the temporary boundary response.

## Approved Direct-Section API Revision

The recipe detail endpoint returns the stored `ingredient_sections` and
`instruction_sections` with `kind`, nullable `name`, and ordered `items`. It
does not duplicate those contents in flat arrays or group boundary fields.
Bitesize renders sections directly and flattens only where local highlighting
logic needs ordered ingredient items.

- [x] Update the API specification to define direct sections as the response contract.
- [x] Update `RecipeDetail` and the endpoint test for the direct section fields.
- [x] Update Bitesize rendering and tests for direct sections.
- [x] Run Python API/group tests, the full Python suite, and Bitesize tests, lint, and build. The focused tests and client checks pass; the full Python suite has the known corpus-count mismatch (`test_parses_all_current_corpus_files`, expects 234 while 222 Markdown files are present).
