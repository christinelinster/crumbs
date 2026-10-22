"""Graph searches and full recipes from their original source episodes."""

import json

from app.chat_capture import current_capture

from zep_cloud.types import (
    DateFilter,
    DateFilterGroup,
    DateFilters,
    SearchFilters,
    EpisodeListFilters,
    MetadataFilter,
    MetadataFilterGroup,
)


SEARCH_PAGE_SIZE = 50


def active_fact_filters():
    """Filter facts that Zep has invalidated or expired from current results."""
    return SearchFilters(
        date_filters=DateFilters(
            any_of=[
                DateFilterGroup(
                    all_of=[
                        DateFilter(field="invalid_at", operator="is_null"),
                        DateFilter(field="expired_at", operator="is_null"),
                    ],
                ),
            ],
        ),
    )


def get_graph_context(client, graph_uuid, query, *, include_history=False):
    """Keep Zep's assembled context and selected results intact for inspection."""
    request = {
        "graph_uuid": graph_uuid,
        "query": query,
        "max_characters": 5000,
        "include_results": True,
    }
    if not include_history:
        request["filters"] = active_fact_filters()
    context_capture = {'request': request, 'context': None, 'results': None, 'truncated': None}
    capture = current_capture.get()
    if capture is not None:
        capture['contexts'].append(context_capture)
    result = client.graph.get_context(**request)
    if capture is not None:
        context_capture.update({
            'context': result.context,
            'results': result.results, 'truncated': result.truncated,
        })
    return result


def _recipe_source(episode):
    """Parse one episode when it contains a complete Crumbs recipe."""
    content = getattr(episode, "content", None)
    try:
        recipe = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(recipe, dict):
        return None
    metadata = getattr(episode, "metadata", None) or {}
    slug = metadata.get("recipe_slug") or getattr(episode, "document_id", None) or recipe.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        return None
    if recipe.get("slug", slug) != slug:
        return None
    title = recipe.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    ingredients = recipe.get("ingredient_sections", recipe.get("ingredients"))
    instructions = recipe.get("instruction_sections", recipe.get("instructions"))
    if not isinstance(ingredients, list) or not ingredients:
        return None
    if not isinstance(instructions, list) or not instructions:
        return None
    recipe["slug"] = slug
    for field in ("category", "tags"):
        if recipe.get(field) is None:
            recipe[field] = []
    for field in ("total_time_minutes", "calories", "protein", "carbs", "fat"):
        recipe.setdefault(field, None)
    return slug, recipe


def _latest_recipe_episodes(client, graph_uuid, recipe_slugs):
    if not recipe_slugs:
        return {}
    latest = {}
    sorted_slugs = sorted(recipe_slugs)
    for offset in range(0, len(sorted_slugs), 100):
        chunk = sorted_slugs[offset:offset + 100]
        filters = EpisodeListFilters(
            metadata_filters=MetadataFilterGroup(
                type="and",
                filters=[
                    MetadataFilter(
                        property_name="recipe_slug",
                        operator="in",
                        value=chunk,
                    ),
                ],
            ),
        )
        request = {
            "graph_uuid": graph_uuid,
            "filters": filters,
            "page_size": SEARCH_PAGE_SIZE,
            "order_by": "created_at",
            "order": "desc",
        }
        pager = client.graph.episode.list(**request)
        chunk_latest = {}
        for episode in pager:
            metadata = getattr(episode, "metadata", None) or {}
            slug = metadata.get("recipe_slug")
            if slug in chunk:
                chunk_latest.setdefault(slug, episode)
                if len(chunk_latest) == len(chunk):
                    break
        latest.update(chunk_latest)
    return latest


def get_source_recipes(
    client, graph_uuid, episode_uuids, *, include_history=False,
):
    """Resolve selected sources to full current or historical recipe snapshots."""
    source_by_slug = {}
    for episode_uuid in dict.fromkeys(episode_uuids):
        episode = client.graph.episode.get(graph_uuid, episode_uuid)
        parsed = _recipe_source(episode)
        if parsed is not None:
            source_by_slug.setdefault(parsed[0], []).append(episode)

    if include_history:
        selected = sorted(
            (episode for episodes in source_by_slug.values() for episode in episodes),
            key=lambda episode: getattr(episode, "created_at", None) or "",
        )
    else:
        latest = _latest_recipe_episodes(client, graph_uuid, set(source_by_slug))
        selected = []
        for slug, episodes in source_by_slug.items():
            # shortcut: legacy episodes lack revision metadata; reingest them to resolve all revisions.
            selected.append(latest.get(slug) or max(
                episodes, key=lambda episode: getattr(episode, "created_at", None) or "",
            ))

    recipes = []
    seen = set()
    for episode in selected:
        parsed = _recipe_source(episode)
        if parsed is None:
            continue
        slug, recipe = parsed
        identity = (slug, getattr(episode, "uuid_", None)) if include_history else slug
        if identity in seen:
            continue
        seen.add(identity)
        recipes.append(recipe)
    return recipes
