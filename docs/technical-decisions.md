# Core technical decisions

## Current storage model

The curated Markdown corpus is the current input for database loads. Postgres
stores structured recipes for application reads and one vector per recipe for
future semantic retrieval. Rerunning the loader replaces stored recipe content
from Markdown; database edits are not currently synchronized back to files.

The executable schema is [app/db/schema.sql](../src/app/db/schema.sql); it
creates tables inside the database selected by `PG_DB`, which must already exist.

| Table | Purpose and constraints |
| --- | --- |
| `recipes` | Identity, frontmatter, optional recipe notes, ordered `ingredient_sections` and `instruction_sections` JSONB arrays, and an embedding vector sized by `app.settings.EMBEDDING_DIMENSIONS` |

Each content array stores ordered section objects with `kind`, `name`, and
`items`. Both ungrouped sections and explicitly unnamed groups have a null
`name`, distinguished by `kind`. The loader normalizes parser data to this
representation before embedding and persistence. The database checks that each
top-level JSONB value is an array. Repository reads, RAG context, and the recipe
detail API retain sections; Bitesize flattens section items locally only for
ingredient highlighting. The representation is documented in [corpus format](recipe-corpus-format.md).

The current schema has no ingredient or instruction child tables. This
removes their row-level keys, positions, foreign keys, and the unused partial
index on normalized ingredient names. No current workflow queries individual
items; the curated Markdown remains the reviewed content source. See
[ADR 004](decisions/004-recipe-content-arrays.md) for the decision and tradeoffs.
Setup assumes a fresh database or one already using the current schema; it does
not upgrade a legacy child-table schema.

### Recipe fields

- `id`: generated `BIGINT` primary key; stable identity for relationships.
- `slug`: required unique text for readable recipe URLs and the stable Markdown-to-database key.
- `title`, `description`: required text.
- `category`, `tags`: `TEXT[] NOT NULL DEFAULT '{}'`; several values are allowed.
- `cuisine`: nullable text representing one cuisine in the curated corpus.
- `total_time_minutes`: nullable nonnegative integer.
- `servings`: nullable positive integer; the corpus uses whole serving counts.
- `calories`, `protein`, `carbs`, `fat`: nullable nonnegative `NUMERIC` values, allowing decimals.
- `source_label`, `source_url`: nullable text; `source_url` is unique when present and stores provenance.
- `notes`: optional recipe Notes section, not a nutrition-provenance field.
- `ingredient_sections`, `instruction_sections`: non-null JSONB arrays with
  empty-array defaults; each stores ordered grouped or ungrouped content.
- `embedding`: nullable vector whose dimension is set by `app.settings.EMBEDDING_DIMENSIONS` (default `1536`).

`'{}'` is PostgreSQL's empty array literal; Markdown uses YAML lists such as `[]`.
No taxonomy tables are needed for this MVP: the loader trusts the curated
vocabulary. No workspace, publisher, recipe-version, or search-document tables
are currently included.

Nutrition field names intentionally omit unit suffixes. The corpus convention is
kcal for calories and grams for protein, carbs, and fat. We chose not to store
nutrition basis, origin, or notes as separate fields. Existing source nutrition
has not universally been verified for portion basis, so per-serving comparisons
require a separate audit before being exposed as reliable filters.

### Identity and repeat imports

The current web parser extracts the first Recipe JSON-LD object from each page.
The MVP therefore assumes one recipe per page. A persisted `slug` is the only
recipe identity used for database lookup across Markdown loads, including personal
recipes without a source URL. A canonical `source_url`, when present, is unique
provenance and a duplicate-import guard, but it is not used to locate a database
row. Different recipes must not share the same non-null source URL.

URL normalization removes fragment anchors, lowercases scheme and host, and
preserves paths and query strings. It does not resolve redirects or declare
different URL aliases equivalent.

The URL importer generates a title-based slug once and persists it in Markdown.
When a title-based slug is already used, the importer keeps the existing file and
chooses the next available numeric suffix, such as `chicken-soup-2`. The database
writer uses only the persisted slug for inserts and updates, preserving the
existing ID and slug even when the title changes. Markdown files must contain a
persisted slug; filenames are not used as an identity fallback.

Multiple `NULL` source URLs are allowed by the schema, while non-null source URLs
are unique. Personal and imported recipes both use their persisted slug for
repeat loads. Changing a source URL does not change the recipe's slug identity,
although it cannot be changed to a URL already assigned to another recipe.

Store full page URLs and publisher display labels directly on each recipe.
A separate `sources` table and base-URL/path reconstruction are deferred.

## Ingredient content

Preserve the original ingredient text for display, including amounts, fractions,
preparation, and alternatives. The loader stores it in ordered JSONB sections
on the recipe row; it does not currently store normalized ingredient names.
Ingredient normalization and alias matching are future work. Keep distinctions
such as chicken breast versus chicken stock rather than reducing both to chicken.

## Embedding and chunking

Use one embedding per complete recipe for the MVP. `load_embeddings` builds text
in this order: title, description, cuisine, categories, tags, ingredients,
instructions, and optional notes. IDs, source URLs, and numeric frontmatter are
excluded. Quantity text within ingredient lines is preserved.

`app.settings` is the single source for `EMBEDDING_MODEL` (default
`text-embedding-3-small`) and `EMBEDDING_DIMENSIONS` (default `1536`). The
current call omits explicit dimensions and encoding format and consumes the
numeric embedding returned by the Python SDK. Fresh schema setup renders the
Postgres vector column from the shared dimension. The embedding helper checks
that the response contains one vector with the configured length.

