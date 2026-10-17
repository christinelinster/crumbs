"""OpenAI embedding helpers shared by ingestion and query code."""

from app.settings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL


def generate_embedding(client, text: str) -> list[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    if len(response.data) != 1:
        raise ValueError("expected exactly one embedding")
    embedding = response.data[0].embedding
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            "embedding dimension mismatch: "
            f"expected {EMBEDDING_DIMENSIONS}, got {len(embedding)}"
        )
    return embedding
