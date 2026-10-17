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

The setup command connects to the database already named by `PG_DB`; create that
database before running setup. It creates the current recipe table schema in a
fresh database and can be rerun against that schema. It does not upgrade the
legacy child-table schema. Use a fresh database, or recreate a legacy database
if its contents can be discarded. Load the curated corpus afterward to populate
recipes and generate embeddings for the files present.

Set the existing `PG_DB`, `PG_HOST`, `PG_USER`, and `PG_PORT` variables
and initialize the schema:

```bash
poetry run python -m app.db.setup
```

Then set `OPENAI_API_KEY` and run:

```bash
poetry run python -m app.ingestion.load_embeddings
```

`app.settings` is the single source for `EMBEDDING_MODEL` and
`EMBEDDING_DIMENSIONS`. The model defaults to `text-embedding-3-small`, and the
dimension defaults to `1536`; both can be configured through environment
variables. Fresh database setup renders the schema's vector dimension from
`EMBEDDING_DIMENSIONS`.

Changing the embedding model requires regenerating all recipe embeddings. If
the configured dimension changes for an existing database, first run the
explicit migration template near the bottom of `src/app/db/schema.sql`,
replacing its dimension placeholders with the target dimension, then run the
loader above. The migration clears the old vectors; the loader regenerates them
for every Markdown recipe. Setup does not migrate an existing database
automatically. If a new model uses the same dimension, update `EMBEDDING_MODEL`
and rerun the loader.

The loader parses every Markdown recipe, generates one embedding using the
shared `EMBEDDING_MODEL` and validates its length against
`EMBEDDING_DIMENSIONS`. It stores the recipe, ordered ingredient and instruction section
arrays, and embedding in the `recipes` row. It uses only the persisted `slug` to
update an existing recipe while preserving its database ID. A
canonical `source_url`, when present, is stored as optional, unique provenance.
Each run regenerates embeddings, so rerunning the command uses OpenAI API
requests for every valid recipe.

The loader reports inserted, updated, and failed recipes and exits with status
`1` if any recipe fails. A failed embedding is not written to the database.
The loader parses the corpus and checks duplicate slugs and canonical source URLs
before making embedding calls. A parsing or duplicate-key error stops that run
before API requests. An individual API or write failure is reported and
processing continues with the next recipe.

The loader parses raw Markdown fields and group boundaries, normalizes them to
canonical content sections, then builds the embedding text from those sections.
Embedding generation happens before the recipe's write transaction. Metadata,
content section arrays, and the vector are committed together; write failures
roll back that recipe. Each loader run re-embeds every Markdown file present.
Removing a Markdown file does not delete its existing database record. There is
no embedding cache, source refresh job, or automatic synchronization from
database edits back to Markdown.

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
- `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` are optional and default to
  `text-embedding-3-small` and `1536`.
- The existing `PG_DB`, `PG_HOST`, `PG_USER`, and `PG_PORT` variables for the
  Postgres connection pool.
- `OPENAI_CHAT_MODEL` is optional and defaults to `gpt-4o-mini`.
- Set `OPENAI_CHAT_MODEL=gpt-6-luna` to use GPT-6 Luna; restart the backend after
  changing the setting. Chat routing and answer generation use the Responses
  API, which supports function calling for both configured models.

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
