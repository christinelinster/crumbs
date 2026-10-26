"""Graphiti setup and ingestion checks without database or model calls."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from graphiti_core.nodes import EpisodeType


class GraphitiTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_ingests_the_selected_file_and_closes_client(self):
        from app.graphiti.main import main

        path = Path('selected-recipe.md')
        client = AsyncMock()
        client.search.return_value = []
        result = SimpleNamespace(episode=SimpleNamespace(uuid='episode-1'), nodes=[], edges=[])
        with patch('app.graphiti.main.get_graphiti', return_value=client), patch(
            'app.graphiti.main.ingest_recipe', new_callable=AsyncMock,
            return_value=result,
        ) as ingest:
            await main(path)
        ingest.assert_awaited_once_with(client, path)
        client.search.assert_not_called()
        client.close.assert_awaited_once()

    async def test_cli_rejects_missing_file_before_creating_client(self):
        from app.graphiti.main import cli

        with tempfile.TemporaryDirectory() as directory, patch(
            'app.graphiti.main.get_graphiti',
        ) as constructor, patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:
                cli([str(Path(directory) / 'missing.md')])
        self.assertEqual(error.exception.code, 2)
        constructor.assert_not_called()

    async def test_setup_routes_configured_models_to_graphiti_prompts(self):
        from graphiti_core.llm_client import PromptRoutes

        from app.graphiti import client as graphiti_client

        default_model = object()
        extraction_model = object()
        with (
            patch.object(graphiti_client, 'Graphiti') as constructor,
            patch.object(graphiti_client, 'OpenAIClient', create=True) as openai_client,
            patch.object(graphiti_client, 'LLMTransport', create=True) as transport_constructor,
            patch.object(graphiti_client, 'LLMRuntime', create=True) as runtime_constructor,
            patch.object(graphiti_client, 'PromptRoutes', PromptRoutes, create=True),
            patch.multiple(
                'app.graphiti.client.settings',
                GRAPHITI_LLM_MODEL='gpt-5.5',
                GRAPHITI_SMALL_MODEL='gpt-5-nano',
                NEO4J_URI='bolt://localhost:7687',
                NEO4J_USER='neo4j',
                NEO4J_PASSWORD='test-password',
            ),
        ):
            transport = transport_constructor.return_value
            transport.model.side_effect = [default_model, extraction_model]
            self.assertIs(graphiti_client.get_graphiti(), constructor.return_value)

        transport_constructor.assert_called_once_with(
            openai_client.return_value,
            models=('gpt-5.5', 'gpt-5-nano'),
        )
        transport.model.assert_any_call('gpt-5.5')
        transport.model.assert_any_call('gpt-5-nano')
        runtime_constructor.assert_called_once()
        runtime = runtime_constructor.call_args.kwargs
        self.assertIs(runtime['model'], default_model)
        routes = runtime['routes']
        self.assertIs(routes.extract_nodes.extract_attributes, extraction_model)
        self.assertIs(routes.extract_edges.extract_attributes, extraction_model)
        constructor.assert_called_once_with(
            uri='bolt://localhost:7687',
            user='neo4j',
            password='test-password',
            llm_runtime=runtime_constructor.return_value,
        )

    async def test_setup_closes_client_when_initialization_fails(self):
        from app.graphiti.main import main

        client = AsyncMock()
        client.build_indices_and_constraints.side_effect = RuntimeError('unavailable')
        with patch('app.graphiti.main.get_graphiti', return_value=client):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                await main(Path('recipe.md'))
        client.close.assert_awaited_once()

    async def test_ingestion_preserves_recipe_and_returns_extracted_graph(self):
        from app.graphiti.ingest import ingest_recipe

        markdown = (
            '---\nslug: garlic-pasta\n---\n# Garlic pasta 🍝\n\n'
            '## Ingredients\n- 2 cloves garlic\n\n'
            '## Instructions\n1. Cook together.\n'
        )
        client = AsyncMock()
        client.add_episode.return_value = SimpleNamespace(episode={'uuid': 'ep'}, nodes=[], edges=[])
        before = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'garlic-pasta.md'
            path.write_text(markdown, encoding='utf-8')
            result = await ingest_recipe(client, path)
        arguments = client.add_episode.call_args.kwargs

        self.assertIs(result, client.add_episode.return_value)
        self.assertEqual(arguments['name'], 'garlic-pasta')
        self.assertEqual(arguments['episode_body'], markdown)
        self.assertEqual(arguments['source'], EpisodeType.text)
        self.assertEqual(arguments['source_description'], 'Crumbs recipe Markdown')
        self.assertEqual(arguments['group_id'], 'shared_recipes')
        self.assertLessEqual(before, arguments['reference_time'])
        self.assertLessEqual(arguments['reference_time'], datetime.now(timezone.utc))


class GraphitiBulkRecipeTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_selection_does_not_write(self):
        from app.graphiti.ingest import ingest_recipes
        client = AsyncMock()
        with self.assertRaises(ValueError):
            await ingest_recipes(client, [])
        client.add_episode_bulk.assert_not_called()

    async def test_bulk_recipe_ingestion_uses_native_text_extraction_without_speaker_prompt(self):
        from app.graphiti.ingest import ingest_recipes
        client = AsyncMock()
        client.add_episode_bulk.return_value = SimpleNamespace(episodes=[], nodes=[], edges=[])
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('first.md', 'second.md')]
            markdown = ['# First 🍲\n- ½ onion\n', '# Second\n- eggs\n']
            for path, content in zip(paths, markdown):
                path.write_text(content, encoding='utf-8')
            result = await ingest_recipes(client, paths)
        args, kwargs = client.add_episode_bulk.call_args
        self.assertEqual([e.content for e in args[0]], markdown)
        self.assertEqual([e.name for e in args[0]], ['first', 'second'])
        self.assertTrue(all(e.source == EpisodeType.text for e in args[0]))
        self.assertEqual(kwargs, {'group_id': 'shared_recipes', 'use_combined_extraction': False})
        self.assertIs(result, client.add_episode_bulk.return_value)
        client.add_episode.assert_not_called()

    async def test_bulk_reads_all_sources_before_any_graph_write(self):
        from app.graphiti.ingest import ingest_recipes
        client = AsyncMock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'valid.md'
            path.write_text('# Recipe')
            with self.assertRaises(FileNotFoundError):
                await ingest_recipes(client, [path, path.with_name('missing.md')])
        client.add_episode_bulk.assert_not_called()

    async def test_bulk_failure_propagates_without_retry(self):
        from app.graphiti.ingest import ingest_recipes
        client = AsyncMock()
        client.add_episode_bulk.side_effect = RuntimeError('unavailable')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recipe.md'
            path.write_text('# Recipe')
            with self.assertRaises(RuntimeError):
                await ingest_recipes(client, [path])
        self.assertEqual(client.add_episode_bulk.await_count, 1)
