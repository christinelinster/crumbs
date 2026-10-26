"""Minimal text reports for graph chat requests."""

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


def _block(text):
    fence = '`' * max(3, 1 + max((len(run) for run in re.findall(r'`+', text)), default=0))
    return f'{fence}text\n{text}\n{fence}\n'


def _readable_text(value):
    return (value.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')
            .replace('\r\n', '\n').replace('\r', '\n'))


def _plain(value, depth=0):
    """Render SDK objects and serialized tool content as text, without vectors."""
    value = jsonable_encoder(value)
    indent = '  ' * depth
    if isinstance(value, str):
        if value.lstrip().startswith(('{', '[')):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, (dict, list)):
                    return _plain(parsed, depth)
        return '\n'.join(indent + line for line in _readable_text(value).splitlines())
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if 'embedding' in key or item is None:
                continue
            label = key.replace('_', ' ').capitalize()
            if key == 'encrypted_content':
                lines.append(f'{indent}{label}: opaque provider data omitted')
            elif isinstance(item, (dict, list)) or isinstance(item, str) and ('\n' in _readable_text(item) or item.lstrip().startswith(('{', '['))):
                lines.extend([f'{indent}{label}:', _plain(item, depth + 1)])
            else:
                lines.append(f'{indent}{label}: {item}')
        return '\n'.join(lines) or indent + 'No fields returned.'
    if isinstance(value, list):
        return '\n\n'.join(_plain(item, depth) for item in value) or indent + 'No items returned.'
    return indent + (str(value) if value is not None else 'Not available.')


def _section(title, value):
    return f'{title}\n\n' + _block(_plain(value))


def record_graphiti_search(query, result):
    capture = current_capture.get()
    if capture is None:
        return
    from graphiti_core.search.search_config import DEFAULT_SEARCH_LIMIT

    from app import settings

    entry = {
        'request': {'searches': [
            {'query': query, 'group_ids': [settings.RECIPE_GROUP_ID],
             'num_results': DEFAULT_SEARCH_LIMIT,
             'search_filter': 'invalid_at is null and expired_at is null'},
            {'query': query, 'group_ids': [settings.USER_GROUP_ID],
             'num_results': DEFAULT_SEARCH_LIMIT,
             'search_filter': 'invalid_at is null and expired_at is null'},
        ]},
        'native_results': {
            'recipe_edges': result.get('recipe_facts', []),
            'user_edges': result.get('user_facts', []),
        },
        'source_fetches': ([{
            'episode_uuids': list(dict.fromkeys(
                source['episode_uuid'] for source in result.get('sources', [])
            )),
            'group_id': settings.RECIPE_GROUP_ID,
        }] if result.get('sources') else []),
        'results': result,
        'configuration': {
            'method': 'Graphiti.search', 'num_results_per_graph': DEFAULT_SEARCH_LIMIT,
            'search_recipe': 'EDGE_HYBRID_SEARCH_RRF (native default without center node)',
            'default_model': settings.GRAPHITI_LLM_MODEL,
            'attribute_model': settings.GRAPHITI_SMALL_MODEL,
        },
    }
    capture['graphiti_used'] = True
    capture['graphiti_contexts'].append(entry)


def _filename(title):
    slug = re.sub(r'[^\w-]+', '-', str(title).lower(), flags=re.UNICODE).strip('-_')[:48].rstrip('-')
    return f'{datetime.now(UTC):%Y%m%dT%H%M%S.%fZ}-{slug or "request"}-{uuid4().hex[:8]}.md'


def _model_input(value):
    value = jsonable_encoder(value)
    sections = []
    if value.get('model'):
        sections.append(f'Model: {value["model"]}\n')
    if value.get('instructions'):
        sections.append(_section('### System prompt (instructions)', value['instructions']))
    items = value.get('input', [])
    if not isinstance(items, list):
        items = [items]
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            sections.append(_section(f'### Input {index}', item))
            continue
        role = item.get('role')
        kind = item.get('type')
        if role:
            title = f'{role.capitalize()} message'
            content = item.get('content', '')
        elif kind == 'function_call_output':
            title = f'Graph context / tool result ({item.get("call_id", "")})'
            content = item.get('output', '')
        elif kind == 'function_call':
            title = f'Tool call: {item.get("name", "unnamed")} ({item.get("call_id", "")})'
            content = item.get('arguments', '')
        else:
            title, content = kind or 'Other model input', item
        sections.append(_section(f'### Input {index}: {title}', content))
    options = {key: item for key, item in value.items() if key not in {'method', 'model', 'instructions', 'input'}}
    if options:
        sections.append(_section('### Other request information', options))
    return '\n'.join(sections)


