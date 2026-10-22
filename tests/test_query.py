from contextlib import contextmanager
import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.db import recipes as recipe_repository
from app.db.recipes import DEFAULT_SIMILARITY_THRESHOLD, find_similar_recipes
from app.rag import query as query_module
from app.rag.tools import RECIPE_TOOLS, build_recipe_cards
from app.settings import DEFAULT_RECIPE_LIMIT, EMBEDDING_DIMENSIONS
from app.rag.query import (
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
    [{"kind": "group", "name": "Egg mixture", "items": ["2 eggs", "1 cup water"]}],
    [{"kind": "ungrouped", "name": None, "items": ["Whisk the eggs.", "Steam until set."]}],
    0.91,
)
ANCHOR_ROW = RECIPE_ROW[:2] + ([0.2] * EMBEDDING_DIMENSIONS,)


def recipe_with_score(score, *, slug=None, title=None):
    row = list(RECIPE_ROW)
    row[-1] = score
    if slug is not None:
        row[0] = slug
    if title is not None:
        row[1] = title
    return tuple(row)


def provider_tool_call(name, arguments, call_id="call-1"):
    return SimpleNamespace(
        id=f"fc_{call_id}",
        type="function_call",
        status="completed",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
    )


def provider_response(content=None, tool_calls=None, finish_reason="stop", extra_output=None, recipe_slugs=()):
    status = "incomplete" if finish_reason == "length" else "completed"
    return SimpleNamespace(
        output=[*(extra_output or []), *(tool_calls or [])],
        output_text=content,
        recipe_slugs=list(recipe_slugs),
        status=status,
        incomplete_details=(
            SimpleNamespace(reason="max_output_tokens")
            if status == "incomplete"
            else None
        ),
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
    def __init__(self, answer="Try the steamed eggs.", error=None, on_chat=None, responses=None):
        self.answer = answer
        self.error = error
        self.on_chat = on_chat
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
        if self.on_chat:
            self.on_chat()
        if self.error:
            raise self.error
        if self.response_queue:
            return self.response_queue.pop(0)
        return provider_response(content=self.answer)


class QueryTestCase(unittest.TestCase):
    def setUp(self):
        self.openai_patch = patch("app.rag.query.OpenAI")
        self.openai_mock = self.openai_patch.start()
        self.addCleanup(self.openai_patch.stop)

    def use_client(self, client):
        client.close = lambda: None
        self.openai_mock.return_value = client
        return client


class QueryRoutingTests(QueryTestCase):
    def test_direct_how_to_skips_embedding_database_and_answer_completion(self):
        connection = FakeConnection([RECIPE_ROW])
        database_pool = FakePool(connection)
        embedding_client = FakeEmbeddingClient([0.1] * EMBEDDING_DIMENSIONS)
        chat = FakeChatClient(
            answer=(
                "Roast broccoli at high heat until browned. Crumbs can help you "
                "find a specific recipe."
            ),
        )
        self.use_client(SimpleNamespace(embeddings=embedding_client, responses=chat.responses))

        result = process_query_result(
            "How do I roast broccoli?",
            [],
            database_pool=database_pool,
        )

        self.assertEqual(result.recipe_cards, [])
        self.assertEqual(result.retrieved_context, [])
        self.assertEqual(embedding_client.calls, [])
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(len(chat.calls), 1)

    def test_general_nutrition_and_unrelated_requests_use_direct_answers(self):
        cases = (
            (
                "Is protein important for muscle recovery?",
                "I'm Crumbs, a recipe assistant, and I don't have information to answer that.",
            ),
            (
                "What is the capital of France?",
                "I'm Crumbs, a recipe assistant, and I don't have information to answer that.",
            ),
        )
        for question, answer in cases:
            with self.subTest(question=question):
                connection = FakeConnection([RECIPE_ROW])
                database_pool = FakePool(connection)
                embedding_client = FakeEmbeddingClient([0.1] * EMBEDDING_DIMENSIONS)
                chat = FakeChatClient(answer=answer)
                self.use_client(SimpleNamespace(embeddings=embedding_client, responses=chat.responses))

                result = process_query_result(question, [], database_pool=database_pool)

                self.assertEqual(result.answer, answer)
                self.assertEqual(result.recipe_cards, [])
                self.assertEqual(embedding_client.calls, [])
                self.assertEqual(database_pool.connection_count, 0)
                self.assertEqual(len(chat.calls), 1)
                self.assertIn("does not have information to answer", chat.calls[0]["instructions"])
                self.assertIn(
                    "do not answer from general knowledge",
                    chat.calls[0]["instructions"].lower(),
                )

    def test_initial_request_uses_history_and_offers_only_recipe_tools(self):
        chat = FakeChatClient(answer="Which recipe would you like to discuss?")
        history = [
            {"role": "user", "content": "I wanted chicken breakfast ideas."},
            {
                "role": "assistant",
                "content": "1. Chicken Pancakes. 2. Chicken Sausage Bowl.",
                "recipe_references": [
                    {"title": "Chicken Pancakes", "slug": "chicken-pancakes"},
                    {"title": "Chicken Sausage Bowl", "slug": "chicken-sausage-bowl"},
                ],
            },
        ]
        self.use_client(SimpleNamespace(
            embeddings=FakeEmbeddingClient([0.1] * EMBEDDING_DIMENSIONS),
            responses=chat.responses,
        ))

        result = process_query_result(
            "Tell me more about the first chicken recipe.",
            history,
        )

        self.assertEqual(result.answer, "Which recipe would you like to discuss?")
        self.assertEqual(chat.calls[0]["input"], [
            {"role": "user", "content": "I wanted chicken breakfast ideas."},
            {"role": "assistant", "content": "1. Chicken Pancakes. 2. Chicken Sausage Bowl."},
            {"role": "user", "content": "Tell me more about the first chicken recipe."},
        ])
        router_prompt = chat.calls[0]["instructions"]
        self.assertEqual(router_prompt, query_module.ROUTER_SYSTEM_PROMPT)
        self.assertIn("<tools>", router_prompt)
        self.assertIn("</tools>", router_prompt)
        self.assertIn("get_recipe_detail", router_prompt)
        self.assertIn("get_recipes", router_prompt)
        self.assertIn("recipe collection", router_prompt.lower())
        self.assertIn("do not answer from general knowledge", router_prompt.lower())
        self.assertEqual(chat.calls[0]["tools"], RECIPE_TOOLS)
        self.assertEqual(chat.calls[0]["tool_choice"], "auto")


class QueryToolExecutionTests(QueryTestCase):
    def test_existing_and_newer_models_use_the_responses_api(self):
        for model in ("gpt-4o-mini", "gpt-6-luna"):
            with self.subTest(model=model), patch.object(query_module, "CHAT_MODEL", model):
                _, client = self.client_for_tools([
                    provider_tool_call("get_recipe_detail", {"slug": "steamed-eggs"})
                ])

                self.execute_tools(
                    "Tell me about Steamed Eggs",
                    [],
                    FakePool(FakeConnection([], row=RECIPE_ROW[:-1])),
                )

                self.assertEqual([call["model"] for call in client.calls], [model, model])
                self.assertTrue(all("messages" not in call for call in client.calls))
                self.assertTrue(all("reasoning_effort" not in call for call in client.calls))

    def client_for_tools(
        self,
        tool_calls,
        answer="Here is the result.",
        embedding=None,
        response_output_items=None,
        recipe_slugs=(),
    ):
        embedding = embedding or FakeEmbeddingClient([0.1] * EMBEDDING_DIMENSIONS)
        chat = FakeChatClient(responses=[
            provider_response(tool_calls=tool_calls, extra_output=response_output_items),
            provider_response(content=answer, recipe_slugs=recipe_slugs),
        ])
        self.use_client(SimpleNamespace(embeddings=embedding, responses=chat.responses))
        return embedding, chat

    def execute_tools(self, question, history, database_pool, recipe_slug=None):
        return process_query_result(
            question,
            history,
            database_pool=database_pool,
            recipe_slug=recipe_slug,
        )

    def tool_results(self, chat):
        return [
            json.loads(item["output"])
            for item in chat.calls[-1]["input"]
            if isinstance(item, dict) and item.get("type") == "function_call_output"
        ]

    def test_new_detail_returns_full_content_without_a_card(self):
        detail_call = provider_tool_call(
            "get_recipe_detail",
            {"slug": "steamed-eggs"},
        )
        embedding, chat = self.client_for_tools(
            [detail_call],
            answer="Steamed Eggs use eggs and water.",
            embedding=FakeEmbeddingClient(
                [0.1] * EMBEDDING_DIMENSIONS,
                error=RuntimeError("detail lookup must not embed"),
            ),
        )
        connection = FakeConnection([], row=RECIPE_ROW[:-1])
        database_pool = FakePool(connection)
        history = []

        result = self.execute_tools(
            "Tell me about Steamed Eggs",
            history,
            database_pool,
        )

        self.assertEqual(result.recipe_cards, [])
        self.assertEqual(embedding.calls, [])
        self.assertEqual(database_pool.connection_count, 1)
        self.assertEqual(len(connection.calls), 1)
        self.assertTrue(connection.calls[0][0].lstrip().startswith("SELECT"))
        detail_result = self.tool_results(chat)[0]
        self.assertEqual(set(detail_result), {"recipe"})
        self.assertEqual(detail_result["recipe"]["ingredient_sections"], RECIPE_ROW[-3])
        self.assertEqual(detail_result["recipe"]["instruction_sections"], RECIPE_ROW[-2])
        self.assertIn("2 eggs", chat.calls[-1]["input"][-1]["output"])
        self.assertNotIn("tools", chat.calls[-1])
        self.assertTrue(chat.calls[-1]["instructions"].startswith(query_module.ANSWER_SYSTEM_PROMPT))
        self.assertEqual(len(chat.calls), 2)
        self.assertEqual(history[-2:], [
            {"role": "user", "content": "Tell me about Steamed Eggs"},
            {"role": "assistant", "content": "Steamed Eggs use eggs and water."},
        ])

    def test_detail_returns_no_card_for_active_or_previously_shown_recipe(self):
        for recipe_slug, history in (
            ("steamed-eggs", []),
            (None, [{
                "role": "assistant",
                "content": "Here are the options.",
                "recipe_references": [{
                    "title": "Steamed Eggs",
                    "slug": "steamed-eggs",
                }],
            }]),
        ):
            with self.subTest(recipe_slug=recipe_slug, history=history):
                _, _ = self.client_for_tools([
                    provider_tool_call("get_recipe_detail", {"slug": "steamed-eggs"})
                ])
                connection = FakeConnection([], row=RECIPE_ROW[:-1])
                result = self.execute_tools(
                    "What ingredients does it use?",
                    history,
                    FakePool(connection),
                    recipe_slug=recipe_slug,
                )
                self.assertEqual(result.recipe_cards, [])
                self.assertIn("2 eggs", json.dumps(result.retrieved_context))

    def test_missing_exact_detail_does_not_embed_or_search(self):
        embedding, chat = self.client_for_tools([
            provider_tool_call("get_recipe_detail", {"slug": "missing-recipe"})
        ])
        connection = FakeConnection([RECIPE_ROW], row=None)
        database_pool = FakePool(connection)

        result = self.execute_tools(
            "Tell me about Missing Recipe",
            [],
            database_pool,
        )

        self.assertEqual(result.recipe_cards, [])
        self.assertEqual(embedding.calls, [])
        self.assertEqual(database_pool.connection_count, 1)
        self.assertEqual(len(connection.calls), 1)
        self.assertIn("WHERE r.slug = %s", connection.calls[0][0])
        self.assertEqual(self.tool_results(chat)[0], {"recipe": None})
        self.assertIn('"recipe": null', chat.calls[-1]["input"][-1]["output"])
        self.assertIn("recipe is null", chat.calls[-1]["instructions"])
        self.assertIn("do not search for substitutes", chat.calls[-1]["instructions"])

    def test_model_slug_is_passed_directly_to_database_lookup(self):
        _, chat = self.client_for_tools([
            provider_tool_call("get_recipe_detail", {"slug": "Steamed_Eggs"})
        ])
        database_pool = FakePool(FakeConnection([RECIPE_ROW], row=RECIPE_ROW[:-1]))

        result = self.execute_tools(
            "Tell me about Steamed Eggs",
            [],
            database_pool,
        )

        self.assertEqual(database_pool.connection_count, 1)
        self.assertEqual(database_pool.connection_value.calls[0][1], ("Steamed_Eggs",))
        self.assertEqual(result.recipe_cards, [])
        self.assertEqual(len(chat.calls), 2)

    def test_general_search_embeds_input_and_only_presents_strong_results_by_default(self):
        rows = [
            recipe_with_score(0.31, slug="protein-pancakes", title="Protein Pancakes"),
            recipe_with_score(0.3, slug="egg-pancakes", title="Egg Pancakes"),
            recipe_with_score(0.29, slug="cottage-cheese-pancakes", title="Cottage Cheese Pancakes"),
        ]
        embedding, chat = self.client_for_tools([
            provider_tool_call("get_recipes", {"input": "high protein pancakes"})
        ], recipe_slugs=['protein-pancakes'])
        connection = FakeConnection(rows)

        result = self.execute_tools(
            "Find high protein pancakes",
            [],
            FakePool(connection),
        )

        self.assertEqual(embedding.calls[0]["input"], "high protein pancakes")
        self.assertEqual(len(connection.calls), 1)
        sql, params = connection.calls[0]
        self.assertNotIn("scored_recipes.similarity_score >=", sql)
        self.assertEqual(params[-1], DEFAULT_RECIPE_LIMIT)
        self.assertEqual([card["slug"] for card in result.recipe_cards], ["protein-pancakes"])
        search_result = self.tool_results(chat)[0]
        self.assertEqual(set(search_result), {"matches"})
        self.assertEqual(search_result["matches"][0]["match_strength"], "strong")
        model_context = chat.calls[-1]["input"][-1]["output"]
        self.assertNotIn("ingredient_sections", model_context)
        self.assertNotIn("instruction_sections", model_context)
        self.assertNotIn("embedding", model_context)
        self.assertNotIn("source_url", model_context)

    def test_explicit_count_fills_short_strong_set_with_weak_matches(self):
        rows = [
            recipe_with_score(0.31, slug="protein-pancakes", title="Protein Pancakes"),
            recipe_with_score(0.3, slug="egg-pancakes", title="Egg Pancakes"),
            recipe_with_score(0.29, slug="cottage-cheese-pancakes", title="Cottage Cheese Pancakes"),
        ]
        _, chat = self.client_for_tools([
            provider_tool_call("get_recipes", {
                "input": "high protein pancakes",
                "limit": 3,
            })
        ], recipe_slugs=['protein-pancakes', 'egg-pancakes', 'cottage-cheese-pancakes'])
        connection = FakeConnection(rows)

        result = self.execute_tools("Show me 3 pancake recipes", [], FakePool(connection))

        self.assertEqual([card["slug"] for card in result.recipe_cards], [
            "protein-pancakes",
            "egg-pancakes",
            "cottage-cheese-pancakes",
        ])
        matches = self.tool_results(chat)[0]["matches"]
        self.assertEqual([item["match_strength"] for item in matches], [
            "strong", "weak", "weak",
        ])
        self.assertIn("imperfect", query_module.ANSWER_SYSTEM_PROMPT.lower())

    def test_exact_threshold_is_weak_and_no_strong_results_still_get_cards(self):
        rows = [
            recipe_with_score(0.3, slug="egg-pancakes", title="Egg Pancakes"),
            recipe_with_score(0.29, slug="cottage-cheese-pancakes", title="Cottage Cheese Pancakes"),
        ]
        _, chat = self.client_for_tools([
            provider_tool_call("get_recipes", {"input": "pancakes"})
        ], recipe_slugs=['egg-pancakes', 'cottage-cheese-pancakes'])

        result = self.execute_tools(
            "Find pancake recipes",
            [],
            FakePool(FakeConnection(rows)),
        )

        self.assertEqual(len(result.recipe_cards), 2)
        search_result = self.tool_results(chat)[0]
        self.assertEqual(set(search_result), {"matches"})
        self.assertEqual(
            [item["match_strength"] for item in search_result["matches"]],
            ["weak", "weak"],
        )

    def test_limit_ten_and_empty_search_results_are_handled_in_one_query(self):
        _, chat = self.client_for_tools([
            provider_tool_call("get_recipes", {"input": "breakfast", "limit": 10})
        ])
        connection = FakeConnection([])

        result = self.execute_tools("Show 10 breakfast recipes", [], FakePool(connection))

        self.assertEqual(result.recipe_cards, [])
        self.assertEqual(len(connection.calls), 1)
        self.assertEqual(connection.calls[0][1][-1], 10)
        self.assertEqual(self.tool_results(chat)[0]["matches"], [])

    def test_anchor_search_uses_stored_vector_and_excludes_anchor(self):
        candidate = recipe_with_score(0.4, slug="egg-custard", title="Egg Custard")
        _, chat = self.client_for_tools([
            provider_tool_call("get_recipes", {
                "input": "recipes like these eggs",
                "similar_to_slug": "steamed-eggs",
                "limit": 2,
            })
        ], embedding=FakeEmbeddingClient(
            [0.1] * EMBEDDING_DIMENSIONS,
            error=RuntimeError("anchored search must not embed"),
        ), recipe_slugs=['egg-custard'])
        connection = FakeConnection([candidate], row=ANCHOR_ROW)
        database_pool = FakePool(connection)

        result = self.execute_tools(
            "Find recipes similar to Steamed Eggs",
            [],
            database_pool,
        )

        self.assertEqual(len(connection.calls), 2)
        self.assertIn("WHERE r.slug = %s", connection.calls[0][0])
        self.assertNotIn("ingredient_sections", connection.calls[0][0])
        self.assertIn("scored_recipes.slug <> %s", connection.calls[1][0])
        self.assertNotIn("scored_recipes.similarity_score >=", connection.calls[1][0])
        self.assertEqual(connection.calls[1][1][0], [0.2] * EMBEDDING_DIMENSIONS)
        self.assertEqual(connection.calls[1][1][-2:], ("steamed-eggs", 2))
        self.assertEqual(result.recipe_cards[0]["slug"], "egg-custard")
        tool_result = self.tool_results(chat)[0]
        self.assertEqual(tool_result["anchor"]["title"], "Steamed Eggs")
        self.assertNotIn("embedding", json.dumps(tool_result))
        self.assertNotIn("ingredient_sections", json.dumps(tool_result))

    def test_combined_detail_and_search_calls_precede_one_answer_and_never_write(self):
        calls = [
            provider_tool_call("get_recipe_detail", {"slug": "steamed-eggs"}, "call-detail"),
            provider_tool_call("get_recipes", {
                "input": "breakfast eggs",
                "limit": 2,
            }, "call-search"),
        ]
        reasoning_item = {"type": "reasoning", "id": "rs_test", "summary": []}
        _, chat = self.client_for_tools(calls, response_output_items=[reasoning_item], recipe_slugs=['egg-custard'])
        connection = FakeConnection(
            [recipe_with_score(0.42, slug="egg-custard", title="Egg Custard")],
            row=RECIPE_ROW[:-1],
        )
        database_pool = FakePool(connection)

        result = self.execute_tools(
            "Tell me about Steamed Eggs and find recipes similar to it",
            [],
            database_pool,
        )

        self.assertEqual(len(chat.calls), 2)
        self.assertEqual(chat.calls[0]["tool_choice"], "auto")
        self.assertNotIn("tools", chat.calls[1])
        self.assertIn(reasoning_item, chat.calls[1]["input"])
        self.assertTrue(any(
            getattr(item, "call_id", None) == "call-detail"
            for item in chat.calls[1]["input"]
        ))
        self.assertEqual(
            sum(
                item.get("type") == "function_call_output"
                for item in chat.calls[1]["input"]
                if isinstance(item, dict)
            ),
            2,
        )
        self.assertEqual([card["slug"] for card in result.recipe_cards], [
            "egg-custard",
        ])
        self.assertEqual(result.recipe_cards[0]["similarity_score"], 0.42)
        self.assertTrue(all(
            sql.lstrip().upper().startswith("SELECT")
            for sql, _ in connection.calls
        ))

    def test_missing_similarity_anchor_returns_null_without_embedding_or_search(self):
        embedding, chat = self.client_for_tools([
            provider_tool_call("get_recipes", {
                "input": "similar to Missing Recipe", "similar_to_slug": "missing",
            })
        ])
        connection = FakeConnection([RECIPE_ROW], row=None)
        result = self.execute_tools("Similar to Missing Recipe?", [], FakePool(connection))
        self.assertEqual(self.tool_results(chat), [{"anchor": None, "matches": []}])
        self.assertEqual(result.recipe_cards, [])
        self.assertEqual(len(connection.calls), 1)
        self.assertEqual(embedding.calls, [])
        self.assertIn("anchor: null", chat.calls[-1]["instructions"])

    def test_anchor_without_embedding_does_not_generate_a_replacement_vector(self):
        embedding, chat = self.client_for_tools([
            provider_tool_call("get_recipes", {
                "input": "similar eggs", "similar_to_slug": "steamed-eggs",
            })
        ])
        connection = FakeConnection([RECIPE_ROW], row=("steamed-eggs", "Steamed Eggs", None))
        result = self.execute_tools("Similar eggs?", [], FakePool(connection))
        self.assertEqual(result.recipe_cards, [])
        self.assertEqual(self.tool_results(chat), [{
            "anchor": {"slug": "steamed-eggs", "title": "Steamed Eggs"}, "matches": [],
        }])
        self.assertEqual(len(connection.calls), 1)
        self.assertEqual(embedding.calls, [])

    def test_unknown_tool_fails_before_database_or_embedding_access(self):
        embedding, chat = self.client_for_tools([
            provider_tool_call("delete_recipe", {"slug": "steamed-eggs"})
        ])
        database_pool = FakePool(FakeConnection([RECIPE_ROW]))
        with self.assertRaisesRegex(ValueError, "unknown recipe tool"):
            self.execute_tools("Delete eggs", [], database_pool)
        self.assertEqual(database_pool.connection_count, 0)
        self.assertEqual(embedding.calls, [])
        self.assertEqual(len(chat.calls), 1)


class RecipeDatabaseTests(QueryTestCase):
    def test_embedding_lookup_returns_only_identity_and_stored_embedding(self):
        connection = FakeConnection([], row=ANCHOR_ROW)
        anchor = recipe_repository.get_recipe_embedding(
            connection,
            "steamed-eggs",
        )

        self.assertEqual(anchor["slug"], "steamed-eggs")
        self.assertEqual(anchor["title"], "Steamed Eggs")
        self.assertEqual(anchor["embedding"], [0.2] * EMBEDDING_DIMENSIONS)
        self.assertEqual(set(anchor), {"slug", "title", "embedding"})
        self.assertNotIn("ingredient_sections", anchor)
        self.assertNotIn("instruction_sections", anchor)
        sql, params = connection.calls[0]
        self.assertIn("WHERE r.slug = %s", sql)
        self.assertIn("r.embedding::real[] AS embedding", sql)
        self.assertNotIn("steamed-eggs", sql)
        self.assertNotIn("ingredient_sections", sql)
        self.assertNotIn("instruction_sections", sql)
        self.assertEqual(params, ("steamed-eggs",))

    def test_embedding_lookup_returns_none_for_missing_similarity_anchor(self):
        self.assertIsNone(recipe_repository.get_recipe_embedding(
            FakeConnection([], row=None),
            "missing-recipe",
        ))

    def test_chat_search_can_skip_threshold_and_exclude_its_anchor(self):
        parameters = inspect.signature(find_similar_recipes).parameters
        self.assertIn("minimum_similarity", parameters)
        self.assertIn("exclude_slug", parameters)
        if "minimum_similarity" not in parameters or "exclude_slug" not in parameters:
            return

        vector = [0.1] * EMBEDDING_DIMENSIONS
        connection = FakeConnection([RECIPE_ROW])
        results = find_similar_recipes(
            connection,
            vector,
            2,
            minimum_similarity=None,
            exclude_slug="anchor-recipe",
        )

        self.assertEqual(results[0]["slug"], "steamed-eggs")
        sql, params = connection.calls[0]
        self.assertIn("scored_recipes.slug <> %s", sql)
        self.assertNotIn("scored_recipes.similarity_score >=", sql)
        self.assertIn("ORDER BY scored_recipes.similarity_score DESC", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertEqual(params, (vector, "anchor-recipe", 2))

    def test_find_similar_recipes_returns_full_context_and_score(self):
        connection = FakeConnection([RECIPE_ROW])

        results = find_similar_recipes(connection, [0.1] * EMBEDDING_DIMENSIONS, 2)

        self.assertEqual(results[0]["slug"], "steamed-eggs")
        self.assertEqual(results[0]["similarity_score"], 0.91)
        self.assertEqual(results[0]["ingredient_sections"], RECIPE_ROW[-3])
        self.assertEqual(results[0]["instruction_sections"], RECIPE_ROW[-2])
        self.assertNotIn("ingredients", results[0])
        self.assertNotIn("instructions", results[0])
        self.assertNotIn("ingredient_groups", results[0])
        self.assertNotIn("instruction_groups", results[0])
        self.assertNotIn("id", results[0])
        self.assertNotIn("embedding", results[0])

        sql, params = connection.calls[0]
        self.assertIn("similarity_score", sql)
        self.assertIn("embedding IS NOT NULL", sql)
        self.assertIn("ORDER BY scored_recipes.similarity_score DESC", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertIn("r.ingredient_sections", sql)
        self.assertIn("r.instruction_sections", sql)
        self.assertNotIn("recipe_ingredients", sql)
        self.assertNotIn("recipe_steps", sql)
        self.assertEqual(params[0], [0.1] * EMBEDDING_DIMENSIONS)
        self.assertEqual(params[-2:], (DEFAULT_SIMILARITY_THRESHOLD, 2))

    def test_find_similar_recipes_rejects_invalid_limits_before_query(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit):
                connection = FakeConnection([RECIPE_ROW])

                with self.assertRaisesRegex(ValueError, "positive integer"):
                    find_similar_recipes(connection, [0.1] * EMBEDDING_DIMENSIONS, limit)

                self.assertEqual(connection.calls, [])


class QueryCardTests(QueryTestCase):
    def test_build_recipe_cards_keeps_scores_and_allows_missing_scores(self):
        common = {
            "slug": "steamed-eggs",
            "title": "Steamed Eggs",
            "category": ["breakfast"],
            "tags": ["eggs"],
            "total_time_minutes": 20,
            "calories": 180,
            "protein": 14,
            "carbs": 4,
            "fat": 10,
        }

        cards = build_recipe_cards([
            {**common, "similarity_score": 0.91},
            {**common, "slug": "without-score", "similarity_score": None},
        ])

        self.assertEqual(cards[0]["similarity_score"], 0.91)
        self.assertIsNone(cards[1]["similarity_score"])
        self.assertNotIn("description", cards[0])
        self.assertNotIn("ingredients", cards[0])


if __name__ == "__main__":
    unittest.main()
