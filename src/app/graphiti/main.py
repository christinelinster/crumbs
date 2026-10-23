import argparse
import asyncio
import logging
from logging import INFO
from pathlib import Path

from app.graphiti.client import get_graphiti
from app.graphiti.ingest import ingest_recipe


logging.basicConfig(
    level=INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


async def main(path: Path):
    client = get_graphiti()
    try:
        await client.build_indices_and_constraints()
        result = await ingest_recipe(client, path)
        print('Episode:', result.episode.uuid)
        for node in result.nodes:
            print('Entity:', node.name, node.labels, node.attributes)
        for edge in result.edges:
            print('Relationship:', edge.name, edge.fact)
    finally:
        await client.close()


def cli(argv=None):
    parser = argparse.ArgumentParser(description='Ingest one Markdown recipe into Graphiti.')
    parser.add_argument('path', type=Path, help='Markdown file path, relative to your working directory or absolute')
    args = parser.parse_args(argv)
    if not args.path.is_file():
        parser.error(f'file not found: {args.path}')
    asyncio.run(main(args.path))


if __name__ == '__main__':
    cli()
