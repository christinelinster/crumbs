from contextlib import contextmanager
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import create_app


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
    ["2 eggs", "1 cup water"],
    ["Whisk the eggs.", "Steam until set."],
    [{"position": 1, "group_position": 1, "group_name": "Egg mixture"}],
    [],
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
        self.vector = vector or [0.1] * 1536
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
    def __init__(self, answer="Try the steamed eggs.", error=None, on_create=None, choices=None):
        self.answer = answer
        self.error = error
        self.on_create = on_create
        self.choices = choices
        self.calls = []

    def create(self, *, model, messages):
        self.calls.append({"model": model, "messages": messages})
        if self.on_create:
            self.on_create()
        if self.error:
            raise self.error
        choices = self.choices
        if choices is None:
            choices = [SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=self.answer),
            )]
        return SimpleNamespace(choices=choices)


class FakeClient:
    def __init__(self, embedding=None, chat=None):
        self.embedding = embedding or FakeEmbeddingClient()
        self.chat_client = chat or FakeChatClient()
        self.embeddings = self.embedding
        self.chat = SimpleNamespace(completions=self.chat_client)
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

    def test_general_query_returns_answer_and_condensed_cards(self):
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
                "limit": 1,
                "similarity_threshold": 0.8,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "answer": "Try the steamed eggs.",
            "recipe_cards": [{
                "slug": "steamed-eggs",
                "title": "Steamed Eggs",
                "category": ["breakfast"],
                "tags": ["eggs"],
                "total_time_minutes": 20,
                "calories": 180,
                "protein": 14,
                "carbs": 4,
                "fat": 10,
                "similarity_score": 0.91,
            }],
        })
        self.assertEqual(connection.calls[0][1][-2:], (0.8, 1))
        self.assertEqual(database_pool.enter_count, 1)
        self.assertEqual(database_pool.exit_count, 1)
        self.assertEqual(client.close_calls, 1)

    def test_omitted_limit_defaults_to_three(self):
        connection = FakeConnection(rows=[RECIPE_ROW])
        database_pool = FakePool(connection)
        client = FakeClient()

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={"question": "egg recipes"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(connection.calls[0][1][2], 3)

    def test_selected_slug_uses_exact_recipe_without_similarity_search(self):
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
                "recipe_slug": "steamed-eggs",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "answer": "Try the steamed eggs.",
            "recipe_cards": [],
        })
        self.assertEqual(embedding.calls, [])
        self.assertEqual(len(connection.calls), 1)
        self.assertIn("WHERE r.slug", connection.calls[0][0])
        self.assertIn("2 eggs", chat.calls[0]["messages"][-1]["content"])

    def test_invalid_request_returns_422_before_retrieval(self):
        payloads = (
            {"question": ""},
            {"question": "   "},
            {"question": "egg recipes", "limit": 0},
            {"question": "egg recipes", "similarity_threshold": 1.1},
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

    def test_missing_slug_returns_404_without_embedding(self):
        connection = FakeConnection(row=None)
        database_pool = FakePool(connection)
        embedding = FakeEmbeddingClient(
            on_create=lambda: self.fail(
                "missing selected recipes should not generate an embedding"
            ),
        )
        client = FakeClient(embedding=embedding)

        with self.http_app(database_pool, client) as http:
            response = http.post("/api/chat", json={
                "question": "Tell me about this recipe",
                "recipe_slug": "missing-recipe",
            })

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "recipe not found: missing-recipe"})
        self.assertEqual(embedding.calls, [])
        self.assertEqual(len(connection.calls), 1)

    def test_embedding_failure_returns_generic_503(self):
        connection = FakeConnection(rows=[RECIPE_ROW])
        client = FakeClient(
            embedding=FakeEmbeddingClient(error=RuntimeError("secret provider error")),
        )

        with self.http_app(FakePool(connection), client) as http:
            response = http.post("/api/chat", json={"question": "egg recipes"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "chat service unavailable"})
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

    def test_invalid_model_response_returns_502(self):
        connection = FakeConnection(rows=[RECIPE_ROW])
        client = FakeClient(
            chat=FakeChatClient(choices=[]),
        )

        with self.http_app(FakePool(connection), client) as http:
            response = http.post("/api/chat", json={"question": "egg recipes"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "chat model returned an invalid response"},
        )

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
