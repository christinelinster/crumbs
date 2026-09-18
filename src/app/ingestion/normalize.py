from dataclasses import dataclass

@dataclass
class NormalizedRecipe:
    title: str
    ingredients: list[str]
    instructions: list[str]
    cuisine: str | None
    cook_time: str | None
    servings: str | None
    source_url: str


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

    return NormalizedRecipe(
        title=recipe.get("name", "").strip(),
        ingredients=recipe.get("recipeIngredient", []),
        instructions=instructions,
        cuisine=cuisine,
        cook_time=recipe.get("cookTime"),
        servings=servings,
        source_url=source_url,
    )

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