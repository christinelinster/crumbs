"""Database writes for recipes and their ordered ingredients and steps."""

import math

from app.ingestion.groups import group_at


def save_recipe(conn, recipe: dict, embedding: list[float]) -> bool:
    """Save a recipe and its children inside the caller's transaction."""
    slug = recipe.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError("recipe slug is required")

    existing = conn.execute(
        "SELECT id, slug FROM recipes WHERE slug = %s",
        (slug,),
    ).fetchone()

    if existing:
        slug = existing[1]

    values = dict(recipe, slug=slug, embedding=embedding)
    recipe_id = conn.execute(
        """
        INSERT INTO recipes (
            slug, title, description, category, tags, cuisine,
            total_time_minutes, servings, calories, protein, carbs, fat,
            source_label, source_url, notes, embedding
        ) VALUES (
            %(slug)s, %(title)s, %(description)s, %(category)s, %(tags)s, %(cuisine)s,
            %(total_time_minutes)s, %(servings)s, %(calories)s, %(protein)s,
            %(carbs)s, %(fat)s, %(source_label)s, %(source_url)s, %(notes)s,
            %(embedding)s::vector
        )
        ON CONFLICT (slug) DO UPDATE SET
            title = EXCLUDED.title, description = EXCLUDED.description,
            category = EXCLUDED.category, tags = EXCLUDED.tags, cuisine = EXCLUDED.cuisine,
            total_time_minutes = EXCLUDED.total_time_minutes, servings = EXCLUDED.servings,
            calories = EXCLUDED.calories, protein = EXCLUDED.protein,
            carbs = EXCLUDED.carbs, fat = EXCLUDED.fat,
            source_label = EXCLUDED.source_label, source_url = EXCLUDED.source_url,
            notes = EXCLUDED.notes,
            embedding = EXCLUDED.embedding
        RETURNING id
        """,
        values,
    ).fetchone()[0]

    conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = %s", (recipe_id,))
    for position, ingredient in enumerate(recipe["ingredients"], 1):
        group_position, group_name = group_at(recipe.get("ingredient_groups", []), position)
        conn.execute(
            """INSERT INTO recipe_ingredients
               (recipe_id, position, raw_text, normalized_name, group_position, group_name)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (recipe_id, position, ingredient, None, group_position, group_name),
        )
    conn.execute("DELETE FROM recipe_steps WHERE recipe_id = %s", (recipe_id,))
    for position, instruction in enumerate(recipe["instructions"], 1):
        group_position, group_name = group_at(recipe.get("instruction_groups", []), position)
        conn.execute(
            """INSERT INTO recipe_steps
               (recipe_id, position, instruction, group_position, group_name)
               VALUES (%s, %s, %s, %s, %s)""",
            (recipe_id, position, instruction, group_position, group_name),
        )
    return existing is None


RECIPE_METADATA_FIELDS = (
    "slug", "title", "description", "category", "tags", "cuisine",
    "total_time_minutes", "servings", "calories", "protein", "carbs", "fat",
)
RECIPE_SOURCE_FIELDS = ("source_label", "source_url")
RECIPE_SUMMARY_FIELDS = (
    "slug", "title", "category", "tags", "total_time_minutes",
    "calories", "protein", "carbs", "fat",
)
RECIPE_DETAIL_METADATA_FIELDS = RECIPE_METADATA_FIELDS + RECIPE_SOURCE_FIELDS
RECIPE_DETAIL_FIELDS = RECIPE_DETAIL_METADATA_FIELDS + (
    "notes", "ingredients", "instructions", "ingredient_groups", "instruction_groups",
)
RECIPE_SEARCH_FIELDS = RECIPE_DETAIL_FIELDS + ("similarity_score",)


def _validate_search_limit(limit: int):
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")


def _validate_similarity_threshold(similarity_threshold):
    if similarity_threshold is None:
        return
    if (
        isinstance(similarity_threshold, bool)
        or not isinstance(similarity_threshold, (int, float))
        or not math.isfinite(similarity_threshold)
        or not -1 <= similarity_threshold <= 1
    ):
        raise ValueError(
            "similarity_threshold must be a finite number between -1 and 1"
        )


def list_recipe_summaries(conn) -> list[dict[str, object]]:
    """Return home-page recipe-card fields in a stable display order."""
    rows = conn.execute(
        """
        SELECT
            r.slug, r.title, r.category, r.tags, r.total_time_minutes,
            r.calories, r.protein, r.carbs, r.fat
        FROM recipes AS r
        ORDER BY r.title, r.slug
        """,
    ).fetchall()
    return [dict(zip(RECIPE_SUMMARY_FIELDS, row)) for row in rows]


def get_recipe_by_slug(conn, slug: str) -> dict[str, object] | None:
    """Return complete public recipe content for one persisted slug."""
    row = conn.execute(
        """
        SELECT
            r.slug, r.title, r.description, r.category, r.tags, r.cuisine,
            r.total_time_minutes, r.servings, r.calories, r.protein, r.carbs, r.fat,
            r.source_label, r.source_url, r.notes,
            ARRAY(
                SELECT ri.raw_text
                FROM recipe_ingredients AS ri
                WHERE ri.recipe_id = r.id
                ORDER BY ri.position
            ) AS ingredients,
            ARRAY(
                SELECT rs.instruction
                FROM recipe_steps AS rs
                WHERE rs.recipe_id = r.id
                ORDER BY rs.position
            ) AS instructions,
            ARRAY(
                SELECT json_build_object('position', ri.position,
                    'group_position', ri.group_position, 'group_name', ri.group_name)
                FROM recipe_ingredients AS ri
                WHERE ri.recipe_id = r.id AND ri.group_position IS NOT NULL
                ORDER BY ri.position
            ) AS ingredient_groups,
            ARRAY(
                SELECT json_build_object('position', rs.position,
                    'group_position', rs.group_position, 'group_name', rs.group_name)
                FROM recipe_steps AS rs
                WHERE rs.recipe_id = r.id AND rs.group_position IS NOT NULL
                ORDER BY rs.position
            ) AS instruction_groups
        FROM recipes AS r
        WHERE r.slug = %s
        """,
        (slug,),
    ).fetchone()
    if row is None:
        return None
    return dict(zip(RECIPE_DETAIL_FIELDS, row))


def find_similar_recipes(
    conn,
    embedding: list[float],
    limit: int,
    similarity_threshold=None,
) -> list[dict[str, object]]:
    """Return complete recipe context and scores ordered by similarity."""
    _validate_search_limit(limit)
    _validate_similarity_threshold(similarity_threshold)

    base_query = """
        SELECT
            r.slug, r.title, r.description, r.category, r.tags, r.cuisine,
            r.total_time_minutes, r.servings, r.calories, r.protein, r.carbs, r.fat,
            r.source_label, r.source_url, r.notes,
            ARRAY(
                SELECT ri.raw_text
                FROM recipe_ingredients AS ri
                WHERE ri.recipe_id = r.id
                ORDER BY ri.position
            ) AS ingredients,
            ARRAY(
                SELECT rs.instruction
                FROM recipe_steps AS rs
                WHERE rs.recipe_id = r.id
                ORDER BY rs.position
            ) AS instructions,
            ARRAY(
                SELECT json_build_object('position', ri.position,
                    'group_position', ri.group_position, 'group_name', ri.group_name)
                FROM recipe_ingredients AS ri
                WHERE ri.recipe_id = r.id AND ri.group_position IS NOT NULL
                ORDER BY ri.position
            ) AS ingredient_groups,
            ARRAY(
                SELECT json_build_object('position', rs.position,
                    'group_position', rs.group_position, 'group_name', rs.group_name)
                FROM recipe_steps AS rs
                WHERE rs.recipe_id = r.id AND rs.group_position IS NOT NULL
                ORDER BY rs.position
            ) AS instruction_groups,
            1 - (r.embedding <=> %s::vector) AS similarity_score
        FROM recipes AS r
        WHERE r.embedding IS NOT NULL
    """
    if similarity_threshold is None:
        query = base_query + """
            ORDER BY r.embedding <=> %s::vector
            LIMIT %s
        """
        params = (embedding, embedding, limit)
    else:
        query = f"""
            SELECT *
            FROM ({base_query}) AS scored_recipes
            WHERE scored_recipes.similarity_score >= %s
            ORDER BY scored_recipes.similarity_score DESC
            LIMIT %s
        """
        params = (embedding, similarity_threshold, limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(zip(RECIPE_SEARCH_FIELDS, row)) for row in rows]
