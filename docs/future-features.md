# Future features and architecture implications

These are agreed directions and deferred options. The current implementation
imports recipes and stores embeddings; it does not yet implement the frontend,
chatbot, search ranking, admin panel, or creator service.

## Recipe cards and recommendation chatbot

The frontend should read structured database recipes. The intended chatbot may
appear in a popup or a separate page; placement has not been selected and does
not change the storage model.

Initial chat scope: recommend existing recipes and explain why they match.
Examples include "What can I make with chicken, cabbage, and gochujang?" and
"I want something soupy and warm with chicken."

Default to three distinct recipes, or the user's requested count. Return fewer
when there are insufficient suitable matches. A maximum count and relevance
thresholds remain to be selected when implementing retrieval.

Ingredient lists default to best overlap, not a requirement to contain every
ingredient or to use only the user's pantry. Clearly explain matched ingredients
and additional ingredients needed. Explicit requests such as "must include all
three" should become stricter constraints.

The intended search combines ingredient matching, lexical search, and semantic
similarity. Embeddings alone do not guarantee ingredient presence, exclusions,
or numeric constraints. Populate normalized ingredient names and define aliases
before relying on precise ingredient matching. Until then, raw-text matches are
approximate. Numeric filters should query database fields directly.

Retrieve a broader candidate set, rank and deduplicate by recipe ID, then load
the selected structured recipes for cards and grounded explanations. Ranking
weights, candidate counts, full-text indexes, and query-intent extraction are
not implemented or fixed. Evaluate these against representative queries before
choosing a final ranking policy.

## Cooking follow-ups and multiple chunks

The next chat capability is answering questions about a selected recipe. Load
its complete instructions by ID first; this does not require more embeddings.

Later, cross-recipe technique questions may benefit from separate overview,
ingredient, instruction-section, or notes embeddings. Introduce a child table
such as `recipe_search_documents` with `recipe_id`, document type, chunk position,
text, and vector when that need is demonstrated. Include recipe and section
context in each chunk and group results back into distinct recipes.

Multiple chunks increase embedding work and retrieval complexity. Do not choose
arbitrary fixed-size chunks or one embedding per instruction by default. Chunk
boundaries and size should follow actual content and retrieval evaluation.

## Creator blog ingestion

Creator-agnostic ingestion and multi-creator support are deferred considerations,
not requirements for the initial Bitesize integration. The options below need
a separate design before implementation.

A creator's collection needs ownership separate from publisher attribution.
`source_label` describes who published the original recipe; it does not identify
the account authorized to manage a stored recipe.

When introducing multiple creators:

1. Add workspaces and a nullable `recipes.workspace_id` foreign key.
2. Assign existing recipes to a Crumbs workspace, then make ownership required.
3. Scope slug and source-URL uniqueness to the workspace.
4. Add authentication, membership, and authorization to reads, writes, imports,
   and retrieval before serving multiple creators.

Ingredient and step ownership can initially be obtained through `recipe_id`.
Workspace IDs alone do not enforce access control. Tenant filters must apply
to vector searches as well as normal recipe reads. Evaluate filtered vector
search performance before introducing approximate indexes or partitioning.

Blog ingestion can add domain URL discovery, import jobs, retries, scheduled
refreshes, and review/publish states around the existing parser and writer.
Retain raw source data and parsing provenance if reprocessing becomes necessary.
Add a publisher/source table when shared metadata or ingestion settings justify
it; keep full recipe-page URLs even if publishers have base URLs.

Supporting multiple recipes on a single page requires changing the parser to
return all Recipe objects and replacing URL-only identity with a stable recipe
identifier within the page, preferably a source-provided JSON-LD identifier when
available. It also requires revisiting the URL uniqueness constraint.

## Admin-created recipes and editing

An admin form should feed the same validation, persistence, and embedding
pipeline. Manual records can have null source URLs and must be edited by database
ID. Generate slugs on creation and preserve them through title changes.

