# Importing recipes

Add one HTTP(S) recipe URL per line to `data/import/recipe-urls.txt`.
Blank lines and lines beginning with `#` are ignored.

From the project root, run:

```bash
poetry run python scripts/import_recipes.py
```

The importer fetches Recipe JSON-LD, normalizes it, and checks that the title,
ingredients, and instructions contain usable text. It writes one Markdown file
per recipe to `data/recipes/`, using the fields and sections in
`docs/recipe-corpus-template.md`. IDs and URL slugs are left for database insertion;
the title-based Markdown filename is only a local filename.

Nutrition and other unavailable metadata remain empty. `source_label` defaults to
the source hostname. Categories and tags are saved as YAML lists.

Existing `source_url` values and repeated URLs are skipped, ignoring URL fragments.
Other URL aliases are not assumed to identify the same recipe. Existing filenames
are never overwritten: a title collision is reported as a failure for manual
review. Malformed existing frontmatter stops the import before fetching, since
it prevents a reliable duplicate check.

Each URL gets an imported, skipped, or failed message, followed by totals.
Individual failures do not stop subsequent URLs. Exit status is `1` if any import
fails and `0` otherwise. Failed URLs can be retried by running the command again;
successfully imported URLs will be skipped. Review generated Markdown before
chunking and database insertion.

The script always uses the paths above, resolved relative to the project root.
No command-line arguments are needed.
