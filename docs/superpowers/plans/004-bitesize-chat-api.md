# Bitesize Chat API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented and verified\
**Approval:** Approved contract; implementation is ready for review

**Goal:** Expose the existing grounded Crumbs query flow through a tested
`POST /api/chat` endpoint that Bitesize can call before the React chat panel is
implemented.

**Architecture:** Keep conversation history request-scoped and in memory. The
Bitesize client sends prior `{role, content}` messages with each request; the
API never stores a global conversation list or writes messages to Postgres.
Reuse the existing embedding, similarity-search, prompt, and history behavior,
but add a structured query result so the API can return the answer and
condensed clickable recipe cards from the same retrieval operation. The optional
`recipe_slug` selects an exact recipe-detail context path before embedding or
vector retrieval; general questions use vector retrieval and return scored
recipe cards.

**Tech Stack:** FastAPI, Pydantic, OpenAI Python SDK, psycopg pool, pgvector,
and the existing Python `unittest` suite.

**Approved contract:** `docs/superpowers/specs/004-bitesize-chat-api.md`
is the endpoint-specific contract;
`SPEC.md`, `docs/product-requirements.md`, and `docs/bitesize-next-steps.md`
define the broader request fields, application-controlled retrieval settings,
in-memory history, guardrails, and response shape.

## Global constraints

- The default retrieval limit remains `3`; callers may provide a positive
  integer override, and the LLM never chooses the limit.
- Similarity filtering is owned by
  `app.db.recipes.DEFAULT_SIMILARITY_THRESHOLD`, currently `0.5`, and is
  applied in the database query before the result limit.
- Clearly unrelated questions use the normal retrieval path; the system prompt
  tells the model not to force recipe recommendations.
- `recipe_slug` is resolved by the persisted slug. A missing selected recipe
  returns 404 rather than silently answering from another recipe.
- Similarity-search `recipe_cards` contain only the condensed summary fields
  plus the numeric vector similarity score. Recipe-specific responses return an
  empty card array because the selected recipe is already on the detail page.
  IDs, embeddings, prompts, and full recipe context are not returned by the
  chat endpoint.
- Retrieved recipe context is request-scoped. Only user and assistant messages
  supplied in the request are passed to the model and updated in the local
  working list; no server-wide history is introduced.
- The CLI remains compatible with `process_query(...) -> str`.
- Tests use fake clients, pools, and database rows. No live OpenAI or Postgres
  service is required.
- Do not add a React panel, streaming, authentication, creator accounts,
  persistent conversation storage, or function calling in this stage.
- Do not stage, commit, or push; leave the implementation diff for review.

## Review focus

- A blank question, invalid history message, or non-positive limit fails before
  embedding or a database connection is leased.
- The database connection is released before the LLM request begins.
- The API returns cards from the exact same scored retrieval used to construct
  the answer context; it does not perform a second embedding or search.
- A selected `recipe_slug` is resolved before embedding or vector retrieval,
  included with its complete stored content, and returns no similarity cards.
- Empty vector retrieval produces a valid answer request with an empty card
  array and explicit no-match context.
- A clearly unrelated question still uses normal retrieval, while its response
  behavior is governed by the system prompt.
- Embedding, database, model, malformed-response, and truncation failures do
  not append false assistant messages and become explicit HTTP failures.
- Tests patch the query-layer OpenAI constructor, so they do not require
  OpenAI credentials; each production chat request closes its client after use.

## File map

- Modify `src/app/db/recipes.py` to apply the configured similarity threshold
  constant in the existing complete-recipe vector query.
- Modify `src/app/rag/query.py` to expose a structured query result, preserve
  the CLI string wrapper, support selected-recipe context, and keep
  recipe-card projection tied to one retrieval.
- Modify `src/app/api.py` to add chat request/response models and
  `POST /api/chat`; OpenAI client creation remains in the query layer.
