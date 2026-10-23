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
GRAPHITI_LLM_MODEL = os.getenv("GRAPHITI_LLM_MODEL", "gpt-5.5")
GRAPHITI_SMALL_MODEL = os.getenv("GRAPHITI_EXTRACTION_MODEL", GRAPHITI_LLM_MODEL)
RECIPE_GROUP_ID = 'shared_recipes'
USER_GROUP_ID = 'user_christine'

ZEP_API_KEY = os.getenv("ZEP_API_KEY")
ZEP_GRAPH_UUID = os.getenv("ZEP_GRAPH_UUID")
ZEP_USER_UUID = os.getenv("ZEP_USER_UUID")

NEO4J_URI=os.getenv("NEO4J_URI")
NEO4J_USER=os.getenv("NEO4J_USER")
NEO4J_PASSWORD=os.getenv("NEO4J_PASSWORD")
