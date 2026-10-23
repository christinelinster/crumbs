# Inspecting native Graphiti and Zep behavior

Use the same Markdown files, fresh recipe graphs, and initially empty user
graphs. Compare each backend's native behavior, not identical output types.
Chat answers use `OPENAI_CHAT_MODEL` for both backends and no graph recipe cards.

## What is stored

| Data | Graphiti | Zep |
| --- | --- | --- |
| Raw recipe | `Episodic` node containing Markdown | Text episode containing Markdown |
| Extracted entities | Entity nodes, labels, attributes, summaries | Nodes, labels, attributes, summaries exposed by the SDK |
| Extracted facts | Temporal `RELATES_TO` edges with episode provenance | Temporal edges with episode provenance |
| User identity | Application identifies Christine inside `USER_GROUP_ID` | Registered user has a dedicated central node |
| Entity summary | Maintained during entity ingestion/update | Managed entity summary |
| User summary | Christine's regular entity summary; no dedicated user-summary service | Managed summary on the central user entity, with dedicated instructions |
| Conversation summary | Saga summary; Crumbs explicitly refreshes it after saved turns | Managed thread summary updated asynchronously |
| Community summary | Available after community construction; not built by this comparison | No Graphiti community-building API assumed by this integration |

Zep's user summary is the summary stored on its user entity, not a second copy
above it. Its public APIs describe its generation and user-specific instructions;
they do not establish that Zep runs Graphiti's default implementation unchanged.
A `group_id` is a namespace, not a user entity or a summary.

## Graphiti ingestion and inspection

```bash
poetry run python -m app.graphiti.main path/to/recipe.md
```

Graphiti ingestion returns extracted entities and facts and writes a report to
`.graphiti/ingestion/`. To inspect current stored state, including summaries:

```python
import asyncio
from app import settings
from app.graphiti.client import get_graphiti
from app.graphiti.inspect import inspect_graph

async def inspect():
    client = get_graphiti()
    try:
        await inspect_graph(client, settings.RECIPE_GROUP_ID)
        await inspect_graph(client, settings.USER_GROUP_ID)
    finally:
        await client.close()

asyncio.run(inspect())
```

Inspection reads all entities, facts, episodes, sagas, and communities in the
selected group and saves Markdown. It does not call an LLM, build communities,
or refresh summaries. Empty results mean no such artifacts are currently stored.
Use it on small comparison graphs, not as an unbounded production reporting job.

Zep submission and inspection instructions are in [Zep recipe context](zep-experiment.md).
No live provisioning or ingestion is performed automatically by this change.

## Retrieval paths and settings

| Step | Graphiti | Zep |
| --- | --- | --- |
| Tool | `get_recipes(input)` | `get_recipes(input)` |
| Graph scopes | Separate recipe/user group searches | Separate recipe/user UUID context requests |
| Native retrieval | `Graphiti.search`, hybrid edge search with RRF and native default limit of 10 per group | `graph.get_context`, native assembly with 5000 characters per graph and selected result arrays |
| Current-fact filters | Invalid/expired timestamps are null | Invalid/expired timestamps are null |
| Native output used | Recipe facts and user facts | Recipe context and user context |
| Source supplement | Recipe facts' episode UUIDs resolve to raw Markdown | Selected results' recipe episode UUIDs resolve to raw Markdown |
| Final response | Common grounded answer instructions and plain text | Common grounded answer instructions and plain text |

Ingestion model routing for Graphiti comes from `GRAPHITI_LLM_MODEL` and
`GRAPHITI_SMALL_MODEL` in settings. The latter currently reads the
`GRAPHITI_EXTRACTION_MODEL` environment variable. The default model handles
unrouted prompts; node/edge attribute extraction is routed to the small model.
The OpenAI client uses reasoning effort `low`. Native extraction prompt templates
remain in Graphiti. These settings are reported, not overwritten for the experiment.

Graphiti search does not automatically retrieve entity or saga summaries in this
path. Zep selects context according to its native assembly. Available summaries
are inspected separately; no extra summary is forced into either model input.
Recipe and user graph results remain distinct throughout. Selecting Zep or
Graphiti in the UI automatically saves the current exchange only to that backend.
Vector RAG saves to neither graph. There are no separate save toggles.

The router chooses whether to search and supplies the actual search query.
The final answer call receives conversation history, router tool calls, and the
retrieval tool output. The source supplement is application behavior and is
identified separately from native results. No graph recipe-detail request falls
back to Postgres or vector search.

## Read a request trace

Select Zep or Graphiti in the Crumbs UI and ask a recipe or preference question.
Inspect the new file in `.zep/requests/` or `.graphiti/requests/`:

- Compare the original question with the actual search query and graph scopes.
- Inspect native results before looking at supplemental Markdown sources.
- Inspect tool outputs to see what was retained for answer generation.
- Inspect router and final model requests to see instructions and conversation history.
- Compare final model text with the API's delivered answer.

A trace without search results is not evidence that a graph has no stored data:
the router may choose a direct answer, or retrieval may find no relevant context.
Storage inspection reports and request traces answer different questions.

References: [Zep text ingestion](https://help.getzep.com/v4/adding-business-data),
[Zep context assembly](https://help.getzep.com/v4/retrieving-context),
[Zep user summaries](https://help.getzep.com/v4/user-summary),
[Graphiti source](https://github.com/getzep/graphiti).
