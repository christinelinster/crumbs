"""Thin SDK integration with no live calls or local persistence."""
import json
import unittest
from unittest.mock import patch

import httpx
from zep_cloud import Zep

from app.zep.client import get_zep
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
