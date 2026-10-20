# Simple Zep experiment

Three small modules, plus the existing settings file:

```text
src/app/zep/
    client.py       # get_zep()
    ingest.py       # recipe episodes and current-turn message writes
    retrieval.py    # graph searches and original source recipe JSON
```

No worker, CLI framework, or database migration. Bitesize uses the same answer
pipeline with a small Vector/Zep discovery branch and optional shared test memory.

## Start

From the project root:

```bash
poetry install
poetry run python
```

Keep `ZEP_API_KEY` and `ZEP_GRAPH_UUID` in the ignored project `.env` file.
For shared memory, also set `ZEP_USER_UUID`. Your existing graph and configured
test user can be reused. In the Python console:

```python
from app import settings
from app.zep.client import get_zep

client = get_zep()
graph_uuid = settings.ZEP_GRAPH_UUID
```

## Create graph

Only if you want a new graph:

```python
graph = client.graph.create(name="Crumbs experiment")
print(graph)
graph_uuid = graph.uuid_
```

Copy its UUID into `.env` for your next session. Recipe-only search does not need
a user or thread. Shared memory uses the separate configured test user.

## Add recipe

```python
from app.paths import RECIPES_DIR
from app.ingestion.load_embeddings import parse_recipe_file
from app.zep.ingest import ingest_recipe

recipe = parse_recipe_file(RECIPES_DIR / "creamy-tomato-pasta.md")
result = ingest_recipe(client, graph_uuid, recipe)
print(result)
```

The slug is passed as `document_id` so related episodes share a document. This
is grouping, not deduplication: repeating the call creates another episode.
Submission is asynchronous and does not prove extraction finished or facts
changed. To explore changes, explicitly submit an edited recipe and inspect
Zep's resulting facts and validity dates.

