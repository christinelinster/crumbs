"""OpenAI embedding helpers shared by ingestion and query code."""
import os
from dotenv import load_dotenv


load_dotenv()
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')



def generate_embedding(client, text: str) -> list[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    if len(response.data) != 1:
        raise ValueError("expected exactly one embedding")
    return response.data[0].embedding
