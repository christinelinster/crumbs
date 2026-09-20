"""Shared URL, Markdown, and naming helpers for recipe ingestion."""

from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

import yaml


def canonical_url(value: str) -> str:
    """Ignore fragments; retain paths and queries that identify recipes."""
    parts = urlsplit(value.strip())
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('expected an HTTP(S) URL')
    if parts.username or parts.password or any(c.isspace() for c in value.strip()):
        raise ValueError('URL contains credentials or whitespace')
    return urlunsplit((
        parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, '',
    ))


def frontmatter(path: Path) -> tuple[dict, str]:
    """Read YAML metadata and the remaining Markdown body from a corpus file."""
    text = path.read_text(encoding='utf-8')
    match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)', text, re.S)
    if not match:
        raise ValueError(f'{path}: missing YAML frontmatter')
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f'{path}: invalid YAML frontmatter') from exc
    if not isinstance(metadata, dict):
        raise ValueError(f'{path}: frontmatter must be a mapping')
    return metadata, text[match.end():]


def slugify(title: str) -> str:
    """Return a title-based name; callers choose fallbacks and handle collisions."""
    return re.sub(
        r'[^\w]+', '-', title.lower(), flags=re.UNICODE,
    ).strip('-_')[:100].rstrip('-')
