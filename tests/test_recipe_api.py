from contextlib import contextmanager
import unittest

from fastapi.testclient import TestClient

import app.db.recipes as recipe_db
from app.api import create_app
from app.db.recipes import get_recipe_by_slug, list_recipe_summaries


SUMMARY_ROW = (
    "steamed-eggs",
    "Steamed Eggs",
    ["breakfast"],
    ["eggs"],
    20,
    180,
    14,
    4,
    10,
)

DETAIL_METADATA_ROW = (
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
)

DETAIL_ROW = DETAIL_METADATA_ROW + (
    "Steam gently.",
    ["2 eggs", "1 cup water"],
    ["Whisk the eggs.", "Steam until set."],
    [{"position": 1, "group_position": 1, "group_name": "Egg mixture"}],
    [],
)


class FakeResult:
    def __init__(self, rows, row=None):
        self.rows = rows
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class ProjectionConnection:
    def __init__(self, rows=(), row=None):
        self.rows = rows
        self.row = row
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "WHERE r.slug" in sql:
            return FakeResult((), self.row)
        return FakeResult(self.rows)


class ApiPool:
    def __init__(self, connection):
        self.connection_value = connection
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
        yield self.connection_value


class RecipeProjectionTests(unittest.TestCase):
    def test_list_recipe_summaries_returns_home_page_card_fields(self):
        connection = ProjectionConnection(rows=[SUMMARY_ROW])

        results = list_recipe_summaries(connection)

        self.assertEqual(
            results[0],
            {
                "slug": "steamed-eggs",
                "title": "Steamed Eggs",
                "category": ["breakfast"],
                "tags": ["eggs"],
                "total_time_minutes": 20,
                "calories": 180,
                "protein": 14,
                "carbs": 4,
                "fat": 10,
            },
        )
        for field in (
            "id", "description", "cuisine", "servings", "source_label",
            "source_url", "ingredients", "instructions", "embedding",
        ):
            self.assertNotIn(field, results[0])
        sql = connection.calls[0][0]
        self.assertIn("ORDER BY r.title, r.slug", sql)
        self.assertNotIn("r.description", sql)
        self.assertNotIn("embedding", sql.lower())

    def test_get_recipe_by_slug_returns_complete_ordered_detail(self):
        connection = ProjectionConnection(row=DETAIL_ROW)

        result = get_recipe_by_slug(connection, "steamed-eggs")

        self.assertEqual(result["slug"], "steamed-eggs")
        self.assertEqual(result["ingredients"], ["2 eggs", "1 cup water"])
        self.assertEqual(result["instructions"], ["Whisk the eggs.", "Steam until set."])
        self.assertEqual(
            result["ingredient_groups"],
            [{"position": 1, "group_position": 1, "group_name": "Egg mixture"}],
        )
        self.assertEqual(result["instruction_groups"], [])
        self.assertEqual(connection.calls[0][1], ("steamed-eggs",))
        self.assertIn("ORDER BY ri.position", connection.calls[0][0])
        self.assertIn("ORDER BY rs.position", connection.calls[0][0])


class RecipeProjectionFieldTests(unittest.TestCase):
    def test_projection_fields_reuse_shared_groups_without_changing_order(self):
        expected_list = (
            "slug", "title", "category", "tags", "total_time_minutes",
            "calories", "protein", "carbs", "fat",
        )
        expected_metadata = (
            "slug", "title", "description", "category", "tags", "cuisine",
            "total_time_minutes", "servings", "calories", "protein", "carbs", "fat",
        )
        expected_source = ("source_label", "source_url")

        self.assertEqual(recipe_db.RECIPE_METADATA_FIELDS, expected_metadata)
        self.assertEqual(recipe_db.RECIPE_SOURCE_FIELDS, expected_source)
        self.assertEqual(
            recipe_db.RECIPE_SUMMARY_FIELDS,
            expected_list,
        )
        self.assertEqual(
            recipe_db.RECIPE_DETAIL_METADATA_FIELDS,
            recipe_db.RECIPE_METADATA_FIELDS + recipe_db.RECIPE_SOURCE_FIELDS,
        )
        self.assertEqual(
            recipe_db.RECIPE_DETAIL_FIELDS,
            recipe_db.RECIPE_DETAIL_METADATA_FIELDS + (
                "notes", "ingredients", "instructions", "ingredient_groups", "instruction_groups",
            ),
        )
        self.assertEqual(
            recipe_db.RECIPE_SEARCH_FIELDS,
            recipe_db.RECIPE_DETAIL_FIELDS + ("similarity_score",),
        )


class RecipeApiTests(unittest.TestCase):
    def test_list_endpoint_returns_condensed_recipe_cards(self):
        pool = ApiPool(ProjectionConnection(rows=[SUMMARY_ROW]))

        with TestClient(create_app(database_pool=pool)) as client:
            response = client.get("/api/recipes")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{
            "slug": "steamed-eggs",
            "title": "Steamed Eggs",
            "category": ["breakfast"],
            "tags": ["eggs"],
            "total_time_minutes": 20,
            "calories": 180,
            "protein": 14,
            "carbs": 4,
            "fat": 10,
        }])
        self.assertEqual(pool.enter_count, 1)
        self.assertEqual(pool.exit_count, 1)
        self.assertEqual(pool.connection_count, 1)

    def test_detail_endpoint_returns_complete_recipe_content(self):
        pool = ApiPool(ProjectionConnection(row=DETAIL_ROW))

        with TestClient(create_app(database_pool=pool)) as client:
            response = client.get("/api/recipes/steamed-eggs")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["slug"], "steamed-eggs")
        self.assertEqual(body["description"], "Silky savory eggs.")
        self.assertEqual(body["ingredients"], ["2 eggs", "1 cup water"])
        self.assertEqual(body["instructions"], ["Whisk the eggs.", "Steam until set."])
        self.assertEqual(
            body["ingredient_groups"],
            [{"position": 1, "group_position": 1, "group_name": "Egg mixture"}],
        )
        self.assertEqual(body["instruction_groups"], [])
        self.assertNotIn("id", body)
        self.assertNotIn("embedding", body)
        self.assertEqual(pool.enter_count, 1)
        self.assertEqual(pool.exit_count, 1)
        self.assertEqual(pool.connection_count, 1)

    def test_missing_slug_returns_not_found(self):
        pool = ApiPool(ProjectionConnection(row=None))

        with TestClient(create_app(database_pool=pool)) as client:
            response = client.get("/api/recipes/unknown-recipe")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "recipe not found: unknown-recipe"})


if __name__ == "__main__":
    unittest.main()
