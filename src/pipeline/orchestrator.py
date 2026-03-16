"""CortexOrchestrator — full NL2SQL pipeline with SSE streaming.

Composition over inheritance: wraps the PoC's AgentOrchestrator (access_llm/chat.py),
does NOT subclass it. Phase 1 (pre-processing) and Phase 3 (post-processing)
are owned by CortexOrchestrator. Phase 2 (ReAct execution) delegates to the
PoC's AgentOrchestrator with an augmented prompt.

Three phases:
  Phase 1 — PRE-PROCESSING (1 LLM call):
    [Intent Classification + Entity Extraction] → [Retrieval (embedding + pgvector)]
    → [Explore Scoring] → [Filter Resolution]
  Phase 2 — REACT EXECUTION (LLM + Looker MCP):
    [Augmented Prompt → AgentOrchestrator → Looker MCP → BigQuery]
  Phase 3 — POST-PROCESSING (1 LLM call, concurrent with results emit):
    [Results Processing] → [Response Formatting + Follow-ups]

Key design decisions:
  - AsyncGenerator[SSEEvent] as the primary output contract
  - Every step emits events regardless of success/failure
  - PipelineTrace is assembled incrementally as steps complete
  - One orchestrator instance per server, not per request
  - Classifier model cached at __init__ — no per-request model lookups
  - Classifier entities passed directly to retrieval pipeline — single LLM extraction,
    not two separate calls. Saves ~300ms per query.
  - Follow-up generation fires concurrently with result emission
  - All sync calls (LLM invoke, retrieval) run in asyncio.to_thread to avoid
    blocking the event loop during SSE streaming

Cosmetic note:
  Steps 3-4 timing is cosmetic: scoring and filter resolution happen inside
  retrieve_with_graph_validation() during Step 2. Steps 3-4 re-emit the results
  as separate SSE events for the frontend's step visualization.
  Post-demo: break retrieval into composable functions.

Usage:
    orchestrator = CortexOrchestrator(react_agent, conversations)
    async for event in orchestrator.process_query("total spend?", "conv_123"):
        yield event.to_sse()
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, AsyncGenerator

from src.adapters.model_adapter import get_model
from src.retrieval.pipeline import (
    retrieve_with_graph_validation,
    get_top_explore,
    PipelineResult,
    _get_explore_desc_similarities,
)
from src.retrieval.vector import EntityExtractor, ExtractedEntities
from config.constants import EXPLORE_DESCRIPTIONS
from src.pipeline.prompts import (
    CLASSIFY_AND_EXTRACT_PROMPT,
    AUGMENTED_SYSTEM_PROMPT,
    FOLLOW_UP_PROMPT,
)

logger = logging.getLogger(__name__)


# ── SSE Event ────────────────────────────────────────────────────────

@dataclass
class SSEEvent:
    """A single Server-Sent Event."""
    event: str              # event type: step_start, step_complete, etc.
    data: dict[str, Any]    # JSON-serializable payload

    def to_sse(self) -> str:
        """Serialize to SSE wire format (single-line JSON per spec)."""
        json_data = json.dumps(self.data, default=str)
        return f"event: {self.event}\ndata: {json_data}\n\n"


# ── Pipeline Trace ───────────────────────────────────────────────────

@dataclass
class StepTrace:
    """Trace of a single pipeline step — stored for eval and debugging."""
    step_name: str
    step_number: int
    started_at: float
    ended_at: float = 0.0
    duration_ms: float = 0.0
    status: str = "pending"          # pending | active | complete | error | skipped
    input_summary: dict = field(default_factory=dict)
    output_summary: dict = field(default_factory=dict)
    decision: str = "pending"        # proceed | disambiguate | clarify | fallback | skip
    confidence: float | None = None
    error: str | None = None


@dataclass
class PipelineTrace:
    """Full pipeline trace for one query — stored for eval and debugging."""
    trace_id: str
    query: str
    conversation_id: str
    timestamp: str                    # ISO 8601
    total_duration_ms: float = 0.0
    llm_calls: int = 0
    mcp_calls: int = 0
    overall_confidence: float = 0.0
    action: str = "pending"           # proceed | disambiguate | clarify | fallback
    steps: list[StepTrace] = field(default_factory=list)
    result: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Conversation Store ───────────────────────────────────────────────

@dataclass
class ConversationContext:
    """Context carried across turns in a conversation."""
    conversation_id: str
    history: list[dict]                             # [{role, content}]
    last_retrieval_result: PipelineResult | None = None
    last_explore: str = ""
    last_filters: dict = field(default_factory=dict)
    turn_count: int = 0


class ConversationStore:
    """In-memory conversation store. Replace with Redis for multi-pod."""

    def __init__(self, max_turns: int = 20):
        self._store: dict[str, ConversationContext] = {}
        self._max_turns = max_turns

    def get_or_create(self, conversation_id: str | None) -> ConversationContext:
        if conversation_id and conversation_id in self._store:
            return self._store[conversation_id]
        new_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
        ctx = ConversationContext(conversation_id=new_id, history=[])
        self._store[new_id] = ctx
        return ctx

    def update(self, ctx: ConversationContext, query: str, answer: str) -> None:
        ctx.history.append({"role": "user", "content": query})
        ctx.history.append({"role": "assistant", "content": answer})
        ctx.turn_count += 1
        if len(ctx.history) > self._max_turns * 2:
            ctx.history = ctx.history[-(self._max_turns * 2):]


# ── Orchestrator ─────────────────────────────────────────────────────

class CortexOrchestrator:
    """Full NL2SQL pipeline with SSE streaming.

    Usage:
        orchestrator = CortexOrchestrator(react_agent, conversations)
        async for event in orchestrator.process_query("total spend?", "conv_123"):
            yield event.to_sse()
    """

    TOTAL_STEPS = 7

    def __init__(
        self,
        react_agent,                              # AgentOrchestrator from chat.py
        conversations: ConversationStore | None = None,
        classifier_model_idx: str = "3",          # Gemini 2.5 Flash
        model_name: str = "proj-d-lumi-gpt",      # Default Looker model
    ):
        self.react_agent = react_agent
        self.conversations = conversations or ConversationStore()
        self.model_name = model_name
        self._trace_store: dict[str, PipelineTrace] = {}

        # ── Singleton model clients — created once, reused across ALL requests ──
        # get_model() hits SafeChain Config.from_env() on first call, then caches.
        # But model() may create a new wrapper each time. By caching here, we ensure
        # zero per-request initialization overhead.
        self._classifier = get_model(classifier_model_idx)

        # Singleton EntityExtractor — holds both LLM + embedding clients.
        # Without this, every request creates new model clients (~50ms waste).
        self._extractor = EntityExtractor()

    async def warm_up(self) -> None:
        """Pre-warm caches so the first request doesn't pay cold-start penalties.

        Triggers:
          - Explore description embedding cache (one-time ~200ms)
          - pgvector connection pool warm-up

        Call this from the server startup handler AFTER __init__.
        """
        logger.info("Pre-warming explore description embeddings...")
        # _get_explore_desc_similarities triggers the one-time cache.
        # Run in thread to avoid blocking the event loop.
        await asyncio.to_thread(
            _get_explore_desc_similarities, "warm-up query", self._extractor
        )
        logger.info("Pre-warm complete — first request will be fast")

    async def process_query(
        self,
        query: str,
        conversation_id: str | None = None,
        view_mode: str = "engineering",
    ) -> AsyncGenerator[SSEEvent, None]:
        """Main entry point. Streams SSE events as the pipeline executes."""
        trace_id = str(uuid.uuid4())
        ctx = self.conversations.get_or_create(conversation_id)
        trace = PipelineTrace(
            trace_id=trace_id,
            query=query,
            conversation_id=ctx.conversation_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        pipeline_start = time.monotonic()
        llm_calls = 0
        mcp_calls = 0

        try:
            # ── PHASE 1: PRE-PROCESSING ──────────────────────────

            # Step 1: Intent Classification + Entity Extraction
            step1_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "intent_classification",
                "step_number": 1,
                "total_steps": self.TOTAL_STEPS,
                "message": "Analyzing your question...",
                "timestamp": step1_start,
            })

            classification = await self._classify_intent(query, ctx)
            llm_calls += 1
            step1_duration = (time.monotonic() - step1_start) * 1000

            step1_trace = StepTrace(
                step_name="intent_classification", step_number=1,
                started_at=step1_start, ended_at=time.monotonic(),
                duration_ms=step1_duration, status="complete",
                input_summary={"query": query[:200]},
                output_summary=classification,
                decision="proceed",
                confidence=classification.get("confidence", 0),
            )
            trace.steps.append(step1_trace)

            yield SSEEvent("step_complete", {
                "step": "intent_classification",
                "step_number": 1,
                "duration_ms": round(step1_duration),
                "message": f"Identified as {classification.get('intent', 'unknown')}",
                "detail": classification,
            })

            # Short-circuit: out of scope
            if classification.get("intent") == "out_of_scope":
                trace.action = "out_of_scope"
                trace.total_duration_ms = (time.monotonic() - pipeline_start) * 1000
                self._trace_store[trace_id] = trace
                yield SSEEvent("done", {
                    "trace_id": trace_id,
                    "message": "This question is outside what I can answer with your Finance data.",
                    "total_duration_ms": round(trace.total_duration_ms),
                    "conversation_id": ctx.conversation_id,
                })
                return

            # Map classifier entities → ExtractedEntities for retrieval pipeline.
            # This eliminates the second LLM call (~300ms saved per query).
            # The classifier already extracts {metrics, dimensions, filters, time_range}
            # in the same format the retrieval extractor would produce.
            entities_data = classification.get("entities", {})
            pre_extracted = ExtractedEntities(
                measures=entities_data.get("metrics", []),
                dimensions=entities_data.get("dimensions", []),
                time_range=entities_data.get("time_range"),
                filters=entities_data.get("filters", []),
            )

            # Step 2: Retrieval (embedding + pgvector + graph scoring)
            step2_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "retrieval",
                "step_number": 2,
                "total_steps": self.TOTAL_STEPS,
                "message": "Searching for matching data fields...",
            })

            # CRITICAL: run in thread — this is synchronous (embedding + pgvector + graph)
            # and would block the event loop, freezing all concurrent SSE streams.
            pipeline_result = await asyncio.to_thread(
                retrieve_with_graph_validation, query, 5,
                pre_extracted=pre_extracted,
                extractor=self._extractor,
            )
            step2_duration = (time.monotonic() - step2_start) * 1000

            if view_mode == "engineering":
                yield SSEEvent("step_progress", {
                    "step": "retrieval",
                    "message": f"Found {len(pipeline_result.explores)} candidate explores",
                    "detail": {
                        "explore_count": len(pipeline_result.explores),
                        "action": pipeline_result.action,
                    },
                })

            step2_trace = StepTrace(
                step_name="retrieval", step_number=2,
                started_at=step2_start, ended_at=time.monotonic(),
                duration_ms=step2_duration, status="complete",
                input_summary={"query": query[:200]},
                output_summary={
                    "explore_count": len(pipeline_result.explores),
                    "action": pipeline_result.action,
                    "confidence": pipeline_result.confidence,
                },
                decision=pipeline_result.action,
                confidence=pipeline_result.confidence,
            )
            trace.steps.append(step2_trace)

            yield SSEEvent("step_complete", {
                "step": "retrieval",
                "step_number": 2,
                "duration_ms": round(step2_duration),
                "message": f"Retrieved {len(pipeline_result.explores)} candidate explores",
                "detail": {
                    "explore_count": len(pipeline_result.explores),
                    "action": pipeline_result.action,
                },
            })

            # Handle clarify / no_match
            if pipeline_result.action in ("clarify", "no_match"):
                trace.action = pipeline_result.action
                trace.total_duration_ms = (time.monotonic() - pipeline_start) * 1000
                self._trace_store[trace_id] = trace
                yield SSEEvent("clarify", {
                    "step": "retrieval",
                    "message": "I couldn't find matching data fields. Could you rephrase your question?",
                    "reason": pipeline_result.clarify_reason,
                })
                yield SSEEvent("done", {
                    "trace_id": trace_id,
                    "total_duration_ms": round(trace.total_duration_ms),
                    "conversation_id": ctx.conversation_id,
                })
                return

            # Step 3: Explore Scoring (already computed in retrieval — emit results)
            step3_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "explore_scoring",
                "step_number": 3,
                "total_steps": self.TOTAL_STEPS,
                "message": "Scoring candidate data sources...",
            })

            top_explore_data = get_top_explore(pipeline_result)
            step3_duration = (time.monotonic() - step3_start) * 1000

            explore_list = []
            for i, exp in enumerate(pipeline_result.explores[:5]):
                explore_list.append({
                    "name": exp.name,
                    "score": exp.score,
                    "confidence": exp.confidence,
                    "coverage": exp.coverage,
                    "matched_entities": exp.supported_entities,
                    "is_winner": i == 0,
                })

            yield SSEEvent("explore_scored", {
                "step": "explore_scoring",
                "explores": explore_list,
                "winner": pipeline_result.explores[0].name if pipeline_result.explores else None,
                "confidence": pipeline_result.confidence,
                "is_near_miss": pipeline_result.explores[0].is_near_miss if pipeline_result.explores else False,
            })

            # Handle disambiguation
            if pipeline_result.action == "disambiguate":
                options = []
                for exp_info in explore_list[:2]:
                    options.append({
                        "explore": exp_info["name"],
                        "description": EXPLORE_DESCRIPTIONS.get(exp_info["name"], ""),
                        "confidence": exp_info["confidence"],
                    })
                trace.action = "disambiguate"
                trace.total_duration_ms = (time.monotonic() - pipeline_start) * 1000
                self._trace_store[trace_id] = trace
                yield SSEEvent("disambiguate", {
                    "step": "explore_scoring",
                    "message": "I found two equally relevant data sources. Which one matches your question?",
                    "options": options,
                })
                yield SSEEvent("done", {
                    "trace_id": trace_id,
                    "total_duration_ms": round(trace.total_duration_ms),
                    "conversation_id": ctx.conversation_id,
                    "action": "disambiguate",
                })
                return

            step3_trace = StepTrace(
                step_name="explore_scoring", step_number=3,
                started_at=step3_start, ended_at=time.monotonic(),
                duration_ms=step3_duration, status="complete",
                output_summary={
                    "selected_explore": top_explore_data.get("top_explore_name"),
                    "confidence": pipeline_result.confidence,
                },
                decision="proceed",
                confidence=pipeline_result.confidence,
            )
            trace.steps.append(step3_trace)

            yield SSEEvent("step_complete", {
                "step": "explore_scoring",
                "step_number": 3,
                "duration_ms": round(step3_duration),
                "message": f"Selected {top_explore_data.get('top_explore_name')} "
                           f"({pipeline_result.confidence:.0%} confidence)",
                "detail": top_explore_data,
            })

            # Step 4: Filter Resolution (already done in retrieval — emit detail)
            step4_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "filter_resolution",
                "step_number": 4,
                "total_steps": self.TOTAL_STEPS,
                "message": "Resolving filter values...",
            })

            filters_data = top_explore_data.get("filters", {})
            unresolved = top_explore_data.get("unresolved_filters", [])
            step4_duration = (time.monotonic() - step4_start) * 1000

            filter_detail: dict[str, Any] = {
                "resolved": filters_data,
                "unresolved": unresolved,
                "filter_count": len(filters_data),
            }
            if pipeline_result.filters:
                filter_detail["resolved_detail"] = [
                    {
                        "field": f.field_name,
                        "user_said": f.original_value,
                        "resolved_to": f.value,
                        "confidence": f.confidence,
                        "pass": f.resolution_pass,
                    }
                    for f in pipeline_result.filters.resolved_filters
                ]
                filter_detail["mandatory_detail"] = [
                    {
                        "field": f.field_name,
                        "value": f.value,
                        "reason": "auto_injected_partition" if f.resolution_pass == 0 else "user",
                    }
                    for f in pipeline_result.filters.mandatory_filters
                ]

            step4_trace = StepTrace(
                step_name="filter_resolution", step_number=4,
                started_at=step4_start, ended_at=time.monotonic(),
                duration_ms=step4_duration, status="complete",
                output_summary=filter_detail,
                decision="proceed",
            )
            trace.steps.append(step4_trace)

            yield SSEEvent("step_complete", {
                "step": "filter_resolution",
                "step_number": 4,
                "duration_ms": round(step4_duration),
                "message": f"Resolved {len(filters_data)} filters",
                "detail": filter_detail,
            })

            # Save retrieval context for follow-ups
            ctx.last_retrieval_result = pipeline_result
            ctx.last_explore = top_explore_data.get("top_explore_name", "")
            ctx.last_filters = filters_data

            # ── PHASE 2: REACT EXECUTION ─────────────────────────

            # Step 5: SQL Generation via Looker MCP
            step5_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "sql_generation",
                "step_number": 5,
                "total_steps": self.TOTAL_STEPS,
                "message": "Generating SQL query...",
            })

            # Build augmented prompt with pre-selected fields
            explore_name = top_explore_data.get("top_explore_name", "")
            measures, dimensions = self._extract_fields_from_entities(
                pipeline_result.entities or [], explore_name
            )

            augmented_prompt = self._build_augmented_prompt(
                explore_name=explore_name,
                confidence=pipeline_result.confidence,
                measures=measures,
                dimensions=dimensions,
                filters=filters_data,
            )

            yield SSEEvent("step_progress", {
                "step": "sql_generation",
                "message": "Calling Looker MCP with pre-selected fields...",
                "detail": {
                    "model": self.model_name,
                    "explore": explore_name,
                    "measures": measures,
                    "dimensions": dimensions,
                    "filters": filters_data,
                },
            })

            messages = [
                {"role": "system", "content": augmented_prompt},
                *ctx.history[-10:],  # last 5 turns
                {"role": "user", "content": query},
            ]

            react_result = await self.react_agent.run(messages)
            llm_calls += 1
            mcp_calls += 1
            step5_duration = (time.monotonic() - step5_start) * 1000

            raw_content = react_result.get("content", "")
            sql = self._extract_sql(raw_content)

            if sql:
                yield SSEEvent("sql_generated", {
                    "step": "sql_generation",
                    "sql": sql,
                    "explore": explore_name,
                    "model": self.model_name,
                })

            step5_trace = StepTrace(
                step_name="sql_generation", step_number=5,
                started_at=step5_start, ended_at=time.monotonic(),
                duration_ms=step5_duration, status="complete",
                output_summary={"sql_length": len(sql) if sql else 0},
                decision="proceed",
            )
            trace.steps.append(step5_trace)

            yield SSEEvent("step_complete", {
                "step": "sql_generation",
                "step_number": 5,
                "duration_ms": round(step5_duration),
                "message": "SQL generated and executed",
                "detail": {
                    "llm_iterations": 1,
                    "mcp_tool_calls": 1,
                },
            })

            # ── PHASE 3: POST-PROCESSING ─────────────────────────
            # Latency optimization: extract answer immediately (regex, <1ms),
            # then fire follow-up generation concurrently with results processing.
            # Follow-ups need the answer but NOT the parsed results — independent.

            answer = self._extract_answer(raw_content)

            # Fire follow-up generation NOW — runs concurrently with Step 6.
            # This LLM call (~300ms) overlaps with result parsing + event emission.
            follow_up_task = asyncio.create_task(
                self._generate_follow_ups(query, answer, explore_name, ctx)
            )

            # Step 6: Results Processing
            step6_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "results_processing",
                "step_number": 6,
                "total_steps": self.TOTAL_STEPS,
                "message": "Processing query results...",
            })

            parsed_results = self._parse_results(raw_content)
            step6_duration = (time.monotonic() - step6_start) * 1000

            row_count = parsed_results.get("row_count", 0)
            yield SSEEvent("results", {
                "step": "results_processing",
                "columns": parsed_results.get("columns", []),
                "rows": parsed_results.get("rows", [])[:500],
                "row_count": row_count,
                "truncated": row_count > 500,
            })

            step6_trace = StepTrace(
                step_name="results_processing", step_number=6,
                started_at=step6_start, ended_at=time.monotonic(),
                duration_ms=step6_duration, status="complete",
                output_summary={"row_count": row_count},
                decision="proceed",
            )
            trace.steps.append(step6_trace)

            yield SSEEvent("step_complete", {
                "step": "results_processing",
                "step_number": 6,
                "duration_ms": round(step6_duration),
                "message": f"Processed {row_count} rows",
            })

            # Step 7: Response Formatting + Follow-ups
            step7_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "response_formatting",
                "step_number": 7,
                "total_steps": self.TOTAL_STEPS,
                "message": "Formatting response...",
            })

            # Await the follow-up task (already running since before Step 6)
            follow_ups = await follow_up_task
            llm_calls += 1
            step7_duration = (time.monotonic() - step7_start) * 1000

            step7_trace = StepTrace(
                step_name="response_formatting", step_number=7,
                started_at=step7_start, ended_at=time.monotonic(),
                duration_ms=step7_duration, status="complete",
                output_summary={
                    "answer_length": len(answer),
                    "follow_up_count": len(follow_ups),
                },
                decision="proceed",
            )
            trace.steps.append(step7_trace)

            yield SSEEvent("step_complete", {
                "step": "response_formatting",
                "step_number": 7,
                "duration_ms": round(step7_duration),
                "message": "Response ready",
                "detail": {
                    "answer": answer,
                    "follow_ups": follow_ups,
                },
            })

            yield SSEEvent("follow_ups", {
                "suggestions": follow_ups,
            })

            # ── FINALIZE ─────────────────────────────────────────

            total_duration = (time.monotonic() - pipeline_start) * 1000
            trace.total_duration_ms = total_duration
            trace.llm_calls = llm_calls
            trace.mcp_calls = mcp_calls
            trace.overall_confidence = pipeline_result.confidence
            trace.action = "proceed"
            trace.result = {
                "answer": answer,
                "sql": sql,
                "row_count": row_count,
                "follow_ups": follow_ups,
            }

            self._trace_store[trace_id] = trace
            self.conversations.update(ctx, query, answer)

            yield SSEEvent("done", {
                "trace_id": trace_id,
                "total_duration_ms": round(total_duration),
                "llm_calls": llm_calls,
                "mcp_calls": mcp_calls,
                "overall_confidence": pipeline_result.confidence,
                "conversation_id": ctx.conversation_id,
            })

        except Exception as e:
            logger.exception("Pipeline error for query: %s", query)
            yield SSEEvent("error", {
                "step": "pipeline",
                "message": str(e),
                "recoverable": False,
                "trace_id": trace_id,
            })
            yield SSEEvent("done", {
                "trace_id": trace_id,
                "total_duration_ms": round((time.monotonic() - pipeline_start) * 1000),
                "conversation_id": ctx.conversation_id,
                "error": str(e),
            })

    def get_trace(self, trace_id: str) -> PipelineTrace | None:
        """Retrieve a stored trace by ID."""
        return self._trace_store.get(trace_id)

    # ── Private Methods ──────────────────────────────────────────

    async def _classify_intent(
        self, query: str, ctx: ConversationContext
    ) -> dict:
        """Classify intent and extract entities using Gemini Flash."""
        explore_desc_text = "\n".join(
            f"- {name}: {desc}" for name, desc in EXPLORE_DESCRIPTIONS.items()
        )
        history_text = ""
        if ctx.history:
            recent = ctx.history[-6:]  # last 3 turns
            history_text = "\n".join(
                f"{msg['role']}: {msg['content'][:200]}" for msg in recent
            )
        else:
            history_text = "(No previous conversation)"

        prompt = CLASSIFY_AND_EXTRACT_PROMPT.format(
            explore_descriptions=explore_desc_text,
            conversation_history=history_text,
            query=query,
        )

        try:
            # CRITICAL: classifier.invoke() is synchronous — run in thread
            # to avoid blocking the event loop during SSE streaming.
            response = await asyncio.to_thread(self._classifier.invoke, prompt)
            json_str = response.content if hasattr(response, "content") else str(response)
            cleaned = self._extract_json_block(json_str)
            return json.loads(cleaned)
        except Exception as e:
            logger.warning("Intent classification failed: %s — using fallback", e)
            return {
                "intent": "data_query",
                "confidence": 0.5,
                "reasoning": f"Classification fallback (error: {e})",
                "entities": {"metrics": [], "dimensions": [], "filters": [], "time_range": None},
                "follow_up_type": None,
            }

    def _build_augmented_prompt(
        self,
        explore_name: str,
        confidence: float,
        measures: list[str],
        dimensions: list[str],
        filters: dict[str, str],
    ) -> str:
        """Build the augmented system prompt for the ReAct agent."""
        measures_list = "\n".join(f"  - {m}" for m in measures) or "  (none)"
        dimensions_list = "\n".join(f"  - {d}" for d in dimensions) or "  (none)"
        filters_list = "\n".join(
            f"  - {k}: {v}" for k, v in filters.items()
        ) or "  (none)"

        return AUGMENTED_SYSTEM_PROMPT.format(
            model_name=self.model_name,
            explore_name=explore_name,
            confidence=confidence,
            measures_list=measures_list,
            dimensions_list=dimensions_list,
            filters_list=filters_list,
            measures_json=json.dumps(measures),
            dimensions_json=json.dumps(dimensions),
            filters_json=json.dumps(filters),
            limit=500,
        )

    def _extract_fields_from_entities(
        self,
        entities: list[dict[str, Any]],
        explore_name: str,
    ) -> tuple[list[str], list[str]]:
        """Extract measure/dimension field keys from scored entities for an explore.

        BUG FIX: The explore field in candidates is comma-separated
        (e.g. "finance_cardmember_360,finance_merchant_profitability").
        Must split and do exact match — substring match would cause
        "finance_card" to match "finance_cardmember_360".
        """
        measures = []
        dimensions = []

        for entity in entities:
            entity_type = entity.get("type", "")
            if entity_type not in ("measure", "dimension"):
                continue

            candidates = entity.get("candidates", [])
            for candidate in candidates:
                candidate_explores_str = candidate.get("explore", "")
                # Split comma-separated explore names and exact-match
                candidate_explores = [
                    e.strip() for e in candidate_explores_str.split(",") if e.strip()
                ]
                if explore_name in candidate_explores:
                    field_key = candidate.get("field_key", "")
                    if field_key:
                        if entity_type == "measure":
                            measures.append(field_key)
                        else:
                            dimensions.append(field_key)
                    break  # Take the first matching candidate for this explore

        return measures, dimensions

    def _extract_sql(self, raw_content: str) -> str:
        """Extract SQL from the raw LLM response."""
        # Look for SQL in markdown code blocks
        sql_match = re.search(
            r"```(?:sql)?\s*\n(.*?)\n```",
            raw_content,
            re.DOTALL | re.IGNORECASE,
        )
        if sql_match:
            return sql_match.group(1).strip()

        # Look for SELECT statement directly
        select_match = re.search(
            r"(SELECT\s+.*?(?:;|\Z))",
            raw_content,
            re.DOTALL | re.IGNORECASE,
        )
        if select_match:
            return select_match.group(1).strip()

        return ""

    def _parse_results(self, raw_content: str) -> dict:
        """Parse query results from LLM response into structured data.

        The MCP tool returns results as formatted text. We extract what we can.
        """
        # Try to find a table or JSON results block in the response
        rows = []
        columns = []

        # Look for JSON data
        json_match = re.search(r"\[[\s\S]*?\{[\s\S]*?\}[\s\S]*?\]", raw_content)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if isinstance(data, list) and data:
                    columns = [
                        {"name": k, "type": "string", "label": k.replace("_", " ").title()}
                        for k in data[0].keys()
                    ]
                    rows = data
                    return {"columns": columns, "rows": rows, "row_count": len(rows)}
            except json.JSONDecodeError:
                pass

        # Fallback: treat the raw content as the result
        return {
            "columns": [{"name": "result", "type": "string", "label": "Result"}],
            "rows": [{"result": raw_content[:2000]}],
            "row_count": 1,
        }

    def _extract_answer(self, raw_content: str) -> str:
        """Extract the natural language answer from LLM response.

        Removes SQL blocks and tool call artifacts, keeps the human-readable part.
        """
        # Remove code blocks
        cleaned = re.sub(r"```(?:sql|json)?.*?```", "", raw_content, flags=re.DOTALL)
        # Remove tool call references
        cleaned = re.sub(r"\[Tool.*?\]", "", cleaned)
        # Clean up whitespace
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned or raw_content[:500]

    async def _generate_follow_ups(
        self,
        query: str,
        answer: str,
        explore_name: str,
        ctx: ConversationContext,
    ) -> list[str]:
        """Generate 2-3 follow-up suggestions using Gemini Flash."""
        try:
            prompt = FOLLOW_UP_PROMPT.format(
                query=query,
                answer=answer[:500],
                explore_name=explore_name,
                available_dimensions="(see explore description)",
                available_measures="(see explore description)",
            )
            # CRITICAL: run in thread — same sync invoke issue.
            response = await asyncio.to_thread(self._classifier.invoke, prompt)
            json_str = response.content if hasattr(response, "content") else str(response)
            cleaned = self._extract_json_block(json_str)
            suggestions = json.loads(cleaned)
            if isinstance(suggestions, list):
                return suggestions[:3]
        except Exception as e:
            logger.warning("Follow-up generation failed: %s", e)

        # Fallback suggestions
        return [
            f"Break that down by another dimension",
            f"Show the trend over time",
            f"Compare across segments",
        ]

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """Extract JSON from potential markdown fences."""
        text = text.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                candidate = part.strip()
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{") or candidate.startswith("["):
                    return candidate

        start = text.find("{")
        bracket_start = text.find("[")
        if bracket_start != -1 and (start == -1 or bracket_start < start):
            start = bracket_start
            end = text.rfind("]")
        else:
            end = text.rfind("}")

        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
        return text
