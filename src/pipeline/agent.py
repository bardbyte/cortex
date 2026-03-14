"""Cortex root agent -- custom BaseAgent that orchestrates the NL2SQL pipeline.

WHY custom BaseAgent instead of LlmAgent:
  LlmAgent gives the LLM control over which tools to call and in what order.
  But our pipeline is NOT LLM-driven -- it is a deterministic sequence with
  LLM calls at specific points. The LLM does not decide to "retrieve fields" --
  the pipeline always retrieves fields after classification.

  Custom BaseAgent gives us:
    1. Deterministic pipeline sequencing (classify -> retrieve -> filter -> validate)
    2. Conditional routing (disambiguate | clarify | proceed | out_of_scope)
    3. Streaming events at each step (PipelineStepEvent for frontend)
    4. Per-step latency tracking (PipelineTrace)
    5. Graceful fallback (any step fails -> fall through to PoC behavior)

  The LLM-driven parts (query execution, response formatting) are delegated
  to LlmAgent sub-agents that ADK orchestrates normally.

Architecture:
  CortexAgent._run_async_impl():
    Phase 1 (deterministic, 1 LLM call max):
      1. classify_intent() -> ClassificationResult
      2. Route by intent -> out_of_scope | schema_browse | data_query
      3. retrieve_fields() -> RetrievalResult
      4. Route by action -> disambiguate | clarify | proceed
      5. resolve_filters() -> resolved filter dict
      6. validate_query() -> ValidationResult

    Phase 2 (LLM-driven, 1-3 calls):
      7. query_agent executes query_sql -> validate_sql -> query

    Phase 3 (LLM-driven, 1 call):
      8. response_agent formats results

References:
  - Design doc: docs/design/adk-agent-orchestration-implementation.md
  - ADR-001: adr/001-adk-over-langgraph.md
  - ADK custom agents: https://google.github.io/adk-docs/agents/custom-agents/
"""

from __future__ import annotations

import logging
import time
from typing import AsyncGenerator, Any

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai.types import Content, Part

from src.pipeline.trace import TraceBuilder
from src.pipeline.events import PipelineStepEvent, StepStatus
from src.pipeline.tools import (
    classify_intent,
    retrieve_fields,
    resolve_filters,
    validate_query,
    ClassificationResult,
)
from src.pipeline.prompts import build_augmented_prompt
from src.retrieval.orchestrator import RetrievalOrchestrator

logger = logging.getLogger(__name__)