For an initial bulk corpus backfill, use Zep's recommended
[zep-ingest](https://help.getzep.com/zep-ingest) rather than building a custom
bulk importer here. It is a separate optional package, not installed or run by
this experiment. Individual submissions use the SDK directly. Nothing ingests
the whole corpus automatically.

## Inspect episode and graph

```python
print(client.graph.episode.get(graph_uuid, result.episode.uuid_))
print(client.graph.get(graph_uuid))
```

Inspect the episode's `processed` field later. Open Zep's managed app and select
the same project/graph UUID to see nodes, relationships, and source episodes.
`graph.get` returns metadata, not a complete graph visualization.

## Search graph

```python
from app.zep.retrieval import search_recipes

query = "Which recipes use tomatoes?"
edges = search_recipes(client, graph_uuid, query)
print(edges.items)

# Try the other SDK primitives directly, independently:
print(client.graph.search_nodes(graph_uuid, query=query).items)
print(client.graph.search_episodes(graph_uuid, query=query).items)
print(client.graph.search_observations(graph_uuid, query=query).items)
```

These are separate retrieval scopes. No common result abstraction or ranking
policy is imposed. `.items` reads the first returned page; iterating the SDK
pager may make additional requests. Inspect edge facts, timestamps, and source
episode IDs directly.

## Use Zep in Bitesize

Start the API and UI in separate terminals from the project root:

```bash
poetry run uvicorn app.api:app --port 3001
```

```bash
npm --prefix clients/bitesize install
npm --prefix clients/bitesize run dev
```

Open the URL printed by Vite, open Ask Crumbs, and leave **Retrieval** set to
**Zep graph**, the default. Recipe discovery now calls Zep's edge search and
passes the first ten returned edge facts to the answer model alongside complete
recipes parsed from their original Zep source episodes. The answer model uses
the complete ingredient and instruction content to assess preferences. There is
no application-side ingredient exclusion matcher, exclusion tool argument, or
custom ingredient reranking. The same episode records supply recipe cards;
Zep discovery does not read Postgres. Duplicate source episode IDs are fetched
once and recipe slugs are deduplicated in source order. Invalid JSON, non-recipe
content, and mismatched source/body slugs are skipped without a Postgres fallback.
When writing the answer, the model also returns the slugs it actually offers.
Bitesize shows only those cards, in answer order. There is no fixed card count:
an answer offering one recipe gets one card; six offered recipes get six cards.
No slugs are guessed from fact text. Exact recipe
detail tools and opening a recipe card still use the canonical Postgres recipe
store. General questions may be answered
without a recipe retrieval tool.

Managed Zep provides semantic and BM25 search with default RRF ranking, plus
temporal extraction/invalidation during ingestion. These do not implement
ingredient exclusions from natural-language search text. Current-fact filters
are supplied explicitly for preference retrieval.

Choose **Vector RAG** to compare with the original discovery path. Changing the
selector starts a fresh chat so earlier answers do not affect the comparison.
Both modes use the same answer model. Zep errors are shown as errors and never
silently switch to vectors. The graph must already contain processed recipes;
chat does not ingest recipes. Conversation persistence is controlled separately
by the shared-memory checkbox.

The request sends `retrieval_backend: "zep"` or `"vector"` to `/api/chat`.
Requests that omit it retain the original vector default for API compatibility.
Bitesize explicitly sends its selected value, defaulting to Zep.

The answer text and selected recipe IDs come from the same
[structured answer response](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses),
not a second model call or a scan of prose for recipe names. Unknown and repeated
IDs cannot add extra cards. This applies to both retrieval backends. Previously
saved browser messages retain their old cards; use New chat to test new replies.

## Shared preferences and conversation history

In Zep mode, enable **Use shared test memory**. Everyone shares this test user's
preferences. The checkbox defaults off; the browser remembers your choice.
With memory off, recipe retrieval and local follow-ups work without personal
memory reads/writes. Only enabled turns are submitted to Zep.

The backend creates a thread for the first enabled turn, retrieves remembered
preference facts for the answer, then saves that turn's user and assistant
messages. Preference search applies Zep's native date filters with
`invalid_at is_null` AND `expired_at is_null`. This excludes facts Zep has
already invalidated or superseded; it does not resolve contradictions still
marked active in the graph. Assistant messages are stored as history but excluded
from graph extraction. The UI says **Conversation saved to Zep** when that write succeeds;
it does not claim extraction has finished or that the graph changed. A save
error preserves the answer and shows a warning. There is no automatic retry.

Try this after restarting the backend so it reads `ZEP_USER_UUID`:

1. Select Zep graph and enable shared test memory.
2. Say “I prefer mild food and avoid shrimp.” Wait for the answer/save status.
3. Reload. The transcript, cards, toggle, and thread UUID restore from one browser
   local-storage record. The next turn uses the same Zep thread.
4. Click New chat. The transcript and thread pointer clear. The first enabled
   message creates a new Zep thread for the same test user.
5. Ask “What food preferences do you remember about me?” or request a recommendation.
6. Later say “I now enjoy spicy food” and inspect the preference change in Zep.

Graph extraction/indexing is asynchronous, so a preference may not be searchable
immediately after its conversation is saved. Inspect processing in Zep's managed
app before judging cross-chat memory. Saving a question need not add a new fact.

Browser recovery is per browser, not cross-device synchronization. Zep keeps the
submitted thread history remotely; the frontend restores its local transcript
rather than downloading it from Zep. Disabled turns remain local. Toggling memory
starts a fresh remote thread segment on the next enabled turn and never uploads
prior disabled messages. New chat does not delete old Zep threads or preferences.
An in-flight request interrupted by a reload is not automatically recovered.

If a test user has not been created, create it once from the Python console and
put the returned UUID in `.env`:

```python
user = client.user.create(user_id="crumbs-shared-test", first_name="Shared test user")
print(user.uuid_)
```

Do not recreate the existing configured user. A user graph is separate from the
recipe graph and contains preferences across that user's threads. Both recipe
and preference facts are supplied to the model; this does not enforce dietary
constraints as database filters.

## Compare both answer paths from Python

With the usual PostgreSQL/OpenAI configuration and a loaded recipe store:

```python
from pprint import pprint
from app.db.connection import pool
from app.rag.query import process_query_result

with pool:
    for backend in ["vector", "zep"]:
        result = process_query_result(query, [], retrieval_backend=backend)
        print(backend)
        pprint(result)
```

Both branches return an answer and retrieved context. Vector results can include
recipe cards; Zep results include raw graph facts and source recipe cards.
Different corpus sizes and model variability mean
this remains exploratory rather than a controlled ranking benchmark. The
existing graph contains a starter subset of the full vector corpus.

Graphiti/Neo4j remain the later integration. No inactive Graphiti option is
shown in the selector.

Existing graph data and credentials are preserved. Earlier experiment tables
and local setup files may still exist; these three modules do not use or delete
them. `ZEP_EXPERIMENT`, `ZEP_MEMORY_CREDIT_CAP`, and `RETRIEVAL_BACKEND` remain
unused; the user UUID is now used only when shared memory is enabled.

## Verify locally

```bash
poetry run python -m unittest discover -s tests -v
```

Tests mock Zep and cover backend selection, graph evidence/cards, preferences,
thread validation, save failures, and browser session restoration. Execute the console operations deliberately when you want to
make live calls or submit paid ingestion work.
