"""Pipeline trace -- first-class observability for every query.

Every CortexOrchestrator.run() call produces a PipelineTrace with
per-step timing, inputs, outputs, and decisions. This is NOT just
logging -- it is a structured object returned to the frontend and
available via GET /trace/{trace_id}.

Design constraints:
  - Immutable after build(). TraceBuilder is the mutable counterpart.
  - Serializable to JSON (for SSE, API response, and storage).
  - Input/output summaries are truncated to prevent bloating responses.

Why not just logging?
  PipelineTrace is a structured DATA OBJECT that:
    1. Gets returned in the API response (debug=true)
    2. Gets streamed as SSE events in /query/stream
    3. Gets stored in PostgreSQL for post-hoc evaluation
    4. Gets displayed in the CLI trace table
  Logging goes to stdout and is not programmatically accessible by
  the frontend. This is the "show your work" feature.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


MAX_SUMMARY_LENGTH = 500  # Truncate input/output summaries for display


def _truncate(obj: Any, max_len: int = MAX_SUMMARY_LENGTH) -> Any:
    """Truncate a value for display in trace summaries."""
    s = str(obj)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def _truncate_dict(data: dict[str, Any], max_str_len: int = 200) -> dict[str, Any]:
    """Truncate string values in a dict for display.

    Prevents trace payloads from bloating with raw SQL, embeddings, etc.
    """
    result = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > max_str_len:
            result[k] = v[:max_str_len] + "..."
        elif isinstance(v, list) and len(v) > 10:
            result[k] = v[:10] + [f"... +{len(v) - 10} more"]
        elif isinstance(v, dict):
            result[k] = _truncate_dict(v, max_str_len)
        else:
            result[k] = v
    return result


@dataclass(frozen=True)
class StepTrace:
    """Immutable record of one pipeline step.

    Attributes:
        step_name: Machine-readable step identifier (e.g. "intent_classification").
        started_at: Monotonic timestamp when step began.
        ended_at: Monotonic timestamp when step finished.
        duration_ms: Wall-clock duration in milliseconds.
        input_summary: Truncated dict of step inputs (for debugging display).
        output_summary: Truncated dict of step outputs (for debugging display).
        decision: What the step decided: "proceed", "disambiguate", "clarify",
                  "fallback", "skip", "low_confidence", "timeout".
        confidence: Step-specific confidence score (0.0-1.0), or None if N/A.
        error: Error message if the step failed, None otherwise.
    """

    step_name: str
    started_at: float
    ended_at: float
    duration_ms: float
    input_summary: dict
    output_summary: dict
    decision: str
    confidence: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.step_name,
            "duration_ms": round(self.duration_ms, 1),
            "decision": self.decision,
            "confidence": round(self.confidence, 3) if self.confidence is not None else None,
            "input": self.input_summary,
            "output": self.output_summary,
            "error": self.error,
        }


@dataclass(frozen=True)
class PipelineTrace:
    """Immutable trace of a complete pipeline execution.

    Created by TraceBuilder.build() at the end of a pipeline run.
    Frozen (immutable) to prevent accidental mutation after construction.
    Uses tuple instead of list for the same reason.
    """

    trace_id: str
    query: str
    steps: tuple[StepTrace, ...]
    total_duration_ms: float
    llm_calls: int
    mcp_calls: int
    retrieval_confidence: float
    action_taken: str

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "llm_calls": self.llm_calls,
            "mcp_calls": self.mcp_calls,
            "confidence": round(self.retrieval_confidence, 3),
            "action": self.action_taken,
            "steps": [s.to_dict() for s in self.steps],
        }


class TraceBuilder:
    """Mutable builder for PipelineTrace. Used during pipeline execution.

    Supports two usage patterns:

    Pattern 1 -- start/end (for steps with measurable duration):
        builder.start_step("intent_classification")
        result = await classify(query)
        builder.end_step(decision="proceed", confidence=0.97)

    Pattern 2 -- add_step (for steps recorded after the fact):
        builder.add_step("fallback", {"reason": "..."}, {}, "fallback")

    Thread safety: NOT thread-safe. One TraceBuilder per pipeline execution.
    """

    def __init__(self, query: str):
        self.trace_id = str(uuid.uuid4())
        self.query = query
        self._steps: list[StepTrace] = []
        self._current_step_name: str | None = None
        self._current_step_start: float = 0.0
        self._pipeline_start = time.monotonic()
        self._llm_calls = 0
        self._mcp_calls = 0

    def start_step(self, step_name: str) -> None:
        """Begin timing a pipeline step.

        If a previous step was started but not ended, this silently
        replaces it. This prevents stuck builders when exceptions
        skip end_step() calls.
        """
        self._current_step_name = step_name
        self._current_step_start = time.monotonic()

    def end_step(
        self,
        *,
        decision: str = "proceed",
        confidence: float | None = None,
        input_summary: dict | None = None,
        output_summary: dict | None = None,
        error: str | None = None,
    ) -> StepTrace:
        """Finish a step and record it.

        Returns the completed StepTrace for immediate inspection.
        """
        now = time.monotonic()
        step = StepTrace(
            step_name=self._current_step_name or "unknown",
            started_at=self._current_step_start,
            ended_at=now,
            duration_ms=(now - self._current_step_start) * 1000,
            input_summary=_truncate_dict(input_summary or {}),
            output_summary=_truncate_dict(output_summary or {}),
            decision=decision,
            confidence=confidence,
            error=error,
        )
        self._steps.append(step)
        self._current_step_name = None
        return step

    def add_step(
        self,
        step_name: str,
        input_summary: dict,
        output_summary: dict,
        decision: str,
        confidence: float | None = None,
        error: str | None = None,
        duration_ms: float = 0.0,
    ) -> StepTrace:
        """Add a completed step directly.

        For steps that don't need start/end timing (e.g. fallback steps
        recorded after the fact).
        """
        now = time.monotonic()
        step = StepTrace(
            step_name=step_name,
            started_at=now - (duration_ms / 1000),
            ended_at=now,
            duration_ms=duration_ms,
            input_summary=_truncate_dict(input_summary),
            output_summary=_truncate_dict(output_summary),
            decision=decision,
            confidence=confidence,
            error=error,
        )
        self._steps.append(step)
        return step

    def increment_llm_calls(self, n: int = 1) -> None:
        """Track LLM round-trips for the trace summary."""
        self._llm_calls += n

    def increment_mcp_calls(self, n: int = 1) -> None:
        """Track MCP tool calls for the trace summary."""
        self._mcp_calls += n

    # Backward-compatible aliases for the old API
    record_llm_call = lambda self: self.increment_llm_calls(1)
    record_mcp_call = lambda self: self.increment_mcp_calls(1)

    def build(self, action: str = "proceed") -> PipelineTrace:
        """Freeze the trace. Called once at the end of pipeline execution.

        Args:
            action: The overall pipeline action taken. If "proceed" (default),
                    scans steps for a retrieval step to infer the action.

        Scans steps for the retrieval step's confidence to use as the
        overall retrieval_confidence in the trace summary.
        """
        total_ms = (time.monotonic() - self._pipeline_start) * 1000
        confidence = 0.0
        for step in self._steps:
            if step.step_name == "retrieval" and step.confidence is not None:
                confidence = step.confidence
                break

        return PipelineTrace(
            trace_id=self.trace_id,
            query=self.query,
            steps=tuple(self._steps),
            total_duration_ms=total_ms,
            llm_calls=self._llm_calls,
            mcp_calls=self._mcp_calls,
            retrieval_confidence=confidence,
            action_taken=action,
        )
