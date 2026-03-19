"""Hybrid retrieval system — the core of Radix.

Two channels find the right {model, explore, dimensions, measures, filters}:

  1. Vector Search (pgvector) — semantic similarity on field embeddings (BGE 1024-dim)
  2. Graph Validation (hybrid tables + AGE) — structural validation of LookML relationships

Scoring formula: score = coverage^3 x mean_sim x base_view_bonus x desc_sim_bonus

Entry point: pipeline.retrieve_with_graph_validation(query)
"""
