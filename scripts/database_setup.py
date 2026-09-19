from pathlib import Path
from app.db.connection import pool

def setup_database() -> None:
    """Initialize the database from schema.sql in a single transaction."""
    schema_path = Path(__file__).resolve().parents[1] / "src/app/db/schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

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
