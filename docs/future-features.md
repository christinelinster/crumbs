# Future features and architecture implications

This document tracks both implemented capabilities and deferred directions.
Crumbs imports Markdown recipes and stores embeddings, exposes recipe and chat
APIs, and includes the Bitesize browsing and chat client. Checklists below mark
completed work separately from capabilities that still need implementation.

## Recipe cards and recommendation chatbot

- [x] Browse recipe summaries and full details in Bitesize through the Crumbs
  recipe API.
- [x] Ask Crumbs for grounded recommendations in Bitesize and receive clickable
  recipe cards built from application retrieval results.
- [x] Use model-directed read-only tools for recipe discovery, exact recipe
  lookup, and similar-recipe search.
- [ ] Combine semantic similarity with lexical and ingredient-aware retrieval
  and ranking.

Bitesize reads structured recipes from the Crumbs API and currently provides a
floating chat panel. Other clients can choose a different presentation without
changing the recipe storage model.

Initial chat scope: recommend existing recipes and explain why they match.
Examples include "What can I make with chicken, cabbage, and gochujang?" and
"I want something soupy and warm with chicken."

The `get_recipes` tool defaults to three results. Its tool schema allows the
model to pass an explicit count from 1 to 10. Results use embedding similarity;
scores greater than `0.3` are classified as strong. When no strong result
exists, Crumbs can offer the closest candidates as imperfect matches. If an
explicit count exceeds the number of strong matches, weaker candidates can fill
the requested count and must be described as imperfect.

Current retrieval does not enforce ingredient presence, exclusions, time, or
nutrition constraints. Similarity can surface related recipes, but it does not
guarantee that a recipe contains a named ingredient or meets a numeric limit.
Exact ingredient matching and pantry-aware recommendations remain future work.

For general discovery, the current search embeds the request. For similar-recipe
search, it uses the selected recipe's stored embedding. Both retrieve one
top-limit candidate set ordered by vector similarity. The application
classifies candidates by a similarity threshold and builds cards from the
recipes it presents. It does not combine lexical and ingredient matches,
apply extra ranking weights, or run a second search to fill results. Add
normalized ingredient names and aliases before relying on precise ingredient
matching; numeric filters should query recipe fields directly.

### Model-directed recipe retrieval

- [x] Let the model choose between exact recipe lookup and recipe search, while
  the application executes read-only tools and builds recipe cards.
- [x] Allow the model to express a requested recipe count through the search
  tool, with a default of three and a schema limit of ten.

The implemented tools are `get_recipes` and `get_recipe_detail`. For discovery,
the application embeds the tool's search input and returns candidate metadata
to the answer model. For an exact recipe request, it loads the complete stored
recipe by slug. The application constructs cards from search results; the
model writes the explanation. Similarity search does not enforce ingredient,
nutrition, or time constraints.

Review query examples for ambiguous count requests and cases where weak matches
fill a requested count. The model supplies tool arguments, and the application
does not perform a separate argument-validation step before dispatch.

## Cooking follow-ups and multiple chunks

- [x] Answer questions about a selected recipe by loading its complete stored
  content through exact recipe lookup, without embedding the follow-up question.
- [ ] Add multiple recipe-search chunks for cross-recipe technique questions.

Selected-recipe follow-ups are implemented. The `get_recipe_detail` tool loads
the recipe by persisted slug and sends its complete stored content to the answer
model; it does not require a question embedding or similarity search.

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

- [x] Import a single recipe from a supplied URL when the page provides Recipe
  JSON-LD, writing a reviewable Markdown file.
- [ ] Discover recipe URLs across a creator's site and manage scheduled,
  retryable import and review jobs.
- [ ] Add workspaces, creator ownership, authentication, and tenant-scoped
  reads, writes, imports, and retrieval.
- [ ] Support multiple recipes on one page with stable per-page recipe identity.

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

- [ ] Add an admin form for creating and editing recipes through the existing
  normalization, persistence, and embedding workflow.
- [ ] Make Postgres the source of truth for edited recipes and add any needed
  revision, import-provenance, draft, and background-job policies.

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

## Future model interfaces and orchestration

The recipe API, Bitesize chat, model-directed routing, and two read-only recipe
tools are implemented. The current chat flow is:

```text
question and history -> direct answer or recipe tool -> app executes tool
    -> grounded answer and, for search results, app-built recipe cards
```

The remaining extensions below are optional additions for constrained searches,
more predictable model output, multi-step workflows, or interoperability.

### Structured Outputs

- [ ] Constrain model-generated answer fields to a JSON schema when the chat
  contract needs structured guidance beyond the existing `answer` and cards.

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

- [x] Support model-selected calls to `get_recipes` and `get_recipe_detail`;
  the application executes those read-only operations and owns card data.
