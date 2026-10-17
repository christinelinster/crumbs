"""Thin SDK integration with no live calls or local persistence."""
import json
import unittest
from unittest.mock import MagicMock, Mock, patch

from app.paths import RECIPES_DIR
from app.zep.client import get_zep
from app.zep.ingest import ingest_recipe
from app.zep.retrieval import search_recipes


class ZepTests(unittest.TestCase):
    def test_client_uses_configured_key(self):
        with patch('app.zep.client.settings.ZEP_API_KEY', 'test-key'), patch(
            'app.zep.client.Zep',
        ) as sdk:
            self.assertIs(get_zep(), sdk.return_value)
        sdk.assert_called_once_with(api_key='test-key')

    def test_recipe_preserves_content_and_groups_episodes_by_slug(self):
        client = Mock()
        recipe = {'slug': 'curry', 'ingredients': ['½ onion', 'tofu']}
        result = ingest_recipe(client, 'graph-1', recipe)
        args, kwargs = client.graph.episode.add.call_args
        self.assertEqual(args, ('graph-1',))
        self.assertEqual(json.loads(kwargs['data']), recipe)
        self.assertEqual(kwargs['document_id'], 'curry')
        self.assertEqual(kwargs['type'], 'json')
        self.assertEqual(kwargs['source_description'], 'Crumbs recipe')
        self.assertIs(result, client.graph.episode.add.return_value)

    def test_reviewed_corpus_recipe_is_json_serializable(self):
        from app.ingestion.load_embeddings import parse_recipe_file
        client = Mock()
        recipe = parse_recipe_file(RECIPES_DIR / 'creamy-tomato-pasta.md')
        ingest_recipe(client, 'graph-1', recipe)
        payload = json.loads(client.graph.episode.add.call_args.kwargs['data'])
        self.assertEqual(payload, recipe)
        self.assertTrue(payload['ingredients'])
        self.assertTrue(payload['instructions'])

    def test_empty_graph_search_returns_empty_evidence(self):
        from types import SimpleNamespace
        from app.rag.query import _execute_zep_search_tool
        with patch('app.rag.query.get_zep'), patch(
            'app.rag.query.search_recipes', return_value=SimpleNamespace(items=None),
        ):
            result = _execute_zep_search_tool({'input': 'eggs'})
        self.assertEqual(result['graph_facts'], [])
        self.assertEqual(result['retrieval_backend'], 'zep')

    def test_source_recipe_slugs_use_metadata_or_document_id_and_skip_duplicates(self):
        from types import SimpleNamespace
        from app.zep.retrieval import get_recipe_slugs
        client = Mock()
        client.graph.episode.get.side_effect = [
            SimpleNamespace(metadata={'recipe_slug': 'curry'}, document_id='revision-1'),
            SimpleNamespace(metadata=None, document_id='pasta'),
        ]
        facts = [{'episode_uuids': ['episode-1', 'episode-2']}, {'episode_uuids': ['episode-1']}]
        self.assertEqual(get_recipe_slugs(client, 'graph-1', facts), ['curry', 'pasta'])
        self.assertEqual(client.graph.episode.get.call_count, 2)

    def test_search_returns_unmodified_sdk_pager(self):
        client = Mock()
        client.graph.search_edges.return_value = MagicMock()
        result = search_recipes(client, 'graph-1', 'tofu')
        client.graph.search_edges.assert_called_once_with('graph-1', query='tofu')
        self.assertIs(result, client.graph.search_edges.return_value)
        result.__iter__.assert_not_called()


if __name__ == '__main__':
    unittest.main()
