# 001: Recipe-grounded conversational retrieval

**Status:** Draft\
**Parent project:** [@SPEC.md](../../../SPEC.md)

## Objective

Provide a conversation-aware query flow that retrieves relevant recipes by
embedding similarity and asks an LLM to return a grounded answer.

## Scope

- Shared recipe and query embedding generation.
- Application-controlled retrieval limit with a default of three.
- Similarity retrieval against the existing complete-recipe vectors.
- Process-local in-memory conversations and ordered user/assistant messages.
- A system prompt with simple grounding and non-invention guardrails.
- An LLM response using retrieved recipes and prior conversation context.

## Out of Scope

- LLM-controlled retrieval count.
- Hybrid lexical or ingredient-aware ranking.
- Multiple chunks or embeddings per recipe.
- Authentication, workspaces, creator ownership, frontend, or HTTP API design.
- Streaming, background jobs, or model-selection policy.

## Dependencies

- None. The existing recipe table and embedding loader are available capabilities.

## Required Context

- [@docs/product-requirements.md#query-behavior](../../product-requirements.md#query-behavior)
- [@docs/architecture.md#data-flow](../../architecture.md#data-flow)
- [@docs/technical-decisions.md#embedding-and-chunking](../../technical-decisions.md#embedding-and-chunking)
- [@docs/decisions/002-in-memory-conversation-history.md](../../decisions/002-in-memory-conversation-history.md)

## Authoritative Requirement References

- [@docs/product-requirements.md#req-query-001](../../product-requirements.md#req-query-001)
- [@docs/product-requirements.md#req-query-002](../../product-requirements.md#req-query-002)
- [@docs/product-requirements.md#req-query-003](../../product-requirements.md#req-query-003)
- [@docs/product-requirements.md#req-query-004](../../product-requirements.md#req-query-004)
- [@docs/product-requirements.md#req-query-005](../../product-requirements.md#req-query-005)
- [@docs/product-requirements.md#req-query-006](../../product-requirements.md#req-query-006)
- [@docs/product-requirements.md#req-query-007](../../product-requirements.md#req-query-007)

## Acceptance Criteria

- A query without an explicit limit retrieves at most three distinct recipes.
- A caller-provided limit is passed to similarity retrieval and is not selected
  or changed by the LLM.
- The query vector uses the same embedding helper and model configuration as
  recipe vectors.
- A conversation's user and assistant messages remain available to a later
  query in the same running process.
- Conversation history is absent after the application process exits.
- The LLM receives the system guardrails, prior conversation messages, and the
  retrieved structured recipe context.
- The returned answer does not invent recipe facts when the retrieved context
  does not support them.
- Failed embedding, retrieval, LLM, or history-update operations are surfaced as
  failures and do not create a false assistant response.

## Verification Expectations

Use unit tests with fake embedding and LLM clients and fake database
connections. Verify limit propagation, vector ordering, message ordering,
prompt contents, failure behavior, and the separation between retrieval context
and system instructions. Run the full repository test suite before implementation
is considered complete.

## Related ADRs

- [@docs/decisions/002-in-memory-conversation-history.md](../../decisions/002-in-memory-conversation-history.md)

## Documentation Fallback

Read [@SPEC.md](../../../SPEC.md) as the fallback routing source whenever
additional project documentation is required.
