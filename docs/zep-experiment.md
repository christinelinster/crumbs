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

Ingestion returns the native submission response without writing trace files.
Submission is not proof that extraction has finished. Inspect `client.task.get(submission.task.uuid_)`
later; no automatic polling runs. For large backfills, use Zep's documented
Batch API or `zep-ingest`, rather than an application loop.

## Inspect stored data and summaries

After processing, explicitly inspect either graph:

```python
from app.zep.inspect import inspect_graph

recipes = inspect_graph(client, settings.ZEP_GRAPH_UUID)
user = inspect_graph(client, settings.ZEP_USER_UUID, user_graph=True)
```

Each call returns entities and their summaries, facts, raw episodes with
processing status, and thread summaries without writing files. User inspection also reads the central user's summary. The SDK
pagers are iterated so these are complete graph listings, not just the first
page. Use this for small comparison graphs; it reads the whole selected graph.
Inspection does not generate summaries or pass them to the answer model.

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

During Zep chat, Crumbs stores the current user message in the active thread and
calls `thread.get_context()`. Zep selects relevant user context from the thread
using its own query window and retrieval behavior; Crumbs sets no turn count.
Crumbs traces the returned block in `.zep/requests/`.

When the router needs recipe information, `get_recipes` separately calls
`graph.get_context` against the shared recipe graph with its concise search
query. It preserves the native context and selected results, then fetches recipe
Markdown for source episodes referenced by the results. User-thread context is
not searched a second time by the recipe tool.

Zep-mode LLM requests do not include browser-supplied conversation history.
The current request and, when retrieved, recipe context are also supplied to
the model. The browser keeps the full transcript for display, while Zep retains
the thread and manages its context selection.

Every Crumbs request selecting Zep writes `.zep/requests/*.md`, including direct
answers and failures. Filenames include a timestamp and short query title. The
text report shows the user query, Zep thread context, recipe graph query and
results, context sent to the model, the final model input, and final response.
Zep traces contain no browser-supplied history. Reports contain no JSON copies
or embeddings. They are written when request handling ends; existing reports
are unchanged.

## Conversation saving

Selecting **Zep graph** in the UI automatically saves new exchanges to Zep. The
backend creates or validates the thread, stores the current user message before
context retrieval, and saves the assistant response after generation. Assistant
messages remain in the thread but are excluded from preference extraction.
Vector RAG retains its optional preloaded Zep memory behavior. The browser keeps
a separate transcript and thread for each backend; switching back restores it.

Graphiti selection saves only to Graphiti; Vector RAG saves to neither graph.
Zep uses its thread Context Block for conversation memory and does not receive
browser-supplied history in the model request. Graphiti sends at most five prior
messages for short-term conversational continuity and searches relevant facts in
its user group across sagas; its
current search does not retrieve whole episode histories or saga summaries.

Writes and extraction are asynchronous. A saved status confirms the write, not
immediate searchability. Save failure preserves the answer and reports an error.
Thread validation and writes live in `app.zep.memory`; the chat API coordinates
the request.
