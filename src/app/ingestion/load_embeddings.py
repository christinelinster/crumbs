"""Load the curated Markdown corpus and one embedding per recipe into Postgres."""

from dataclasses import dataclass
import os
from pathlib import Path
import re

from openai import OpenAI

from app.db.connection import pool
from app.db.recipes import save_recipe
from app.rag.embeddings import generate_embedding
from app.paths import RECIPES_DIR
from app.ingestion.utils import canonical_url, frontmatter


API_KEY = os.getenv("OPENAI_API_KEY")


@dataclass
class LoadSummary:
    inserted: int = 0
    updated: int = 0
    failed: int = 0


def parse_recipe_file(path: Path) -> dict:
    """Read reviewed frontmatter and ordered Markdown lists."""
    recipe, body = frontmatter(path)
    slug = recipe.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError("slug must be nonempty text")

    for field in ("cuisine", "source_label"):
        recipe.setdefault(field, None)
    source_url = recipe.get("source_url")
    recipe["source_url"] = (
        canonical_url(source_url) if source_url and source_url.strip() else None
    )
    recipe["category"] = recipe.get("category") or []
    recipe["tags"] = recipe.get("tags") or []
    for field in ("total_time_minutes", "servings", "calories", "protein", "carbs", "fat"):
        recipe.setdefault(field, None)

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
        groups = []
        pending_group = False
        for line in sections.get(heading, []):
            if not line.strip():
                continue
            if line.startswith("### "):
                name = line[4:].strip()
                if not name or pending_group:
                    raise ValueError(f"empty group in {heading}")
                groups.append({"start": len(items) + 1,
                               "name": None if name == "<!-- unnamed group -->" else name})
                pending_group = True
                continue
            match = re.match(pattern, line.strip())
            if match:
                items.append(" ".join(match[1].split()))
                pending_group = False
            elif items and not pending_group and line[0].isspace():
                items[-1] += " " + " ".join(line.split())
            else:
                raise ValueError(f"invalid list item in {heading}: {line}")
        if not items:
            raise ValueError(f"{heading} must contain at least one item")
        if pending_group:
            raise ValueError(f"empty group in {heading}")
        recipe[heading.lower()] = items
        recipe["ingredient_groups" if heading == "Ingredients" else "instruction_groups"] = groups

    recipe["notes"] = "\n".join(sections.get("Notes", [])).strip() or None
    return recipe


def build_embedding_text(recipe: dict) -> str:
    """Render the recipe's semantic content in a stable order."""
    lines = [f"Title: {recipe['title']}", f"Description: {recipe['description']}"]
    for field, label in (("cuisine", "Cuisine"), ("category", "Categories"), ("tags", "Tags")):
        value = recipe[field]
        if value:
            lines.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    for field, label, group_key in (
        ("ingredients", "Ingredients", "ingredient_groups"),
        ("instructions", "Instructions", "instruction_groups"),
    ):
        lines.append(f"{label}:")
        headings = {g["start"]: g["name"] for g in recipe.get(group_key, [])}
        for i, item in enumerate(recipe[field], 1):
            if headings.get(i):
                lines.append(f"{headings[i]}")
            lines.append(f"- {item}" if field == "ingredients" else f"{i}. {item}")
    if recipe["notes"]:
        lines.extend(("Notes:", recipe["notes"]))
    return "\n".join(lines)


def load_embeddings(
    recipes_dir: Path = RECIPES_DIR, *, client, database_pool=pool,
) -> LoadSummary:
    """Embed and commit each reviewed recipe independently.

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
