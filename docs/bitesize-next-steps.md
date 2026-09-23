# Bitesize + Crumbs: next steps

Status: client foundation, recipe API, and chat API implemented; chat panel next.

The reference frontend lives at `clients/bitesize/` inside the Crumbs
repository. This client boundary is separate from the shared API service and
from Crumbs' Python RAG core.

The initial client foundation now exists at `clients/bitesize/`. It contains
only the React/Vite frontend, installs from its own lockfile, keeps relative
`/api` requests, and can be linted and production-built independently. The
recipe API now supplies the list and detail data, while local development still
requires the API service to be running.

## Goal and starting point

Use Bitesize (`../bitesize`) for recipe browsing and an integrated Crumbs chat
panel. Crumbs owns recipe data and RAG. The panel opens beside recipes on desktop
and fills the screen on mobile.

Crumbs currently loads Markdown into Postgres and supports CLI chat. Bitesize has
a React frontend and an Express recipe endpoint with a different recipe schema.
Use the Crumbs database as the shared recipe source; do not run Bitesize's existing
seed script against it.

## Implementation order

1. [x] **Complete - connect browsing and recipe details.** Add FastAPI endpoints
   `GET /api/recipes` for lightweight home-page card fields and
   `GET /api/recipes/{slug}` for full recipes. Adapt Bitesize's `name` and
   `time` fields to `title` and `total_time_minutes`, display category, tags,
   nutrition, and missing values safely, and use persisted slugs for recipe
   links. Render stored ingredients and instructions directly, preserving
   complete cooking details. Retire the Express recipe backend once its
   remaining responsibilities have been checked and migrated.

2. [x] **Complete - expose chat.** Add `POST /api/chat` accepting `question`, prior `history`,
   and optional `recipe_slug`. Return `answer` and `recipe_cards` containing
   the same condensed fields used by home-page cards plus numeric
   `similarity_score` for general similarity-search questions. Derive the cards
   from the same full-recipe retrieval used for the answer, while keeping the CLI
   working. For recipe-specific questions, resolve the supplied slug directly,
   skip embedding and similarity search, and return an empty card array because
   the user is already on that recipe's detail page. Build links
   from database slugs and label references "Recipes used for this answer".
   Retrieval remains application-controlled, defaulting to three recipes with
   caller-controlled overrides and an optional application threshold.

   The implementation plan is [Bitesize Chat API Implementation Plan](superpowers/plans/004-bitesize-chat-api.md).

3. [ ] **Next - add the chat panel.** Keep history in React memory above the page routes.
   Navigation and closing the panel preserve it; refresh and "New chat" clear it.
   Send previous messages with each new question. Append successful exchanges,
   show retryable errors without duplicate messages, and link recipe references
   to detail pages. Keep API credentials and system instructions on the backend;
   never share a global conversation history between visitors.

4. [ ] **Add recipe-specific context.** Show "Discussing: [recipe title]" on recipe
   pages and send the current slug. Fetch that recipe directly and include its
   complete content rather than relying on similarity search for vague follow-ups.
   Allow clearing the selection for general recommendations. Invalid slugs produce
   an explicit error rather than an answer about another recipe.

## Verification checkpoints

- Browsing and detail pages use the same corpus as chat; stored steps stay intact.
- Chat references link to the correct recipe and omit embeddings from API output.
- Conversations remain separate; navigation preserves history and refresh clears it.
- A Sukiyaki follow-up about sauce uses the selected recipe's exact ingredients,
  quantities, and preparation steps. Failed or truncated answers are not saved.

## Deferred decisions and next stage

LLM function calling, question-intent routing, structured outputs, MCP, Phoenix
evaluation, and creator-agnostic/multi-creator support are future
considerations, outside this integration. Recipe-specific context in stage 4
uses the explicit page selection; it does not require an intent router. See
[future considerations](future-features.md#deferred-model-interfaces-orchestration-and-evaluation).

Decide whether substitutions may use clearly labeled general cooking knowledge.
The current prompt permits only facts supported by retrieved recipes, which can
prevent answers about substitutions absent from the source.

The next implementation stage is the React chat panel. The recipe and chat API
contracts are implemented and documented, so the panel can reuse the same slug,
summary-card, and full-detail boundaries without coupling the client to the
Bitesize Express schema. Browser-to-Postgres behavior still requires a local
Postgres database, loaded corpus, and running API service.
