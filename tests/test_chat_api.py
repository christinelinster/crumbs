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
        self.capture_dir = Path(directory.name) / 'zep'
        self.graphiti_capture_dir = Path(directory.name) / 'graphiti'
        for capture_patch in (
            patch('app.chat_capture.CAPTURE_DIR', self.capture_dir),
            patch('app.chat_capture.GRAPHITI_CAPTURE_DIR', self.graphiti_capture_dir),
        ):
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
            "graphiti_thread_uuid": None,
            "graphiti_memory_status": None,
        })
        self.assertEqual(connection.calls, [])
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(database_pool.enter_count, 1)
        self.assertEqual(database_pool.exit_count, 1)
        self.assertEqual(client.close_calls, 1)

    def test_native_zep_markdown_and_both_contexts_reach_answer_without_cards(self):
        from unittest.mock import Mock
        zep = Mock()
        recipe_context = zep_context([{'fact': 'Eggs use eggs.', 'episode_uuids': ['episode-1']}])
        user_context = zep_context(context='Christine avoids garlic.')
        zep.graph.get_context.return_value = recipe_context
        zep.thread.create.return_value.uuid_ = 'thread-1'
        zep.thread.get_context.return_value = user_context
        markdown = '# Steamed Eggs\n\n## Ingredients\n- 2 eggs\n- 1 cup water\n\n## Instructions\nSteam gently.'
        zep.graph.episode.get.return_value = SimpleNamespace(
            graph_uuid='graph-1', document_id='steamed-eggs', content=markdown,
        )
        chat = FakeChatClient(responses=[
            provider_response(tool_calls=[provider_tool_call('get_recipes', {'input': 'egg recipes'})]),
            provider_response(content='Try Steamed Eggs.'),
        ])
        client = FakeClient(chat=chat)
        database_pool = FakePool(FakeConnection())
        with self.http_app(database_pool, client) as http, patch(
            'app.zep.retrieval.get_zep', return_value=zep,
        ), patch('app.zep.memory.get_zep', return_value=zep), patch.multiple(
            'app.zep.retrieval.settings', ZEP_GRAPH_UUID='graph-1', ZEP_USER_UUID='user-1',
        ):
            response = http.post('/api/chat', json={
                'question': 'egg recipes', 'retrieval_backend': 'zep',
                'history': [{'role': 'user', 'content': 'I want breakfast.'}],
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['answer'], 'Try Steamed Eggs.')
        self.assertEqual(response.json()['recipe_cards'], [])
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(client.embedding.calls, [])
        self.assertEqual([c.kwargs['graph_uuid'] for c in zep.graph.get_context.call_args_list], ['graph-1'])
        self.assertEqual(zep.thread.add_messages.call_count, 2)
        zep.thread.get_context.assert_called_once_with('thread-1')
        zep.graph.episode.get.assert_called_once_with('graph-1', 'episode-1')
        final = json.loads(chat.calls[1]['input'][-1]['output'])
        self.assertEqual(final['recipe_context'], recipe_context.context)
        self.assertEqual(final['sources'][0]['markdown'], markdown)
        self.assertEqual([t['name'] for t in chat.calls[0]['tools']], ['get_recipes'])
        self.assertIn('Christine avoids garlic.', chat.calls[0]['input'][0]['content'])
        trace = next(self.capture_dir.glob('*.md')).read_text()
        for text in ('recipe graph', 'user thread', 'Christine avoids garlic.', 'thread.get_context',
                     'Supplemental recipe source fetches', '## 4. Full final LLM input',
                     'Try Steamed Eggs.'):
            self.assertIn(text, trace)
        self.assertIn('System prompt (instructions)', trace)
        self.assertFalse(list(self.graphiti_capture_dir.glob('*.md')))

    def test_zep_source_failure_preserves_partial_trace_without_fallback(self):
        from unittest.mock import Mock
        zep = Mock()
        zep.graph.get_context.return_value = zep_context([{'fact': 'Eggs.', 'episode_uuids': ['ep']}])
        zep.thread.create.return_value.uuid_ = 'thread-2'
        zep.thread.get_context.return_value.context = 'Relevant thread context.'
        zep.thread.get_context.return_value.results = None
        zep.thread.get_context.return_value.truncated = None
        zep.graph.episode.get.side_effect = RuntimeError('private source error')
        chat = FakeChatClient(responses=[provider_response(tool_calls=[provider_tool_call('get_recipes', {'input': 'eggs'})])])
        database_pool = FakePool(FakeConnection())
        client = FakeClient(chat=chat)
        with self.http_app(database_pool, client) as http, patch('app.zep.retrieval.get_zep', return_value=zep), patch(
            'app.zep.memory.get_zep', return_value=zep,
        ), patch.multiple(
            'app.zep.retrieval.settings', ZEP_GRAPH_UUID='recipes', ZEP_USER_UUID='user',
        ):
            response = http.post('/api/chat', json={'question': 'eggs', 'retrieval_backend': 'zep'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private', response.text)
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(client.embedding.calls, [])
        trace = next(self.capture_dir.glob('*.md')).read_text()
        self.assertIn('RuntimeError', trace)
        self.assertIn('Supplemental recipe source fetches', trace)
        self.assertEqual(len(chat.calls), 1)

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
            "app.zep.retrieval.settings.ZEP_GRAPH_UUID", "graph-1",
        ), patch("app.zep.retrieval.settings.ZEP_USER_UUID", "user-1"), patch(
            "app.zep.retrieval.get_zep", side_effect=ApiError(status_code=503, body="secret"),
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
            "graphiti_thread_uuid": None,
            "graphiti_memory_status": None,
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
            "graphiti_thread_uuid": None,
            "graphiti_memory_status": None,
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
            "graphiti_thread_uuid": None,
            "graphiti_memory_status": None,
        })
        self.assertEqual(embedding.calls, [])
        self.assertEqual(connection.calls, [])
        router_input = chat.calls[0]["input"]
        self.assertEqual(router_input[0]["role"], "developer")
        self.assertIn("Discussing", router_input[0]["content"])
        self.assertIn("steamed-eggs", router_input[0]["content"])
        self.assertEqual(router_input[1]["content"], "Earlier, we looked at Turkey Bowl.")
        self.assertEqual(router_input[-1]["content"], "What goes into the egg mixture?")
        self.assertIn("it is the only recipe the user is discussing", chat.calls[0]["instructions"].lower())

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
