"""Direct SDK writes for recipe episodes and current conversation turns."""
import hashlib
import json


def serialize_recipe(recipe):
    return json.dumps(recipe, ensure_ascii=False)


def ingest_recipe(client, graph_uuid, recipe):
    serialized_recipe = serialize_recipe(recipe)
    canonical_recipe = json.dumps(
        recipe,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    revision = hashlib.sha256(canonical_recipe.encode("utf-8")).hexdigest()
    return client.graph.episode.add(
        graph_uuid,
        type="json",
        data=serialized_recipe,
        document_id=recipe["slug"],
        metadata={"recipe_slug": recipe["slug"], "recipe_revision": revision},
        source_description="Crumbs recipe",
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
