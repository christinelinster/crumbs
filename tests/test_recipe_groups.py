"""Grouping boundaries, corpus preservation, and grouped persistence checks."""

from pathlib import Path
import tempfile
import unittest

from app.db.recipes import save_recipe
from app.ingestion.groups import group_at
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
        text = build_embedding_text(recipe)
        self.assertIn("Sauce\n- 2 chicken breasts sliced thinly", text)
        self.assertIn("Cook\n1. Simmer the chicken. Skim the broth.", text)
        self.assertNotIn("None", text)
        conn = FakeConnection()
        save_recipe(conn, recipe, [0.1])
        ingredients = [p for sql, p in conn.calls if "INSERT INTO recipe_ingredients" in sql]
        self.assertEqual([p[-2:] for p in ingredients], [(1, "Sauce"), (2, None)])
        steps = [p for sql, p in conn.calls if "INSERT INTO recipe_steps" in sql]
        self.assertEqual([p[-2:] for p in steps], [(1, "Cook"), (1, "Cook")])

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
