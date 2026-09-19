import json
import unittest
from unittest.mock import patch

import httpx

from app.ingestion.normalize import normalize_recipe
from app.ingestion.web.fetch import fetch_page
from app.ingestion.web.jsonld import get_recipe_json_ld


class WebIngestionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client_type = httpx.AsyncClient

    def mock_http(self, handler):
        # Keep HTTPX's redirect and status handling; replace only the network.
        transport = httpx.MockTransport(handler)
        self.enterContext(patch(
            "httpx.AsyncClient",
            side_effect=lambda **kwargs: self.client_type(transport=transport, **kwargs),
        ))

    async def test_fetch_returns_html_after_redirect(self):
        def handler(request):
            if request.url.path == "/old":
                return httpx.Response(302, headers={"Location": "/recipe"})
            return httpx.Response(200, text="<html>Crème brûlée</html>")

        self.mock_http(handler)
        self.assertEqual(
            await fetch_page("https://recipes.example/old"),
            "<html>Crème brûlée</html>",
        )

    async def test_fetch_raises_for_http_errors(self):
        for status in (404, 500):
            with self.subTest(status=status):
                self.mock_http(lambda request: httpx.Response(status))
                with self.assertRaises(httpx.HTTPStatusError):
                    await fetch_page("https://recipes.example/missing")

    async def test_fetch_propagates_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("Timed out", request=request)

        self.mock_http(handler)
        with self.assertRaises(httpx.TimeoutException):
            await fetch_page("https://recipes.example/slow")

    async def test_extracts_ingredients_from_recipe_shapes(self):
        for data in (
            {"@type": "Recipe", "recipeIngredient": ["2 eggs", "½ cup milk"]},
            [{"@type": "Recipe", "recipeIngredient": ["2 eggs", "½ cup milk"]}],
            {"@graph": [{"@type": ["Thing", "Recipe"],
                         "recipeIngredient": ["2 eggs", "½ cup milk"]}]},
        ):
            with self.subTest(data=data):
                html = (
                    '<script type="application/ld+json">invalid json</script>'
                    '<script type="application/ld+json"></script>'
                    '<script type="application/ld+json">'
                    + json.dumps(data) + '</script>'
                )
                self.mock_http(lambda request: httpx.Response(200, text=html))
                source_url = "https://recipes.example/recipe"
                recipe = await get_recipe_json_ld(source_url)
                self.assertIsNotNone(recipe)
                normalized = normalize_recipe(recipe, source_url)
                self.assertEqual(normalized.ingredients, ["2 eggs", "½ cup milk"])
                self.assertEqual(normalized.source_url, source_url)

    async def test_returns_none_without_recipe_data(self):
        self.mock_http(lambda request: httpx.Response(
            200, text='<script type="application/ld+json">'
            '{"@type": "Article", "name": "Food"}</script>',
        ))
        self.assertIsNone(await get_recipe_json_ld("https://recipes.example/article"))


if __name__ == "__main__":
    unittest.main()
