import unittest

from app.ingestion.normalize import normalize_recipe


class NormalizeRecipeTests(unittest.TestCase):
    def normalize(self, **fields):
        return normalize_recipe(fields, "https://example.com/recipe")

    def test_normalizes_template_metadata(self):
        recipe = self.normalize(
            description="<p>A quick &amp; tasty <b>dinner</b>. Ready for the family!</p>",
            recipeCategory=["Dinner", " Main course ", "Dinner"],
            keywords="easy, weeknight, easy",
            totalTime="PT1H15M",
            cookTime="PT45M",
            nutrition={
                "calories": " 350 kcal ",
                "proteinContent": "20 g",
                "carbohydrateContent": "35 g",
                "fatContent": "12 g",
            },
        )
        self.assertEqual(recipe.description, "A quick & tasty dinner.")
        self.assertEqual(recipe.category, ["Dinner", "Main course"])
        self.assertEqual(recipe.tags, ["easy", "weeknight"])
        self.assertEqual(recipe.total_time_minutes, 75)
        self.assertEqual(recipe.calories, "350 kcal")
        self.assertEqual(recipe.protein, "20 g")
        self.assertEqual(recipe.carbs, "35 g")
        self.assertEqual(recipe.fat, "12 g")

    def test_missing_metadata_stays_empty(self):
        recipe = self.normalize()
        for field in ("description", "total_time_minutes", "calories", "protein", "carbs", "fat"):
            self.assertIsNone(getattr(recipe, field), field)
        self.assertEqual(recipe.category, [])
        self.assertEqual(recipe.tags, [])

    def test_malformed_metadata_is_ignored(self):
        recipe = self.normalize(
            description={"text": "unexpected"},
            nutrition=["unexpected"],
            recipeCategory=42,
            keywords=[None, {}, " quick ", ""],
            totalTime="not a duration",
        )
        self.assertIsNone(recipe.description)
        self.assertIsNone(recipe.calories)
        self.assertIsNone(recipe.total_time_minutes)
        self.assertEqual(recipe.category, [])
        self.assertEqual(recipe.tags, ["quick"])

    def test_description_preserves_decimals_and_cleans_whitespace(self):
        recipe = self.normalize(description="  Ready in 2.5 minutes!\nAnother sentence. ")
        self.assertEqual(recipe.description, "Ready in 2.5 minutes!")
        self.assertEqual(self.normalize(description="Simple soup").description, "Simple soup")
        self.assertIsNone(self.normalize(description="<p> </p>").description)

    def test_categories_and_tags_accept_strings_and_lists(self):
        recipe = self.normalize(
            recipeCategory="lunch, dinner",
            keywords=["comfort food", "budget, easy", "budget"],
        )
        self.assertEqual(recipe.category, ["lunch", "dinner"])
        self.assertEqual(recipe.tags, ["comfort food", "budget", "easy"])

    def test_long_description_is_shortened_at_a_word_boundary(self):
        recipe = self.normalize(description="A delicious " + "warming " * 40 + "soup.")
        self.assertLessEqual(len(recipe.description), 200)
        self.assertTrue(recipe.description.endswith("warming..."))

    def test_time_uses_total_then_prep_plus_cook_then_cook(self):
        cases = [
            ({"totalTime": "PT20M", "prepTime": "PT10M", "cookTime": "PT30M"}, 20),
            ({"prepTime": "PT10M", "cookTime": "PT30M"}, 40),
            ({"totalTime": "unknown", "cookTime": "PT30M"}, 30),
            ({"prepTime": "unknown", "cookTime": "PT30M"}, 30),
            ({"totalTime": "P1DT2H"}, 1560),
            ({"totalTime": "PT1.5H"}, 90),
            ({"totalTime": "PT90S"}, 2),
            ({"totalTime": "PT0M"}, 0),
            ({"totalTime": "P"}, None),
            ({"totalTime": "PT"}, None),
            ({"totalTime": "P1M"}, None),
            ({"totalTime": -10}, None),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                self.assertEqual(self.normalize(**fields).total_time_minutes, expected)

    def test_nutrition_keeps_zero_and_ignores_invalid_values(self):
        recipe = self.normalize(nutrition={
            "calories": 0, "proteinContent": None,
            "carbohydrateContent": {}, "fatContent": False,
        })
        self.assertEqual(recipe.calories, "0")
        self.assertIsNone(recipe.protein)
        self.assertIsNone(recipe.carbs)
        self.assertIsNone(recipe.fat)
