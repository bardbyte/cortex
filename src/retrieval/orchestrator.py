"""Retrieval Orchestrator — the brain of the Cortex retrieval system.

Coordinates vector search (pgvector), graph validation (Apache AGE),
and few-shot matching (FAISS) into a single, structurally validated
RetrievalResult that the Looker MCP can execute directly.

Position in the pipeline:
  Stage 2 (Entity Extraction) → THIS → Stage 4 (SQL Generation via Looker MCP)

Why this exists:
  Each retrieval channel answers a DIFFERENT question:
    - Vector (pgvector): "What fields are semantically similar to the user's terms?"
    - Graph (AGE):       "Can these fields actually be queried together?"
    - Few-shot (FAISS):  "Have we seen a query like this before?"

  No single channel gives you the answer. The orchestrator:
    1. Calls each channel with the right inputs
    2. Applies quality gates (confidence floor, near-miss detection)
    3. Fuses results with structural validation as the final arbiter
    4. Resolves filter values, injects mandatory filters, handles disambiguation
    5. Returns a ready-to-execute RetrievalResult

Key design decisions (see ADR-004):
  - Per-field-per-view embedding (41 rows, NOT per-explore). Graph handles explore routing.
  - Field names + roles are the interface from vector → graph. No scores, no view names.
  - Three-signal explore weighting: base view priority > few-shot confirmation > coverage count.
  - Confidence floor at 0.70 — below this, don't hit the graph, ask user to rephrase.
  - Near-miss δ of 0.05 — if top-2 scores are within this range, keep both for disambiguation.

Dependencies:
  - src/retrieval/vector (pgvector cosine search)
  - src/retrieval/graph_search (AGE structural validation)
  - src/retrieval/fewshot (FAISS golden query matching)
  - src/retrieval/fusion (RRF merge + validation gate)
  - src/retrieval/models (FieldCandidate, RetrievalResult)
  - src/pipeline/state (CortexState — provides entities, receives result)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.retrieval.models import FieldCandidate, RetrievalResult

logger = logging.getLogger(__name__)

# ─── CONFIGURATION ────────────────────────────────────────────────────
# These thresholds are tuned for v1 (Finance BU, 7 views, 41 fields).
# Re-evaluate when adding new BUs or exceeding 200 fields.

SIMILARITY_FLOOR = 0.70       # Below this, don't trust vector results
NEAR_MISS_DELTA = 0.05        # If top-2 within this range, keep both candidates
DISAMBIGUATION_THRESHOLD = 0.10  # If top-2 explores within this coverage gap, disambiguate
MAX_VECTOR_RESULTS = 20       # Per-entity top-K from pgvector
MAX_FEWSHOT_RESULTS = 5       # Top-K golden query matches from FAISS
MAX_GRAPH_DEPTH = 4           # Max join hops in AGE traversal (BASE_VIEW|JOINS*0..N)


# ─── FILTER VALUE MAP ─────────────────────────────────────────────────
# Single source of truth: src/retrieval/filters.py
# Imported here for backward compatibility with orchestrator's _resolve_filters().
from src.retrieval.filters import FILTER_VALUE_MAP, YESNO_DIMENSIONS


# ─── DATA STRUCTURES ─────────────────────────────────────────────────

@dataclass
class EntitySearchResult:
    """Per-entity vector search output before graph validation."""
    entity_text: str         # Original user term, e.g. "total spend"
    entity_role: str         # "metric" | "dimension" | "filter"
    candidates: list[FieldCandidate] = field(default_factory=list)
    top_score: float = 0.0
    near_miss: bool = False  # True if top-2 within NEAR_MISS_DELTA


@dataclass
class ExploreCandidate:
    """An explore that passed structural validation with scored fields."""
    explore: str
    model: str
    confirmed_fields: list[FieldCandidate] = field(default_factory=list)
    coverage: float = 0.0          # fraction of requested fields found
    base_view_priority: bool = False  # True if primary measure comes from explore's base view
    fewshot_confirmed: bool = False   # True if a golden query matched this explore
    score: float = 0.0               # Composite score for ranking


# ─── ORCHESTRATOR ─────────────────────────────────────────────────────

class RetrievalOrchestrator:
    """Coordinates vector → graph → fewshot → fusion into a RetrievalResult.

    Usage:
        orchestrator = RetrievalOrchestrator(pg_conn, embed_fn)
        result = orchestrator.retrieve(entities)
        # result.action is "proceed" | "disambiguate" | "clarify" | "no_match"

    Args:
        pg_conn: Active psycopg connection (shared by pgvector and AGE).
        embed_fn: Callable that turns text → 1024-dim embedding vector.
                  Signature: (text: str) -> list[float]
                  In production, this calls SafeChain's BGE-large-en endpoint.
                  Locally, uses sentence-transformers via model_adapter.
        model_name: Optional model scope (e.g. "finance") to narrow vector search.
    """

    def __init__(self, pg_conn, embed_fn, *, model_name: str | None = None):
        self.pg_conn = pg_conn
        self.embed_fn = embed_fn
        self.model_name = model_name

    # ── MAIN ENTRY POINT ──────────────────────────────────────────

    def retrieve(self, entities: dict) -> RetrievalResult:
        """10-step retrieval pipeline. Takes extracted entities, returns
        a structurally validated RetrievalResult ready for Looker MCP.

        Args:
            entities: Output of Stage 2 (entity extraction). Expected keys:
                {
                    "metrics": ["total billed business"],
                    "dimensions": ["generation", "card product"],
                    "filters": {"generation": "Millennials"},
                    "time_range": "last 90 days"
                }

        Returns:
            RetrievalResult with action, model, explore, dimensions, measures, filters.
        """

        # Step 1: Per-entity vector search
        entity_results = self._vector_search_per_entity(entities)

        # Step 2: Confidence gate — reject if ALL entities below floor
        if self._all_below_confidence_floor(entity_results):
            logger.warning("All entities below confidence floor %.2f", SIMILARITY_FLOOR)
            return RetrievalResult(
                action="clarify",
                confidence=max((r.top_score for r in entity_results), default=0.0),
            )

        # Step 3: Near-miss detection — flag entities where top candidates are close
        self._detect_near_misses(entity_results)

        # Step 4: Collect candidate field names + roles for graph validation
        candidate_fields = self._collect_candidates_for_graph(entity_results)

        # Step 5: Structural validation via AGE graph
        valid_explores = self._graph_validate(candidate_fields)

        if not valid_explores:
            logger.warning("No explore contains all candidate fields")
            return RetrievalResult(action="no_match", confidence=0.0)

        # Step 6: Few-shot search — check if golden queries confirm an explore
        fewshot_matches = self._fewshot_search(entities)
        self._apply_fewshot_signal(valid_explores, fewshot_matches)

        # Step 7: Score and rank explores (three-signal weighting)
        ranked_explores = self._rank_explores(valid_explores, entity_results)

        # Step 8: Disambiguation check — are top-2 explores too close?
        if self._needs_disambiguation(ranked_explores):
            return self._build_disambiguation_result(ranked_explores)

        # Step 9: Select best explore, resolve filter values, inject mandatory filters
        best = ranked_explores[0]
        dimensions, measures = self._split_fields(best.confirmed_fields)
        filters = self._resolve_filters(entities, best.explore)
        mandatory_filters = self._get_mandatory_filters(best.explore)
        filters.update(mandatory_filters)

        # Step 10: Construct RetrievalResult
        return RetrievalResult(
            action="proceed",
            model=best.model,
            explore=best.explore,
            dimensions=[f.field_name for f in dimensions],
            measures=[f.field_name for f in measures],
            filters=filters,
            confidence=best.score,
            coverage=best.coverage,
            fewshot_matches=[
                m.id if hasattr(m, "id") else str(m)
                for m in fewshot_matches[:3]
            ],
        )

    # ── STEP 1: PER-ENTITY VECTOR SEARCH ──────────────────────────

    def _vector_search_per_entity(self, entities: dict) -> list[EntitySearchResult]:
        """Search pgvector separately for each extracted entity.

        Why per-entity (not a single combined embedding)?
          "total billed business by generation" embeds as one vector that's close
          to neither "billed business" nor "generation" individually. Per-entity
          search gets precision on each concept, then graph combines them.
        """
        from src.retrieval import vector

        results = []

        for metric in entities.get("metrics", []):
            embedding = self.embed_fn(metric)
            candidates = vector.search(
                self.pg_conn, embedding,
                top_k=MAX_VECTOR_RESULTS, model_name=self.model_name,
            )
            results.append(EntitySearchResult(
                entity_text=metric,
                entity_role="metric",
                candidates=candidates,
                top_score=candidates[0].score if candidates else 0.0,
            ))

        for dim in entities.get("dimensions", []):
            embedding = self.embed_fn(dim)
            candidates = vector.search(
                self.pg_conn, embedding,
                top_k=MAX_VECTOR_RESULTS, model_name=self.model_name,
            )
            results.append(EntitySearchResult(
                entity_text=dim,
                entity_role="dimension",
                candidates=candidates,
                top_score=candidates[0].score if candidates else 0.0,
            ))

        for filt_key in entities.get("filters", {}):
            embedding = self.embed_fn(filt_key)
            candidates = vector.search(
                self.pg_conn, embedding,
                top_k=MAX_VECTOR_RESULTS, model_name=self.model_name,
            )
            results.append(EntitySearchResult(
                entity_text=filt_key,
                entity_role="filter",
                candidates=candidates,
                top_score=candidates[0].score if candidates else 0.0,
            ))

        return results

    # ── STEP 2: CONFIDENCE GATE ───────────────────────────────────

    @staticmethod
    def _all_below_confidence_floor(
        entity_results: list[EntitySearchResult],
    ) -> bool:
        """If every entity's top score is below the floor, the query is
        too far from anything we know. Ask the user to rephrase."""
        return all(r.top_score < SIMILARITY_FLOOR for r in entity_results)

    # ── STEP 3: NEAR-MISS DETECTION ───────────────────────────────

    @staticmethod
    def _detect_near_misses(entity_results: list[EntitySearchResult]) -> None:
        """Flag entities where the top-2 candidates are within NEAR_MISS_DELTA.

        This catches ambiguity:
          "active customers" → active_customers_standard (0.92) vs
                               active_customers_premium (0.89)
          Delta = 0.03 < 0.05 → near miss → keep both for disambiguation.
        """
        for result in entity_results:
            if len(result.candidates) >= 2:
                delta = result.candidates[0].score - result.candidates[1].score
                if delta < NEAR_MISS_DELTA:
                    result.near_miss = True
                    logger.info(
                        "Near-miss on '%s': %s (%.3f) vs %s (%.3f), δ=%.3f",
                        result.entity_text,
                        result.candidates[0].field_name,
                        result.candidates[0].score,
                        result.candidates[1].field_name,
                        result.candidates[1].score,
                        delta,
                    )

    # ── STEP 4: COLLECT CANDIDATES FOR GRAPH ──────────────────────

    @staticmethod
    def _collect_candidates_for_graph(
        entity_results: list[EntitySearchResult],
    ) -> list[str]:
        """Extract unique field names to send to the AGE graph.

        The graph receives ONLY field names — no scores, no view names.
        It answers: "Which explores contain ALL of these fields?"

        For near-miss entities, include both top candidates so the graph
        can try both combinations.
        """
        field_names: list[str] = []
        seen: set[str] = set()

        for result in entity_results:
            if not result.candidates:
                continue

            # Always include the top candidate
            top = result.candidates[0]
            if top.field_name not in seen:
                field_names.append(top.field_name)
                seen.add(top.field_name)

            # For near-misses, also include the runner-up
            if result.near_miss and len(result.candidates) >= 2:
                runner_up = result.candidates[1]
                if runner_up.field_name not in seen:
                    field_names.append(runner_up.field_name)
                    seen.add(runner_up.field_name)

        return field_names

    # ── STEP 5: GRAPH VALIDATION ──────────────────────────────────

    def _graph_validate(
        self, candidate_fields: list[str],
    ) -> list[ExploreCandidate]:
        """Run AGE Cypher structural validation.

        Asks: "Which explores contain ALL of these candidate fields?"
        Returns explores ranked by coverage.

        The graph also tells us which fields come from the base view vs
        joined views — this is the base_view_priority signal.
        """
        from src.retrieval import graph_search

        raw_results = graph_search.validate_fields_in_explore(
            self.pg_conn, candidate_fields,
        )

        explores = []
        for row in raw_results:
            explores.append(ExploreCandidate(
                explore=row["explore"],
                model=row.get("model", self.model_name or ""),
                confirmed_fields=[],  # Populated in _rank_explores
                coverage=row["coverage"] / len(candidate_fields) if candidate_fields else 0.0,
                base_view_priority=row.get("base_view_match", False),
            ))

        return explores

    # ── STEP 6: FEW-SHOT SEARCH ───────────────────────────────────

    @staticmethod
    def _fewshot_search(entities: dict) -> list:
        """Search FAISS for golden queries matching the user's intent.

        Uses the combined entity text (metrics + dimensions) as the query.
        Returns GoldenQuery objects with known-correct field selections.
        """
        from src.retrieval import fewshot

        # Build a search string from all entities
        parts = entities.get("metrics", []) + entities.get("dimensions", [])
        if not parts:
            return []

        query_text = " ".join(parts)
        return fewshot.search(query_text, top_k=MAX_FEWSHOT_RESULTS)

    @staticmethod
    def _apply_fewshot_signal(
        explores: list[ExploreCandidate], fewshot_matches: list,
    ) -> None:
        """Mark explores that are confirmed by golden query matches."""
        if not fewshot_matches:
            return

        confirmed_explores = set()
        for match in fewshot_matches:
            if hasattr(match, "explore"):
                confirmed_explores.add(match.explore)
            elif isinstance(match, FieldCandidate):
                confirmed_explores.add(match.explore)

        for explore in explores:
            if explore.explore in confirmed_explores:
                explore.fewshot_confirmed = True

    # ── STEP 7: SCORE AND RANK EXPLORES ───────────────────────────

    @staticmethod
    def _rank_explores(
        explores: list[ExploreCandidate],
        entity_results: list[EntitySearchResult],
    ) -> list[ExploreCandidate]:
        """Three-signal explore scoring.

        Signal 1 — Base view priority (strongest):
          If the primary measure comes from the explore's BASE_VIEW,
          that explore gets priority. A measure from a joined view is
          a smell — it usually means the wrong explore.

        Signal 2 — Few-shot confirmation:
          A golden query matching this explore is strong evidence.
          Bumps score by 0.2.

        Signal 3 — Field coverage count (tiebreaker):
          How many of the requested fields does this explore contain?
          Higher is better, but this alone can be misleading.

        Scoring formula:
          score = coverage
                  + (0.3 if base_view_priority)
                  + (0.2 if fewshot_confirmed)
        """
        for explore in explores:
            score = explore.coverage
            if explore.base_view_priority:
                score += 0.3
            if explore.fewshot_confirmed:
                score += 0.2
            explore.score = score

        explores.sort(key=lambda e: e.score, reverse=True)

        # Populate confirmed_fields on the top candidate from entity_results
        if explores:
            top_explore = explores[0].explore
            for explore in explores:
                confirmed = []
                for er in entity_results:
                    for c in er.candidates:
                        if c.explore == explore.explore:
                            confirmed.append(c)
                            break
                explore.confirmed_fields = confirmed

        return explores

    # ── STEP 8: DISAMBIGUATION CHECK ──────────────────────────────

    @staticmethod
    def _needs_disambiguation(
        ranked_explores: list[ExploreCandidate],
    ) -> bool:
        """If top-2 explores are within DISAMBIGUATION_THRESHOLD, ask the user."""
        if len(ranked_explores) < 2:
            return False
        gap = ranked_explores[0].score - ranked_explores[1].score
        return gap < DISAMBIGUATION_THRESHOLD

    @staticmethod
    def _build_disambiguation_result(
        ranked_explores: list[ExploreCandidate],
    ) -> RetrievalResult:
        """Build a RetrievalResult that asks the user to choose."""
        alternatives = []
        for explore in ranked_explores[:3]:
            alternatives.append({
                "explore": explore.explore,
                "model": explore.model,
                "coverage": explore.coverage,
                "score": explore.score,
                "base_view_priority": explore.base_view_priority,
                "fewshot_confirmed": explore.fewshot_confirmed,
            })

        return RetrievalResult(
            action="disambiguate",
            confidence=ranked_explores[0].score,
            alternatives=alternatives,
        )

    # ── STEP 9: FILTER RESOLUTION + MANDATORY FILTERS ─────────────

    def _resolve_filters(self, entities: dict, explore: str) -> dict[str, str]:
        """Translate user filter values to their LookML equivalents.

        Three types of resolution:
          1. Categorical: "Millennials" → "Millennial" (via FILTER_VALUE_MAP)
          2. Yesno: "yes" → "Yes" (Looker yesno syntax)
          3. Time: "last quarter" → "last 1 quarters" (Looker time syntax)
        """
        raw_filters = entities.get("filters", {})
        resolved: dict[str, str] = {}

        for dim_name, user_value in raw_filters.items():
            user_lower = str(user_value).lower().strip()

            # Check categorical map
            if dim_name in FILTER_VALUE_MAP:
                mapped = FILTER_VALUE_MAP[dim_name].get(user_lower)
                if mapped:
                    resolved[dim_name] = mapped
                    continue

            # Check yesno dimensions
            if dim_name in YESNO_DIMENSIONS:
                if user_lower in ("yes", "true", "y", "1"):
                    resolved[dim_name] = "Yes"
                elif user_lower in ("no", "false", "n", "0"):
                    resolved[dim_name] = "No"
                continue

            # Pass through as-is (time ranges, numeric values, etc.)
            resolved[dim_name] = str(user_value)

        # Add time_range as partition filter — use correct field name per explore
        from src.retrieval.filters import EXPLORE_PARTITION_FIELDS
        time_range = entities.get("time_range")
        if time_range:
            partition_field = EXPLORE_PARTITION_FIELDS.get(explore, "partition_date")
            resolved[partition_field] = time_range

        return resolved

    def _get_mandatory_filters(self, explore: str) -> dict[str, str]:
        """Get required partition filters from the AGE graph.

        Every explore in the finance model has ALWAYS_FILTER_ON edges
        pointing to partition dimensions. These MUST be in the final query.
        """
        from src.retrieval import graph_search
        from src.retrieval.filters import EXPLORE_PARTITION_FIELDS

        try:
            filters = graph_search.get_partition_filters(self.pg_conn, explore)
            mandatory = {}
            for f in filters:
                field_name = f.get("filter_field", "")
                if field_name and field_name not in mandatory:
                    # Default to "last 90 days" if no user-specified time range
                    mandatory[field_name] = "last 90 days"
            return mandatory
        except (NotImplementedError, Exception) as exc:
            logger.debug("Mandatory filter lookup failed: %s", exc)
            # Fallback: use explore-specific partition field name
            partition_field = EXPLORE_PARTITION_FIELDS.get(explore, "partition_date")
            return {partition_field: "last 90 days"}

    # ── STEP 10: FIELD SPLITTING ──────────────────────────────────

    @staticmethod
    def _split_fields(
        fields: list[FieldCandidate],
    ) -> tuple[list[FieldCandidate], list[FieldCandidate]]:
        """Split confirmed fields into dimensions and measures."""
        dimensions = [f for f in fields if f.field_type == "dimension"]
        measures = [f for f in fields if f.field_type == "measure"]
        return dimensions, measures
