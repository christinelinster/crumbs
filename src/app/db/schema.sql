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

      embedding VECTOR(1536)
  );

  CREATE TABLE IF NOT EXISTS recipe_ingredients (
      recipe_id BIGINT NOT NULL
          REFERENCES recipes(id) ON DELETE CASCADE,

      position INTEGER NOT NULL CHECK (position > 0),
      raw_text TEXT NOT NULL,
      normalized_name TEXT,

      PRIMARY KEY (recipe_id, position)
  );

  CREATE INDEX IF NOT EXISTS recipe_ingredients_normalized_name_idx
      ON recipe_ingredients (normalized_name)
      WHERE normalized_name IS NOT NULL;

  CREATE TABLE IF NOT EXISTS recipe_steps (
      recipe_id BIGINT NOT NULL
          REFERENCES recipes(id) ON DELETE CASCADE,

      position INTEGER NOT NULL CHECK (position > 0),
      instruction TEXT NOT NULL,

      PRIMARY KEY (recipe_id, position)
  );