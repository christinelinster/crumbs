from dataclasses import dataclass, field
from decimal import Decimal
import math
import re
from textwrap import shorten

from bs4 import BeautifulSoup


@dataclass
class NormalizedRecipe:
    title: str
    ingredients: list[str]
    instructions: list[str]
    cuisine: str | None
    servings: str | None
    source_url: str
    description: str | None = None
    category: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    total_time_minutes: int | None = None
    calories: str | None = None
    protein: str | None = None
    carbs: str | None = None
    fat: str | None = None


def normalize_recipe(
    recipe: dict,
    source_url: str,
) -> NormalizedRecipe:

    instructions = normalize_instructions(
        recipe.get("recipeInstructions", [])
    )

    cuisine = recipe.get("recipeCuisine")

    if isinstance(cuisine, list):
        cuisine = ", ".join(cuisine)

    servings = recipe.get("recipeYield")

    if isinstance(servings, list):
        servings = ", ".join(str(item) for item in servings)

    nutrition = recipe.get("nutrition")
    if not isinstance(nutrition, dict):
        nutrition = {}

    return NormalizedRecipe(
        title=recipe.get("name", "").strip(),
        ingredients=recipe.get("recipeIngredient", []),
        instructions=instructions,
        cuisine=cuisine,
        servings=servings,
        source_url=source_url,
        description=normalize_description(recipe.get("description")),
        category=normalize_labels(recipe.get("recipeCategory")),
        tags=normalize_labels(recipe.get("keywords")),
        total_time_minutes=normalize_total_time(recipe),
        calories=normalize_nutrient(nutrition.get("calories")),
        protein=normalize_nutrient(nutrition.get("proteinContent")),
        carbs=normalize_nutrient(nutrition.get("carbohydrateContent")),
        fat=normalize_nutrient(nutrition.get("fatContent")),
    )


def normalize_description(value: object) -> str | None:
    """Keep the first source sentence, capped at 200 characters at a word boundary."""
    if not isinstance(value, str):
        return None
    text = " ".join(BeautifulSoup(value, "html.parser").get_text(" ").split())
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return shorten(sentence, width=200, placeholder="...") or None


def normalize_labels(value: object) -> list[str]:
    """Accept comma-separated strings or lists, preserving order and spelling."""
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list):
        return []
    labels = [
        label.strip()
        for item in values if isinstance(item, str)
        for label in item.split(",") if label.strip()
    ]
    return list(dict.fromkeys(labels))


def normalize_nutrient(value: object) -> str | None:
    """Preserve source units and portion basis; never invent missing nutrition."""
    if isinstance(value, str):
        return value.strip() or None
    if type(value) in (int, float) and math.isfinite(value):
        return str(value)
    return None


def _duration_minutes(value: object) -> Decimal | None:
    """Read ISO 8601 day/time durations; calendar months/years are ambiguous."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"P(?:(\d+(?:\.\d+)?)D)?"
        r"(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?",
        value.strip(),
    )
    if not match or not any(match.groups()) or value.strip().endswith("T"):
        return None
    days, hours, minutes, seconds = (Decimal(part or "0") for part in match.groups())
    return days * 1440 + hours * 60 + minutes + seconds / 60


def normalize_total_time(recipe: dict) -> int | None:
    """Prefer total, then prep + cook, then cook alone; round up partial minutes."""
    total = _duration_minutes(recipe.get("totalTime"))
    if total is None:
        cook = _duration_minutes(recipe.get("cookTime"))
        if cook is None:
            return None
        prep = _duration_minutes(recipe.get("prepTime"))
        total = cook + (prep if prep is not None else Decimal(0))
    return math.ceil(total)


def normalize_instructions(instructions) -> list[str]:
    result = []

    if isinstance(instructions, str):
        return [instructions]

    if not isinstance(instructions, list):
        return result

    for item in instructions:
        if isinstance(item, str):
            result.append(item)

        elif isinstance(item, dict):
            if item.get("@type") == "HowToStep":
                text = item.get("text")

                if text:
                    result.append(text)

            elif item.get("@type") == "HowToSection":
                nested = item.get("itemListElement", [])
                result.extend(
                    normalize_instructions(nested)
                )

    return result
