"""Grouping boundaries, corpus preservation, and grouped persistence checks."""

from pathlib import Path
import tempfile
import unittest

import app.ingestion.groups as recipe_groups
from app.db.recipes import save_recipe
from app.ingestion.groups import group_at, normalize_recipe_sections
from app.ingestion.load_embeddings import build_embedding_text, parse_recipe_file
from tests.test_load_embeddings import FakeConnection, RECIPE_MARKDOWN


class RecipeGroupTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipe.md"
            path.write_text(text, encoding="utf-8")
            return parse_recipe_file(path)

    def test_groups_preserve_continuations_metadata_and_order(self):
        recipe = self.parse(RECIPE_MARKDOWN.replace(
            "- 2 chicken", "### Sauce\n- 2 chicken"
        ).replace("- 1 cabbage", "### <!-- unnamed group -->\n- 1 cabbage")
            .replace("1. Simmer", "### Cook\n1. Simmer"))
        self.assertEqual(recipe["total_time_minutes"], 45)
        self.assertEqual(recipe["ingredients"], ["2 chicken breasts sliced thinly", "1 cabbage"])
        self.assertEqual(recipe["ingredient_groups"], [
            {"start": 1, "name": "Sauce"}, {"start": 2, "name": None},
        ])
        self.assertEqual(recipe["instruction_groups"], [{"start": 1, "name": "Cook"}])
        normalized = normalize_recipe_sections(recipe)
        text = build_embedding_text(normalized)
        self.assertIn("Sauce\n- 2 chicken breasts sliced thinly", text)
        self.assertIn("Cook\n1. Simmer the chicken. Skim the broth.", text)
        self.assertNotIn("None", text)
        conn = FakeConnection()
        save_recipe(conn, normalized, [0.1])
        upsert = next(params for sql, params in conn.calls if "INSERT INTO recipes" in sql)
        self.assertEqual(upsert["ingredient_sections"].obj, [
            {"kind": "group", "name": "Sauce", "items": ["2 chicken breasts sliced thinly"]},
            {"kind": "group", "name": None, "items": ["1 cabbage"]},
        ])
        self.assertEqual(upsert["instruction_sections"].obj, [
            {"kind": "group", "name": "Cook", "items": [
                "Simmer the chicken. Skim the broth.", "Add the cabbage.",
            ]},
        ])
        self.assertFalse(any(
            "recipe_ingredients" in sql or "recipe_steps" in sql
            for sql, _ in conn.calls
        ))

    def test_normalizes_parser_fields_to_canonical_sections(self):
        raw = self.parse(RECIPE_MARKDOWN.replace(
            "- 2 chicken", "### Sauce\n- 2 chicken"
        ))

        normalized = normalize_recipe_sections(raw)

        self.assertEqual(normalized["ingredient_sections"], [
            {"kind": "group", "name": "Sauce", "items": [
                "2 chicken breasts sliced thinly", "1 cabbage",
            ]},
        ])
        self.assertEqual(normalized["instruction_sections"], [
            {"kind": "ungrouped", "name": None, "items": [
                "Simmer the chicken. Skim the broth.", "Add the cabbage.",
            ]},
        ])
        self.assertNotIn("ingredients", normalized)
        self.assertNotIn("instructions", normalized)
        self.assertNotIn("ingredient_groups", normalized)
        self.assertNotIn("instruction_groups", normalized)
        self.assertEqual(normalized["slug"], raw["slug"])

    def test_parser_boundaries_normalize_to_ordered_sections(self):
        items_to_sections = getattr(recipe_groups, "items_to_sections", None)
        self.assertIsNotNone(items_to_sections, "items_to_sections helper is missing")
        if items_to_sections is None:
            return

        items = ["before", "soy sauce", "vinegar", "sugar", "pepper"]
        groups = [
            {"start": 2, "name": "For sauce"},
            {"start": 4, "name": None},
            {"start": 5, "name": "For sauce"},
        ]
        sections = items_to_sections(items, groups)

        self.assertEqual(sections, [
            {"kind": "ungrouped", "name": None, "items": ["before"]},
            {"kind": "group", "name": "For sauce", "items": ["soy sauce", "vinegar"]},
            {"kind": "group", "name": None, "items": ["sugar"]},
            {"kind": "group", "name": "For sauce", "items": ["pepper"]},
        ])

    def test_all_ungrouped_items_use_one_section(self):
        items_to_sections = getattr(recipe_groups, "items_to_sections", None)
        self.assertIsNotNone(items_to_sections, "items_to_sections helper is missing")
        if items_to_sections is None:
            return

        sections = items_to_sections(["first", "second"], [])
        self.assertEqual(sections, [{
            "kind": "ungrouped", "name": None, "items": ["first", "second"],
        }])

    def test_ungrouped_and_repeated_names(self):
        self.assertEqual(self.parse(RECIPE_MARKDOWN)["ingredient_groups"], [])
        recipe = self.parse(RECIPE_MARKDOWN.replace(
            "- 2 chicken", "### Sauce\n- 2 chicken"
        ).replace("- 1 cabbage", "### Sauce\n- 1 cabbage"))
        self.assertEqual(group_at(recipe["ingredient_groups"], 2), (2, "Sauce"))
        self.assertEqual(group_at([{"start": 2, "name": "Sauce"}], 1), (None, None))

    def test_empty_groups_are_rejected(self):
        for headings in ("### \n", "### Sauce\n### Other\n"):
            with self.subTest(headings=headings), self.assertRaisesRegex(ValueError, "empty group"):
                self.parse(RECIPE_MARKDOWN.replace("- 2 chicken", headings + "- 2 chicken"))
        with self.assertRaisesRegex(ValueError, "empty group"):
            self.parse(RECIPE_MARKDOWN.replace("## Instructions", "### Empty\n\n## Instructions"))

if __name__ == "__main__":
    unittest.main()
