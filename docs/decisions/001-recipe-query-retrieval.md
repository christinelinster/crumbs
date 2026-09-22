# 001: Recipe-grounded query retrieval and conversation persistence

**Status:** Superseded by [002: In-memory conversation history](002-in-memory-conversation-history.md)  
**Date:** 2026-09-20

## Context

Recipes already have one complete-recipe vector in Postgres, but the
application has no retrieval or conversation layer. The query feature needs to
ground LLM responses in stored recipes and preserve multi-turn context.

## Decision

Use a shared embedding helper for both recipe and query vectors. Let application
code choose the retrieval limit, defaulting to three, and use vector similarity
search to select recipe context before the LLM call. The original design stored
conversation and message history in Postgres; that decision was superseded by
ADR 002 in favor of process-local memory. Treat the LLM as the response
generator over the retrieved context rather than as the retrieval-limit
selector.

## Consequences

- Query and recipe vectors remain compatible because they use one model and
  dimension configuration.
- Retrieval is deterministic with respect to the application-selected limit
  and stored vectors.
- This decision no longer governs conversation storage; ADR 002 governs it.
- Prompt and response behavior can be tested independently of vector search.
- A future change to chunking, hybrid ranking, authentication, or model choice
  will require a separate design decision.

## Alternatives considered

In-memory history and caller-supplied history were considered during the
original design. Postgres persistence was the original choice and was later
replaced by the process-local memory decision in ADR 002.
