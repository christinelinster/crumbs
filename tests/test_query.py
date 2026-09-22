from contextlib import contextmanager
import unittest
from types import SimpleNamespace

from app.db.recipes import find_similar_recipes
from app.rag.query import build_recipe_cards, process_query, search_similar_recipes


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
    [{"position": 1, "group_position": 1, "group_name": "Egg mixture"},
     {"position": 2, "group_position": 1, "group_name": "Egg mixture"}],
    [],
    0.91,
)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return FakeResult(self.rows)


class FakePool:
    def __init__(self, connection):
        self.connection_value = connection
        self.connection_count = 0
        self.active = False

    @contextmanager
    def connection(self):
        self.connection_count += 1
        self.active = True
        try:
            yield self.connection_value
        finally:
            self.active = False


class FakeEmbeddingClient:
    def __init__(self, vector, on_embed=None, error=None):
        self.vector = vector
        self.on_embed = on_embed
        self.error = error
        self.embeddings = self
        self.calls = []

    def create(self, *, model, input):
        self.calls.append({"model": model, "input": input})
        if self.on_embed:
            self.on_embed()
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(embedding=self.vector)])


class FakeChatClient:
    def __init__(self, answer="Try the steamed eggs.", error=None, on_chat=None, choices=None):
        self.answer = answer
        self.error = error
        self.on_chat = on_chat
        self.choices = choices
        self.chat = self
        self.completions = self
        self.calls = []

    def create(self, *, model, messages):
        self.calls.append({"model": model, "messages": messages})
        if self.on_chat:
            self.on_chat()
        if self.error:
            raise self.error
        choices = self.choices
        if choices is None:
            choices = [SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=self.answer),
            )]
        return SimpleNamespace(choices=choices)


