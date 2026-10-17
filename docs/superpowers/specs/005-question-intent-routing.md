# 005: Model-directed question routing

**Status:** Implemented
**Parent project:** [@SPEC.md](../../../SPEC.md)

## Objective

Route each chat turn before recipe retrieval. A model chooses whether to answer
directly or call one of two recipe tools. The application parses and executes
the selected tool, owns retrieval and recipe-card data, and uses a second model
call to write the grounded answer when a tool returns recipe context.

## Scope

- Use the latest question and ordinary role/content conversation history to
  understand user intent.
- Let the routing model either answer without a recipe tool or call
  `get_recipe_detail` or `get_recipes`.
- Support exact recipe questions, similar-recipe search, general recipe
  discovery, standalone cooking how-to questions, and out-of-scope questions.
- Keep database access, result limits, similarity classification, and cards
  under application control.
- Preserve the existing `POST /api/chat` answer and `recipe_cards` response
  contract while removing its request-level `limit` field. The model tool's
  `limit` is the only recipe-count control.

## Out of Scope

- Filtering or ranking similar recipes by requested nutrition, time, cuisine,
  ingredients, or other constraints. Similarity search remains based on the
  stored recipe embedding.
- Recipe creation or editing, meal planning, arbitrary database operations,
  database writes, or tools beyond the approved recipe lookups.
- A complete title-to-slug catalog or a separate title resolver. The model
  derives a slug from explicit recipe names or conversation history.
- Persistent server-side chat sessions or conversation history.

Because title-derived slugs may not match manually assigned or collision-
suffixed stored slugs, a direct title lookup can report not found even when a
recipe with that title exists. This is an accepted limitation of omitting a
title catalog or resolver; the app does not fall back to similarity search.

## Routing context

The initial Responses call receives the current user message and conversation
history as plain role/content messages, plus the two recipe tools. If the
request includes an active `recipe_slug`, the app adds a developer message
labeled `Discussing` with that slug before the conversation. For ambiguous
follow-ups, the router prioritizes this active recipe over older recipes in
history. A different recipe explicitly named or clearly selected in the latest
message still takes precedence. The active slug alone does not trigger a
database lookup or tool call. The router prompt includes a `<tools>` section
and tells the model when to answer directly and when to select a tool. A
separate answer prompt is used only after recipe tools return context. There is
no JSON routing-context prompt or additional recipe-reference projection. The
client continues to own and send its conversation history; the application
does not persist it.

## Configuration

Keep runtime defaults and model dimensions in one `app.settings` module:

- `DEFAULT_RECIPE_LIMIT = 3` and `MAX_RECIPE_LIMIT = 10`;
- `DEFAULT_SIMILARITY_THRESHOLD = 0.3`;
- `EMBEDDING_MODEL`, defaulting to `text-embedding-3-small` and overridable by
  the existing `EMBEDDING_MODEL` environment variable;
- `EMBEDDING_DIMENSIONS = 1536`, overridable by `EMBEDDING_DIMENSIONS`;
- `OPENAI_CHAT_MODEL`, defaulting to `gpt-4o-mini` and overridable by the
  existing `OPENAI_CHAT_MODEL` environment variable.

