# Minimal Graphiti experiment

Graphiti + Neo4j recipe ingestion, chat retrieval, and conversation
saving for the selected graph backend. The existing Poetry environment includes `graphiti-core`.

Start your Neo4j container and set these values in the repository's ignored
`.env` file:

```dotenv
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-existing-neo4j-password
OPENAI_API_KEY=your-openai-key
GRAPHITI_LLM_MODEL=gpt-5.5
GRAPHITI_EXTRACTION_MODEL=gpt-5.5
```

Zep's [current Graphiti quick start uses `gpt-5.5` as its default OpenAI
model](https://help.getzep.com/graphiti/getting-started/mcp-server), and its
[LLM guidance recommends models with structured output](https://help.getzep.com/graphiti/configuration/llm-configuration).
`GRAPHITI_LLM_MODEL` is the fallback for Graphiti's other LLM prompts.
`GRAPHITI_EXTRACTION_MODEL` supplies `GRAPHITI_SMALL_MODEL` in settings and is
routed to node/edge attribute extraction. Other extraction and summary prompts
use `GRAPHITI_LLM_MODEL`; if omitted, the small model inherits that value.

These settings are separate from Crumbs' chat model setting. Graphiti embeddings
and reranking use Graphiti's own defaults. Ingestion and search can make paid
model calls.

To ingest one Markdown recipe and inspect extraction, pass its path:

```bash
poetry run python -m app.graphiti.main data/recipes/creamy-tomato-pasta.md
```

Replace the example path with any Markdown file. Relative paths are resolved
from your current working directory; absolute paths also work. Quote paths
containing spaces. The command prints the extracted entities and relationships.
Indexes are initialized before ingestion; the CLI does not run a search.
Ingestion does not write trace files. Inspect stored data in the Neo4j UI.
For programmatic summary inspection and the Zep comparison, see [the comparison guide](../../../docs/native-graph-comparison.md).

Run it again with another file, or edit a file and rerun it, to observe how
Graphiti incorporates new evidence. Each run adds an episode rather than
replacing the previous episode; entity merging and fact invalidation are managed
by Graphiti's extraction pipeline.

For selected recipes in bulk, use `app.graphiti.ingest.ingest_recipes(client, paths)`
inside the same client/index initialization and close lifecycle. It reads every
file before writing and calls `add_episode_bulk(..., use_combined_extraction=False)`.
This uses Graphiti's native text node/edge prompts, matching single-file text
ingestion. The default combined bulk prompt is conversational and can attribute
recipe facts to a generic `User`; this helper avoids that prompt without custom
extraction instructions or an ontology. Model output still needs inspection.
Changing the ingestion path does not rewrite existing graph data.

Neo4j uses `MENTIONS` edges for episode-to-entity provenance. Extracted facts are
entity-to-entity `RELATES_TO` edges; their semantic predicate is `r.name` and their
fact text is `r.fact`. To inspect only recipe facts:

```cypher
MATCH (source:Entity)-[r:RELATES_TO]->(target:Entity)
WHERE r.group_id = 'shared_recipes'
RETURN source.name AS source, r.name AS relationship, r.fact AS fact,
       target.name AS target;
```

The complete Markdown file, including frontmatter and headings, is submitted as
text without parsing or normalization. The episode name is the filename without
its extension. Ingestion waits for extraction. No custom ontology is supplied yet;
`ingest.py` is where you can later pass `entity_types`, `edge_types`, and
`edge_type_map` to `add_episode`.

Each ingestion call adds an episode, even when the filename is unchanged.
There is no repeat-import deduplication or recipe revision selection. The
recipe namespace is `shared_recipes`, set in `app.settings.RECIPE_GROUP_ID`.
Chat retrieval searches both `shared_recipes` and `user_christine`, keeping
user facts separate from recipe facts and fetching Markdown sources only for
recipe facts. Earlier data ingested into the default group is not moved or
deleted; ingest the source files again to populate `shared_recipes`.

Every request selecting Graphiti saves a text Markdown trace in
`.graphiti/requests/`, including direct answers and failures. Filenames contain
a timestamp and short query title. Reports show the user query, graph IDs and
actual search queries, returned facts and recipe sources, context submitted to
the model, full final input with system instructions and at most six recent conversation
messages,
and final response. Unsent context is labeled separately. No JSON copies or
embedding vectors are included. Reports are written when request handling ends.
`.graphiti/` is ignored by Git, so these files remain local until deleted.

## Query recipes in Bitesize

Select **Graphiti (Neo4j)** in the chat's Retrieval menu, then type a recipe
question. The existing intent router sends recipe searches to Graphiti's native
search. It uses the search text derived from your question and conversation,
and filters invalidated/expired facts. Source episode IDs on the returned facts
are used to fetch the original Markdown without parsing or normalization.

The answer model receives those facts and sources as tool data. It is instructed
to check source ingredients/instructions for dietary exclusions and acknowledge
missing evidence. This is model guidance, not a deterministic dietary guarantee.
Graphiti mode returns text answers without recipe cards or Postgres lookups;
questions about specific recipes also use graph search. General cooking or
unrelated questions can still receive a direct router answer without searching.

Graphiti search errors surface as a chat error, without falling back to vector
or Zep search. In Graphiti mode, the current exchange is automatically saved
after answering. Retrieved user
facts can personalize recommendations, but remain distinct from recipe evidence.
The current exchange is saved after the answer and can inform later requests.

## Capture test-user conversations

In Bitesize, select **Graphiti (Neo4j)**. Each successful chat automatically saves
only its current user/assistant exchange into `user_christine`, set in
`app.settings.USER_GROUP_ID`. Earlier history is not uploaded again. Graph-mode LLM calls receive at most the
five latest prior messages plus the current question; relevant long-term facts
come from Graphiti search across Christine's user group.

The API generates a separate `graphiti_thread_uuid` for the first enabled turn.
Graphiti's `saga` parameter groups turns under `thread_<uuid>` using a Saga node
and episode links. The browser stores the UUID with the transcript and reuses
it after reload. Switching retrieval backends restores that backend's saved transcript and thread.
New chat starts a fresh conversation only for the selected backend without
deleting remote data. Selecting Zep saves only to Zep; Vector RAG saves
to neither graph. There are no separate save toggles.

The user graph unifies knowledge across those conversation segments. A saga
groups episodes; it is not a separate namespace or a guarantee that extraction
context is confined to that conversation. Extraction instructions ask Graphiti
to use Christine's statements as evidence and assistant text only as context.
This is model guidance, not a deterministic preference filter.

This is one shared test identity, not login or private per-user storage. The
application chooses these namespaces; it does not accept user-supplied group
IDs. Namespace filtering does not provide authorization for a future multi-user
deployment.

Saving waits for Graphiti extraction before the HTTP response returns, so it
adds model latency. A save failure preserves the answer and displays a warning;
there are no automatic retries. Unconfirmed or repeated saves can leave extra
episodes. Retrieved user facts can inform later answers. The save function
explicitly refreshes the saga summary; that summary is stored but is not
automatically included by this fact-search retrieval path.

Inspect the graph at <http://localhost:7474>:

```cypher
MATCH (n) RETURN n LIMIT 50;
```

Inspect just the shared recipe space:

```cypher
MATCH (n {group_id: 'shared_recipes'}) RETURN n LIMIT 50;
```

Inspect test-user conversation episodes grouped by saga:

```cypher
MATCH (s:Saga {group_id: 'user_christine'})-[:HAS_EPISODE]->(e:Episodic)
RETURN s.name, e.uuid, e.content;
```

Run mocked checks without Neo4j or OpenAI calls:

```bash
poetry run python -m unittest tests.test_graphiti tests.test_graphiti_retrieval tests.test_graphiti_memory -v
```
