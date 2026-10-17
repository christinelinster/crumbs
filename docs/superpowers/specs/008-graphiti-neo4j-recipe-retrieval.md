# 008: Graphiti and Neo4j recipe retrieval

**Status:** Awaiting approval
**Parent project:** [SPEC.md](../../../SPEC.md)
**Design brief:** Agreed in conversation on 2026-10-17; written specification awaiting review

## Objective

Use Graphiti in the real Crumbs recipe application to understand its ingestion,
entity and relationship extraction, temporal updates, hybrid retrieval, and
model sensitivity. The result must be usable through Bitesize, with evidence
that makes the pipeline inspectable. Better retrieval than the existing vector
backend is an evaluation question, not an assumed outcome.

## Scope and boundaries

- Implement on a new development branch. Preserve existing uncommitted work;
  do not stage, commit, or push without explicit instruction.
- Graphiti is the branch's default recipe discovery backend. A configuration
  switch selects the existing PostgreSQL/pgvector backend for comparison.
- Keep backend implementations in the same application and development branch.
  Zep is a subsequent implementation through the same retrieval boundary,
  not a parallel branch with a divergent application. Implementing Zep is
  outside this specification; compare the starter batch before deciding where
  to ingest the full corpus.
- Run Neo4j locally using Docker Compose with persistent storage and access
  through Neo4j Browser. Keep experiment data separate from other databases.
- Use OpenAI for every model-dependent operation.
- Ingest recipes only. User profiles, persisted conversation memory,
  authentication, automatic background synchronization, historical chat queries,
  and hosted infrastructure are outside this feature.
- Preserve exact-recipe lookup, existing recipe navigation, cards, ordered
  ingredients/instructions, and conversation routing behavior.
- This feature extends the vector-only retrieval scope described in the parent
  specification for this experimental branch. PostgreSQL remains the canonical
  application recipe store; Neo4j stores derived graph knowledge and provenance.

## Architecture and data flow

Use the Graphiti Python library directly from the Python application rather
than introduce its separate REST or MCP server. Pin a compatible Graphiti
version in the dependency lockfile and document the exact version used.
The supplied upstream commit is the investigation reference, not a promise
that an unverified dependency combination already works.

Provide a small retrieval boundary with vector and Graphiti implementations.
Select them through `RETRIEVAL_BACKEND=vector|graphiti`; selecting an unsupported
value fails clearly. A later Zep integration will add `zep` as a valid value,
not silently route it to another backend. Configuration changes may require
an application restart; a live backend picker is outside this feature.
The boundary returns recipe candidates and supporting evidence in a shared
format while retaining backend-specific ranking metadata. Keep vector data in
PostgreSQL, Graphiti data in local Neo4j, and future Zep data in a separate
managed graph. Zep uses its own SDK/API and credentials; its API key is not
a replacement for Graphiti's OpenAI or Neo4j credentials.

The query service owns intent routing and answer synthesis; each backend owns
candidate retrieval and its evidence. Keep async Graphiti client lifecycle and
connection management explicit and compatible with both FastAPI and CLI entry
points. Do not repeatedly create event loops around shared live clients.

Graph discovery follows this flow:

1. The existing OpenAI router interprets the request and invokes recipe search.
2. Graphiti embeds the search text and performs hybrid retrieval.
3. If enabled, the configured OpenAI reranker reranks retrieved candidates.
4. Resolve graph evidence through episode provenance to stable recipe slugs.
5. Aggregate supporting evidence per recipe, remove duplicates, and load current
   recipe data from PostgreSQL. Exclude the anchor for similar-recipe requests.
6. Supply relevant graph evidence and current recipe data to answer synthesis.
   Return ordinary recipe cards plus structured diagnostics.

Graph relationships guide discovery; current recipe content remains the source
of truth for quantities, instructions, and whether a candidate satisfies a
claimed constraint. Do not infer ingredient absence from a missing graph edge.
Preserve the existing behavior of labeling imperfect matches as alternatives.

The graph backend must not reuse the vector cosine threshold as if graph
ranking scores were cosine similarities. Use explicit backend-specific score
metadata; keep the existing vector score semantics. Graph cards may expose a
null legacy similarity score. Define deterministic recipe aggregation and tie
breaking during implementation planning and test the resulting behavior.

## Recipe ingestion and provenance

