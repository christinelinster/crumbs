# Model-directed question routing Implementation Plan

**Status:** Implemented; the approved validation cleanup passes the full backend suite (95 tests, 1 opt-in PostgreSQL check skipped).

> **For agentic workers:** Use `superpowers:executing-plans` for native execution or `superpowers:subagent-driven-development` if that execution method is selected. Follow the repository rule not to stage or commit changes. Steps use checkbox syntax for tracking.

**Goal:** Route each `/api/chat` turn through model-selected recipe tools, use application-owned retrieval and cards, and preserve direct answers for requests that need no recipe search.

**Architecture:** Add a shared `src/app/settings.py` source for runtime model names, embedding dimensions, recipe limits, and the similarity threshold. Keep only the two tool schemas in `src/app/rag/tools.py`. In `src/app/rag/query.py`, one Responses call receives ordinary role/content conversation history and a router prompt with a `<tools>` section. It either answers directly or returns recipe tool calls. The application parses and dispatches each call directly, then uses one more Responses call with the grounded-answer prompt. The application remains the sole source of recipe cards.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, psycopg, OpenAI Responses API function calling, React, Vite, Node's built-in test runner, and Python `unittest`.

**Spec:** [005-question-intent-routing.md](../specs/005-question-intent-routing.md)

**Current routing note:** Tasks 4, 6, and 7 record the initial implementation.
Their call-validation and JSON history-projection details were superseded by
the implemented simplification at the end of this plan. The router prompt and
its `<tools>` section remain part of the current design.
Recipe-detail tool results return full content without creating cards; cards
come only from `get_recipes` results.
When present, the active `recipe_slug` is passed in a separate `Discussing`
developer message and takes priority for ambiguous follow-ups.

## Global Constraints

- The `/api/chat` request has no `limit` field; the optional `get_recipes.limit` is the only recipe-count control, defaults to 3, and is restricted to 1 through 10.
- `src/app/settings.py` is the single source for `DEFAULT_RECIPE_LIMIT = 3`, `MAX_RECIPE_LIMIT = 10`, `DEFAULT_SIMILARITY_THRESHOLD = 0.3`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, and `OPENAI_CHAT_MODEL`.
- A strong search match has a score strictly greater than `DEFAULT_SIMILARITY_THRESHOLD`; retrieve one top-limit candidate set and do not run a second search to fill results.
- Routing and grounded answer generation use `client.responses.create`; the default `gpt-4o-mini` and configurable `gpt-6-luna` both support Responses function calling.
- General discovery embeds the user's search text; similarity-to-recipe search uses the stored anchor embedding and excludes that anchor.
- Reject generated vectors whose length differs from `EMBEDDING_DIMENSIONS`. Fresh schema setup renders its vector column dimension from the same setting; changing an existing database's dimension still requires an explicit migration and corpus re-embedding.
- Direct out-of-scope, general nutrition, and standalone cooking how-to answers perform no recipe retrieval or embedding.
- Detail lookups use exact stored slugs without embeddings. Missing exact recipes do not trigger alternative search. Detail and similarity-anchor retrieval share `get_recipe_by_slug`; anchor retrieval requests its compact metadata and stored-embedding projection.
- An active `recipe_slug` is sent as a `Discussing` developer message and takes priority over earlier references for ambiguous follow-ups. It does not trigger a lookup by itself; clear references in the latest user message can select another recipe.
- The final model receives concise discovery data and full content only for detail results. The application builds cards only from search results.
- The response keeps the `{answer, recipe_cards}` envelope. Only search results create recipe cards; a detail lookup returns its full recipe content to the answer model without a card.
- Do not add title catalogs, title resolvers, nutrition filters, Phoenix references, database writes, or new database constraints.
- Preserve existing user changes in recipe-section handling and other unrelated workspace changes. Make narrow edits to the affected definitions and tests only.
- Do not stage, commit, or push. Show the completed diff and actual test results for review.

## Review Focus

