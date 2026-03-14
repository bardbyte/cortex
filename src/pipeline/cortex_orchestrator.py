"""CortexOrchestrator -- the 3-phase pipeline integration layer.

Wraps the existing AgentOrchestrator (from access_llm/chat.py) with
pre-processing (hybrid retrieval) and post-processing (trace + formatting).

Composition over inheritance:
  - Does NOT subclass AgentOrchestrator
  - Wraps it: Phase 1 prepares, Phase 2 delegates, Phase 3 post-processes
  - If Phase 1 fails, falls through to raw AgentOrchestrator behavior

Entry points:
  run()            -- returns dict matching CortexResponse shape
  run_streaming()  -- async generator yielding StreamEvent dicts

Position in the system:
  CLI (cortex_cli.py)  --\
                          +--> CortexOrchestrator.run()
  API (server.py)      --/         |
                                   +---> Phase 1: _classify, _retrieve, _resolve_filters
                                   +---> Phase 2: AgentOrchestrator.run() (SafeChain + MCP)
                                   +---> Phase 3: _build_response
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Callable

from src.pipeline.trace import TraceBuilder, PipelineTrace
from src.pipeline.errors import (
    CortexError,
    ClassificationError,
    RetrievalError,
    PipelineTimeoutError,
)
from src.retrieval.models import RetrievalResult
from src.retrieval.orchestrator import RetrievalOrchestrator

logger = logging.getLogger(__name__)

# ---- Configuration --------------------------------------------------------

TOTAL_TIMEOUT_MS = 10_000       # 10 second total budget
CLASSIFICATION_TIMEOUT_MS = 2_000
REACT_TIMEOUT_MS = 5_000
MIN_CLASSIFICATION_CONFIDENCE = 0.70
MAX_CONVERSATION_HISTORY = 20
TRACE_STORE_MAX = 1000          # Max traces held in memory
TRACE_STORE_EVICT = 500         # Evict this many when max reached


# ---- Prompt templates (imported from prompts.py) ---------------------------
from src.pipeline.prompts import (
    CLASSIFY_AND_EXTRACT_PROMPT as CLASSIFY_PROMPT,
    build_augmented_prompt as _build_augmented_prompt_fn,
)


class CortexOrchestrator:
    """Three-phase pipeline: retrieve -> execute -> format.

    Thread safety: One instance per server. The _trace_store dict is not
    thread-safe but that is fine -- FastAPI runs in a single event loop
    and we only have one writer (this class) per request.
    """

    def __init__(
        self,
        agent_orchestrator: Any,               # AgentOrchestrator from chat.py
        retrieval: RetrievalOrchestrator,
        classifier_agent: Any,                 # MCPToolAgent (no tools, for classification)
        embed_fn: Callable[[str], list[float]],
        taxonomy_terms: list[str] | None = None,
    ):
        self.agent = agent_orchestrator
        self.retrieval = retrieval
        self.classifier = classifier_agent
        self.embed_fn = embed_fn
        self.taxonomy_terms = taxonomy_terms or []
        self.last_retrieval_result: RetrievalResult | None = None
        self._trace_store: dict[str, PipelineTrace] = {}

    # ==== Public interface ==================================================

    async def run(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
        debug: bool = False,
        last_retrieval_context: dict | None = None,
    ) -> dict:
        """Main entry point. Returns a dict matching CortexResponse shape.

        Args:
            query: User's natural language question.
            conversation_history: Previous messages [{role, content}].
            debug: If True, include full trace in response.
            last_retrieval_context: Previous turn's retrieval result for follow-ups.

        Returns:
            Dict with keys: answer, data, sql, trace, follow_ups,
            retrieval_context, error, metadata.
        """
        trace = TraceBuilder(query)
        history = (conversation_history or [])[-MAX_CONVERSATION_HISTORY:]
        pipeline_start = time.monotonic()

        try:
            # ==== PHASE 1: PRE-PROCESSING ====
            classification = await self._classify(query, history, trace)

            if classification["intent"] == "out_of_scope":
                return self._out_of_scope(query, classification, trace)

            if classification["intent"] in ("schema_browse", "saved_content"):
                return await self._passthrough(query, history, trace)

            # Handle follow-ups with previous context
            if classification["intent"] == "follow_up" and last_retrieval_context:
                retrieval_result = self._handle_follow_up(
                    classification, last_retrieval_context, trace
                )
            else:
                retrieval_result = self._retrieve(
                    classification["entities"], trace
                )

            if retrieval_result.action == "clarify":
                return self._clarify_response(query, retrieval_result, trace)

            if retrieval_result.action == "disambiguate":
                return self._disambiguate_response(query, retrieval_result, trace)

            # Filter resolution
            resolved_filters = self._resolve_filters(
                classification["entities"], retrieval_result, trace
            )
            retrieval_result.filters = resolved_filters

            # Check time budget before Phase 2
            elapsed = (time.monotonic() - pipeline_start) * 1000
            if elapsed > TOTAL_TIMEOUT_MS * 0.6:
                logger.warning("Phase 1 took %.0fms, approaching budget", elapsed)

            # ==== PHASE 2: REACT EXECUTION ====
            augmented_prompt = self._build_prompt(retrieval_result)
            messages = [
                {"role": "system", "content": augmented_prompt},
                *history,
                {"role": "user", "content": query},
            ]

            trace.start_step("react_execution")
            react_result = await asyncio.wait_for(
                self.agent.run(messages),
                timeout=REACT_TIMEOUT_MS / 1000,
            )
            trace.end_step(
                decision="proceed",
                output_summary={
                    "content_length": len(react_result.get("content", "")),
                },
            )
            trace.increment_llm_calls(2)  # typical: 1 tool call + 1 format
            trace.increment_mcp_calls(1)  # 1 query-sql call

            # ==== PHASE 3: POST-PROCESSING ====
            self.last_retrieval_result = retrieval_result
            return self._build_response(
                react_result, retrieval_result, trace, debug
            )

        except asyncio.TimeoutError:
            trace.end_step(
                decision="timeout",
                error="Pipeline timeout exceeded",
            )
            return self._error_response(
                query, "Query took too long. Try a simpler question.",
                trace, step="timeout"
            )

        except CortexError as e:
            if e.recoverable:
                return await self._fallback(query, history, trace, str(e))
            return self._error_response(query, str(e), trace, step=e.step)

        except Exception as e:
            logger.exception("Unexpected error in CortexOrchestrator.run()")
            return await self._fallback(query, history, trace, str(e))

    async def run_streaming(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
        last_retrieval_context: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming entry point. Yields dicts matching StreamEvent shape.

        Same pipeline as run(), but yields step_start/step_complete events
        as each phase executes. The frontend renders these as a progress bar.

        Yields:
            Dicts with keys: event_type, step, progress, message, duration_ms,
            result, answer (on final event).
        """
        trace = TraceBuilder(query)
        history = (conversation_history or [])[-MAX_CONVERSATION_HISTORY:]

        try:
            # ---- Intent Classification ----
            yield _stream_event("step_start", "intent_classification", 0.05,
                                message="Understanding your question...")

            classification = await self._classify(query, history, trace)

            yield _stream_event("step_complete", "intent_classification", 0.15,
                                duration_ms=trace._steps[-1].duration_ms if trace._steps else 0,
                                result={"intent": classification["intent"],
                                        "confidence": classification["confidence"]})

            if classification["intent"] == "out_of_scope":
                resp = self._out_of_scope(query, classification, trace)
                yield _stream_event("answer", progress=1.0, answer=resp)
                return

            # ---- Retrieval ----
            yield _stream_event("step_start", "retrieval", 0.20,
                                message="Finding matching data fields...")

            if classification["intent"] == "follow_up" and last_retrieval_context:
                retrieval_result = self._handle_follow_up(
                    classification, last_retrieval_context, trace
                )
            else:
                retrieval_result = self._retrieve(classification["entities"], trace)

            yield _stream_event("step_complete", "retrieval", 0.35,
                                duration_ms=trace._steps[-1].duration_ms if trace._steps else 0,
                                result={"model": retrieval_result.model,
                                        "explore": retrieval_result.explore,
                                        "action": retrieval_result.action,
                                        "confidence": retrieval_result.confidence})

            if retrieval_result.action in ("clarify", "disambiguate"):
                resp = (self._clarify_response(query, retrieval_result, trace)
                        if retrieval_result.action == "clarify"
                        else self._disambiguate_response(query, retrieval_result, trace))
                yield _stream_event("answer", progress=1.0, answer=resp)
                return

            # ---- Filter Resolution ----
            yield _stream_event("step_start", "filter_resolution", 0.40,
                                message="Resolving filter values...")

            resolved_filters = self._resolve_filters(
                classification["entities"], retrieval_result, trace
            )
            retrieval_result.filters = resolved_filters

            yield _stream_event("step_complete", "filter_resolution", 0.45,
                                duration_ms=trace._steps[-1].duration_ms if trace._steps else 0,
                                result={"filters": resolved_filters})

            # ---- ReAct Execution ----
            yield _stream_event("step_start", "react_execution", 0.55,
                                message="Querying Looker for data...")

            augmented_prompt = self._build_prompt(retrieval_result)
            messages = [
                {"role": "system", "content": augmented_prompt},
                *history,
                {"role": "user", "content": query},
            ]

            trace.start_step("react_execution")
            react_result = await self.agent.run(messages)
            trace.end_step(decision="proceed")
            trace.increment_llm_calls(2)
            trace.increment_mcp_calls(1)

            yield _stream_event("step_complete", "react_execution", 0.80,
                                duration_ms=trace._steps[-1].duration_ms if trace._steps else 0,
                                result={"content_length": len(react_result.get("content", ""))})

            # ---- Response Formatting ----
            yield _stream_event("step_start", "response_formatting", 0.85,
                                message="Formatting your answer...")

            self.last_retrieval_result = retrieval_result
            response = self._build_response(react_result, retrieval_result, trace, False)

            yield _stream_event("step_complete", "response_formatting", 0.95)
            yield _stream_event("answer", progress=1.0, answer=response)

        except Exception as e:
            logger.exception("Streaming pipeline error")
            yield _stream_event("error", message=str(e))

    def get_trace(self, trace_id: str) -> PipelineTrace | None:
        """Retrieve a stored trace by ID."""
        return self._trace_store.get(trace_id)

    # ==== Phase 1 internals =================================================

    async def _classify(
        self, query: str, history: list[dict], trace: TraceBuilder,
    ) -> dict:
        """Intent classification via single LLM call."""
        trace.start_step("intent_classification")

        previous_context = ""
        if history:
            recent = history[-4:]  # last 2 exchanges
            previous_context = "\n".join(
                f"{m['role']}: {m['content']}" for m in recent
            )

        prompt = CLASSIFY_PROMPT.format(
            taxonomy_terms="\n".join(f"- {t}" for t in self.taxonomy_terms[:50]),
            previous_context=previous_context or "(first message in conversation)",
            query=query,
        )

        try:
            from langchain_core.messages import HumanMessage
            result = await asyncio.wait_for(
                self.classifier.ainvoke([HumanMessage(content=prompt)]),
                timeout=CLASSIFICATION_TIMEOUT_MS / 1000,
            )

            content = result.content if hasattr(result, "content") else str(result)
            classification = self._parse_classification(content)
            trace.increment_llm_calls(1)

            trace.end_step(
                decision=(
                    "proceed"
                    if classification["confidence"] >= MIN_CLASSIFICATION_CONFIDENCE
                    else "low_confidence"
                ),
                confidence=classification["confidence"],
                input_summary={"query": query},
                output_summary={
                    "intent": classification["intent"],
                    "confidence": classification["confidence"],
                },
            )

            if classification["confidence"] < MIN_CLASSIFICATION_CONFIDENCE:
                raise ClassificationError(
                    f"Low confidence: {classification['confidence']:.2f}",
                    confidence=classification["confidence"],
                )

            return classification

        except asyncio.TimeoutError:
            trace.end_step(decision="fallback", error="Classification timeout")
            raise ClassificationError("Classification timed out")

        except ClassificationError:
            raise

        except Exception as e:
            trace.end_step(decision="fallback", error=str(e))
            raise ClassificationError(f"Classification failed: {e}")

    @staticmethod
    def _parse_classification(llm_response: str) -> dict:
        """Extract JSON classification from LLM response.

        Handles markdown code blocks, bare JSON, and JSON embedded in text.
        """
        text = llm_response.strip()

        # Strip markdown code fences
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try to find a JSON object in the response
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
            else:
                raise ClassificationError("Could not parse classification JSON")

        return {
            "intent": parsed.get("intent", "data_query"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "reasoning": parsed.get("reasoning", ""),
            "entities": parsed.get("entities", {
                "metrics": [], "dimensions": [], "filters": {},
                "time_range": None, "sort": None, "limit": None,
            }),
        }

    def _retrieve(
        self, entities: dict, trace: TraceBuilder,
    ) -> RetrievalResult:
        """Run hybrid retrieval (pgvector + AGE + FAISS)."""
        trace.start_step("retrieval")

        try:
            result = self.retrieval.retrieve(entities)

            trace.end_step(
                decision=result.action,
                confidence=result.confidence,
                input_summary={"entities": entities},
                output_summary={
                    "model": result.model,
                    "explore": result.explore,
                    "dimensions": result.dimensions,
                    "measures": result.measures,
                    "action": result.action,
                },
            )
            return result

        except Exception as e:
            trace.end_step(decision="fallback", error=str(e))
            raise RetrievalError(f"Retrieval failed: {e}")

    def _handle_follow_up(
        self,
        classification: dict,
        last_context: dict,
        trace: TraceBuilder,
    ) -> RetrievalResult:
        """Handle follow-up queries by modifying the previous retrieval result.

        "Break that down by card product" -> keep previous model/explore/measures,
        add card_prod_id to dimensions.
        """
        trace.start_step("retrieval")

        entities = classification.get("entities", {})
        new_dims = entities.get("dimensions", [])

        result = RetrievalResult(
            action="proceed",
            model=last_context.get("model", ""),
            explore=last_context.get("explore", ""),
            dimensions=last_context.get("dimensions", []) + new_dims,
            measures=last_context.get("measures", []),
            filters=dict(last_context.get("filters", {})),
            confidence=0.85,
        )

        trace.end_step(
            decision="proceed",
            confidence=0.85,
            input_summary={"follow_up_entities": entities},
            output_summary={"model": result.model, "explore": result.explore,
                            "added_dimensions": new_dims},
        )
        return result

    def _resolve_filters(
        self,
        entities: dict,
        retrieval_result: RetrievalResult,
        trace: TraceBuilder,
    ) -> dict[str, str]:
        """Resolve filter values using the filter resolution engine."""
        trace.start_step("filter_resolution")

        try:
            resolved = self.retrieval._resolve_filters(entities, retrieval_result.explore)
            mandatory = self.retrieval._get_mandatory_filters(retrieval_result.explore)
            resolved.update(mandatory)

            trace.end_step(
                decision="proceed",
                input_summary={"raw_filters": entities.get("filters", {})},
                output_summary={"resolved": resolved},
            )
            return resolved

        except Exception as e:
            trace.end_step(decision="fallback", error=str(e))
            return entities.get("filters", {})

    def _build_prompt(self, result: RetrievalResult) -> str:
        """Build the augmented system prompt from retrieval result."""
        return _build_augmented_prompt_fn(
            model=result.model,
            explore=result.explore,
            dimensions=result.dimensions,
            measures=result.measures,
            filters=result.filters,
            confidence=result.confidence,
            fewshot_match=(
                result.fewshot_matches[0]
                if hasattr(result, 'fewshot_matches') and result.fewshot_matches
                else "none"
            ),
        )

    # ==== Phase 3: response building ========================================

    def _build_response(
        self,
        react_result: dict,
        retrieval_result: RetrievalResult,
        trace: TraceBuilder,
        debug: bool,
    ) -> dict:
        """Build the final CortexResponse dict."""
        trace.start_step("response_formatting")

        content = react_result.get("content", "")
        data = self._extract_data(react_result)
        sql = self._extract_sql(content)
        follow_ups = self._generate_follow_ups(content, retrieval_result)

        retrieval_context = {
            "model": retrieval_result.model,
            "explore": retrieval_result.explore,
            "dimensions": retrieval_result.dimensions,
            "measures": retrieval_result.measures,
            "filters": retrieval_result.filters,
        }

        pipeline_trace = trace.build(action=retrieval_result.action)
        self._store_trace(pipeline_trace)

        trace.end_step(decision="proceed")

        response = {
            "answer": content,
            "data": data,
            "sql": sql,
            "follow_ups": follow_ups,
            "retrieval_context": retrieval_context,
            "error": None,
            "metadata": {
                "pipeline_version": "0.1.0",
                "trace_id": pipeline_trace.trace_id,
                "total_duration_ms": round(pipeline_trace.total_duration_ms, 1),
            },
        }

        if debug:
            response["trace"] = pipeline_trace.to_dict()

        return response

    # ==== Canned responses ==================================================

    def _out_of_scope(
        self, query: str, classification: dict, trace: TraceBuilder,
    ) -> dict:
        pipeline_trace = trace.build(action="out_of_scope")
        self._store_trace(pipeline_trace)
        return {
            "answer": (
                "I can help with data queries about American Express business metrics. "
                "Try asking about billed business, card issuance, travel bookings, "
                "or customer segments."
            ),
            "data": None, "sql": None,
            "follow_ups": [
                "What was total billed business last quarter?",
                "How many new cards were issued this month?",
                "Show me travel booking revenue by vertical",
            ],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    def _clarify_response(
        self, query: str, result: RetrievalResult, trace: TraceBuilder,
    ) -> dict:
        pipeline_trace = trace.build(action="clarify")
        self._store_trace(pipeline_trace)
        return {
            "answer": (
                "I was not able to match your question to a specific dataset. "
                "Could you rephrase using more specific terms? "
                "For example, mention a metric like 'billed business' "
                "or a dimension like 'card product'."
            ),
            "data": None, "sql": None, "follow_ups": [],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    def _disambiguate_response(
        self, query: str, result: RetrievalResult, trace: TraceBuilder,
    ) -> dict:
        pipeline_trace = trace.build(action="disambiguate")
        self._store_trace(pipeline_trace)
        options = result.alternatives[:3]
        option_text = "\n".join(
            f"  {i+1}. {opt['explore']} (confidence: {opt['score']:.0%})"
            for i, opt in enumerate(options)
        )
        return {
            "answer": (
                f"I found multiple possible data sources for your query:\n"
                f"{option_text}\n\n"
                f"Which one would you like to query?"
            ),
            "data": None, "sql": None,
            "follow_ups": [f"Use {opt['explore']}" for opt in options],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    def _error_response(
        self, query: str, message: str, trace: TraceBuilder, step: str = "",
    ) -> dict:
        pipeline_trace = trace.build(action="error")
        self._store_trace(pipeline_trace)
        return {
            "answer": f"Something went wrong: {message}",
            "data": None, "sql": None, "follow_ups": [],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": {"message": message, "step": step, "recoverable": False},
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    async def _fallback(
        self, query: str, history: list[dict],
        trace: TraceBuilder, reason: str,
    ) -> dict:
        """Fall back to raw AgentOrchestrator (PoC behavior)."""
        trace.add_step(
            "fallback",
            input_summary={"reason": reason},
            output_summary={},
            decision="fallback",
        )
        logger.warning("Falling back to raw AgentOrchestrator: %s", reason)

        messages = [*history, {"role": "user", "content": query}]
        raw = await self.agent.run(messages)

        pipeline_trace = trace.build(action="fallback")
        self._store_trace(pipeline_trace)

        return {
            "answer": raw.get("content", "I could not process your query."),
            "data": None, "sql": None, "follow_ups": [],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {
                "trace_id": pipeline_trace.trace_id,
                "fallback_reason": reason,
            },
        }

    async def _passthrough(
        self, query: str, history: list[dict], trace: TraceBuilder,
    ) -> dict:
        """Pass through to raw AgentOrchestrator for schema/saved content queries."""
        trace.add_step(
            "passthrough",
            input_summary={"query": query},
            output_summary={},
            decision="passthrough",
        )
        messages = [*history, {"role": "user", "content": query}]
        raw = await self.agent.run(messages)
        pipeline_trace = trace.build(action="passthrough")
        self._store_trace(pipeline_trace)
        return {
            "answer": raw.get("content", ""),
            "data": None, "sql": None, "follow_ups": [],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    # ==== Helpers ============================================================

    def _store_trace(self, trace: PipelineTrace) -> None:
        """Store a trace, evicting oldest entries if over capacity."""
        self._trace_store[trace.trace_id] = trace
        if len(self._trace_store) > TRACE_STORE_MAX:
            oldest = sorted(self._trace_store.keys())[:TRACE_STORE_EVICT]
            for k in oldest:
                del self._trace_store[k]

    @staticmethod
    def _extract_data(react_result: dict) -> dict | None:
        """Extract structured data from ReAct result tool calls."""
        tool_results = react_result.get("tool_results", [])
        for tr in tool_results:
            result_str = str(tr.get("result", ""))
            if result_str and "{" in result_str:
                try:
                    data = json.loads(result_str)
                    if isinstance(data, list):
                        return {
                            "rows": data,
                            "columns": list(data[0].keys()) if data else [],
                            "row_count": len(data),
                        }
                    if isinstance(data, dict) and "rows" in data:
                        return data
                except json.JSONDecodeError:
                    pass
        return None

    @staticmethod
    def _extract_sql(content: str) -> str | None:
        """Extract SQL from the LLM response."""
        if "```sql" in content:
            parts = content.split("```sql")
            if len(parts) > 1:
                return parts[1].split("```")[0].strip()
        if "SELECT" in content.upper():
            match = re.search(r'(SELECT\s+.*?;)', content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _generate_follow_ups(content: str, result: RetrievalResult) -> list[str]:
        """Generate follow-up suggestions based on the result."""
        follow_ups = []
        if result.dimensions:
            follow_ups.append(f"Break this down by {result.dimensions[0]}")
        if result.measures and len(result.measures) > 1:
            follow_ups.append(f"Show only {result.measures[0]}")
        if result.filters:
            follow_ups.append("Remove all filters and show the total")
        if not follow_ups:
            follow_ups = [
                "Show me the trend over time",
                "Compare to previous period",
            ]
        return follow_ups[:3]


# ---- Stream event helper ---------------------------------------------------

def _stream_event(
    event_type: str,
    step: str = "",
    progress: float = 0.0,
    *,
    message: str = "",
    duration_ms: float | None = None,
    result: dict | None = None,
    answer: dict | None = None,
) -> dict:
    """Build a stream event dict for SSE."""
    event: dict[str, Any] = {
        "event_type": event_type,
        "step": step,
        "progress": progress,
    }
    if message:
        event["message"] = message
    if duration_ms is not None:
        event["duration_ms"] = round(duration_ms, 1)
    if result is not None:
        event["result"] = result
    if answer is not None:
        event["answer"] = answer
    return event
