"""Import recipe URLs into the Markdown corpus without replacing existing files."""

import asyncio
from dataclasses import asdict
from hashlib import sha256
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
import yaml

from app.ingestion.normalize import normalize_recipe
from app.ingestion.web.jsonld import get_recipe_json_ld

ROOT = Path(__file__).resolve().parents[1]


def canonical_url(value: str) -> str:
    """Ignore fragment anchors; retain paths and queries that identify recipes."""
    parts = urlsplit(value.strip())
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('expected an HTTP(S) URL')
    if parts.username or parts.password or any(c.isspace() for c in value.strip()):
        raise ValueError('URL contains credentials or whitespace')
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, ''))


def frontmatter(path: Path) -> tuple[dict, str]:
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


def clean_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('expected text')
    return ' '.join(BeautifulSoup(value, 'html.parser').get_text(' ').split())


def validate_recipe(recipe):
    recipe.title = clean_text(recipe.title)
    if not recipe.title:
        raise ValueError('title is empty')
    for field in ('ingredients', 'instructions'):
        values = getattr(recipe, field)
        if not isinstance(values, list) or not values:
            raise ValueError(f'{field} must be a nonempty list')
        cleaned = [clean_text(value) for value in values]
        if not all(cleaned):
            raise ValueError(f'{field} contains empty text')
        setattr(recipe, field, cleaned)


def render_recipe(recipe, fields: dict, body: str) -> str:
    values = asdict(recipe)
    values['source_label'] = urlsplit(recipe.source_url).hostname
    unknown = fields.keys() - values.keys()
    if unknown:
        raise ValueError(f'unsupported template fields: {sorted(unknown)}')
    metadata = {key: values[key] for key in fields}
    ingredients = '\n'.join(f'- {line}' for line in recipe.ingredients)
    instructions = '\n'.join(f'{i}. {line}' for i, line in enumerate(recipe.instructions, 1))
    for heading, content in (('Ingredients', ingredients), ('Instructions', instructions)):
        marker = f'## {heading}'
        if body.splitlines().count(marker) != 1:
            raise ValueError(f'template must contain one {marker} heading')
        body = body.replace(marker, f'{marker}\n\n{content}', 1)
    return '---\n' + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + '---\n\n' + body.strip() + '\n'


def write_recipe(path: Path, text: str):
    # Publish a complete file atomically; link fails if the destination exists.
    with tempfile.TemporaryDirectory(prefix='.import-', dir=path.parent) as directory:
        temporary = Path(directory) / 'recipe.md'
        temporary.write_text(text, encoding='utf-8')
        os.link(temporary, path)


async def import_recipes(url_file: Path, output_dir: Path, template: Path) -> int:
    imported = skipped = failed = 0
    seen = set()
    try:
        lines = url_file.read_text(encoding='utf-8').splitlines()
        fields, body = frontmatter(template)
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in output_dir.glob('*.md'):
            metadata, _ = frontmatter(path)
            source = metadata.get('source_url')
            if source:
                if not isinstance(source, str):
                    raise ValueError(f'{path}: source_url must be text')
                try:
                    seen.add(canonical_url(source))
                except ValueError as exc:
                    raise ValueError(f'{path}: invalid source_url') from exc
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}')
        return 1

    for line in lines:
        url = line.strip()
        if not url or url.startswith('#'):
            continue
        try:
            url = canonical_url(url)
            if url in seen:
                skipped += 1
                print(f'SKIP {url}: already imported or listed')
                continue
            seen.add(url)
            raw = await get_recipe_json_ld(url)
            if raw is None:
                raise ValueError('no Recipe JSON-LD found')
            recipe = normalize_recipe(raw, url)
            validate_recipe(recipe)
            name = re.sub(r'[^\w]+', '-', recipe.title.lower(), flags=re.UNICODE).strip('-_')[:100].rstrip('-')
            if not name:
                digest = sha256(recipe.source_url.encode('utf-8')).hexdigest()[:8]
                name = f'recipe-{digest}'
            target = output_dir / f'{name}.md'
            markdown = render_recipe(recipe, fields, body)
            try:
                write_recipe(target, markdown)
            except FileExistsError as exc:
                raise ValueError(f'{target.name} already exists; refusing to overwrite') from exc
            imported += 1
            print(f'IMPORTED {url} -> {target}')
        except Exception as exc:
            # A failed URL must not prevent the rest of the batch from importing.
            failed += 1
            print(f'FAILED {url}: {type(exc).__name__}: {exc}')

    print(f'{imported} imported, {skipped} skipped, {failed} failed')
    return 1 if failed else 0


def main() -> int:
    return asyncio.run(import_recipes(
        ROOT / 'data/import/recipe-urls.txt',
        ROOT / 'data/recipes',
        ROOT / 'docs/recipe-corpus-template.md',
    ))


if __name__ == '__main__':
    raise SystemExit(main())
