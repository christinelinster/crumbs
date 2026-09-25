"""Read-only recipe tools available to the chat model."""

from app.settings import (
    DEFAULT_RECIPE_LIMIT,
    DEFAULT_SIMILARITY_THRESHOLD,
    MAX_RECIPE_LIMIT,
)


RECIPE_TOOLS = [
    {
        "type": "function",
        "name": "get_recipe_detail",
        "description": (
            "Get the full recipe by its stored slug. Use the conversation "
            "history to identify which specific recipe the user means. "
            "For an explicit title, derive its normalized slug. "
            "Do not substitute a similar recipe when the exact lookup fails."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "The exact stored recipe slug.",
                },
            },
            "required": ["slug"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "get_recipes",
        "description": (
            "Search the recipe corpus for the user's request. When no count "
            f"was requested, omit limit; the application returns up to {DEFAULT_RECIPE_LIMIT}. "
            f"If a count was requested, set limit from 1 to {MAX_RECIPE_LIMIT}. "
            "For recipes similar to a recipe mentioned in the conversation, "
            "set similar_to_slug to that stored slug; the application uses "
            "its stored embedding and excludes the anchor. Otherwise omit "
            "similar_to_slug. Similarity results use only the recipe embedding; "
            "do not claim unrequested ingredient or nutrition filtering. "
            f"The app classifies strong results using score > {DEFAULT_SIMILARITY_THRESHOLD}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "The user's recipe search or similarity request.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_RECIPE_LIMIT,
                    "description": "Only include this when the user explicitly asks for a count.",
                },
                "similar_to_slug": {
                    "type": "string",
                    "description": "Stored slug of the recipe to use as a similarity anchor.",
                },
            },
            "required": ["input"],
            "additionalProperties": False,
        },
        "strict": False,
    },
]