Reuse the existing Markdown parser and section normalization. Preserve recipe
identity, grouped ingredients, instructions, metadata, and relevant notes in
episode inputs. Use lightweight Pydantic entity types for Recipe, Ingredient,
and CookingTechnique, with extraction guidance rather than a closed ontology.
Do not invent missing nutrition, ingredient quantities, or dietary properties.

Provide an explicit ingestion command with mutually clear selection modes:
named recipe slugs, a checked-in starter manifest, or the entire corpus.
Validate the selection and recipe identities before paid extraction calls.
No implicit full-corpus ingestion on application startup.

Track experiment identity, stable recipe slug, normalized content hash,
immutable revision identity, Graphiti episode UUID, observation/effective time,
extraction configuration, and ingestion status. Persist successful bookkeeping
so an unchanged rerun makes no extraction calls. Hash semantic recipe content,
not irrelevant Markdown formatting. Graphiti episode UUIDs are provenance IDs,
not application upsert keys.

New recipes receive initial snapshot episodes. A selected recipe's graph input
must agree with its current PostgreSQL content before it is served through chat;
report missing or stale canonical rows with an actionable instruction to refresh
the existing recipe loader. Do not silently serve mismatched revisions.

Report per-recipe success, skip, and failure status plus summary counts. A failed
run exits unsuccessfully and does not mark failed revisions complete. Account
for partially completed graph writes: never assume a retry is safe merely
because the final application bookkeeping write failed. The implementation plan
must include a detectable pending state and recovery policy, without claiming
an atomic transaction across PostgreSQL, Graphiti, and model calls.

## Temporal recipe revisions

For a changed recipe, append a new timestamped episode identifying the same
recipe, the previous and new revision, an explicit description of changes, and
the updated snapshot. Preserve earlier episodes and historical relationships.
Use the actual change time if known; otherwise record the ingestion observation
time and label it accordingly. Do not fabricate historical effective dates.

Explicitly state removals and replacements. A newer snapshot that omits butter
does not by itself prove the previous butter relationship is false. Graphiti's
invalidation is extraction- and retrieval-dependent, so verify its effects.
Apply explicit temporal filtering for current retrieval rather than assume
Graphiti's default search excludes invalidated relationships.

Check retrieved evidence against the active recipe revision and canonical
content. Outdated or unverified evidence must not justify a current recipe
claim. If reconciliation cannot establish the current state, report the issue
instead of silently presenting the graph as current.

Recipe deletion and slug changes are not implicit temporal edits: report a
missing indexed source or identity change for explicit reconciliation. Do not
infer deletion from a selected-subset run. A title rename with an unchanged
slug remains the same recipe and is covered by revision tests.

Rebuilds remain explicit maintenance/experiment operations. They must target
only the selected experiment's graph and metadata. Do not erase history as
part of ordinary ingestion. Historical relationships are inspectable in Neo4j
Browser; the chat UI answers current-state questions only.

## Model configuration and comparisons

Independently configure OpenAI extraction, embedding, chat, and reranking
models. If Graphiti uses additional small-model calls, make that effective
configuration explicit as well. Provide documented configuration examples and
validated defaults compatible with the pinned library. Optional LLM reranking
is disabled for the initial hybrid-retrieval baseline.

Changing extraction models does not re-extract existing facts automatically.
Changing embedding models or dimensions must not mix incompatible vectors.
Record an ingestion configuration fingerprint, including schema/instruction
version, and reject incompatible writes to an existing experiment.

Compare extraction models using identical recipe inputs, instructions,
embedding settings, and ingestion order in isolated experiment graphs.
Use distinct local Neo4j instances/Compose projects and volumes when needed;
do not assume Neo4j Community supports multiple application databases or that
Graphiti group IDs provide the required isolation. Select the active experiment
explicitly for both application queries and ingestion.

Capture model names, configurations, counts, timings, and provider-reported
token usage where available. Clearly label unavailable usage. Do not fabricate
token counts or dollar costs; cost estimates require documented pricing inputs.

## Starter batch and evaluation

Support the full current recipe corpus, not only a demo subset. First use a
checked-in manifest of approximately ten actual recipes
selected to include shared ingredients, similar recipes with differences,
multiple cooking techniques, grouped sections, quantities, and optional
ingredients or substitutions where present. Record why each recipe was chosen.
Do not select a different arbitrary batch on every run.

The evaluation sequence is:

1. Integrate Graphiti into Crumbs using the starter batch, inspect extraction,
   test a controlled revision, and compare two extraction models.
