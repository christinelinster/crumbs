"""Check relocated commands without connecting to external services."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ModulePathsTests(unittest.TestCase):
    def test_commands_resolve_checkout_paths_from_another_directory(self):
        project_root = Path(__file__).resolve().parents[1]
        code = '''
import asyncio
from pathlib import Path
import runpy
import sys
from unittest.mock import AsyncMock, patch

from app.paths import PROJECT_ROOT, RECIPES_DIR, RECIPE_URLS_PATH, RECIPE_TEMPLATE_PATH, SCHEMA_PATH
assert PROJECT_ROOT == Path(sys.argv[1])
assert RECIPES_DIR.is_dir()
assert RECIPE_URLS_PATH.is_file()
assert RECIPE_TEMPLATE_PATH.is_file()
assert SCHEMA_PATH.is_file()

# Execute the setup entry point with a mocked connection pool.
with patch('app.db.connection.pool') as pool:
    runpy.run_module('app.db.setup', run_name='__main__')
    conn = pool.connection.return_value.__enter__.return_value
    conn.execute.assert_called_once_with(SCHEMA_PATH.read_text(encoding='utf-8'))

from app.ingestion import import_recipes, load_embeddings
from app.db.recipes import save_recipe
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
