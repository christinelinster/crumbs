# Crumbs

Recipe search and chat with a FastAPI backend and the Bitesize React frontend.

## Run locally

### 1. Install dependencies

You need Python 3.13+, Poetry, Node.js 22.12+, and a running PostgreSQL server
with the pgvector extension installed.

From the repository root:

```bash
poetry install
npm ci --prefix clients/bitesize
```

### 2. Configure the environment

Create `.env` in the repository root with your local values:

```dotenv
OPENAI_API_KEY=your_openai_api_key
OPENAI_CHAT_MODEL=gpt-4o-mini
PG_DB=crumbs
PG_HOST=localhost
PG_PORT=5432
PG_USER=your_postgres_user
# If your PostgreSQL server requires a password:
# PGPASSWORD=your_postgres_password
```

To use Zep retrieval, also add:

```dotenv
ZEP_API_KEY=your_zep_api_key
ZEP_GRAPH_UUID=your_recipe_graph_uuid
# Required only when enabling shared test-user memory:
ZEP_USER_UUID=your_zep_user_uuid
```

Zep graph setup and recipe ingestion are described in
[the Zep guide](docs/zep-experiment.md#setup-and-recipe-ingestion).
For local chat without Zep, select **Vector RAG** in the chat panel.

### 3. Set up the recipe database

For a new local database, create it using your PostgreSQL role (matching `.env`):

```bash
createdb -h localhost -p 5432 -U your_postgres_user crumbs
poetry run python -m app.db.setup
poetry run python -m app.ingestion.load_embeddings
```

If the database already exists, skip `createdb`. The loader reads
`data/recipes/`, calls OpenAI to create embeddings, and inserts or updates
recipes. It incurs API usage; rerun it when loading changed recipes. The schema
setup expects a fresh database or the current schema, not a legacy schema.
PostgreSQL is required for recipe browsing and detail pages even with Zep chat.

### 4. Start the API

From the repository root, in one terminal:

```bash
poetry run uvicorn app.api:app --reload --port 3001
```

API documentation: <http://localhost:3001/docs>.

### 5. Start Bitesize

In another terminal, from the repository root:

```bash
npm run dev --prefix clients/bitesize
```

Open the URL printed by Vite, normally <http://localhost:5173>.
The frontend forwards `/api` requests to the backend on port 3001.

### Optional: terminal chat

After setting up the database, you can run the vector-backed CLI:

```bash
poetry run python -m app.main
```

Type `quit` to exit.

## Zep experiment

Bitesize chat supports Zep graph search, source recipe cards, and optional memory
for one shared test user, alongside existing vector RAG. The browser restores the
current conversation after reload. See [setup and examples](docs/zep-experiment.md).

Every handled chat request saves an ordered Markdown capture in `.zep/requests/`.
