"""Database writes for recipes and their ordered ingredients and steps."""

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


RECIPE_CONTEXT_FIELDS = (
    "id", "slug", "title", "description", "category", "tags", "cuisine",
    "total_time_minutes", "servings", "calories", "protein", "carbs", "fat",
    "source_label", "source_url", "notes", "ingredients", "instructions",
    "ingredient_groups", "instruction_groups",
)
RECIPE_CARD_FIELDS = (
    "id", "slug", "title", "description", "category", "tags", "cuisine",
    "total_time_minutes", "servings", "calories", "protein", "carbs", "fat",
    "source_label", "source_url", "similarity_score",
)


def _validate_search_limit(limit: int):
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")


def find_similar_recipes(
    conn, embedding: list[float], limit: int,
) -> list[dict[str, object]]:
    """Return complete recipe context ordered by vector similarity."""
    _validate_search_limit(limit)

    rows = conn.execute(
        """
        SELECT
            r.id, r.slug, r.title, r.description, r.category, r.tags, r.cuisine,
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
        WHERE r.embedding IS NOT NULL
        ORDER BY r.embedding <=> %s::vector
        LIMIT %s
        """,
        (embedding, limit),
    ).fetchall()
    return [dict(zip(RECIPE_CONTEXT_FIELDS, row)) for row in rows]


def find_similar_recipe_cards(
    conn, embedding: list[float], limit: int,
) -> list[dict[str, object]]:
    """Return recipe-card fields ordered by vector similarity."""
    _validate_search_limit(limit)

    rows = conn.execute(
        """
        SELECT
            r.id, r.slug, r.title, r.description, r.category, r.tags, r.cuisine,
            r.total_time_minutes, r.servings, r.calories, r.protein, r.carbs, r.fat,
            r.source_label, r.source_url,
            1 - (r.embedding <=> %s::vector) AS similarity_score
        FROM recipes AS r
        WHERE r.embedding IS NOT NULL
        ORDER BY r.embedding <=> %s::vector
        LIMIT %s
        """,
        (embedding, embedding, limit),
    ).fetchall()
    return [dict(zip(RECIPE_CARD_FIELDS, row)) for row in rows]
