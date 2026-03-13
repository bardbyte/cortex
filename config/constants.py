"""Constants for the DMP-ESL-Agent project."""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


def _get_required_env(var_name: str) -> str:
    """Get required environment variable, raise error if missing."""
    value = os.getenv(var_name)
    if value is None or value.strip() == "":
        raise ValueError(f"Required environment variable '{var_name}' is not set.")
    return value


# Embedding model index from config.yml
# Embedding '2' is configured as type: embedding, provider: vertex, model_name: bge
EMBED_MODEL_IDX = '2'

# Default Looker model allowlist (used by API loader when required_models is explicitly passed.
DEFAULT_REQUIRED_LOOKER_MODELS = ["proj-d-lumi-gpt"]

# PostgreSQL connection values from .env
POSTGRES_HOST = _get_required_env("POSTGRES_HOST")
POSTGRES_PORT = int(_get_required_env("POSTGRES_PORT"))
POSTGRES_DBNAME = _get_required_env("POSTGRES_DBNAME")
POSTGRES_USER = _get_required_env("POSTGRES_USER")
POSTGRES_PASSWORD = _get_required_env("POSTGRES_PASSWORD")

# SQL statements
SQL_CREATE_VECTOR_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"

SQL_CREATE_FIELD_EMBEDDINGS_TABLE = """
CREATE TABLE IF NOT EXISTS field_embeddings (
    id SERIAL PRIMARY KEY,
    field_key TEXT UNIQUE NOT NULL,
    embedding VECTOR(1024),
    content TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_type TEXT NOT NULL,
    measure_type TEXT,
    view_name TEXT NOT NULL,
    explore_name TEXT NOT NULL,
    model_name TEXT,
    label TEXT,
    group_label TEXT,
    tags TEXT,
    hidden BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
)"""

SQL_CREATE_FIELD_EMBEDDINGS_HNSW_INDEX = """
CREATE INDEX IF NOT EXISTS field_embeddings_hnsw_idx ON field_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
"""

SQL_UPSERT_FIELD_EMBEDDING_RECORD = """
INSERT INTO field_embeddings (
    id,
    field_key,
    embedding,
    content,
    field_name,
    field_type,
    measure_type,
    view_name,
    explore_name,
    model_name,
    label,
    group_label,
    tags,
    hidden,
    created_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (field_key) DO UPDATE SET
    embedding = EXCLUDED.embedding,
    content = EXCLUDED.content,
    id = EXCLUDED.id,
    field_name = EXCLUDED.field_name,
    field_type = EXCLUDED.field_type,
    measure_type = EXCLUDED.measure_type,
    view_name = EXCLUDED.view_name,
    explore_name = EXCLUDED.explore_name,
    model_name = EXCLUDED.model_name,
    label = EXCLUDED.label,
    group_label = EXCLUDED.group_label,
    tags = EXCLUDED.tags,
    hidden = EXCLUDED.hidden,
    created_at = EXCLUDED.created_at;
"""

SQL_RETRIEVE_TOP_K_BY_DISTANCE = """
SELECT id, field_key, content, field_name, field_type, measure_type, view_name,
    explore_name, model_name, label, group_label, tags, hidden, created_at
FROM field_embeddings
ORDER BY embedding <=> :embedding
LIMIT :limit;
"""

SQL_COUNT_FIELD_EMBEDDINGS = "SELECT count(*) FROM field_embeddings;"

SQL_SAMPLE_FIELD_EMBEDDINGS = """
SELECT id, field_key, content, field_name, field_type, measure_type, view_name,
    explore_name, model_name, label, group_label, tags, hidden, created_at
FROM field_embeddings
LIMIT 5;
"""

SQL_VERIFY_VECTOR_SELF_MATCH = """
SELECT field_key
FROM field_embeddings
ORDER BY embedding <=> embedding
LIMIT 5;
"""

SQL_SEARCH_SIMILAR_FIELDS = """
SELECT
    field_key,
    field_name,
    label,
    explore_name,
    view_name,
    field_type,
    measure_type,
    1 - (embedding <=> :embedding) AS similarity
FROM field_embeddings
WHERE hidden = FALSE
ORDER BY embedding <=> :embedding
LIMIT :limit;
"""
