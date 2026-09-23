"""Read-only HTTP API for the Crumbs recipe corpus."""

from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field, field_validator

from app.db.connection import pool
from app.db.recipes import get_recipe_by_slug, list_recipe_summaries
from app.rag.query import (
    QueryGenerationError,
    RecipeNotFoundError,
    process_query_result,
)


Number = int | float | None


class ChatMessage(BaseModel):
    """A user or assistant message supplied as conversation context."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def require_nonempty_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must be nonempty text")
        return value


class ChatRequest(BaseModel):
    """Input contract for the grounded chat endpoint."""

    question: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    limit: int = Field(default=3, gt=0)
    recipe_slug: str | None = None

    @field_validator("question")
    @classmethod
    def require_nonempty_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must be nonempty text")
        return value


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


class RecipeCard(RecipeSummary):
    """A condensed recipe reference returned from similarity retrieval."""

    similarity_score: float


class ChatResponse(BaseModel):
    """Public response contract for a grounded chat request."""

    answer: str
    recipe_cards: list[RecipeCard]


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
    """Build the recipe and chat API."""

    @asynccontextmanager
    async def lifespan(api: FastAPI):
        with database_pool:
            yield

    api = FastAPI(
        title="Crumbs API",
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

    @api.post("/api/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        history = [message.model_dump() for message in request.history]
        try:
            result = process_query_result(
                request.question,
                history,
                database_pool=database_pool,
                limit=request.limit,
                recipe_slug=request.recipe_slug,
            )
        except RecipeNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except QueryGenerationError as error:
            raise HTTPException(
                status_code=502,
                detail="chat model returned an invalid response",
            ) from error
        except (OSError, RuntimeError, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail="chat service unavailable",
            ) from error
        return ChatResponse(
            answer=result.answer,
            recipe_cards=result.recipe_cards,
        )

    return api


app = create_app()
