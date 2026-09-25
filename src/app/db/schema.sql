CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS recipes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,

    category TEXT[] NOT NULL DEFAULT '{}',
    tags TEXT[] NOT NULL DEFAULT '{}',
    cuisine TEXT,

    total_time_minutes INTEGER CHECK (total_time_minutes >= 0),
    servings INTEGER CHECK (servings > 0),

    calories NUMERIC CHECK (calories >= 0),
    protein NUMERIC CHECK (protein >= 0),
    carbs NUMERIC CHECK (carbs >= 0),
    fat NUMERIC CHECK (fat >= 0),

    source_label TEXT,
    source_url TEXT UNIQUE,
    notes TEXT,

    ingredient_sections JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(ingredient_sections) = 'array'),
    instruction_sections JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(instruction_sections) = 'array'),

    embedding VECTOR(1536)
);

  -- Embedding dimension migration for an existing database
  --
  -- The CREATE TABLE definition above is the fresh-database default. If a new
  -- embedding model returns a different vector dimension, replace 3072 below
  -- with the model's dimension and run this block against the existing
  -- database before running app.ingestion.load_embeddings. It intentionally
  -- clears the old vectors because vectors from different dimensions or
  -- embedding models must not be mixed.
  --
  -- BEGIN;
  -- ALTER TABLE recipes
  --     ALTER COLUMN embedding TYPE VECTOR(3072)
  --     USING NULL::VECTOR(3072);
  -- COMMIT;
  --
  -- Then regenerate every recipe vector:
  -- poetry run python -m app.ingestion.load_embeddings
