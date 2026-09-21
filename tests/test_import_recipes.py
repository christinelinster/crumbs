import contextlib
from hashlib import sha256
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from app.ingestion.import_recipes import import_recipes

from app.paths import RECIPE_TEMPLATE_PATH
RECIPE = {
    'name': 'Soup: "quick"',
    'description': 'A warm soup. Another sentence.',
    'recipeCuisine': 'Italian',
    'recipeIngredient': ['2 cups water', '1 carrot'],
    'recipeInstructions': [{'@type': 'HowToStep', 'text': 'Simmer.\nServe.'}],
    'totalTime': 'PT30M',
}


class ImportRecipesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp)
        self.urls = self.root / 'urls.txt'
        self.output = self.root / 'recipes'
        self.template = RECIPE_TEMPLATE_PATH

    async def run_import(self, urls, responses):
        self.urls.write_text(urls, encoding='utf-8')
        log = io.StringIO()
        with patch('app.ingestion.import_recipes.get_recipe_json_ld', side_effect=responses):
            with contextlib.redirect_stdout(log):
                result = await import_recipes(self.urls, self.output, self.template)
        return result, log.getvalue()

    async def test_writes_template_and_skips_duplicates_on_rerun(self):
        urls = '# recipes\n\nhttps://example.com/soup\nhttps://example.com/soup#recipe\n'
        result, log = await self.run_import(urls, [RECIPE])
        self.assertEqual(result, 0)
        files = list(self.output.glob('*.md'))
        self.assertEqual(len(files), 1)
        original = files[0].read_bytes()
        text = original.decode()
        metadata = yaml.safe_load(text.split('---', 2)[1])
        self.assertEqual(metadata['title'], 'Soup: "quick"')
        self.assertEqual(metadata['slug'], 'soup-quick')
        self.assertEqual(metadata['total_time_minutes'], 30)
        self.assertEqual(metadata['description'], 'A warm soup.')
        self.assertEqual(metadata['cuisine'], 'Italian')
        self.assertEqual(metadata['source_url'], 'https://example.com/soup')
        self.assertNotIn('id', metadata)
        self.assertIn('- 2 cups water', text)
        self.assertIn('1. Simmer. Serve.', text)
        self.assertIn('## Notes', text)
        result, log = await self.run_import(urls, [])
        self.assertEqual(result, 0)
        self.assertEqual(files[0].read_bytes(), original)
        self.assertIn('skipped', log)

    async def test_increments_slugs_for_distinct_recipes_with_same_title(self):
        urls = '\n'.join(
            'https://example.com/{}'.format(name)
            for name in ('one', 'two', 'three')
        )
        responses = [
            dict(RECIPE, name='Chicken Soup', description=f'Chicken soup version {i}.')
            for i in range(1, 4)
        ]

        result, _ = await self.run_import(urls, responses)

        self.assertEqual(result, 0)
        metadata_by_file = {
            path.name: yaml.safe_load(path.read_text(encoding='utf-8').split('---', 2)[1])
            for path in self.output.glob('*.md')
        }
        self.assertEqual(
            set(metadata_by_file),
            {'chicken-soup.md', 'chicken-soup-2.md', 'chicken-soup-3.md'},
        )
        self.assertEqual(
            {metadata['slug'] for metadata in metadata_by_file.values()},
            {'chicken-soup', 'chicken-soup-2', 'chicken-soup-3'},
        )

    async def test_uses_unique_filenames_for_titles_without_slugs(self):
        urls = 'https://example.com/one\nhttps://example.com/two\n'
        responses = [
            dict(RECIPE, name='!!!'),
            dict(RECIPE, name='???'),
        ]
        result, _ = await self.run_import(urls, responses)

        self.assertEqual(result, 0)
        expected = {
            f'recipe-{sha256(url.encode()).hexdigest()[:8]}.md'
            for url in urls.splitlines()
        }
        self.assertEqual(
            {path.name for path in self.output.glob('*.md')},
            expected,
        )

    async def test_failures_do_not_prevent_later_imports(self):
        urls = '\n'.join(f'https://example.com/{i}' for i in range(5))
        result, log = await self.run_import(urls, [
            RuntimeError('network failed'), None,
            dict(RECIPE, recipeIngredient='2 cups water'),
            dict(RECIPE, recipeInstructions=[]), RECIPE,
        ])
        self.assertEqual(result, 1)
        self.assertEqual(len(list(self.output.glob('*.md'))), 1)
        self.assertIn('4 failed', log)

    async def test_existing_filename_gets_incremented_slug_without_overwrite(self):
        self.output.mkdir()
        existing = self.output / 'soup-quick.md'
        existing.write_text(
            '---\ntitle: Hand written\nslug: soup-quick\n---\nPersonal recipe\n'
        )
        original = existing.read_bytes()
        result, log = await self.run_import('https://example.com/soup', [RECIPE])
        self.assertEqual(result, 0)
        self.assertEqual(existing.read_bytes(), original)
        imported = self.output / 'soup-quick-2.md'
        self.assertTrue(imported.exists())
        self.assertIn('soup-quick-2.md', log)

    async def test_rejects_existing_recipe_without_persisted_slug(self):
        self.output.mkdir()
        (self.output / 'hand-written.md').write_text(
            '---\ntitle: Hand written\n---\nPersonal recipe\n'
        )
        result, log = await self.run_import('https://example.com/soup', [RECIPE])
        self.assertEqual(result, 1)
        self.assertIn('slug must be nonempty text', log)

    async def test_rejects_blank_title_and_invalid_urls(self):
        result, log = await self.run_import(
            'file:///tmp/recipe\nhttps://example.com/blank', [dict(RECIPE, name=' ')]
        )
        self.assertEqual(result, 1)
        self.assertEqual(list(self.output.glob('*.md')), [])
        self.assertIn('2 failed', log)

    async def test_malformed_existing_frontmatter_stops_import(self):
        self.output.mkdir()
        (self.output / 'broken.md').write_text('---\nsource_url: [broken\n---\n')
        result, log = await self.run_import('https://example.com/soup', [])
        self.assertEqual(result, 1)
        self.assertIn('broken.md', log)
        self.assertEqual(len(list(self.output.glob('*.md'))), 1)
