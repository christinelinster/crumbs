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
    def test_vector_requests_do_not_write_zep_or_graphiti_traces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zep_dir = root / 'zep'
            graphiti_dir = root / 'graphiti'
            with patch('app.chat_capture.CAPTURE_DIR', zep_dir), patch(
                'app.chat_capture.GRAPHITI_CAPTURE_DIR', graphiti_dir,
            ), patch('app.rag.query.OpenAI', return_value=FakeClient()):
                with TestClient(create_app(FakePool(FakeConnection()))) as http:
                    for question in ('How do I boil water?', 'How do I steam rice?'):
                        response = http.post('/api/chat', json={'question': question})
                        self.assertEqual(response.status_code, 200)

            self.assertEqual(list(zep_dir.glob('*.md')) if zep_dir.exists() else [], [])
            self.assertEqual(list(graphiti_dir.glob('*.md')) if graphiti_dir.exists() else [], [])

    def test_graphiti_trace_formats_multiline_content_and_keeps_exact_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zep_dir = root / 'zep'
            graphiti_dir = root / 'graphiti'
            with patch('app.chat_capture.CAPTURE_DIR', zep_dir), patch(
                'app.chat_capture.GRAPHITI_CAPTURE_DIR', graphiti_dir,
            ):
                with capture_chat('Which recipes use garlic?') as record:
                    record['graphiti_used'] = True
                    record['graphiti_contexts'].append({
                        'request': {'searches': [
                            {'query': 'Which recipes?\\nUse garlic.', 'group_id': 'shared_recipes'},
                            {'query': 'Which recipes?\\nUse garlic.', 'group_id': 'user_christine'},
                        ]},
                        'results': {'sources': [{'markdown': '# Tomato pasta\n- garlic'}]},
                    })
                    record['model_input'] = {
                        'method': 'responses.parse',
                        'model': 'test-model',
                        'instructions': 'First sentence.\nSecond sentence.',
                        'input': [
                            {'role': 'user', 'content': 'Which recipes?\\nUse garlic.'},
                            {
                                'type': 'function_call_output',
                                'call_id': 'call-1',
                                'output': '{"sources": [{"markdown": "# Tomato pasta\\n- garlic"}]}',
                            },
                        ],
                    }
                    record['model_output'] = {'text': 'Try tomato pasta.\nIt uses garlic.'}

            content = next(graphiti_dir.glob('*.md')).read_text()
            self.assertEqual(list(zep_dir.glob('*.md')) if zep_dir.exists() else [], [])
            self.assertIn('## 2. Graphiti retrieval', content)
            self.assertIn('      Which recipes?\n      Use garlic.', content)
            self.assertIn('      # Tomato pasta\n      - garlic', content)
            self.assertIn('First sentence.\nSecond sentence.', content)
            self.assertIn('Try tomato pasta.\nIt uses garlic.', content)
            self.assertIn('<summary>Exact payload</summary>', content)
            self.assertIn('"instructions": "First sentence.\\nSecond sentence."', content)

    def test_zep_capture_does_not_write_a_graphiti_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zep_dir = root / 'zep'
            graphiti_dir = root / 'graphiti'
            with patch('app.chat_capture.CAPTURE_DIR', zep_dir), patch(
                'app.chat_capture.GRAPHITI_CAPTURE_DIR', graphiti_dir,
            ):
                with capture_chat('Dinner?') as record:
                    record['zep_used'] = True
                    record['model_input'] = {'input': 'Dinner?'}
                    record['model_output'] = {'text': 'A recipe answer.'}

            content = next(zep_dir.glob('*.md')).read_text()
            self.assertIn('## 2. Zep retrieval', content)
            self.assertEqual(list(graphiti_dir.glob('*.md')) if graphiti_dir.exists() else [], [])

    def test_concurrent_captures_do_not_mix_requests_and_preserve_markdown(self):
        barrier = Barrier(2)

        def capture(question):
            with capture_chat(question) as record:
                record['zep_used'] = True
                barrier.wait(timeout=5)
                self.assertIs(current_capture.get(), record)
                record['model_input'] = {'input': question}
            self.assertIsNone(current_capture.get())

        questions = ['first ``` recipe', 'second recipe']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zep_dir = root / 'zep'
            graphiti_dir = root / 'graphiti'
            with patch('app.chat_capture.CAPTURE_DIR', zep_dir), patch(
                'app.chat_capture.GRAPHITI_CAPTURE_DIR', graphiti_dir,
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    list(executor.map(capture, questions))
                contents = [path.read_text() for path in zep_dir.glob('*.md')]

        self.assertEqual(len(contents), 2)
        self.assertEqual(list(graphiti_dir.glob('*.md')) if graphiti_dir.exists() else [], [])
        self.assertTrue(any('````text\nfirst ``` recipe\n````' in content for content in contents))
        for content in contents:
            self.assertEqual(sum(question in content for question in questions), 1)

    def test_file_write_failure_is_logged_without_raising_from_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / 'file'
            blocker.write_text('existing file')
            with patch('app.chat_capture.CAPTURE_DIR', blocker / 'requests'), patch(
                'app.chat_capture.GRAPHITI_CAPTURE_DIR', blocker / 'graphiti-requests',
            ), self.assertLogs('app.chat_capture', level='ERROR') as logs:
                with capture_chat('Dinner?') as record:
                    record['zep_used'] = True
            self.assertIn('Could not write zep chat capture', '\n'.join(logs.output))
