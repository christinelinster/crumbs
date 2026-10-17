"""Shared test memory is explicit and does not change answer delivery on save failure."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from zep_cloud.core.api_error import ApiError

from app.api import create_app
from app.rag.query import QueryResult
from tests.test_chat_api import FakeConnection, FakePool

USER_UUID = '671fae5e-4f0b-485c-aa14-d4cdd01106d8'
THREAD_UUID = '00f14dc0-7cd5-4936-9663-2e253d75a016'


class SharedMemoryTests(unittest.TestCase):
    def setUp(self):
        self.zep = Mock()
        self.zep.thread.create.return_value = SimpleNamespace(uuid_=THREAD_UUID)
        self.zep.thread.get.return_value = SimpleNamespace(user_uuid=USER_UUID)
        self.fact = Mock()
        self.fact.model_dump.return_value = {'fact': 'User avoids shrimp.'}
        self.patches = [
            patch('app.api.get_zep', return_value=self.zep),
            patch('app.api.settings.ZEP_USER_UUID', USER_UUID),
            patch('app.api.search_preferences', return_value=SimpleNamespace(items=[self.fact])),
            patch('app.api.process_query_result', return_value=QueryResult('Try tofu.', [], [])),
        ]
        self.mocks = []
        for item in self.patches:
            self.mocks.append(item.start())
            self.addCleanup(item.stop)
        self.http = TestClient(create_app(FakePool(FakeConnection())))

    def test_enabled_turn_creates_thread_reads_preferences_and_saves_only_current_pair(self):
        response = self.http.post('/api/chat', json={
            'question': 'Dinner?', 'retrieval_backend': 'zep', 'shared_memory': True,
            'history': [{'role': 'user', 'content': 'An earlier disabled turn.'}],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['thread_uuid'], THREAD_UUID)
        self.assertEqual(response.json()['memory_status'], 'saved')
        self.zep.thread.create.assert_called_once_with(user_uuid=USER_UUID)
        self.assertEqual(self.mocks[3].call_args.kwargs['memory_context'], [{'fact': 'User avoids shrimp.'}])
        args, kwargs = self.zep.thread.add_messages.call_args
        self.assertEqual(args, (THREAD_UUID,))
        self.assertEqual([(m.role, m.content) for m in kwargs['messages']],
                         [('user', 'Dinner?'), ('assistant', 'Try tofu.')])
        self.assertEqual(kwargs['ignore_roles'], ['assistant'])

    def test_reload_reuses_thread_and_memory_off_makes_no_personal_calls(self):
        response = self.http.post('/api/chat', json={
            'question': 'More ideas?', 'shared_memory': True, 'thread_uuid': THREAD_UUID,
        })
        self.assertEqual(response.status_code, 200)
        self.zep.thread.create.assert_not_called()
        self.zep.thread.get.assert_called_once_with(THREAD_UUID)
        self.zep.reset_mock()
        self.mocks[0].reset_mock()
        self.mocks[2].reset_mock()
        response = self.http.post('/api/chat', json={
            'question': 'Dinner?', 'shared_memory': False, 'thread_uuid': THREAD_UUID,
        })
        self.assertEqual(response.status_code, 200)
        self.mocks[0].assert_not_called()
        self.mocks[2].assert_not_called()
        self.zep.thread.add_messages.assert_not_called()

    def test_save_failure_preserves_answer_and_thread_without_exposing_provider_error(self):
        self.zep.thread.add_messages.side_effect = ApiError(status_code=503, body='secret headers')
        response = self.http.post('/api/chat', json={'question': 'Dinner?', 'shared_memory': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['answer'], 'Try tofu.')
        self.assertEqual(response.json()['thread_uuid'], THREAD_UUID)
        self.assertEqual(response.json()['memory_status'], 'error')
        self.assertNotIn('secret', response.text)

    def test_thread_must_belong_to_configured_shared_test_user(self):
        self.zep.thread.get.return_value = SimpleNamespace(user_uuid='another-user')
        response = self.http.post('/api/chat', json={
            'question': 'Dinner?', 'shared_memory': True, 'thread_uuid': THREAD_UUID,
        })
        self.assertEqual(response.status_code, 404)
        self.mocks[3].assert_not_called()
        self.zep.thread.add_messages.assert_not_called()
