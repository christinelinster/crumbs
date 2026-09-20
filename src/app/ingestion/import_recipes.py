"""Import recipe URLs into the Markdown corpus without replacing existing files."""

import asyncio
from dataclasses import asdict
from hashlib import sha256
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
import yaml

from app.paths import RECIPE_URLS_PATH, RECIPES_DIR, RECIPE_TEMPLATE_PATH
from app.ingestion.normalize import normalize_recipe
from app.ingestion.utils import canonical_url, frontmatter, slugify
from app.ingestion.web.jsonld import get_recipe_json_ld


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


def render_recipe(recipe, fields: dict, body: str, slug: str) -> str:
    values = asdict(recipe)
    values['slug'] = slug
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


def available_slug(base_slug: str, output_dir: Path, used_slugs: set[str]) -> str:
    """Return the first unused slug, preserving the base slug when possible."""
    candidate = base_slug
    suffix = 2
    while candidate in used_slugs or (output_dir / f'{candidate}.md').exists():
        candidate = f'{base_slug}-{suffix}'
        suffix += 1
    return candidate


async def import_recipes(url_file: Path, output_dir: Path, template: Path) -> int:
    imported = skipped = failed = 0
    # Source URLs are a uniqueness check for web imports, not the database
    # identity. The persisted slug still controls recipe lookup and updates.
    seen_urls = set()
    used_slugs = set()
    try:
        lines = url_file.read_text(encoding='utf-8').splitlines()
        fields, body = frontmatter(template)
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in output_dir.glob('*.md'):
            metadata, _ = frontmatter(path)
            existing_slug = metadata.get('slug')
            if not isinstance(existing_slug, str) or not existing_slug.strip():
                raise ValueError(f'{path}: slug must be nonempty text')
            existing_slug = slugify(existing_slug)
            if not existing_slug:
                raise ValueError(f'{path}: slug must contain usable text')
            used_slugs.add(existing_slug)
            source = metadata.get('source_url')
            if source:
                if not isinstance(source, str):
                    raise ValueError(f'{path}: source_url must be text')
                try:
                    seen_urls.add(canonical_url(source))
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
            if url in seen_urls:
                skipped += 1
                print(f'SKIP {url}: already imported or listed')
                continue
            seen_urls.add(url)
            raw = await get_recipe_json_ld(url)
            if raw is None:
                raise ValueError('no Recipe JSON-LD found')
            recipe = normalize_recipe(raw, url)
            validate_recipe(recipe)
            slug = slugify(recipe.title)
            if not slug:
                digest = sha256(recipe.source_url.encode('utf-8')).hexdigest()[:8]
                slug = f'recipe-{digest}'
            slug = available_slug(slug, output_dir, used_slugs)
            target = output_dir / f'{slug}.md'
            markdown = render_recipe(recipe, fields, body, slug)
            try:
                write_recipe(target, markdown)
            except FileExistsError as exc:
                raise ValueError(f'{target.name} already exists; refusing to overwrite') from exc
            used_slugs.add(slug)
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
        RECIPE_URLS_PATH,
        RECIPES_DIR,
        RECIPE_TEMPLATE_PATH,
    ))


if __name__ == '__main__':
    raise SystemExit(main())