2. In a follow-up feature, integrate Zep into the same application and ingest
   the identical starter batch. Compare it with Graphiti and vector retrieval
   using the same saved questions, conversation histories, and answer model.
3. Use the comparison to decide which backend or backends receive the full
   corpus. Full-corpus ingestion remains an explicit command, not an automatic
   next action when the starter run succeeds.

Provide a repeatable comparison command for the currently implemented graph
and vector backends. Save the shared inputs and results so the later Zep
implementation can participate without branching the application. A future
Zep comparison evaluates complete systems: do not claim identical extraction
models, embedding models, or internal search settings when the managed service
does not expose those controls. Verify account capabilities and estimate
payload-based credit consumption before that follow-up's ingestion.

Do not run expensive full-corpus extraction as a side effect of tests or
dependency installation.

Maintain representative comparison questions covering similarity, shared
ingredients/techniques, exclusions, and insufficient evidence. Run the same
questions and corpus against graph and vector backends; hold chat models and
other relevant settings fixed. Save configuration, retrieved sources/facts,
answers, timing, and available usage. Judge relevance and grounding rather than
require a predetermined Graphiti win or identical generated text.

## Diagnostics and failure behavior

Extend chat responses additively with structured diagnostics and render an
expandable Bitesize view. Show backend and experiment, interpreted search input,
effective model settings, retrieved facts, supporting recipe links, ranking
information, and timings for routing, embedding/retrieval, optional reranking,
and answer generation when individually measurable. Distinguish stages not
run from metrics unavailable from the library. Report direct-answer and
exact-detail paths accurately, without implying graph retrieval occurred.

Do not expose credentials, hidden prompts, or model chain-of-thought. Explain
model stages in developer documentation; ordinary answer prose remains focused
on recipes. Neo4j Browser supplies graph inspection; a custom graph visualizer
is outside scope.

Surface database, extraction, and retrieval failures clearly. Never silently
fall back to vector retrieval, since that would invalidate comparisons. The
configuration switch remains the explicit way to select vector retrieval.

## Acceptance and verification

- Selected, starter, and full-corpus ingestion modes behave as documented.
  Unchanged reruns skip extraction; invalid selections fail before model calls.
- Facts resolve to stable recipe slugs/cards with traceable episode provenance.
- Real Neo4j/OpenAI smoke verification covers ingestion, hybrid retrieval,
  optional reranking, and a grounded answer from the starter batch.
- Tests cover revision addition, ingredient removal/replacement, quantity
  change, and title rename. Verify historical evidence remains inspectable and
  obsolete facts cannot support current answers.
- Isolated extraction-model experiments cannot contaminate each other. A
  configuration mismatch is rejected with an actionable message.
- Graph retrieval is the branch default; vector configuration retains its
  existing scoring behavior. Exact lookup and anchor exclusion still work.
- Diagnostics render facts, sources, configurations, and honest timings.
  Backend failures are visible rather than hidden by fallback.
- Add meaningful unit/contract tests for ingestion bookkeeping and recovery,
  provenance aggregation, temporal/current-content guards, backend selection,
  API diagnostics, and the client inspector. Use mocked providers for normal
  tests and explicitly opt into paid/external integration runs.
- Run the focused and complete Python suites and relevant Bitesize tests,
  build, and lint. Report actual commands/results and distinguish live
  integration evidence from mocked tests or blocked checks.
- Document Docker startup, Browser access, configuration, batch/full ingestion,
  model comparisons, revisions, recovery, and experiment-specific reset.
- At implementation completion, present the scoped diff for review. Do not
  stage, commit, or push.

## References

- [Graphiti repository](https://github.com/getzep/graphiti)
- [User-supplied quickstart revision](https://github.com/getzep/graphiti/tree/d50741d1bf463cbe3859eb73914cbff1b66839e6/examples/quickstart)
- [Episode and search APIs at the supplied revision](https://github.com/getzep/graphiti/blob/d50741d1bf463cbe3859eb73914cbff1b66839e6/graphiti_core/graphiti.py)
- [Upstream contradiction rules](https://github.com/getzep/graphiti/blob/main/graphiti_core/prompts/dedupe_edges.py)
- [Upstream search filters](https://github.com/getzep/graphiti/blob/main/graphiti_core/search/search_filters.py)

The latter two links track upstream main. Recheck relevant behavior against the
locked release during implementation; public APIs and defaults may differ.
