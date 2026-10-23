"""Read stored entities, facts, episodes, and summaries without changing them."""
from app.chat_capture import write_ingestion_report


async def inspect_graph(client, group_id):
    report = {
        'group_id': group_id, 'sent_to_answer_model': False,
        'entities': await client.nodes.entity.get_by_group_ids([group_id]),
        'facts': await client.edges.entity.get_by_group_ids([group_id]),
        'episodes': await client.nodes.episode.get_by_group_ids([group_id]),
        'sagas': await client.nodes.saga.get_by_group_ids([group_id]),
        'communities': await client.nodes.community.get_by_group_ids([group_id]),
    }
    write_ingestion_report('graphiti', report)
    return report
