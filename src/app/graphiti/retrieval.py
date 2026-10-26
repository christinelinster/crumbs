"""Search Christine's user facts and shared recipe facts separately."""

from graphiti_core.nodes import EpisodicNode
from graphiti_core.search.search_config import DEFAULT_SEARCH_LIMIT

from graphiti_core.search.search_filters import ComparisonOperator, DateFilter, SearchFilters

from app.settings import RECIPE_GROUP_ID, USER_GROUP_ID
from app.graphiti.client import get_graphiti


async def search_recipes(query):
    client = get_graphiti()
    try:
        search_filter = SearchFilters(
            invalid_at=[[DateFilter(comparison_operator=ComparisonOperator.is_null)]],
            expired_at=[[DateFilter(comparison_operator=ComparisonOperator.is_null)]],
        )
        recipe_edges = await client.search(
            query=query, group_ids=[RECIPE_GROUP_ID], num_results=DEFAULT_SEARCH_LIMIT,
            search_filter=search_filter,
        )
        user_edges = await client.search(
            query=query, group_ids=[USER_GROUP_ID], num_results=DEFAULT_SEARCH_LIMIT,
            search_filter=search_filter,
        )
        source_ids = list(dict.fromkeys(uuid for edge in recipe_edges for uuid in edge.episodes))
        episodes = await EpisodicNode.get_by_uuids(client.driver, source_ids) if source_ids else []
        result = {
            'backend': 'graphiti',
            'recipe_facts': [
                {'name': edge.name, 'fact': edge.fact, 'episode_uuids': edge.episodes}
                for edge in recipe_edges
            ],
            'user_facts': [
                {'name': edge.name, 'fact': edge.fact, 'episode_uuids': edge.episodes}
                for edge in user_edges
            ],
            'sources': [
                {'episode_uuid': episode.uuid, 'name': episode.name, 'markdown': episode.content}
                for episode in episodes if episode.group_id == RECIPE_GROUP_ID
            ],
        }
        return result
    finally:
        await client.close()