- An omitted tool `limit` means the default of 3 and never counts as an explicit count for weak-result filling; a supplied `limit: 3` does. Test both cases in Task 7.
- A similarity score of exactly `DEFAULT_SIMILARITY_THRESHOLD` is weak, while a score above it is strong. Test boundary values in Task 7.
- Detail lookups never add cards; combined detail-and-search turns create cards only for search results.
- Tool JSON arguments are parsed and passed directly to the selected operation without a separate validation layer. Test argument pass-through in the simplification follow-up.
- A title-derived slug that does not exactly match a stored slug returns not found without embedding or similar-recipe fallback. Test this in Task 7.

---

## File Map

- Create `src/app/settings.py` as the single source for runtime defaults, environment-backed model names, and embedding dimensions.
- Create `src/app/rag/tools.py` for the two model tool schemas.
- Modify `src/app/rag/embeddings.py` to use shared settings and validate vector dimensions; modify `src/app/db/recipes.py` to import the shared threshold and support a shared slug lookup with an optional compact anchor projection and unfiltered candidates.
- Modify `src/app/rag/query.py` for routing and answer model calls, approved tool execution, response-context projection, result classification, and application-generated cards.
- Modify `src/app/db/schema.sql` and `src/app/db/setup.py` so fresh schema setup renders the embedding vector dimension from shared settings.
- Modify `src/app/api.py` for the revised request-history model, removal of request `limit`, optional card score, and passing validated context to the orchestration layer. Preserve the existing recipe-section detail projection.
- Modify `clients/bitesize/src/utils/chat.js` and `clients/bitesize/src/utils/chat.test.js` to send only ordered `{title, slug}` references from earlier assistant cards.
- Modify `tests/test_query.py` and `tests/test_chat_api.py`, and create `tests/test_routing.py` for tool schema and API behavior.
- Modify `tests/test_module_paths.py`, `tests/test_load_embeddings.py`, `docs/importing-recipes.md`, and `docs/technical-decisions.md` for settings and vector-dimension consistency.
- Add a supersession notice to `docs/superpowers/specs/004-bitesize-chat-api.md` linking this spec. Keep unrelated documentation intact.

### Task 1: Centralize runtime model and retrieval settings

**Files:**

- Create: `src/app/settings.py`
- Modify: `src/app/rag/embeddings.py`
- Modify: `src/app/rag/query.py`
- Modify: `src/app/db/recipes.py`
- Test: `tests/test_module_paths.py`
- Test: `tests/test_load_embeddings.py`
- Test: `tests/test_query.py`
- Test: `tests/test_chat_api.py`

**Interfaces:**

- `app.settings` exports `DEFAULT_RECIPE_LIMIT = 3`, `MAX_RECIPE_LIMIT = 10`, `DEFAULT_SIMILARITY_THRESHOLD = 0.3`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS = 1536`, and `OPENAI_CHAT_MODEL`.
- `EMBEDDING_MODEL` and `OPENAI_CHAT_MODEL` retain their existing environment variable names and defaults. `EMBEDDING_DIMENSIONS` may be overridden by an environment variable of the same name.
- `app.db.recipes.DEFAULT_SIMILARITY_THRESHOLD`, `app.rag.query.DEFAULT_RECIPE_LIMIT`, and `app.rag.embeddings.EMBEDDING_MODEL` may remain imported aliases for compatibility, but values are defined only in `app.settings`.
- `generate_embedding(client, text)` raises `ValueError` if the provider returns a vector whose length differs from `EMBEDDING_DIMENSIONS`.

- [x] **Step 1: Add failing settings and vector-validation tests.** Assert each default, confirm `recipes` and `embeddings` import the shared objects, and verify `generate_embedding` accepts the configured size and rejects a different size.

- [x] **Step 2: Add `src/app/settings.py`.** Load `.env` once, parse the existing model variables and the dimension variable, and define the runtime constants. Reject a non-integer or non-positive embedding dimension at import time with a clear configuration error.

```python
load_dotenv()