class RecipeDatabaseTests(unittest.TestCase):
    def test_find_similar_recipes_returns_full_context_and_score(self):
        connection = FakeConnection([RECIPE_ROW])

        results = find_similar_recipes(connection, [0.1] * 1536, 2)

        self.assertEqual(results[0]["slug"], "steamed-eggs")
        self.assertEqual(results[0]["similarity_score"], 0.91)
        self.assertEqual(results[0]["ingredients"], ["2 eggs", "1 cup water"])
        self.assertEqual(results[0]["ingredient_groups"][0]["group_name"], "Egg mixture")
        self.assertEqual(
            results[0]["instructions"],
            ["Whisk the eggs.", "Steam until set."],
        )
        self.assertNotIn("id", results[0])
        self.assertNotIn("embedding", results[0])

        sql, params = connection.calls[0]
        self.assertIn("similarity_score", sql)
        self.assertIn("embedding IS NOT NULL", sql)
        self.assertIn("ORDER BY r.embedding <=> %s::vector", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertEqual(params[0], [0.1] * 1536)
        self.assertEqual(params[1], [0.1] * 1536)
        self.assertEqual(params[2], 2)

    def test_find_similar_recipes_rejects_invalid_limits_before_query(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit):
                connection = FakeConnection([RECIPE_ROW])

                with self.assertRaisesRegex(ValueError, "positive integer"):
                    find_similar_recipes(connection, [0.1] * 1536, limit)

                self.assertEqual(connection.calls, [])


class QueryRetrievalTests(unittest.TestCase):
    def test_build_recipe_cards_uses_condensed_fields_and_score(self):
        cards = build_recipe_cards([{
            "slug": "steamed-eggs",
            "title": "Steamed Eggs",
            "description": "Silky savory eggs.",
            "category": ["breakfast"],
            "tags": ["eggs"],
            "cuisine": "Chinese",
            "total_time_minutes": 20,
            "servings": 2,
            "calories": 180,
            "protein": 14,
            "carbs": 4,
            "fat": 10,
            "source_label": "Crumbs",
            "source_url": None,
            "notes": "Steam gently.",
            "ingredients": ["2 eggs", "1 cup water"],
            "instructions": ["Whisk the eggs.", "Steam until set."],
            "ingredient_groups": [],
            "instruction_groups": [],
            "similarity_score": 0.91,
        }])

        self.assertEqual(cards, [{
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
        }])

    def test_default_limit_is_three_and_embedding_precedes_connection(self):
        connection = FakeConnection([RECIPE_ROW])
        database_pool = FakePool(connection)
        client = FakeEmbeddingClient(
            [0.1] * 1536,
            on_embed=lambda: self.assertEqual(database_pool.connection_count, 0),
        )

        results = search_similar_recipes(
            "What can I make with eggs?",
            client=client,
            database_pool=database_pool,
        )

        self.assertEqual(results[0]["title"], "Steamed Eggs")
        self.assertEqual(client.calls[0]["input"], "What can I make with eggs?")
        self.assertEqual(connection.calls[0][1][2], 3)
        self.assertEqual(database_pool.connection_count, 1)

    def test_explicit_limit_is_passed_unchanged(self):
        connection = FakeConnection([RECIPE_ROW])
        client = FakeEmbeddingClient([0.1] * 1536)

        search_similar_recipes(
            "egg recipes",
            5,
            client=client,
            database_pool=FakePool(connection),
        )

        self.assertEqual(connection.calls[0][1][2], 5)

    def test_blank_or_nontext_question_is_rejected_before_embedding(self):
        for question in ("", "   ", None):
            with self.subTest(question=question):
                client = FakeEmbeddingClient([0.1] * 1536)

                with self.assertRaisesRegex(ValueError, "nonempty text"):
                    search_similar_recipes(
                        question,
                        client=client,
                        database_pool=FakePool(FakeConnection([RECIPE_ROW])),
                    )

                self.assertEqual(client.calls, [])

    def test_invalid_limit_is_rejected_before_embedding_or_connection(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit):
                client = FakeEmbeddingClient([0.1] * 1536)
                database_pool = FakePool(FakeConnection([RECIPE_ROW]))

                with self.assertRaisesRegex(ValueError, "positive integer"):
                    search_similar_recipes(
                        "egg recipes",
                        limit,
                        client=client,
                        database_pool=database_pool,
                    )

                self.assertEqual(client.calls, [])
                self.assertEqual(database_pool.connection_count, 0)


class QueryConversationTests(unittest.TestCase):
    def test_process_query_sends_guardrails_history_and_recipe_context(self):
        connection = FakeConnection([RECIPE_ROW])
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        database_pool = FakePool(connection)
        chat = FakeChatClient(
            on_chat=lambda: self.assertFalse(database_pool.active),
        )
        client = SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        )
        history = [
            {"role": "user", "content": "I want a quick breakfast."},
            {"role": "assistant", "content": "Steamed eggs may work."},
        ]

        answer = process_query(
            "What are the ingredients?",
            history,
            client=client,
            database_pool=database_pool,
            limit=1,
        )

        self.assertEqual(answer, "Try the steamed eggs.")
        messages = chat.calls[0]["messages"]
        self.assertEqual(messages[0]["role"], "system")
        system_prompt = messages[0]["content"].lower()
        self.assertIn("do not invent", system_prompt)
        self.assertIn("title", system_prompt)
        self.assertIn("source url", system_prompt)
        self.assertIn("ingredients", system_prompt)
        self.assertIn("numbered list", system_prompt)
        self.assertIn("no external source link", system_prompt)
        self.assertEqual(messages[1:3], history[:2])
        self.assertIn("Steamed Eggs", messages[-1]["content"])
        self.assertIn("2 eggs", messages[-1]["content"])
        self.assertIn('"instructions"', messages[-1]["content"])
        self.assertIn('"group_name": "Egg mixture"', messages[-1]["content"])
        self.assertNotIn('"similarity_score"', messages[-1]["content"])
        self.assertNotIn("0.1", messages[-1]["content"])
        self.assertEqual(history[-2:], [
            {"role": "user", "content": "What are the ingredients?"},
            {"role": "assistant", "content": "Try the steamed eggs."},
        ])
        self.assertNotIn("Retrieved recipe context", history[-2]["content"])

    def test_failed_embedding_does_not_append_messages(self):
        connection = FakeConnection([RECIPE_ROW])
        embedding_client = FakeEmbeddingClient(
            [0.1] * 1536,
            error=RuntimeError("embedding unavailable"),
        )
        client = SimpleNamespace(embeddings=embedding_client.embeddings)
        history = [{"role": "user", "content": "Earlier question"}]

        with self.assertRaisesRegex(RuntimeError, "embedding unavailable"):
            process_query(
                "New question",
                history,
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(history, [{"role": "user", "content": "Earlier question"}])

    def test_failed_llm_call_does_not_append_messages(self):
        connection = FakeConnection([RECIPE_ROW])
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        chat = FakeChatClient(error=RuntimeError("LLM unavailable"))
        client = SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        )
        history = [{"role": "user", "content": "Earlier question"}]

        with self.assertRaisesRegex(RuntimeError, "LLM unavailable"):
            process_query(
                "New question",
                history,
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(history, [{"role": "user", "content": "Earlier question"}])

    def test_malformed_llm_response_does_not_append_messages(self):
        connection = FakeConnection([RECIPE_ROW])
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        chat = FakeChatClient(choices=[])
        client = SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        )
        history = []

        with self.assertRaisesRegex(ValueError, "at least one chat response"):
            process_query(
                "New question",
                history,
                client=client,
                database_pool=FakePool(connection),
            )

        self.assertEqual(history, [])

    def test_truncated_response_is_rejected_without_changing_history(self):
        chat = FakeChatClient(choices=[SimpleNamespace(
            finish_reason="length",
            message=SimpleNamespace(content="1. Prepare the sauce and"),
        )])
        client = SimpleNamespace(
            embeddings=FakeEmbeddingClient([0.1] * 1536),
            chat=chat,
        )
        history = [{"role": "user", "content": "I want sukiyaki."}]
        original_history = list(history)

        with self.assertRaisesRegex(ValueError, "cut off before completion"):
            process_query(
                "Give me the complete recipe",
                history,
                client=client,
                database_pool=FakePool(FakeConnection([RECIPE_ROW])),
            )

        self.assertEqual(history, original_history)

    def test_empty_retrieval_context_is_explicit(self):
        connection = FakeConnection([])
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        chat = FakeChatClient()
        client = SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        )

        process_query(
            "Something unavailable",
            [],
            client=client,
            database_pool=FakePool(connection),
        )

        self.assertIn(
            "No matching recipes were found.",
            chat.calls[0]["messages"][-1]["content"],
        )


if __name__ == "__main__":
    unittest.main()
