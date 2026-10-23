"""Native backend comparison contracts, with no external services."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from zep_cloud.types import GraphContextResponse


class NativeComparisonTests(unittest.TestCase):
    def test_zep_submits_exact_markdown_and_reports_submission(self):
        from app.zep.ingest import ingest_recipe
        client = Mock()
        client.graph.episode.add.return_value = SimpleNamespace(task_uuid='task-1', episode_uuid='ep-1')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'curry.md'
            markdown = '# Curry 🍛\n\n- ½ onion\n'
            path.write_text(markdown)
            with patch('app.zep.ingest.write_ingestion_report') as report:
                result = ingest_recipe(client, 'recipe-graph', path)
        self.assertEqual(client.graph.episode.add.call_args.args, ('recipe-graph',))
        request = client.graph.episode.add.call_args.kwargs
        self.assertEqual(request['type'], 'text')
        self.assertEqual(request['data'], markdown)
        self.assertEqual(request['document_id'], 'curry')
        self.assertNotIn('metadata', request)
        self.assertIs(result, client.graph.episode.add.return_value)
        self.assertEqual(report.call_args.args[0], 'zep')
        self.assertEqual(report.call_args.args[1]['source_markdown'], markdown)

    def test_zep_searches_both_graphs_and_follows_only_recipe_provenance(self):
        from app.zep.retrieval import search_recipes
        client = Mock()
        client.graph.get_context.side_effect = [
            GraphContextResponse(context='Recipe native context', results={
                'edges': [{'fact': 'Curry contains onion', 'episode_uuids': ['ep-1', 'ep-1']}],
                'nodes': [{'name': 'Curry', 'episode_uuids': ['ep-1'], 'episode_uuids_truncated': False}],
            }),
            GraphContextResponse(context='Christine avoids garlic', results={
                'edges': [{'fact': 'Avoids garlic', 'episode_uuids': ['private-ep']}],
            }),
        ]
        client.graph.episode.get.return_value = SimpleNamespace(content='# Curry\n- onion', document_id='curry', graph_uuid='recipes')
        with patch('app.zep.retrieval.get_zep', return_value=client), patch.multiple(
            'app.zep.retrieval.settings', ZEP_GRAPH_UUID='recipes', ZEP_USER_UUID='user',
        ):
            result = search_recipes('Dinner?')
        calls = client.graph.get_context.call_args_list
        self.assertEqual([c.kwargs['graph_uuid'] for c in calls], ['recipes', 'user'])
        self.assertEqual([c.kwargs['query'] for c in calls], ['Dinner?', 'Dinner?'])
        self.assertEqual(result['recipe_context'], 'Recipe native context')
        self.assertEqual(result['user_context'], 'Christine avoids garlic')
        self.assertEqual(result['sources'][0]['markdown'], '# Curry\n- onion')
        client.graph.episode.get.assert_called_once_with('recipes', 'ep-1')
        client.graph.episode.list.assert_not_called()
        client.thread.add_messages.assert_not_called()

    def test_zep_empty_graphs_return_empty_sources(self):
        from app.zep.retrieval import search_recipes
        client = Mock()
        client.graph.get_context.return_value = GraphContextResponse(context='', results={})
        with patch('app.zep.retrieval.get_zep', return_value=client), patch.multiple(
            'app.zep.retrieval.settings', ZEP_GRAPH_UUID='recipes', ZEP_USER_UUID='user',
        ):
            result = search_recipes('Dinner?')
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['user_context'], '')
        client.graph.episode.get.assert_not_called()

    def test_zep_inspection_records_processing_and_available_summaries(self):
        from app.zep.inspect import inspect_graph
        client = Mock()
        client.graph.node.list.return_value = [SimpleNamespace(name='Christine', summary='Avoids garlic')]
        client.graph.edge.list.return_value = []
        client.graph.episode.list.return_value = []
        client.graph.thread_summary.list.return_value = []
        client.user.get_node.return_value = SimpleNamespace(summary='User baseline')
        with patch('app.zep.inspect.write_ingestion_report') as report:
            result = inspect_graph(client, 'user', user_graph=True)
        self.assertEqual(result['user_summary'], 'User baseline')
        self.assertEqual(result['entities'][0].summary, 'Avoids garlic')
        self.assertFalse(result['sent_to_answer_model'])
        client.graph.get_context.assert_not_called()
        report.assert_called_once()

    def test_graph_tools_have_no_detail_or_revision_arguments(self):
        from app.rag.tools import get_recipe_tools
        for backend in ('zep', 'graphiti'):
            tools = get_recipe_tools(backend)
            self.assertEqual([t['name'] for t in tools], ['get_recipes'])
            self.assertEqual(set(tools[0]['parameters']['properties']), {'input'})

    def test_ingestion_report_is_readable_and_preserves_exact_payload(self):
        from app.chat_capture import write_ingestion_report
        with tempfile.TemporaryDirectory() as directory, patch('app.chat_capture.PROJECT_ROOT', Path(directory)):
            path = write_ingestion_report('zep', {'source_markdown': '# Curry\n- ½ onion', 'entities': []})
            text = path.read_text()
        self.assertIn('# Curry\n', text)
        self.assertIn('No items returned.', text)
        self.assertIn('<summary>Exact payload</summary>', text)

    def test_reports_keep_embedding_vectors_collapsed(self):
        from app.chat_capture import write_ingestion_report
        with tempfile.TemporaryDirectory() as directory, patch('app.chat_capture.PROJECT_ROOT', Path(directory)):
            path = write_ingestion_report('graphiti', {'name_embedding': [0.1, 0.2, 0.3]})
            content = path.read_text()
        self.assertIn('3 values (see exact payload)', content)
        exact = content.split('<summary>Exact payload</summary>')[1]
        self.assertEqual(json.loads(exact.split('```json\n')[1].split('\n```')[0])['name_embedding'], [0.1, 0.2, 0.3])


class GraphitiReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingestion_reports_entities_and_summaries_without_changing_input(self):
        from app.graphiti.ingest import ingest_recipe
        client = AsyncMock()
        client.add_episode.return_value = SimpleNamespace(episode={'uuid': 'ep'}, nodes=[{'name': 'Curry', 'summary': 'A warm dish'}], edges=[])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'curry.md'
            path.write_text('# Curry\n- onion')
            with patch('app.graphiti.ingest.write_ingestion_report') as report:
                await ingest_recipe(client, path)
        self.assertEqual(client.add_episode.call_args.kwargs['episode_body'], '# Curry\n- onion')
        data = report.call_args.args[1]
        self.assertEqual(data['entities'][0]['summary'], 'A warm dish')

class InspectionFailureTests(unittest.TestCase):
    def client(self):
        client = Mock()
        client.graph.node.list.return_value = []
        client.graph.edge.list.return_value = []
        client.graph.episode.list.return_value = []
        client.graph.thread_summary.list.return_value = []
        return client

    def test_unavailable_zep_diagnostics_preserve_storage_report(self):
        from app.zep.inspect import inspect_graph
        from zep_cloud.core.api_error import ApiError
        client = self.client()
        client.graph.episode.get.return_value = SimpleNamespace(processed=False)
        client.graph.episode.get_debug_logs.side_effect = ApiError(status_code=403, body='private')
        with patch('app.zep.inspect.write_ingestion_report') as write:
            result = inspect_graph(client, 'recipes', episode_uuid='ep', debug=True)
        self.assertFalse(result['episode'].processed)
        self.assertEqual(result['diagnostics_unavailable'], {'status_code': 403})
        client.debug_log.enable.assert_not_called()
        client.graph.get_context.assert_not_called()
        write.assert_called_once()

    def test_recipe_inspection_does_not_request_user_summary_or_debug(self):
        from app.zep.inspect import inspect_graph
        client = self.client()
        with patch('app.zep.inspect.write_ingestion_report'):
            report = inspect_graph(client, 'recipes')
        self.assertEqual(report['entities'], [])
        client.user.get_node.assert_not_called()
        client.graph.episode.get_debug_logs.assert_not_called()

    def test_report_write_failure_does_not_break_ingestion(self):
        from app.zep.ingest import ingest_recipe
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recipe.md'
            path.write_text('# Recipe')
            blocker = Path(directory) / 'blocker'
            blocker.write_text('not a directory')
            client = Mock()
            client.graph.episode.add.return_value = {'task': {'uuid': 'task'}}
            with patch('app.chat_capture.PROJECT_ROOT', blocker), self.assertLogs('app.chat_capture', level='ERROR'):
                result = ingest_recipe(client, 'recipes', path)
        self.assertEqual(result['task']['uuid'], 'task')

    def test_failed_ingestion_retains_markdown_and_error_type(self):
        from app.zep.ingest import ingest_recipe
        client = Mock()
        client.graph.episode.add.side_effect = RuntimeError('private')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recipe.md'
            path.write_text('# Recipe')
            with patch('app.zep.ingest.write_ingestion_report') as write:
                with self.assertRaises(RuntimeError):
                    ingest_recipe(client, 'recipes', path)
        self.assertEqual(write.call_args.args[1]['error'], {'type': 'RuntimeError'})
        self.assertEqual(write.call_args.args[1]['source_markdown'], '# Recipe')


class NativeGraphitiInspectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_stored_summaries_are_inspected_without_refresh_or_retrieval(self):
        from app.graphiti.inspect import inspect_graph
        client = AsyncMock()
        client.nodes.entity.get_by_group_ids.return_value = [{'name': 'Christine', 'summary': 'Avoids garlic'}]
        client.nodes.episode.get_by_group_ids.return_value = []
        client.nodes.saga.get_by_group_ids.return_value = [{'summary': 'Lunch conversation'}]
        client.nodes.community.get_by_group_ids.return_value = []
        client.edges.entity.get_by_group_ids.return_value = []
        with patch('app.graphiti.inspect.write_ingestion_report'):
            result = await inspect_graph(client, 'user_christine')
        self.assertFalse(result['sent_to_answer_model'])
        self.assertEqual(result['sagas'][0]['summary'], 'Lunch conversation')
        client.search.assert_not_called()
        client.summarize_saga.assert_not_called()
        client.build_communities.assert_not_called()

class TraceAccuracyTests(unittest.TestCase):
    def test_default_generated_episode_uuid_is_in_both_report_views(self):
        from datetime import datetime, timezone
        from graphiti_core.nodes import EpisodicNode, EpisodeType
        from app.chat_capture import write_ingestion_report
        episode = EpisodicNode(name='Recipe', group_id='recipes', content='# Recipe',
                               source=EpisodeType.text, source_description='Markdown',
                               valid_at=datetime.now(timezone.utc))
        with tempfile.TemporaryDirectory() as directory, patch('app.chat_capture.PROJECT_ROOT', Path(directory)):
            path = write_ingestion_report('graphiti', {'episode': episode})
            content = path.read_text()
        readable, exact = content.split('<summary>Exact payload</summary>')
        self.assertIn(episode.uuid, readable)
        self.assertIn(episode.uuid, exact)

    def test_partial_tool_failure_does_not_claim_answer_model_received_results(self):
        from app.chat_capture import capture_chat
        from app.rag.query import process_query_result
        from tests.test_chat_api import FakeClient, FakeChatClient, FakePool, FakeConnection, provider_response, provider_tool_call
        chat = FakeChatClient(responses=[provider_response(tool_calls=[
            provider_tool_call('get_recipes', {'input': 'eggs'}, call_id='first'),
            provider_tool_call('get_recipes', {'input': 'tofu'}, call_id='second'),
        ])])
        with tempfile.TemporaryDirectory() as directory, patch('app.chat_capture.CAPTURE_DIR', Path(directory)), patch(
            'app.rag.query.OpenAI', return_value=FakeClient(chat=chat),
        ), patch('app.rag.tools.search_zep_recipes', side_effect=[
            {'backend': 'zep', 'recipe_context': 'Eggs', 'user_context': '', 'sources': []},
            RuntimeError('unavailable'),
        ]):
            with self.assertRaises(RuntimeError), capture_chat('Lunch?'):
                process_query_result('Lunch?', [], retrieval_backend='zep', database_pool=FakePool(FakeConnection()))
            content = next(Path(directory).glob('*.md')).read_text()
        self.assertEqual(len(chat.calls), 1)
        self.assertIn('No answer-model call was made.', content)
        self.assertIn('retrieved but not submitted', content)
        self.assertNotIn('### Tool calls and information sent to the answer model', content)
        final_section = content.split('## 3. Final LLM input')[1].split('## 4. Final output')[0]
        self.assertNotIn('responses.create', final_section)


class EmptyGraphInspectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_graph_uses_namespace_fact_listing(self):
        from app.graphiti.inspect import inspect_graph
        from graphiti_core.errors import GroupsEdgesNotFoundError
        client = AsyncMock()
        for namespace in (client.nodes.entity, client.nodes.episode, client.nodes.saga, client.nodes.community, client.edges.entity):
            namespace.get_by_group_ids.return_value = []
        with patch('graphiti_core.edges.EntityEdge.get_by_group_ids', new_callable=AsyncMock, side_effect=GroupsEdgesNotFoundError(['user'])), patch(
            'app.graphiti.inspect.write_ingestion_report',
        ) as write:
            result = await inspect_graph(client, 'user')
        self.assertEqual(result['facts'], [])
        client.edges.entity.get_by_group_ids.assert_awaited_once_with(['user'])
        write.assert_called_once()
