"""Conversation capture is opt-in, scoped to the test user, and failure tolerant."""

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from graphiti_core.nodes import EpisodeType

from app.api import create_app
from app.rag.query import QueryResult
from tests.test_chat_api import FakeConnection, FakePool


THREAD_UUID = '00f14dc0-7cd5-4936-9663-2e253d75a016'


class GraphitiMemoryApiTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.zep_capture_dir = Path(directory.name) / 'zep'
        self.graphiti_capture_dir = Path(directory.name) / 'graphiti'
        patches = [
            patch('app.chat_capture.CAPTURE_DIR', self.zep_capture_dir),
            patch('app.chat_capture.GRAPHITI_CAPTURE_DIR', self.graphiti_capture_dir),
            patch('app.api.save_graphiti_conversation', new_callable=AsyncMock),
            patch('app.api.process_query_result', return_value=QueryResult('Try tofu.', [], [])),
            patch('app.zep.memory.get_zep'),
        ]
        self.mocks = [item.start() for item in patches]
        for item in patches:
            self.addCleanup(item.stop)
        self.save = self.mocks[2]
        self.http = TestClient(create_app(FakePool(FakeConnection())))

    def test_enabled_turn_saves_only_current_exchange_and_reuses_conversation(self):
        response = self.http.post('/api/chat', json={
            'question': 'I avoid onions.', 'graphiti_memory': True,
            'history': [{'role': 'user', 'content': 'Earlier disabled turn.'}],
        })
        self.assertEqual(response.status_code, 200)
        thread = response.json()['graphiti_thread_uuid']
        UUID(thread)
        self.assertEqual(response.json()['graphiti_memory_status'], 'saved')
        self.save.assert_awaited_once_with('I avoid onions.', 'Try tofu.', thread)
        self.mocks[4].assert_not_called()
        self.assertEqual(
            list(self.graphiti_capture_dir.glob('*.md')) if self.graphiti_capture_dir.exists() else [],
            [],
        )
        self.assertEqual(
            list(self.zep_capture_dir.glob('*.md')) if self.zep_capture_dir.exists() else [],
            [],
        )
        self.save.reset_mock()
        response = self.http.post('/api/chat', json={
            'question': 'More ideas?', 'graphiti_memory': True,
            'graphiti_thread_uuid': thread,
        })
        self.assertEqual(response.json()['graphiti_thread_uuid'], thread)
        self.save.assert_awaited_once_with('More ideas?', 'Try tofu.', thread)

    def test_disabled_capture_makes_no_graphiti_call(self):
        response = self.http.post('/api/chat', json={
            'question': 'Dinner?', 'graphiti_memory': False,
            'graphiti_thread_uuid': THREAD_UUID,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['graphiti_memory_status'])
        self.assertIsNone(response.json()['graphiti_thread_uuid'])
        self.save.assert_not_called()

    def test_save_failure_preserves_answer_and_conversation_without_provider_details(self):
        self.save.side_effect = RuntimeError('private provider details')
        response = self.http.post('/api/chat', json={
            'question': 'Dinner?', 'graphiti_memory': True,
            'graphiti_thread_uuid': THREAD_UUID,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['answer'], 'Try tofu.')
        self.assertEqual(response.json()['graphiti_memory_status'], 'error')
        self.assertEqual(response.json()['graphiti_thread_uuid'], THREAD_UUID)
        self.assertNotIn('private', response.text)


class GraphitiConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_conversation_has_user_namespace_and_thread_saga_and_closes_client(self):
        from app.graphiti.memory import save_conversation

        client = AsyncMock()
        client.nodes.saga.get_by_group_ids.return_value = [SimpleNamespace(
            name=f'thread_{THREAD_UUID}', uuid='saga-uuid',
        )]
        with patch('app.graphiti.memory.get_graphiti', return_value=client):
            result = await save_conversation('No onions.', 'Try tofu.', THREAD_UUID)
        arguments = client.add_episode.call_args.kwargs
        self.assertEqual(arguments['group_id'], 'user_christine')
        self.assertEqual(arguments['saga'], f'thread_{THREAD_UUID}')
        self.assertEqual(arguments['source'], EpisodeType.message)
        self.assertEqual(arguments['episode_body'], 'Christine: No onions.\nAssistant: Try tofu.')
        self.assertIn('only', arguments['custom_extraction_instructions'])
        client.nodes.saga.get_by_group_ids.assert_awaited_once_with(['user_christine'])
        client.summarize_saga.assert_awaited_once_with('saga-uuid')
        self.assertIs(result, client.add_episode.return_value)
        client.close.assert_awaited_once()

    async def test_client_is_closed_on_extraction_failure(self):
        from app.graphiti.memory import save_conversation

        client = AsyncMock()
        client.add_episode.side_effect = RuntimeError('unavailable')
        with patch('app.graphiti.memory.get_graphiti', return_value=client):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                await save_conversation('No onions.', 'Try tofu.', THREAD_UUID)
        client.close.assert_awaited_once()
