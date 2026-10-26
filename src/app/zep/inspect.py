"""Explicit graph inspection; no ingestion, summarization, or answer-model calls."""
from zep_cloud.core.api_error import ApiError



def inspect_graph(client, graph_uuid, *, user_graph=False, episode_uuid=None, debug=False):
    report = {
        'graph_uuid': graph_uuid, 'sent_to_answer_model': False,
        'entities': list(client.graph.node.list(graph_uuid)),
        'facts': list(client.graph.edge.list(graph_uuid)),
        'episodes': list(client.graph.episode.list(graph_uuid)),
        'thread_summaries': list(client.graph.thread_summary.list(graph_uuid)),
    }
    if user_graph:
        report['user_summary'] = client.user.get_node(graph_uuid).summary
    if episode_uuid:
        report['episode'] = client.graph.episode.get(graph_uuid, episode_uuid)
    if debug and episode_uuid:
        try:
            report['debug_logs'] = client.graph.episode.get_debug_logs(graph_uuid, episode_uuid)
            report['ingestion_traces'] = list(client.graph.episode.list_ingestion_traces(graph_uuid, episode_uuid))
        except ApiError as error:
            report['diagnostics_unavailable'] = {'status_code': error.status_code}
    return report
