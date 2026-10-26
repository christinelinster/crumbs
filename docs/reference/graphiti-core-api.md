# Graphiti Core Python API reference

**Scope:** `graphiti-core==0.31.2`, the Python library used directly by an application. This is a practical reference to the public `Graphiti` methods, its CRUD namespaces, and the main configuration and result types. It is not a complete reference to every internal helper or every database-driver operation.

Graphiti Core is the open-source graph library. The **Graphiti MCP server** wraps selected operations as tools for MCP-compatible clients. **Zep Cloud** is a hosted product with a different SDK and API. Their method names and capabilities should not be assumed to match this Python API.

Sources: [Graphiti Core Python package at v0.31.2](https://github.com/getzep/graphiti/tree/v0.31.2/graphiti_core), [Graphiti API docs](https://help.getzep.com/graphiti/), [Adding Episodes](https://help.getzep.com/graphiti/core-concepts/adding-episodes), [Searching](https://help.getzep.com/graphiti/working-with-data/searching), and [CRUD Operations](https://help.getzep.com/graphiti/working-with-data/crud-operations). Signatures below are checked against the project's installed `graphiti-core==0.31.2`; newer releases may differ.

## Install and connect

Install the core package, then construct `Graphiti`. The default driver is Neo4j and the default LLM, embedder, and reranker clients use OpenAI. Supply alternatives explicitly for other services or deployments. `llm_client` and `llm_runtime` are mutually exclusive.

```python
from graphiti_core import Graphiti

graph = Graphiti(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password",
)
try:
    await graph.build_indices_and_constraints()
    # Use graph...
finally:
    await graph.close()
```

Constructor parameters in 0.31.2:

| Parameter | Purpose |
|---|---|
| `uri`, `user`, `password` | Neo4j connection details when no `graph_driver` is supplied. |
| `graph_driver` | A configured `GraphDriver`; use this for another supported backend or a preconfigured driver. |
| `llm_client` | LLM implementation for extraction, resolution, and summaries. Defaults to `OpenAIClient`. |
| `llm_runtime` | Runtime/model routing alternative to `llm_client`; mutually exclusive with it. |
| `embedder` | Embedding implementation. Defaults to `OpenAIEmbedder`. |
| `cross_encoder` | Search reranker implementation. Defaults to `OpenAIRerankerClient`. |
| `store_raw_episode_content` | Whether the original episode text is stored. Defaults to `True`; set deliberately because disabling it affects provenance and episode-content workflows. |
| `max_coroutines` | Per-instance cap on concurrent operations at Graphiti's internal gather sites. |
| `tracer`, `trace_span_prefix` | Optional tracing integration and span prefix. |
| `prompt_library` | Optional prompt-library override. |

`await graph.close()` closes the driver's resources. Call it when the instance is no longer needed.

`await graph.build_indices_and_constraints(delete_existing=False)` creates the database indexes and constraints needed by Graphiti. The destructive `delete_existing=True` path drops and rebuilds existing indexes/constraints; do not use it as a graph wipe operation.

## Main operations

### `add_episode(...)`

Extracts entities and temporal relationships from one episode, resolves them against the graph, and persists the episode and extracted graph data. Episodes can be text, a message, or JSON serialized as a string. See [Adding Episodes](https://help.getzep.com/graphiti/core-concepts/adding-episodes).

```python
from datetime import datetime, timezone
from graphiti_core.nodes import EpisodeType

result = await graph.add_episode(
    name="support-001",
    episode_body="Customer: My order arrived late.",
    source=EpisodeType.message,
    source_description="Support chat",
    reference_time=datetime.now(timezone.utc),
    group_id="customer-123",
)
print(result.episode.uuid, result.nodes, result.edges)
```

Parameters:

| Parameter | Meaning |
|---|---|
| `name`, `episode_body`, `source_description`, `reference_time` | Required episode label, body string, provenance description, and event/reference timestamp. |
| `source` | `EpisodeType.message` by default; use `text` or `json` for those source formats. |
| `group_id` | Partition identifier. Defaults to the library's default group if omitted. Use explicit IDs to isolate data. |
| `uuid` | Optional caller-supplied episode UUID. Otherwise generated. |
| `update_communities` | Whether to update communities after ingesting this episode. Defaults to `False`. |
| `entity_types`, `excluded_entity_types` | Custom Pydantic entity schemas and type names to exclude. |
| `edge_types`, `edge_type_map` | Custom Pydantic edge schemas and allowed source/target-type mapping. |
| `previous_episode_uuids` | Optional prior episode context used during extraction; if absent, Graphiti finds recent episodes. |
| `custom_extraction_instructions` | Extra extraction guidance included in extraction prompts. |
| `saga`, `saga_previous_episode_uuid` | Optional saga association and explicit previous episode within that saga. |

Returns `AddEpisodeResults`: `episode: EpisodicNode`, `episodic_edges`, extracted/resolved `nodes: list[EntityNode]`, `edges: list[EntityEdge]`, and any `communities` and `community_edges` generated in this operation.

### `add_episode_bulk(...)`

Processes a list of `RawEpisode` items in one bulk pipeline. It returns aggregate lists, not one result object per input episode. In 0.31.2, `use_combined_extraction=True` selects a combined node-and-edge extraction call per episode; `False` uses separate node then edge extraction. This is about extraction calls, not merging episode bodies.

```python
from datetime import datetime, timezone
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.bulk_utils import RawEpisode

items = [
    RawEpisode(
        name="note-1",
        content="Alex works at Acme.",
        source=EpisodeType.text,
        source_description="Research notes",
        reference_time=datetime.now(timezone.utc),
    ),
]
result = await graph.add_episode_bulk(items, group_id="research")
print([episode.uuid for episode in result.episodes])
```

Parameters: `bulk_episodes` is required; `group_id`, custom/excluded entity types, custom edge types and `edge_type_map`, `strict_edge_types`, extraction instructions, and `saga` parallel the single-episode options. `use_combined_extraction` defaults to `True` in this version. Returns `AddBulkEpisodeResults` with `episodes`, `episodic_edges`, `nodes`, `edges`, `communities`, and `community_edges` lists.

`RawEpisode` in 0.31.2 has exactly six fields: required `name`, `content`, `source`, `source_description`, and `reference_time`, plus optional `uuid`. Group and extraction settings are passed to `add_episode_bulk`, not each `RawEpisode`.

### `remove_episode(episode_uuid)`

Removes the episode and its episode relationships, then removes graph data whose only episode provenance was that episode. Data supported by other episodes is retained. It returns no useful result (`None`); missing IDs/errors may raise. There is no `update_episode` method in 0.31.2. To replace content, remove and re-add an episode, typically with a deliberate stable or new UUID. See [Graphiti source](https://github.com/getzep/graphiti/blob/main/graphiti_core/graphiti.py).

```python
await graph.remove_episode(episode_uuid)
```

### Search

`search(query, ...)` is the simple fact-search API. It returns `list[EntityEdge]` and uses hybrid edge retrieval. With no center node it uses the RRF edge recipe; with `center_node_uuid` it uses node-distance reranking.

```python
facts = await graph.search(
    "Where does Alex work?",
    group_ids=["research"],
    num_results=10,
)
for fact in facts:
    print(fact.fact, fact.valid_at, fact.invalid_at)
```

Arguments: `query`; optional `center_node_uuid`, `group_ids`, `num_results` (default 10), `search_filter`, and request-scoped `driver`. Results are entity edges, not raw episodes or a prompt/context block.

`search_(query, ...)` is the configurable API. It returns `SearchResults`, which can contain `edges`, `nodes`, `episodes`, `communities`, and scores, depending on the selected search configuration. Use `SearchConfig` recipes from `graphiti_core.search.search_config_recipes` or create a custom `SearchConfig`.

```python
from graphiti_core.search.search_config_recipes import (
    EDGE_HYBRID_SEARCH_RRF,
)

results = await graph.search_(
    "Where does Alex work?",
    config=EDGE_HYBRID_SEARCH_RRF,
    group_ids=["research"],
)
print(results.edges, results.nodes, results.episodes)
```

Additional options: `center_node_uuid`, `bfs_origin_node_uuids`, `search_filter`, `driver`, and a precomputed `query_vector`. The config selects result scopes, retrieval methods, limits, and reranking. See [Searching the Graph](https://help.getzep.com/graphiti/working-with-data/searching) for the concepts and built-in recipes; inspect the installed `SearchConfig` definitions for the exact 0.31.2 fields.

`_search(...)` is deprecated and forwards to `search_`; use `search_` directly.

### Episode and extraction helpers

| Method | Input | Output / use |
|---|---|---|
| `retrieve_episodes(reference_time, last_n=..., group_ids=None, source=None, driver=None, saga=None)` | Timestamp and optional count, group(s), source type, driver, saga name. | Recent `EpisodicNode` records preceding the reference time; useful to provide previous episode context. |
| `get_nodes_and_edges_by_episode(episode_uuids)` | Episode UUID list. | `SearchResults` containing entity nodes and edges mentioned/extracted by those episodes; useful for provenance inspection. |
| `summarize_saga(saga_id)` | Saga UUID string. | Incrementally updates and returns the persisted `SagaNode`, whose summary and summary watermarks can be inspected. This is a maintenance operation, not a search call. |
| `build_communities(group_ids=None, driver=None)` | Optional groups and request driver. | Clears and rebuilds community structures in the selected partition(s); returns `(list[CommunityNode], list[CommunityEdge])`. This replaces the existing communities for those groups. |
| `add_triplet(source_node, edge, target_node, episode=None)` | Two `EntityNode`s, an `EntityEdge`, optional `EpisodicNode`. | Saves a caller-constructed fact triplet and optional episode provenance; returns `AddTripletResults(nodes, edges)`. This bypasses LLM extraction. |

`retrieve_episodes` and `summarize_saga` are distinct from relevance search: they follow episode recency/saga membership rather than selecting facts by a natural-language query. `SagaNode` represents an ordered episode grouping; an episode saga is not an automatically available full transcript summary. Use `summarize_saga` when that summary is desired.

## CRUD namespaces

`Graphiti` exposes typed repositories through `graph.nodes` and `graph.edges`. They save/load/delete graph model objects using the configured driver. `save` generally persists the object as provided; entity/edge/community embedding helpers are explicit namespace methods.

### Node namespaces

| Namespace | Model | Operations |
|---|---|---|
| `graph.nodes.entity` | `EntityNode` | `save(node, tx=None)`, `save_bulk(nodes, tx=None, batch_size=100)`, `delete(node, tx=None)`, `delete_by_group_id(group_id, tx=None, batch_size=100)`, `delete_by_uuids(uuids, tx=None, batch_size=100)`, `get_by_uuid(uuid)`, `get_by_uuids(uuids)`, `get_by_group_ids(group_ids, limit=None, uuid_cursor=None)`, `load_embeddings(node)`, `load_embeddings_bulk(nodes, batch_size=100)`. |
| `graph.nodes.episode` | `EpisodicNode` | Same save/bulk/delete/get operations as entity nodes; also `get_by_entity_node_uuid(entity_node_uuid)` and `retrieve_episodes(reference_time, last_n=3, group_ids=None, source=None, saga=None)`. |
| `graph.nodes.community` | `CommunityNode` | Same save/bulk/delete/get operations; `load_name_embedding(node)`. |
| `graph.nodes.saga` | `SagaNode` | Same save/bulk/delete/get operations. |

`get_by_group_ids` accepts a list and pagination via `limit`/`uuid_cursor`; `delete_by_group_id` accepts one group ID. Model getters generally return a model or a list of models; missing records may raise a Graphiti not-found error, so handle errors when IDs may not exist.

### Edge namespaces

| Namespace | Model | Operations |
|---|---|---|
| `graph.edges.entity` | `EntityEdge` | `save`, `save_bulk`, `delete`, `delete_by_uuids`, `get_by_uuid`, `get_by_uuids`, `get_by_group_ids`, `get_between_nodes(source_node_uuid, target_node_uuid)`, `get_by_node_uuid(node_uuid)`, `load_embeddings`, `load_embeddings_bulk`. |
| `graph.edges.episodic` | `EpisodicEdge` | `save`, `save_bulk`, `delete`, `delete_by_uuids`, `get_by_uuid`, `get_by_uuids`, `get_by_group_ids`. |
| `graph.edges.community` | `CommunityEdge` | `save`, `delete`, `delete_by_uuids`, `get_by_uuid`, `get_by_uuids`, `get_by_group_ids`. |
| `graph.edges.has_episode` | `HasEpisodeEdge` | `save`, `save_bulk`, `delete`, `delete_by_uuids`, `get_by_uuid`, `get_by_uuids`, `get_by_group_ids`. |
| `graph.edges.next_episode` | `NextEpisodeEdge` | Same operations as `has_episode`. |

For edge namespaces, `save(edge, tx=None)`, `save_bulk(edges, tx=None, batch_size=100)`, `delete(edge, tx=None)`, and `delete_by_uuids(uuids, tx=None)` are the common shapes; `get_by_group_ids(group_ids, limit=None, uuid_cursor=None)` is paginated. Only namespaces listed in the table expose bulk save in 0.31.2. Namespace methods are lower-level CRUD; episode removal is the higher-level operation that also maintains provenance-dependent graph data.

Example:

```python
from graphiti_core.nodes import EntityNode

person = await graph.nodes.entity.save(
    EntityNode(name="Alex", group_id="research", summary="Researcher")
)
same_person = await graph.nodes.entity.get_by_uuid(person.uuid)
await graph.nodes.entity.delete(same_person)
```

Deleting a node/edge directly is not equivalent to removing its source episode. Use `remove_episode` when the intent is to retract an ingestion event and let Graphiti reconcile dependent facts.

## Main models and enums

| Type | Role / common fields |
|---|---|
| `EpisodeType` | Enum values `message`, `text`, `json`, and `fact_triple`; tells Graphiti how to interpret the episode input. `fact_triple` is for a structured fact triplet rather than ordinary prose. |
| `RawEpisode` | Bulk-ingestion input described above. `content` is a string. |
| `EpisodicNode` | Persisted episode record, including identity, name, source/body-related data, timestamps, group, and links to extracted entity edges. Raw content may be absent if raw content storage is disabled. |
| `EntityNode` | Extracted entity with `uuid`, `name`, `group_id`, `summary`, labels/type, timestamps, attributes, and embedding. |
| `EntityEdge` | Temporal fact with endpoints, `name`, `fact`, `group_id`, timestamps such as `valid_at`, `invalid_at`, `created_at`, `expired_at`, and provenance episode IDs. |
| `CommunityNode` / `CommunityEdge` | Derived community grouping and its relationships. Communities must be built/updated; they are not synonymous with an episode. |
| `SagaNode` | A named sequence/grouping of episodes, including summary bookkeeping fields in this release. |
| `AddEpisodeResults`, `AddBulkEpisodeResults`, `AddTripletResults` | Pydantic result containers described in their operation sections. |
| `SearchResults` | Search container; the configured result scopes determine which of `edges`, `nodes`, `episodes`, and `communities` are populated. |
| `SearchFilters`, `SearchConfig` | Search predicates and retrieval/reranking plan. These are detailed, version-sensitive APIs; inspect their package definitions and recipes. |

For custom entity and edge schemas, pass Pydantic model **classes** in `entity_types`/`edge_types`, not instances. Use `edge_type_map` to constrain valid relations between entity types. See [Custom Entity and Edge Types](https://help.getzep.com/graphiti/core-concepts/custom-entity-and-edge-types/).

## Configuration extension points

Graphiti Core's main extension points are interfaces, not service-specific settings on `Graphiti`:

- **LLM:** `LLMClient` or `LLMRuntime`. Clients implement completion behavior; runtime routes model roles/tasks. `llm_client` and `llm_runtime` cannot both be passed.
- **Embeddings:** `EmbedderClient`, such as `OpenAIEmbedder` or another package implementation.
- **Reranking:** `CrossEncoderClient`, such as the default `OpenAIRerankerClient` or optional implementations installed with their extras.
- **Storage:** `GraphDriver`, commonly `Neo4jDriver`; the concrete driver supplies graph queries, transactions, and backend behavior.
- **Prompts:** `ChatPromptLibrary` override.

These interfaces and client-specific config models live in package modules such as `graphiti_core.llm_client`, `graphiti_core.embedder`, `graphiti_core.cross_encoder`, and `graphiti_core.driver`. Their concrete constructor parameters depend on the chosen provider/backend and may require optional extras. Configure your provider using its package client; do not confuse the Python Core interface with Zep Cloud's API key/configuration or MCP tool parameters.

## What this reference does not cover

- Internal underscore-prefixed methods, extraction helpers, migrations, Cypher queries, and backend-driver internals are not stable application APIs.
- The MCP server has its own published tool list and parameter schemas; see the [MCP server guide](https://help.getzep.com/graphiti/getting-started/mcp-server).
- Zep Cloud's hosted graph, thread, and batch endpoints belong to the separate [Zep Cloud API](https://help.getzep.com/), not `graphiti-core`.
- If a method or signature matters to your capstone, verify it against the exact package version you pin. This document targets 0.31.2, while hosted documentation and the repository's `main` branch may move independently.
