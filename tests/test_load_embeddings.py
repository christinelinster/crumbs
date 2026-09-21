from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.embeddings import EMBEDDING_MODEL, generate_embedding
from app.ingestion.load_embeddings import (
    build_embedding_text,
    load_embeddings,
    parse_recipe_file,
)


RECIPE_MARKDOWN = """---
title: Test Chicken Soup
slug: test-chicken-soup
description: A warm chicken soup.
category:
- dinner
tags:
- soup
cuisine: Chinese
total_time_minutes: 45
servings: 4
source_label: Test Kitchen
source_url: https://example.com/test-chicken-soup#recipe
calories: 300
protein: 25
fat: 10
carbs: 30
---

## Ingredients

- 2 chicken breasts
  sliced thinly
- 1 cabbage

## Instructions

1. Simmer the chicken.
   Skim the broth.
2. Add the cabbage.

## Notes

Make ahead and reheat gently.
"""


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.recipe_id = 7

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT id, slug FROM recipes"):
            return FakeResult(None)
        if normalized.startswith("SELECT 1 FROM recipes WHERE slug"):
            return FakeResult(None)
        if normalized.startswith("INSERT INTO recipes"):
            return FakeResult((self.recipe_id,))
        return FakeResult(None)


class ExistingConnection(FakeConnection):
    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT id, slug FROM recipes"):
            self.calls.append((sql, params))
            return FakeResult((7, "existing-slug"))
        return super().execute(sql, params)


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakePool:
    def __init__(self, connection):
        self.connection_value = connection
        self.active = False
        self.connection_count = 0
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    @contextmanager
    def connection(self):
        self.connection_count += 1
        self.active = True
        try:
            yield self.connection_value
        except Exception:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1
        finally:
            self.active = False