- Modify `tests/test_query.py` for structured results, the configured threshold,
  selected recipe context, and unchanged history on failures.
- Create `tests/test_chat_api.py` for endpoint validation, successful response
  projection, selected-slug errors, and service failures.
- Modify `SPEC.md`, `docs/README.md`, `docs/architecture.md`, and
  `docs/bitesize-next-steps.md` after implementation to record feature 004 and
  route the next work to the React chat panel.

### Task 1: Extend retrieval and query orchestration with a structured result

**Files:**
- Modify: `src/app/db/recipes.py`
- Modify: `src/app/rag/query.py`
- Test: `tests/test_query.py`

**Interfaces:**
- `find_similar_recipes(conn, embedding, limit) -> list[dict[str, object]]`
- `QueryResult` exposes `answer: str` and `recipe_cards: list[dict[str, object]]`.
- `QueryGenerationError(RuntimeError)` and `RecipeNotFoundError(LookupError)`
  distinguish model output and selected-recipe failures for the HTTP layer.
- `process_query_result(question, history, *, database_pool=pool, limit=3, recipe_slug=None) -> QueryResult`
- Existing `process_query(...) -> str` delegates to `process_query_result(...).answer`, so the CLI contract remains unchanged.

- [x] **Step 1: Add failing query tests for the new result and controls**

  Extend the existing fake-row tests with these behaviors:

  ```python
  result = process_query_result(
      "What can I make with eggs?",
      [],
      database_pool=database_pool,
      limit=1,
  )

  self.assertEqual(result.answer, "Try the steamed eggs.")
  self.assertEqual(result.recipe_cards[0]["slug"], "steamed-eggs")
  self.assertEqual(connection.calls[0][1][-2:], (0.5, 1))
  ```

  Add a direct-slug fixture for `get_recipe_by_slug` and assert that the
  selected recipe's full ingredients, instructions, and group markers appear
  in the LLM context, while the selected recipe is not duplicated if vector
  retrieval already returned it. Add a missing-slug assertion and preserve the
  existing tests that require history to remain unchanged after failures.

- [x] **Step 2: Run the focused query tests and verify the expected failure**

  Run:

  ```bash
  poetry run python -m unittest tests.test_query -v
  ```

  Expected: FAIL because the configured threshold, structured result, and
  selected-recipe context path do not exist yet.

- [x] **Step 3: Add threshold filtering and structured orchestration**

  Apply `app.db.recipes.DEFAULT_SIMILARITY_THRESHOLD` in the existing SQL
  before `ORDER BY` and `LIMIT`, while preserving the existing `%s::vector`
  binding and null-vector exclusion. Keep the connection context limited to
  embedding retrieval and direct slug lookup.

  Keep the retrieval, selected-recipe lookup, prompt construction, model call,
  and history update in the result-producing function:

  ```python
  @dataclass(frozen=True)
  class QueryResult:
      answer: str
      recipe_cards: list[dict[str, object]]

  def process_query_result(..., recipe_slug=None) -> QueryResult:
      if recipe_slug is not None:
          with database_pool.connection() as conn:
              selected = get_recipe_by_slug(conn, recipe_slug)
          if selected is None:
              raise RecipeNotFoundError(recipe_slug)
          context_recipes = [selected]
          recipe_cards = []
      else:
          embedding = generate_embedding(client, question)
          with database_pool.connection() as conn:
              context_recipes = find_similar_recipes(
                  conn, embedding, limit
              )
          recipe_cards = build_recipe_cards(context_recipes)
      # Build the prompt, call the model, and append successful messages here.
      return QueryResult(answer, recipe_cards)

  def process_query(...):
      return process_query_result(...).answer
  ```

  Inputs and history are supplied by the application as valid values. Keep the
  existing system prompt and history append timing. Raise
  `QueryGenerationError` for empty, malformed, or truncated model responses.
  The selected recipe is context-only and does not receive a fabricated
  similarity score; the detail page already identifies the recipe being
  discussed.

