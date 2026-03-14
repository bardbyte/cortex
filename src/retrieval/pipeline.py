"""Unified retrieval pipeline combining vector search and graph validation.

This module orchestrates the end-to-end retrieval flow:
  1) Extract entities from user query using LLM (vector.py)
  2) Find candidate fields via vector similarity search (field-type filtered)
  3) Validate candidate explores against hybrid tables (explore_field_index)
  4) Score explores using multiplicative formula

Scoring formula:
  score = coverage^3 × mean_sim × base_view_bonus × desc_sim_bonus

  Where:
    coverage = matched_entities / total_entities (0 to 1)
    coverage^3 = cubic penalty (0.5 coverage → 0.125 score)
    mean_sim = mean cosine similarity of best match per entity
    base_view_bonus = 1.0 + weighted_base_view_ratio (up to 2.0x)
      - Measures count 2x, dimensions 1x in the ratio (P1)
      - Only counted if similarity >= SIMILARITY_FLOOR (P3)
    desc_sim_bonus = 1.0 + 0.2 × explore_description_similarity (P2 tiebreaker)

Usage:
    results = retrieve_with_graph_validation("Total spend by merchant")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from src.retrieval.vector import EntityExtractor
from src.retrieval.graph_search import get_explores_for_fields
from src.retrieval.filters import resolve_filters, FilterResolutionResult
from config.constants import (
    EXPLORE_BASE_VIEWS,
    EXPLORE_DESCRIPTIONS,
    SIMILARITY_FLOOR,
)

logger = logging.getLogger(__name__)

# Module-level cache for explore description embeddings (computed once)
_explore_desc_embeddings: dict[str, list[float]] | None = None


@dataclass
class ScoredExplore:
    """Represents an explore scored by how well it supports extracted entities."""
    name: str
    supported_entities: list[str]
    score: float
    raw_score: float
    coverage: float
    base_view_name: str = ""


@dataclass
class PipelineResult:
    """Final output from the retrieval pipeline."""
    query: str
    explores: list[ScoredExplore]
    entities: list[dict[str, Any]] | None = None
    raw_results: dict[str, Any] | None = None
    filters: FilterResolutionResult | None = None


def _get_explore_desc_similarities(
    query: str,
    extractor: EntityExtractor,
) -> dict[str, float]:
    """Compute cosine similarity between query and each explore's description.

    P2: Tiebreaker for when base_view_bonus can't discriminate (e.g., all entities
    from joined views like cmdl_card_main). Explore descriptions are embedded once
    and cached at module level.

    Returns dict of {explore_name: cosine_similarity}.
    """
    global _explore_desc_embeddings

    if _explore_desc_embeddings is None:
        logger.info("Computing explore description embeddings (one-time cache)...")
        _explore_desc_embeddings = {}
        for name, desc in EXPLORE_DESCRIPTIONS.items():
            # Descriptions are documents — no BGE prefix
            _explore_desc_embeddings[name] = extractor.embedding_client.embed_query(desc)
        logger.info("Cached %d explore description embeddings", len(_explore_desc_embeddings))

    # Query gets BGE prefix via embed_text
    query_embedding = extractor.embed_text(query, is_query=True)

    # Both vectors are L2-normalized (BGE with normalize_embeddings=True)
    # so cosine similarity = dot product
    similarities = {}
    for name, desc_emb in _explore_desc_embeddings.items():
        similarities[name] = sum(a * b for a, b in zip(query_embedding, desc_emb))

    return similarities


def retrieve_with_graph_validation(
    query: str,
    top_k: int = 5,
    llm_model_idx: str = "",
    embedding_model_idx: str = "",
) -> PipelineResult:
    """Execute full retrieval pipeline: entity extraction + vector search + explore scoring.

    Args:
        query: User natural language query
        top_k: Number of candidate fields to retrieve per entity
        llm_model_idx: LLM model index for entity extraction (default from constants)
        embedding_model_idx: Embedding model index (default from constants)

    Returns:
        PipelineResult with scored explores and retrieval metadata
    """
    logger.info("Starting retrieval pipeline for query: %s", query)

    # Step 1: Initialize extractor and process query
    logger.info("[1/5] Extracting entities from query...")
    kwargs = {}
    if llm_model_idx:
        kwargs["llm_model_idx"] = llm_model_idx
    if embedding_model_idx:
        kwargs["embedding_model_idx"] = embedding_model_idx
    extractor = EntityExtractor(**kwargs)
    raw_results = extractor.process_query(query, top_k)

    # Step 2: Compute explore description similarities (P2 tiebreaker)
    logger.info("[2/5] Computing explore description similarities...")
    explore_desc_sims = _get_explore_desc_similarities(query, extractor)

    # Step 3: Score explores using hybrid table validation
    logger.info("[3/5] Scoring explores via explore_field_index...")
    extracted_entities = raw_results.get("entities", [])
    explores = _score_explores(extracted_entities, explore_desc_sims=explore_desc_sims)

    # Step 4: Resolve filters for the top explore
    filter_result = None
    if explores:
        top_explore_name = explores[0].name
        logger.info("[4/5] Resolving filters for top explore: %s", top_explore_name)
        filter_result = resolve_filters(extracted_entities, top_explore_name)
        if filter_result.resolved_filters:
            logger.info(
                "Resolved %d user filters, %d mandatory filters",
                len(filter_result.resolved_filters),
                len(filter_result.mandatory_filters),
            )
        if filter_result.unresolved:
            logger.warning(
                "%d filters could not be resolved: %s",
                len(filter_result.unresolved),
                filter_result.unresolved,
            )
    else:
        logger.info("[4/5] No explores scored — skipping filter resolution")

    # Step 5: Format and return
    logger.info("[5/5] Pipeline complete!")
    pipeline_result = PipelineResult(
        query=query,
        entities=extracted_entities,
        explores=explores,
        raw_results=raw_results,
        filters=filter_result,
    )
    logger.info(
        "Result: %d entities, %d scored explores",
        len(extracted_entities),
        len(explores),
    )

    return pipeline_result


def get_top_explore(pipeline_result: PipelineResult) -> dict[str, Any] | None:
    """Return the top explore from a PipelineResult."""
    if not pipeline_result.explores:
        return None

    top = pipeline_result.explores[0]
    result: dict[str, Any] = {
        "top_explore_name": top.name,
        "retrieval_metadata": {
            "entity_vector_search": {
                "explore_name": top.name,
                "supported_entities": top.supported_entities,
                "score": top.score,
                "raw_score": top.raw_score,
                "coverage": top.coverage,
            },
        },
    }

    if pipeline_result.filters:
        result["filters"] = pipeline_result.filters.to_looker_filters()
        if pipeline_result.filters.unresolved:
            result["unresolved_filters"] = pipeline_result.filters.unresolved

    return result


def retrieve_top_explore(
    query: str,
    top_k: int = 5,
    llm_model_idx: str = "",
) -> dict[str, Any] | None:
    """Run full retrieval pipeline and return the top explore with metadata."""
    result = retrieve_with_graph_validation(query, top_k, llm_model_idx)
    return get_top_explore(result)


def _score_explores(
    entities: list[dict[str, Any]],
    explore_desc_sims: dict[str, float] | None = None,
) -> list[ScoredExplore]:
    """Score explores using multiplicative formula with three hardening signals.

    For each entity with candidates, collect (explore, field, view, similarity).
    Group by explore. Compute:
      coverage = matched_entity_count / total_entity_count
      mean_sim = mean of best similarity per matched entity
      base_view_bonus = 1.0 + weighted_base_view_ratio (up to 2.0x)
      desc_sim_bonus = 1.0 + 0.2 * explore_description_similarity
      score = coverage^3 * mean_sim * base_view_bonus * desc_sim_bonus

    Three hardening signals:
      P1: Measures count 2x, dimensions 1x in base_view_ratio.
          The measure determines the analytical grain — it should dominate routing.
      P2: Explore description similarity as tiebreaker (0.2 coefficient).
          Handles failure mode where no entity comes from any base view
          (e.g., all entities from cmdl_card_main, a universal join view).
      P3: Base-view match only counts if similarity >= SIMILARITY_FLOOR (0.65).
          Prevents low-quality vector matches from being boosted by structural signal.

    Args:
        entities: Raw entities from EntityExtractor.process_query()
        explore_desc_sims: Pre-computed query↔explore description similarities

    Returns:
        Explore scores sorted descending by final score
    """
    # ── Phase 1: Collect candidates per (explore, entity) ────────────
    per_explore_entities: dict[str, dict[str, float]] = {}
    per_explore_entity_views: dict[str, dict[str, str]] = {}
    entity_ids: list[str] = []
    entity_types: dict[str, str] = {}  # P1: track type for weighting

    for entity in entities:
        entity_type = entity.get("type", "unknown")
        entity_id = entity.get("id", "unknown")

        if entity_type not in ("measure", "dimension"):
            continue

        entity_ids.append(entity_id)
        entity_types[entity_id] = entity_type
        candidates = entity.get("candidates", [])

        for candidate in candidates:
            view_name = candidate.get("view_name", "")
            field_name = candidate.get("field_name", "")
            similarity = candidate.get("similarity", 0.0)
            explore_names_str = candidate.get("explore", "")

            if not view_name or not field_name:
                continue

            explore_names = [e.strip() for e in explore_names_str.split(",") if e.strip()]

            for explore_name in explore_names:
                entity_scores = per_explore_entities.setdefault(explore_name, {})
                current_best = entity_scores.get(entity_id, 0.0)

                if similarity >= current_best:
                    entity_scores[entity_id] = similarity
                    per_explore_entity_views.setdefault(explore_name, {})[entity_id] = view_name

    total_entities = len(entity_ids)
    if total_entities == 0:
        return []

    # ── Phase 2: Hybrid table enrichment ─────────────────────────────
    all_field_names = set()
    for entity in entities:
        for candidate in entity.get("candidates", []):
            fname = candidate.get("field_name", "")
            if fname:
                all_field_names.add(fname)

    if all_field_names:
        try:
            hybrid_results = get_explores_for_fields(list(all_field_names))
            for row in hybrid_results:
                explore_name = row["explore_name"]
                if explore_name not in per_explore_entities:
                    per_explore_entities[explore_name] = {}
        except Exception as e:
            logger.debug("Hybrid table lookup failed (may not be populated yet): %s", e)

    # ── Phase 3: Score each explore ──────────────────────────────────
    MEASURE_WEIGHT = 2.0
    DIMENSION_WEIGHT = 1.0

    scored: list[ScoredExplore] = []
    for explore_name, entity_contrib in per_explore_entities.items():
        supported_entity_ids = list(entity_contrib.keys())
        supported_count = len(supported_entity_ids)

        coverage = supported_count / total_entities

        similarities = list(entity_contrib.values())
        mean_similarity = sum(similarities) / len(similarities) if similarities else 0.0

        # ── P1 + P3: Weighted base_view_ratio with similarity gating ──
        base_view = EXPLORE_BASE_VIEWS.get(explore_name)
        base_view_bonus = 1.0
        if base_view and supported_count > 0:
            entity_views = per_explore_entity_views.get(explore_name, {})
            weighted_base_matches = 0.0
            weighted_total = 0.0

            for eid in supported_entity_ids:
                weight = MEASURE_WEIGHT if entity_types.get(eid) == "measure" else DIMENSION_WEIGHT
                weighted_total += weight

                # P3: Only count as base-view match if similarity passes floor
                eid_sim = entity_contrib.get(eid, 0.0)
                if entity_views.get(eid) == base_view and eid_sim >= SIMILARITY_FLOOR:
                    weighted_base_matches += weight

            base_view_ratio = weighted_base_matches / weighted_total if weighted_total > 0 else 0.0
            base_view_bonus = 1.0 + base_view_ratio

        # ── P2: Explore description similarity tiebreaker ──
        desc_sim_bonus = 1.0
        if explore_desc_sims:
            desc_sim = explore_desc_sims.get(explore_name, 0.0)
            desc_sim_bonus = 1.0 + 0.2 * max(desc_sim, 0.0)

        # ── Final multiplicative score ──
        raw_score = mean_similarity
        final_score = (coverage ** 3) * mean_similarity * base_view_bonus * desc_sim_bonus

        scored.append(
            ScoredExplore(
                name=explore_name,
                supported_entities=supported_entity_ids,
                score=round(final_score, 4),
                raw_score=round(raw_score, 4),
                coverage=round(coverage, 4),
                base_view_name=base_view or "",
            )
        )

    scored.sort(key=lambda e: e.score, reverse=True)
    return scored


def _demo_run() -> None:
    """Demo: Run full pipeline on multiple queries and fetch top explore for each."""
    from src.retrieval.filters import format_resolution_report

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("\n" + "=" * 80)
    print("Pipeline Demo — Top Explore + Filter Resolution")
    print("=" * 80)

    queries = [
        "What is the total billed business for the OPEN segment?",
        "How many attrited customers do we have by generation?",
        "What is our attrition rate for Q4 2025?",
        "What is the highest billed business by merchant category?",
        "Show me the top 5 travel verticals by gross sales and booking count",
        "How many Millennial customers have Apple Pay enrolled and are active?",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        result = retrieve_with_graph_validation(query, top_k=5)
        output = get_top_explore(result)
        print(json.dumps(output, indent=2, default=str))
        if result.filters:
            print(format_resolution_report(result.filters))


if __name__ == "__main__":
    _demo_run()
