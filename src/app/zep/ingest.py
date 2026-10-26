"""Submit recipe Markdown to Zep's default extraction pipeline."""
from pathlib import Path


def ingest_recipe(client, graph_uuid, path: Path):
    return client.graph.episode.add(
        graph_uuid, type='text', data=path.read_text(encoding='utf-8'),
        document_id=path.stem, source_description='Crumbs recipe Markdown',
    )
