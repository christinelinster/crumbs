# 003: Crumbs recipe API for Bitesize browsing

**Status:** Implemented\
**Parent project:** [@SPEC.md](../../../SPEC.md)

## Objective

Expose the curated Crumbs recipe corpus through a small HTTP boundary so the
Bitesize reference client can browse recipe summaries and render complete
recipe-detail pages without importing Python modules or connecting to Postgres.

## Scope

- Add a FastAPI application with `GET /api/recipes` and
  `GET /api/recipes/{slug}`.
- Return the canonical Crumbs field names rather than Bitesize's former
  `name`, `id`, and `time` fields.
- Return full stored ingredient and instruction sections, notes, and metadata for
  a recipe detail response.
- Use persisted slugs as the only client navigation identifier.
- Keep database access behind small read projections and inject the pool for
  endpoint tests.
- Update Bitesize to consume the canonical response and fetch details by slug.

## Out of Scope

- Chat or `POST /api/chat`.
- Authentication, per-user state, corpus isolation, or creator accounts.
- Recipe writes, embedding generation, or changes to the database schema.
- Copying or running Bitesize's former Express backend.
- Replacing the existing CLI query flow.

## HTTP contract

`GET /api/recipes` returns a JSON array of summary objects:

```json
[
  {
    "slug": "sukiyaki-japanese-one-pot-meal",
    "title": "Sukiyaki",
    "category": ["dinner"],
    "tags": ["beef", "one-pot"],
    "total_time_minutes": 40,
    "calories": 751,
    "protein": 37,
    "carbs": 68,
    "fat": 35
  }
]
```

The list response is intentionally limited to the fields needed by Bitesize's
home-page recipe cards. `GET /api/recipes/{slug}` returns the complete recipe
metadata, including description, cuisine, servings, source information, and
notes, plus:

```json
{
  "ingredient_sections": [
    {"kind": "group", "name": "For the sauce", "items": ["2 tablespoons sake"]}
  ],
  "instruction_sections": [
    {"kind": "ungrouped", "name": null, "items": ["Add the sake to a saucepan."]}
  ],
  "notes": "..."
}
```

Each section has `kind`, `name`, and ordered `items`. `kind` is `ungrouped` or
`group`; ungrouped sections use `name: null`, and explicitly unnamed groups
also use `name: null` while retaining `kind: "group"`. Repeated group names
remain separate ordered sections. Ingredient and instruction sections are the
only API representation for those contents; the response does not duplicate
them as flat lists or group boundaries. This is a breaking API change for
clients that consume the previous fields; update clients alongside the server
contract.
The API does not return database IDs or embeddings. A missing slug returns HTTP
404 with a clear error detail.

## Implementation boundary

`create_app(database_pool=pool)` constructs the FastAPI application and keeps
the database pool injectable for tests. The application lifespan opens and
closes the production pool. Database read functions perform the summary and
slug-detail projections; routes do not contain SQL.

The Bitesize client uses `/api/recipes`, stores favourites by slug, displays
the returned title, category, tags, time, and nutrition on home-page cards, and
fetches `/api/recipes/{slug}` for the detail route. It preserves the existing
ingredient highlighting behavior by flattening section items locally when
needed, and renders section headings directly from the returned sections.
Chat recipe cards reuse the same condensed fields and add
`similarity_score`. The LLM receives complete retrieved recipe context, but
that context remains request-scoped and is not added to conversation history.

## Verification

- Unit tests cover summary/detail database projections and missing-slug 404s.
- API tests run through FastAPI's test client with an injected fake pool.
- Bitesize tests, lint, and production build pass from `clients/bitesize/`.
- The existing Crumbs Python suite remains green.
