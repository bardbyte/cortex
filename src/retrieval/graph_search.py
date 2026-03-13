"""Graph search via PostgreSQL AGE — structural validation and relationship traversal.

The knowledge graph stores the full LookML model structure as nodes and edges.
It answers questions that vector search CANNOT:

  "Can these fields actually be queried together?"
  "What explore contains BOTH a spend measure AND a merchant dimension?"
  "What's the join path between these two views?"
  "What partition filters are required?"

The structural validation gate — checking that all candidate fields are reachable
from a single explore — is the single most important quality check in the system.
Without it, you return semantically similar fields from incompatible explores,
generating "correct" SQL that answers the wrong question.

Graph schema:
  NODES: Model, Explore, View, Dimension, Measure, BusinessTerm
  EDGES: CONTAINS, BASE_VIEW, JOINS, HAS_DIMENSION, HAS_MEASURE, MAPS_TO

Implementation strategy:
  1. Use hybrid relational tables for hot-path lookups (explore_field_index,
     explore_partition_filters).
  2. Use graph_search_index for explore_partition_filters.
  3. Fall back to pure graph queries only when hybrid tables are unavailable.

Prerequisites:
  - PostgreSQL AGE free graph and hybrid tables created by scripts/setup_optimized_age_schema.py
  - LookML loaded via scripts/load_lookml_to_age.py
  - Hybrid tables populated via scripts/build_hybrid_indexes.py
"""

from sqlalchemy import text
from src.connectors.postgres_age_client import get_engine, init_age_session


def find_explores_for_view(view_name: str, graph_name: str = "lookml_schema") -> list[dict]:
    """
    Find all explores connected to a view through BASE_VIEW or JOINS relationships.

    Args:
        view_name: Name of the view to search for.
        graph_name: Name of the AGE graph (default: 'lookml_schema')

    Returns:
        List of explore objects with their properties
    """
    engine = get_engine()

    # Escape identifiers/values for SQL safety in f-string query assembly
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
