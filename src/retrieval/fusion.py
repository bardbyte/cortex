"""Reciprocal Rank Fusion + Structural Validation Gate.

Merges three retrieval channels (vector, graph, fewshot) into one answer.

Why RRF (not weighted sum or learned fusion)?
  - Vector scores (cosine similarity) and graph results (binary valid/invalid)
    are on fundamentally different scales. RRF is rank-based — it doesn't
    care about score magnitudes, only ordering.
  - No training data needed (learned fusion requires labeled examples).
  - Battle-tested in production search (Elasticsearch, OpenSearch both use it).

RRF formula:
  For each field across all ranked lists:
    score(field) = sum over sources: weight[source] * (1 / (k + rank))
  Where k=60 (standard smoothing constant).

Weights (configurable in config/retrieval.yaml):
  graph: 1.5   — structural truth is the most reliable signal
  fewshot: 1.2 — proven patterns from real usage
  vector: 1.0  — semantic similarity (good but noisy)

After fusion, the STRUCTURAL VALIDATION GATE runs:
  "Are ALL top-ranked fields reachable from a SINGLE explore?"
  - YES with high confidence → proceed to SQL generation
  - MULTIPLE explores score similarly → disambiguate (ask user)
  - LOW coverage → clarify (ask user to narrow scope)
  - NO explore matches → error

Storage: pgvector + Apache AGE on PostgreSQL (see ADR-004).
The structural validation gate uses AGE Cypher queries against the
lookml_schema graph, executed via the same pg_conn as vector search.

What to implement:
  1. reciprocal_rank_fusion() — merge ranked lists with weights
  2. fuse_and_validate() — RRF + group by explore + AGE validation + decision
  3. Decision logic returning a RetrievalResult

Dependencies:
  - src/retrieval/graph_search.py (for structural validation via AGE)
  - config/retrieval.yaml (for weights and thresholds)
"""

from src.retrieval.models import FieldCandidate, RetrievalResult


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[FieldCandidate]],
    weights: dict[str, float] | None = None,
    k: int = 60,
) -> list[tuple[str, float, FieldCandidate]]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion.

    Args:
        ranked_lists: {source_name: [candidates sorted by relevance]}.
        weights: Per-source multipliers. Defaults: graph=1.5, fewshot=1.2, vector=1.0.
        k: Smoothing constant (standard: 60).

    Returns:
        List of (field_id, fused_score, FieldCandidate) sorted by score descending.
    """
    raise NotImplementedError


def fuse_and_validate(
    vector_results: list[FieldCandidate],
    graph_results: list[FieldCandidate],
    fewshot_results: list[FieldCandidate],
    pg_conn,
) -> RetrievalResult:
    """Complete retrieval fusion pipeline.

    Steps:
      1. RRF merge three ranked lists
      2. Take top-N fused candidates
      3. Structural validation: AGE Cypher checks which explores contain ALL candidates
      4. Score each explore by coverage + aggregate RRF score
      5. Decision: proceed / disambiguate / clarify / no_match

    Args:
        vector_results: From pgvector similarity search.
        graph_results: From AGE graph traversal.
        fewshot_results: From FAISS golden queries.
        pg_conn: Active psycopg connection (pgvector + AGE on same PG instance).

    Returns:
        RetrievalResult with action and selected fields.
    """
    raise NotImplementedError
