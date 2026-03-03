"""Graph search via Neo4j — structural validation and relationship traversal.

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

What to implement:
  1. Load LookML into Neo4j (scripts/load_lookml_to_neo4j.py)
  2. Load BusinessTerm nodes from taxonomy YAML
  3. Implement the 5 critical Cypher queries below as methods
  4. Expose a search() method returning FieldCandidates

Dependencies:
  - neo4j (Python driver)
  - lkml (LookML parser)
  - Taxonomy YAML for BusinessTerm nodes
"""

from src.retrieval.models import FieldCandidate

# ─── THE 5 CRITICAL CYPHER QUERIES ──────────────────────────────
#
# These are the exact queries you need. Copy them into your implementation.
# They have been validated against the Neo4j schema above.

# QUERY 1: STRUCTURAL VALIDATION GATE
# Given candidate field names from vector/fewshot search,
# find which explores contain ALL of them.
# This is the most important query in the system.
STRUCTURAL_VALIDATION = """
WITH $candidate_fields AS fields
UNWIND fields AS field_name
MATCH (e:Explore)-[:BASE_VIEW|JOINS*1..3]->(v:View)
      -[:HAS_DIMENSION|HAS_MEASURE]->(f)
WHERE f.name = field_name
WITH e, collect(DISTINCT f.name) AS matched, fields
WHERE size(matched) = size(fields)
RETURN e.name AS explore,
       matched AS confirmed_fields,
       size(matched) AS coverage
ORDER BY coverage DESC
"""

# QUERY 2: EXPLORE SCHEMA
# Given an explore, return all available dimensions and measures.
# Used to populate full context for the agent.
EXPLORE_SCHEMA = """
MATCH (e:Explore {name: $explore})-[:BASE_VIEW|JOINS*1..3]->(v:View)
OPTIONAL MATCH (v)-[:HAS_DIMENSION]->(d)
OPTIONAL MATCH (v)-[:HAS_MEASURE]->(m)
RETURN v.name AS view,
       collect(DISTINCT {name: d.name, type: d.type,
               description: d.description}) AS dimensions,
       collect(DISTINCT {name: m.name, type: m.type,
               description: m.description}) AS measures
"""

# QUERY 3: BUSINESS TERM RESOLUTION
# Resolve a user's business term (or synonym) to LookML fields.
# The graph connects user language → canonical term → physical field.
BUSINESS_TERM_RESOLUTION = """
MATCH (bt:BusinessTerm)-[:MAPS_TO]->(f)
WHERE bt.canonical =~ ('(?i).*' + $search_term + '.*')
   OR ANY(syn IN bt.synonyms WHERE syn =~ ('(?i).*' + $search_term + '.*'))
OPTIONAL MATCH (e:Explore)-[:BASE_VIEW|JOINS*1..3]->(v:View)
               -[:HAS_DIMENSION|HAS_MEASURE]->(f)
RETURN bt.canonical AS business_term,
       f.name AS field_name,
       f.description AS field_description,
       collect(DISTINCT e.name) AS available_in_explores
"""

# QUERY 4: JOIN PATH
# Find the join chain between two views within an explore.
# Needed when selected fields span multiple views.
JOIN_PATH = """
MATCH (e:Explore {name: $explore})
MATCH path = (e)-[:BASE_VIEW|JOINS*1..5]->(v1:View {name: $view1})
MATCH path2 = (e)-[:BASE_VIEW|JOINS*1..5]->(v2:View {name: $view2})
RETURN [rel IN relationships(path) | {type: type(rel),
        join_type: rel.type, relationship: rel.relationship,
        sql_on: rel.sql_on}] AS join_chain
"""

# QUERY 5: PARTITION FILTERS
# What filters are REQUIRED for an explore (cost control).
# Run before SQL generation — a query without partition filter on a
# 5PB warehouse can cost thousands.
PARTITION_FILTERS = """
MATCH (e:Explore {name: $explore})-[:ALWAYS_FILTER_ON]->(d:Dimension)
RETURN d.name AS filter_field,
       e.always_filter_default AS default_value
"""


# ─── INTERFACE ───────────────────────────────────────────────────


def validate_fields_in_explore(
    neo4j_driver, candidate_fields: list[str]
) -> list[dict]:
    """The structural validation gate.

    Given candidate field names, find which explores contain ALL of them.

    Args:
        neo4j_driver: Active Neo4j driver instance.
        candidate_fields: List of field names to validate.

    Returns:
        List of {explore, confirmed_fields, coverage} dicts,
        sorted by coverage descending.
    """
    raise NotImplementedError


def resolve_business_term(neo4j_driver, term: str) -> list[dict]:
    """Resolve a business term or synonym to LookML fields.

    Args:
        neo4j_driver: Active Neo4j driver instance.
        term: Business term to resolve (e.g. "CAC", "revenue").

    Returns:
        List of {business_term, field_name, field_description, available_in_explores}.
    """
    raise NotImplementedError


def get_partition_filters(neo4j_driver, explore: str) -> list[dict]:
    """Get required partition filters for an explore.

    Args:
        neo4j_driver: Active Neo4j driver instance.
        explore: Explore name.

    Returns:
        List of {filter_field, default_value}.
    """
    raise NotImplementedError


def search(neo4j_driver, entities: dict, top_k: int = 20) -> list[FieldCandidate]:
    """Search the graph for fields matching extracted entities.

    Combines business term resolution with structural validation.

    Args:
        neo4j_driver: Active Neo4j driver instance.
        entities: Extracted entities from Stage 2 (metrics, dimensions, etc.).
        top_k: Max results to return.

    Returns:
        FieldCandidate list with structural validity guaranteed.
    """
    raise NotImplementedError