Use `client.responses.create` for the initial answer-or-tool choice and for
grounded answer generation after a tool call.
Responses function calling is supported by the default `gpt-4o-mini` model and
by `gpt-6-luna` ([GPT-4o mini API docs](https://developers.openai.com/api/docs/models/gpt-4o-mini),
[GPT-6 Luna API docs](https://developers.openai.com/api/docs/models/gpt-6-luna)).
Keep `OPENAI_CHAT_MODEL` as the environment variable name for configuration
compatibility. Use the Responses function-tool schema and preserve the router's
output items when submitting function-call outputs to the answer request.

Use `DEFAULT_SIMILARITY_THRESHOLD` as the single numeric source for strict
strong-match classification (`score > threshold`) and the repository's
default similarity filter. The chat recipe tool explicitly disables the SQL
filter so it can receive weaker candidates for the agreed fallback behavior.
Validate each generated embedding against `EMBEDDING_DIMENSIONS` before it is
stored or used for a search.

The fresh-database schema setup renders its vector column dimension from
`EMBEDDING_DIMENSIONS`. Changing the dimension of an existing database still
requires an explicit schema migration and a corpus re-embedding; the app must
not perform that destructive migration automatically.

## Model tool contract

The routing model receives only these read-only tools:

### `get_recipe_detail`

Accepts a persisted `slug` and returns one complete recipe. Use it for a
specific recipe named by the user or identified from conversation history.
Exact-recipe requests do not generate embeddings.

If the tool cannot find the slug, the final response says the exact recipe
could not be found. It does not silently substitute a similar recipe. For an
explicit title, the model derives a slug from the title or conversation
history. The application uses that value directly in a parameterized exact
lookup without a separate slug validator.

The detail result supplies full stored recipe content to the answer model and
does not create a recipe card. Cards come from `get_recipes` search results.
When a turn combines detail and search tools, only the search results create
cards.

### `get_recipes`

Accepts:

- `input`: the user's recipe search or similarity request;
- optional `limit`: an explicit requested count, from 1 to 10;
- optional `similar_to_slug`: a specific recipe to use as a similarity anchor.

When the user does not state a count, the model omits `limit` and the
application uses a default of 3. The existing `/api/chat` request-level `limit`
field is removed. The effective limit is capped at 10; fewer recipes may be
returned when fewer candidates exist.

For general recipe discovery, the application embeds `input` and searches
stored recipe embeddings. For a request for recipes related to a specific
recipe, the application uses that recipe's stored embedding as the query vector
and excludes the anchor from results. The model identifies the anchor from the
conversation history. No additional ingredient or nutrition constraints are
enforced in this search.

Both exact detail retrieval and anchor retrieval use the repository's
`get_recipe_by_slug` lookup. Anchor retrieval selects compact metadata and the
stored embedding; detail retrieval selects the complete recipe.

The database query returns up to the effective limit in similarity order with
scores, without filtering candidates at the strong-match boundary. The tool
schema describes the supported input fields and count range. The application
does not run a separate tool-argument validation step before dispatch. The
application classifies a candidate as strong only when its score is greater
than `0.3`:

- If one or more strong results exist, return only strong results unless the
  user explicitly requested a count and there are too few strong results. In
  that case, fill the requested count with the highest-scoring weak candidates.
- If no strong results exist, tell the user no suitable match was found and
  offer the closest available candidates, up to the effective limit, with a
  brief explanation. If no candidates are available, say that no recipes were
  found.
- Identify weak candidates as imperfect or not exact matches. Attach recipe
  cards for every candidate that is presented.
- Do not run a second search to fill a result set. The single top-limit query
  supplies both strong and fallback candidates.

### Direct response without a tool

Clearly unrelated questions and standalone general nutrition advice use no
recipe tool and perform no retrieval or embedding. The router politely says
Crumbs is a recipe assistant and does not have information to answer questions
outside its recipe collection. It does not answer those questions from general
knowledge.

Standalone cooking how-to questions, such as “How do I roast broccoli?”, also
use no retrieval. The model answers the cooking question generally, then
reminds the user that Crumbs is a recipe assistant and can help find a specific
recipe.

## Tool execution and final answer

The model may make multiple tool calls when a user clearly asks for more than
one operation, such as asking for a recipe's nutrition and similar recipes in
the same turn. The application parses the JSON arguments and dispatches the
model-selected tool directly; it does not maintain a separate tool-call
validator. Database queries remain read-only and parameterized.

When tools return results, the application sends them to a second model call
for the final answer. For `get_recipes`, that model receives concise fields
needed to explain the recommendations, such as title, description, category,
tags, nutrition, similarity score, and strong/weak status. It does not receive
full ingredients or instructions for discovery results. For
`get_recipe_detail`, it receives the complete recipe content.

The final model writes recommendation prose and reasoning. The application
builds `recipe_cards` only from `get_recipes` results, preserving stored slugs
and metadata. The model never creates or edits card fields. A direct no-tool
response is returned without a second answer-model call.

## Request and response behavior

`POST /api/chat` keeps `question`, `history`, and optional `recipe_slug` as
request fields. It no longer accepts a request-level `limit`; requested recipe
counts are expressed through the model's `get_recipes` tool call. Assistant
counts are expressed through the model's `get_recipes` tool call. Model input
uses ordinary role/content history without a separate recipe-reference
projection.

The response remains `{answer, recipe_cards}`. The cards are generated by the
application from the recipes selected for presentation. Full recipe content
remains available only through `get_recipe_detail` and the existing recipe
detail endpoint.

## Error behavior

- A model-selected slug is passed to an exact parameterized stored-slug lookup.
  If it does not resolve, the tool reports not found to the model; no similarity
  search is substituted for an exact request.
- Tool JSON is parsed and dispatched directly. There is no separate application
  validator for tool names, argument keys, slugs, or count values.
- Embedding, database, or answer-model failures follow the existing generic
  service-error behavior. Internal prompts, SQL, raw provider details, and
  embeddings are not exposed to users.

## Acceptance Criteria

- Off-topic and standalone general nutrition requests make no recipe tool call,
  database search, or embedding request.
- Standalone cooking how-to questions are answered without recipe retrieval and
  end with an invitation to use Crumbs for a specific recipe.
- Specific recipe lookups use `get_recipe_detail`, skip embeddings, return full
  recipe context, and do not return recipe cards. Missing exact recipes are
  not silently replaced.
- Similar-recipe search uses the anchor's stored embedding, excludes the anchor,
  and does not apply unrequested macro or ingredient filters.
- General recipe discovery embeds the search input and uses an effective
  default count of three, respecting explicit counts and the maximum of ten.
- Runtime recipe limits, similarity threshold, chat model, embedding model,
  and expected embedding dimension are read from the shared `app.settings`
  module rather than duplicated across tools and repository code.
- Generated embeddings whose length does not match `EMBEDDING_DIMENSIONS` are
  rejected before database writes or similarity queries.
- Search result classification uses a strict strong-match boundary of `> 0.3`
  and follows the strong/weak fallback rules above with a single query.
- Conversation text lets the model resolve follow-ups such as “the first
  recipe” without sending card metadata as separate routing context.
- An active `recipe_slug` is provided as priority context for ambiguous
  follow-ups without triggering a lookup by itself; explicit references in the
  latest user message can select another recipe.
- Clear combined requests can execute multiple approved tools in one turn.
- The answer model receives concise discovery results or full detail content as
  appropriate. The app constructs cards from database results.
- The request-level `limit` is removed from `/api/chat`; the response shape is
  unchanged.
- Recipe lookup SQL remains parameterized and read-only.

## Verification Expectations

Add unit and API tests proving that each no-tool and tool route invokes only
the intended model, embedding, and database paths. Cover explicit detail,
selected-recipe follow-up, similar search and anchor exclusion, general search,
follow-ups from conversation text, default/explicit/max counts, strong/weak
result presentation, direct cooking answers, off-topic responses, combined
tool calls, argument pass-through, and response cards. Run focused chat,
retrieval, and API tests plus the complete test suite and `git diff --check`.

## Supersedes

This specification updates the earlier routing direction that used a
rule-based intent router. It also supersedes the `limit` field and fixed
similarity-threshold behavior described in
[@docs/superpowers/specs/004-bitesize-chat-api.md](004-bitesize-chat-api.md)
for `POST /api/chat`. The route-specific `0.3` strong-match classification
replaces the previous query-time cutoff for this chat workflow.

## Related ADRs

- [@docs/decisions/002-in-memory-conversation-history.md](../../decisions/002-in-memory-conversation-history.md)
- [@docs/decisions/003-bitesize-reference-client.md](../../decisions/003-bitesize-reference-client.md)
