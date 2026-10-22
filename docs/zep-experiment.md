# Zep recipe context

Crumbs uses Zep's native context assembly for recipe discovery and optional
shared preferences. Full source recipe snapshots supplement the context so the
answer model can check every ingredient and instruction.

## Setup and recipe ingestion

Set `ZEP_API_KEY` and `ZEP_GRAPH_UUID` in the ignored `.env` file. For shared
memory, also set `ZEP_USER_UUID`. Start a Python console with `poetry run python`:

```python
from app import settings
from app.zep.client import get_zep

client = get_zep()
graph_uuid = settings.ZEP_GRAPH_UUID
```

Reuse the existing graph. If you need a separate graph, create one with
`client.graph.create(name="Crumbs experiment")` and save its `uuid_` in `.env`.

Submit a full recipe snapshot:

```python
from app.paths import RECIPES_DIR
from app.ingestion.load_embeddings import parse_recipe_file
from app.zep.ingest import ingest_recipe

recipe = parse_recipe_file(RECIPES_DIR / "creamy-tomato-pasta.md")
submission = ingest_recipe(client, graph_uuid, recipe)
print(submission)
```

Each submission preserves the complete JSON, groups revisions by slug in
`document_id`, and records `recipe_slug` plus a SHA-256 `recipe_revision` in
metadata. Repeated submissions create new episodes. Ingestion and extraction
are asynchronous; inspect the returned task or the episode's processing status
before expecting newly extracted facts in search. For an initial bulk backfill,
use [zep-ingest](https://help.getzep.com/zep-ingest).

Current retrieval filters invalidated/expired facts and resolves each candidate
slug to the newest snapshot by creation time. Legacy episodes without revision
metadata can only resolve among linked search sources; reingest those recipes
to make all revisions discoverable. Explicit history questions can include
superseded facts and the selected historical source episodes.

## Inspect Zep's assembled context

This is the same retrieval operation the application uses:

```python
from app.zep.retrieval import get_graph_context

result = get_graph_context(client, graph_uuid, "Show me recipes without onions")
print(result.context)                    # Exact Zep-generated context string
print(result.truncated)                  # Whether the context budget was reached
print(result.results.edges)
print(result.results.nodes)
print(result.results.observations)
print(result.results.thread_summaries)
```

The helper calls `client.graph.get_context` with `max_characters=5000`,
`include_results=True`, and current-fact filters. Zep chooses and ranks results
across scopes and renders the context block. Its native headings and content
are preserved verbatim; Crumbs does not manufacture preference/fact sections or
apply a first-ten-facts cutoff. `selection_rank` identifies global selection
order. The SDK response retains all selected result arrays, including empty arrays.
See [Zep auto search](https://help.getzep.com/v4/searching-the-graph).

Follow selected source UUIDs back to the ingested recipe content:

```python
for edge in result.results.edges or []:
    for episode_uuid in edge.episode_uuids or []:
        episode = client.graph.episode.get(graph_uuid, episode_uuid)
        print(episode.content)
```

The application follows episode UUIDs on selected edges, nodes, and
observations, fetches each UUID once, and selects full current recipe snapshots.
Invalid JSON, incomplete recipes, and mismatched slugs are skipped. Zep-only
discovery uses those snapshots for recipe cards and reads no Postgres data.
Exact recipe detail tools and card pages use the canonical Postgres store.

The final model checks hard exclusions against every ingredient/instruction
section in the selected snapshots. An absent graph fact does not prove that
an ingredient is absent. This check is performed by the answer model, so it
is not a deterministic dietary guarantee. The 5000-character budget applies
to Zep's context block; supplemental full recipes can make the final input larger.

## Inspect the final LLM input

`include_results=True` is a Zep SDK option. Inspect `result.context` and
`result.results` directly in the console example above.

Every valid `/api/chat` request automatically saves one timestamped Markdown
file in `.zep/requests/`, with these sections in order:

1. Original user query.
2. Each exact Zep request, materialized context block, selected retrieval results,
   and truncation status. Shared user context and recipe context are separate blocks.
3. Complete final LLM request: model, instructions, conversation history,
   router tool calls, tool outputs containing native context and full recipes,
   and the structured output schema.
4. Raw final model output, usage when available, and the application's response.

No request flag is required. For a direct answer, the final call is the router
call and the context section says no Zep context was retrieved. Failed requests
retain whatever was captured, including the last attempted model request and
the error type. Invalid requests rejected before the handler runs have no file.
Capture write failures are logged without breaking answer delivery.

The files contain full conversation history and source content. `.zep/` is
ignored by Git; files remain locally until deleted. Authorization headers and
API keys are not captured. Programmatic calls to `process_query_result` can be
captured with the same local writer:

```python
from app.chat_capture import capture_chat
from app.rag.query import process_query_result

with capture_chat(query) as capture:
    result = process_query_result(query, [], retrieval_backend="zep")
    capture["response"] = {"answer": result.answer, "recipe_cards": result.recipe_cards}
```

Recipe context is tool data, and shared user context is user data, never system
or developer instructions. Selected raw results appear in the Markdown file;
they do not duplicate the context in the final model prompt.

For discovery, the order is: router model, recipe `get_context`, source episode
resolution, final answer model. A direct router answer needs no recipe search
or second model call. Recipe ingestion remains a separate operation.

## Shared preferences

In Bitesize, **Use shared test memory** enables memory for `ZEP_USER_UUID`.
Everyone using it shares that test identity. Crumbs retrieves a separate native
context block from the user graph before the router, passes it to both models,
then saves only the current question/answer pair after answering. Assistant
messages remain in history but are excluded from graph extraction. The recipe graph and user graph are queried separately.

`client.thread.add_messages` returns asynchronous task and message IDs.
Check progress later with `client.task.get(task_uuid)`.
**Conversation saved to Zep** confirms the write, not completed extraction.
Save failures preserve the answer and show a warning; writes are not retried.
New preferences may take time to become searchable.

The browser restores its transcript and thread UUID from local storage. New
chat clears those local values without deleting remote memory. Turning memory
off keeps those turns local; enabling it again starts a fresh thread segment.
A reload during an unfinished request does not recover that request.

## Ingestion debugging

Use Zep's managed UI or the episode APIs for extraction workflow inspection.
Enable [Debug Mode](https://help.getzep.com/v4/debug-mode) before ingestion;
selected extraction/resolution traces require a supported plan. Debug Mode
does not backfill old episodes. Follow `result.results` source episode UUIDs
to the relevant ingestion diagnostics:

```python
print(client.graph.episode.get_debug_logs(graph_uuid, episode_uuid))
for trace in client.graph.episode.list_ingestion_traces(graph_uuid, episode_uuid):
    print(trace)
```

## Run and verify

Start the API with `poetry run uvicorn app.api:app --port 3001`, then run
`npm --prefix clients/bitesize run dev` in another terminal. Bitesize defaults to
Zep; **Vector RAG** uses the existing vector retrieval path. API requests default
to vector retrieval when `retrieval_backend` is omitted. Zep errors are surfaced
without a vector fallback. Both modes return only the recipe cards selected in
the same structured answer call, in answer order.

```bash
poetry run python -m unittest discover -s tests -v
```

Automated tests use mocked services and an SDK HTTP transport check. They cover
native context preservation, selected result scopes, source snapshots, temporal
resolution, exact final inputs, and shared memory ordering and failures.

## Query and tool boundaries

- `rag/query.py` owns conversation input, router/final model calls, capture data,
  and the cards selected for the answer.
- `rag/tools.py` owns tool schemas, dispatch, vector/Zep retrieval, and result
  preparation. Vector search exposes `input`, `limit`, and `similar_to_slug`;
  Zep search exposes `input` and `include_history`.
- `db/recipes.py` owns SQL. Full recipe lookups and embedding lookups are separate.
- `api.py` validates HTTP input, manages optional shared memory, and captures
  each chat request. `main.py` is the CLI entry point to the same query function.

A detail tool returns `{"recipe": null}` when the slug is missing. The final
answer prompt explicitly treats this as not found and forbids substitute
searches. Tool outputs omit arguments already present in the model's tool call.
Vector search returns `matches` with per-match strength; a requested similarity
anchor is an identity object, or `null` when missing. Zep search returns the
native `context`, `truncated`, and full source `recipes`.