Do not store embedding text, model metadata, or content hashes in the database
for the MVP. Text is reconstructible from recipe content, the model is a code
constant, and every loader run regenerates embeddings. Recipe and query vectors
must use the same model and dimensions. Changing models requires rebuilding the
stored embeddings even if the new model has the same dimensions. Changing the
dimension for an existing database requires the explicit migration template in
`src/app/db/schema.sql` and re-embedding the full corpus; setup never performs
that migration automatically.

`recipe_search_documents` was considered and deferred. A separate table becomes
useful when one recipe needs multiple chunks or embedding configurations. Recipe
recommendations should return distinct recipes, not multiple chunks of one dish.

No vector index or retrieval endpoint has been implemented. Start retrieval
evaluation with exact vector search for the small corpus. Fetch only display
fields for recipe cards rather than transferring embeddings with `SELECT *`.
The home-page summary and chat recipe references share the same condensed fields:
`slug`, `title`, `category`, `tags`, `total_time_minutes`, `calories`,
`protein`, `carbs`, and `fat`. Chat references add `similarity_score` as
retrieval metadata so the client can render it separately.

There is one vector-search projection: `find_similar_recipes` returns the full
recipe context needed for a grounded answer plus its similarity score. The query
layer's `build_recipe_cards` derives condensed clickable cards from those same
results, keeping the answer context and displayed references synchronized. The
similarity score is omitted from the LLM context because it is application
metadata, not recipe content. A recipe detail request still uses the persisted
slug to fetch the full recipe directly.

## Modules and paths

| Module | Responsibility |
| --- | --- |
| `app.settings` | Shared model names, embedding dimensions, recipe limits, and similarity threshold |
| `app.db.setup` | Execute the canonical schema in one transaction |
| `app.db.recipes` | Save recipe metadata and ordered JSONB content sections |
| `app.rag.embeddings` | Generate one vector using the shared model and validate its dimension |
| `app.ingestion.import_recipes` | Fetch web recipes and write reviewable Markdown |
| `app.ingestion.load_embeddings` | Parse Markdown, generate vectors, coordinate database writes |
| `app.ingestion.utils` | Shared URL normalization, frontmatter parsing, and slug generation |
| `app.rag.query` | Application-owned limit, vector retrieval orchestration, guarded LLM prompt, and in-memory history |
| `app.paths` | Central paths for the checkout, corpus, URL list, template, and schema |

Use `python -m` entry points, not the former `scripts/` commands. Path calculations
are relative to the fixed location of `app.paths`, independent of the invoking
module or working directory. Deployment without this repository layout will
need a configured corpus location or packaged resources.

Web HTML cleaning and curated Markdown validation remain separate because they
have different behavior. Preserve literal Markdown ingredient content during
loading; the web importer strips source HTML.

## Query flow

`app.rag.query.process_query_result(question, history, *,
database_pool=pool, recipe_slug=None)` routes each request through a model
completion with the `get_recipe_detail` and `get_recipes` tools. The model sees
text history plus compact ordered references for earlier recipe cards. The
application validates every tool call before accessing the database, then
executes exact detail lookup or one similarity query and builds cards from
stored recipe rows. Direct answers for unrelated questions, general nutrition,
and standalone cooking how-to questions skip recipe retrieval and embeddings.

`get_recipes` owns the optional requested count: it defaults to three and is
capped at ten. General discovery embeds the supplied search text. Similarity to
a specific recipe uses its stored embedding and excludes the anchor. Chat
search retrieves one top-limit candidate set without a SQL similarity cutoff;
the application classifies scores strictly above
`app.settings.DEFAULT_SIMILARITY_THRESHOLD` (currently `0.3`) as strong and
applies the approved weak-result rules to that same set. Exact detail cards
have a null similarity score.

When a tool returns recipe data, one final model completion writes the answer.
Discovery context includes concise metadata and match strength; complete recipe
content is supplied only for `get_recipe_detail`. Database connections are
released before the final completion. `database_pool` is an optional override
used by callers and tests; the default is the application's shared pool.

`app.rag.query.process_query(question, history, *, database_pool=pool,
recipe_slug=None)` is a string wrapper around
`process_query_result(...).answer`. The result-producing function appends the
user and assistant messages to the caller-owned `history` list only after a
successful answer. Conversation history is process-local and is not assigned a
database ID or written to Postgres. The history disappears when the
application exits.

The chat model is configured by `OPENAI_CHAT_MODEL` and defaults to
`gpt-4o-mini`. The interactive entry point is
`poetry run python -m app.main`.
Routing and answer generation use `client.responses.create`; both the default
`gpt-4o-mini` and configurable `gpt-6-luna` support Responses function calling.
The existing `OPENAI_CHAT_MODEL` variable name remains to avoid changing the
application's configuration interface.

The retrieved recipe documents are request-scoped prompt context. They are not
added to the process-local conversation history; history contains only the
user and assistant messages needed for conversational continuity.

`app.db.setup` connects to the already-created database named by `PG_DB` and
executes `schema.sql` in one transaction. The schema creates the `recipes`
table with its JSONB arrays. Setup is intended for a fresh database or one
already using the current schema. Because `CREATE TABLE IF NOT EXISTS` does not
alter an existing legacy table, setup does not upgrade the former child-table
schema; recreate a legacy database when its contents can be discarded.

After setup, `load_embeddings` upserts and re-embeds every Markdown file present
in the corpus. It does not delete database recipes whose Markdown files are
absent. The full storage choice and its tradeoffs are in
[ADR 004](decisions/004-recipe-content-arrays.md).