def positive_integer_setting(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


DEFAULT_RECIPE_LIMIT = 3
MAX_RECIPE_LIMIT = 10
DEFAULT_SIMILARITY_THRESHOLD = 0.3
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = positive_integer_setting("EMBEDDING_DIMENSIONS", "1536")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
```

- [x] **Step 3: Move existing runtime reads to the shared settings.** Import `EMBEDDING_MODEL` in `rag/embeddings.py`, `OPENAI_CHAT_MODEL` in `rag/query.py`, and `DEFAULT_SIMILARITY_THRESHOLD` in `db/recipes.py`. Remove duplicate definitions while preserving imported aliases needed by existing callers.

- [x] **Step 4: Add vector length validation and update test vectors.** Validate the embedding response before returning it. Replace hard-coded test vector lengths in chat, retrieval, and embedding tests with `EMBEDDING_DIMENSIONS`.

- [x] **Step 5: Run the focused settings and embedding tests.**

Run: `python -m unittest tests.test_module_paths tests.test_load_embeddings tests.test_query -v`

Expected: PASS with the current defaults and clear rejection of a mismatched vector.

Task 1 verification note: the exact module command also reaches the pre-existing `test_parses_all_current_corpus_files` baseline failure (222 parsed versus 234 expected). The affected settings, embedding, query, and chat API coverage passed separately: `python -m unittest tests.test_module_paths tests.test_query tests.test_chat_api tests.test_load_embeddings.LoadEmbeddingsTests.test_generate_embedding_enforces_shared_dimension tests.test_load_embeddings.LoadEmbeddingsTests.test_requires_exactly_one_embedding -v` (32 tests).

### Task 2: Render the database vector dimension from shared settings

**Files:**

- Modify: `src/app/db/schema.sql`
- Modify: `src/app/db/setup.py`
- Modify: `docs/importing-recipes.md`
- Modify: `docs/technical-decisions.md`
- Test: `tests/test_module_paths.py`

**Interfaces:**

- `schema.sql` uses `__EMBEDDING_DIMENSIONS__` for the fresh table column and the documented dimension migration template.
- `app.db.setup` replaces the placeholder with the validated integer from `app.settings.EMBEDDING_DIMENSIONS` before executing the schema.
- Existing databases are never altered by the fresh-database setup command. A dimension change still requires the documented explicit migration and full corpus re-embedding.

- [x] **Step 1: Add a failing setup test.** Assert that setup executes schema SQL containing `f"VECTOR({EMBEDDING_DIMENSIONS})"` and no unresolved dimension placeholder, using the shared setting rather than a duplicated expected literal.

- [x] **Step 2: Template the dimension in `schema.sql` and render it in setup.** Substitute only the known placeholder using the validated integer; keep the vector type constrained in Postgres.

```python
schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
schema_sql = schema_sql.replace(
    "__EMBEDDING_DIMENSIONS__",
    str(EMBEDDING_DIMENSIONS),
)
```

- [x] **Step 3: Update embedding documentation.** Document `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` in `app.settings`, explain that model or dimension changes require re-embedding, and keep the explicit migration step for an existing database when its vector dimension changes.

- [x] **Step 4: Run setup-path tests and inspect the rendered SQL.**

Run: `python -m unittest tests.test_module_paths -v`

Expected: PASS; setup executes valid SQL with the configured dimension and no placeholder text.

### Task 3: Update the chat request and history-reference contract

**Files:**

- Modify: `src/app/api.py`
- Modify: `clients/bitesize/src/utils/chat.js`
- Test: `tests/test_chat_api.py`
- Test: `clients/bitesize/src/utils/chat.test.js`

**Interfaces:**

- `ChatMessage` continues to accept `role` and `content`; assistant history messages may also carry `recipe_references: list[RecipeReference]`.
- `RecipeReference` contains only `title: str` and `slug: str`.
- `ChatRequest` contains `question`, `history`, and optional `recipe_slug`; it has no `limit` field.
- `buildChatRequest(question, messages, recipeSlug)` returns the same fields and maps previous assistant `recipeCards` to ordered title/slug pairs only.

- [x] **Step 1: Write a failing API contract test.** Assert that `/api/chat` rejects a legacy request-level `limit` with HTTP 422 before calling the model or opening a database connection. Assert that assistant history references accept only title and slug, and user history entries cannot supply them.

```python
def test_request_limit_is_rejected_before_chat_work(self):
    connection = FakeConnection(rows=[RECIPE_ROW])
    database_pool = FakePool(connection)
    client = FakeClient()
    with self.http_app(database_pool, client) as http:
        response = http.post("/api/chat", json={
            "question": "egg recipes",
            "limit": 1,
        })
    self.assertEqual(response.status_code, 422)
    self.assertEqual(database_pool.connection_count, 0)
```

- [x] **Step 2: Run the focused API test and confirm it fails.**

Run: `python -m unittest tests.test_chat_api.ChatApiTests.test_request_limit_is_rejected_before_chat_work -v`

Expected: FAIL because the existing request model still accepts `limit`.

- [x] **Step 3: Add the request types and remove request-level count forwarding.** Add a `RecipeReference` Pydantic model, allow references only on assistant messages, remove `limit` from `ChatRequest`, reject extra request fields so a stale `limit` is not silently accepted, and stop passing `request.limit` into `process_query_result`. Keep `RecipeCard.similarity_score` optional so the response can represent recipes without a score.

```python
class RecipeReference(BaseModel):
    title: str = Field(min_length=1)
    slug: str = Field(min_length=1)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    recipe_references: list[RecipeReference] | None = None
```

- [x] **Step 4: Add a failing client reference-projection test.** Check that cards are removed from history and only ordered title/slug pairs are sent for assistant messages; user messages and assistant messages without cards retain their text-only form.

```javascript
test('sends only ordered recipe references from earlier assistant cards', () => {
  const request = buildChatRequest('More like these?', [{
    role: 'assistant',
    content: 'Here are two.',
    recipeCards: [
      { title: 'Egg Pancakes', slug: 'egg-pancakes', calories: 300 },
      { title: 'Turkey Bowl', slug: 'turkey-bowl', similarity_score: 0.4 },
    ],
  }])

  assert.deepEqual(request.history[0].recipe_references, [
    { title: 'Egg Pancakes', slug: 'egg-pancakes' },
    { title: 'Turkey Bowl', slug: 'turkey-bowl' },
  ])
})
```

- [x] **Step 5: Implement the client projection and run the focused tests.** Build `recipe_references` only for assistant messages with cards. Do not send full card objects or add a frontend count control.

Run: `python -m unittest tests.test_chat_api -v`

Run: `npm test --prefix clients/bitesize -- --test-name-pattern="chat request|recipe references"`

Expected: both focused suites PASS; the existing response envelope remains unchanged.

### Task 4: Define and validate the model tool contract

**Files:**

- Create: `src/app/rag/tools.py`
- Create: `tests/test_routing.py`

**Interfaces:**

- `ValidatedToolCall` has `call_id: str`, `name: Literal["get_recipe_detail", "get_recipes"]`, and `arguments: dict[str, object]`.
- `RECIPE_TOOLS` exposes only `get_recipe_detail(slug)` and `get_recipes(input, limit?, similar_to_slug?)`.
- `validate_tool_call(raw_call: object) -> ValidatedToolCall` parses JSON arguments and rejects unknown tools, unknown argument keys, malformed slugs, empty inputs, non-integer limits, and limits outside 1 through 10 before any database work.
- The validator preserves whether `limit` was omitted so the caller can distinguish a default count from an explicit count.

- [x] **Step 1: Add failing tests for valid detail and search calls.** Verify the tool names, required and optional fields, and that an omitted search count remains omitted after validation.

```python
def test_search_call_keeps_omitted_limit_distinct_from_explicit_limit(self):
    call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="get_recipes",
            arguments=json.dumps({"input": "high protein breakfast"}),
        ),
    )
    validated = validate_tool_call(call)
    self.assertNotIn("limit", validated.arguments)
