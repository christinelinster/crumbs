"""Database writes for recipes and their ordered ingredients and steps."""

import json


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

    values = dict(recipe, slug=slug, embedding=json.dumps(embedding, allow_nan=False))
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
        conn.execute(
            """INSERT INTO recipe_ingredients (recipe_id, position, raw_text, normalized_name)
               VALUES (%s, %s, %s, %s)""",
            (recipe_id, position, ingredient, None),
        )
    conn.execute("DELETE FROM recipe_steps WHERE recipe_id = %s", (recipe_id,))
    for position, instruction in enumerate(recipe["instructions"], 1):
        conn.execute(
            "INSERT INTO recipe_steps (recipe_id, position, instruction) VALUES (%s, %s, %s)",
            (recipe_id, position, instruction),
        )
    return existing is None
