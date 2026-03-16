"""Constants for the Cortex retrieval pipeline."""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


def _get_required_env(var_name: str) -> str:
    """Get required environment variable, raise error if missing."""
    value = os.getenv(var_name)
    if value is None or value.strip() == "":
        raise ValueError(f"Required environment variable '{var_name}' is not set.")
    return value


# ─── Model Indices (from config.yml) ─────────────────────────────────
# Model "1" = Gemini 2.5 Pro (LLM for entity extraction)
# Model "2" = BGE-large-en-v1.5 (embedding for vector search, 1024-dim)
LLM_MODEL_IDX = '1'
EMBED_MODEL_IDX = '2'

# Default Looker model allowlist
DEFAULT_REQUIRED_LOOKER_MODELS = ["proj-d-lumi-gpt"]

# Explore → Base View mapping (from LookML model `from:` declarations)
# Used for explore scoring: fields from an explore's base view get a strong bonus
# because the explore was DESIGNED to analyze that view's data.
# Fields reachable only via JOINs are secondary.
EXPLORE_BASE_VIEWS = {
    "finance_cardmember_360": "custins_customer_insights_cardmember",
    "finance_merchant_profitability": "fin_card_member_merchant_profitability",
    "finance_travel_sales": "tlsarpt_travel_sales",
    "finance_card_issuance": "gihr_card_issuance",
    "finance_customer_risk": "risk_indv_cust",
}

# Explore descriptions from LookML model — used for tiebreaking when
# base_view_bonus can't discriminate (e.g., all entities from joined views)
EXPLORE_DESCRIPTIONS = {
    "finance_cardmember_360": "Comprehensive card member view combining customer activity (billed business, active status, tenure), demographics (generation, card type), risk indicators (revolve index), and organizational context. Use for segmentation, portfolio health, and cross-dimensional analysis.",
    "finance_merchant_profitability": "Analyze card member spending by merchant category, Return on Capital (ROC) metrics, and dining behavior. Join with demographics for segmented profitability analysis.",
    "finance_travel_sales": "Analyze Travel and Lifestyle Services revenue by travel vertical (Vacation, Business, Transit), air trip type (Round Trip, One Way), and hotel metrics. Join with demographics for customer segmentation.",
    "finance_card_issuance": "Analyze new card issuance by campaign, distinguishing member-initiated (organic) from company-driven (campaign, mass migration) acquisitions. Join with org hierarchy for divisional views.",
    "finance_customer_risk": "Analyze customer risk indicators including revolve index (proportion of revolving accounts) and risk rankings. Join with demographics for risk segmentation by generation and card type.",
}

# Minimum cosine similarity for a base-view match to count toward the bonus.
# Prevents low-quality vector matches from getting boosted by structural signal.
SIMILARITY_FLOOR = 0.65

# PostgreSQL connection values from .env
POSTGRES_HOST = _get_required_env("POSTGRES_HOST")
POSTGRES_PORT = int(_get_required_env("POSTGRES_PORT"))
POSTGRES_DBNAME = _get_required_env("POSTGRES_DBNAME")
POSTGRES_USER = _get_required_env("POSTGRES_USER")
POSTGRES_PASSWORD = _get_required_env("POSTGRES_PASSWORD")

# ─── BGE Embedding Configuration ─────────────────────────────────────
# BGE-large-en-v1.5 was trained with asymmetric instructions.
# Queries MUST use this prefix; documents do NOT.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# ─── SQL: Schema Setup ───────────────────────────────────────────────

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

# ─── SQL: Data Operations ────────────────────────────────────────────

SQL_UPSERT_FIELD_EMBEDDING_RECORD = """
INSERT INTO field_embeddings (
    id, field_key, embedding, content, field_name, field_type, measure_type,
    view_name, explore_name, model_name, label, group_label, tags, hidden, created_at
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

# ─── SQL: Vector Search ──────────────────────────────────────────────

SQL_SEARCH_SIMILAR_FIELDS = """
SELECT
    field_key,
    field_name,
    label,
    explore_name,
    view_name,
    field_type,
    measure_type,
    1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
FROM field_embeddings
WHERE hidden = FALSE
ORDER BY embedding <=> CAST(:embedding AS vector)
LIMIT :limit;
"""

# Field-type filtered search — search only measures or only dimensions
SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE = """
SELECT
    field_key,
    field_name,
    label,
    explore_name,
    view_name,
    field_type,
    measure_type,
    1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
FROM field_embeddings
WHERE hidden = FALSE
  AND field_type = :field_type
ORDER BY embedding <=> CAST(:embedding AS vector)
LIMIT :limit;
"""

# ─── SQL: Hybrid Table Queries (explore_field_index) ──────────────────

SQL_VALIDATE_FIELDS_IN_EXPLORE = """
SELECT explore_name, field_name, field_type, view_name, is_partition_key
FROM explore_field_index
WHERE explore_name = :explore_name
  AND field_name = ANY(:field_names)
  AND NOT is_hidden;
"""

SQL_GET_EXPLORES_FOR_FIELDS = """
SELECT explore_name,
       array_agg(field_name) AS matched_fields,
       COUNT(*) AS match_count
FROM explore_field_index
WHERE field_name = ANY(:field_names)
  AND NOT is_hidden
GROUP BY explore_name
ORDER BY match_count DESC;
"""

SQL_GET_PARTITION_FILTERS = """
SELECT explore_name, required_filters
FROM explore_partition_filters
WHERE explore_name = :explore_name;
"""

SQL_GET_ALL_EXPLORE_FIELDS = """
SELECT explore_name, field_name, field_type, view_name
FROM explore_field_index
WHERE explore_name = :explore_name
  AND NOT is_hidden;
"""

# GAP 1: Check which explores contain dimensions matching filter field_hints.
# Used to compute filter_penalty BEFORE explore selection (not after).
# field_patterns are ILIKE patterns like ['%generation%', '%card_type%'].
SQL_CHECK_FILTER_FIELDS_IN_EXPLORES = """
SELECT explore_name, field_name
FROM explore_field_index
WHERE field_type = 'dimension'
  AND NOT is_hidden
  AND field_name ILIKE ANY(:field_patterns);
"""

# ─── SQL: Verification ───────────────────────────────────────────────

SQL_COUNT_FIELD_EMBEDDINGS = "SELECT count(*) FROM field_embeddings;"

SQL_SAMPLE_FIELD_EMBEDDINGS = """
SELECT id, field_key, content, field_name, field_type, measure_type, view_name,
    explore_name, model_name, label, group_label, tags, hidden, created_at
FROM field_embeddings
LIMIT 5;
"""

SQL_RETRIEVE_TOP_K_BY_DISTANCE = """
SELECT id, field_key, content, field_name, field_type, measure_type, view_name,
    explore_name, model_name, label, group_label, tags, hidden, created_at
FROM field_embeddings
ORDER BY embedding <=> %s::vector
LIMIT %s;
"""

SQL_VERIFY_VECTOR_SEARCH = """
SELECT field_key, field_name, field_type, view_name,
    1 - (embedding <=> (SELECT embedding FROM field_embeddings WHERE field_key = :test_key)) AS similarity
FROM field_embeddings
WHERE field_key != :test_key
ORDER BY embedding <=> (SELECT embedding FROM field_embeddings WHERE field_key = :test_key)
LIMIT 5;
"""
