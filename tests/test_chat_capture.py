"""Each chat gets a separate, ordered Markdown capture without changing its response."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import create_app
from app.chat_capture import capture_chat, current_capture
from tests.test_chat_api import FakeClient, FakeConnection, FakePool


class ChatCaptureTests(unittest.TestCase):
    def test_direct_requests_write_separate_ordered_files_with_exact_model_input(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            'app.chat_capture.CAPTURE_DIR', Path(directory),
        ), patch('app.rag.query.OpenAI', return_value=FakeClient()):
            with TestClient(create_app(FakePool(FakeConnection()))) as http:
                for question in ('How do I boil water?', 'How do I steam rice?'):
                    response = http.post('/api/chat', json={'question': question})
                    self.assertEqual(response.status_code, 200)
            captures = [path.read_text() for path in Path(directory).glob('*.md')]

        self.assertEqual(len(captures), 2)
        for content in captures:
            headings = [content.index(f'## {number}.') for number in range(1, 5)]
            self.assertEqual(headings, sorted(headings))
            self.assertIn('No Zep context retrieved.', content)
            self.assertIn('"tool_choice": "auto"', content)
            self.assertIn('"instructions":', content)
            self.assertIn('Try the steamed eggs.', content)
        self.assertTrue(any('How do I boil water?' in content for content in captures))
        self.assertTrue(any('How do I steam rice?' in content for content in captures))

    def test_failed_request_keeps_query_and_attempted_model_input(self):
        client = FakeClient()
        client.chat_client.error = RuntimeError('provider unavailable')
        with tempfile.TemporaryDirectory() as directory, patch(
            'app.chat_capture.CAPTURE_DIR', Path(directory),
        ), patch('app.rag.query.OpenAI', return_value=client):
            with TestClient(create_app(FakePool(FakeConnection()))) as http:
                response = http.post('/api/chat', json={'question': 'Dinner?'})
            content = next(Path(directory).glob('*.md')).read_text()

        self.assertEqual(response.status_code, 503)
        self.assertIn('Dinner?', content)
        self.assertIn('"instructions":', content)
        self.assertIn('RuntimeError', content)
        self.assertIn('No model output returned.', content)

    def test_concurrent_captures_do_not_mix_requests_and_preserve_markdown(self):
        barrier = Barrier(2)

        def capture(question):
            with capture_chat(question) as record:
                barrier.wait(timeout=5)
                self.assertIs(current_capture.get(), record)
                record['model_input'] = {'input': question}
            self.assertIsNone(current_capture.get())

        questions = ['first ``` recipe', 'second recipe']
        with tempfile.TemporaryDirectory() as directory, patch(
            'app.chat_capture.CAPTURE_DIR', Path(directory),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(capture, questions))
            contents = [path.read_text() for path in Path(directory).glob('*.md')]

        self.assertEqual(len(contents), 2)
        self.assertTrue(any('````text\nfirst ``` recipe\n````' in content for content in contents))
        for content in contents:
            self.assertEqual(sum(question in content for question in questions), 1)

    def test_file_write_failure_preserves_the_chat_response_and_logs_error(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / 'file'
            blocker.write_text('existing file')
            with patch('app.chat_capture.CAPTURE_DIR', blocker / 'requests'), patch(
                'app.rag.query.OpenAI', return_value=FakeClient(),
            ), self.assertLogs('app.chat_capture', level='ERROR') as logs:
                with TestClient(create_app(FakePool(FakeConnection()))) as http:
                    response = http.post('/api/chat', json={'question': 'Dinner?'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('Could not write chat capture', '\n'.join(logs.output))
