"""Unified retrieval pipeline combining vector search and graph validation.

This module orchestrates the end-to-end retrieval flow:
  1) Extract entities from user query using LLM (vector.py)
  2) Confidence gate — reject if all similarities below floor
  3) Find candidate fields via vector similarity search (field-type filtered)
  4) Validate candidate explores against hybrid tables (explore_field_index)
  5) Score explores using multiplicative formula with 4 hardening signals
  6) Normalize score to [0, 1] confidence for downstream consumers

Scoring formula:
  score = coverage³ × mean_sim × base_view_bonus × desc_sim_bonus × filter_penalty

  Where:
    coverage = matched_entities / total_entities (0 to 1)
    coverage³ = cubic penalty (0.5 coverage → 0.125 score)
    mean_sim = mean cosine similarity of best match per entity
    base_view_bonus = 1.0 + weighted_base_view_ratio (up to 2.0x)
      - Measures count 2x, dimensions 1x in the ratio (P1)
      - Only counted if similarity >= SIMILARITY_FLOOR (P3)
    desc_sim_bonus = 1.0 + 0.2 × explore_description_similarity (P2 tiebreaker)
    filter_penalty = max(filter_coverage, 0.1) (P4 filter routing signal)
      - filter_coverage = matched_filter_hints / total_filter_hints
      - Floor of 0.1 prevents zeroing on LLM extraction errors

Confidence normalization:
  Relative normalization: confidence = score / max(top_raw_score, QUALITY_FLOOR_SCORE)
  QUALITY_FLOOR_SCORE = 0.3 prevents division by tiny denominators on junk queries.
  This is scale-invariant — doesn't depend on a hardcoded theoretical maximum.

Usage:
    results = retrieve_with_graph_validation("Total spend by merchant")
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any

from src.retrieval.vector import EntityExtractor
from src.retrieval.graph_search import get_explores_for_fields, check_filter_fields_in_explores
from src.retrieval.filters import resolve_filters, FilterResolutionResult
from config.constants import (
    EXPLORE_BASE_VIEWS,
    EXPLORE_DESCRIPTIONS,
    SIMILARITY_FLOOR,
)

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────
# Confidence gate: reject queries where ALL entity similarities are below this.
# Prevents garbage-in → garbage-out. Tuned for BGE-large-en-v1.5 on finance domain.
CONFIDENCE_FLOOR = 0.70

# Near-miss detection: if runner-up / top > this ratio, flag as ambiguous.
# Ratio-based (not absolute delta) to handle BGE's anisotropic similarity space.
NEAR_MISS_RATIO = 0.92

# GAP 7: Quality floor for relative normalization. Prevents division by tiny
# denominators on junk queries. Set to the score of a single low-quality match.
QUALITY_FLOOR_SCORE = 0.3

# GAP 1: Filter penalty floor. Prevents zeroing on LLM extraction errors.
# Linear penalty because filter presence is a binary structural signal.
FILTER_PENALTY_FLOOR = 0.1

# Module-level cache for explore description embeddings (computed once)
# GAP 6: Lock protects against concurrent initialization in threaded servers
_explore_desc_embeddings: dict[str, list[float]] | None = None
_explore_desc_lock = threading.Lock()


@dataclass
class ScoredExplore:
    """Represents an explore scored by how well it supports extracted entities."""
    name: str
    supported_entities: list[str]
    score: float
    raw_score: float
    coverage: float
    confidence: float = 0.0       # Normalized to [0, 1]
    base_view_name: str = ""
    is_near_miss: bool = False    # True if runner-up is within NEAR_MISS_RATIO


@dataclass
class PipelineResult:
    """Final output from the retrieval pipeline."""
    query: str
    explores: list[ScoredExplore]
    action: str = "proceed"       # "proceed" | "clarify" | "no_match"
    confidence: float = 0.0       # Normalized [0, 1] confidence of top explore
    clarify_reason: str = ""      # GAP 3: Why we're asking for clarification
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

    # GAP 6: Thread-safe lazy initialization
    with _explore_desc_lock:
        if _explore_desc_embeddings is None:
            logger.info("Computing explore description embeddings (one-time cache)...")
            _explore_desc_embeddings = {}
            for name, desc in EXPLORE_DESCRIPTIONS.items():
                # GAP 2: Descriptions are documents — use embed_text(is_query=False)
                # to skip BGE query prefix. embed_query() adds no prefix but
                # embed_text(is_query=False) makes the asymmetry explicit.
                _explore_desc_embeddings[name] = extractor.embed_text(desc, is_query=False)
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
    logger.info("[1/6] Extracting entities from query...")
    kwargs = {}
    if llm_model_idx:
        kwargs["llm_model_idx"] = llm_model_idx
    if embedding_model_idx:
        kwargs["embedding_model_idx"] = embedding_model_idx
    extractor = EntityExtractor(**kwargs)
    raw_results = extractor.process_query(query, top_k)
    extracted_entities = raw_results.get("entities", [])

    # Step 2: Confidence gate — reject if ALL entity similarities are below floor.
    # Prevents garbage queries from producing garbage results.
    measure_dim_entities = [
        e for e in extracted_entities if e.get("type") in ("measure", "dimension")
    ]
    if not measure_dim_entities:
        logger.warning("No measure/dimension entities extracted — clarify")
        return PipelineResult(query=query, explores=[], action="clarify", confidence=0.0,
                              clarify_reason="no_entities_extracted",
                              entities=extracted_entities, raw_results=raw_results)

    top_similarities = []
    for entity in measure_dim_entities:
        candidates = entity.get("candidates", [])
        if candidates:
            top_sim = max(c.get("similarity", 0.0) for c in candidates)
            top_similarities.append(top_sim)

    if top_similarities and all(s < CONFIDENCE_FLOOR for s in top_similarities):
        best_sim = max(top_similarities)
        logger.warning(
            "All entity similarities below floor %.2f (best: %.3f) — clarify",
            CONFIDENCE_FLOOR, best_sim,
        )
        return PipelineResult(query=query, explores=[], action="clarify",
                              confidence=best_sim,
                              clarify_reason=f"all_similarities_below_floor_{CONFIDENCE_FLOOR}",
                              entities=extracted_entities,
                              raw_results=raw_results)

    # Step 3: Compute explore description similarities (P2 tiebreaker)
    logger.info("[2/6] Computing explore description similarities...")
    explore_desc_sims = _get_explore_desc_similarities(query, extractor)

    # Step 4: Score explores using hybrid table validation
    logger.info("[3/6] Scoring explores via explore_field_index...")
    explores = _score_explores(extracted_entities, explore_desc_sims=explore_desc_sims)

    if not explores:
        logger.warning("No explores scored — no_match")
        return PipelineResult(query=query, explores=[], action="no_match",
                              confidence=0.0, entities=extracted_entities,
                              raw_results=raw_results)

    # Step 4b: Near-miss detection (ratio-based, not absolute delta)
    if len(explores) >= 2:
        top_score = explores[0].score
        runner_up_score = explores[1].score
        if top_score > 0 and runner_up_score / top_score > NEAR_MISS_RATIO:
            explores[0].is_near_miss = True
            explores[1].is_near_miss = True
            logger.info(
                "Near-miss: %s (%.4f) vs %s (%.4f), ratio=%.3f",
                explores[0].name, top_score,
                explores[1].name, runner_up_score,
                runner_up_score / top_score,
            )

    # Step 5: Resolve filters for the top explore
    filter_result = None
    top_explore_name = explores[0].name
    logger.info("[4/6] Resolving filters for top explore: %s", top_explore_name)
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

    # Step 6: Normalize scores using relative normalization (GAP 7)
    # confidence = score / max(top_score, QUALITY_FLOOR_SCORE)
    # This is scale-invariant — doesn't depend on a hardcoded theoretical maximum.
    # QUALITY_FLOOR_SCORE prevents division by tiny denominators on junk queries.
    logger.info("[5/6] Normalizing scores (relative)...")
    top_raw = explores[0].score
    normalization_base = max(top_raw, QUALITY_FLOOR_SCORE)
    for explore in explores:
        explore.confidence = round(min(explore.score / normalization_base, 1.0), 4)

    top_confidence = explores[0].confidence
    action = "proceed"

    logger.info("[6/6] Pipeline complete!")
    pipeline_result = PipelineResult(
        query=query,
        explores=explores,
        action=action,
        confidence=top_confidence,
        entities=extracted_entities,
        raw_results=raw_results,
        filters=filter_result,
    )
    logger.info(
        "Result: action=%s, confidence=%.3f, %d entities, %d scored explores",
        action, top_confidence, len(extracted_entities), len(explores),
    )

    return pipeline_result


def get_top_explore(pipeline_result: PipelineResult) -> dict[str, Any]:
    """Return the top explore from a PipelineResult.

    Always returns a dict with at least 'action' and 'confidence'.
    When action is 'proceed', includes explore details and filters.
    When action is 'clarify' or 'no_match', the consumer should prompt the user.
    """
    base: dict[str, Any] = {
        "action": pipeline_result.action,
        "confidence": pipeline_result.confidence,
    }

    if pipeline_result.clarify_reason:
        base["clarify_reason"] = pipeline_result.clarify_reason

    if not pipeline_result.explores:
        return base

    top = pipeline_result.explores[0]
    base["top_explore_name"] = top.name
    base["retrieval_metadata"] = {
        "explore_name": top.name,
        "supported_entities": top.supported_entities,
        "score": top.score,
        "confidence": top.confidence,
        "raw_score": top.raw_score,
        "coverage": top.coverage,
        "is_near_miss": top.is_near_miss,
    }

    if pipeline_result.filters:
        base["filters"] = pipeline_result.filters.to_looker_filters()
        if pipeline_result.filters.unresolved:
            base["unresolved_filters"] = pipeline_result.filters.unresolved

    return base


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
    """Score explores using multiplicative formula with four hardening signals.

    For each entity with candidates, collect (explore, field, view, similarity).
    Group by explore. Compute:
      coverage = matched_entity_count / total_entity_count
      mean_sim = mean of best similarity per matched entity
      base_view_bonus = 1.0 + weighted_base_view_ratio (up to 2.0x)
      desc_sim_bonus = 1.0 + 0.2 * explore_description_similarity
      filter_penalty = max(filter_coverage, FILTER_PENALTY_FLOOR)
      score = coverage³ × mean_sim × base_view_bonus × desc_sim_bonus × filter_penalty

    Four hardening signals:
      P1: Measures count 2x, dimensions 1x in base_view_ratio.
          The measure determines the analytical grain — it should dominate routing.
      P2: Explore description similarity as tiebreaker (0.2 coefficient).
          Handles failure mode where no entity comes from any base view
          (e.g., all entities from cmdl_card_main, a universal join view).
      P3: Base-view match only counts if similarity >= SIMILARITY_FLOOR (0.65).
          Prevents low-quality vector matches from being boosted by structural signal.
      P4: Filter penalty — penalizes explores that lack filter dimensions.
          Linear because filter presence is a binary structural signal.
          Floor of 0.1 prevents zeroing on LLM extraction errors.

    Additional fixes:
      GAP 4: Equal-similarity tie-breaking prefers base-view candidates.
      GAP 5: Skip explores with no entity contributions (hybrid-table-only ghosts).

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

                if similarity > current_best:
                    entity_scores[entity_id] = similarity
                    per_explore_entity_views.setdefault(explore_name, {})[entity_id] = view_name
                elif similarity == current_best:
                    # GAP 4: On tie, prefer candidate from explore's base view.
                    # The base view is the table the explore was designed to analyze —
                    # a tie from a base-view field is more likely the intended match.
                    base_view = EXPLORE_BASE_VIEWS.get(explore_name)
                    if base_view and view_name == base_view:
                        per_explore_entity_views.setdefault(explore_name, {})[entity_id] = view_name

    total_entities = len(entity_ids)
    if total_entities == 0:
        return []

    # ── Phase 2a: Hybrid table enrichment ────────────────────────────
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

    # ── Phase 2b: Filter field_hint presence check (GAP 1) ──────────
    # Extract filter hints from entities and check which explores have them.
    # This MUST happen before scoring so filter_penalty routes correctly.
    filter_hints = [
        entity.get("name", "")
        for entity in entities
        if entity.get("type") == "filter" and entity.get("name")
    ]
    explore_filter_hits: dict[str, set[str]] = {}
    if filter_hints:
        explore_filter_hits = check_filter_fields_in_explores(filter_hints)
        logger.info(
            "Filter routing: %d hints checked, %d explores have matches",
            len(filter_hints), len(explore_filter_hits),
        )

    # ── Phase 3: Score each explore ──────────────────────────────────
    MEASURE_WEIGHT = 2.0
    DIMENSION_WEIGHT = 1.0

    scored: list[ScoredExplore] = []
    for explore_name, entity_contrib in per_explore_entities.items():
        # GAP 5: Skip explores with no entity contributions.
        # These are "ghost" explores added by hybrid table enrichment
        # that have structural matches but no semantic relevance.
        if not entity_contrib:
            continue

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

        # ── P4: Filter penalty (GAP 1) ──
        # Linear penalty: filter_coverage = present_hints / total_hints
        # Floor of 0.1 prevents zeroing when LLM hallucinated a filter hint
        filter_penalty = 1.0
        if filter_hints:
            matched_hints = explore_filter_hits.get(explore_name, set())
            filter_coverage = len(matched_hints) / len(filter_hints)
            filter_penalty = max(filter_coverage, FILTER_PENALTY_FLOOR)

        # ── Final multiplicative score ──
        raw_score = mean_similarity
        final_score = (
            (coverage ** 3)
            * mean_similarity
            * base_view_bonus
            * desc_sim_bonus
            * filter_penalty
        )

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