class CortexAgent(BaseAgent):
    """Root agent for the Cortex NL2SQL pipeline.

    Orchestrates the deterministic pre-processing pipeline, then delegates
    to LlmAgent sub-agents for execution and response formatting.

    Sub-agents (set at construction, referenced by name):
      query_agent          -- executes Looker MCP queries
      response_agent       -- formats results for business users
      disambiguation_agent -- presents options when retrieval is ambiguous
      clarification_agent  -- asks user to rephrase when retrieval fails
      boundary_agent       -- handles out-of-scope queries gracefully

    State protocol:
      CortexAgent writes to ctx.session.state so sub-agents can read context:
        state["retrieval_result"]  -- RetrievalResult as dict
        state["augmented_prompt"]  -- system prompt for query_agent
        state["pipeline_trace"]    -- PipelineTrace.to_dict() after completion
        state["alternatives"]      -- list of explore alternatives for disambiguation
    """

    def __init__(
        self,
        *,
        query_agent: LlmAgent,
        response_agent: LlmAgent,
        disambiguation_agent: LlmAgent,
        clarification_agent: LlmAgent,
        boundary_agent: LlmAgent,
        classifier_llm: Any,
        retrieval_orchestrator: RetrievalOrchestrator,
        embed_fn: Any,
        pg_conn: Any,
        taxonomy_terms: list[str] | None = None,
    ):
        super().__init__(
            name="cortex",
            description=(
                "Cortex NL2SQL pipeline -- translates natural language to "
                "SQL via Looker's semantic layer."
            ),
            sub_agents=[
                query_agent,
                response_agent,
                disambiguation_agent,
                clarification_agent,
                boundary_agent,
            ],
        )
        self._query_agent = query_agent
        self._response_agent = response_agent
        self._disambiguation_agent = disambiguation_agent
        self._clarification_agent = clarification_agent
        self._boundary_agent = boundary_agent
        self._classifier_llm = classifier_llm
        self._retrieval = retrieval_orchestrator
        self._embed_fn = embed_fn
        self._pg_conn = pg_conn
        self._taxonomy_terms = taxonomy_terms or []

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Execute the Cortex pipeline.

        Every step emits PipelineStepEvents that the ADK runner surfaces
        to the frontend via SSE. Sub-agent calls yield their own events
        (tool calls, text chunks) through the standard ADK mechanism.
        """
        user_query = _get_user_query(ctx)
        history = _get_history(ctx)
        state = ctx.session.state
        trace = TraceBuilder(query=user_query)

        # ==============================================================
        # PHASE 1: PRE-PROCESSING (deterministic, 1 LLM call max)
        # ==============================================================

        # ---- Step 1: Intent Classification ----
        yield _step_event("classify_intent", StepStatus.STARTED)
        trace.start_step("classify_intent")

        try:
            classification = await classify_intent(
                query=user_query,
                history=history,
                taxonomy_terms=self._taxonomy_terms,
                classifier_llm=self._classifier_llm,
            )
            trace.increment_llm_calls()
        except Exception as e:
            logger.warning("Classification failed: %s -- falling through", e)
            trace.end_step(
                decision="fallback",
                error=str(e),
                input_summary={"query": user_query},
            )
            yield _step_event(
                "classify_intent", StepStatus.FAILED, detail=str(e),
            )
            # Fallback: pass raw query to query_agent
            async for event in self._query_agent.run_async(ctx):
                yield event
            state["pipeline_trace"] = trace.build(action="fallback").to_dict()
            return

        trace.end_step(
            decision=classification.intent,
            confidence=classification.confidence,
            input_summary={"query": user_query},
            output_summary={
                "intent": classification.intent,
                "confidence": classification.confidence,
                "entities": classification.entities.__dict__,
            },
        )
        yield _step_event(
            "classify_intent",
            StepStatus.COMPLETED,
            detail=f"intent={classification.intent} ({classification.confidence:.0%})",
        )

        # ---- Route by intent ----
        if classification.intent == "out_of_scope":
            state["classification_intent"] = "out_of_scope"
            async for event in self._boundary_agent.run_async(ctx):
                yield event
            state["pipeline_trace"] = trace.build(action="out_of_scope").to_dict()
            return

        if classification.intent in ("schema_browse", "saved_content"):
            # Passthrough: let LLM discover via MCP tools (PoC behavior)
            async for event in self._query_agent.run_async(ctx):
                yield event
            state["pipeline_trace"] = trace.build(action="passthrough").to_dict()
            return

        # ---- Step 2: Hybrid Retrieval ----
        yield _step_event("retrieve_fields", StepStatus.STARTED)
        trace.start_step("retrieve_fields")

        entities_dict = {
            "metrics": classification.entities.metrics,
            "dimensions": classification.entities.dimensions,
            "filters": classification.entities.filters,
            "time_range": classification.entities.time_range,
        }

        try:
            retrieval_result = retrieve_fields(
                entities=entities_dict,
                retrieval_orchestrator=self._retrieval,
            )
        except Exception as e:
            logger.warning("Retrieval failed: %s -- falling through", e)
            trace.end_step(decision="fallback", error=str(e))
            yield _step_event("retrieve_fields", StepStatus.FAILED, detail=str(e))
            async for event in self._query_agent.run_async(ctx):
                yield event
            state["pipeline_trace"] = trace.build(action="fallback").to_dict()
            return

        trace.end_step(
            decision=retrieval_result.action,
            confidence=retrieval_result.confidence,
            input_summary={"entities": entities_dict},
            output_summary={
                "action": retrieval_result.action,
                "model": retrieval_result.model,
                "explore": retrieval_result.explore,
                "dimensions": retrieval_result.dimensions,
                "measures": retrieval_result.measures,
                "confidence": retrieval_result.confidence,
            },
        )
        yield _step_event(
            "retrieve_fields",
            StepStatus.COMPLETED,
            detail=(
                f"action={retrieval_result.action} "
                f"explore={retrieval_result.explore} "
                f"confidence={retrieval_result.confidence:.0%}"
            ),
        )

        # ---- Route by retrieval action ----
        if retrieval_result.action == "disambiguate":
            state["alternatives"] = retrieval_result.alternatives
            async for event in self._disambiguation_agent.run_async(ctx):
                yield event
            state["pipeline_trace"] = trace.build(action="disambiguate").to_dict()
            return

        if retrieval_result.action in ("clarify", "no_match"):
            state["retrieval_confidence"] = retrieval_result.confidence
            async for event in self._clarification_agent.run_async(ctx):
                yield event
            state["pipeline_trace"] = trace.build(action="clarify").to_dict()
            return

        # ---- Step 3: Filter Resolution ----
        yield _step_event("resolve_filters", StepStatus.STARTED)
        trace.start_step("resolve_filters")

        resolved_filters = resolve_filters(
            entities=classification.entities,
            explore_name=retrieval_result.explore,
        )
        retrieval_result.filters = resolved_filters

        trace.end_step(
            decision="proceed",
            input_summary={"raw_filters": classification.entities.filters},
            output_summary={"resolved": resolved_filters},
        )
        yield _step_event(
            "resolve_filters",
            StepStatus.COMPLETED,
            detail=f"filters={resolved_filters}",
        )

        # ---- Step 4: Pre-execution Validation ----
        yield _step_event("validate_query", StepStatus.STARTED)
        trace.start_step("validate_query")

        validation = validate_query(retrieval_result)

        trace.end_step(
            decision="proceed" if validation.valid else "blocked",
            input_summary={"explore": retrieval_result.explore},
            output_summary={
                "valid": validation.valid,
                "issues": validation.issues,
                "warnings": validation.warnings,
            },
        )

        if not validation.valid and validation.blocking:
            yield _step_event(
                "validate_query",
                StepStatus.BLOCKED,
                detail=f"BLOCKED: {validation.issues}",
            )
            # Emit blocking message as a text event
            blocking_text = (
                f"I found the right dataset ({retrieval_result.explore}) "
                f"but the query has issues that prevent safe execution:\n"
                + "\n".join(f"- {issue}" for issue in validation.issues)
                + "\n\nPlease try rephrasing your question."
            )
            yield _make_text_event(blocking_text)
            state["pipeline_trace"] = trace.build(action="blocked").to_dict()
            return

        yield _step_event("validate_query", StepStatus.COMPLETED, detail="valid=True")

        # ==============================================================
        # PHASE 2: EXECUTION (LLM-driven via query_agent)
        # ==============================================================

        # Inject retrieval context into session state
        augmented_prompt = build_augmented_prompt(
            model=retrieval_result.model,
            explore=retrieval_result.explore,
            dimensions=retrieval_result.dimensions,
            measures=retrieval_result.measures,
            filters=retrieval_result.filters,
            confidence=retrieval_result.confidence,
            fewshot_match=(
                retrieval_result.fewshot_matches[0]
                if retrieval_result.fewshot_matches
                else "none"
            ),
        )
        state["retrieval_result"] = {
            "model": retrieval_result.model,
            "explore": retrieval_result.explore,
            "dimensions": retrieval_result.dimensions,
            "measures": retrieval_result.measures,
            "filters": retrieval_result.filters,
            "confidence": retrieval_result.confidence,
        }
        state["augmented_prompt"] = augmented_prompt

        # Override the query_agent's instruction with the augmented prompt
        self._query_agent.instruction = augmented_prompt

        yield _step_event("query_execution", StepStatus.STARTED)
        trace.start_step("query_execution")

        async for event in self._query_agent.run_async(ctx):
            yield event

        trace.end_step(decision="proceed")
        trace.increment_llm_calls()  # at least 1 LLM call in query_agent
        trace.increment_mcp_calls(2)  # query_sql + query
        yield _step_event("query_execution", StepStatus.COMPLETED)

        # ==============================================================
        # PHASE 3: RESPONSE (LLM-driven via response_agent)
        # ==============================================================

        yield _step_event("format_response", StepStatus.STARTED)
        trace.start_step("format_response")

        async for event in self._response_agent.run_async(ctx):
            yield event

        trace.end_step(decision="proceed")
        trace.increment_llm_calls()
        yield _step_event("format_response", StepStatus.COMPLETED)

        # ---- Emit final trace ----
        pipeline_trace = trace.build(action="proceed")
        state["pipeline_trace"] = pipeline_trace.to_dict()

        yield _step_event(
            "pipeline",
            StepStatus.COMPLETED,
            detail=f"total={pipeline_trace.total_duration_ms:.0f}ms llm={pipeline_trace.llm_calls} mcp={pipeline_trace.mcp_calls}",
        )


# =====================================================================
# Helpers
# =====================================================================

def _get_user_query(ctx: InvocationContext) -> str:
    """Extract the user's query from the invocation context."""
    if ctx.user_content and ctx.user_content.parts:
        for part in ctx.user_content.parts:
            if part.text:
                return part.text
    return ""


def _get_history(ctx: InvocationContext) -> list[dict]:
    """Extract conversation history from session state."""
    return ctx.session.state.get("conversation_history", [])


def _step_event(
    step: str,
    status: StepStatus,
    detail: str = "",
) -> PipelineStepEvent:
    """Create a PipelineStepEvent for SSE streaming."""
    return PipelineStepEvent(step=step, status=status, detail=detail)


def _make_text_event(text: str) -> Event:
    """Create an ADK Event containing text content.

    Used for direct text responses (e.g., validation blocking messages)
    that bypass sub-agents.
    """
    return Event(
        author="cortex",
        content=Content(role="model", parts=[Part(text=text)]),
    )
