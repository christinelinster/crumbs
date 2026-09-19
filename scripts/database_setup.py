from app.db.connection import pool


def setup_database():
    schema_sql = """
        CREATE TABLE IF NOT EXISTS test (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
        );
    """

    with pool:
        with pool.connection() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.execute(schema_sql)


if __name__ == "__main__":
    try:
        setup_database()
        print("Database setup complete!")
    except Exception as error:
        print("Error during setup:", error)
        raise