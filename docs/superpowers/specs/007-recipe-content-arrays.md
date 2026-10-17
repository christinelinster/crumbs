# 007: Recipe content arrays

**Status:** Implemented
**Parent project:** [@SPEC.md](../../../SPEC.md)

## Objective

Store each recipe's ordered ingredients and instructions with the recipe while
preserving group headings, existing retrieval behavior, and the public recipe
API's direct section representation.

## Scope

- Persist ingredients and instructions in separate ordered section arrays on
  each recipe. Every section has `kind`, `name`, and `items`; `name` is `null`
  for ungrouped sections.
- Normalize the raw Markdown parser representation into sections before
  embedding and persistence. Sections are the canonical application and
  database representation.
- Preserve section order and repeated group names. Represent ungrouped items
  distinctly from items under an explicitly unnamed heading.
- Assume existing databases already use the JSONB schema or can be safely
  recreated. Do not implement an automatic upgrade from the former child-table
  schema.
- Return `ingredient_sections` and `instruction_sections` directly in the recipe
  detail API, with the same `kind`, `name`, and `items` representation stored in
  JSONB. Do not also return flat arrays or group boundary fields. Keep RAG query
  context in section form.
- Keep the current whole-recipe embedding and similarity search behavior.
- Keep Markdown as the reviewed import source. The importer parses its structure
  but does not add a duplicate semantic validation pass for list contents or
  group positions.

## Schema File Scope

Assume the PostgreSQL database already exists. `src/app/db/schema.sql` supplies
the database-local SQL needed to create the recipe tables and related schema
objects inside that database. Setup targets a fresh database or one already
using this schema; `CREATE TABLE IF NOT EXISTS` does not upgrade legacy tables.

## Out of Scope

- Changing other recipe API fields, chat responses, or CLI output. Ingredient
  and instruction fields in the recipe detail API change to direct sections.
- Searching or updating individual ingredient or instruction rows.
- Adding exact ingredient filters, normalization, lexical ranking, chunks, or
  additional embeddings.
- Deleting database recipes when their Markdown source file is missing.
- Changing the current behavior of regenerating embeddings for each Markdown
  file present on every loader run.
- Upgrading an existing legacy child-table database from `setup_database()`.

## Dependencies

- None. This feature changes the existing recipe persistence capability.

## Required Context

- [@docs/decisions/004-recipe-content-arrays.md](../../decisions/004-recipe-content-arrays.md)
- [@docs/technical-decisions.md#current-storage-model](../../technical-decisions.md#current-storage-model)
- [@docs/recipe-corpus-format.md](../../recipe-corpus-format.md)
- [@docs/importing-recipes.md#loading-recipes-into-postgres](../../importing-recipes.md#loading-recipes-into-postgres)
- [@docs/superpowers/specs/003-recipe-api-design.md#http-contract](003-recipe-api-design.md#http-contract)
- [@docs/superpowers/specs/001-recipe-grounded-query.md](001-recipe-grounded-query.md)

## Authoritative Requirement References

- [@docs/superpowers/specs/003-recipe-api-design.md#http-contract](003-recipe-api-design.md#http-contract)

## Acceptance Criteria

- Section and item order survives persistence and the detail API, including
  repeated group names, ungrouped items, and explicitly unnamed groups.
  Repository reads and the recipe detail API both retain canonical sections.
- Fresh database setup creates the JSONB fields and no ingredient or instruction
  child tables. Rerunning setup against that schema is safe.
- Setup against a legacy child-table schema does not attempt an upgrade; the
  database must already use the target schema or be recreated.
- `schema.sql` supplies the database-local DDL for creating the new schema in
  an already-created database.
- The recipe detail HTTP response exposes `ingredient_sections` and
  `instruction_sections` with `kind`, `name`, and ordered `items`, and omits the
  previous flat arrays and group boundary fields. Other API fields and
  similarity scoring, threshold, ordering, and limit are unchanged.
- The loader normalizes parser fields to sections before generating the
  embedding and writing JSONB. No stored section omits `name`.
- Query prompts and the recipe detail API receive canonical sections. Bitesize
  renders sections directly and flattens items locally only for ingredient
  highlighting.
- The loader continues to embed and upsert every Markdown file present and
  leaves database recipes without a Markdown file untouched.
- No active query or write path depends on `recipe_ingredients`,
  `recipe_steps`, or the unused `normalized_name` index.

## Verification Expectations

- Verify the canonical schema in a transaction-local namespace, including the
  JSONB array checks, absence of child tables, and a safe rerun. Roll back the
  schema check so it leaves persistent application tables unchanged.
- Use unit tests to cover database writes, section normalization, direct recipe
  detail responses, similarity projections, and unchanged non-content API data.
- Verify the loader's whole-corpus re-embedding behavior and that absent
  Markdown files do not trigger database deletion.
- Run the focused Python tests and the complete Python test suite after
  implementation.

## Related ADRs

- [@docs/decisions/004-recipe-content-arrays.md](../../decisions/004-recipe-content-arrays.md)

## Documentation Fallback

Read [@SPEC.md](../../../SPEC.md) as the fallback routing source whenever
additional project documentation is required.
