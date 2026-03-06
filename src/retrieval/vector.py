"""Vector search via pgvector (PostgreSQL extension).

Finds LookML fields whose descriptions are semantically similar to the user's query.

How it works:
  INDEXING (offline, triggered on LookML deploy):
    - One document per field (NOT per-view, NOT per-explore)
    - Each doc = field name + description + explore/view context + taxonomy synonyms
    - Structured columns for filtering: field_type, view, explore, model
    - Embedding model: text-embedding-005 (768-dim, fine-tunable for Amex terminology)
    - Index type: HNSW (m=16, ef_construction=64) for approximate nearest neighbor

  QUERYING (runtime, <100ms):
    - Embed extracted entities (e.g. "total spend", "merchant category")
    - pgvector cosine distance search for top-K similar fields
    - Return FieldCandidate list ranked by cosine similarity

Why pgvector over Vertex AI Search (see ADR-004):
    - Approved within Amex — no cloud API exception needed
    - Runs locally — no network egress, no cloud dependency
    - Same PostgreSQL instance as AGE graph — operational simplicity
    - SQL-based queries — team already knows SQL
    - Can combine vector + graph queries in a single SQL statement

Schema (PostgreSQL):
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE field_embeddings (
        id              SERIAL PRIMARY KEY,
        field_key       TEXT UNIQUE NOT NULL,   -- "finance.finance_cardmember_360.custins.billed_business"
        embedding       vector(768) NOT NULL,   -- text-embedding-005 output
        content         TEXT NOT NULL,           -- the text that was embedded
        field_name      TEXT NOT NULL,
        field_type      TEXT NOT NULL,           -- "dimension" | "measure"
        measure_type    TEXT,                    -- "sum" | "average" | "count_distinct" | null
        view_name       TEXT NOT NULL,
        explore_name    TEXT NOT NULL,
        model_name      TEXT NOT NULL,
        label           TEXT,
        group_label     TEXT,
        tags            TEXT[],
        hidden          BOOLEAN DEFAULT FALSE,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX ON field_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);

Why per-field chunking?
  Per-view returns 50 irrelevant fields alongside the 2 you need.
  Per-field lets retrieval pinpoint exact matches. Precision > recall here.

What to implement:
  1. build_field_embeddings() — parse LookML, enrich with taxonomy, create rows
  2. index_to_pgvector() — INSERT into field_embeddings table
  3. search() — query pgvector, return ranked FieldCandidates

Dependencies:
  - psycopg[binary] (PostgreSQL driver with pgvector support)
  - pgvector (Python helper for vector type)
  - lkml (LookML parser)
  - Taxonomy YAML files for synonym enrichment (src/taxonomy/)
  - An embedding endpoint (SafeChain → text-embedding-005)
"""

from src.retrieval.models import FieldCandidate

# ─── QUERY TEMPLATES ───────────────────────────────────────

# Core similarity search — returns top-K fields by cosine distance
VECTOR_SEARCH_SQL = """
SELECT field_key, field_name, field_type, view_name, explore_name,
       model_name, label, group_label, tags, content,
       1 - (embedding <=> %(query_embedding)s::vector) AS similarity
FROM field_embeddings
WHERE hidden = FALSE
  AND model_name = %(model_name)s
ORDER BY embedding <=> %(query_embedding)s::vector
LIMIT %(top_k)s;
"""

# Unscoped search (when model is not yet identified)
VECTOR_SEARCH_UNSCOPED_SQL = """
SELECT field_key, field_name, field_type, view_name, explore_name,
       model_name, label, group_label, tags, content,
       1 - (embedding <=> %(query_embedding)s::vector) AS similarity
FROM field_embeddings
WHERE hidden = FALSE
ORDER BY embedding <=> %(query_embedding)s::vector
LIMIT %(top_k)s;
"""


# ─── INTERFACE ─────────────────────────────────────────────


def build_field_embeddings(
    lookml_models: list, taxonomy: dict | None = None
) -> list[dict]:
    """Build pgvector rows from parsed LookML.

    Args:
        lookml_models: Parsed LookML model objects (from lkml library).
        taxonomy: Optional {field_name: TaxonomyEntry} for synonym enrichment.

    Returns:
        List of dicts ready for INSERT into field_embeddings table.
        Each dict:
          {
            "field_key": "model.explore.view.field",
            "content": "field_name is a [type] in [view], accessible through [explore]...",
            "field_name": "billed_business",
            "field_type": "dimension",
            "view_name": "custins_customer_insights_cardmember",
            "explore_name": "finance_cardmember_360",
            "model_name": "finance",
            ...
          }

    Note: Embedding generation (content → vector) is done separately via
    SafeChain's embedding endpoint before INSERT.
    """
    raise NotImplementedError


def search(
    pg_conn,
    query_embedding: list[float],
    *,
    top_k: int = 20,
    model_name: str | None = None,
) -> list[FieldCandidate]:
    """Search pgvector for semantically similar LookML fields.

    Args:
        pg_conn: Active psycopg connection to PostgreSQL with pgvector.
        query_embedding: 768-dim embedding of the search query.
        top_k: Number of results to return.
        model_name: Optional model name to scope results (recommended).

    Returns:
        FieldCandidate list ranked by cosine similarity.
    """
    raise NotImplementedError
