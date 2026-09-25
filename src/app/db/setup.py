from app.paths import SCHEMA_PATH
from app.db.connection import pool
from app.settings import EMBEDDING_DIMENSIONS


def render_schema(schema_sql: str) -> str:
    """Render validated runtime settings into the fresh-schema template."""
    return schema_sql.replace(
        "__EMBEDDING_DIMENSIONS__",
        str(EMBEDDING_DIMENSIONS),
    )


def setup_database() -> None:
    """Initialize the recipe schema in a single transaction."""
    schema_sql = render_schema(SCHEMA_PATH.read_text(encoding="utf-8"))

    with pool:
        with pool.connection() as conn:
            with conn.transaction():
                conn.execute(schema_sql)


if __name__ == "__main__":
    try:
        setup_database()
        print("Database setup complete!")
    except Exception as error:
        print("Error during setup:", error)
        raise
