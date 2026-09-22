"""Read-only HTTP API for the Crumbs recipe corpus."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel

from app.db.connection import pool
from app.db.recipes import get_recipe_by_slug, list_recipe_summaries


Number = int | float | None


class RecipeSummary(BaseModel):
    """Fields needed to render a condensed, clickable recipe card."""

    slug: str
    title: str
    category: list[str]
    tags: list[str]
    total_time_minutes: int | None
    calories: Number
    protein: Number
    carbs: Number
    fat: Number


class RecipeGroupMarker(BaseModel):
    """A group heading beginning at a position in an ordered recipe list."""

    position: int
    group_position: int
    group_name: str | None


class RecipeDetail(RecipeSummary):
    """Complete public recipe content for the detail page."""

    description: str
    cuisine: str | None
    servings: int | None
    source_label: str | None
    source_url: str | None
    notes: str | None
    ingredients: list[str]
    instructions: list[str]
    ingredient_groups: list[RecipeGroupMarker]
    instruction_groups: list[RecipeGroupMarker]


def create_app(database_pool=pool) -> FastAPI:
    """Build the recipe API with an injectable connection pool."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        with database_pool:
            yield

    api = FastAPI(
        title="Crumbs Recipe API",
        lifespan=lifespan,
    )

    @api.get("/api/recipes", response_model=list[RecipeSummary])
    def list_recipes() -> list[dict[str, object]]:
        with database_pool.connection() as conn:
            return list_recipe_summaries(conn)

    @api.get(
        "/api/recipes/{slug}",
        response_model=RecipeDetail,
    )
    def recipe_detail(
        slug: Annotated[str, Path(min_length=1)],
    ) -> dict[str, object]:
        with database_pool.connection() as conn:
            recipe = get_recipe_by_slug(conn, slug)
        if recipe is None:
            raise HTTPException(
                status_code=404,
                detail=f"recipe not found: {slug}",
            )
        return recipe

    return api


app = create_app()
