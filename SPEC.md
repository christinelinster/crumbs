# Project Specification

**Status:** Draft\
**Source design:** Approved, later revised inline\
**Source:** Provided inline in the conversation\
**Approved:** TBD\
**Owner:** TBD\
**Last updated:** 2026-09-24

## Problem & Goals

Crumbs is a reusable recipe retrieval-augmented generation layer. It imports
and stores structured recipes, generates embeddings, and answers questions with
retrieved recipe context. It should be usable by more than one client, with
Bitesize as the first reference client.

The current product direction includes:

- a reusable Python RAG core for ingestion, storage, embedding, retrieval, and
  grounded responses;
- a shared API layer that keeps clients separate from Python internals;
- `clients/bitesize/` as the first reference frontend; and
- a single-corpus, multi-user MVP with a future boundary for independent blog
  corpora.

## Non-Goals

- Natural-language or LLM-controlled selection of the retrieval limit.
- Hybrid lexical and ingredient-aware ranking beyond the current vector search.
- Recipe chunking or multiple embeddings per recipe.
- Creator accounts, tenant administration, authentication, or independent
  corpus permissions in the MVP.
- Copying Bitesize's existing Express backend into Crumbs.
- Background embedding jobs or response streaming.

## Architecture Summary

The repository keeps the RAG implementation and recipe corpus in the Crumbs
core, places the Bitesize reference frontend under `clients/bitesize/`, and
exposes a read-only recipe API between clients and Python internals. The query
service embeds the latest question through a shared helper, passes an
application-selected `limit` to similarity retrieval, loads in-memory
conversation history and structured recipe context, and sends a guarded prompt
to the LLM. Recipe vectors remain in the existing `recipes` table; conversation
messages exist only for the lifetime of the running application process.

## API contract decisions

The shared API keeps client-facing response fields stable even if the Python
RAG implementation changes internally.

The production chat model is configured with `OPENAI_CHAT_MODEL`. A chat request
may carry a `question`, ordered in-memory `history`, an optional `limit`, an
optional `similarity_threshold`, and an optional `recipe_slug` for
recipe-specific context. The application chooses the default retrieval limit,
currently `3`; there is no product-level maximum in this MVP, and callers may
override the default.

The chat response is an object with this shape:

```json
{
  "answer": "...",
  "recipe_cards": [
    {
      "slug": "sukiyaki-japanese-one-pot-meal",
      "title": "Sukiyaki",
      "category": ["dinner"],
      "tags": ["one-pot"],
      "total_time_minutes": 45,
      "calories": 520,
      "protein": 32,
      "carbs": 28,
      "fat": 26,
      "similarity_score": 0.87
    }
  ]
}
```

Recipe cards use the persisted `slug` as the client navigation key. The
category, tags, time, and nutrition fields are shared with the home-page recipe
cards. `similarity_score` is retrieval metadata; the client may render it as
small, light-gray supporting text. Full descriptions, source information,
ingredients, and instructions are loaded from the recipe-detail endpoint or
provided as request-scoped context to the LLM.

Conversation history is an ordered in-memory list of `{role, content}`
messages, where `role` is `user` or `assistant`. It is discarded when the
application process exits. System instructions are application-controlled and
are not part of user-editable history.

## Decision Log

| Decision | Status |
| --- | --- |
| [001: Recipe-grounded query retrieval and conversation persistence](docs/decisions/001-recipe-query-retrieval.md) | Superseded by 002 |
| [002: In-memory conversation history](docs/decisions/002-in-memory-conversation-history.md) | Accepted |
| [003: Bitesize as the first Crumbs client](docs/decisions/003-bitesize-reference-client.md) | Accepted |
| [004: Store ordered recipe content on recipe rows](docs/decisions/004-recipe-content-arrays.md) | Accepted |

## Document Routing

| Document | Purpose | Status |
| --- | --- | --- |
| [Product requirements](docs/product-requirements.md) | Durable query behavior and guardrails | Approved for MVP direction |
| [Architecture](docs/architecture.md) | Components, client boundaries, data flow, and persistence | Approved for MVP direction |
| [Bitesize integration next steps](docs/bitesize-next-steps.md) | Client, API, chat, and recipe-context integration stages | Bitesize MVP stages implemented |
| [Technical decisions](docs/technical-decisions.md) | Schema, identity, embeddings, and code organization | Draft |
| [Testing](docs/testing.md) | Verification strategy for core RAG and clients | Draft |

## Feature Routing

| ID | Feature | Specification | Status | Dependencies |
| --- | --- | --- | --- | --- |
| 001 | Recipe-grounded conversational retrieval | [docs/superpowers/specs/001-recipe-grounded-query.md](docs/superpowers/specs/001-recipe-grounded-query.md) | Draft | None |
| 002 | Bitesize reference client foundation | [docs/superpowers/specs/002-bitesize-client-foundation.md](docs/superpowers/specs/002-bitesize-client-foundation.md) | Implemented | None |
| 003 | Crumbs recipe API for Bitesize browsing | [docs/superpowers/specs/003-recipe-api-design.md](docs/superpowers/specs/003-recipe-api-design.md) | Implemented | 002 |
| 004 | Bitesize chat API | [docs/superpowers/specs/004-bitesize-chat-api.md](docs/superpowers/specs/004-bitesize-chat-api.md) | Implemented | 001, 003 |
| 005 | Question-intent routing | [docs/superpowers/specs/005-question-intent-routing.md](docs/superpowers/specs/005-question-intent-routing.md) | Draft | 004 |
| 007 | Recipe content arrays | [docs/superpowers/specs/007-recipe-content-arrays.md](docs/superpowers/specs/007-recipe-content-arrays.md) | Implemented | None |
| 008 | Graphiti and Neo4j recipe retrieval | [docs/superpowers/specs/008-graphiti-neo4j-recipe-retrieval.md](docs/superpowers/specs/008-graphiti-neo4j-recipe-retrieval.md) | Awaiting approval | 003, 004, 007 |

## Deferred considerations

- The exact similarity-threshold value remains an evaluation setting. The API
  exposes it as an application-controlled parameter so it can be tuned without
  changing the client contract.
- When independent blogs are introduced, corpus isolation still needs a final
  choice between a tenant ID, a separate database, or another boundary.
- LLM function calling, question-intent routing, creator accounts, and
  creator-agnostic corpus support remain future considerations.

## Open Questions

- When a selected-recipe question is ambiguous between a follow-up and a
  related-recipe request, should the router default to exact recipe context,
  ask a clarification question, or use another policy? The Draft routing spec
  currently recommends preserving exact context and avoiding an unsolicited
  similarity search.
