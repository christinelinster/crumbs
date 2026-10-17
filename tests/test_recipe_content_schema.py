"""PostgreSQL integration check for fresh recipe schema setup."""

import os
from pathlib import Path
import unittest

from app.db.connection import pool
from app.db.setup import render_schema
from psycopg.errors import CheckViolation


SCHEMA_SQL_PATH = (
    Path(__file__).resolve().parents[1] / "src/app/db/schema.sql"
)


@unittest.skipUnless(
    os.getenv("CRUMBS_RUN_PG_SCHEMA_TESTS") == "1",
    "set CRUMBS_RUN_PG_SCHEMA_TESTS=1 to run the PostgreSQL schema check",
)
class RecipeContentSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pool.open()

    @classmethod
    def tearDownClass(cls):
        pool.close()

    def test_schema_creates_sections_and_reruns_without_losing_data(self):
        schema_sql = render_schema(SCHEMA_SQL_PATH.read_text(encoding="utf-8"))

        with pool.connection() as conn:
            with conn.transaction():
                conn.execute("SAVEPOINT fresh_schema_verification")
                conn.execute("SET LOCAL search_path TO pg_temp, public")
                conn.execute(schema_sql)

                columns = conn.execute(
                    """
                    SELECT attname, format_type(atttypid, atttypmod)
                    FROM pg_attribute
                    WHERE attrelid = 'pg_temp.recipes'::regclass
                      AND attnum > 0 AND NOT attisdropped
                      AND attname IN ('ingredient_sections', 'instruction_sections')
                    ORDER BY attname
                    """
                ).fetchall()
                self.assertEqual(columns, [
                    ("ingredient_sections", "jsonb"),
                    ("instruction_sections", "jsonb"),
                ])
                self.assertIsNone(conn.execute(
                    "SELECT to_regclass('pg_temp.recipe_ingredients')"
                ).fetchone()[0])
                self.assertIsNone(conn.execute(
                    "SELECT to_regclass('pg_temp.recipe_steps')"
                ).fetchone()[0])

                conn.execute(
                    "INSERT INTO recipes (slug, title, description) VALUES (%s, %s, %s)",
                    ("fresh-setup", "Fresh setup", "Sentinel row"),
                )
                row = conn.execute(
                    """
                    SELECT slug, title, description, ingredient_sections,
                           instruction_sections
                    FROM recipes
                    WHERE slug = 'fresh-setup'
                    """
                ).fetchone()
                self.assertEqual(row, (
                    "fresh-setup", "Fresh setup", "Sentinel row", [], [],
                ))

                with self.assertRaises(CheckViolation):
                    with conn.transaction():
                        conn.execute(
                            "UPDATE recipes SET ingredient_sections = '{}'::jsonb "
                            "WHERE slug = 'fresh-setup'"
                        )

                conn.execute(schema_sql)
                rerun = conn.execute(
                    """
                    SELECT slug, title, description, ingredient_sections,
                           instruction_sections
                    FROM recipes
                    WHERE slug = 'fresh-setup'
                    """
                ).fetchone()
                self.assertEqual(rerun, row)
                conn.execute("ROLLBACK TO SAVEPOINT fresh_schema_verification")
                conn.execute("RELEASE SAVEPOINT fresh_schema_verification")


if __name__ == "__main__":
    unittest.main()
