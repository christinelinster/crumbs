"""Search Christine's user facts and shared recipe facts separately."""

from graphiti_core.nodes import EpisodicNode
from graphiti_core.search.search_config import DEFAULT_SEARCH_LIMIT

from app import settings
from app.chat_capture import current_capture
from graphiti_core.search.search_filters import ComparisonOperator, DateFilter, SearchFilters

from app.settings import RECIPE_GROUP_ID, USER_GROUP_ID
from app.graphiti.client import get_graphiti


async def search_recipes(query):
    client = get_graphiti()
    capture = current_capture.get()
    entry = {
        'request': {'searches': []}, 'results': None, 'source_fetches': [], 'native_results': {},
        'configuration': {
            'method': 'Graphiti.search', 'num_results_per_graph': DEFAULT_SEARCH_LIMIT,
            'search_recipe': 'EDGE_HYBRID_SEARCH_RRF (native default without center node)',
            'default_model': settings.GRAPHITI_LLM_MODEL,
            'attribute_model': settings.GRAPHITI_SMALL_MODEL,
        },
    }
    if capture is not None:
        capture['graphiti_used'] = True
        capture['graphiti_contexts'].append(entry)
    try:
        search_filter = SearchFilters(
            invalid_at=[[DateFilter(comparison_operator=ComparisonOperator.is_null)]],
            expired_at=[[DateFilter(comparison_operator=ComparisonOperator.is_null)]],
        )
        searches = entry['request']['searches']
        searches.append({'query': query, 'group_ids': [RECIPE_GROUP_ID],
                         'num_results': DEFAULT_SEARCH_LIMIT, 'search_filter': search_filter})
        recipe_edges = await client.search(**searches[-1])
        entry['native_results']['recipe_edges'] = recipe_edges
        searches.append({'query': query, 'group_ids': [USER_GROUP_ID],
                         'num_results': DEFAULT_SEARCH_LIMIT, 'search_filter': search_filter})
        user_edges = await client.search(**searches[-1])
        entry['native_results']['user_edges'] = user_edges
        source_ids = list(dict.fromkeys(uuid for edge in recipe_edges for uuid in edge.episodes))
        if source_ids:
            entry['source_fetches'].append({'episode_uuids': source_ids, 'group_id': RECIPE_GROUP_ID})
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
        entry['results'] = result
        return result
    except Exception as error:
        entry['error'] = {'type': type(error).__name__}
        raise
    finally:
        await client.close()
