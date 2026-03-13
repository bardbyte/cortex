"""Unified retrieval pipeline combining vector search and graph traversal.

This module orchestrates the end-to-end retrieval flow:
  1) Extract entities from user query using LLM (vector.py)
  2) Find candidate fields via vector similarity search
  3) Validate candidate explores against graph topology (graph_search.py)
  4) Score explores by entity support

Usage:
    results = retrieve_with_graph_validation("Total spend by merchant")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from src.retrieval.vector import EntityExtractor
from src.retrieval.graph_search import find_explores_for_view

logger = logging.getLogger(__name__)


@dataclass
class ScoredExplore:
    """Represents an explore scored by how well it supports extracted entities."""
    name: str
    supported_entities: list[str]
    score: float
    raw_score: float
    coverage: float
    missing_penalty: float


@dataclass
class PipelineResult:
    """Final output from the retrieval pipeline."""
    query: str
    explores: list[ScoredExplore]
    entities: list[dict[str, Any]] | None = None
    raw_results: dict[str, Any] | None = None


def retrieve_with_graph_validation(
    query: str,
    top_k: int = 5,
    llm_model_idx: str = "",
    penalty_constant: float = 0.15,
) -> PipelineResult:
    """
    Execute full retrieval pipeline: entity extraction + vector search + graph validation.

    Args:
        query: User natural language query
        top_k: Number of candidate fields to retrieve per entity
        llm_model_idx: LLM model index for entity extraction
        penalty_constant: Penalty applied for each entity not supported by an explore

    Returns:
        PipelineResult with scored explores and retrieval metadata
    """
    logger.info("Starting retrieval pipeline for query: %s", query)

    # Step 1: Initialize extractor and process query
    logger.info("[1/3] Extracting entities from query...")
    extractor = EntityExtractor(llm_model_idx=llm_model_idx)
    raw_results = extractor.process_query(query, top_k)

    # Step 2: Validate candidate explores against graph topology and score explores
    logger.info("[2/3] Validating candidates and scoring explores...")
    extracted_entities = raw_results.get("entities", [])
    explores = _score_explores(extracted_entities, penalty_constant)

    # Step 3: Format and return
    logger.info("[3/3] Pipeline complete!")
    pipeline_result = PipelineResult(
        query=query,
        entities=extracted_entities,
        explores=explores,
        raw_results=raw_results,
    )
    logger.info(
        "Result: %d entities, %d scored explores",
        len(extracted_entities),
        len(explores),
    )

    return pipeline_result


def get_top_explore(pipeline_result: PipelineResult) -> dict[str, Any] | None:
    """
    Return the top explore: PipelineResult from retrieve_with_graph_validation()

    Returns:
        Dict with top_explore_name and retrieval_metadata, or None if no explores were found
    """
    if not pipeline_result.explores:
        return None

    top = pipeline_result.explores[0]
    return {
        "top_explore_name": top.name,
        "retrieval_metadata": {
            "entity_vector_search": {
                "explore_name": top.name,
                "supported_entities": top.supported_entities,
                "score": top.score,
                "raw_score": top.raw_score,
                "coverage": top.coverage,
                "missing_penalty": top.missing_penalty,
            },
            "graph_search_explore": top.name,
        },
    }


def retrieve_top_explore(
    query: str,
    top_k: int = 5,
    llm_model_idx: str = "",
    penalty_constant: float = 0.15,
) -> dict[str, Any] | None:
    """
    Run full retrieval pipeline and return the top explore with metadata.

    Args:
        query: User natural language query
        top_k: Number of candidate fields to retrieve per entity
        llm_model_idx: LLM model index for entity extraction
        penalty_constant: Penalty applied for each entity not supported by an explore

    Returns:
        Dict with top_explore_name and retrieval_metadata, or None if no explores were found
    """
    result = retrieve_with_graph_validation(query, top_k, llm_model_idx, penalty_constant)
    return get_top_explore(result)


def _score_explores(entities: list[dict[str, Any]], penalty_constant: float) -> list[ScoredExplore]:
    """
    Score explores by validating candidate explore membership in graph results.

    Per explore: sum (similarity * weight * support_flag) over all entities
    RawScore = sum(similarity * weight * support_flag)
    coverage = supported_entities / total_entities
    MissingPenalty = (total_entities - supported_entities) * penalty_constant
    FinalScore = (RawScore + coverage) - MissingPenalty

    Args:
        entities: Raw entities from EntityExtractor.process_query()
        penalty_constant: Penalty applied for each unsupported entity

    Returns:
        Explore scores sorted descending by final score
    """
    # explore_support: dict[str, dict[str, float]] = {}
    per_explore_support: dict[str, dict[str, float]] = {}

    entity_ids: list[str] = []
    for entity in entities:
        entity_type = entity.get("type", "unknown")
        entity_id = entity.get("id", "unknown")
        weight = float(entity.get("weight", 1.0))

        logger.debug("Processing entity %s (type=%s, name=%s)", entity_id, entity_type, entity.get("name"))

        if entity_type not in ("measure", "dimension", "filter"):
            logger.warning("Unknown entity type: %s", entity_type)
            continue

        entity_ids.append(entity_id)
        candidates = entity.get("candidates", [])

        for candidate in candidates:
            candidate_explore = candidate.get("explore")
            similarity = candidate.get("similarity", 0.0)
            view_name = candidate.get("view_name")
            field_name = candidate.get("field_name")

            if not candidate_explore or not view_name:
                continue

            try:
                matched_explores = find_explores_for_view(view_name)
            except Exception as e:
                logger.debug("Error querying graph for view=%s: %s", view_name, e)
                matched_explores = []

            matched_explore_names = set(_get_explore_names(matched_explores))

            # Candidate contributes only when its own explore exists in graph-matched explores.
            support_flag = 1.0 if candidate_explore in matched_explore_names else 0.0

            contribution = similarity * weight * support_flag
            if support_flag == 0.0:
                continue

            explore_support = per_explore_support.setdefault(candidate_explore, {})
            explore_support[entity_id] = max(explore_support.get(entity_id, 0.0), contribution)

    total_entities = len(entity_ids)
    if total_entities == 0:
        return []

    scored: list[ScoredExplore] = []
    for explore_name, entity_contrib in per_explore_support.items():
        supported_entity_ids = list(entity_contrib.keys())
        supported_entities = sum(entity_contrib.values())
        raw_score = sum(entity_contrib.values())
        coverage = (total_entities / total_entities) if total_entities > 0 else 0
        supported_entities_count = len(supported_entity_ids)
        missing_penalty = (total_entities - supported_entities_count) * penalty_constant
        final_score = (raw_score + coverage) - missing_penalty

        scored.append(
            ScoredExplore(
                name=explore_name,
                supported_entities=supported_entity_ids,
                score=round(final_score, 4),
                raw_score=round(raw_score, 4),
                coverage=round(coverage, 4),
                missing_penalty=round(missing_penalty, 4),
            )
        )

    scored.sort(key=lambda e: e.score, reverse=True)
    return scored


def _get_explore_names(matched_explores: list[str]) -> list[str]:
    """Extract explore names from graph results."""
    names = []
    for explore in matched_explores:
        if isinstance(explore, str) and explore.endswith("::vertex"):
            try:
                parsed = json.loads(explore[:-len("::vertex")])
                if isinstance(parsed, dict):
                    name = parsed.get("properties", {}).get("name")
                    if isinstance(name, str):
                        names.append(name)
            except json.JSONDecodeError:
                continue
        else:
            obj_name = getattr(explore, "name", str)
            if isinstance(obj_name, dict):
                names.append(obj_name)
            name = explore.get("name") if isinstance(explore, dict) else None
            if name:
                names.append(name)
            if isinstance(explore, str):
                names.append(name)

    return names


def _demo_run() -> None:
    """Demo: Run full pipeline on multiple queries and fetch top explore for each."""
    logging.basicConfig(level=logging.INFO, format="%(levelnames)s %(name)s: %(message)s")

    print("\n" + "=" * 80)
    print("Pipeline Demo — Top Explore for Multiple Queries")
    print("=" * 80)

    queries = [
        "Millennial customers with billed business over $100k",
        "Total spend by merchant category",
        "Card issuance by region",
        "Customer loyalty metrics",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        output = retrieve_top_explore(query, top_k=5)
        print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    _demo_run()
