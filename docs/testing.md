# Testing strategy

**Status:** Draft

The query feature should be testable without live OpenAI or Postgres services.
Use injected clients and database connections consistent with the existing
ingestion tests.

## Required coverage

- The shared embedding helper sends one input and rejects responses that do not
  contain exactly one vector.
- The application default is `limit=3`, and an explicit limit is passed to
  similarity retrieval unchanged.
- Similarity retrieval orders by vector distance and returns only the requested
  number of distinct recipes.
- Recipe-card retrieval returns display metadata and similarity scores without
  embeddings, ingredients, or instructions; full-context retrieval retains those
  fields for grounded chatbot responses.
- In-memory conversation messages are retained in order and prior history is
  supplied to the LLM during the same process.
- The system prompt contains the grounding and non-invention guardrails.
- Recipe responses are instructed to include the title, source URL when
  available, ingredients, and numbered instructions.
- A failed embedding or LLM request does not append an assistant message.
- Retrieved recipe context is included in the LLM request, while embeddings and
  internal retrieval details are not exposed as the user-facing answer.

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

## Client foundation

The Bitesize reference client should be verifiable independently from the
Python test suite. Its package checks should include a successful lint run and a
production build from `clients/bitesize/`. API integration tests belong to the
shared API feature once its response contract is approved; the client should
not require a live OpenAI or Postgres service merely to build.