Once admin editing is supported, make Postgres the application source of truth
and treat Markdown as an import/export format. The current loader treats Markdown
as authoritative and would overwrite admin edits on reruns; introduce an explicit
update/review policy before combining those workflows.

Consider recipe revisions to preserve edits, import provenance to distinguish
source updates, and draft/published states. Background embedding jobs would let
the form save without waiting for the embedding API. They need retry status and
a version or hash check so a delayed result cannot replace a newer recipe's vector.
Search must exclude stale embeddings or deliberately serve a prior published
version according to the chosen publishing policy.

No authentication scheme, job queue, revision schema, publisher-specific taxonomy,
or publishing policy has been chosen yet. These require a separate design when
the feature is brought into scope.

## Deferred model interfaces, orchestration, and evaluation

The current Crumbs flow is intentionally application-controlled:

```text
question -> embedding -> vector search -> recipe context -> grounded answer
```

The extensions below can be added when the product needs more predictable API
responses, multi-step workflows, interoperability, or evidence-based quality
measurement. None of them is required for the current Bitesize MVP.

### Structured Outputs

**Purpose in Crumbs:** Structured Outputs would constrain an LLM response to a
known JSON schema. This is useful when the API or Bitesize UI needs predictable
fields instead of parsing free-form prose. A future model response could
include an `answer`, an optional `follow_up_question`, and structured cooking
guidance.

Recipe cards and similarity scores should remain application-owned. Crumbs
already receives those values from the database search, so the model should not
be asked to invent scores, slugs, or links. The API can combine the model's
structured answer with the application-generated cards.

Example queries this could support reliably:

- "What can I make with chicken, cabbage, and gochujang?"
- "Walk me through the sukiyaki instructions one step at a time."
- "Which recipe should I choose if I only have 30 minutes?"

