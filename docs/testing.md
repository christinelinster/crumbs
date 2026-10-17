# Testing strategy

**Status:** Draft

The query feature should be testable without live OpenAI or Postgres services.
Patch the query-layer OpenAI constructor and use fake database connections
consistent with the existing ingestion tests.

## Required coverage

- The shared embedding helper sends one input and rejects responses that do not
  contain exactly one vector.
- The application default is `limit=3`, and an explicit limit is passed to
  similarity retrieval unchanged.
- General retrieval uses the application default similarity threshold of `0.5`.
  Clearly unrelated questions use the normal retrieval path and are handled by
  the system prompt; an explicit scope redirect clears returned recipe cards.
- Similarity retrieval orders by vector distance and returns only the requested
  number of distinct recipes.
- Recipe-card retrieval returns display metadata and similarity scores without
  embeddings, ingredients, or instructions; full-context retrieval retains those
  fields for grounded chatbot responses.
- In-memory conversation messages are retained in order and prior history is
  supplied to the LLM during the same process.
- The system prompt contains the grounding and non-invention guardrails.
- Recommendation responses are instructed to number qualifying recipes and
  explain why they fit in short prose rather than bullet points; explicit
  detail requests preserve complete ingredients and instructions with readable
  Markdown headings and lists.
- A failed embedding or LLM request does not append an assistant message.
- Retrieved recipe context is included in the LLM request, while embeddings and
  internal retrieval details are not exposed as the user-facing answer.
- Loader normalization turns raw parser fields into ordered JSONB sections;
  every section has `kind`, `name`, and `items`. Repository reads and RAG
  context retain sections. The recipe detail API returns those section objects
  directly. Bitesize flattens items locally only for ingredient highlighting.
  Cover repeated group names, unnamed groups, and ungrouped items with
  `name: null`.
- The opt-in PostgreSQL schema test verifies the JSONB fields, array checks,
  absence of child tables, and safe reruns in a transaction-local namespace.

Run the focused query tests with:

```bash
poetry run python -m unittest tests.test_query tests.test_main -v
```

Run the ingestion and query tests together with:

```bash
poetry run python -m unittest tests.test_load_embeddings tests.test_query tests.test_main -v
```

Run the repository test suite with:

```bash
poetry run python -m unittest discover -s tests -v
```

Run the opt-in PostgreSQL schema check with:

```bash
env CRUMBS_RUN_PG_SCHEMA_TESTS=1 poetry run python -m unittest tests.test_recipe_content_schema -v
```

## Client foundation

The Bitesize reference client should be verifiable independently from the
Python test suite. Its package checks should include a successful lint run and a
production build from `clients/bitesize/`. API integration tests belong to the
shared API feature once its response contract is approved; the client should
not require a live OpenAI or Postgres service merely to build. Chat utility
tests cover optimistic user messages, request history, and assistant content
block parsing.
