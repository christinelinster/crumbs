# Crumbs technical documentation

Start here when changing ingestion, storage, or retrieval. These documents record
the current implementation and the decisions agreed for the MVP. Future features
are proposals, not claims that those features already exist.

- [Project specification](../SPEC.md): goals, routing, and open questions.
- [Product requirements](product-requirements.md): durable query behavior and guardrails.
- [Architecture](architecture.md): query components, data flow, and persistence.
- [Bitesize integration next steps](bitesize-next-steps.md): staged recipe API and chat panel work for the next session.
- [Testing](testing.md): retrieval and conversation verification strategy.
- [Feature specifications](superpowers/specs/002-bitesize-client-foundation.md): independently reviewable project outcomes.

- [Corpus format](recipe-corpus-format.md): curated Markdown fields, units, and sections.
- [Corpus template](recipe-corpus-template.md): starting point for a recipe file.
- [Taxonomy](recipe-taxonomy.yaml): approved categories and tags.
- [Importing and loading recipes](importing-recipes.md): commands, configuration, and failure behavior.
- [Technical decisions](technical-decisions.md): schema, identity, embeddings, and code organization.
- [Future features](future-features.md): recommendation behavior, creator ingestion, admin editing, and migration considerations.

The executable database definition is [schema.sql](../src/app/db/schema.sql).
When a decision changes, update the relevant document alongside the code and
tests. Keep implemented behavior separate from planned behavior, and record the
reason for changes that affect identity, data compatibility, or retrieval.
