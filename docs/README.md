# Crumbs technical documentation

Start here when changing ingestion, storage, or retrieval. These documents record
the current implementation and the decisions agreed for the MVP. Future features
are proposals, not claims that those features already exist.

- [Project specification](../SPEC.md): goals, routing, and current decisions.
- [Product requirements](product-requirements.md): durable query behavior and guardrails.
- [Architecture](architecture.md): query components, data flow, and persistence.
- [Bitesize chat API specification](superpowers/specs/004-bitesize-chat-api.md): the implemented shared `POST /api/chat` request, response, and retrieval behavior.
- [Question-intent routing specification](superpowers/specs/005-question-intent-routing.md): future routing between discovery, recipe follow-up, and related-recipe workflows.
- [Recipe content arrays specification](superpowers/specs/007-recipe-content-arrays.md): canonical ordered JSONB sections returned directly by the recipe detail API.
- [Recipe content arrays implementation plan](superpowers/plans/007-recipe-content-arrays.md): query impact, fresh-schema setup, verification, and documentation changes.
- [Bitesize integration next steps](bitesize-next-steps.md): staged recipe API and chat panel work.
- [Testing](testing.md): retrieval and conversation verification strategy.
- [Bitesize client foundation specification](superpowers/specs/002-bitesize-client-foundation.md): implemented client boundary.
- [Recipe API specification](superpowers/specs/003-recipe-api-design.md): browsing and detail API, including direct section responses.

- [Corpus format](recipe-corpus-format.md): curated Markdown fields, units, and sections.
- [Corpus template](recipe-corpus-template.md): starting point for a recipe file.
- [Taxonomy](recipe-taxonomy.yaml): approved categories and tags.
- [Importing and loading recipes](importing-recipes.md): commands, configuration, and failure behavior.
- [Technical decisions](technical-decisions.md): schema, identity, embeddings, and code organization.
- [Future features](future-features.md): recommendation behavior, creator ingestion, model extensions, evaluation, and migration considerations.

The executable database definition is [schema.sql](../src/app/db/schema.sql).
When a decision changes, update the relevant document alongside the code and
tests. Keep implemented behavior separate from planned behavior, and record the
reason for changes that affect identity, data compatibility, or retrieval.
