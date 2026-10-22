"""One local Markdown capture for each handled chat request."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
import json
import logging
import re
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from app.paths import PROJECT_ROOT


CAPTURE_DIR = PROJECT_ROOT / '.zep/requests'
current_capture = ContextVar('chat_capture', default=None)
logger = logging.getLogger(__name__)


def _block(value, language='text'):
    text = value if isinstance(value, str) else json.dumps(
        jsonable_encoder(value, exclude_unset=True), ensure_ascii=False, indent=2,
    )
    fence = '`' * max(3, 1 + max((len(run) for run in re.findall(r'`+', text)), default=0))
    return f'{fence}{language}\n{text}\n{fence}\n'


def _markdown(record):
    sections = ['# Chat request\n', '## 1. User query\n', _block(record['query'])]
    sections.append('## 2. Zep context blocks\n')
    if not record['contexts']:
        sections.append('No Zep context retrieved.\n')
    for context in record['contexts']:
        sections.extend([
            '### Zep request\n', _block(context['request'], 'json'),
            '### Materialized context block\n',
            _block(context['context']) if context['context'] is not None else 'No context returned.\n',
            '### Selected retrieval results\n', _block({
                'results': context['results'], 'truncated': context['truncated'],
            }, 'json'),
        ])
    sections.extend([
        '## 3. Final LLM input\n',
        _block(record['model_input'], 'json') if record['model_input'] is not None else 'No model call made.\n',
        '## 4. Final output\n',
        _block(record['model_output'], 'json') if record['model_output'] is not None else 'No model output returned.\n',
    ])
    if 'response' in record:
        sections.extend(['### Application response\n', _block(record['response'], 'json')])
    if 'error' in record:
        sections.extend(['### Request failed\n', _block(record['error'], 'json')])
    return '\n'.join(sections)


@contextmanager
def capture_chat(question):
    record = {'query': question, 'contexts': [], 'model_input': None, 'model_output': None}
    token = current_capture.set(record)
    filename = f'{datetime.now(UTC):%Y%m%dT%H%M%S.%fZ}-{uuid4().hex}.md'
    try:
        yield record
    except Exception as error:
        cause = error.__cause__ or error
        record['error'] = {
            'type': type(cause).__name__, 'status_code': getattr(error, 'status_code', None),
        }
        raise
    finally:
        current_capture.reset(token)
        try:
            CAPTURE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (CAPTURE_DIR / filename).open('x', encoding='utf-8') as capture:
                capture.write(_markdown(record))
        except (OSError, TypeError, ValueError):
            logger.exception('Could not write chat capture to %s', CAPTURE_DIR)
