"""Hybrid retrieval system — the heart of Cortex.

Three parallel channels find the right {model, explore, dimensions, measures}:

  1. Vector Search (Vertex AI Search) — semantic similarity on field descriptions
  2. Graph Search (Neo4j) — structural validation of LookML relationships
  3. Few-Shot Match (FAISS) — pattern matching against proven golden queries

These feed into Reciprocal Rank Fusion (RRF) + a structural validation gate.

Why three channels?
  - Vector alone: returns semantically similar fields but ignores LookML structure
  - Graph alone: understands structure but can't do fuzzy matching
  - Few-shot alone: only works when a similar query has been seen before
  - Together: they cover each other's blind spots

This module is 75% of your error budget. Fix retrieval, fix Cortex.
"""
