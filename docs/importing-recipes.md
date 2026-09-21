# Importing recipes

See [the documentation index](README.md) for the curated data contract,
schema decisions, and future features.

Add one HTTP(S) recipe URL per line to `data/import/recipe-urls.txt`.
Blank lines and lines beginning with `#` are ignored.

From the project root, run:

```bash
poetry run python -m app.ingestion.import_recipes
```

The importer fetches Recipe JSON-LD, normalizes it, and checks that the title,
ingredients, and instructions contain usable text. It writes one Markdown file
per recipe to `data/recipes/`, using the fields and sections in
`docs/recipe-corpus-template.md`. It creates and persists a stable title-based
slug in the Markdown frontmatter. The URL importer always has a source URL;
personal Markdown recipes should provide their own stable slug and may leave
`source_url` null.

Nutrition and other unavailable metadata remain empty. `source_label` defaults to
the source hostname. Categories and tags are saved as YAML lists.
Before database loading, curate the result to match
[the corpus format](recipe-corpus-format.md), including numeric metadata,
publisher display names, one cuisine, and the approved taxonomy.

Existing source URLs and repeated URLs in the same input batch are skipped after
canonicalization, ignoring URL fragments. Source URLs are stored as optional
provenance and are unique when present, but database lookup and updates still use
the persisted slug. Existing filenames are never overwritten. When a generated
slug is already in use, the importer chooses the next available numeric suffix,
such as `chicken-soup-2` or `chicken-soup-3`, and persists that slug in the new
Markdown file. Existing Markdown files must have a nonempty persisted slug.
Malformed frontmatter stops the import before fetching.

Each URL gets an imported, skipped, or failed message, followed by totals.
Individual failures do not stop subsequent URLs. Exit status is `1` if any import
fails and `0` otherwise. Failed URLs can be retried by running the command again;
successfully imported source URLs will be skipped. Review generated Markdown
before chunking and database insertion.

## Loading recipes into Postgres

The schema now supports optional ingredient and instruction groups. Running the
setup command below both creates the correct tables for a fresh database and adds
the four nullable grouping columns to existing tables using repeatable
`ADD COLUMN IF NOT EXISTS` statements. Existing rows initially remain ungrouped.
Load the updated corpus afterward to persist its headings and regenerate embeddings.
See [the grouping refresh report](recipe-grouping-refresh.md) for the source audit
and preservation checks from the September 2026 refresh.

Set the existing `PG_DB`, `PG_HOST`, `PG_USER`, and `PG_PORT` variables
and initialize the schema:

```bash
poetry run python -m app.db.setup
```

Then set `OPENAI_API_KEY` and run:

```bash
poetry run python -m app.ingestion.load_embeddings
```

The schema defaults to `VECTOR(1536)` because the current embedding model
returns 1,536-dimensional vectors by default. If you change the embedding model
and its output dimension is different, update `EMBEDDING_MODEL`, run the
dimension migration template near the bottom of `src/app/db/schema.sql` after
replacing `3072` with the new dimension, and then run the loader above. The
migration clears only the old vectors; the loader regenerates them for every
Markdown recipe. If the new model uses the same dimension, only changing
`EMBEDDING_MODEL` and rerunning the loader is required.

The loader parses every Markdown recipe, generates one embedding using
`EMBEDDING_MODEL` (which defaults to `text-embedding-3-small` and 1,536
dimensions), and stores the recipe, ordered ingredients, ordered instructions,
and embedding in Postgres. It uses only the persisted `slug` to update an
existing recipe while preserving its database ID. A
canonical `source_url`, when present, is stored as optional, unique provenance.
Each run regenerates embeddings, so rerunning the command uses OpenAI API
requests for every valid recipe. Normalized ingredient names are initially left
empty and can be populated later.

The loader reports inserted, updated, and failed recipes and exits with status
`1` if any recipe fails. A failed embedding is not written to the database.
The loader parses the corpus and checks duplicate slugs and canonical source URLs
before making embedding calls. A parsing or duplicate-key error stops that run
before API requests. An individual API or write failure is reported and
processing continues with the next recipe.

Embedding generation happens before the recipe's write transaction. Metadata,
ingredients, steps, and the vector are committed together; write failures roll
back that recipe. Updates replace the child rows, including any previously
populated normalized ingredient names. Removing a Markdown file does not delete
its existing database record. There is no embedding cache, source refresh job,
or automatic synchronization from database edits back to Markdown.

All three commands use shared paths from `app.paths`, resolved relative to this
checkout rather than the current working directory. Run the Poetry commands from
the project root; from elsewhere, use the project's virtual-environment Python
with the same `-m` module names. No command-line arguments are needed.

Recipe persistence lives in `app.db.recipes`; the ingestion loader calls it after
generating an embedding. The former `scripts/*.py` entry points have been replaced
by these module commands.

## Running the recipe assistant

After initializing Postgres and loading the recipe corpus, set the required
runtime variables:

- `OPENAI_API_KEY` for embeddings and chat responses.
- The existing `PG_DB`, `PG_HOST`, `PG_USER`, and `PG_PORT` variables for the
  Postgres connection pool.
- `OPENAI_CHAT_MODEL` is optional and defaults to `gpt-4o-mini`.

Start the interactive CLI from the project root with:

```bash
poetry run python -m app.main
```

The application embeds each question, retrieves the three closest recipes by
default, and asks the chat model for a grounded answer using the retrieved
ingredients and instructions. Retrieval count is controlled by application
code, not by the model. Conversation history is kept only in memory while the
CLI is running and is discarded when the process exits; it is not stored in
Postgres or a file.
