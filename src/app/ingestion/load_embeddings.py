"""Load the curated Markdown corpus and one embedding per recipe into Postgres."""

from dataclasses import dataclass
import math
import os
from pathlib import Path
import re

from openai import OpenAI

from app.db.connection import pool
from app.db.recipes import save_recipe
from app.embeddings import generate_embedding
from app.paths import RECIPES_DIR
from app.ingestion.utils import canonical_url, frontmatter


API_KEY = os.getenv("OPENAI_API_KEY")


@dataclass
class LoadSummary:
    inserted: int = 0
    updated: int = 0
    failed: int = 0


def parse_recipe_file(path: Path) -> dict:
    """Read frontmatter and ordered Markdown lists, preserving continuation lines."""
    recipe, body = frontmatter(path)
    optional_text_fields = {"cuisine", "source_label", "source_url"}
    for field in ("title", "description", "cuisine", "source_label", "source_url"):
        value = recipe.get(field)
        if value is None and field in optional_text_fields:
            recipe[field] = None
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be nonempty text")
        recipe[field] = canonical_url(value) if field == "source_url" else " ".join(value.split())

    slug = recipe.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError("slug must be nonempty text")

    for field in ("category", "tags"):
        values = recipe.get(field) or []
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise ValueError(f"{field} must be a list of nonempty strings")
        recipe[field] = [" ".join(value.split()) for value in values]

    for field in ("total_time_minutes", "servings", "calories", "protein", "carbs", "fat"):
        value = recipe.get(field)
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{field} must be a finite, nonnegative number")
            if field in ("total_time_minutes", "servings"):
                if value != int(value) or (field == "servings" and value == 0):
                    raise ValueError(f"invalid {field}")
                value = int(value)
        recipe[field] = value

    sections = {}
    current = None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            if current in sections:
                raise ValueError(f"duplicate section: {current}")
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    for heading, pattern in (
        ("Ingredients", r"^-\s+(.+)$"),
        ("Instructions", r"^\d+[.)]\s+(.+)$"),
    ):
        items = []
        for line in sections.get(heading, []):
            if not line.strip():
                continue
            match = re.match(pattern, line.strip())
            if match:
                items.append(" ".join(match[1].split()))
            elif items and line[0].isspace():
                items[-1] += " " + " ".join(line.split())
            else:
                raise ValueError(f"invalid list item in {heading}: {line}")
        if not items:
            raise ValueError(f"{heading} must contain at least one item")
        recipe[heading.lower()] = items

    recipe["notes"] = "\n".join(sections.get("Notes", [])).strip() or None
    return recipe


def build_embedding_text(recipe: dict) -> str:
    """Render the recipe's semantic content in a stable order."""
    lines = [f"Title: {recipe['title']}", f"Description: {recipe['description']}"]
    for field, label in (("cuisine", "Cuisine"), ("category", "Categories"), ("tags", "Tags")):
        value = recipe[field]
        if value:
            lines.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    lines.append("Ingredients:")
    lines.extend(f"- {item}" for item in recipe["ingredients"])
    lines.append("Instructions:")
    lines.extend(f"{i}. {step}" for i, step in enumerate(recipe["instructions"], 1))
    if recipe["notes"]:
        lines.extend(("Notes:", recipe["notes"]))
    return "\n".join(lines)


def load_embeddings(
    recipes_dir: Path = RECIPES_DIR, *, client, database_pool=pool,
) -> LoadSummary:
    """Validate, embed, and commit each recipe independently.

    The caller owns the OpenAI client. The database pool is managed for the
    duration of the load, while each connection is leased only for a recipe
    write after that recipe's embedding has been generated.
    """
    paths = sorted(recipes_dir.glob("*.md"))
    if not paths:
        raise ValueError(f"no Markdown recipes found in {recipes_dir}")
    recipes = [(path, parse_recipe_file(path)) for path in paths]
    seen_slugs = {}
    seen_urls = {}
    for path, recipe in recipes:
        slug = recipe["slug"]
        if slug in seen_slugs:
            raise ValueError(f"duplicate slug in {seen_slugs[slug].name} and {path.name}: {slug}")
        seen_slugs[slug] = path
        url = recipe["source_url"]
        if url is not None:
            if url in seen_urls:
                raise ValueError(f"duplicate source_url in {seen_urls[url].name} and {path.name}: {url}")
            seen_urls[url] = path

    summary = LoadSummary()
    with database_pool:
        for path, recipe in recipes:
            try:
                embedding = generate_embedding(client, build_embedding_text(recipe))
                # The connection context commits on success and rolls back on failure.
                with database_pool.connection() as conn:
                    inserted = save_recipe(conn, recipe, embedding)
                if inserted:
                    summary.inserted += 1
                else:
                    summary.updated += 1
                print(f"{'INSERTED' if inserted else 'UPDATED'} {path.name}")
            except Exception as error:
                summary.failed += 1
                print(f"FAILED {path.name}: {type(error).__name__}: {error}")
    return summary


def main() -> int:
    try:
        with OpenAI(api_key=API_KEY, timeout=60.0, max_retries=2) as client:
            summary = load_embeddings(client=client)
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}")
        return 1
    print(f"{summary.inserted} inserted, {summary.updated} updated, {summary.failed} failed")
    return int(summary.failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
