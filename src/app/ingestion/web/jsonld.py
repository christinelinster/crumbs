import json
import asyncio
from bs4 import BeautifulSoup

from app.ingestion.web.fetch import fetch_page


async def get_recipe_json_ld(url: str) -> dict | None:
    """Return the first Recipe JSON-LD object, or None when none is present.

    The recipeIngredient field contains raw ingredient strings for parsing.
    HTTP and network errors propagate to the caller.
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
    if isinstance(data, list):
        for item in data:
            recipe = find_recipe(item)

            if recipe:
                return recipe

    if isinstance(data, dict):
        type_value = data.get("@type")

        if type_value == "Recipe":
            return data

        if (
            isinstance(type_value, list)
            and "Recipe" in type_value
        ):
            return data

        for value in data.values():
            recipe = find_recipe(value)

            if recipe:
                return recipe

    return None
