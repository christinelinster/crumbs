"""Raw graph searches and stable source recipe identities."""


def search_recipes(client, graph_uuid, query):
    return client.graph.search_edges(graph_uuid, query=query)


def search_preferences(client, user_uuid, query):
    return client.graph.search_edges(user_uuid, query=query)


def get_recipe_slugs(client, graph_uuid, graph_facts):
    """Resolve source episodes to stable slugs; never guess from fact text."""
    episode_uuids = dict.fromkeys(
        episode_uuid
        for fact in graph_facts
        for episode_uuid in fact.get('episode_uuids', [])
    )
    slugs = []
    for episode_uuid in episode_uuids:
        episode = client.graph.episode.get(graph_uuid, episode_uuid)
        slug = (episode.metadata or {}).get('recipe_slug') or episode.document_id
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs
