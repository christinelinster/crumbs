"""Repository paths shared by application modules and command entry points."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RECIPES_DIR = PROJECT_ROOT / "data/recipes"
RECIPE_URLS_PATH = PROJECT_ROOT / "data/import/recipe-urls.txt"
RECIPE_TEMPLATE_PATH = PROJECT_ROOT / "docs/recipe-corpus-template.md"
SCHEMA_PATH = Path(__file__).resolve().parent / "db/schema.sql"
