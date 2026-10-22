"""Check relocated commands without connecting to external services."""

from pathlib import Path
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest


class ModulePathsTests(unittest.TestCase):
    def test_schema_renderer_substitutes_the_shared_embedding_dimension(self):
        from app.db.setup import render_schema
        from app.paths import SCHEMA_PATH
        from app.settings import EMBEDDING_DIMENSIONS

        rendered = render_schema(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertIn(f"VECTOR({EMBEDDING_DIMENSIONS})", rendered)
        self.assertNotIn("__EMBEDDING_DIMENSIONS__", rendered)

    def test_shared_runtime_settings_are_defined(self):
        self.assertIsNotNone(importlib.util.find_spec("app.settings"))

        from app import settings
        from app.db import recipes
        from app.rag import embeddings, tools

        self.assertEqual(settings.DEFAULT_RECIPE_LIMIT, 3)
        self.assertEqual(settings.MAX_RECIPE_LIMIT, 10)
        self.assertEqual(settings.DEFAULT_SIMILARITY_THRESHOLD, 0.3)
        self.assertEqual(
            recipes.DEFAULT_SIMILARITY_THRESHOLD,
            settings.DEFAULT_SIMILARITY_THRESHOLD,
        )
        self.assertEqual(tools.DEFAULT_RECIPE_LIMIT, settings.DEFAULT_RECIPE_LIMIT)
        self.assertEqual(embeddings.EMBEDDING_MODEL, settings.EMBEDDING_MODEL)
        self.assertGreater(settings.EMBEDDING_DIMENSIONS, 0)
        self.assertTrue(settings.OPENAI_CHAT_MODEL)

    def test_embedding_dimension_rejects_invalid_environment_values(self):
        self.assertIsNotNone(importlib.util.find_spec("app.settings"))
        project_root = Path(__file__).resolve().parents[1]
        for raw in ("invalid", "0", "-1"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                environment = dict(os.environ)
                environment["PYTHONPATH"] = str(project_root / "src")
                environment["EMBEDDING_DIMENSIONS"] = raw
                result = subprocess.run(
                    [sys.executable, "-c", "import app.settings"],
                    cwd=directory,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "EMBEDDING_DIMENSIONS must be a positive integer",
                    result.stderr,
                )

    def test_embedding_dimension_uses_environment_override_or_default(self):
        project_root = Path(__file__).resolve().parents[1]
        for raw, expected in ((None, 1536), ("3072", 3072)):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                environment = dict(os.environ)
                environment["PYTHONPATH"] = str(project_root / "src")
                environment["PYTHON_DOTENV_DISABLED"] = "1"
                environment.pop("EMBEDDING_DIMENSIONS", None)
                if raw is not None:
                    environment["EMBEDDING_DIMENSIONS"] = raw
                result = subprocess.run(
                    [sys.executable, "-c",
                     "from app.settings import EMBEDDING_DIMENSIONS; "
                     "print(EMBEDDING_DIMENSIONS)"],
                    cwd=directory,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(int(result.stdout.strip()), expected)

    def test_commands_resolve_checkout_paths_from_another_directory(self):
        project_root = Path(__file__).resolve().parents[1]
        code = '''
import asyncio
from contextlib import contextmanager
from pathlib import Path
import runpy
import sys
from unittest.mock import AsyncMock, patch

from app import paths
from app import settings
from app.paths import PROJECT_ROOT, RECIPES_DIR, RECIPE_URLS_PATH, RECIPE_TEMPLATE_PATH, SCHEMA_PATH
assert PROJECT_ROOT == Path(sys.argv[1])
assert RECIPES_DIR.is_dir()
assert RECIPE_URLS_PATH.is_file()
assert RECIPE_TEMPLATE_PATH.is_file()
assert SCHEMA_PATH.is_file()
schema_template = SCHEMA_PATH.read_text(encoding='utf-8')
assert "__EMBEDDING_DIMENSIONS__" in schema_template
schema_sql = " ".join(schema_template.split())
assert "ingredient_sections JSONB NOT NULL DEFAULT '[]'::jsonb" in schema_sql
assert "instruction_sections JSONB NOT NULL DEFAULT '[]'::jsonb" in schema_sql
assert "CHECK (jsonb_typeof(ingredient_sections) = 'array')" in schema_sql
assert "CHECK (jsonb_typeof(instruction_sections) = 'array')" in schema_sql
assert 'CREATE TABLE IF NOT EXISTS recipe_ingredients' not in schema_sql
assert 'CREATE TABLE IF NOT EXISTS recipe_steps' not in schema_sql
assert 'recipe_ingredients_normalized_name_idx' not in schema_sql
assert not hasattr(paths, 'RECIPE_CONTENT_ARRAYS_MIGRATION_PATH')

# Execute the setup entry point with a mocked connection pool.
state = {'in_transaction': False, 'executed': []}
class FakeTransaction:
    def __enter__(self):
        state['in_transaction'] = True
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        state['in_transaction'] = False
        return False
class FakeConnection:
    def transaction(self):
        return FakeTransaction()
    def execute(self, sql):
        state['executed'].append((sql, state['in_transaction']))
class FakePool:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        return False
    @contextmanager
    def connection(self):
        yield FakeConnection()
pool = FakePool()
with patch('app.db.connection.pool', pool):
    runpy.run_module('app.db.setup', run_name='__main__')
expected_schema_sql = schema_template.replace(
    "__EMBEDDING_DIMENSIONS__",
    str(settings.EMBEDDING_DIMENSIONS),
)
assert state['executed'] == [
    (expected_schema_sql, True),
]

from app.ingestion import import_recipes, load_embeddings
from app.rag import embeddings, tools
from app.db.recipes import save_recipe
assert embeddings.EMBEDDING_MODEL == settings.EMBEDDING_MODEL
assert tools.DEFAULT_RECIPE_LIMIT == settings.DEFAULT_RECIPE_LIMIT
assert load_embeddings.save_recipe is save_recipe
assert load_embeddings.load_embeddings.__defaults__ == (RECIPES_DIR,)
paths = sorted(RECIPES_DIR.glob('*.md'))
assert paths
for path in paths:
    load_embeddings.parse_recipe_file(path)
with patch.object(import_recipes, 'import_recipes', new_callable=AsyncMock) as importer:
    importer.return_value = 0
    assert import_recipes.main() == 0
    importer.assert_awaited_once_with(RECIPE_URLS_PATH, RECIPES_DIR, RECIPE_TEMPLATE_PATH)
'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, '-c', code, str(project_root)],
                cwd=directory, capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
