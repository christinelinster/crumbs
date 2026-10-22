from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from zep_cloud.types import GraphContextResponse

from app.api import create_app
from app.db.recipes import DEFAULT_SIMILARITY_THRESHOLD, RECIPE_REPOSITORY_DETAIL_FIELDS
from app.rag import query as query_module
from app.settings import EMBEDDING_DIMENSIONS


RECIPE_ROW = (
    "steamed-eggs",
    "Steamed Eggs",
    "Silky savory eggs.",
    ["breakfast"],
    ["eggs"],
    "Chinese",
    20,
    2,
    180,
    14,
    4,
    10,
    "Crumbs",
    None,
    "Steam gently.",
    [{"kind": "group", "name": "Egg mixture", "items": ["2 eggs", "1 cup water"]}],
    [{"kind": "ungrouped", "name": None, "items": ["Whisk the eggs.", "Steam until set."]}],
    0.91,
)


def zep_context(edges=(), *, context="<Relevant Facts>Steamed Eggs use eggs.</Relevant Facts>"):
    return GraphContextResponse(
        context=context, truncated=False,
        results={"edges": list(edges), "nodes": [], "observations": [], "thread_summaries": []},
    )


class FakeResult:
    def __init__(self, rows=(), row=None):
        self.rows = rows
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, rows=(), row=None):
        self.rows = rows
        self.row = row
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "WHERE r.slug" in sql:
            return FakeResult(row=self.row)
        return FakeResult(rows=self.rows)


class FakePool:
    def __init__(self, connection):
        self.connection_value = connection
        self.active = False
        self.enter_count = 0
        self.exit_count = 0
        self.connection_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_count += 1

    @contextmanager
    def connection(self):
        self.connection_count += 1
        self.active = True
        try:
            yield self.connection_value
        finally:
            self.active = False


class FakeEmbeddingClient:
    def __init__(self, vector=None, error=None, on_create=None):
        self.vector = vector or [0.1] * EMBEDDING_DIMENSIONS
        self.error = error
        self.on_create = on_create
        self.calls = []

    def create(self, *, model, input):
        self.calls.append({"model": model, "input": input})
        if self.on_create:
            self.on_create()
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(embedding=self.vector)])


class FakeChatClient:
    def __init__(
        self,
        answer="Try the steamed eggs.",
        error=None,
        on_create=None,
        responses=None,
    ):
        self.answer = answer
        self.error = error
        self.on_create = on_create
        self.response_queue = list(responses or [])
        self.responses = SimpleNamespace(create=self.create, parse=self.parse)
        self.calls = []

    def parse(self, *, text_format, **kwargs):
        response = self.create(text_format=text_format, **kwargs)
        response.output_parsed = text_format(
            answer=response.output_text or "", recipe_slugs=response.recipe_slugs,
        )
        return response

    def create(self, *, model, input, instructions=None, **kwargs):
        self.calls.append({
            "model": model,
            "input": input,
            "instructions": instructions,
            **kwargs,
        })
        if self.on_create:
            self.on_create()
        if self.error:
            raise self.error
        if self.response_queue:
            return self.response_queue.pop(0)
        return provider_response(content=self.answer)


def provider_tool_call(name, arguments, call_id="call-1"):
    return SimpleNamespace(
        id=f"fc_{call_id}",
        type="function_call",
        status="completed",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
    )


def provider_response(content=None, tool_calls=None, finish_reason="stop", recipe_slugs=()):
    status = "incomplete" if finish_reason == "length" else "completed"
    return SimpleNamespace(
        output=list(tool_calls or []),
        output_text=content,
        recipe_slugs=list(recipe_slugs),
        status=status,
        incomplete_details=(
            SimpleNamespace(reason="max_output_tokens")
            if status == "incomplete"
            else None
        ),
    )