```

- [x] **Step 2: Add failing validation tests.** Cover malformed JSON, an unknown function name, unexpected keys, empty `input`, malformed slugs, `True`, `0`, `11`, and `1.5` as limits. Verify the validator does not access a database.

- [x] **Step 3: Define the two JSON Schema tools and the validated-call type.** Mark all unspecified fields optional and set `additionalProperties` to false. Describe how prior references and the active slug identify a recipe, how `similar_to_slug` requests use the stored embedding, and that the model must omit `limit` unless the user explicitly requested a count.

```python
from app.settings import (
    DEFAULT_RECIPE_LIMIT,
    DEFAULT_SIMILARITY_THRESHOLD,
    MAX_RECIPE_LIMIT,
)


@dataclass(frozen=True)
class ValidatedToolCall:
    call_id: str
    name: Literal["get_recipe_detail", "get_recipes"]
    arguments: dict[str, object]
```

- [x] **Step 4: Implement argument parsing and validation, then run the focused routing tests.** Validate the slug syntax before lookup but do not attempt title-to-slug database resolution.

Run: `python -m unittest tests.test_routing -v`

Expected: PASS for valid calls and all malformed-call cases.

### Task 5: Add repository support for similarity anchors and unfiltered candidates

**Files:**

- Modify: `src/app/db/recipes.py`
- Test: `tests/test_query.py`

**Interfaces:**

- Use `get_recipe_by_slug(conn, slug, *, include_embedding=False) -> dict[str, object] | None` for both detail and anchor retrieval. With `include_embedding=True`, return the stored embedding plus concise metadata needed to explain recommendations; do not select ingredients or instructions.
- Extend `find_similar_recipes(conn, embedding, limit, *, minimum_similarity=DEFAULT_SIMILARITY_THRESHOLD, exclude_slug=None)`.
- Other callers use the same configured threshold as their default SQL filter. The new chat tool passes `minimum_similarity=None`, so its one query returns the top candidates regardless of the shared threshold and passes `exclude_slug` for anchored search.

- [x] **Step 1: Add failing repository tests for the shared slug lookup.** Assert exact slug lookup, returned vector and title metadata in compact mode, missing slug behavior, absence of full recipe content, and parameterized SQL.

- [x] **Step 2: Add failing search tests for the chat query mode.** Assert the query omits a similarity threshold when `minimum_similarity=None`, excludes the specified slug, keeps descending score order, and binds the requested limit. Keep a test for the existing default threshold for other callers.

- [x] **Step 3: Implement the shared slug lookup's compact anchor projection and optional search clauses.** Keep dynamic SQL fragments limited to application-owned branch choices and bind all values as SQL parameters. Preserve the current recipe-section projections and ordering.

```python
def _candidate_filters(
    minimum_similarity: float | None,
    exclude_slug: str | None,
) -> tuple[str, tuple[object, ...]]:
    filters = []
    parameters = []
    if exclude_slug is not None:
        filters.append("scored_recipes.slug <> %s")
        parameters.append(exclude_slug)
    if minimum_similarity is not None:
        filters.append("scored_recipes.similarity_score >= %s")
        parameters.append(minimum_similarity)
    where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
    return where_clause, tuple(parameters)
