# 004: Bitesize chat API

**Status:** Implemented
**Parent project:** [@SPEC.md](../../../SPEC.md)

> **Superseded for chat routing:** [spec 005](005-question-intent-routing.md) is
> the current source for `/api/chat` intent routing, recipe-count ownership, and
> similarity result classification. The historical request and response
> details below remain useful for the endpoint behavior that spec 005 retains.

## Objective

Expose the grounded Crumbs query flow through a shared HTTP endpoint that the
Bitesize reference client can use for conversational recipe discovery and
recipe-specific follow-up questions.

Crumbs owns retrieval, grounding, conversation-history handling, and response
data. Bitesize owns presentation, clickable routes, and the future chat-panel
interface.

## Scope

- `POST /api/chat` with application-controlled retrieval settings.
- Request-scoped in-memory conversation history.
- Grounded answers based on complete recipe context.
- Condensed clickable recipe cards for general similarity-search questions.
- Exact recipe context selected by a persisted `recipe_slug`.
- Explicit validation and service-error behavior.

## Out of Scope

- Persistent conversations or conversation IDs.
- Authentication, creator accounts, or independent blog corpora.
- Streaming responses.
- LLM function calling, MCP, intent routing, or model-generated recipe cards.
- Substitution or nutrition tools beyond the retrieved recipe context.
- The React chat-panel implementation.

## Dependencies

- [@docs/superpowers/specs/001-recipe-grounded-query.md](001-recipe-grounded-query.md)
  - provides the existing grounded query, embedding, prompt, and history
  capability consumed by the API.
- [@docs/superpowers/specs/003-recipe-api-design.md](003-recipe-api-design.md)
  - provides the persisted recipe slug and detail route used by recipe-card
  navigation.

## Required Context