class FakeClient:
    def __init__(self, embedding=None, chat=None):
        self.embedding = embedding or FakeEmbeddingClient()
        self.chat_client = chat or FakeChatClient()
        self.embeddings = self.embedding
        self.responses = self.chat_client.responses
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.capture_dir = Path(directory.name)
        capture_patch = patch('app.chat_capture.CAPTURE_DIR', self.capture_dir)
        capture_patch.start()
        self.addCleanup(capture_patch.stop)
        self.openai_patch = patch("app.rag.query.OpenAI")
        self.openai_mock = self.openai_patch.start()
        self.addCleanup(self.openai_patch.stop)

    @contextmanager
    def http_app(self, database_pool, client):
        self.openai_mock.return_value = client
        with TestClient(create_app(database_pool=database_pool)) as http:
            yield http

    def test_request_limit_is_rejected_before_chat_work(self):
        database_pool = FakePool(FakeConnection(rows=[RECIPE_ROW]))
        client = FakeClient()

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "egg recipes",
                "limit": 1,
            })

        self.assertEqual(response.status_code, 422)
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(client.embedding.calls, [])
        self.assertEqual(client.chat_client.calls, [])

    def test_history_references_are_assistant_only_and_strict(self):
        invalid_histories = (
            [{
                "role": "user",
                "content": "I liked this one.",
                "recipe_references": None,
            }],
            [{
                "role": "user",
                "content": "I liked this one.",
                "recipe_references": [{"title": "Eggs", "slug": "eggs"}],
            }],
            [{
                "role": "assistant",
                "content": "Try this one.",
                "recipe_references": [{
                    "title": "Eggs",
                    "slug": "eggs",
                    "calories": 180,
                }],
            }],
        )

        for history in invalid_histories:
            with self.subTest(history=history):
                database_pool = FakePool(FakeConnection(rows=[RECIPE_ROW]))
                client = FakeClient()
                with self.http_app(database_pool, client) as http:
                    response = http.post("/api/chat", json={
                        "question": "More like this?",
                        "history": history,
                    })
                self.assertEqual(response.status_code, 422)
                self.assertEqual(database_pool.connection_count, 0)
                self.assertEqual(client.chat_client.calls, [])

    def test_direct_route_returns_answer_with_no_recipe_cards(self):
        connection = FakeConnection(rows=[RECIPE_ROW])
        database_pool = FakePool(connection)
        client = FakeClient(
            chat=FakeChatClient(
                on_create=lambda: self.assertFalse(database_pool.active),
            ),
        )

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "What can I make with eggs?",
                "history": [{"role": "user", "content": "I want breakfast."}],
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "answer": "Try the steamed eggs.",
            "recipe_cards": [],
            "thread_uuid": None,
            "memory_status": None,
        })
        self.assertEqual(connection.calls, [])
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(database_pool.enter_count, 1)
        self.assertEqual(database_pool.exit_count, 1)
        self.assertEqual(client.close_calls, 1)

    def test_zep_discovery_supplies_full_source_recipes_and_cards_without_postgres_or_vectors(self):
        from unittest.mock import Mock
        edge = {"fact": "Steamed Eggs use eggs.", "episode_uuids": ["episode-1"]}
        zep = Mock()
        zep.graph.episode.list.return_value = []
        zep.graph.episode.get.return_value = SimpleNamespace(
            metadata={"recipe_slug": "steamed-eggs"}, document_id="recipe-revision",
            content=json.dumps(dict(zip(RECIPE_REPOSITORY_DETAIL_FIELDS, RECIPE_ROW[:-1]))),
        )
        chat = FakeChatClient(responses=[
            provider_response(tool_calls=[provider_tool_call(
                "get_recipes", {"input": "egg recipes"},
            )], finish_reason="tool_calls"),
            provider_response(content="Try Steamed Eggs.", recipe_slugs=["steamed-eggs"]),
        ])
        client = FakeClient(chat=chat)
        database_pool = FakePool(FakeConnection())
        with self.http_app(database_pool, client) as http, patch(
            "app.rag.tools.get_zep", return_value=zep,
        ), patch("app.rag.tools.get_graph_context", return_value=zep_context([edge])) as search, patch(
            "app.rag.tools.settings.ZEP_GRAPH_UUID", "graph-1",
        ):
            response = http.post("/api/chat", json={
                "question": "egg recipes", "retrieval_backend": "zep",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recipe_cards"][0]["slug"], "steamed-eggs")
        self.assertIsNone(response.json()["recipe_cards"][0]["similarity_score"])
        zep.graph.episode.get.assert_called_once_with("graph-1", "episode-1")

        search.assert_called_once_with(
            zep, "graph-1", "egg recipes", include_history=False,
        )
        self.assertEqual(client.embedding.calls, [])
        self.assertEqual(database_pool.connection_count, 0)
        tool_output = json.loads(chat.calls[1]["input"][-1]["output"])
        self.assertEqual(tool_output["context"], zep_context().context)
        self.assertEqual(tool_output["recipes"][0]["ingredient_sections"], [
            {"kind": "group", "name": "Egg mixture", "items": ["2 eggs", "1 cup water"]},
        ])
        self.assertEqual(tool_output["recipes"][0]["instruction_sections"], [
            {"kind": "ungrouped", "name": None, "items": ["Whisk the eggs.", "Steam until set."]},
        ])

    def test_native_zep_context_reaches_final_model_without_custom_trace(self):
        from unittest.mock import Mock
        edge = {"fact": "Steamed Eggs use eggs.", "episode_uuids": ["episode-1"]}
        recipe = dict(zip(RECIPE_REPOSITORY_DETAIL_FIELDS, RECIPE_ROW[:-1]))
        episode = SimpleNamespace(
            metadata={"recipe_slug": "steamed-eggs", "recipe_revision": "rev-1"},
            document_id="steamed-eggs", content=json.dumps(recipe),
            uuid_="episode-1", created_at="2026-10-10T00:00:00Z",
        )
        zep = Mock()
        context_result = zep_context([edge])
        zep.graph.get_context.return_value = context_result
        zep.graph.episode.get.return_value = episode
        zep.graph.episode.list.return_value = [episode]
        chat = FakeChatClient(responses=[
            provider_response(tool_calls=[provider_tool_call(
                "get_recipes", {"input": "egg recipes"},
            )]),
            provider_response(content="Try Steamed Eggs.", recipe_slugs=["steamed-eggs"]),
        ])
        client = FakeClient(chat=chat)
        with self.http_app(FakePool(FakeConnection()), client) as http, patch(
            "app.rag.tools.get_zep", return_value=zep,
        ), patch("app.rag.tools.settings.ZEP_GRAPH_UUID", "graph-1"):
            response = http.post("/api/chat", json={
                "question": "egg recipes", "retrieval_backend": "zep",
            })

        from app.api import ChatRequest, ChatResponse
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("trace", response.json())
        self.assertNotIn("include_trace", ChatRequest.model_fields)
        self.assertNotIn("trace", ChatResponse.model_fields)
        request = zep.graph.get_context.call_args.kwargs
        self.assertEqual(request["query"], "egg recipes")
        self.assertTrue(request["include_results"])
        self.assertEqual(request["max_characters"], 5000)
        final_tool_output = json.loads(chat.calls[1]["input"][-1]["output"])
        self.assertEqual(final_tool_output["context"], context_result.context)
        self.assertEqual(final_tool_output["recipes"][0]["ingredient_sections"], recipe["ingredient_sections"])
        self.assertEqual(final_tool_output["recipes"][0]["instruction_sections"], recipe["instruction_sections"])
        zep.graph.episode.get.assert_called_once_with("graph-1", "episode-1")

        from fastapi.encoders import jsonable_encoder
        content = next(self.capture_dir.glob('*.md')).read_text()
        self.assertIn(context_result.context, content)
        self.assertIn('"query": "egg recipes"', content)
        captured_input = json.loads(content.split('## 3. Final LLM input\n')[1].split('```json\n')[1].split('\n```')[0])
        self.assertEqual(captured_input['instructions'], chat.calls[1]['instructions'])
        self.assertEqual(captured_input['input'], jsonable_encoder(chat.calls[1]['input'], exclude_unset=True))
        self.assertEqual(captured_input['text_format']['schema'], query_module.RecipeAnswer.model_json_schema())
        self.assertIn('"text": "Try Steamed Eggs."', content.split('## 4. Final output')[1])

    def test_zep_discovery_supplies_raw_ingredients_missing_from_graph_facts(self):
        from unittest.mock import Mock
        edge = {
            "fact": "Steamed Eggs are a Chinese breakfast.",
            "episode_uuids": ["episode-1"],
        }
        zep = Mock()
        zep.graph.episode.list.return_value = []
        for ingredients in (
            ["2 eggs", "1 clove garlic"],
            ["2 eggs", "1 tsp garlic powder"],
            ["2 eggs", "1 onion"],
        ):
            with self.subTest(ingredients=ingredients):
                recipe = dict(zip(RECIPE_REPOSITORY_DETAIL_FIELDS, RECIPE_ROW[:-1]))
                recipe.pop('ingredient_sections')
                recipe.pop('instruction_sections')
                recipe['ingredients'] = ingredients
                recipe['instructions'] = ['Whisk the eggs and remaining ingredients.']
                zep.graph.episode.get.return_value = SimpleNamespace(
                    metadata={'recipe_slug': 'steamed-eggs'}, document_id='steamed-eggs',
                    content=json.dumps(recipe),
                )
                chat = FakeChatClient(responses=[
                    provider_response(tool_calls=[provider_tool_call(
                        "get_recipes", {"input": "breakfast without onions or garlic"},
                    )]),
                    provider_response(content="No suitable recipes found.", recipe_slugs=[]),
                ])
                database_pool = FakePool(FakeConnection())
                with self.http_app(database_pool, FakeClient(chat=chat)) as http, patch(
                    "app.rag.tools.get_zep", return_value=zep,
                ), patch("app.rag.tools.get_graph_context", return_value=zep_context([edge])):
                    response = http.post('/api/chat', json={
                        'question': 'Breakfast without onions or garlic?', 'retrieval_backend': 'zep',
                    })
                self.assertEqual(response.status_code, 200)
                output = json.loads(chat.calls[1]['input'][-1]['output'])
                self.assertEqual(output['recipes'][0]['ingredients'], ingredients)
                self.assertEqual(output['recipes'][0]['instructions'], ['Whisk the eggs and remaining ingredients.'])
                self.assertEqual(output['context'], zep_context().context)
                self.assertEqual(database_pool.connection_count, 0)
                self.assertEqual(response.json()['recipe_cards'], [])

    def test_zep_discovery_does_not_offer_malformed_source_episodes_or_fall_back_to_postgres(self):
        from unittest.mock import Mock
        edge = {'fact': 'A missing recipe uses eggs.', 'episode_uuids': ['episode-1']}
        zep = Mock()
        zep.graph.episode.get.return_value = SimpleNamespace(metadata=None, document_id='missing', content='not JSON')
        chat = FakeChatClient(responses=[
            provider_response(tool_calls=[provider_tool_call('get_recipes', {'input': 'eggs'})]),
            provider_response(content='No suitable recipes found.', recipe_slugs=['missing']),
        ])
        database_pool = FakePool(FakeConnection(row=RECIPE_ROW[:-1]))
        with self.http_app(database_pool, FakeClient(chat=chat)) as http, patch(
            'app.rag.tools.get_zep', return_value=zep,
        ), patch('app.rag.tools.get_graph_context', return_value=zep_context([edge])):
            response = http.post('/api/chat', json={'question': 'Eggs?', 'retrieval_backend': 'zep'})
        self.assertEqual(response.status_code, 200)
        output = json.loads(chat.calls[1]['input'][-1]['output'])
        self.assertEqual(output.get('recipes'), [])
        self.assertEqual(response.json()['recipe_cards'], [])
        self.assertEqual(database_pool.connection_count, 0)

    def test_zep_candidates_reach_model_without_application_ingredient_filtering(self):
        from unittest.mock import Mock
        zep = Mock()
        zep.graph.episode.list.return_value = []
        edges = []
        episodes = []
        for slug, ingredients in (
            ('garlic-eggs', ['2 eggs', '1 tsp garlic powder']),
            ('plain-eggs', ['2 eggs', 'water']),
        ):
            edge = {'fact': f'{slug} is tasty.', 'episode_uuids': [slug]}
            edges.append(edge)
            recipe = dict(zip(RECIPE_REPOSITORY_DETAIL_FIELDS, RECIPE_ROW[:-1]))
            recipe.update(slug=slug, ingredient_sections=[{'kind': 'ungrouped', 'name': None, 'items': ingredients}])
            episodes.append(SimpleNamespace(metadata=None, document_id=slug, content=json.dumps(recipe)))
        zep.graph.episode.get.side_effect = episodes
        chat = FakeChatClient(responses=[
            provider_response(tool_calls=[provider_tool_call('get_recipes', {
                'input': 'eggs without garlic',
            })]),
            provider_response(content='Try plain eggs.', recipe_slugs=['plain-eggs']),
        ])
        database_pool = FakePool(FakeConnection())
        with self.http_app(database_pool, FakeClient(chat=chat)) as http, patch(
            'app.rag.tools.get_zep', return_value=zep,
        ), patch('app.rag.tools.get_graph_context', return_value=zep_context(edges)):
            response = http.post('/api/chat', json={
                'question': 'Egg recipes without garlic', 'retrieval_backend': 'zep',
            })
        self.assertEqual(response.status_code, 200)
        output = json.loads(chat.calls[1]['input'][-1]['output'])
        self.assertEqual([r['slug'] for r in output['recipes']], ['garlic-eggs', 'plain-eggs'])
        self.assertEqual(output['context'], zep_context().context)
        self.assertNotIn('excluded_ingredients', output)
        search_tool = next(tool for tool in chat.calls[0]['tools'] if tool['name'] == 'get_recipes')
        self.assertNotIn('excluded_ingredients', search_tool['parameters']['properties'])
        self.assertEqual([c['slug'] for c in response.json()['recipe_cards']], ['plain-eggs'])
        self.assertEqual(database_pool.connection_count, 0)

    def test_remembered_preferences_reach_both_router_and_answer_model(self):
        chat = FakeChatClient(responses=[
            provider_response(tool_calls=[provider_tool_call(
                "get_recipe_detail", {"slug": "steamed-eggs"},
            )], finish_reason="tool_calls"),
            provider_response(content="Steamed Eggs fit your preference."),
        ])
        client = FakeClient(chat=chat)
        with patch("app.rag.query.OpenAI", return_value=client):
            query_module.process_query_result(
                "Does this fit my preferences?", [],
                database_pool=FakePool(FakeConnection(row=RECIPE_ROW[:-1])),
                memory_context="<User Preferences>User avoids shrimp.</User Preferences>",
            )
        for call in chat.calls:
            self.assertEqual(call["input"][0]["role"], "user")
            self.assertIn("User avoids shrimp", call["input"][0]["content"])

    def test_zep_error_is_generic_and_does_not_fall_back_to_vector(self):
        from zep_cloud.core.api_error import ApiError
        chat = FakeChatClient(responses=[provider_response(tool_calls=[provider_tool_call(
            "get_recipes", {"input": "egg recipes"},
        )], finish_reason="tool_calls")])
        client = FakeClient(chat=chat)
        database_pool = FakePool(FakeConnection(rows=[RECIPE_ROW]))
        with self.http_app(database_pool, client) as http, patch(
            "app.rag.tools.settings.ZEP_GRAPH_UUID", "graph-1",
        ), patch("app.rag.tools.get_zep"), patch(
            "app.rag.tools.get_graph_context", side_effect=ApiError(status_code=503, body="secret"),
        ):
            response = http.post("/api/chat", json={
                "question": "egg recipes", "retrieval_backend": "zep",
            })
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text)
        self.assertEqual(client.embedding.calls, [])
        self.assertEqual(database_pool.connection_count, 0)

    def test_unsupported_retrieval_backend_is_rejected(self):
        with self.http_app(FakePool(FakeConnection()), FakeClient()) as http:
            response = http.post("/api/chat", json={
                "question": "egg recipes", "retrieval_backend": "unknown",
            })
        self.assertEqual(response.status_code, 422)

    def test_chat_request_has_no_recipe_count_field(self):
        from app.api import ChatRequest

        self.assertNotIn("limit", ChatRequest.model_fields)

    def test_unrelated_question_uses_direct_route_without_retrieval(self):
        connection = FakeConnection(rows=[RECIPE_ROW])
        database_pool = FakePool(connection)
        embedding = FakeEmbeddingClient()
        chat = FakeChatClient(
            answer=(
                "I'm Crumbs, a recipe assistant, and I don't have information to answer that. "
                "I can help with recipes from my collection."
            )
        )
        client = FakeClient(embedding=embedding, chat=chat)

        with self.http_app(database_pool, client) as http:
            response = http.post(
                "/api/chat",
                json={"question": "What is the capital of France?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "answer": chat.answer,
            "recipe_cards": [],
            "thread_uuid": None,
            "memory_status": None,
        })
        self.assertEqual(embedding.calls, [])
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(len(chat.calls), 1)
        self.assertEqual(chat.calls[0]["tool_choice"], "auto")
        self.assertEqual(chat.calls[0]["instructions"], query_module.ROUTER_SYSTEM_PROMPT)
        self.assertIn("<tools>", chat.calls[0]["instructions"])
        self.assertIn("does not have information to answer", chat.calls[0]["instructions"])

    def test_standalone_cooking_how_to_uses_direct_route_without_retrieval(self):
        embedding = FakeEmbeddingClient()
        database_pool = FakePool(FakeConnection(rows=[RECIPE_ROW]))
        chat = FakeChatClient(
            answer="Roast broccoli at high heat until browned. Crumbs can help find a specific recipe."
        )
        client = FakeClient(embedding=embedding, chat=chat)

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "How do I roast broccoli?",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "answer": chat.answer,
            "recipe_cards": [],
            "thread_uuid": None,
            "memory_status": None,
        })
        self.assertEqual(embedding.calls, [])
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(len(chat.calls), 1)

    def test_detail_tool_returns_no_recipe_card(self):
        chat = FakeChatClient(responses=[
            provider_response(
                tool_calls=[provider_tool_call(
                    "get_recipe_detail",
                    {"slug": "steamed-eggs"},
                )],
                finish_reason="tool_calls",
            ),
            provider_response(content="Steamed Eggs use eggs and water."),
        ])
        client = FakeClient(
            embedding=FakeEmbeddingClient(error=RuntimeError("must not embed details")),
            chat=chat,
        )
        connection = FakeConnection(row=RECIPE_ROW[:-1])
        database_pool = FakePool(connection)

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "Tell me about Steamed Eggs",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recipe_cards"], [])
        self.assertEqual(client.embedding.calls, [])
        self.assertEqual(database_pool.connection_count, 1)
        self.assertEqual(len(chat.calls), 2)

    def test_missing_exact_recipe_returns_a_not_found_answer_without_search(self):
        chat = FakeChatClient(responses=[
            provider_response(
                tool_calls=[provider_tool_call(
                    "get_recipe_detail",
                    {"slug": "missing-recipe"},
                )],
                finish_reason="tool_calls",
            ),
            provider_response(content="I couldn't find that exact recipe. Ask if you'd like alternatives."),
        ])
        client = FakeClient(chat=chat)
        connection = FakeConnection(rows=[RECIPE_ROW], row=None)
        database_pool = FakePool(connection)

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "Tell me about Missing Recipe",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recipe_cards"], [])
        self.assertIn("exact recipe", response.json()["answer"])
        self.assertEqual(database_pool.connection_count, 1)
        self.assertEqual(len(connection.calls), 1)
        self.assertEqual(client.embedding.calls, [])
        output = json.loads(chat.calls[-1]['input'][-1]['output'])
        self.assertEqual(output, {"recipe": None})
        self.assertIn("recipe is null", chat.calls[-1]['instructions'])

    def test_model_tool_arguments_are_used_without_slug_prevalidation(self):
        chat = FakeChatClient(responses=[provider_response(
            tool_calls=[provider_tool_call(
                "get_recipe_detail",
                {"slug": "Not_A_Valid_Slug"},
            )],
            finish_reason="tool_calls",
        )])
        client = FakeClient(chat=chat)
        connection = FakeConnection(rows=[RECIPE_ROW], row=RECIPE_ROW[:-1])
        database_pool = FakePool(connection)

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "Tell me about this recipe",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(database_pool.connection_count, 1)
        self.assertEqual(connection.calls[0][1], ("Not_A_Valid_Slug",))
        self.assertEqual(response.json()["recipe_cards"], [])
        self.assertEqual(client.embedding.calls, [])

    def test_selected_recipe_slug_does_not_trigger_database_lookup_on_its_own(self):
        connection = FakeConnection(row=RECIPE_ROW[:-1])
        database_pool = FakePool(connection)
        embedding = FakeEmbeddingClient(
            on_create=lambda: self.fail(
                "selected-recipe requests should not generate an embedding"
            ),
        )
        chat = FakeChatClient(
            on_create=lambda: self.assertFalse(database_pool.active),
        )
        client = FakeClient(embedding=embedding, chat=chat)

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "What goes into the egg mixture?",
                "history": [{
                    "role": "assistant",
                    "content": "Earlier, we looked at Turkey Bowl.",
                    "recipe_references": [{
                        "title": "Turkey Bowl",
                        "slug": "turkey-bowl",
                    }],
                }],
                "recipe_slug": "steamed-eggs",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "answer": "Try the steamed eggs.",
            "recipe_cards": [],
            "thread_uuid": None,
            "memory_status": None,
        })
        self.assertEqual(embedding.calls, [])
        self.assertEqual(connection.calls, [])
        router_input = chat.calls[0]["input"]
        self.assertEqual(router_input[0]["role"], "developer")
        self.assertIn("Discussing", router_input[0]["content"])
        self.assertIn("steamed-eggs", router_input[0]["content"])
        self.assertEqual(router_input[1]["content"], "Earlier, we looked at Turkey Bowl.")
        self.assertEqual(router_input[-1]["content"], "What goes into the egg mixture?")
        self.assertIn("prioritize it over earlier recipe references", chat.calls[0]["instructions"].lower())

    def test_invalid_request_returns_422_before_retrieval(self):
        payloads = (
            {"question": ""},
            {"question": "   "},
            {"question": "egg recipes", "limit": 0},
            {
                "question": "egg recipes",
                "history": [{"role": "system", "content": "invalid"}],
            },
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                connection = FakeConnection(rows=[RECIPE_ROW])
                database_pool = FakePool(connection)
                client = FakeClient()

                with self.http_app(database_pool, client) as http:
                    response = http.post("/api/chat", json=payload)

                self.assertEqual(response.status_code, 422)
                self.assertEqual(client.embedding.calls, [])
                self.assertEqual(database_pool.connection_count, 0)

    def test_direct_response_does_not_call_unavailable_embedding_service(self):
        connection = FakeConnection(rows=[RECIPE_ROW])
        client = FakeClient(
            embedding=FakeEmbeddingClient(error=RuntimeError("secret provider error")),
        )

        database_pool = FakePool(connection)
        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "How do I roast broccoli?",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recipe_cards"], [])
        self.assertEqual(client.embedding.calls, [])
        self.assertEqual(database_pool.connection_count, 0)
        self.assertNotIn("secret provider error", response.text)

    def test_llm_failure_returns_generic_503(self):
        connection = FakeConnection(rows=[RECIPE_ROW])
        client = FakeClient(
            chat=FakeChatClient(error=RuntimeError("secret model error")),
        )

        with self.http_app(FakePool(connection), client) as http:
            response = http.post("/api/chat", json={"question": "egg recipes"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "chat service unavailable"})
        self.assertNotIn("secret model error", response.text)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_client_is_created_and_closed_for_a_chat_request(self):
        connection = FakeConnection(rows=[RECIPE_ROW])
        database_pool = FakePool(connection)
        client = FakeClient()
        self.openai_mock.return_value = client

        with TestClient(create_app(database_pool=database_pool)) as http:
            response = http.post("/api/chat", json={"question": "egg recipes"})

        self.assertEqual(response.status_code, 200)
        self.openai_mock.assert_called_once_with(
            api_key="test-key",
            timeout=60.0,
            max_retries=2,
        )
        self.assertEqual(client.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
