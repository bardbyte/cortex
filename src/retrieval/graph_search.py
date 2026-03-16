"""Graph search via PostgreSQL AGE + hybrid relational tables.

Two strategies, chosen by availability:

  HOT PATH (hybrid tables — used for all production validation):
    explore_field_index   → "Which explores contain field X?" (~40μs)
    explore_partition_filters → "What filters are required for explore Y?" (~20μs)
    These are B-tree indexed relational tables. 10-50x faster than graph.

  COLD PATH (AGE Cypher — used for complex multi-hop analysis):
    find_explores_for_view → "What explores use view V?" via graph traversal (~1-5ms)
    Used for offline analysis, not in the hot retrieval path.

Graph schema:
  NODES: Model, Explore, View, Dimension, Measure, BusinessTerm
  EDGES: CONTAINS, BASE_VIEW, JOINS, HAS_DIMENSION, HAS_MEASURE, MAPS_TO
"""

import logging
from sqlalchemy import text
from src.connectors.postgres_age_client import get_engine, init_age_session
from config.constants import (
    SQL_VALIDATE_FIELDS_IN_EXPLORE,
    SQL_GET_EXPLORES_FOR_FIELDS,
    SQL_GET_PARTITION_FILTERS,
    SQL_GET_ALL_EXPLORE_FIELDS,
    SQL_CHECK_FILTER_FIELDS_IN_EXPLORES,
)

logger = logging.getLogger(__name__)


# ─── HOT PATH: Hybrid Table Queries ──────────────────────────────────


def validate_fields_in_explore(
    explore_name: str,
    field_names: list[str],
) -> list[dict]:
    """Check which of the given fields exist in the specified explore.

    Uses the explore_field_index relational table (~40μs per query).

    Args:
        explore_name: Name of the explore to validate against.
        field_names: List of field names to check.

    Returns:
        List of dicts with keys: explore_name, field_name, field_type, view_name, is_partition_key
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(SQL_VALIDATE_FIELDS_IN_EXPLORE).bindparams(
                explore_name=explore_name,
                field_names=field_names,
            )
        )
        return [
            {
                "explore_name": row[0],
                "field_name": row[1],
                "field_type": row[2],
                "view_name": row[3],
                "is_partition_key": row[4],
            }
            for row in result.fetchall()
        ]


def get_explores_for_fields(field_names: list[str]) -> list[dict]:
    """Find all explores that contain ANY of the given fields, ranked by match count.

    This is the core explore selection query. For a set of extracted entities
    (measure names + dimension names), find which explores can serve them all.

    Args:
        field_names: List of field names to search for.

    Returns:
        List of dicts with keys: explore_name, matched_fields, match_count
        Sorted by match_count DESC (best coverage first).
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(SQL_GET_EXPLORES_FOR_FIELDS).bindparams(
                field_names=field_names,
            )
        )
        return [
            {
                "explore_name": row[0],
                "matched_fields": list(row[1]) if row[1] else [],
                "match_count": row[2],
            }
            for row in result.fetchall()
        ]


def get_partition_filters(explore_name: str) -> list[dict]:
    """Get required partition filters for an explore.

    Every explore has mandatory partition filters (always_filter in LookML).
    These MUST be included in every query to avoid full table scans.

    Args:
        explore_name: Name of the explore.

    Returns:
        List of dicts with keys: explore_name, required_filters
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(SQL_GET_PARTITION_FILTERS).bindparams(
                explore_name=explore_name,
            )
        )
        return [
            {
                "explore_name": row[0],
                "required_filters": row[1],
            }
            for row in result.fetchall()
        ]


def get_all_explore_fields(explore_name: str) -> list[dict]:
    """Get all visible fields for an explore.

    Args:
        explore_name: Name of the explore.

    Returns:
        List of dicts with keys: explore_name, field_name, field_type, view_name
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(SQL_GET_ALL_EXPLORE_FIELDS).bindparams(
                explore_name=explore_name,
            )
        )
        return [
            {
                "explore_name": row[0],
                "field_name": row[1],
                "field_type": row[2],
                "view_name": row[3],
            }
            for row in result.fetchall()
        ]


def check_filter_fields_in_explores(field_hints: list[str]) -> dict[str, set[str]]:
    """Check which explores contain dimensions matching filter field_hints.

    GAP 1: Used to compute filter_penalty during explore scoring.
    If a user asks for "generation = Millennial", we need to verify that the
    candidate explore actually HAS a "generation" dimension before scoring it.

    Args:
        field_hints: Conceptual field names from filter extraction (e.g., ["generation", "card_type"])

    Returns:
        {explore_name: {matched_hint_1, matched_hint_2, ...}}
        Empty dict if no matches or if the hybrid table isn't populated.
    """
    if not field_hints:
        return {}

    engine = get_engine()
    field_patterns = [f"%{hint}%" for hint in field_hints]

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(SQL_CHECK_FILTER_FIELDS_IN_EXPLORES).bindparams(
                    field_patterns=field_patterns,
                )
            )

            explore_hints: dict[str, set[str]] = {}
            for row in result.fetchall():
                explore_name = row[0]
                field_name = row[1]
                # Match back to which hint this field satisfies
                for hint in field_hints:
                    if hint.lower() in field_name.lower():
                        explore_hints.setdefault(explore_name, set()).add(hint)

            return explore_hints
    except Exception as e:
        logger.debug("Filter field check failed (table may not exist): %s", e)
        return {}


# ─── COLD PATH: AGE Graph Queries ────────────────────────────────────


def find_explores_for_view(view_name: str, graph_name: str = "lookml_schema") -> list[dict]:
    """Find all explores connected to a view through BASE_VIEW or JOINS relationships.

    Uses AGE Cypher graph traversal (~1-5ms). Use for offline analysis,
    not in the hot retrieval path.

    Args:
        view_name: Name of the view to search for.
        graph_name: Name of the AGE graph (default: 'lookml_schema')

    Returns:
        List of explore objects with their properties
    """
    engine = get_engine()

    escaped_view = view_name.replace("'", "''")
    escaped_graph = graph_name.replace("'", "''")

    with engine.connect() as conn:
        init_age_session(conn)

        sql = f"""
        SELECT * FROM ag_catalog.cypher('{escaped_graph}'::name, $$
            MATCH (e:Explore)-[:BASE_VIEW]->(v:View {{name: '{escaped_view}'}})
            RETURN DISTINCT e
            UNION
            MATCH (e:Explore)-[:JOINS]->(v:View {{name: '{escaped_view}'}})
            RETURN DISTINCT e
        $$::cstring) AS (explore agtype);
        """

        result = conn.execute(text(sql))
        return [row[0] for row in result.fetchall()]