class LoadEmbeddingsTests(unittest.TestCase):
    def write_recipe(self, root: Path, text: str = RECIPE_MARKDOWN) -> Path:
        path = root / "test-chicken-soup.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_parses_frontmatter_and_ordered_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = parse_recipe_file(self.write_recipe(Path(directory)))

        self.assertEqual(recipe["title"], "Test Chicken Soup")
        self.assertEqual(recipe["slug"], "test-chicken-soup")
        self.assertEqual(recipe["source_url"], "https://example.com/test-chicken-soup")
        self.assertEqual(
            recipe["ingredients"],
            ["2 chicken breasts sliced thinly", "1 cabbage"],
        )
        self.assertEqual(
            recipe["instructions"],
            ["Simmer the chicken. Skim the broth.", "Add the cabbage."],
        )
        self.assertEqual(recipe["notes"], "Make ahead and reheat gently.")

    def test_accepts_missing_source_url_and_uses_persisted_slug(self):
        text = RECIPE_MARKDOWN.replace(
            "source_url: https://example.com/test-chicken-soup#recipe",
            "source_url:",
        )
        with tempfile.TemporaryDirectory() as directory:
            recipe = parse_recipe_file(self.write_recipe(Path(directory), text))

        self.assertIsNone(recipe["source_url"])
        self.assertEqual(recipe["slug"], "test-chicken-soup")

    def test_validates_blank_source_url_with_shared_text_fields(self):
        text = RECIPE_MARKDOWN.replace(
            "source_url: https://example.com/test-chicken-soup#recipe",
            "source_url: '   '",
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "source_url must be nonempty text"):
                parse_recipe_file(self.write_recipe(Path(directory), text))

    def test_uses_persisted_slug_when_title_changes(self):
        connection = FakeConnection()
        client = Mock()
        client.embeddings.create.return_value.data = [
            Mock(embedding=[0.1] * 1536)
        ]
        text = RECIPE_MARKDOWN.replace(
            "title: Test Chicken Soup",
            "title: Savory Chicken Soup",
        )

        with tempfile.TemporaryDirectory() as directory:
            self.write_recipe(Path(directory), text)
            summary = load_embeddings(
                Path(directory),
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(summary.inserted, 1)
        insert = next(
            params for sql, params in connection.calls
            if "INSERT INTO recipes" in sql
        )
        self.assertEqual(insert["slug"], "test-chicken-soup")

    def test_updates_personal_recipe_by_slug_without_source_url(self):
        connection = ExistingConnection()
        client = Mock()
        client.embeddings.create.return_value.data = [
            Mock(embedding=[0.1] * 1536)
        ]
        text = RECIPE_MARKDOWN.replace(
            "source_url: https://example.com/test-chicken-soup#recipe",
            "source_url:",
        )

        with tempfile.TemporaryDirectory() as directory:
            self.write_recipe(Path(directory), text)
            summary = load_embeddings(
                Path(directory),
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(summary.inserted, 0)
        self.assertEqual(summary.updated, 1)
        self.assertFalse(
            any("WHERE source_url" in sql for sql, _ in connection.calls)
        )

    def test_uses_only_slug_to_find_existing_row(self):
        connection = FakeConnection()
        client = Mock()
        client.embeddings.create.return_value.data = [
            Mock(embedding=[0.1] * 1536)
        ]

        with tempfile.TemporaryDirectory() as directory:
            self.write_recipe(Path(directory))
            summary = load_embeddings(
                Path(directory),
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(summary.inserted, 1)
        self.assertEqual(summary.updated, 0)
        self.assertFalse(
            any("WHERE source_url" in sql for sql, _ in connection.calls)
        )

    def test_rejects_duplicate_slugs_before_embedding(self):
        connection = FakeConnection()
        client = Mock()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_recipe(root)
            duplicate = root / "duplicate.md"
            duplicate.write_text(
                RECIPE_MARKDOWN.replace(
                    "test-chicken-soup#recipe",
                    "another-source",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate slug"):
                load_embeddings(
                    root,
                    client=client,
                    database_pool=FakePool(connection),
                )

        client.embeddings.create.assert_not_called()

    def test_builds_embedding_text_without_source_url(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = parse_recipe_file(self.write_recipe(Path(directory)))

        text = build_embedding_text(recipe)

        self.assertIn("Title: Test Chicken Soup", text)
        self.assertIn("Ingredients:\n- 2 chicken breasts sliced", text)
        self.assertIn("Instructions:\n1. Simmer the chicken. Skim the broth.", text)
        self.assertNotIn("example.com", text)

    def test_load_inserts_recipe_and_ordered_children(self):
        connection = FakeConnection()
        client = Mock()
        client.embeddings.create.return_value.data = [
            Mock(embedding=[0.1] * 1536)
        ]

        with tempfile.TemporaryDirectory() as directory:
            self.write_recipe(Path(directory))
            summary = load_embeddings(
                Path(directory),
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(summary.inserted, 1)
        self.assertEqual(summary.updated, 0)
        self.assertEqual(summary.failed, 0)
        client.embeddings.create.assert_called_once()
        request = client.embeddings.create.call_args.kwargs
        self.assertEqual(request["model"], EMBEDDING_MODEL)
        self.assertTrue(
            any("INSERT INTO recipes" in sql for sql, _ in connection.calls)
        )
        recipe_insert = next(
            params for sql, params in connection.calls
            if "INSERT INTO recipes" in sql
        )
        self.assertEqual(recipe_insert["embedding"], [0.1] * 1536)
        ingredient_calls = [
            params for sql, params in connection.calls
            if "INSERT INTO recipe_ingredients" in sql
        ]
        self.assertEqual(
            [params[1:] for params in ingredient_calls],
            [(1, "2 chicken breasts sliced thinly", None), (2, "1 cabbage", None)],
        )

    def test_generates_embedding_before_leasing_connection(self):
        connection = FakeConnection()
        database_pool = FakePool(connection)
        client = Mock()

        def embed(**kwargs):
            self.assertEqual(database_pool.connection_count, 0)
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * 1536)])

        client.embeddings.create.side_effect = embed
        with tempfile.TemporaryDirectory() as directory:
            self.write_recipe(Path(directory))
            summary = load_embeddings(
                Path(directory),
                client=client,
                database_pool=database_pool,
            )

        self.assertEqual(summary.inserted, 1)
        self.assertEqual(database_pool.connection_count, 1)

    def test_load_updates_existing_recipe_without_changing_slug(self):
        connection = ExistingConnection()
        client = Mock()
        client.embeddings.create.return_value.data = [
            Mock(embedding=[0.1] * 1536)
        ]

        with tempfile.TemporaryDirectory() as directory:
            self.write_recipe(Path(directory))
            summary = load_embeddings(
                Path(directory),
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(summary.inserted, 0)
        self.assertEqual(summary.updated, 1)
        upserts = [
            (sql, params) for sql, params in connection.calls if "INSERT INTO recipes" in sql
        ]
        self.assertEqual(len(upserts), 1)
        sql, params = upserts[0]
        self.assertEqual(params["slug"], "existing-slug")
        update_clause = sql.split("DO UPDATE SET")[1]
        self.assertNotIn("slug =", update_clause)
        self.assertNotIn("id =", update_clause)
        self.assertIn("ON CONFLICT (slug)", sql)

    def test_embedding_failure_does_not_write_recipe(self):
        connection = ExistingConnection()
        client = Mock()
        client.embeddings.create.side_effect = RuntimeError("API unavailable")

        with tempfile.TemporaryDirectory() as directory:
            self.write_recipe(Path(directory))
            summary = load_embeddings(
                Path(directory),
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(summary.failed, 1)
        self.assertFalse(any("UPDATE recipes" in sql for sql, _ in connection.calls))
        self.assertFalse(any("DELETE FROM" in sql for sql, _ in connection.calls))

    def test_rejects_duplicate_source_urls_before_embedding(self):
        connection = FakeConnection()
        client = Mock()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_recipe(root)
            duplicate = root / "duplicate.md"
            duplicate.write_text(
                RECIPE_MARKDOWN.replace(
                    "slug: test-chicken-soup",
                    "slug: duplicate-source",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate source_url"):
                load_embeddings(
                    root,
                    client=client,
                    database_pool=FakePool(connection),
                )

        client.embeddings.create.assert_not_called()

    def test_requires_persisted_slug(self):
        text = RECIPE_MARKDOWN.replace("slug: test-chicken-soup\n", "")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "slug must be nonempty text"):
                parse_recipe_file(self.write_recipe(Path(directory), text))

    def test_parses_all_current_corpus_files(self):
        from app.paths import RECIPES_DIR

        paths = sorted(RECIPES_DIR.glob("*.md"))
        recipes = [parse_recipe_file(path) for path in paths]

        self.assertEqual(len(recipes), 39)
        self.assertTrue(all(recipe["ingredients"] for recipe in recipes))
        self.assertTrue(all(recipe["instructions"] for recipe in recipes))

    def test_requires_exactly_one_embedding(self):
        client = Mock()
        for data in ([], [SimpleNamespace(embedding=[0.1]), SimpleNamespace(embedding=[0.2])]):
            with self.subTest(result_count=len(data)):
                client.embeddings.create.return_value.data = data
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    generate_embedding(client, 'Chicken soup')

    def test_returns_embedding_from_sdk(self):
        client = Mock()
        vector = [0.1] * 1536
        client.embeddings.create.return_value.data = [SimpleNamespace(embedding=vector)]
        self.assertEqual(generate_embedding(client, 'Chicken soup'), vector)

    def test_rejects_invalid_metadata_before_api_call(self):
        for old, new in (
            ('servings: 4', 'servings: 0'),
            ('servings: 4', 'servings: 2.5'),
            ('fat: 10', 'fat: .nan'),
            ('calories: 300', 'calories: -1'),
        ):
            with self.subTest(value=new), tempfile.TemporaryDirectory() as directory:
                path = self.write_recipe(Path(directory), RECIPE_MARKDOWN.replace(old, new))
                with self.assertRaises(ValueError):
                    parse_recipe_file(path)

    def test_releases_connection_during_api_call_and_rolls_back_failed_recipe(self):
        connection = FakeConnection()
        database_pool = FakePool(connection)
        execute = connection.execute

        def fail_first_child(sql, params=None):
            if 'INSERT INTO recipe_steps' in sql and database_pool.rollbacks == 0:
                raise RuntimeError('step write failed')
            return execute(sql, params)

        connection.execute = fail_first_child
        client = Mock()

        def embed(**kwargs):
            self.assertFalse(database_pool.active)
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * 1536)])

        client.embeddings.create.side_effect = embed
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_recipe(root)
            (root / 'second.md').write_text(
                RECIPE_MARKDOWN.replace(
                    'slug: test-chicken-soup', 'slug: second'
                ).replace('test-chicken-soup#recipe', 'second'),
                encoding='utf-8',
            )
            summary = load_embeddings(root, client=client, database_pool=database_pool)

        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.inserted, 1)
        self.assertEqual(database_pool.rollbacks, 1)
        self.assertEqual(database_pool.commits, 1)  # Successful recipe only.


if __name__ == "__main__":
    unittest.main()
