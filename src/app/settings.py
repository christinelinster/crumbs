"""Shared runtime configuration for recipe retrieval and chat."""

import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_RECIPE_LIMIT = 3
MAX_RECIPE_LIMIT = 10
DEFAULT_SIMILARITY_THRESHOLD = 0.3
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
try:
    EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
except ValueError:
    raise ValueError("EMBEDDING_DIMENSIONS must be a positive integer") from None
if EMBEDDING_DIMENSIONS <= 0:
    raise ValueError("EMBEDDING_DIMENSIONS must be a positive integer")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
