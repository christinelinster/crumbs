"""Direct SDK writes for recipe episodes and current conversation turns."""
import json


def serialize_recipe(recipe):
    return json.dumps(recipe, ensure_ascii=False)


def ingest_recipe(client, graph_uuid, recipe):
    return client.graph.episode.add(
        graph_uuid,
        type='json',
        data=serialize_recipe(recipe),
        document_id=recipe['slug'],
        source_description='Crumbs recipe',
    )


def save_messages(client, thread_uuid, question, answer):
    from zep_cloud import AddMessage

    return client.thread.add_messages(
        thread_uuid,
        messages=[
            AddMessage(role='user', content=question),
            AddMessage(role='assistant', content=answer),
        ],
        ignore_roles=['assistant'],
    )