```

- [x] **Step 4: Run the repository tests.**

Run: `python -m unittest tests.test_query.RecipeDatabaseTests -v`

Expected: PASS for default threshold, unfiltered chat mode, anchor exclusion, and limit validation.

### Task 6: Implement routing and direct no-tool answers

**Files:**

- Modify: `src/app/rag/query.py`
- Test: `tests/test_query.py`
- Test: `tests/test_chat_api.py`

**Interfaces:**

- `process_query_result(question, history, *, database_pool=pool, recipe_slug=None) -> QueryResult` and its `process_query` wrapper have no request-level `limit` argument.
- The first Responses request receives the current question, ordinary role/content history, an optional active `recipe_slug` developer message, the two approved tools, and `tool_choice="auto"`.
- The active recipe message precedes history so the router can prioritize it for ambiguous follow-ups. It does not retrieve that recipe unless the model selects a tool.
- The request model's `recipe_references` metadata is omitted from model input; the model sees only message text plus the optional active recipe message, never full prior cards.
- A response with no tool call returns its nonempty `output_text` directly with `recipe_cards=[]`; it does not call embeddings, connect to the recipe database, or make a second request.
- A response with tools yields validated function-call items for Task 7. Invalid model output raises `QueryGenerationError` and does not add an exchange to history.

- [x] **Step 1: Extend the fake Responses client to capture tool schemas and return ordered response fixtures.** Keep provider-shaped fake objects for `output_text`, function-call output items, and response status so tests exercise the real parsing path.

- [x] **Step 2: Add failing API and query tests for unrelated, general nutrition, and cooking how-to messages.** Each test should assert one routing completion, no embedding call, no database connection, no cards, and the specified direct answer style. Add an empty or truncated routing response case and assert history is unchanged. Add a routing-context assertion showing prior references preserve their order so “the first chicken recipe” can resolve to its stored slug.

```python
def test_direct_how_to_answer_skips_recipe_services(self):
    connection = FakeConnection(rows=[])
    database_pool = FakePool(connection)
    embedding_client = FakeEmbeddingClient([0.1] * EMBEDDING_DIMENSIONS)
    chat = FakeChatClient(answer="Roast broccoli at high heat until browned. Crumbs can help find a specific recipe.")
    client = self.use_client(SimpleNamespace(
        embeddings=embedding_client,
        chat=chat,
    ))
    result = process_query_result(
        "How do I roast broccoli?",
        [],
        database_pool=database_pool,
    )
    self.assertEqual(result.recipe_cards, [])
    self.assertEqual(embedding_client.calls, [])
    self.assertEqual(database_pool.connection_count, 0)
    self.assertEqual(len(chat.calls), 1)
