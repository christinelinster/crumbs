"""Submit one Markdown recipe directly to Graphiti's extraction pipeline."""

from datetime import datetime, timezone
from pathlib import Path

from graphiti_core.nodes import EpisodeType

from app.settings import RECIPE_GROUP_ID
from app import settings
from app.chat_capture import write_ingestion_report


async def ingest_recipe(client, path: Path):
    markdown = path.read_text(encoding='utf-8')
    report = {
        'group_id': RECIPE_GROUP_ID, 'source_path': str(path), 'source_markdown': markdown,
        'default_model': settings.GRAPHITI_LLM_MODEL, 'attribute_model': settings.GRAPHITI_SMALL_MODEL,
    }
    try:
        result = await client.add_episode(
            name=path.stem,
            episode_body=markdown,
            source=EpisodeType.text,
            source_description='Crumbs recipe Markdown',
            reference_time=datetime.now(timezone.utc),
            group_id=RECIPE_GROUP_ID,
        )
        report.update(status='completed', episode=result.episode, entities=result.nodes, facts=result.edges)
        return result
    except Exception as error:
        report.update(status='failed', error={'type': type(error).__name__})
        raise
    finally:
        write_ingestion_report('graphiti', report)
