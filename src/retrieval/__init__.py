"""Hybrid retrieval system — the heart of Cortex.

Two channels find the right {model, explore, dimensions, measures, filters}:

  1. Vector Search (pgvector) — semantic similarity on field embeddings (BGE 1024-dim)
  2. Graph Validation (hybrid tables + AGE) — structural validation of LookML relationships

These feed into a multiplicative scoring formula that enforces coverage dominance:
  score = coverage³ × mean_sim × base_view_bonus × desc_sim_bonus

Entry point: pipeline.retrieve_with_graph_validation(query)
"""
