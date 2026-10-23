"""Submit recipe Markdown to Zep's default extraction pipeline."""
from pathlib import Path

from app.chat_capture import write_ingestion_report


def ingest_recipe(client, graph_uuid, path: Path):
    markdown = path.read_text(encoding='utf-8')
    report = {
        'graph_uuid': graph_uuid, 'source_path': str(path),
        'source_markdown': markdown, 'extraction': 'Zep-managed defaults',
    }
    try:
        result = client.graph.episode.add(
            graph_uuid, type='text', data=markdown,
            document_id=path.stem, source_description='Crumbs recipe Markdown',
        )
        report.update(status='submitted; extraction is asynchronous', submission=result)
        return result
    except Exception as error:
        report.update(status='submission failed', error={'type': type(error).__name__})
        raise
    finally:
        write_ingestion_report('zep', report)