- [x] **Step 4: Run query tests and the existing CLI tests**

  Run:

  ```bash
  poetry run python -m unittest tests.test_query tests.test_main -v
  ```

  Expected: all query and CLI tests pass, including the old string-returning
  `process_query` behavior and the new structured-result assertions.

### Task 2: Add the FastAPI chat endpoint and client lifecycle

**Files:**
- Modify: `src/app/api.py`
- Create: `tests/test_chat_api.py`

**Interfaces:**
- `ChatMessage` contains `role: Literal["user", "assistant"]` and nonempty `content`.
- `ChatRequest` contains `question`, `history`, `limit`, and optional
  `recipe_slug`.
- `RecipeCard` extends the condensed recipe summary with
  `similarity_score: float`.
- `ChatResponse` contains `answer: str` and `recipe_cards: list[RecipeCard]`.
- `create_app(database_pool=pool) -> FastAPI` accepts the database pool only;
  the query layer creates and closes its OpenAI client internally.
- `POST /api/chat` returns `ChatResponse` and never returns database IDs,
  embeddings, raw prompts, or conversation history.

- [x] **Step 1: Write failing endpoint tests**

  Build the endpoint with `TestClient`, the existing fake pool pattern, and a
  fake embedding/chat client. Cover:

  ```python
  response = test_client.post("/api/chat", json={
      "question": "What can I make with eggs?",
      "history": [{"role": "user", "content": "I want breakfast."}],
      "limit": 1,
  })

  self.assertEqual(response.status_code, 200)
  self.assertEqual(response.json(), {
      "answer": "Try the steamed eggs.",
      "recipe_cards": [{
          "slug": "steamed-eggs",
          "title": "Steamed Eggs",
          "category": ["breakfast"],
          "tags": ["eggs"],
          "total_time_minutes": 20,
          "calories": 180,
          "protein": 14,
          "carbs": 4,
          "fat": 10,
          "similarity_score": 0.91,
      }],
  })
  ```

  Also assert that omitted `limit` defaults to 3, malformed history and
  invalid limits return 422, an unknown `recipe_slug` returns 404, and an
  embedding/LLM failure returns a non-success service response without
  leaking raw exception text or adding history outside the request. Add a
  successful selected-slug request that returns the complete recipe-grounded
  answer with an empty `recipe_cards` array and does not call the embedding
  client.

- [x] **Step 2: Run the endpoint tests and verify the expected failure**

  Run:

  ```bash
  poetry run python -m unittest tests.test_chat_api -v
  ```

  Expected: FAIL because `POST /api/chat` and its response models do not exist.

- [x] **Step 3: Implement request models, lifecycle, and route**

  Add the models in `src/app/api.py` using a `default_factory` for history and
  strict positive validation for `limit`. Keep the route shape simple:

  ```python
  @api.post("/api/chat", response_model=ChatResponse)
  def chat(request: ChatRequest) -> ChatResponse:
      history = [message.model_dump() for message in request.history]
      try:
          result = process_query_result(
              request.question,
              history,
              database_pool=database_pool,
              limit=request.limit,
              recipe_slug=request.recipe_slug,
          )
      except RecipeNotFoundError as error:
          raise HTTPException(status_code=404, detail=str(error)) from error
      except QueryGenerationError as error:
          raise HTTPException(
              status_code=502,
              detail="chat model returned an invalid response",
          ) from error
      except (OSError, RuntimeError, ValueError) as error:
          raise HTTPException(
              status_code=503,
              detail="chat service unavailable",
          ) from error
      return ChatResponse(
          answer=result.answer,
          recipe_cards=result.recipe_cards,
      )
  ```

  Keep `create_app` responsible for the database pool only. The query layer
  creates `OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60.0,
  max_retries=2)` for each chat request and closes it after the request. Tests
  patch the query-layer constructor rather than passing a client through the
  API.

