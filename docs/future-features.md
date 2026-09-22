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

## Deferred LLM tools and intent routing

Function calling and routing based on question intent are future considerations.
The initial Bitesize integration can reuse the existing RAG flow and explicitly
selected recipe context without introducing either capability.

Potential tools include recipe search, fetching a specific recipe, importing a
URL into a draft, and proposing personal recipe edits. Application code would
execute tools and retain control of validation, stable slugs, persistence, and
embedding generation. Intent routing could later distinguish discovery,
recipe follow-ups, and conversational messages.

Pantry-aware meal planning with calorie targets is another possible future use
case, not an implementation commitment. It would need verified nutrition per
serving, structured ingredient quantities, and backend calculations before
reliable budget or pantry constraints could be enforced.
