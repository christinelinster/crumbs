# Bitesize + Crumbs: next steps

Status: proposed integration, not yet implemented.

The reference frontend is planned at `clients/bitesize/` inside the Crumbs
repository. This client boundary is separate from the future shared API and
from Crumbs' Python RAG core.

## Goal and starting point

Use Bitesize (`../bitesize`) for recipe browsing and an integrated Crumbs chat
panel. Crumbs owns recipe data and RAG. The panel opens beside recipes on desktop
and fills the screen on mobile.

Crumbs currently loads Markdown into Postgres and supports CLI chat. Bitesize has
a React frontend and an Express recipe endpoint with a different recipe schema.
Use the Crumbs database as the shared recipe source; do not run Bitesize's existing
seed script against it.

## Implementation order

1. **Connect browsing and recipe details.** Add FastAPI endpoints
   `GET /api/recipes` for summaries and `GET /api/recipes/{slug}` for full recipes.
   Adapt Bitesize's `name` and `time` fields to `title` and `total_time_minutes`,
   support category arrays, and display missing values as unknown. Use persisted
   slugs for recipe links. Render stored ingredients and instructions directly,
   preserving complete cooking details. Retire the Express recipe backend once
   its remaining responsibilities have been checked and migrated.

2. **Expose chat.** Add `POST /api/chat` accepting `question`, prior `history`,
   and optional `recipe_slug`. Return `answer` and recipe references containing
   `slug` and `title`. Refactor the query service to return references from the
   same retrieval used for the answer, while keeping the CLI working. Build links
   from database slugs and label references "Recipes used for this answer".
   Retrieval remains application-controlled, defaulting to three recipes.

3. **Add the chat panel.** Keep history in React memory above the page routes.
   Navigation and closing the panel preserve it; refresh and "New chat" clear it.
   Send previous messages with each new question. Append successful exchanges,
   show retryable errors without duplicate messages, and link recipe references
   to detail pages. Keep API credentials and system instructions on the backend;
   never share a global conversation history between visitors.

4. **Add recipe-specific context.** Show "Discussing: [recipe title]" on recipe
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

## Open decision and next session

LLM function calling, question-intent routing, and creator-agnostic/multi-creator
support are future considerations, outside this integration. Recipe-specific
context in stage 4 uses the explicit page selection; it does not require an
intent router. See [future considerations](future-features.md#deferred-llm-tools-and-intent-routing).

Decide whether substitutions may use clearly labeled general cooking knowledge.
The current prompt permits only facts supported by retrieved recipes, which can
prevent answers about substitutions absent from the source.

Start next session by inspecting both repositories and agreeing on the recipe API
response fields, then implement stage 1. Later stages can follow independently.
The frontend/API integration and live end-to-end behavior have not been verified.