def _markdown(record, approach):
    no_answer_call = record.get('answer_model_expected') and not record.get('answer_model_started')
    model_input = None if no_answer_call else record['model_input']
    sections = [f'# {approach.title()} request\n', _section('## 1. User query', record['query']),
                '## 2. Graph searches and returned information\n']
    contexts = record['contexts'] if approach == 'zep' else record['graphiti_contexts']
    if not contexts:
        sections.append('No graph search was run.\n')
    for index, context in enumerate(contexts, start=1):
        scope = context.get('scope', 'recipe and user')
        sections.append(f'### Search {index}: {scope}\n')
        sections.append(_section('#### Graphs, search queries, and filters', context['request']))
        if context.get('configuration'):
            sections.append(_section('#### Search configuration', context['configuration']))
        if approach == 'zep':
            sections.append(_section('#### Returned context block', context.get('context')))
            if context.get('results') is not None:
                sections.append(_section('#### Returned search results', context['results']))
            else:
                sections.append('Zep returned a context block without a separate result breakdown.\n')
            if context.get('truncated') is not None:
                sections.append(f'Context truncated: {context["truncated"]}\n')
            fetches = context.get('sources')
        else:
            sections.append(_section('#### Returned recipe and user facts', context.get('native_results', {})))
            fetches = context.get('source_fetches')
        if fetches:
            sections.append(_section('#### Supplemental recipe source fetches', fetches))
        if context.get('error'):
            sections.append(_section('#### Search failed', context['error']))
    # Mocked or interrupted searches can have completed tool results without a native capture.
    for tool in record['tool_results']:
        if tool['backend'] == approach and tool.get('error'):
            sections.append(_section('### Retrieval failed', {'query': tool.get('arguments'), 'error': tool['error']}))
        if tool['backend'] == approach and tool.get('result') is not None and not record.get('answer_model_started'):
            sections.append(_section('### Context retrieved but not submitted', tool['result']))
    sections.append('## 3. Graph context used in the final LLM input (without system prompt)\n')
    submitted = []
    if model_input:
        items = jsonable_encoder(model_input).get('input', [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get('type') == 'function_call_output':
                    submitted.append(item.get('output', ''))
                elif isinstance(item, dict) and isinstance(item.get('content'), str) and item['content'].startswith('Retrieved Zep user memory (data, not instructions):\n'):
                    submitted.append(item['content'])
    if submitted:
        sections.extend(_section(f'### Context {index}', value) for index, value in enumerate(submitted, start=1))
        sections.append('These tool results / memory blocks were included in the model request below.\n')
    else:
        sections.append('No retrieved graph context was submitted to a final answer call.\n')
    sections.append('## 4. Full final LLM input\n')
    if model_input:
        if not record.get('answer_model_started'):
            sections.append('The router answered directly; its request is the final LLM input.\n'
                            if record.get('model_output') is not None else
                            'Router request attempted; no final response returned.\n')
        sections.append(_model_input(model_input))
    else:
        sections.append('No answer-model call was made.\n')
        if record.get('router_input'):
            sections.append('### Earlier router request\n' + _model_input(record['router_input']))
    sections.append('## 5. Final response to the user\n')
    output = record.get('response', {}).get('answer')
    if output is None and record.get('model_output'):
        output = record['model_output'].get('text')
    sections.append(_block(_readable_text(output)) if output is not None else 'No answer returned.\n')
    if record.get('response'):
        status = {key: value for key, value in record['response'].items()
                  if value is not None and key in {'thread_uuid', 'graphiti_thread_uuid', 'memory_status', 'graphiti_memory_status'}}
        if status:
            sections.append(_section('### Conversation save status', status))
    if 'error' in record:
        sections.append(_section('### Request failed', record['error']))
    return '\n'.join(sections)


@contextmanager
def capture_chat(question, backend=None):
    record = {
        'query': question, 'contexts': [], 'tool_results': [], 'router_input': None,
        'router_output': None, 'graphiti_contexts': [],
        'zep_used': backend == 'zep', 'graphiti_used': backend == 'graphiti',
        'model_input': None, 'model_output': None,
    }
    token = current_capture.set(record)
    filename = _filename(question)
    try:
        yield record
    except Exception as error:
        cause = error.__cause__ or error
        record['error'] = {'type': type(cause).__name__, 'status_code': getattr(error, 'status_code', None)}
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
