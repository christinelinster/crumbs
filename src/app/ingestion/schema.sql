CREATE TABLE recipes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    cuisine TEXT,
    cook_time TEXT,
    servings TEXT,
    source_url TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO recipes (
    title,
    cuisine,
    cook_time,
    servings,
    source_url
)
VALUES ($1, $2, $3, $4, $5)
RETURNING id;