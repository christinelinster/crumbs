# Core technical decisions

## Current storage model

The curated Markdown corpus is the current input for database loads. Postgres
stores structured recipes for application reads and one vector per recipe for
future semantic retrieval. Rerunning the loader replaces stored recipe content
from Markdown; database edits are not currently synchronized back to files.

The executable schema is [app/db/schema.sql](../src/app/db/schema.sql).

| Table | Purpose and constraints |
| --- | --- |
| `recipes` | Identity, frontmatter, optional recipe notes, and `embedding VECTOR(1536)` |
| `recipe_ingredients` | `recipe_id`, one-based `position`, `raw_text`, nullable `normalized_name` |
| `recipe_steps` | `recipe_id`, one-based `position`, `instruction` |

Both child tables use `(recipe_id, position)` as their primary key and reference
`recipes(id)` with `ON DELETE CASCADE`. The database indexes non-null normalized
ingredient names. Positions preserve display order; reads must explicitly order
by `position`.

Both child tables also have nullable `group_position` (positive integer) and
`group_name` (text). These are display sections, not step-to-ingredient mappings.
Group names may repeat, so group position identifies each section within a recipe.
No group means both values are null; an unnamed group has a position and null name.
The Markdown contract and query group metadata are documented in
[corpus format](recipe-corpus-format.md).

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
- `embedding`: nullable 1,536-dimensional vector.

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

## Ingredients

Preserve the original ingredient text for display, including amounts, fractions,
preparation, and alternatives. `normalized_name` is an optional interpretation
for ingredient matching, for example:

```text
raw_text: 300 g boneless chicken breasts, sliced
normalized_name: chicken breast
```

Each ingredient row pairs its own raw text with its own name; names are not kept
in a separate parallel array. The current loader sets all normalized names to
`NULL`. Normalization and alias matching are future work. Keep distinctions such
as chicken breast versus chicken stock rather than reducing both to chicken.

## Embedding and chunking

Use one embedding per complete recipe for the MVP. `load_embeddings` builds text
in this order: title, description, cuisine, categories, tags, ingredients,
instructions, and optional notes. IDs, source URLs, and numeric frontmatter are
excluded. Quantity text within ingredient lines is preserved.

The current model is `text-embedding-3-small`, using its default 1,536 dimensions.
The current call omits explicit dimensions and encoding format and consumes the
numeric embedding returned by the Python SDK. The database column fixes the
vector dimension. The function checks that the response contains one embedding;
Postgres enforces the vector's size when it is written.

Do not store embedding text, model metadata, or content hashes in the database
for the MVP. Text is reconstructible from recipe content, the model is a code
constant, and every loader run regenerates embeddings. Recipe and query vectors
must use the same model and dimensions. Changing models requires rebuilding the
stored embeddings even if the new model has the same dimensions.

`recipe_search_documents` was considered and deferred. A separate table becomes
useful when one recipe needs multiple chunks or embedding configurations. Recipe
recommendations should return distinct recipes, not multiple chunks of one dish.

No vector index or retrieval endpoint has been implemented. Start retrieval
evaluation with exact vector search for the small corpus. Fetch only display
fields for recipe cards rather than transferring embeddings with `SELECT *`.

## Modules and paths

| Module | Responsibility |
| --- | --- |
| `app.db.setup` | Execute the schema inside a transaction |
| `app.db.recipes` | Save recipe metadata and ordered child rows |
| `app.embeddings` | Shared OpenAI embedding model constant and one-vector helper |
| `app.ingestion.import_recipes` | Fetch web recipes and write reviewable Markdown |
| `app.ingestion.load_embeddings` | Parse Markdown, generate vectors, coordinate database writes |
| `app.ingestion.utils` | Shared URL normalization, frontmatter parsing, and slug generation |
| `app.query` | Application-owned limit, vector retrieval orchestration, guarded LLM prompt, and in-memory history |
| `app.paths` | Central paths for the checkout, corpus, URL list, template, and schema |

Use `python -m` entry points, not the former `scripts/` commands. Path calculations
are relative to the fixed location of `app.paths`, independent of the invoking
module or working directory. Deployment without this repository layout will
need a configured corpus location or packaged resources.

Web HTML cleaning and curated Markdown validation remain separate because they
have different behavior. Preserve literal Markdown ingredient content during
loading; the web importer strips source HTML.

## Query flow

`app.query.search_similar_recipes(question, limit=3, *, client,
database_pool=pool)` embeds the question with the shared helper and retrieves
the closest complete recipes. The OpenAI `client` is a required injected
dependency. `database_pool` is an optional override used by callers and tests;
the default is the application's shared pool. The `limit` is owned by
application code and defaults to three; the LLM does not choose how many
recipes are retrieved.

`app.query.process_query(question, history, *, client, database_pool=pool,
limit=3)` coordinates retrieval, the guarded system prompt, prior in-memory
messages, and the chat completion. It appends the user and assistant messages
to the caller-owned `history` list only after a successful nonempty answer.
Conversation history is process-local and is not assigned a database ID or
written to Postgres. The history disappears when the application exits.

The chat model is configured by `OPENAI_CHAT_MODEL` and defaults to
`gpt-4o-mini`. The interactive entry point is
`poetry run python -m app.main`.

Setup uses `CREATE ... IF NOT EXISTS` plus an explicit, additive grouping upgrade
with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. This upgrades existing child
tables without replacing their rows. Other schema differences are not automatically
migrated; future schema changes require their own migrations.
See [the operations guide](importing-recipes.md) for loading and transaction behavior.
