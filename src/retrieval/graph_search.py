"""Graph search via Apache AGE (PostgreSQL extension) — structural validation.

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

Why Apache AGE over Neo4j (see ADR-004):
  - PostgreSQL extension — approved within Amex, no separate DB to manage
  - Supports Cypher query language (same as Neo4j, minor syntax differences)
  - Same PostgreSQL instance as pgvector — one DB for vector + graph
  - Runs locally — no cloud dependency
  - Can combine graph traversal with vector search in a single SQL statement

Graph schema (loaded into AGE graph 'lookml_schema'):
  NODES: Model, Explore, View, Dimension, Measure, BusinessTerm
  EDGES: CONTAINS, BASE_VIEW, JOINS, HAS_DIMENSION, HAS_MEASURE,
         ALWAYS_FILTER_ON, MAPS_TO

Setup:
  CREATE EXTENSION IF NOT EXISTS age;
  LOAD 'age';
  SET search_path = ag_catalog, "$user", public;
  SELECT create_graph('lookml_schema');

What to implement:
  1. Load LookML into AGE graph (scripts/load_lookml_to_age.py)
  2. Load BusinessTerm nodes from taxonomy YAML
  3. Implement the 5 critical Cypher queries below as methods
  4. Expose a search() method returning FieldCandidates

Dependencies:
  - psycopg[binary] (PostgreSQL driver)
  - age (Apache AGE Python wrapper, or raw SQL via psycopg)
  - lkml (LookML parser)
  - Taxonomy YAML for BusinessTerm nodes
"""

from src.retrieval.models import FieldCandidate

# ─── THE 5 CRITICAL CYPHER QUERIES (AGE-compatible) ───────
#
# AGE uses: SELECT * FROM cypher('graph_name', $$ ... $$) AS (col agtype);
# These queries are wrapped in the AGE SQL syntax below.

# QUERY 1: STRUCTURAL VALIDATION GATE
# Given candidate field names from vector/fewshot search,
# find which explores contain ALL of them.
# This is the most important query in the system.
STRUCTURAL_VALIDATION = """
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore)-[:BASE_VIEW|JOINS*0..3]->(v:View)
        -[:HAS_DIMENSION|HAS_MEASURE]->(f)
  WHERE f.name IN %s
  WITH e, collect(DISTINCT f.name) AS matched
  WHERE size(matched) = %s
  RETURN e.name AS explore,
         matched AS confirmed_fields,
         size(matched) AS coverage
  ORDER BY coverage DESC
$$) AS (explore agtype, confirmed_fields agtype, coverage agtype);
"""

# QUERY 2: EXPLORE SCHEMA
# Given an explore, return all available dimensions and measures.
EXPLORE_SCHEMA = """
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore {name: %s})-[:BASE_VIEW|JOINS*0..3]->(v:View)
  OPTIONAL MATCH (v)-[:HAS_DIMENSION]->(d)
  OPTIONAL MATCH (v)-[:HAS_MEASURE]->(m)
  RETURN v.name AS view,
         collect(DISTINCT {name: d.name, type: d.type,
                 description: d.description}) AS dimensions,
         collect(DISTINCT {name: m.name, type: m.type,
                 description: m.description}) AS measures
$$) AS (view agtype, dimensions agtype, measures agtype);
"""

# QUERY 3: BUSINESS TERM RESOLUTION
# Resolve a user's business term (or synonym) to LookML fields.
BUSINESS_TERM_RESOLUTION = """
SELECT * FROM cypher('lookml_schema', $$
  MATCH (bt:BusinessTerm)-[:MAPS_TO]->(f)
  WHERE bt.canonical =~ ('(?i).*' + %s + '.*')
     OR ANY(syn IN bt.synonyms WHERE syn =~ ('(?i).*' + %s + '.*'))
  OPTIONAL MATCH (e:Explore)-[:BASE_VIEW|JOINS*0..3]->(v:View)
                 -[:HAS_DIMENSION|HAS_MEASURE]->(f)
  RETURN bt.canonical AS business_term,
         f.name AS field_name,
         f.description AS field_description,
         collect(DISTINCT e.name) AS available_in_explores
$$) AS (business_term agtype, field_name agtype,
        field_description agtype, available_in_explores agtype);
"""

# QUERY 4: JOIN PATH
# Find the join chain between two views within an explore.
JOIN_PATH = """
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore {name: %s})
  MATCH (e)-[j:JOINS]->(v:View {name: %s})
  RETURN j.type AS join_type, j.relationship AS relationship, j.sql_on AS sql_on
$$) AS (join_type agtype, relationship agtype, sql_on agtype);
"""

# QUERY 5: PARTITION FILTERS
# What filters are REQUIRED for an explore (cost control).
PARTITION_FILTERS = """
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore {name: %s})-[:ALWAYS_FILTER_ON]->(d:Dimension)
  RETURN d.name AS filter_field, d.tags AS tags
$$) AS (filter_field agtype, tags agtype);
"""


# ─── INTERFACE ─────────────────────────────────────────────


def validate_fields_in_explore(
    pg_conn, candidate_fields: list[str]
) -> list[dict]:
    """The structural validation gate.

    Given candidate field names, find which explores contain ALL of them.

    Args:
        pg_conn: Active psycopg connection to PostgreSQL with AGE.
        candidate_fields: List of field names to validate.

    Returns:
        List of {explore, confirmed_fields, coverage} dicts,
        sorted by coverage descending.
    """
    raise NotImplementedError


def resolve_business_term(pg_conn, term: str) -> list[dict]:
    """Resolve a business term or synonym to LookML fields.

    Args:
        pg_conn: Active psycopg connection to PostgreSQL with AGE.
        term: Business term to resolve (e.g. "billed business", "active customers").

    Returns:
        List of {business_term, field_name, field_description, available_in_explores}.
    """
    raise NotImplementedError


def get_partition_filters(pg_conn, explore: str) -> list[dict]:
    """Get required partition filters for an explore.

    Args:
        pg_conn: Active psycopg connection to PostgreSQL with AGE.
        explore: Explore name.

    Returns:
        List of {filter_field, tags}.
    """
    raise NotImplementedError


def search(pg_conn, entities: dict, top_k: int = 20) -> list[FieldCandidate]:
    """Search the graph for fields matching extracted entities.

    Combines business term resolution with structural validation.

    Args:
        pg_conn: Active psycopg connection to PostgreSQL with AGE.
        entities: Extracted entities from Stage 2 (metrics, dimensions, etc.).
        top_k: Max results to return.

    Returns:
        FieldCandidate list with structural validity guaranteed.
    """
    raise NotImplementedError