Structured output is a response-formatting capability, not a database or tool
execution capability. See the [OpenAI Structured Outputs
guide](https://developers.openai.com/api/docs/guides/structured-outputs).

### Function calling / tool calling

**Purpose in Crumbs:** Tool calling would allow the model to request a named,
validated application operation. The model emits the tool name and arguments;
Crumbs decides whether to execute it, runs the operation, and sends the result
back to the model for the final response.

Potential read-only tools include:

- `search_recipes(query, limit, similarity_threshold)`
- `get_recipe(slug)`
- `filter_recipes_by_nutrition(max_calories, max_time_minutes)`

Potential write-oriented workflows should begin with a reviewable draft, such as
`draft_recipe`, rather than giving the model direct access to Markdown files or
Postgres. The application must retain control of validation, stable slugs,
source-URL uniqueness, persistence, and embedding regeneration. A separate
user-approved action could save the draft.

Example queries this could support:

- "What can I make with eggs and tofu in under 20 minutes?"
- "Show me the full recipe for steamed eggs."
- "Create a draft recipe from this personal recipe text for me to review."
- "Create a one-week meal plan under 1,500 calories using the ingredients I have."

The last example would require verified nutrition, structured quantities, and
backend calculations. Tool calling is not required for the current single-step
RAG flow. See the [OpenAI function calling
guide](https://developers.openai.com/api/docs/guides/function-calling).

### Model Context Protocol (MCP)

**Purpose in Crumbs:** MCP would provide a standard interoperability boundary
for exposing Crumbs capabilities to MCP-compatible AI hosts and applications.
An MCP server could expose read-only recipe resources, search and recipe-detail
tools, and reusable prompts for recipe conversations. This could let a future
assistant use Crumbs without embedding Crumbs-specific Python calls into that
assistant.

MCP is not a replacement for the Bitesize HTTP API. The HTTP API remains the
client contract for Bitesize, while MCP would be useful if multiple external
AI hosts need the same recipe capabilities.

Possible MCP surfaces include:

- a `recipe://{slug}` resource for a full recipe;
- a `search_recipes` tool with application-controlled limits and thresholds;
- a `recipe_follow_up` prompt that includes the selected recipe context; and
- a review-only `draft_recipe` tool for future creator workflows.

Example queries this could support from an MCP-compatible host:

- "Use Crumbs to find three warm chicken recipes for tonight."
- "Read the sukiyaki recipe and explain what goes into the sauce."
- "Draft this recipe into Crumbs, but do not save it until I approve it."

Start with read-only resources and tools. Authentication, authorization,
corpus scoping, rate limits, and confirmation for write operations would be
required before exposing creator or personal-recipe actions. MCP defines
separate primitives for prompts, resources, and executable tools in its
[server overview](https://modelcontextprotocol.io/specification/draft/server/index).

### Question-intent routing

**Purpose in Crumbs:** Routing would classify a request into an application
workflow before generating the final answer. It could select the right context,
retrieval strategy, tool set, and response format instead of sending every
question through the same recipe-recommendation path.

The first planned routing slice is specified in
[005: Question-intent routing](superpowers/specs/005-question-intent-routing.md).
It focuses on three workflows:

- general discovery;
- follow-up about the currently selected recipe; and
- related-recipe comparison or recommendation.

Longer-term intent categories could include:

- constrained search such as time, calories, or pantry ingredients;
- meal planning; and
- recipe creation or editing.

The current explicit `recipe_slug` context already handles the most important
recipe-follow-up case without an intent router. If routing is added, simple
application rules should handle obvious cases first, with an LLM classifier
introduced only when rules are insufficient. The router should choose a
workflow, not bypass permission checks or let the model decide database writes.

Example queries routing could distinguish:

- "What can I make with mushrooms?" -> discovery search.
- "How much sake goes into the sukiyaki sauce?" -> selected-recipe follow-up.
- "What recipes are similar to this one?" -> related-recipe search.
- "Find a dinner under 500 calories that takes 25 minutes." -> constrained search.
- "Plan five dinners using my pantry and a 1,500 calorie daily budget." -> meal planning.
- "Turn this handwritten recipe into a Crumbs draft." -> recipe-creation workflow.

### Phoenix tracing and evaluations

**Purpose in Crumbs:** Phoenix would provide observability and evaluation for
the RAG pipeline. Traces could capture the query, embedding and retrieval
steps, selected recipe slugs and scores, prompt context, model response,
latency, and token usage. Evaluations could then measure whether changes to the
embedding model, threshold, prompt, routing, or tools actually improve quality.

The first evaluation dataset should contain representative queries and expected
properties, such as relevant recipe slugs, required ingredients or steps, and
whether the answer should acknowledge missing information. Useful metrics
include retrieval relevance, answer faithfulness to recipe context, instruction
completeness, correct recipe-card links, refusal or uncertainty behavior, and
latency. Use deterministic checks where possible and model-based judging only
where a rubric is needed. Traces should redact secrets and any user data that
should not leave the application.

Example queries to evaluate:

- "What can I make with chicken, cabbage, and gochujang?" - are the returned
  recipes relevant and are the matched ingredients explained?
- "What are the sauce ingredients in sukiyaki?" - are all grouped sauce
  ingredients present and not confused with later additions?
- "Show me one recipe under 30 minutes." - is the application limit respected?
- "Can I replace sake with mirin?" - does the answer distinguish corpus facts
  from unsupported cooking advice?
- "Make me a 1,500 calorie weekly plan." - does the system avoid making a
  nutrition claim until verified calculations and data exist?

Phoenix supports traces, datasets, experiments, code-based checks, and
LLM-based evaluators for this type of workflow. See the [Phoenix evaluation
documentation](https://arize.com/docs/phoenix/evaluation/evals) and [Phoenix
tracing documentation](https://arize.com/docs/phoenix/learn/tracing).

### Recommended adoption order

1. Add Phoenix tracing and a small evaluation dataset before changing retrieval
   or prompting, so regressions can be measured.
2. Add Structured Outputs when the chat API needs more fields than a plain
   answer, while keeping recipe cards application-owned.
3. Add read-only tool calling when Crumbs must support multi-step retrieval or
   constrained searches.
4. Add intent routing when different workflows need distinct context or tools.
5. Add MCP only when external AI hosts or multiple applications need a standard
   Crumbs integration surface.
