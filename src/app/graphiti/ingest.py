"""Submit recipe Markdown directly to Graphiti's extraction pipeline."""

from datetime import datetime, timezone
from pathlib import Path

from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.bulk_utils import RawEpisode

from app.settings import RECIPE_GROUP_ID


async def ingest_recipe(client, path: Path):
    return await client.add_episode(
        name=path.stem,
        episode_body=path.read_text(encoding='utf-8'),
        source=EpisodeType.text,
        source_description='Crumbs recipe Markdown',
        reference_time=datetime.now(timezone.utc),
        group_id=RECIPE_GROUP_ID,
    )


async def ingest_recipes(client, paths):
    reference_time = datetime.now(timezone.utc)
    episodes = [RawEpisode(
        name=path.stem, content=path.read_text(encoding='utf-8'), source=EpisodeType.text,
        source_description='Crumbs recipe Markdown', reference_time=reference_time,
    ) for path in paths]
    if not episodes:
        raise ValueError('Select at least one recipe')
    # The combined bulk prompt treats documents as conversations with speakers.
    return await client.add_episode_bulk(
        episodes, group_id=RECIPE_GROUP_ID, use_combined_extraction=False,
    )
