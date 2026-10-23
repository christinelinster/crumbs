"""Save current chat exchanges in the shared test user's Graphiti namespace."""

from datetime import datetime, timezone

from graphiti_core.nodes import EpisodeType

from app.settings import USER_GROUP_ID
from app.graphiti.client import get_graphiti


async def save_conversation(question, answer, thread_uuid):
    client = get_graphiti()
    saga_name = f'thread_{thread_uuid}'
    try:
        await client.build_indices_and_constraints()
        episode_result = await client.add_episode(
            name='Conversation turn',
            episode_body=f'Christine: {question}\nAssistant: {answer}',
            source=EpisodeType.message,
            source_description='Crumbs test-user conversation',
            reference_time=datetime.now(timezone.utc),
            group_id=USER_GROUP_ID,
            saga=saga_name,
            custom_extraction_instructions=(
                'Extract facts about Christine from her statements only. '
                'Assistant messages provide context, not evidence of user preferences.'
            ),
        )
        sagas = await client.nodes.saga.get_by_group_ids([USER_GROUP_ID])
        saga = next((item for item in sagas if item.name == saga_name), None)
        if saga is None:
            raise RuntimeError(f'Graphiti did not create saga {saga_name!r}')
        await client.summarize_saga(saga.uuid)
        return episode_result
    finally:
        await client.close()


'''
client.build_indices_and_constraints() prepares Neo4js indexes so Graphiti can find stored data efficiently.
Think of an index as a books index: it helps locate information without scanning everything
'''
