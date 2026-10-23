"""Read-only recipe tools available to the chat model."""

import asyncio
import json

from app.chat_capture import current_capture
from app.db.recipes import (
    RECIPE_SUMMARY_FIELDS,
    find_similar_recipes,
    get_recipe_by_slug,
    get_recipe_embedding,
)
from app.rag.embeddings import generate_embedding
from app.graphiti.retrieval import search_recipes as search_graphiti_recipes
from app.zep.retrieval import search_recipes as search_zep_recipes

from app.settings import (
    DEFAULT_RECIPE_LIMIT,
    DEFAULT_SIMILARITY_THRESHOLD,
    EMBEDDING_DIMENSIONS,
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
            "Search the recipe corpus for the user's request. "
            "When no count "
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


def get_recipe_tools(retrieval_backend):
    """Expose only the arguments supported by the selected search backend."""
    if retrieval_backend == "vector":
        return RECIPE_TOOLS
    if retrieval_backend not in {'zep', 'graphiti'}:
        raise ValueError('unknown retrieval backend')
    search = RECIPE_TOOLS[1]
    return [{
        **search,
        'description': (
            "Search the shared recipe graph and Christine's user graph for recipe discovery, "
            "specific recipe details, or food-preference questions. Recipe and user context "
            "are returned separately; recipe results include their original Markdown sources."
        ),
        'parameters': {
            **search['parameters'],
            'properties': {'input': search['parameters']['properties']['input']},
        },
    }]


def build_recipe_cards(recipes: list[dict[str, object]]) -> list[dict[str, object]]:
    """Project full retrieval results into condensed clickable recipe cards."""
    return [
        {
            **{field: recipe[field] for field in RECIPE_SUMMARY_FIELDS},
            "similarity_score": recipe.get("similarity_score"),
        }
        for recipe in recipes
    ]


_DISCOVERY_FIELDS = (
    "slug",
    "title",
    "description",
    "category",
    "tags",
    "calories",
    "protein",
    "carbs",
    "fat",
    "similarity_score",
)


def _execute_search_tool(
    client,
    database_pool,
    arguments: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    search_input = arguments["input"]
    explicit_count = "limit" in arguments
    limit = arguments.get("limit", DEFAULT_RECIPE_LIMIT)

    anchor = None
    anchor_slug = arguments.get("similar_to_slug")
    if anchor_slug is None:
        embedding = generate_embedding(client, search_input)
        with database_pool.connection() as conn:
            candidates = find_similar_recipes(
                conn,
                embedding,
                limit,
                minimum_similarity=None,
            )
    else:
        with database_pool.connection() as conn:
            anchor = get_recipe_embedding(conn, anchor_slug)
            if anchor is None:
                return {
                    "anchor": None,
                    "matches": [],
                }, []
            embedding = anchor.get("embedding")
            if embedding is None:
                candidates = []
            else:
                if len(embedding) != EMBEDDING_DIMENSIONS:
                    raise ValueError(
                        "stored recipe embedding dimension mismatch: "
                        f"expected {EMBEDDING_DIMENSIONS}, got {len(embedding)}"
                    )
                candidates = find_similar_recipes(
                    conn,
                    embedding,
                    limit,
                    minimum_similarity=None,
                    exclude_slug=anchor["slug"],
                )

    strong = [
        recipe
        for recipe in candidates
        if recipe.get("similarity_score") is not None
        and recipe["similarity_score"] > DEFAULT_SIMILARITY_THRESHOLD
    ]
    strong_slugs = {recipe["slug"] for recipe in strong}
    weak = [recipe for recipe in candidates if recipe["slug"] not in strong_slugs]
    if strong:
        presented = list(strong)
        if explicit_count:
            presented.extend(weak[: max(0, limit - len(presented))])
    else:
        presented = list(weak)

    matches = [
        {
            **{field: recipe.get(field) for field in _DISCOVERY_FIELDS},
            "match_strength": "strong" if recipe["slug"] in strong_slugs else "weak",
        }
        for recipe in presented
    ]
    result = {
        "matches": matches,
    }
    if anchor is not None:
        result["anchor"] = {"slug": anchor["slug"], "title": anchor["title"]}
    return result, build_recipe_cards(presented)


def execute_recipe_tool(
    call,
    *,
    client,
    database_pool,
    retrieval_backend,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if call.name not in {"get_recipe_detail", "get_recipes"}:
        raise ValueError(f"unknown recipe tool: {call.name}")
    arguments = json.loads(call.arguments)
    if retrieval_backend in {'zep', 'graphiti'}:
        if call.name != 'get_recipes':
            raise ValueError('Graph backends support only native graph search')
        capture = current_capture.get()
        entry = {'backend': retrieval_backend, 'tool_name': call.name,
                 'call_id': call.call_id, 'arguments': arguments, 'result': None}
        if capture is not None:
            capture['tool_results'].append(entry)
            capture[f'{retrieval_backend}_used'] = True
        try:
            result = (asyncio.run(search_graphiti_recipes(arguments['input']))
                      if retrieval_backend == 'graphiti' else search_zep_recipes(arguments['input']))
            entry['result'] = result
            entry['delivery'] = 'retrieved but not submitted'
            return result, []
        except Exception as error:
            entry['error'] = {'type': type(error).__name__}
            raise RuntimeError(f'{retrieval_backend} retrieval unavailable') from error
    if call.name == "get_recipe_detail":
        with database_pool.connection() as conn:
            recipe = get_recipe_by_slug(conn, arguments["slug"])
        return {"recipe": recipe}, []
    return _execute_search_tool(client, database_pool, arguments)
