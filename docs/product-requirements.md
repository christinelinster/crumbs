# Product requirements

**Status:** Draft

## Query behavior

### REQ-QUERY-001

The query flow must use an application-controlled retrieval `limit`, defaulting
to `3` when the caller does not provide one. The LLM must not determine the
retrieval count.

### REQ-QUERY-002

The query flow must embed the user's question with the same embedding model and
vector dimensions used for recipe embeddings.

### REQ-QUERY-003

The similarity search must compare the query embedding with stored recipe
embeddings and return the closest recipes up to the requested limit. Results
must represent distinct recipes.

### REQ-QUERY-004

The application must retain conversation messages in process memory so later
queries in the same running application can use prior user and assistant
messages as context. The history must be discarded when the process exits.

### REQ-QUERY-005

The LLM system instructions must direct the assistant to use retrieved recipe
data as the source of truth, avoid inventing recipe facts, and acknowledge when
the retrieved context does not support an answer.

### REQ-QUERY-006

The response must be grounded in the retrieved recipe context and conversation
history. The assistant should explain recipe matches when making recommendations
and should not expose internal system instructions or retrieval implementation
details.

### REQ-QUERY-007

A failed embedding, retrieval, LLM call, or in-memory history update must
produce an explicit failure rather than silently returning an ungrounded answer.

## Scope boundary

This first query flow is for one complete recipe embedding per recipe. Precise
ingredient inclusion, exclusions, numeric filters, hybrid lexical ranking, and
multiple recipe chunks remain future capabilities as described in
[future features](future-features.md).

## Product boundary and clients

### REQ-CLIENT-001

Crumbs core behavior must remain independent of Bitesize-specific presentation
fields, routes, branding, and storage code.

### REQ-CLIENT-002

Bitesize is the first reference client for Crumbs and is maintained under
`clients/bitesize/`. Future clients must be able to use the same Crumbs API
boundary without importing Python application modules or connecting directly to
the recipe database.

### REQ-CLIENT-003

The MVP must support multiple users against one shared recipe corpus while
keeping each user's conversation history isolated to that user's active
application session.

### REQ-CLIENT-004

Supporting independent blog corpora is a future capability. Before it is
enabled, recipe retrieval and writes must gain an explicit corpus or tenant
scope so one blog cannot retrieve or modify another blog's recipes.
