"""Backend-specific local Markdown traces for graph retrieval requests."""

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
GRAPHITI_CAPTURE_DIR = PROJECT_ROOT / '.graphiti/requests'
current_capture = ContextVar('chat_capture', default=None)
logger = logging.getLogger(__name__)


def _block(value, language='text'):
    text = value if isinstance(value, str) else json.dumps(
        jsonable_encoder(value, exclude_unset=True), ensure_ascii=False, indent=2,
    )
    fence = '`' * max(3, 1 + max((len(run) for run in re.findall(r'`+', text)), default=0))
    return f'{fence}{language}\n{text}\n{fence}\n'


def _readable_text(value):
    return (
        value.replace('\\r\\n', '\n')
        .replace('\\n', '\n')
        .replace('\\r', '\n')
        .replace('\r\n', '\n')
        .replace('\r', '\n')
    )


def _json_container(value):
    if not isinstance(value, str) or not value.lstrip().startswith(('{', '[')):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _readable_data(value, depth=0):
    value = jsonable_encoder(value, exclude_unset=True)
    indent = '  ' * depth
    if isinstance(value, dict):
        sections = []
        for key, item in value.items():
            label = str(key).replace('_', ' ').title()
            if str(key).endswith('_embedding') and isinstance(item, list):
                sections.append(f'{indent}- **{label}:** {len(item)} values (see exact payload).')
                continue
            if isinstance(item, (dict, list)):
                sections.extend([f'{indent}- **{label}:**', _readable_data(item, depth + 1)])
            elif isinstance(item, str):
                parsed = _json_container(item)
                if parsed is not None:
                    sections.extend([f'{indent}- **{label}:**', _readable_data(parsed, depth + 1)])
                    continue
                readable = _readable_text(item)
                if '\n' in readable:
                    sections.extend([
                        f'{indent}- **{label}:**',
                        _indent_block(_block(readable), depth + 1),
                    ])
                else:
                    sections.append(f'{indent}- **{label}:** {readable}')
            else:
                sections.append(f'{indent}- **{label}:** `{item}`')
        return '\n'.join(sections) if sections else f'{indent}- No fields returned.'
    if isinstance(value, list):
        sections = []
        for index, item in enumerate(value, start=1):
            if isinstance(item, (dict, list)):
                sections.extend([
                    f'{indent}- **Item {index}:**',
                    _readable_data(item, depth + 1),
                ])
            elif isinstance(item, str):
                parsed = _json_container(item)
                if parsed is not None:
                    sections.extend([
                        f'{indent}- **Item {index}:**',
                        _readable_data(parsed, depth + 1),
                    ])
                    continue
                readable = _readable_text(item)
                if '\n' in readable:
                    sections.extend([
                        f'{indent}- **Item {index}:**',
                        _indent_block(_block(readable), depth + 1),
                    ])
                else:
                    sections.append(f'{indent}- **Item {index}:** {readable}')
            else:
                sections.append(f'{indent}- **Item {index}:** `{item}`')
        return '\n'.join(sections) if sections else f'{indent}- No items returned.'
    if isinstance(value, str):
        parsed = _json_container(value)
        if parsed is not None:
            return _readable_data(parsed, depth)
        return _block(_readable_text(value))
    return f'`{value}`\n'


def _indent_block(block, depth):
    indent = '  ' * depth
    return '\n'.join(indent + line if line else '' for line in block.rstrip().splitlines()) + '\n'


def _readable_model_input(value):
    value = jsonable_encoder(value, exclude_unset=True)
    if not isinstance(value, dict):
        return _readable_data(value)

    sections = []
    for key in ('method', 'model'):
        if key in value:
            sections.append(f'**{key.title()}:** `{value[key]}`\n')
    if 'instructions' in value:
        sections.extend(['#### Instructions\n', _block(_readable_text(value['instructions']))])
    input_items = value.get('input', [])
    if not isinstance(input_items, list):
        input_items = [input_items]
    for index, item in enumerate(input_items, start=1):
        item = jsonable_encoder(item, exclude_unset=True)
        if isinstance(item, dict):
            role = item.get('role')
            function_type = item.get('type')
            name = item.get('name')
            if role:
                label = f'{role.title()} message'
            elif function_type == 'function_call':
                label = f'Tool call: {name or "unnamed"}'
            elif function_type == 'function_call_output':
                label = 'Retrieved information sent to the model'
            else:
                label = str(function_type or 'input item')
            sections.append(f'#### Input {index}: {label}\n')
            sections.append(_readable_data(item, depth=1))
        else:
            sections.extend([f'#### Input {index}\n', _readable_data(item, depth=1)])
    for key, item in value.items():
        if key in {'method', 'model', 'instructions', 'input'}:
            continue
        label = str(key).replace('_', ' ').title()
        sections.extend([f'#### {label}\n', _readable_data(item, depth=1)])
    return '\n'.join(sections)


def _readable_model_output(value):
    value = jsonable_encoder(value, exclude_unset=True)
    if isinstance(value, dict) and isinstance(value.get('text'), str):
        sections = ['### Text\n', _block(_readable_text(value['text']))]
        metadata = {key: item for key, item in value.items() if key != 'text'}
        if metadata:
            sections.extend(['### Response metadata\n', _readable_data(metadata)])
        return '\n'.join(sections)
    return _readable_data(value)


