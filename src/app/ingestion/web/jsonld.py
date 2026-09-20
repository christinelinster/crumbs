import json
from bs4 import BeautifulSoup

from app.ingestion.web.fetch import fetch_page


async def get_recipe_json_ld(url: str) -> dict | None:
    """
    Return the first Recipe JSON-LD object, or None when none is present.
    JSON-LD for recipes is a standardized, machine-readable format embedded in a webpage's HTML
    that tells search engines and apps specific details about a dish, such as its ingredients, cooking time, and instructions
    """

    html = await fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")

    scripts = soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
    )

    for script in scripts:
        if not script.string:
            continue

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        recipe = find_recipe(data)

        if recipe:
            return recipe

    return None


def find_recipe(data) -> dict | None:
    """Find the recipe data from the Recipe JSON-LD object, taking into account different nested structures to only extract the recipe data."""
    if isinstance(data, list):
        for item in data:
            recipe = find_recipe(item)

            if recipe:
                return recipe

    if isinstance(data, dict):
        type_value = data.get("@type")

        if type_value == "Recipe":
            return data

        if isinstance(type_value, list) and "Recipe" in type_value:
            return data

        for value in data.values():
            recipe = find_recipe(value)

            if recipe:
                return recipe

    return None
