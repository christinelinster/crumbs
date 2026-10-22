"""Thin SDK integration with no live calls or local persistence."""
import json
import unittest
from unittest.mock import Mock, patch

import httpx
from zep_cloud import Zep
from zep_cloud.types import GraphContextResponse

from app.paths import RECIPES_DIR
from app.zep.client import get_zep
from app.zep.ingest import ingest_recipe
from app.zep.retrieval import get_graph_context


class ZepTests(unittest.TestCase):
    def test_native_context_preserves_block_and_all_selected_scopes(self):
        requests = []
        context = '<Relevant Facts>Steamed Eggs use eggs.</Relevant Facts>'

        def respond(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={
                'context': context, 'truncated': True,
                'results': {
                    'edges': [{'fact': 'Eggs use eggs.', 'episode_uuids': ['source-1']}],
                    'nodes': [{'name': 'Eggs', 'episode_uuids': ['source-1'], 'episode_uuids_truncated': False}],
                    'observations': [{'summary': 'Breakfast recipes'}],
                    'thread_summaries': [{'summary': 'Cooking breakfast'}],
                },
            })

        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            result = get_graph_context(
                Zep(api_key='test-key', httpx_client=http), 'graph-1', 'eggs',
            )

        self.assertEqual(requests[0]['query'], 'eggs')
        self.assertEqual(requests[0]['max_characters'], 5000)
        self.assertTrue(requests[0]['include_results'])
        self.assertNotIn('reranker', requests[0])
        self.assertEqual(requests[0]['filters'], {
            'date_filters': {'any_of': [{'all_of': [
                {'field': 'invalid_at', 'operator': 'is_null'},
                {'field': 'expired_at', 'operator': 'is_null'},
            ]}]},
        })
        self.assertTrue(result.truncated)
        self.assertEqual(result.context, context)
        self.assertEqual(result.results.edges[0].episode_uuids, ['source-1'])
        for scope in ('edges', 'nodes', 'observations', 'thread_summaries'):
            self.assertTrue(getattr(result.results, scope))

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
        self.assertEqual(kwargs['metadata']['recipe_slug'], 'curry')
        self.assertEqual(len(kwargs['metadata']['recipe_revision']), 64)
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
        from app.rag.tools import _execute_zep_search_tool
        with patch('app.rag.tools.get_zep'), patch(
            'app.rag.tools.get_graph_context', return_value=GraphContextResponse(context='', truncated=False),
        ):
            result = _execute_zep_search_tool({'input': 'eggs'})
        self.assertEqual(result['context'], '')
        self.assertEqual(result['recipes'], [])

    def test_recipe_sources_can_come_from_nodes_and_observations_without_edges(self):
        from types import SimpleNamespace
        from app.rag.tools import _execute_zep_search_tool
        recipe = {
            'slug': 'eggs', 'title': 'Eggs',
            'ingredients': ['2 eggs'], 'instructions': ['Steam the eggs.'],
        }
        for scope in ('nodes', 'observations'):
            with self.subTest(scope=scope):
                client = Mock()
                client.graph.get_context.return_value = GraphContextResponse(
                    context='<Relevant Facts>Eggs.</Relevant Facts>',
                    results={scope: [{
                        'episode_uuids': ['episode-1', 'episode-1'],
                        **({'episode_uuids_truncated': False} if scope == 'nodes' else {}),
                    }]},
                )
                client.graph.episode.list.return_value = []
                client.graph.episode.get.return_value = SimpleNamespace(
                    content=json.dumps(recipe), metadata={}, document_id='eggs',
                )
                with patch('app.rag.tools.get_zep', return_value=client):
                    result = _execute_zep_search_tool({'input': 'eggs'})
                self.assertEqual(result['recipes'][0]['ingredients'], ['2 eggs'])
                client.graph.episode.get.assert_called_once()

    def test_source_recipes_preserve_complete_episode_content_and_stable_identities(self):
        from types import SimpleNamespace
        from app.zep.retrieval import get_source_recipes
        client = Mock()
        client.graph.episode.list.return_value = []
        curry = {
            'title': 'Curry', 'slug': 'curry', 'servings': 2,
            'ingredients': ['1 onion', 'tofu'], 'instructions': ['Cook the onion, then add tofu.'],
            'ingredient_groups': [{'start': 1, 'name': 'Sauce'}],
        }
        pasta = {'title': 'Pasta', 'ingredients': ['pasta'], 'instructions': ['Boil pasta.']}
        client.graph.episode.get.side_effect = [
            SimpleNamespace(metadata={'recipe_slug': 'curry'}, document_id='revision-1', content=json.dumps(curry)),
            SimpleNamespace(metadata=None, document_id='pasta', content=json.dumps(pasta)),
            SimpleNamespace(metadata=None, document_id='curry', content=json.dumps(curry)),
        ]
        recipes = get_source_recipes(client, 'graph-1', ['episode-1', 'episode-2', 'episode-1', 'episode-3'])
        self.assertEqual([recipe['slug'] for recipe in recipes], ['curry', 'pasta'])
        for key, value in curry.items():
            self.assertEqual(recipes[0][key], value)
        self.assertEqual(recipes[1]['ingredients'], ['pasta'])
        self.assertEqual(client.graph.episode.get.call_count, 3)

    def test_current_source_recipe_uses_newest_episode_for_a_slug(self):
        from types import SimpleNamespace
        from app.zep.retrieval import get_source_recipes
        client = Mock()
        old = {
            'slug': 'curry', 'title': 'Curry', 'ingredients': ['onion'],
            'instructions': ['Cook onion.'],
        }
        current = {
            'slug': 'curry', 'title': 'Curry', 'ingredients': ['tofu'],
            'instructions': ['Cook tofu.'],
        }
        old_episode = SimpleNamespace(
            metadata={'recipe_slug': 'curry', 'recipe_revision': 'old'},
            document_id='curry', content=json.dumps(old), created_at='2026-10-01T00:00:00Z',
        )
        client.graph.episode.get.return_value = old_episode
        client.graph.episode.list.return_value = [
            SimpleNamespace(
                metadata={'recipe_slug': 'curry', 'recipe_revision': 'new'},
                document_id='curry', content=json.dumps(current),
                created_at='2026-10-10T00:00:00Z',
            ),
            old_episode,
        ]

        recipes = get_source_recipes(client, 'graph-1', ['old-episode'])

        self.assertEqual(recipes[0]['ingredients'], ['tofu'])
        self.assertEqual(recipes[0]['instructions'], ['Cook tofu.'])
        kwargs = client.graph.episode.list.call_args.kwargs
        self.assertEqual(kwargs['order_by'], 'created_at')
        self.assertEqual(kwargs['order'], 'desc')

    def test_history_search_keeps_superseded_episode_and_disables_current_filter(self):
        from types import SimpleNamespace
        from app.zep.retrieval import get_source_recipes
        client = Mock()
        old = SimpleNamespace(
            metadata={'recipe_slug': 'curry', 'recipe_revision': 'old'},
            document_id='curry', content=json.dumps({
                'slug': 'curry', 'title': 'Curry', 'ingredients': ['onion'],
                'instructions': ['Cook onion.'],
            }), created_at='2026-10-01T00:00:00Z', uuid_='old-episode',
        )
        new = SimpleNamespace(
            metadata={'recipe_slug': 'curry', 'recipe_revision': 'new'},
            document_id='curry', content=json.dumps({
                'slug': 'curry', 'title': 'Curry', 'ingredients': ['tofu'],
                'instructions': ['Cook tofu.'],
            }), created_at='2026-10-10T00:00:00Z', uuid_='new-episode',
        )
        client.graph.episode.get.side_effect = [old, new]

        recipes = get_source_recipes(
            client,
            'graph-1',
            ['old-episode', 'new-episode'],
            include_history=True,
        )

        self.assertEqual([recipe['ingredients'] for recipe in recipes], [['onion'], ['tofu']])
        client.graph.episode.list.assert_not_called()

        get_graph_context(client, 'graph-1', 'curry changes', include_history=True)
        search_kwargs = client.graph.get_context.call_args.kwargs
        self.assertNotIn('filters', search_kwargs)

    def test_invalid_or_unrelated_source_episodes_are_not_recipe_candidates(self):
        from types import SimpleNamespace
        from app.zep.retrieval import get_source_recipes
        client = Mock()
        client.graph.episode.get.side_effect = [
            SimpleNamespace(metadata=None, document_id='not-json', content='I like onions'),
            SimpleNamespace(metadata=None, document_id='array', content='[]'),
            SimpleNamespace(metadata=None, document_id='message', content='{"fact": "User likes onions"}'),
            SimpleNamespace(metadata=None, document_id='mismatch', content=json.dumps({
                'slug': 'other', 'title': 'Other', 'ingredients': ['garlic'], 'instructions': ['Cook.'],
            })),
        ]
        self.assertEqual(get_source_recipes(client, 'graph-1', [
            'not-json', 'array', 'message', 'mismatch',
        ]), [])

    def test_episode_recipe_with_null_categories_can_supply_a_valid_card(self):
        from types import SimpleNamespace
        from app.api import RecipeCard
        from app.rag.tools import build_recipe_cards
        from app.zep.retrieval import get_source_recipes
        client = Mock()
        client.graph.episode.list.return_value = []
        client.graph.episode.get.return_value = SimpleNamespace(
            metadata=None, document_id='eggs', content=json.dumps({
                'title': 'Eggs', 'category': None, 'tags': None,
                'ingredients': ['2 eggs'], 'instructions': ['Cook the eggs.'],
            }),
        )
        recipes = get_source_recipes(client, 'graph-1', ['episode-1'])
        card = build_recipe_cards(recipes)[0]
        self.assertEqual(card['category'], [])
        self.assertEqual(card['tags'], [])
        self.assertEqual(RecipeCard.model_validate(card).slug, 'eggs')



if __name__ == '__main__':
    unittest.main()
