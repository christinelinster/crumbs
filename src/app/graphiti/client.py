"""Create a Graphiti client and initialize its Neo4j indexes."""

from graphiti_core import Graphiti
from graphiti_core.llm_client import LLMRuntime, LLMTransport, OpenAIClient, PromptRoutes

from app import settings


def get_graphiti():
    transport = LLMTransport(
        OpenAIClient(reasoning="low"),
        models=(settings.GRAPHITI_LLM_MODEL, settings.GRAPHITI_SMALL_MODEL),
    )
    default_model = transport.model(settings.GRAPHITI_LLM_MODEL)
    small_model = transport.model(settings.GRAPHITI_SMALL_MODEL)
    runtime = LLMRuntime(
        model=default_model,
        routes=PromptRoutes(
            extract_nodes=PromptRoutes.ExtractNodes(
                extract_attributes=small_model,
            ),
            extract_edges=PromptRoutes.ExtractEdges(extract_attributes=small_model),
        ),
    )
    return Graphiti(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        llm_runtime=runtime,
    )
