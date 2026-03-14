"""Pipeline stage tools -- each wraps a pipeline step as a callable.

These are NOT LlmAgent tools (the LLM does not choose when to call them).
They are called directly by CortexAgent._run_async_impl() at deterministic
points in the pipeline.

Exception: validate_sql_post_execution IS exposed as an ADK FunctionTool
inside query_agent, so the LLM calls it after receiving SQL from Looker MCP
but before executing the query.

Tool inventory:
  classify_intent        -- 1 LLM call, ~200ms
  retrieve_fields        -- 0 LLM calls, ~260ms
  resolve_filters        -- 0 LLM calls, ~15ms
  validate_query         -- 0 LLM calls, ~5ms   (pre-execution, deterministic)
  validate_sql_post_exec -- 0 LLM calls, ~5ms   (post-SQL-gen, before execution)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.retrieval.models import RetrievalResult
from src.retrieval import filters as filter_module

logger = logging.getLogger(__name__)


# =====================================================================
# Data Models for Tool I/O
# =====================================================================

@dataclass
class ExtractedEntities:
    """Structured entities extracted from user query."""
    metrics: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    time_range: str | None = None
    sort: str | None = None
    limit: int | None = None


@dataclass
class ClassificationResult:
    """Output of intent classification."""
    intent: str        # data_query | schema_browse | saved_content | follow_up | out_of_scope
    confidence: float  # 0.0 - 1.0
    entities: ExtractedEntities
    reasoning: str


@dataclass
class ValidationResult:
    """Output of pre-execution query validation."""
    valid: bool
    issues: list[str] = field(default_factory=list)
    blocking: bool = False    # True = hard stop (missing partition filter)
    warnings: list[str] = field(default_factory=list)
    estimated_scan_gb: float | None = None


# =====================================================================
# Tool: classify_intent
# =====================================================================

async def classify_intent(
    query: str,
    history: list[dict],
    taxonomy_terms: list[str],
    classifier_llm: Any,
) -> ClassificationResult:
    """Classify user intent and extract structured entities.

    This is the ONE LLM call in Phase 1. Uses Gemini Flash for speed.

    The prompt includes:
      - Intent taxonomy (data_query, schema_browse, etc.)
      - Available business terms (from LookML descriptions + taxonomy)
      - Conversation history (for follow-up detection)

    Args:
        query: The raw user query string.
        history: Conversation history as list of {role, content} dicts.
        taxonomy_terms: List of known business terms for the prompt.
        classifier_llm: SafeChainLlm instance (Flash, no tools).

    Returns:
        ClassificationResult with intent, confidence, and extracted entities.

    Latency budget: 400ms (P95).
    """
    from src.pipeline.prompts import CLASSIFY_AND_EXTRACT_PROMPT
    from langchain_core.messages import HumanMessage, SystemMessage

    # Build context from recent history
    previous_context = ""
    if history:
        recent = history[-4:]  # last 2 exchanges
        previous_context = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        )

    prompt = CLASSIFY_AND_EXTRACT_PROMPT.format(
        taxonomy_terms="\n".join(f"- {t}" for t in taxonomy_terms[:50]),
        previous_context=previous_context or "(first message in conversation)",
        query=query,
    )

    # Direct SafeChain call via the underlying MCPToolAgent
    # (classifier_llm has no tools, so this is a single prompt->response call)
    await classifier_llm.connect()
    lc_messages = [HumanMessage(content=prompt)]
    result = await classifier_llm._agent.ainvoke(lc_messages)

    # Extract text from result
    if isinstance(result, dict):
        response_text = result.get("content", "")
    elif hasattr(result, "content"):
        response_text = str(result.content)
    else:
        response_text = str(result)

    # Parse JSON response
    return _parse_classification_response(response_text, query)


def _parse_classification_response(
    response_text: str,
    original_query: str,
) -> ClassificationResult:
    """Parse the LLM's JSON classification response.

    Handles common failure modes:
      - Markdown code fences wrapping the JSON
      - Partial JSON (trailing text after the object)
      - Complete parse failure (falls back to data_query)
    """
    try:
        cleaned = response_text.strip()

        # Strip markdown code fences
        if cleaned.startswith("```"):
            # Remove first line (```json or ```) and last line (```)
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3]

        # Try to find the JSON object boundaries
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            cleaned = cleaned[start:end]

        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "Classification JSON parse failed: %s | response: %s",
            e,
            response_text[:200],
        )
        return ClassificationResult(
            intent="data_query",
            confidence=0.5,
            entities=ExtractedEntities(metrics=[original_query]),
            reasoning="JSON parse failed -- falling through as data_query",
        )

    entities_data = data.get("entities", {})
    entities = ExtractedEntities(
        metrics=entities_data.get("metrics", []),
        dimensions=entities_data.get("dimensions", []),
        filters=entities_data.get("filters", {}),
        time_range=entities_data.get("time_range"),
        sort=entities_data.get("sort"),
        limit=entities_data.get("limit"),
    )

    return ClassificationResult(
        intent=data.get("intent", "data_query"),
        confidence=data.get("confidence", 0.5),
        entities=entities,
        reasoning=data.get("reasoning", ""),
    )


# =====================================================================
# Tool: retrieve_fields
# =====================================================================

def retrieve_fields(
    entities: dict,
    retrieval_orchestrator: Any,
) -> RetrievalResult:
    """Run hybrid retrieval pipeline. ZERO LLM calls.

    Calls the 10-step RetrievalOrchestrator:
      1. Per-entity vector search (pgvector)
      2. Confidence gate
      3. Near-miss detection
      4. Candidate collection for graph
      5. Structural validation (Apache AGE)
      6. Few-shot search (FAISS)
      7. Few-shot signal application
      8. Explore scoring + ranking
      9. Disambiguation check
     10. Field splitting + filter resolution

    Args:
        entities: Dict with keys: metrics, dimensions, filters, time_range.
        retrieval_orchestrator: RetrievalOrchestrator instance.

    Returns:
        RetrievalResult with action, model, explore, dimensions, measures.

    Latency budget: 260ms (P95).
    """
    return retrieval_orchestrator.retrieve(entities)


# =====================================================================
# Tool: resolve_filters
# =====================================================================

def resolve_filters(
    entities: ExtractedEntities,
    explore_name: str,
) -> dict[str, str]:
    """Resolve raw user filter values to LookML-compatible expressions.

    ZERO LLM calls -- deterministic 5-pass resolution:
      Pass 1: Exact match (namespaced value map)
      Pass 2: Synonym expansion
      Pass 3: Fuzzy match (Levenshtein <= 2)
      Pass 4: Embedding similarity (TODO)
      Pass 5: Passthrough with low confidence

    Also handles:
      - Yesno dimensions ("enrolled" -> "Yes")
      - Negation ("not Gold" -> "-GOLD")
      - Numeric ranges ("between 1000 and 5000" -> "[1000,5000]")
      - Time normalization ("Q4 2025" -> "2025-10-01 to 2025-12-31")
      - Mandatory partition filter injection

    Args:
        entities: ExtractedEntities from classification.
        explore_name: Selected explore name for context-aware resolution.

    Returns:
        Dict of {field_name: looker_filter_value} ready for Looker MCP.

    Latency budget: 15ms.
    """
    entity_list: list[dict[str, Any]] = []

    for dim_name, value in entities.filters.items():
        entity_list.append({
            "type": "filter",
            "name": dim_name,
            "values": [value],
            "operator": "=",
        })

    if entities.time_range:
        entity_list.append({
            "type": "time_range",
            "name": "time_range",
            "values": [entities.time_range],
        })

    result = filter_module.resolve_filters(entity_list, explore_name)
    return result.to_looker_filters()


# =====================================================================
# Tool: validate_query (pre-execution, deterministic)
# =====================================================================

def validate_query(retrieval_result: RetrievalResult) -> ValidationResult:
    """Pre-execution validation. ZERO LLM calls.

    Five checks before we let Looker MCP execute:

    Check 1: Partition filter present (BLOCKING)
      Every explore in the finance model has ALWAYS_FILTER_ON pointing to
      a partition date dimension. Without it, BigQuery scans the full table.

    Check 2: Dimensions + measures not empty
      A query with no fields is nonsensical.

    Check 3: Model + explore resolved
      Must have non-empty model and explore names.

    Check 4: Field count sanity
      More than 20 dimensions or 10 measures is almost certainly wrong.

    Check 5: SQL injection patterns (defense in depth)
      Should never happen via MCP (parameterized queries), but belt + suspenders.

    Args:
        retrieval_result: The RetrievalResult from hybrid retrieval.

    Returns:
        ValidationResult with issues list and blocking flag.
    """
    issues: list[str] = []
    warnings: list[str] = []
    blocking = False

    # Check 1: Partition filter
    partition_field = filter_module.EXPLORE_PARTITION_FIELDS.get(
        retrieval_result.explore, "partition_date"
    )
    if partition_field not in retrieval_result.filters:
        issues.append(
            f"MISSING PARTITION FILTER: {partition_field} not in filters. "
            f"This will cause a full table scan on {retrieval_result.explore}."
        )
        blocking = True

    # Check 2: Fields not empty
    if not retrieval_result.dimensions and not retrieval_result.measures:
        issues.append("No dimensions or measures resolved. Cannot generate query.")
        blocking = True

    # Check 3: Model + explore present
    if not retrieval_result.model:
        issues.append("Model name not resolved.")
        blocking = True
    if not retrieval_result.explore:
        issues.append("Explore name not resolved.")
        blocking = True

    # Check 4: Field count sanity
    if len(retrieval_result.dimensions) > 20:
        warnings.append(
            f"High dimension count ({len(retrieval_result.dimensions)}). "
            f"Check retrieval quality."
        )
    if len(retrieval_result.measures) > 10:
        warnings.append(
            f"High measure count ({len(retrieval_result.measures)}). "
            f"Check retrieval quality."
        )

    # Check 5: SQL injection patterns in filter values
    _DANGEROUS_PATTERNS = [
        "DROP ", "DELETE ", "UPDATE ", "INSERT ", "ALTER ",
        "TRUNCATE ", "--", ";--", "/*", "*/", "xp_",
    ]
    for field_name, value in retrieval_result.filters.items():
        value_upper = str(value).upper()
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in value_upper:
                issues.append(
                    f"Dangerous pattern '{pattern.strip()}' detected in "
                    f"filter {field_name}='{value}'."
                )
                blocking = True

    return ValidationResult(
        valid=len(issues) == 0,
        issues=issues,
        blocking=blocking,
        warnings=warnings,
    )


# =====================================================================
# Tool: validate_sql_post_execution (FunctionTool for query_agent)
# =====================================================================

def validate_sql_post_execution(
    sql: str,
    retrieval_result_dict: dict,
) -> dict:
    """Post-generation SQL validation for the query_agent.

    Exposed as an ADK FunctionTool so the query_agent LlmAgent calls it
    after Looker MCP's query_sql returns SQL but BEFORE calling query to
    execute.

    CRITICAL: Looker MCP has TWO separate tools:
      - query_sql: generates SQL only (returns SQL string, no execution)
      - query: executes and returns data rows
    This separation enables validate-then-execute.

    Pipeline in query_agent:
      1. LLM calls query_sql (Looker MCP) -> gets SQL
      2. LLM calls validate_sql_post_execution -> gets validation
      3. If valid: LLM calls query (Looker MCP) -> gets data
      4. If invalid: LLM reports issue (no execution)

    Checks:
      1. Query is SELECT only
      2. Partition field appears in WHERE clause
      3. Expected fields appear in SELECT/GROUP BY
      4. No DML/DDL patterns

    Args:
        sql: The SQL string generated by Looker MCP's query_sql.
        retrieval_result_dict: The RetrievalResult as a dict (from session state).

    Returns:
        Dict with {valid, issues, sql_length, recommendation}.
        Returns a dict (not a dataclass) because ADK FunctionTools must
        return JSON-serializable types.
    """
    issues: list[str] = []
    sql_upper = sql.upper().strip()

    # Must be a SELECT
    if not sql_upper.startswith("SELECT"):
        issues.append("Query is not a SELECT statement.")

    # Partition filter in WHERE
    explore = retrieval_result_dict.get("explore", "")
    expected_partition = filter_module.EXPLORE_PARTITION_FIELDS.get(
        explore, "partition_date"
    )
    if "WHERE" not in sql_upper:
        issues.append("No WHERE clause -- will scan entire table.")
    elif expected_partition.upper() not in sql_upper:
        issues.append(
            f"Partition field '{expected_partition}' not found in WHERE clause. "
            f"Risk of full table scan."
        )

    # Check expected fields appear somewhere in the SQL
    expected_dims = retrieval_result_dict.get("dimensions", [])
    expected_measures = retrieval_result_dict.get("measures", [])
    missing_fields = []
    for field_name in expected_dims + expected_measures:
        if field_name.upper() not in sql_upper:
            missing_fields.append(field_name)
    if missing_fields:
        issues.append(
            f"Expected fields not found in SQL: {missing_fields}. "
            f"Looker may have aliased them."
        )

    # DML/DDL guard
    for dangerous in ["DROP ", "DELETE ", "UPDATE ", "INSERT ", "ALTER ", "TRUNCATE "]:
        if dangerous in sql_upper:
            issues.append(f"Dangerous SQL operation detected: {dangerous.strip()}")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "sql_length": len(sql),
        "recommendation": "proceed" if not issues else "do_not_execute",
    }
