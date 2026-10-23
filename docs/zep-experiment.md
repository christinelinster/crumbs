# Native Zep recipe and user context

Crumbs submits the same raw recipe Markdown used by Graphiti. Zep controls
extraction and native context assembly. Graph backends return chat answers,
without recipe cards, recipe JSON conversion, or Postgres detail lookups.

## Fresh comparison data

Create fresh recipe and user graphs in Zep and put their UUIDs in the ignored
`.env` as `ZEP_GRAPH_UUID` and `ZEP_USER_UUID`. Also set `ZEP_API_KEY`.
Start the user graph empty. The app does not create, clear, or migrate graphs
on startup. Existing JSON episodes are not converted automatically.

For Graphiti, choose fresh `RECIPE_GROUP_ID` and `USER_GROUP_ID` values in
`src/app/settings.py`. Use exactly the same recipe files for both backends.
See [the comparison guide](native-graph-comparison.md) for both paths.

## Submit one recipe

Run `poetry run python`, then:

```python
from app import settings
from app.paths import RECIPES_DIR
from app.zep.client import get_zep
from app.zep.ingest import ingest_recipe

client = get_zep()
submission = ingest_recipe(
    client, settings.ZEP_GRAPH_UUID, RECIPES_DIR / 'creamy-tomato-pasta.md',
)
print(submission)
```

This calls `graph.episode.add` with `type='text'`, the exact UTF-8 file
content, a filename-based `document_id`, and a source description. It does not
set an ontology or custom recipe extraction instructions. Repeated submissions
create episodes; `document_id` groups them and does not make the write an upsert.

The local submission report is in `.zep/ingestion/`. It records the source and
native submission response, including the asynchronous task. Submission is not
proof that extraction has finished. Inspect `client.task.get(submission.task.uuid_)`
later; no automatic polling runs. For large backfills, use Zep's documented
Batch API or `zep-ingest`, rather than an application loop.

## Inspect stored data and summaries

After processing, explicitly inspect either graph:

```python
from app.zep.inspect import inspect_graph

recipes = inspect_graph(client, settings.ZEP_GRAPH_UUID)
user = inspect_graph(client, settings.ZEP_USER_UUID, user_graph=True)
```

Each call writes a new Markdown report in `.zep/ingestion/` containing entities
and their summaries, facts, raw episodes with processing status, and thread
summaries. User inspection also reads the central user's summary. The SDK
pagers are iterated so these are complete graph listings, not just the first
page. Use this for small comparison graphs; it reads the whole selected graph.
These reports do not generate summaries or pass them to the answer model.

For a particular episode, optionally include existing diagnostics:

```python
inspect_graph(
    client, settings.ZEP_GRAPH_UUID, episode_uuid='EPISODE_UUID', debug=True,
)
```

This reads workflow logs and ingestion traces if available. It never enables
debug mode. Enable [Zep Debug Mode](https://help.getzep.com/v4/debug-mode)
before ingesting if those diagnostics are needed. Detailed traces require an
eligible plan; a permission or availability error is recorded separately from
stored graph data. This integration does not expose or infer Zep's hidden
model settings or internal implementation.

## Native retrieval and chat traces

```python
from app.zep.retrieval import search_recipes
result = search_recipes('Quick warm chicken lunches')
print(result['recipe_context'])
print(result['user_context'])
print(result['sources'])
```

Every graph search queries the configured recipe and user graphs separately,
independently of conversation writes. Both receive the same model-selected
search query. `graph.get_context` uses `max_characters=5000`,
`include_results=True`, and active-fact filters (`invalid_at` and `expired_at`
are null). Native context and selected results are preserved. Model, ranking,
and context-selection decisions internal to Zep remain managed by Zep.

Crumbs follows selected recipe-source episode UUIDs from edges, nodes,
observations, and thread summaries, fetching each source once. Original Markdown
supplements the native recipe context. There is no JSON parsing, revision
lookup, or application-level dietary filtering. User source episodes are not
fetched as recipe sources. The answer model checks explicit exclusions using
available sources; missing facts do not establish ingredient absence.

When the Crumbs UI actually calls Zep retrieval, it writes `.zep/requests/*.md`:

1. Original question and actual search requests, including graph scope and filters.
2. Native contexts and selected results, with separate recipe and user sections.
3. Supplemental source fetches and the exact tool result sent to the model.
4. Router request/output, then final model instructions, history, tool outputs,
   answer, and application response. Direct answers identify the router as the
   final model call.

Text uses readable line breaks, with exact payloads in collapsible sections.
Partial failures retain completed stages. Disk-write failures are logged without
breaking chat or ingestion. Files contain full source and conversation content,
are ignored by Git, and remain until deleted. Graphiti calls use `.graphiti/`;
vector-only requests create neither graph trace.

## Conversation saving

Selecting **Zep graph** in the UI automatically saves new exchanges to Zep.
The backend creates or validates a thread for the configured user, answers the
question, and saves only the current user/assistant pair. Assistant messages
remain in history but are excluded from preference extraction. Graphiti selection
saves only to Graphiti; Vector RAG saves to neither graph. Earlier conversation
history is not uploaded as part of the current exchange.

Writes and extraction are asynchronous. A saved status confirms the write, not
immediate searchability. Save failure preserves the answer and reports an error.
Thread validation and writes live in `app.zep.memory`; the chat API coordinates
the request. Vector mode retains its existing optional preloaded Zep memory.