- [ ] Add tools for enforcing time, nutrition, or ingredient constraints using
  structured recipe fields.

**Purpose in Crumbs:** Tool calling lets the model request a named application
operation. Crumbs decides whether to execute it, runs the operation, and sends
the result back to the model for the final response. The current chat exposes
only the two read-only recipe operations checked above.

Potential additional tools include:

- `filter_recipes_by_nutrition(max_calories, max_time_minutes)`
- ingredient- and time-constrained recipe search;
- a reviewable `draft_recipe` operation for future authoring workflows.

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

The meal-planning example requires a separate plan feature, verified nutrition,
structured quantities, and backend calculations. Tool calling is already used
for recipe retrieval; more complex workflows need their own design. See the [OpenAI function calling
guide](https://developers.openai.com/api/docs/guides/function-calling).

### Model Context Protocol (MCP)

- [ ] Provide an MCP server if external AI hosts need Crumbs recipe capabilities.

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

- [x] Route discovery, selected-recipe follow-ups, and related-recipe searches.
- [x] Respond directly to clearly unrelated questions and standalone cooking
  how-to questions without recipe retrieval.
- [ ] Add workflows for constrained search, meal planning, or recipe creation.

**Purpose in Crumbs:** Routing classifies a request into an application
workflow before generating the final answer. The implemented router can answer
directly or select the recipe context and retrieval tool instead of sending
every question through the same recommendation path.

The initial routing slice is implemented and specified in
[005: Question-intent routing](superpowers/specs/005-question-intent-routing.md).
It covers three recipe workflows:

- general discovery;
- follow-up about the currently selected recipe; and
- related-recipe comparison or recommendation.

Longer-term intent categories could include:

- constrained search such as time, calories, or pantry ingredients;
- meal planning; and
- recipe creation or editing.

An active `recipe_slug` provides recipe-page context to the router for
ambiguous follow-ups. The model chooses a workflow, while the application
restricts execution to its approved tools. Future tools must not bypass
permission checks or let the model decide database writes.

Example queries routing could distinguish:

- "What can I make with mushrooms?" -> discovery search.
- "How much sake goes into the sukiyaki sauce?" -> selected-recipe follow-up.
- "What recipes are similar to this one?" -> related-recipe search.
- "Find a dinner under 500 calories that takes 25 minutes." -> constrained search.
- "Plan five dinners using my pantry and a 1,500 calorie daily budget." -> meal planning.
- "Turn this handwritten recipe into a Crumbs draft." -> recipe-creation workflow.

### Meal planning and grocery lists

- [ ] Build a calendar plan for one or more weeks, with breakfast, lunch, and
  dinner slots and Crumbs recommendations that can be added to a chosen slot.
- [ ] Let users customize assigned meals and servings, and show daily calories
  and macros where recipe data supports complete totals.
- [ ] Generate a grocery list for a selected week or date range, merge
  compatible ingredients, and let users mark pantry and purchased items.
- [ ] Investigate optional commerce integration with an order preview and an
  explicit user approval step before purchase.

Let users build a plan for one or more weeks, adding weeks as needed for a
month-length plan. Show the plan as a calendar with breakfast, lunch, and dinner
slots for each day. Users can ask Crumbs for recipe recommendations and add a
recipe to a specific day and meal slot, then customize the plan by swapping,
moving, or removing meals and adjusting servings.

Show daily calorie and macro totals calculated from the planned recipes and
servings when the recipe data contains the required nutrition values. Make
missing nutrition data visible instead of presenting an incomplete total as
complete.

Generate a combined grocery list for any selected week or range of weeks. Merge
duplicate ingredients and scale quantities to planned servings when the source
data provides compatible names, units, and amounts. Keep quantities separate
or identify them as unavailable when they cannot be safely combined; do not
invent amounts. Let users mark ingredients they already have so they are
excluded from the items to buy, and check off items as they shop. Pantry contents
come from the user's selections, not from model assumptions.

Consider retailer or commerce integration, potentially through Shopify's
Universal Commerce Protocol (UCP), as a separate later phase. It should prepare
the remaining grocery list for user review and require explicit approval before
placing an order. Users should also be able to use the grocery list without a
commerce integration.

### Recommended adoption order

1. Use reviewed query examples as a baseline before changing retrieval or
   prompting, so regressions can be measured.
2. Improve retrieval with lexical and ingredient-aware signals, then compare
   those results with the current embedding-only search.
3. Add constrained search tools when ingredient names, quantities, and
   nutrition data support reliable filtering.
4. Build meal planning and grocery lists from selected recipes, with nutrition
   totals and shopping quantities grounded in available recipe data.
5. Add Structured Outputs when the chat API needs more fields than a plain
   answer, while keeping recipe cards application-owned.
6. Add MCP only when external AI hosts or multiple applications need a standard
   Crumbs integration surface.
