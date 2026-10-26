"""Native Zep thread context and shared recipe graph assembly."""
from zep_cloud.types import DateFilter, DateFilterGroup, DateFilters, SearchFilters

from app import settings
from app.chat_capture import current_capture
from app.zep.client import get_zep


def get_thread_context(client, thread_uuid):
    entry = {
        'scope': 'user thread',
        'request': {
            'method': 'thread.get_context', 'thread_uuid': thread_uuid,
            'query': 'Zep-managed thread context query and relevance selection',
        },
        'context': None, 'results': None, 'truncated': None, 'sources': [],
        'configuration': 'Zep default thread context; selected context types and ranking are managed by Zep.',
    }
    capture = current_capture.get()
    if capture is not None:
        capture['zep_used'] = True
        capture['contexts'].append(entry)
    try:
        result = client.thread.get_context(thread_uuid)
        entry.update(
            context=result.context,
            results=getattr(result, 'results', None),
            truncated=getattr(result, 'truncated', None),
        )
        return result
    except Exception as error:
        entry['error'] = {'type': type(error).__name__}
        raise


def active_fact_filters():
    return SearchFilters(date_filters=DateFilters(any_of=[DateFilterGroup(all_of=[
        DateFilter(field='invalid_at', operator='is_null'),
        DateFilter(field='expired_at', operator='is_null'),
    ])]))


def get_graph_context(client, graph_uuid, query, *, scope='user'):
    request = {
        'graph_uuid': graph_uuid, 'query': query, 'max_characters': 5000,
        'include_results': True, 'filters': active_fact_filters(),
    }
    entry = {
        'scope': scope, 'request': request, 'context': None, 'results': None,
        'truncated': None, 'sources': [],
        'configuration': 'Native context assembly; internal models and ranking settings are Zep-managed and not exposed by this response.',
    }
    capture = current_capture.get()
    if capture is not None:
        capture['zep_used'] = True
        capture['contexts'].append(entry)
    try:
        result = client.graph.get_context(**request)
        entry.update(context=result.context, results=result.results, truncated=result.truncated)
        return result
    except Exception as error:
        entry['error'] = {'type': type(error).__name__}
        raise


def search_recipes(query):
    if not settings.ZEP_GRAPH_UUID:
        raise RuntimeError('Set ZEP_GRAPH_UUID for graph comparison')
    client = get_zep()
    recipe = get_graph_context(client, settings.ZEP_GRAPH_UUID, query, scope='shared recipe graph')
    capture = current_capture.get()
    recipe_capture = capture['contexts'][-1] if capture is not None else None
    selected = recipe.results
    provenance = [
        item
        for field in ('edges', 'nodes', 'observations', 'thread_summaries', 'episodes')
        for item in (getattr(selected, field, None) or [])
    ] if selected is not None else []
    episode_ids = dict.fromkeys(
        uuid for item in provenance for uuid in (getattr(item, 'episode_uuids', None) or [])
    )
    sources = []
    for episode_uuid in episode_ids:
        request = {'graph_uuid': settings.ZEP_GRAPH_UUID, 'episode_uuid': episode_uuid}
        fetch = {'request': request, 'episode': None}
        if recipe_capture is not None:
            recipe_capture['sources'].append(fetch)
        try:
            episode = client.graph.episode.get(settings.ZEP_GRAPH_UUID, episode_uuid)
            fetch['episode'] = episode
        except Exception as error:
            fetch['error'] = {'type': type(error).__name__}
            raise
        if episode.graph_uuid is not None and episode.graph_uuid != settings.ZEP_GRAPH_UUID:
            raise ValueError('Source episode belongs to another graph')
        if episode.content:
            sources.append({
                'episode_uuid': episode_uuid, 'name': episode.document_id,
                'markdown': episode.content,
            })
    return {
        'backend': 'zep', 'recipe_context': recipe.context,
        'recipe_context_truncated': recipe.truncated, 'sources': sources,
    }
