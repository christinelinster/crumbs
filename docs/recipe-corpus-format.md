# Recipe corpus format

Store one recipe per Markdown file in `data/recipes/`, using the
[template](recipe-corpus-template.md). Filenames are local identifiers; the
persisted `slug` is the recipe identity used by the loader.

## Curated frontmatter

| Field | Curated format | Meaning |
| --- | --- | --- |
| `title` | Nonempty string | Recipe name |
| `slug` | Nonempty unique string | Stable recipe identity; preserve it when the title changes |
| `description` | Nonempty string | One informative sentence |
| `category` | List of strings | Zero or more approved categories |
| `tags` | List of strings | Zero or more approved tags |
| `cuisine` | String or null | One cuisine, for example `Chinese`, not `American/Chinese` |
| `total_time_minutes` | Nonnegative integer or null | Total recipe time in minutes |
| `servings` | Positive integer or null | Whole serving count |
| `source_label` | String or null | Publisher name, for example `The Woks of Life` |
| `source_url` | Full HTTP(S) URL or null | Original recipe page, unique when present; not the primary recipe identity |
| `calories` | Nonnegative number or null | kcal |
| `protein`, `carbs`, `fat` | Nonnegative numbers or null | Grams |

The template includes title, slug, description, category, tags, total time, and
servings as core fields; unknown time and servings may be null. Cuisine,
attribution, nutrition, and source URL are optional. The slug is created once
when a recipe is created and identifies the same recipe on later loads. If a
title-based slug is already used during URL import, the importer adds the next
available numeric suffix, such as `-2`, and persists the result.

Category and tag values must come from [recipe-taxonomy.yaml](recipe-taxonomy.yaml).
Several values are allowed. Use `[]` for an empty YAML list. The loader trusts
these human-reviewed values and does not enforce the taxonomy.

Use numeric YAML values, without unit strings or quotes:

```yaml
servings: 4
calories: 300
protein: 24.5
category:
  - lunch
  - dinner
tags:
  - soup
  - chicken
source_label: The Woks of Life
```

Quotes around publisher names are optional for ordinary YAML strings. Use null
for unavailable metadata instead of inventing zero values. Ambiguous source
yields such as `4-6 servings` or `12 buns` need review before entering a numeric
serving count; the current schema has no separate yield or servings-text field.

The raw web importer may preserve source strings such as `350 kcal`, mixed
cuisines, arbitrary tags, and hostname source labels. Its output requires review
and conversion to this curated format before loading into Postgres. It persists a
slug in generated Markdown but does not automatically apply the other editorial
rules in this document.

## Markdown sections

- `## Ingredients`: required nonempty bullet list, one ingredient per item.
- `## Instructions`: required nonempty numbered list, one step per item.
- `## Notes`: optional recipe notes.

Within Ingredients and Instructions, optional `### Source group name` headings
start a new group. Preserve source names and item order; do not infer groups.
Keep step numbering continuous across groups. Files without headings remain valid.
For a source group that has no name, use `### <!-- unnamed group -->`; the loader
stores a group section with a null name. Items before the first heading remain
ungrouped. Empty groups are rejected. Group headings do not change frontmatter
types or values.

The parser first reads headings as raw ordered group boundaries. The loader
normalizes that parser representation into canonical sections, then stores each
content list as JSONB on the recipe row, for example:

```json
[
  {"kind": "ungrouped", "name": null, "items": ["2 eggs"]},
  {"kind": "group", "name": "For the sauce", "items": ["soy sauce", "vinegar"]}
]
```

Every section has `kind`, `name`, and `items`. Ungrouped content uses
`{"kind":"ungrouped","name":null,...}`; a group with no heading name uses
`{"kind":"group","name":null,...}`. Repeated group names remain separate
sections. Embedding text is built from normalized sections and includes named
headings. RAG context and the recipe detail API retain sections directly. The
API exposes `ingredient_sections` and `instruction_sections` with the same
`kind`, `name`, and `items` fields as storage.

Indented continuation lines are supported within ingredients and instructions.
Preserve the ingredient and step order. Plain fractions such as `1/3` and Unicode
fractions such as `½` remain readable text; they are not parsed into quantities.
Use a single pair of parentheses around annotations, for example `(minced)`.

Keep the original ingredient lines for display. Normalized ingredient names are
not part of the current Markdown format or database storage model.

## Nutrition curation

Existing source nutrition was retained during corpus cleanup. Missing values for
seven Made With Lau recipes were manually estimated using ingredient quantities,
declared servings, USDA nutrient references, and assumptions where exact products
or cooking yields were unavailable. These are estimates, not verified nutrition
labels. The affected recipes are borscht soup, century egg pork congee, pan-fried
chicken breast, fried pork belly, egg fried rice, steamed eggs, and chicken stir-fry.

The current schema intentionally has no nutrition-origin or portion-basis fields,
so those distinctions are not recoverable from numeric fields alone. Do not assume
that all imported source nutrition has a verified common serving basis. Automatic
nutrition calculation is not part of the importer or embedding loader.

See [technical decisions](technical-decisions.md) for database mapping and
[the operations guide](importing-recipes.md) for import commands.
