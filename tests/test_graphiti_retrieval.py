"""Graphiti chat search uses shared recipe evidence without parsing Markdown."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api import create_app
from app.rag.tools import get_recipe_tools
from tests.test_chat_api import (
    FakeChatClient, FakeClient, FakeConnection, FakePool,
    provider_response, provider_tool_call,
)


class GraphitiRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_keeps_user_facts_separate_from_recipe_facts_and_sources(self):
        from app.graphiti.retrieval import search_recipes

        client = AsyncMock()
        client.search.side_effect = [
            [SimpleNamespace(name='CONTAINS', fact='Pasta contains tomatoes.', episodes=['source-1'])],
            [SimpleNamespace(name='AVOIDS', fact='Christine avoids cilantro.', episodes=['user-source-1'])],
        ]
        markdown = '---\nslug: tomato-pasta\n---\n# Pasta\n- tomatoes\n- garlic\n'
        sources = [
            SimpleNamespace(uuid='source-1', name='tomato-pasta', content=markdown, group_id='shared_recipes'),
            SimpleNamespace(uuid='user-source-1', name='Conversation turn', content='Personal data', group_id='user_christine'),
        ]
        with patch('app.graphiti.retrieval.get_graphiti', return_value=client), patch(
            'app.graphiti.retrieval.EpisodicNode.get_by_uuids',
            new_callable=AsyncMock, return_value=sources,
        ) as fetch:
            result = await search_recipes('Which recipes use garlic?')

        self.assertEqual(len(client.search.await_args_list), 2)
        recipe_search, user_search = client.search.await_args_list
        self.assertEqual(recipe_search.kwargs['query'], 'Which recipes use garlic?')
        self.assertEqual(user_search.kwargs['query'], recipe_search.kwargs['query'])
        self.assertEqual(recipe_search.kwargs['group_ids'], ['shared_recipes'])
        self.assertEqual(user_search.kwargs['group_ids'], ['user_christine'])
        for search in (recipe_search, user_search):
            self.assertEqual(search.kwargs['search_filter'].invalid_at[0][0].comparison_operator.value, 'IS NULL')
            self.assertEqual(search.kwargs['search_filter'].expired_at[0][0].comparison_operator.value, 'IS NULL')
        fetch.assert_awaited_once_with(client.driver, ['source-1'])
        self.assertEqual(result['backend'], 'graphiti')
        self.assertEqual(result['recipe_facts'][0]['fact'], 'Pasta contains tomatoes.')
        self.assertEqual(result['user_facts'][0]['fact'], 'Christine avoids cilantro.')
        self.assertEqual(result['sources'], [{
            'episode_uuid': 'source-1', 'name': 'tomato-pasta', 'markdown': markdown,
        }])
        client.close.assert_awaited_once()
        client.add_episode.assert_not_called()

    async def test_no_matches_skips_source_fetch_and_closes_client(self):
        from app.graphiti.retrieval import search_recipes

        client = AsyncMock()
        client.search.return_value = []
        with patch('app.graphiti.retrieval.get_graphiti', return_value=client), patch(
            'app.graphiti.retrieval.EpisodicNode.get_by_uuids', new_callable=AsyncMock,
        ) as fetch:
            result = await search_recipes('Unknown recipe')
        self.assertEqual(result, {
            'backend': 'graphiti', 'recipe_facts': [], 'user_facts': [], 'sources': [],
        })
        fetch.assert_not_called()
        client.close.assert_awaited_once()

    async def test_failed_search_still_closes_client(self):
        from app.graphiti.retrieval import search_recipes

        client = AsyncMock()
        client.search.side_effect = RuntimeError('unavailable')
        with patch('app.graphiti.retrieval.get_graphiti', return_value=client):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                await search_recipes('Dinner?')
        client.close.assert_awaited_once()


class GraphitiChatTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.zep_capture_dir = Path(directory.name) / 'zep'
        self.graphiti_capture_dir = Path(directory.name) / 'graphiti'
        for capture in (
            patch('app.chat_capture.CAPTURE_DIR', self.zep_capture_dir),
            patch('app.chat_capture.GRAPHITI_CAPTURE_DIR', self.graphiti_capture_dir),
        ):
            capture.start()
            self.addCleanup(capture.stop)
        self.pool = FakePool(FakeConnection())
        self.chat = FakeChatClient(responses=[
            provider_response(tool_calls=[provider_tool_call('get_recipes', {'input': 'Dinner with garlic?'})]),
            provider_response(content='Tomato pasta uses garlic.'),
        ])
        self.client = FakeClient(chat=self.chat)

    def test_graphiti_schema_has_only_native_search_tool(self):
        tools = get_recipe_tools('graphiti')
        self.assertEqual([tool['name'] for tool in tools], ['get_recipes'])
        self.assertEqual(set(tools[0]['parameters']['properties']), {'input'})

    def test_chat_question_reaches_graphiti_and_evidence_reaches_answer_model(self):
        evidence = {
            'backend': 'graphiti',
            'recipe_facts': [{'name': 'USES', 'fact': 'Tomato pasta uses garlic.', 'episode_uuids': ['source-1']}],
            'user_facts': [{'name': 'AVOIDS', 'fact': 'Christine avoids cilantro.', 'episode_uuids': ['user-source-1']}],
            'sources': [{'episode_uuid': 'source-1', 'name': 'tomato-pasta', 'markdown': '# Tomato pasta\n- garlic'}],
        }
        with patch('app.rag.query.OpenAI', return_value=self.client), patch(
            'app.rag.tools.search_graphiti_recipes', new_callable=AsyncMock, return_value=evidence,
        ) as search, TestClient(create_app(self.pool)) as http:
            response = http.post('/api/chat', json={
                'question': 'Dinner with garlic?', 'retrieval_backend': 'graphiti',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['answer'], 'Tomato pasta uses garlic.')
        self.assertEqual(response.json()['recipe_cards'], [])
        search.assert_awaited_once_with('Dinner with garlic?')
        outputs = [item for item in self.chat.calls[1]['input']
                   if isinstance(item, dict) and item.get('type') == 'function_call_output']
        self.assertEqual(json.loads(outputs[0]['output']), evidence)
        self.assertIn('Graphiti', self.chat.calls[1]['instructions'])
        self.assertNotIn('recommend only recipes from this list', self.chat.calls[1]['instructions'])
        trace = next(self.graphiti_capture_dir.glob('*.md')).read_text()
        self.assertIn('## 2. Graphiti retrieval', trace)
        self.assertIn('Dinner with garlic?', trace)
        self.assertIn('Christine avoids cilantro.', trace)
        self.assertIn('## 3. Final LLM input', trace)
        self.assertIn('Tomato pasta uses garlic.', trace)
        self.assertIn('## 4. Final output', trace)
        self.assertIn('Tomato pasta uses garlic.', trace)
        self.assertEqual(list(self.zep_capture_dir.glob('*.md')) if self.zep_capture_dir.exists() else [], [])
        self.assertEqual(self.pool.connection_count, 0)
        self.assertEqual(self.client.embedding.calls, [])

    def test_graphiti_failure_returns_generic_error_without_vector_fallback(self):
        with patch('app.rag.query.OpenAI', return_value=self.client), patch(
            'app.rag.tools.search_graphiti_recipes', new_callable=AsyncMock,
            side_effect=Exception('private connection details'),
        ), TestClient(create_app(self.pool)) as http:
            response = http.post('/api/chat', json={
                'question': 'Dinner with garlic?', 'retrieval_backend': 'graphiti',
            })
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private', response.text)
        self.assertEqual(self.pool.connection_count, 0)
        self.assertEqual(self.client.embedding.calls, [])
