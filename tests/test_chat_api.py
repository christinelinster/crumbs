from contextlib import contextmanager
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import create_app
from app.db.recipes import DEFAULT_SIMILARITY_THRESHOLD
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
        self.responses = SimpleNamespace(create=self.create)
        self.calls = []

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


def provider_response(content=None, tool_calls=None, finish_reason="stop"):
    status = "incomplete" if finish_reason == "length" else "completed"
    return SimpleNamespace(
        output=list(tool_calls or []),
        output_text=content,
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
        })
        self.assertEqual(connection.calls, [])
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(database_pool.enter_count, 1)
        self.assertEqual(database_pool.exit_count, 1)
        self.assertEqual(client.close_calls, 1)

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
