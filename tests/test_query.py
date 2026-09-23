from contextlib import contextmanager
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.db.recipes import DEFAULT_SIMILARITY_THRESHOLD, find_similar_recipes
from app.rag.query import (
    QueryGenerationError,
    RecipeNotFoundError,
    build_recipe_cards,
    process_query,
    process_query_result,
)


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
    def __init__(self, rows, row=None):
        self.rows = rows
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, rows, row=None):
        self.rows = rows
        self.row = row
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "WHERE r.slug" in sql:
            return FakeResult((), self.row)
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


class QueryTestCase(unittest.TestCase):
    def setUp(self):
        self.openai_patch = patch("app.rag.query.OpenAI")
        self.openai_mock = self.openai_patch.start()
        self.addCleanup(self.openai_patch.stop)

    def use_client(self, client):
        client.close = lambda: None
        self.openai_mock.return_value = client
        return client


class RecipeDatabaseTests(QueryTestCase):
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
        self.assertIn("ORDER BY scored_recipes.similarity_score DESC", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertEqual(params[0], [0.1] * 1536)
        self.assertEqual(params[-2:], (DEFAULT_SIMILARITY_THRESHOLD, 2))

    def test_find_similar_recipes_rejects_invalid_limits_before_query(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit):
                connection = FakeConnection([RECIPE_ROW])

                with self.assertRaisesRegex(ValueError, "positive integer"):
                    find_similar_recipes(connection, [0.1] * 1536, limit)

                self.assertEqual(connection.calls, [])


class QueryRetrievalTests(QueryTestCase):
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
        embedding_client = FakeEmbeddingClient(
            [0.1] * 1536,
            on_embed=lambda: self.assertEqual(database_pool.connection_count, 0),
        )
        chat = FakeChatClient(
            on_chat=lambda: self.assertFalse(database_pool.active),
        )
        client = self.use_client(SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        ))

        result = process_query_result(
            "What can I make with eggs?",
            [],
            database_pool=database_pool,
        )

        self.assertEqual(result.recipe_cards[0]["title"], "Steamed Eggs")
        self.assertEqual(embedding_client.calls[0]["input"], "What can I make with eggs?")
        self.assertEqual(
            connection.calls[0][1][-2:],
            (DEFAULT_SIMILARITY_THRESHOLD, 3),
        )
        self.assertEqual(database_pool.connection_count, 1)

    def test_explicit_limit_is_passed_unchanged(self):
        connection = FakeConnection([RECIPE_ROW])
        client = self.use_client(SimpleNamespace(
            embeddings=FakeEmbeddingClient([0.1] * 1536).embeddings,
            chat=FakeChatClient(),
        ))

        process_query_result(
            "egg recipes",
            [],
            database_pool=FakePool(connection),
            limit=5,
        )

        self.assertEqual(
            connection.calls[0][1][-2:],
            (DEFAULT_SIMILARITY_THRESHOLD, 5),
        )

    def test_process_query_result_uses_database_threshold(self):
        connection = FakeConnection([RECIPE_ROW])
        database_pool = FakePool(connection)
        client = self.use_client(SimpleNamespace(
            embeddings=FakeEmbeddingClient([0.1] * 1536).embeddings,
            chat=FakeChatClient(),
        ))

        result = process_query_result(
            "What can I make with eggs?",
            [],
            database_pool=database_pool,
            limit=1,
        )

        self.assertEqual(result.answer, "Try the steamed eggs.")
        self.assertEqual(result.recipe_cards[0]["slug"], "steamed-eggs")
        self.assertEqual(
            connection.calls[0][1][-2:],
            (DEFAULT_SIMILARITY_THRESHOLD, 1),
        )