- [@docs/architecture.md#stable-client-contract](../../architecture.md#stable-client-contract)
- [@docs/architecture.md#data-flow](../../architecture.md#data-flow)
- [@docs/technical-decisions.md#query-flow](../../technical-decisions.md#query-flow)
- [@docs/decisions/002-in-memory-conversation-history.md](../../decisions/002-in-memory-conversation-history.md)
- [@docs/decisions/003-bitesize-reference-client.md](../../decisions/003-bitesize-reference-client.md)

## Authoritative Requirement References

- [@docs/product-requirements.md#req-query-001](../../product-requirements.md#req-query-001)
- [@docs/product-requirements.md#req-query-002](../../product-requirements.md#req-query-002)
- [@docs/product-requirements.md#req-query-003](../../product-requirements.md#req-query-003)
- [@docs/product-requirements.md#req-query-004](../../product-requirements.md#req-query-004)
- [@docs/product-requirements.md#req-query-005](../../product-requirements.md#req-query-005)
- [@docs/product-requirements.md#req-query-006](../../product-requirements.md#req-query-006)
- [@docs/product-requirements.md#req-query-007](../../product-requirements.md#req-query-007)
- [@docs/product-requirements.md#req-query-008](../../product-requirements.md#req-query-008)
- [@docs/product-requirements.md#req-query-009](../../product-requirements.md#req-query-009)
- [@docs/product-requirements.md#req-api-001](../../product-requirements.md#req-api-001)
- [@docs/product-requirements.md#req-api-002](../../product-requirements.md#req-api-002)
- [@docs/product-requirements.md#req-api-003](../../product-requirements.md#req-api-003)

## HTTP contract

### Endpoint

```http
POST /api/chat
Content-Type: application/json
```

The endpoint returns a grounded answer and structured recipe references. It
does not return database IDs, embeddings, raw prompts, system instructions, or
conversation history.

### Request

```json
{
  "question": "What can I make with eggs?",
  "history": [
    {"role": "user", "content": "I want a quick breakfast."},
    {"role": "assistant", "content": "Steamed eggs may work."}
  ],
  "limit": 3,
  "recipe_slug": null
}
```

| Field | Type | Required | Behavior |
| --- | --- | --- | --- |
| `question` | string | Yes | The current user question. It must be nonempty text. |
| `history` | array | No | Ordered `{role, content}` messages. Defaults to `[]`. |
| `limit` | integer | No | Positive application-controlled retrieval count. Defaults to `3`. There is no product-level maximum in the MVP. |
| `recipe_slug` | string or `null` | No | The persisted slug of the recipe currently being viewed. |

History roles are limited to `user` and `assistant`. System instructions are
application-controlled and cannot be supplied by the client.

### Response

```json
{
  "answer": "Here are recipes that match your question.",
  "recipe_cards": [
    {
      "slug": "steamed-eggs",
      "title": "Steamed Eggs",
      "category": ["breakfast"],
      "tags": ["eggs"],
      "total_time_minutes": 20,
      "calories": 180,
      "protein": 14,
      "carbs": 4,
      "fat": 10,
      "similarity_score": 0.91
    }
  ]
}
```

The response always contains an `answer` string and a `recipe_cards` array.
The array may be empty.

Each recipe card contains the same summary fields used by the Bitesize
home-page cards: `slug`, `title`, `category`, `tags`,
`total_time_minutes`, `calories`, `protein`, `carbs`, and `fat`. Cards from
similarity retrieval also contain a numeric `similarity_score`. Bitesize may
render that score as small, light-gray supporting text.

The card's `slug` is the navigation key. Bitesize uses it to navigate to its
recipe-detail route, currently `/recipe/{slug}`, and loads complete details
through `GET /api/recipes/{slug}`. A card is not intended to contain the full
ingredients or instructions.

## Retrieval behavior

The request has two mutually exclusive retrieval paths.

### General question

When `recipe_slug` is absent, Crumbs:

1. Generates an embedding for `question`.
2. Compares it with stored recipe embeddings.
3. Applies `app.db.recipes.DEFAULT_SIMILARITY_THRESHOLD`, currently `0.5`.
4. Returns up to `limit` qualifying recipes.
5. Uses the complete retrieved recipes as LLM context.
6. Builds `recipe_cards` from those same scored results.

The LLM does not choose `limit`, run retrieval, or create recipe-card links.
For qualifying recommendation queries, the system prompt asks for a short
summary of each recipe and why it fits. Clearly unrelated questions should not
be forced into recipe recommendations; that behavior is owned by the system
prompt rather than an application-side question classifier.

### Recipe-specific question

When `recipe_slug` is present, Crumbs:

1. Looks up that exact recipe by its persisted slug.
2. Fails with HTTP 404 if the slug does not exist.
3. Uses the complete recipe, including grouped ingredients and instructions, as
   LLM context.
4. Skips question embedding and similarity search.
5. Returns an empty `recipe_cards` array because the user is already viewing
   the selected recipe.

For example, a Bitesize detail page can send:

```json
{
  "question": "Can I prepare the sauce ahead of time?",
  "history": [],
  "recipe_slug": "sukiyaki-japanese-one-pot-meal"
}
```

The slug is application-provided context. The LLM does not infer or choose it.

## Conversation and grounding

The client sends prior user and assistant messages with each request. Crumbs
keeps that history in memory only for the active application process; it is not
stored in Postgres and disappears when the process exits.

Retrieved recipe data is request-scoped prompt context. It is not appended to
conversation history. The system prompt instructs the model to treat recipe
data as the source of truth, write qualifying recommendations as short prose
paragraphs in an ordered list with a reason they fit, preserve complete stored
instructions when explicitly requested, respond appropriately to unrelated
questions, avoid inventing unsupported facts, and acknowledge when recipe
context is insufficient.

The API returns an answer only after a nonempty model response. Failed model,
embedding, database, or retrieval operations must not add a false assistant
message to the caller's history.

## Error responses

| Status | Meaning |
| --- | --- |
| `422` | The request body is invalid, such as an empty question, malformed history, or non-positive `limit`. |
| `404` | The supplied `recipe_slug` does not identify a stored recipe. |
| `502` | The chat model returned an empty, malformed, or truncated response. |
| `503` | Embedding, database, or other chat-service dependency is unavailable. |

Service responses do not expose raw exception text, SQL, prompts, or provider
credentials.

## Acceptance Criteria

- A valid general question returns an answer and cards derived from the same
  similarity retrieval used to construct the LLM context.
- A valid recipe-specific question resolves the slug before embedding or vector
  retrieval and uses the complete selected recipe as context.
- A recipe-specific response contains an empty `recipe_cards` array rather than
  assigning a fabricated similarity score to the selected recipe.
- A missing slug returns HTTP 404 without silently answering from another
  recipe.
- Clearly unrelated questions use the normal retrieval path, while the system
  prompt tells the model to respond briefly without forcing a recommendation.
- General recommendations use the application-owned similarity cutoff of `0.5`.
- Conversation history remains request-scoped and is not persisted.
- Invalid requests and dependency failures return explicit errors without
  leaking internal implementation details.

## Verification Expectations

Use endpoint tests with fake embedding, chat, and database clients. Verify the
request and response shapes, default and overridden retrieval limits, card
projection, selected-slug behavior, error statuses, connection release before
the LLM call, and absence of false history updates after failures. Run the
existing Crumbs test suite alongside the endpoint tests.

## Related ADRs

- [@docs/decisions/002-in-memory-conversation-history.md](../../decisions/002-in-memory-conversation-history.md)
- [@docs/decisions/003-bitesize-reference-client.md](../../decisions/003-bitesize-reference-client.md)

## Documentation Fallback

Read [@SPEC.md](../../../SPEC.md) as the fallback routing source whenever
additional project documentation is required.