def _exact_payload(value, label='Exact payload'):
    return f'<details>\n<summary>{label}</summary>\n\n' + _block(value, 'json') + '\n</details>\n'


def write_ingestion_report(backend, record):
    directory = PROJECT_ROOT / f'.{backend}' / 'ingestion'
    try:
        record = jsonable_encoder(record)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / f'{datetime.now(UTC):%Y%m%dT%H%M%S.%fZ}-{uuid4().hex}.md'
        path.write_text(
            f'# {backend.title()} ingestion / storage inspection\n\n'
            + _readable_data(record) + '\n\n' + _exact_payload(record), encoding='utf-8',
        )
        return path
    except (OSError, TypeError, ValueError):
        logger.exception('Could not write %s ingestion report', backend)


def _markdown(record, approach):
    no_answer_call = record.get('answer_model_expected') and not record.get('answer_model_started')
    model_input = None if no_answer_call else record['model_input']
    sections = [
        '# Chat request\n', '## 1. User query\n',
        _block(_readable_text(record['query'])),
    ]
    if approach == 'zep':
        sections.append('## 2. Zep retrieval\n')
        if not record['contexts']:
            sections.append('No Zep context retrieved.\n')
        for index, context in enumerate(record['contexts'], start=1):
            sections.extend([
                f"### Zep search {index}: {context.get('scope', 'unspecified')} graph\n",
                _readable_data(context.get('configuration', {})),
                '#### Request\n', _readable_data(context['request']),
                _exact_payload(context['request']),
                '#### Materialized context\n',
                _block(_readable_text(context['context']))
                if context['context'] is not None else 'No context returned.\n',
                '#### Selected retrieval results\n',
                _readable_data({'results': context['results'], 'truncated': context['truncated']}),
                _exact_payload({'results': context['results'], 'truncated': context['truncated']}),
                '#### Supplemental recipe source fetches\n',
                _readable_data(context.get('sources', [])),
                _readable_data({'error': context['error']}) if 'error' in context else '',
            ])
    else:
        sections.append('## 2. Graphiti retrieval\n')
        if not record['graphiti_contexts']:
            sections.append('No Graphiti search was run.\n')
        for index, context in enumerate(record['graphiti_contexts'], start=1):
            sections.append(f'### Graphiti search {index}\n')
            sections.extend([
                '#### Search request\n', _readable_data(context['request']),
                _exact_payload(context['request']),
                '#### Configuration\n', _readable_data(context.get('configuration', {})),
                '#### Supplemental recipe source fetches\n', _readable_data(context.get('source_fetches', [])),
            ])
            sections.extend([
                '#### Native fact-search results\n', _readable_data(context.get('native_results', {})),
                _exact_payload(context.get('native_results', {}), 'Exact native fact-search results'),
            ])
            if context.get('results') is not None:
                sections.extend([
                    '#### Retrieved information prepared for the answer model\n',
                    _readable_data(context['results']),
                    _exact_payload(context['results'], 'Exact Graphiti tool result'),
                ])
            if context.get('error') is not None:
                sections.extend(['#### Search error\n', _readable_data(context['error'])])
    sections.extend([
        '### Tool calls and retrieval results\n',
        _readable_data([item for item in record.get('tool_results', []) if item['backend'] == approach]),
        '### Router LLM input\n',
        _readable_model_input(record['router_input']) if record.get('router_input') else 'No router call recorded.\n',
        _exact_payload(record['router_input']) if record.get('router_input') else '',
        '### Router LLM output\n', _readable_data(record.get('router_output')),
    ])
    sections.extend([
        '## 3. Final LLM input\n',
        '### Readable view\n',
        _readable_model_input(model_input)
        if model_input is not None else ('No answer-model call was made. Router request is recorded above.\n'
                                        if no_answer_call else 'No model call made.\n'),
        _exact_payload(model_input) if model_input is not None else '',
        '## 4. Final output\n',
        _readable_model_output(record['model_output'])
        if record['model_output'] is not None else 'No model output returned.\n',
        _exact_payload(record['model_output']) if record['model_output'] is not None else '',
    ])
    if 'response' in record:
        sections.extend(['### Application response\n', _block(record['response'], 'json')])
    if 'error' in record:
        sections.extend(['### Request failed\n', _block(record['error'], 'json')])
    return '\n'.join(sections)


@contextmanager
def capture_chat(question):
    record = {
        'query': question,
        'contexts': [],
        'tool_results': [],
        'router_input': None,
        'router_output': None,
        'graphiti_contexts': [],
        'zep_used': False,
        'graphiti_used': False,
        'model_input': None,
        'model_output': None,
    }
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
        for used, directory, approach in (
            (record['zep_used'], CAPTURE_DIR, 'zep'),
            (record['graphiti_used'], GRAPHITI_CAPTURE_DIR, 'graphiti'),
        ):
            if not used:
                continue
            try:
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                with (directory / filename).open('x', encoding='utf-8') as capture:
                    capture.write(_markdown(record, approach))
            except (OSError, TypeError, ValueError):
                logger.exception('Could not write %s chat capture to %s', approach, directory)