class QueryConversationTests(QueryTestCase):
    def test_process_query_sends_guardrails_history_and_recipe_context(self):
        connection = FakeConnection([RECIPE_ROW])
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        database_pool = FakePool(connection)
        chat = FakeChatClient(
            on_chat=lambda: self.assertFalse(database_pool.active),
        )
        client = self.use_client(SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        ))
        history = [
            {"role": "user", "content": "I want a quick breakfast."},
            {"role": "assistant", "content": "Steamed eggs may work."},
        ]

        answer = process_query(
            "What are the ingredients?",
            history,
            database_pool=database_pool,
            limit=1,
        )

        self.assertEqual(answer, "Try the steamed eggs.")
        messages = chat.calls[0]["messages"]
        self.assertEqual(messages[0]["role"], "system")
        system_prompt = messages[0]["content"].lower()
        self.assertIn("do not invent", system_prompt)
        self.assertIn("title", system_prompt)
        self.assertIn("short summary", system_prompt)
        self.assertIn("why it fits", system_prompt)
        self.assertIn("full ingredients", system_prompt)
        self.assertIn("explicitly asks", system_prompt)
        self.assertIn("unrelated to cooking or recipes", system_prompt)
        self.assertIn("short prose paragraph", system_prompt)
        self.assertIn("ordered list", system_prompt)
        self.assertIn("do not use bullet points", system_prompt)
        self.assertIn("selected recipe walkthrough", system_prompt)
        self.assertIn("ingredients and amounts used in that step", system_prompt)
        self.assertIn("do not copy the stored instructions verbatim", system_prompt)
        self.assertIn("do not repeat ingredient names or amounts in the step", system_prompt)
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
        client = self.use_client(SimpleNamespace(embeddings=embedding_client.embeddings))
        history = [{"role": "user", "content": "Earlier question"}]

        with self.assertRaisesRegex(RuntimeError, "embedding unavailable"):
            process_query(
                "New question",
                history,
                database_pool=FakePool(connection),
            )

        self.assertEqual(history, [{"role": "user", "content": "Earlier question"}])

    def test_failed_llm_call_does_not_append_messages(self):
        connection = FakeConnection([RECIPE_ROW])
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        chat = FakeChatClient(error=RuntimeError("LLM unavailable"))
        client = self.use_client(SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        ))
        history = [{"role": "user", "content": "Earlier question"}]

        with self.assertRaisesRegex(RuntimeError, "LLM unavailable"):
            process_query(
                "New question",
                history,
                database_pool=FakePool(connection),
            )

        self.assertEqual(history, [{"role": "user", "content": "Earlier question"}])

    def test_malformed_llm_response_does_not_append_messages(self):
        connection = FakeConnection([RECIPE_ROW])
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        chat = FakeChatClient(choices=[])
        client = self.use_client(SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        ))
        history = []

        with self.assertRaisesRegex(QueryGenerationError, "at least one chat response"):
            process_query(
                "New question",
                history,
                database_pool=FakePool(connection),
            )

        self.assertEqual(history, [])

    def test_truncated_response_is_rejected_without_changing_history(self):
        chat = FakeChatClient(choices=[SimpleNamespace(
            finish_reason="length",
            message=SimpleNamespace(content="1. Prepare the sauce and"),
        )])
        client = self.use_client(SimpleNamespace(
            embeddings=FakeEmbeddingClient([0.1] * 1536),
            chat=chat,
        ))
        history = [{"role": "user", "content": "I want sukiyaki."}]
        original_history = list(history)

        with self.assertRaisesRegex(QueryGenerationError, "cut off before completion"):
            process_query(
                "Give me the complete recipe",
                history,
                database_pool=FakePool(FakeConnection([RECIPE_ROW])),
            )

        self.assertEqual(history, original_history)

    def test_empty_retrieval_context_is_explicit(self):
        connection = FakeConnection([])
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        chat = FakeChatClient()
        client = self.use_client(SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        ))

        process_query(
            "Something unavailable",
            [],
            database_pool=FakePool(connection),
        )

        self.assertIn(
            "No matching recipes were found.",
            chat.calls[0]["messages"][-1]["content"],
        )

    def test_unrelated_question_uses_retrieval_and_prompt_guardrail(self):
        embedding_client = FakeEmbeddingClient([0.1] * 1536)
        chat = FakeChatClient(answer="I can help with recipes and cooking questions.")
        client = self.use_client(SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        ))
        database_pool = FakePool(FakeConnection([RECIPE_ROW]))

        result = process_query_result(
            "What is the capital of France?",
            [],
            database_pool=database_pool,
        )

        self.assertEqual(result.answer, "I can help with recipes and cooking questions.")
        self.assertEqual(result.recipe_cards[0]["slug"], "steamed-eggs")
        self.assertEqual(len(embedding_client.calls), 1)
        self.assertEqual(database_pool.connection_count, 1)
        system_prompt = chat.calls[0]["messages"][0]["content"].lower()
        self.assertIn("unrelated to cooking or recipes", system_prompt)
        self.assertIn("invite a recipe-related question", system_prompt)
        self.assertNotIn("greeting", system_prompt)

    def test_selected_recipe_context_uses_direct_lookup_without_similarity_search(self):
        connection = FakeConnection([RECIPE_ROW], row=RECIPE_ROW[:-1])
        embedding_client = FakeEmbeddingClient(
            [0.1] * 1536,
            on_embed=lambda: self.fail(
                "recipe-specific queries should not generate an embedding"
            ),
        )
        chat = FakeChatClient()
        client = self.use_client(SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=chat,
        ))
        database_pool = FakePool(connection)

        result = process_query_result(
            "What goes into the egg mixture?",
            [],
            database_pool=database_pool,
            limit=1,
            recipe_slug="steamed-eggs",
        )

        self.assertEqual(result.answer, "Try the steamed eggs.")
        context = chat.calls[0]["messages"][-1]["content"]
        self.assertIn('"ingredients": [\n      "2 eggs"', context)
        self.assertIn('"instructions": [\n      "Whisk the eggs."', context)
        self.assertIn('"group_name": "Egg mixture"', context)
        self.assertEqual(context.count('"slug": "steamed-eggs"'), 1)
        self.assertEqual(result.recipe_cards, [])
        self.assertEqual(embedding_client.calls, [])
        self.assertEqual(database_pool.connection_count, 1)
        self.assertEqual(len(connection.calls), 1)
        self.assertIn("WHERE r.slug", connection.calls[0][0])

    def test_missing_selected_recipe_raises_without_appending_history(self):
        connection = FakeConnection([RECIPE_ROW], row=None)
        embedding_client = FakeEmbeddingClient(
            [0.1] * 1536,
            on_embed=lambda: self.fail(
                "recipe-specific queries should not generate an embedding"
            ),
        )
        client = self.use_client(SimpleNamespace(
            embeddings=embedding_client.embeddings,
            chat=FakeChatClient(),
        ))
        history = [{"role": "user", "content": "Earlier question"}]

        with self.assertRaises(RecipeNotFoundError):
            process_query_result(
                "Tell me about this recipe",
                history,
                database_pool=FakePool(connection),
                recipe_slug="missing-recipe",
            )

        self.assertEqual(history, [{"role": "user", "content": "Earlier question"}])
        self.assertEqual(embedding_client.calls, [])
        self.assertEqual(len(connection.calls), 1)


if __name__ == "__main__":
    unittest.main()
