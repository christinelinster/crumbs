# 004: Store ordered recipe content on recipe rows

**Status:** Accepted\
**Date:** 2026-09-24

## Context

The current database stores each ingredient and instruction as an ordered row
in `recipe_ingredients` and `recipe_steps`. The recipe detail and similarity
queries rebuild ordered lists and group metadata from those rows. The
application retrieves whole recipes by vector similarity, and the client uses
the API's ordered lists and group boundaries. No current feature queries
or updates individual ingredient or instruction rows. The curated Markdown
files are manually reviewed and remain the ingestion source.

## Decision

Store ingredients and instructions as ordered JSONB arrays of section objects
on each recipe row. Normalize parser output to sections before embedding and
persistence. Every section contains `kind`, `name`, and ordered `items`; an
ungrouped section has `name: null`, while `kind` distinguishes it from an
explicitly unnamed group. Keep repeated group names as separate ordered
sections. Repository reads, RAG context, and recipe detail API responses retain
sections. The current schema has no ingredient or instruction child tables.
Setup targets fresh databases or databases already using this schema; it does not
automatically upgrade the former child-table schema. Recreate a legacy database if its contents can be
discarded. The database enforces basic required-column and storage-type
constraints; do not add a second semantic validation pass for manually
reviewed list content.

Continue to upsert and re-embed every Markdown recipe present on a loader run.
Do not delete a database recipe just because its Markdown file is absent.

## Consequences

- Recipe writes no longer delete and reinsert one row per ingredient and
  instruction.
- Detail and similarity queries read recipe section arrays directly. The
  recipe detail API returns these sections without duplicate flat arrays or
  group boundaries. This is a breaking response-shape change for clients that
  use the old fields. Similarity ranking, threshold, and result limit are
  unchanged.
- The database no longer provides row-level uniqueness, position, foreign-key,
  or ingredient-name constraints and indexes. The current loader sets
  `normalized_name` to `NULL`, and current application queries do not depend on
  it. Any manually populated `normalized_name` values will be discarded with
  the child table. Future ingredient-level filtering or aggregation will need a
  new storage or indexing decision.
- A Markdown loader run still makes an embedding request for each file present
  and commits recipe updates separately. Schema setup does not invoke the
  loader or make embedding API calls.

## Alternatives considered

- Retain the child tables. They provide per-row constraints and make individual
  ingredient or instruction queries straightforward, but neither capability is
  used by the current product workflow.
