"""Load parsed LookML into Neo4j knowledge graph.

This script parses LookML files using the `lkml` library and loads the
model/explore/view/dimension/measure structure into Neo4j as a graph.

Usage:
    python scripts/load_lookml_to_neo4j.py --lookml-dir=path/to/lookml/
    python scripts/load_lookml_to_neo4j.py --lookml-dir=path/to/lookml/ --neo4j-uri=bolt://localhost:7687

Graph schema to create:
  Nodes:
    (:Model {name})
    (:Explore {name, description, always_filter})
    (:View {name, sql_table_name})
    (:Dimension {name, type, description, label, group_label})
    (:Measure {name, type, description, label, sql})
    (:BusinessTerm {canonical, synonyms, definition})   ← loaded from taxonomy YAML

  Edges:
    (Model)-[:CONTAINS]->(Explore)
    (Explore)-[:BASE_VIEW]->(View)
    (Explore)-[:JOINS {type, relationship, sql_on}]->(View)
    (View)-[:HAS_DIMENSION]->(Dimension)
    (View)-[:HAS_MEASURE]->(Measure)
    (BusinessTerm)-[:MAPS_TO]->(Dimension|Measure)

Requirements:
  - Parse .lkml files with the `lkml` library
  - Handle: dimensions, measures, dimension_groups, derived tables
  - Extract always_filter, sql_on, relationship type from joins
  - Script must be idempotent (re-run safely — clear and reload)
  - Optionally load BusinessTerm nodes from taxonomy/ YAML files

Dependencies:
  - lkml (pip install lkml)
  - neo4j (pip install neo4j)
  - pyyaml (for taxonomy loading)

Run Neo4j locally: docker compose up neo4j
"""

if __name__ == "__main__":
    raise NotImplementedError(
        "Implement: parse LookML files, create Neo4j nodes/edges per schema above"
    )