- [x] **Step 4: Run the endpoint tests and the recipe API tests**

  Run:

  ```bash
  poetry run python -m unittest tests.test_chat_api tests.test_recipe_api -v
  ```

  Expected: all chat and existing recipe browsing endpoint tests pass.

### Task 3: Document the chat boundary and mark roadmap progress

**Files:**
- Modify: `SPEC.md`
- Modify: `docs/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/bitesize-next-steps.md`
- Modify: `docs/superpowers/specs/004-bitesize-chat-api.md`

**Interfaces:**
- Documentation identifies feature 004 as the implemented Bitesize chat API.
- The roadmap marks the recipe API and chat API stages complete and identifies
  the React chat panel as the next stage.
- The chat API specification records request-scoped history, response cards,
  error behavior, the application-owned threshold, and the selected-slug
  context path.

- [x] **Step 1: Mark the approved feature specification as implemented**

  Update `docs/superpowers/specs/004-bitesize-chat-api.md` and the feature
  routing row in `SPEC.md` from `Approved` to `Implemented` after the endpoint
  behavior and tests are complete. Preserve the exact JSON request and
  response shapes, request-scoped history, similarity-card behavior, and
  selected-slug context path already approved in the specification.

- [x] **Step 2: Update project routing and next-step status**

  Add feature 004 to `SPEC.md`, link the new specification from `docs/README.md`,
  update `docs/architecture.md` with the API sequence, and change
  `docs/bitesize-next-steps.md` to:

  ```text
  1. [x] Recipe browsing and detail API
  2. [x] Chat API
  3. [ ] React chat panel
  4. [ ] Recipe-specific panel context
  ```

  Keep function calling, intent routing, authentication, creator support, and
  persistent history deferred.

- [x] **Step 3: Verify documentation consistency**

  Run:

  ```bash
  rg -n "api does not exist|chat API.*next|feature 004|recipe_cards|DEFAULT_SIMILARITY_THRESHOLD" SPEC.md docs
  git diff --check
  ```

  Inspect the results to ensure no document claims the chat API is still
  missing or that the API persists conversation history.

### Task 4: Run repository-wide verification

**Files:**
- Test: `tests/**`
- Verify: `clients/bitesize/`

**Interfaces:**
- The full Python suite and client checks remain green after the API addition.
- No live OpenAI or Postgres service is required for automated verification.

- [x] **Step 1: Run the focused backend suite**

  ```bash
  poetry run python -m unittest tests.test_query tests.test_chat_api tests.test_recipe_api tests.test_main -v
  ```

- [x] **Step 2: Run the full Python suite**

  ```bash
  poetry run python -m unittest discover -s tests -v
  ```

- [x] **Step 3: Run the client checks**

  From `clients/bitesize/`:

  ```bash
  npm test
  npm run lint
  npm run build
  ```

- [x] **Step 4: Inspect the final diff**

  Run `git status --short --untracked-files=all` and `git diff --check`.
  Confirm that no schema migration, database write endpoint, global history,
  or client API credential was added. Leave all changes unstaged for review;
  the React chat panel is the separate follow-up stage.

## Self-review coverage

- Default and explicit retrieval limits are covered by Task 1 and Task 2.
- The application-owned similarity threshold and its SQL placement are covered
  by Task 1.
- Complete selected-slug context, missing-slug 404, and duplicate prevention
  are covered by Task 1 and Task 2.
- Card projection, no-match context, and absence of IDs/embeddings are covered
  by Task 1 and Task 2.
- Request history ordering and no server-side persistence are covered by Task 2.
- Embedding, database, model, malformed-response, and truncation failures are
  covered by existing query tests plus the endpoint failure tests in Task 2.
- Query-layer client creation and cleanup are covered by the endpoint tests;
  the API lifespan only owns the database pool.
- The React chat panel, authentication, streaming, function calling, intent
  routing, creator support, and persistent history are deliberately outside
  this plan.