```

- [x] **Step 3: Split routing and answer prompts.** The router prompt chooses only approved tools or answers unrelated/general how-to questions directly. For a cooking how-to, answer generally and then remind the user that Crumbs can help find a specific recipe. If history cannot identify the exact recipe a user describes, tell them the exact recipe could not be found and wait for them to ask for alternatives. Preserve the current detail-formatting, source, safety, and one-step walkthrough rules in an answer prompt for tool-result turns. Include user text and recipe descriptions as untrusted data.

- [x] **Step 4: Implement the first model call and direct-response path.** Pass the active slug in a `Discussing` developer message and ordinary conversation history as role/content input. Do not generate an embedding or access the database before the model selects `get_recipes` or `get_recipe_detail`.

- [x] **Step 5: Run the no-tool tests.**

Run: `python -m unittest tests.test_query.QueryRoutingTests tests.test_chat_api -v`

Expected: PASS; direct no-tool requests make one model call and no retrieval call.

### Task 7: Execute recipe tools and synthesize grounded answers

**Files:**

- Modify: `src/app/rag/query.py`
- Modify: `src/app/db/recipes.py` only if Task 5 tests expose a missing repository projection
- Test: `tests/test_query.py`
- Test: `tests/test_chat_api.py`

**Interfaces:**

- `get_recipe_detail(slug)` performs exact lookup and no embedding. Its result is full recipe content for the answer model. A missing slug becomes a not-found tool result; it does not raise an API 404 or trigger similarity search.
- `get_recipes(input, limit?, similar_to_slug?)` defaults to 3 when `limit` is absent and rejects malformed values. General search embeds `input`; anchored search fetches the stored embedding and excludes its slug.
- The search query retrieves up to the effective limit once. The application marks only scores `> DEFAULT_SIMILARITY_THRESHOLD` strong, applies the approved weak-result rules, and creates cards from the presented validated rows.
- Discovery answer context contains `slug`, `title`, `description`, `category`, `tags`, nutrition, `similarity_score`, and strong/weak status. It excludes ingredients and instructions. Detail answer context contains the full stored recipe.
- Anchored-search answer context also contains only the anchor's title and concise metadata, never its stored embedding or full recipe content, so the final model can explain why results relate to it.
- Detail results do not create cards. `build_recipe_cards` remains a search-result projection and tolerates missing similarity scores.

- [x] **Step 1: Add failing tests for `get_recipe_detail`.** Cover detail without embedding or a card, missing title-derived slug with no embedding and no similar search, and direct parameterized slug lookup.

- [x] **Step 2: Implement exact detail execution.** Use `get_recipe_by_slug`, pass the complete canonical content only to the answer model, and return a structured not-found tool result to that model when absent. Do not add cards for detail results. Instruct the answer model to say the exact recipe was not found and wait for an alternatives request; never trigger a similar-recipe search automatically.

- [x] **Step 3: Add failing tests for general and anchored `get_recipes`.** Verify general search embeds `input`; anchored search fetches the stored embedding and concise anchor title, does not call embedding generation, excludes the anchor, and uses the effective limit. Verify the answer prompt gets concise anchor and candidate fields without ingredient, instruction, or embedding data.

- [x] **Step 4: Implement both search modes and one-query match handling.** Use `minimum_similarity=None` for chat candidates, partition with `score > DEFAULT_SIMILARITY_THRESHOLD`, and never issue another search. If no strong result exists, pass up to the effective limit of closest candidates and mark them weak; if no candidates exist, pass an explicit empty result. If some strong results exist, return them only unless an explicit count needs weak candidates to fill the requested count.

- [x] **Step 5: Add boundary and count tests.** Include exactly `0.3`, just above `0.3`, omitted limit, explicit `limit: 3`, limit `10`, and invalid `True`, `0`, and `11`. Assert omitted and explicit three use different weak-fill behavior where the candidate set has too few strong results.

- [x] **Step 6: Add tests for no strong matches and combined tool calls.** Verify weak candidates are clearly labeled in the answer context, each presented recipe gets a card, empty or short result sets return only available candidates, no tool performs a database write, and one router response with detail plus search calls is executed before one final answer completion.

- [x] **Step 7: Implement final answer synthesis and application-built cards.** Send one final completion with all tool results, disable further tools on this completion, project discovery and detail contexts as specified, and build cards from search results only. Instruct the answer model to explain why each recommendation fits and to identify weak results as imperfect matches. Preserve canonical slugs.

- [x] **Step 8: Run focused backend tests.**

Run: `python -m unittest tests.test_routing tests.test_query tests.test_chat_api -v`

Expected: PASS for tool validation, routing, retrieval, score classification, cards, direct answers, combined calls, and generic API error behavior.

### Task 8: Align the historical chat spec and run full verification

**Files:**

- Modify: `docs/superpowers/specs/004-bitesize-chat-api.md`
- Verify: `docs/superpowers/specs/005-question-intent-routing.md`
- Verify: `docs/superpowers/plans/005-question-intent-routing.md`
- Verify: `src/app/api.py`, `src/app/rag/query.py`, `src/app/db/recipes.py`, and the changed tests

- [x] **Step 1: Add a short supersession note to spec 004.** Link spec 005 as the current source for `/api/chat` routing, count ownership, and similarity result classification. Retain unrelated historical endpoint and response information.

- [x] **Step 2: Check the spec-to-plan coverage.** Confirm every acceptance criterion in spec 005 maps to an implementation step or test in Tasks 1 through 7. Confirm all task checkboxes remain unchecked until implementation begins, then update each immediately as work is completed.

- [x] **Step 3: Run the complete backend suite.**

Run: `python -m unittest discover -s tests -v`

Expected: all routing-related tests pass; the previously recorded corpus-count baseline failure may remain and must be reported without expanding this routing task.

Verification note: the final run executed 101 tests, with 1 skipped and the known baseline corpus-count failure (222 parsed versus 234 expected). The other 99 tests passed.

- [x] **Step 4: Run client tests and build.**

Run: `npm test --prefix clients/bitesize`

Run: `npm run build --prefix clients/bitesize`

Expected: both commands PASS.

- [x] **Step 5: Check changed-file whitespace and inspect the final diff.** Run `git diff --check`, inspect the changed and untracked files, and verify existing user modifications in recipe-section code remain intact. Do not stage or commit. Report commands and results and present the complete diff for approval.

### Responses API compatibility follow-up

Status: Implemented.

- [x] Switch routing and grounded answer generation to `client.responses.create` while keeping `OPENAI_CHAT_MODEL` as the configuration variable.
- [x] Use Responses function-tool schemas and validate typed `function_call` output items before execution.
- [x] Replay all router output items with their matching `function_call_output` items so reasoning and tool state remain connected.
- [x] Verify `gpt-4o-mini` and `gpt-6-luna` against the installed SDK; run focused routing tests, the full backend suite, and `git diff --check`.

The focused routing/API command passed all 42 tests. A local `httpx.MockTransport` SDK round-trip verified request serialization and tool output parsing without making network calls. The full backend run had 101 tests: 99 passed, 1 skipped, and the known corpus-count failure remains (222 parsed versus 234 expected). `git diff --check` passed.

### Simplified tool routing follow-up

Status: Implemented with user approval.

- [x] Use a router prompt with a `<tools>` section and one initial Responses
  call with plain role/content history and the two recipe tools. Return
  `output_text` directly when the model selects no tool.
- [x] Give unrelated questions a polite no-information response because Crumbs
  answers from the recipe collection; do not answer those questions from
  general knowledge. Keep standalone cooking how-to behavior as previously
  agreed.
- [x] Parse the selected function call's JSON arguments and dispatch directly
  to `get_recipe_detail` or `get_recipes`; remove the validator type and
  validation function.
- [x] Remove the separate JSON history projection, JSON helper functions,
  shown-slug filtering, and concise-anchor helper.
- [x] At that point, return a card for every successful detail lookup, even
  when the recipe appeared earlier in the conversation. Superseded by the
  no-detail-cards follow-up below.
- [x] Update tests and the current routing specification for direct dispatch,
  history-only context, and argument pass-through. The repeated-detail-card
  behavior was changed by the follow-up below.
- [x] Run the full backend suite and `git diff --check`; record actual results.

Verification: `python -m unittest tests.test_query tests.test_routing
tests.test_chat_api -v` passed all 35 tests. `python -m compileall -q
src/app/rag src/app/api.py` and `git diff --check` passed. The fresh
`python -m unittest discover -s tests -v` run executed 94 tests: 1 skipped, 5
failed, and 1 errored. The routing tests passed. Failures outside this routing
change were the corpus count (222 versus 234), embedding cardinality/dimension
expectations, and environment-based embedding-dimension settings.

### Shared slug lookup follow-up

Status: Implemented.

- [x] Use `get_recipe_by_slug(conn, slug, *, include_embedding=False)` for
  detail lookups and similarity-anchor retrieval.
- [x] Keep anchor retrieval's metadata and stored-embedding projection compact;
  ordinary slug lookups continue to select complete recipe content.
- [x] Verify the shared lookup modes, missing-anchor behavior, callers, and
  updated specification and plan.

### Detail lookup card follow-up

Status: Implemented with user approval.

- [x] Return full recipe content from `get_recipe_detail` to the answer model
  without creating a recipe card.
- [x] Keep cards from `get_recipes` results, including in turns that also call
  `get_recipe_detail`.
- [x] Update query/API tests and the routing specification; verify focused and
  complete backend suites.

Verification: `python -m unittest tests.test_query tests.test_routing
tests.test_chat_api -v` passed all 35 tests. `python -m compileall -q
src/app/rag src/app/api.py` and `git diff --check` passed. The complete backend
run executed 94 tests with 1 skipped, 5 failures, and 1 error in corpus-count,
embedding-cardinality, and embedding-dimension-settings tests unrelated to
detail cards.

### Active recipe context follow-up

Status: Implemented with user approval.

- [x] Pass an active `recipe_slug` as a `Discussing` developer message before
  prior conversation history.
- [x] Tell the router to prioritize the active recipe for ambiguous follow-ups
  while honoring a different recipe clearly identified in the latest message.
- [x] Keep the active slug from triggering a database lookup by itself; test
  the request boundary with older recipe references also present.

Verification: `python -m unittest tests.test_query tests.test_routing
tests.test_chat_api -v` passed all 35 tests. `python -m compileall -q
src/app/rag src/app/api.py` and `git diff --check` passed. The complete backend
run executed 94 tests with 1 skipped, 5 failures, and 1 error in the previously
noted corpus-count and embedding-settings/cardinality tests.

### Validation cleanup before baseline commit

Status: Implemented with user approval on 2026-10-17.

- [x] Read and validate `EMBEDDING_DIMENSIONS` as a positive integer, retaining
  the default of 1536. Cover both valid overrides and invalid values.
- [x] Reject embedding responses containing zero or multiple vectors before
  indexing into the response.
- [x] Replace the stale fixed corpus count with checks that the corpus is
  nonempty, all recipes parse, and persisted slugs are unique.
- [x] Run `poetry run python -m unittest discover -s tests -v`: 95 tests,
  successful with 1 opt-in PostgreSQL schema check skipped. The historical
  failures recorded above are resolved by this cleanup.
