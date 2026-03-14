# Cortex API & CLI Architecture

**Author:** Saheb | **Date:** March 13, 2026 | **Status:** Proposed
**Depends on:** [Agentic Orchestration Design](agentic-orchestration-design.md), ADR-001 (ADK), ADR-007 (Filters), ADR-008 (Learning Loop)

---

## 1. Overview

This document specifies the three entry points into the Cortex pipeline:

1. **CLI** (`cortex_cli.py`) -- Interactive terminal for pipeline testing and debugging. First thing that needs to work.
2. **FastAPI Server** (`api/server.py`) -- Production HTTP API with synchronous, streaming, and health endpoints.
3. **API Contracts** (`api/models.py`) -- Pydantic models defining request/response shapes, SSE events, and internal pipeline types.

All three share the same core: `CortexOrchestrator` from `pipeline/cortex_orchestrator.py`, which wraps the existing `AgentOrchestrator` from `access_llm/chat.py` with the hybrid retrieval pipeline.

### Data Flow

```
                 CLI                    ChatGPT Enterprise
                  |                            |
                  v                            v
            cortex_cli.py              api/server.py (FastAPI)
                  |                            |
                  +------------+---------------+
                               |
                               v
                      CortexOrchestrator
                     /         |         \
              Phase 1      Phase 2      Phase 3
            (retrieval)   (ReAct via   (format +
                          SafeChain)    trace)
```

### Design Principles

1. **CLI first, API second.** The CLI proves the pipeline works end-to-end. The API is a thin HTTP layer on top of the same orchestrator.
2. **Stateless API.** Conversation history is sent with every request. No server-side session storage. `last_retrieval_result` for follow-ups is reconstructed from the previous turn's trace, or the frontend caches it.
3. **Same orchestrator, different consumers.** CLI and API both call `CortexOrchestrator.run()` or `.run_streaming()`. The difference is presentation, not logic.
4. **SSE for progress, not for content.** Streaming sends pipeline step events (progress indicators). The final answer is a single `answer` event, not token-by-token streaming.

---

## 2. File Structure

```
cortex/src/
|-- cli/
|   |-- __init__.py              # (empty)
|   +-- cortex_cli.py            # Interactive CLI with rich UI       ~320 lines
|
|-- api/
|   |-- __init__.py              # (empty)
|   |-- server.py                # FastAPI app + endpoints            ~280 lines
|   |-- models.py                # Pydantic request/response models   ~350 lines
|   |-- events.py                # SSE event protocol + streaming     ~120 lines
|   +-- middleware.py            # Logging, CORS, error handling      ~100 lines
|
|-- pipeline/
|   |-- __init__.py              # (existing)
|   |-- agent.py                 # (existing stub -- remains thin)
|   |-- state.py                 # (existing -- CortexState)
|   |-- cortex_orchestrator.py   # Main 3-phase orchestrator          ~350 lines
|   |-- trace.py                 # PipelineTrace, StepTrace, Builder  ~180 lines
|   |-- prompts.py               # Classification + augmentation      ~120 lines
|   +-- errors.py                # Error hierarchy                     ~80 lines
|
|-- connectors/
|   |-- __init__.py              # (existing)
|   |-- safechain_client.py      # (existing stub -- extend)          ~150 lines
|   +-- mcp_tools.py             # (existing)
|
+-- retrieval/                   # (existing -- unchanged)
    |-- orchestrator.py
    |-- models.py
    |-- filters.py
    +-- ...

Total new code: ~1,930 lines across 10 new files.
```

### Dependency Graph

```
cortex_cli.py -----> CortexOrchestrator
                          |
api/server.py -----> CortexOrchestrator
                          |
                          +---> RetrievalOrchestrator (existing)
                          +---> AgentOrchestrator (existing, from chat.py)
                          +---> PipelineTrace (new)
                          +---> prompts.py (new)
                          +---> errors.py (new)
                          |
api/models.py <----> CortexOrchestrator (shared types)
api/events.py <----- api/server.py (SSE streaming)
api/middleware.py <-- api/server.py (ASGI middleware)
```

No circular dependencies. `api/models.py` is a leaf -- nothing in `pipeline/` imports from `api/`.

---

## 3. Pipeline Errors (`pipeline/errors.py`)

```python
"""Cortex pipeline error hierarchy.

Every error carries the step name where it occurred and whether the
pipeline can recover (fall back to raw AgentOrchestrator) or must abort.

Recovery matrix:
  ClassificationError  -> recoverable (skip to Phase 2 raw)
  RetrievalError       -> recoverable (skip to Phase 2 raw)
  FilterResolutionError -> recoverable (use raw filter values)
  SafeChainError       -> NOT recoverable (no LLM access at all)
  TimeoutError         -> NOT recoverable (budget exhausted)
  ValidationError      -> NOT recoverable (SQL is unsafe)
"""

from __future__ import annotations


class CortexError(Exception):
    """Base exception for all Cortex pipeline errors."""

    def __init__(
        self,
        message: str,
        step: str,
        recoverable: bool = True,
        details: dict | None = None,
    ):
        self.step = step
        self.recoverable = recoverable
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error": str(self),
            "step": self.step,
            "recoverable": self.recoverable,
            "details": self.details,
        }


class ClassificationError(CortexError):
    """Intent classification failed or returned low confidence."""

    def __init__(self, message: str, confidence: float = 0.0):
        super().__init__(
            message,
            step="intent_classification",
            recoverable=True,
            details={"confidence": confidence},
        )


class RetrievalError(CortexError):
    """Hybrid retrieval failed to find matching fields."""

    def __init__(self, message: str, action: str = "no_match"):
        super().__init__(
            message,
            step="retrieval",
            recoverable=True,
            details={"action": action},
        )


class FilterResolutionError(CortexError):
    """Filter value resolution failed."""

    def __init__(self, message: str, unresolved: list[dict] | None = None):
        super().__init__(
            message,
            step="filter_resolution",
            recoverable=True,
            details={"unresolved": unresolved or []},
        )


class SafeChainError(CortexError):
    """SafeChain/CIBIS authentication or connectivity failure."""

    def __init__(self, message: str):
        super().__init__(message, step="safechain", recoverable=False)


class PipelineTimeoutError(CortexError):
    """Total pipeline time budget exhausted."""

    def __init__(self, message: str, elapsed_ms: float, budget_ms: float):
        super().__init__(
            message,
            step="timeout",
            recoverable=False,
            details={"elapsed_ms": elapsed_ms, "budget_ms": budget_ms},
        )


class SQLValidationError(CortexError):
    """Generated SQL failed structural validation."""

    def __init__(self, message: str, sql: str = ""):
        super().__init__(
            message,
            step="sql_validation",
            recoverable=False,
            details={"sql": sql},
        )
```

---

## 4. Pipeline Trace (`pipeline/trace.py`)

```python
"""Pipeline trace -- first-class observability for every query.

Every CortexOrchestrator.run() call produces a PipelineTrace with
per-step timing, inputs, outputs, and decisions. This is NOT just
logging -- it's a structured object returned to the frontend and
available via GET /trace/{trace_id}.

Design constraints:
  - Immutable after build(). TraceBuilder is the mutable counterpart.
  - Serializable to JSON (for SSE, API response, and storage).
  - Input/output summaries are truncated to prevent bloating responses.
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


@dataclass(frozen=True)
class StepTrace:
    """Immutable record of one pipeline step."""

    step_name: str
    started_at: float          # time.monotonic()
    ended_at: float            # time.monotonic()
    duration_ms: float         # (ended_at - started_at) * 1000
    input_summary: dict        # truncated inputs
    output_summary: dict       # truncated outputs
    decision: str              # "proceed" | "disambiguate" | "clarify" | "fallback" | "skip"
    confidence: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.step_name,
            "duration_ms": round(self.duration_ms, 1),
            "decision": self.decision,
            "confidence": self.confidence,
            "input": self.input_summary,
            "output": self.output_summary,
            "error": self.error,
        }


@dataclass(frozen=True)
class PipelineTrace:
    """Immutable trace of a complete pipeline execution."""

    trace_id: str
    query: str
    steps: tuple[StepTrace, ...]   # frozen = tuple, not list
    total_duration_ms: float
    llm_calls: int
    mcp_calls: int
    retrieval_confidence: float
    action_taken: str              # "proceed" | "disambiguate" | "clarify" | "fallback"

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "llm_calls": self.llm_calls,
            "mcp_calls": self.mcp_calls,
            "confidence": self.retrieval_confidence,
            "action": self.action_taken,
            "steps": [s.to_dict() for s in self.steps],
        }


class TraceBuilder:
    """Mutable builder for PipelineTrace. Used during pipeline execution.

    Usage:
        builder = TraceBuilder("What is total billed business?")
        builder.start_step("intent_classification")
        # ... do work ...
        builder.end_step(decision="proceed", confidence=0.97,
                         input_summary={"query": query},
                         output_summary={"intent": "data_query"})
        trace = builder.build()
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
        """Begin timing a pipeline step."""
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
        """Finish a step and record it."""
        now = time.monotonic()
        step = StepTrace(
            step_name=self._current_step_name or "unknown",
            started_at=self._current_step_start,
            ended_at=now,
            duration_ms=(now - self._current_step_start) * 1000,
            input_summary={k: _truncate(v) for k, v in (input_summary or {}).items()},
            output_summary={k: _truncate(v) for k, v in (output_summary or {}).items()},
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
        """Add a completed step directly (for steps that don't need start/end timing)."""
        now = time.monotonic()
        step = StepTrace(
            step_name=step_name,
            started_at=now - (duration_ms / 1000),
            ended_at=now,
            duration_ms=duration_ms,
            input_summary={k: _truncate(v) for k, v in input_summary.items()},
            output_summary={k: _truncate(v) for k, v in output_summary.items()},
            decision=decision,
            confidence=confidence,
            error=error,
        )
        self._steps.append(step)
        return step

    def increment_llm_calls(self, n: int = 1) -> None:
        self._llm_calls += n

    def increment_mcp_calls(self, n: int = 1) -> None:
        self._mcp_calls += n

    def build(self, action: str = "proceed") -> PipelineTrace:
        """Freeze the trace. Called once at the end of pipeline execution."""
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
```

---

## 5. API Data Contracts (`api/models.py`)

```python
"""Pydantic models for the Cortex API.

These are the CONTRACTS between frontend and backend. Change with care --
ChatGPT Enterprise connector and any future UI depend on these shapes.

Separation from pipeline internals:
  - Pipeline uses dataclasses (pipeline/trace.py, retrieval/models.py)
  - API uses Pydantic (this file) for validation, serialization, OpenAPI docs
  - Conversion happens at the boundary (CortexOrchestrator.run() returns
    internal types, FastAPI endpoint converts to Pydantic before returning)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---- Enums ---------------------------------------------------------------

class IntentType(str, Enum):
    DATA_QUERY = "data_query"
    SCHEMA_BROWSE = "schema_browse"
    SAVED_CONTENT = "saved_content"
    FOLLOW_UP = "follow_up"
    OUT_OF_SCOPE = "out_of_scope"


class RetrievalAction(str, Enum):
    PROCEED = "proceed"
    DISAMBIGUATE = "disambiguate"
    CLARIFY = "clarify"
    NO_MATCH = "no_match"


class PipelineStepName(str, Enum):
    INTENT_CLASSIFICATION = "intent_classification"
    ENTITY_EXTRACTION = "entity_extraction"
    RETRIEVAL = "retrieval"
    FILTER_RESOLUTION = "filter_resolution"
    PROMPT_AUGMENTATION = "prompt_augmentation"
    REACT_EXECUTION = "react_execution"
    SQL_VALIDATION = "sql_validation"
    RESPONSE_FORMATTING = "response_formatting"
    FALLBACK = "fallback"


class StreamEventType(str, Enum):
    STEP_START = "step_start"
    STEP_COMPLETE = "step_complete"
    STEP_ERROR = "step_error"
    ANSWER = "answer"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class ComponentStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"


# ---- Request Models -------------------------------------------------------

class ConversationMessage(BaseModel):
    """A single message in conversation history."""
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class QueryRequest(BaseModel):
    """Request body for POST /query and POST /query/stream."""
    query: str = Field(..., min_length=1, max_length=2000,
                       description="The natural language question")
    history: list[ConversationMessage] = Field(
        default_factory=list,
        max_length=20,
        description="Conversation history (max 20 messages)")
    session_id: str | None = Field(
        None, description="Session ID for multi-turn tracking")
    user_id: str | None = Field(
        None, description="User identifier for feedback attribution")
    debug: bool = Field(
        False, description="Include full pipeline trace in response")
    last_retrieval_context: RetrievalContext | None = Field(
        None, description="Previous turn's retrieval result for follow-ups")

    model_config = {"json_schema_extra": {
        "examples": [{
            "query": "What was total billed business for small businesses last quarter?",
            "history": [],
            "session_id": "sess_abc123",
            "debug": False,
        }]
    }}


class RetrievalContext(BaseModel):
    """Previous turn's retrieval context, sent by frontend for follow-up queries.

    When a user says "break that down by card product", the frontend sends
    the previous RetrievalResult so we know what model/explore/measures to
    modify rather than re-discovering from scratch.
    """
    model: str
    explore: str
    dimensions: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    filters: dict[str, str] = Field(default_factory=dict)


class FilterCorrectionPayload(BaseModel):
    """User correction of a filter value, feeds ADR-008 learning loop."""
    user_term: str = Field(..., description="What the user originally typed")
    correct_value: str = Field(..., description="The correct LookML value")
    dimension: str = Field(..., description="The LookML dimension name")


class FeedbackRequest(BaseModel):
    """Request body for POST /feedback."""
    query: str
    session_id: str
    trace_id: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    filter_correction: FilterCorrectionPayload | None = None
    comment: str | None = Field(None, max_length=1000)

    model_config = {"json_schema_extra": {
        "examples": [{
            "query": "What was total billed business for small businesses?",
            "session_id": "sess_abc123",
            "rating": 4,
            "comment": "Correct data but filter label was confusing",
        }]
    }}


# ---- Response Models -------------------------------------------------------

class StepTraceResponse(BaseModel):
    """One pipeline step in the trace."""
    name: str
    duration_ms: float
    decision: str
    confidence: float | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class PipelineTraceResponse(BaseModel):
    """Full pipeline trace for debugging and transparency."""
    trace_id: str
    query: str
    total_duration_ms: float
    llm_calls: int
    mcp_calls: int
    confidence: float
    action: str
    steps: list[StepTraceResponse]


class DataPayload(BaseModel):
    """Structured query results."""
    rows: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0


class CortexResponse(BaseModel):
    """Response body for POST /query.

    Invariant: `answer` is always present (even on error, it contains
    a human-readable error message). `data`, `sql`, `trace` are optional.
    """
    answer: str = Field(..., description="Natural language answer")
    data: DataPayload | None = Field(
        None, description="Structured query results")
    sql: str | None = Field(
        None, description="Generated SQL for transparency")
    trace: PipelineTraceResponse | None = Field(
        None, description="Pipeline trace (included when debug=true)")
    follow_ups: list[str] = Field(
        default_factory=list,
        description="Suggested follow-up questions")
    retrieval_context: RetrievalContext | None = Field(
        None, description="Retrieval context for follow-up queries")
    error: ErrorDetail | None = Field(
        None, description="Error details if the query failed")
    metadata: ResponseMetadata = Field(
        default_factory=lambda: ResponseMetadata())

    model_config = {"json_schema_extra": {
        "examples": [{
            "answer": "Total billed business for Small Business (OPEN) last quarter was $4.2B.",
            "data": {"rows": [{"total_billed_business": 4200000000}],
                     "columns": ["total_billed_business"], "row_count": 1},
            "sql": "SELECT SUM(billed_amount) FROM ... WHERE bus_seg = 'OPEN'",
            "follow_ups": ["Break down by card product",
                           "Compare to previous quarter"],
        }]
    }}


class ResponseMetadata(BaseModel):
    """Metadata about the response for monitoring."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = "gemini-2.0-flash"
    pipeline_version: str = "0.1.0"


class ErrorDetail(BaseModel):
    """Structured error for API responses."""
    message: str
    step: str = ""
    recoverable: bool = True
    details: dict[str, Any] = Field(default_factory=dict)


# ---- Health Check ----------------------------------------------------------

class ComponentHealth(BaseModel):
    """Health status of a single dependency."""
    status: ComponentStatus
    latency_ms: float | None = None
    message: str | None = None


class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: ComponentStatus = ComponentStatus.OK
    version: str = "0.1.0"
    uptime_seconds: float = 0.0
    components: dict[str, ComponentHealth] = Field(default_factory=dict)

    model_config = {"json_schema_extra": {
        "examples": [{
            "status": "ok",
            "version": "0.1.0",
            "uptime_seconds": 3621.5,
            "components": {
                "safechain": {"status": "ok", "latency_ms": 45.2},
                "postgresql": {"status": "ok", "latency_ms": 3.1},
                "faiss": {"status": "ok", "latency_ms": 0.2},
                "mcp_toolbox": {"status": "ok", "latency_ms": 12.7},
            },
        }]
    }}


# ---- Capabilities ----------------------------------------------------------

class DemoQuery(BaseModel):
    """A suggested query for the "Try asking:" section."""
    question: str
    category: str  # e.g. "Spending", "Travel", "Risk"


class CapabilitiesResponse(BaseModel):
    """Response body for GET /capabilities."""
    models: list[str]
    explores: list[str]
    demo_queries: list[DemoQuery]
    field_count: int
    business_units: list[str]


# ---- SSE Stream Events ----------------------------------------------------

class StreamEvent(BaseModel):
    """A single Server-Sent Event in the /query/stream response.

    SSE wire format:
        event: step_start
        data: {"step": "intent_classification", "progress": 0.1, ...}

    The `event_type` field maps to the SSE `event:` line.
    The rest of the model serializes as the `data:` line.
    """
    event_type: StreamEventType
    step: str = ""
    progress: float = Field(0.0, ge=0.0, le=1.0,
                            description="Pipeline progress 0.0-1.0")
    message: str = ""
    duration_ms: float | None = None
    result: dict[str, Any] | None = None
    # Only present on event_type=answer
    answer: CortexResponse | None = None

    def to_sse(self) -> str:
        """Serialize to SSE wire format."""
        import json
        data = self.model_dump(exclude_none=True, exclude={"event_type"})
        return f"event: {self.event_type.value}\ndata: {json.dumps(data)}\n\n"
```

---

## 6. SSE Streaming Protocol (`api/events.py`)

```python
"""SSE event definitions and streaming helpers.

Defines the exact event sequence that /query/stream emits.
The frontend uses progress percentages to render a pipeline visualization.

Event flow (happy path):
    step_start  intent_classification   0.05  "Understanding your question..."
    step_complete intent_classification 0.15  {intent, confidence}
    step_start  retrieval               0.20  "Finding matching data..."
    step_complete retrieval             0.35  {model, explore, fields}
    step_start  filter_resolution       0.40  "Resolving filter values..."
    step_complete filter_resolution     0.45  {filters}
    step_start  prompt_augmentation     0.48  "Preparing context..."
    step_complete prompt_augmentation   0.50  {}
    step_start  react_execution         0.55  "Querying data..."
    step_complete react_execution       0.80  {sql, row_count}
    step_start  response_formatting     0.85  "Formatting answer..."
    step_complete response_formatting   0.95  {}
    answer      -                       1.00  CortexResponse

Event flow (error, recoverable):
    step_start    intent_classification 0.05
    step_error    intent_classification 0.05  {error, recoverable: true}
    step_start    fallback              0.10  "Using direct query mode..."
    step_complete fallback              0.80  {raw_response}
    answer        -                     1.00  CortexResponse

Event flow (error, non-recoverable):
    step_start    react_execution       0.55
    step_error    react_execution       0.55  {error, recoverable: false}
    error         -                     -     {message, step}

Heartbeat:
    Every 15 seconds during long operations to prevent timeout.
    heartbeat     -                     (current progress)  ""
"""

from __future__ import annotations

from api.models import (
    CortexResponse,
    StreamEvent,
    StreamEventType,
)


# ---- Progress map ----------------------------------------------------------
# Fixed progress percentages for each step.
# These give the frontend a predictable progress bar.

STEP_PROGRESS = {
    "intent_classification":  (0.05, 0.15),  # (start, complete)
    "entity_extraction":      (0.15, 0.20),
    "retrieval":              (0.20, 0.35),
    "filter_resolution":      (0.35, 0.45),
    "prompt_augmentation":    (0.45, 0.50),
    "react_execution":        (0.50, 0.80),
    "sql_validation":         (0.80, 0.85),
    "response_formatting":    (0.85, 0.95),
    "fallback":               (0.10, 0.80),
}

STEP_MESSAGES = {
    "intent_classification": "Understanding your question...",
    "entity_extraction": "Extracting business concepts...",
    "retrieval": "Finding matching data fields...",
    "filter_resolution": "Resolving filter values...",
    "prompt_augmentation": "Preparing context for query...",
    "react_execution": "Querying Looker for data...",
    "sql_validation": "Validating query...",
    "response_formatting": "Formatting your answer...",
    "fallback": "Using direct query mode...",
}


def make_step_start(step_name: str) -> StreamEvent:
    """Create a step_start event."""
    start_progress, _ = STEP_PROGRESS.get(step_name, (0.0, 0.0))
    return StreamEvent(
        event_type=StreamEventType.STEP_START,
        step=step_name,
        progress=start_progress,
        message=STEP_MESSAGES.get(step_name, "Processing..."),
    )


def make_step_complete(
    step_name: str,
    duration_ms: float,
    result: dict | None = None,
) -> StreamEvent:
    """Create a step_complete event."""
    _, end_progress = STEP_PROGRESS.get(step_name, (0.0, 0.0))
    return StreamEvent(
        event_type=StreamEventType.STEP_COMPLETE,
        step=step_name,
        progress=end_progress,
        duration_ms=duration_ms,
        result=result,
    )


def make_step_error(
    step_name: str,
    error_msg: str,
    recoverable: bool = True,
) -> StreamEvent:
    """Create a step_error event."""
    start_progress, _ = STEP_PROGRESS.get(step_name, (0.0, 0.0))
    return StreamEvent(
        event_type=StreamEventType.STEP_ERROR,
        step=step_name,
        progress=start_progress,
        message=error_msg,
        result={"recoverable": recoverable},
    )


def make_answer(response: CortexResponse) -> StreamEvent:
    """Create the final answer event."""
    return StreamEvent(
        event_type=StreamEventType.ANSWER,
        progress=1.0,
        answer=response,
    )


def make_error(message: str, step: str = "") -> StreamEvent:
    """Create a non-recoverable error event."""
    return StreamEvent(
        event_type=StreamEventType.ERROR,
        step=step,
        message=message,
    )


def make_heartbeat(current_progress: float) -> StreamEvent:
    """Create a heartbeat event (keeps SSE connection alive)."""
    return StreamEvent(
        event_type=StreamEventType.HEARTBEAT,
        progress=current_progress,
    )
```

---

## 7. CortexOrchestrator (`pipeline/cortex_orchestrator.py`)

```python
"""CortexOrchestrator -- the 3-phase pipeline integration layer.

Wraps the existing AgentOrchestrator (from access_llm/chat.py) with
pre-processing (hybrid retrieval) and post-processing (trace + formatting).

Composition over inheritance:
  - Does NOT subclass AgentOrchestrator
  - Wraps it: Phase 1 prepares, Phase 2 delegates, Phase 3 post-processes
  - If Phase 1 fails, falls through to raw AgentOrchestrator behavior

Entry points:
  run()            -- synchronous (returns CortexResponse dict)
  run_streaming()  -- async generator yielding StreamEvent objects
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from typing import Any, AsyncGenerator, Callable

from src.pipeline.trace import TraceBuilder, PipelineTrace
from src.pipeline.errors import (
    CortexError,
    ClassificationError,
    RetrievalError,
    PipelineTimeoutError,
    SafeChainError,
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


# ---- Prompt templates (imported from prompts.py in production) ------------

CLASSIFY_PROMPT = """You are an intent classifier for a financial data analytics system.
Given the user's question, return valid JSON with intent, confidence, reasoning, and entities.

Intents: data_query, schema_browse, saved_content, follow_up, out_of_scope

Available business terms: {taxonomy_terms}
Previous context: {previous_context}

User query: {query}

Return JSON: {{"intent": "...", "confidence": 0.0-1.0, "reasoning": "...",
  "entities": {{"metrics": [], "dimensions": [], "filters": {{}},
  "time_range": null, "sort": null, "limit": null}}}}"""

AUGMENTED_PROMPT = """You are a data analyst assistant querying Looker for American Express.

## Retrieved Context (confidence: {confidence:.0%})
- Model: {model}
- Explore: {explore}
- Dimensions: {dimensions}
- Measures: {measures}
- Filters: {filters}

## Instructions
1. Use query-sql with EXACTLY these fields. Do NOT explore or discover.
2. Filters include mandatory partition filters. Do NOT remove them.
3. If query-sql errors, report the error. Do NOT change fields.
4. Present: direct answer, data table, SQL used.
5. Suggest 2-3 follow-up questions."""


class CortexOrchestrator:
    """Three-phase pipeline: retrieve -> execute -> format."""

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
        self._trace_store: dict[str, PipelineTrace] = {}  # trace_id -> trace

    # ---- Public interface -------------------------------------------------

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
            # ---- PHASE 1: PRE-PROCESSING ----
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

            # ---- Check time budget ----
            elapsed = (time.monotonic() - pipeline_start) * 1000
            if elapsed > TOTAL_TIMEOUT_MS * 0.6:
                logger.warning("Phase 1 took %.0fms, approaching budget", elapsed)

            # ---- PHASE 2: REACT EXECUTION ----
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
                output_summary={"content_length": len(react_result.get("content", ""))},
            )
            trace.increment_llm_calls(2)  # typical: 1 tool call + 1 format
            trace.increment_mcp_calls(1)  # 1 query-sql call

            # ---- PHASE 3: POST-PROCESSING ----
            self.last_retrieval_result = retrieval_result
            response = self._build_response(
                react_result, retrieval_result, trace, debug
            )
            return response

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
        as each phase executes.
        """
        trace = TraceBuilder(query)
        history = (conversation_history or [])[-MAX_CONVERSATION_HISTORY:]

        try:
            # ---- Intent Classification ----
            yield {"event_type": "step_start", "step": "intent_classification",
                   "progress": 0.05, "message": "Understanding your question..."}

            classification = await self._classify(query, history, trace)

            yield {"event_type": "step_complete", "step": "intent_classification",
                   "progress": 0.15,
                   "duration_ms": trace._steps[-1].duration_ms if trace._steps else 0,
                   "result": {"intent": classification["intent"],
                              "confidence": classification["confidence"]}}

            if classification["intent"] == "out_of_scope":
                resp = self._out_of_scope(query, classification, trace)
                yield {"event_type": "answer", "progress": 1.0, "answer": resp}
                return

            # ---- Retrieval ----
            yield {"event_type": "step_start", "step": "retrieval",
                   "progress": 0.20, "message": "Finding matching data fields..."}

            if classification["intent"] == "follow_up" and last_retrieval_context:
                retrieval_result = self._handle_follow_up(
                    classification, last_retrieval_context, trace
                )
            else:
                retrieval_result = self._retrieve(classification["entities"], trace)

            yield {"event_type": "step_complete", "step": "retrieval",
                   "progress": 0.35,
                   "duration_ms": trace._steps[-1].duration_ms if trace._steps else 0,
                   "result": {"model": retrieval_result.model,
                              "explore": retrieval_result.explore,
                              "action": retrieval_result.action,
                              "confidence": retrieval_result.confidence}}

            if retrieval_result.action in ("clarify", "disambiguate"):
                resp = (self._clarify_response(query, retrieval_result, trace)
                        if retrieval_result.action == "clarify"
                        else self._disambiguate_response(query, retrieval_result, trace))
                yield {"event_type": "answer", "progress": 1.0, "answer": resp}
                return

            # ---- Filter Resolution ----
            yield {"event_type": "step_start", "step": "filter_resolution",
                   "progress": 0.40, "message": "Resolving filter values..."}

            resolved_filters = self._resolve_filters(
                classification["entities"], retrieval_result, trace
            )
            retrieval_result.filters = resolved_filters

            yield {"event_type": "step_complete", "step": "filter_resolution",
                   "progress": 0.45,
                   "duration_ms": trace._steps[-1].duration_ms if trace._steps else 0,
                   "result": {"filters": resolved_filters}}

            # ---- ReAct Execution ----
            yield {"event_type": "step_start", "step": "react_execution",
                   "progress": 0.55, "message": "Querying Looker for data..."}

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

            yield {"event_type": "step_complete", "step": "react_execution",
                   "progress": 0.80,
                   "duration_ms": trace._steps[-1].duration_ms if trace._steps else 0,
                   "result": {"content_length": len(react_result.get("content", ""))}}

            # ---- Response ----
            yield {"event_type": "step_start", "step": "response_formatting",
                   "progress": 0.85, "message": "Formatting your answer..."}

            self.last_retrieval_result = retrieval_result
            response = self._build_response(react_result, retrieval_result, trace, False)

            yield {"event_type": "step_complete", "step": "response_formatting",
                   "progress": 0.95}

            yield {"event_type": "answer", "progress": 1.0, "answer": response}

        except Exception as e:
            logger.exception("Streaming pipeline error")
            yield {"event_type": "error", "message": str(e), "step": "unknown"}

    def get_trace(self, trace_id: str) -> PipelineTrace | None:
        """Retrieve a stored trace by ID."""
        return self._trace_store.get(trace_id)

    # ---- Phase 1 internals ------------------------------------------------

    async def _classify(
        self, query: str, history: list[dict], trace: TraceBuilder,
    ) -> dict:
        """Intent classification via single LLM call."""
        trace.start_step("intent_classification")

        previous_context = ""
        if history:
            last_msg = history[-1].get("content", "")
            previous_context = f"Previous: {last_msg[:200]}"

        prompt = CLASSIFY_PROMPT.format(
            taxonomy_terms=", ".join(self.taxonomy_terms[:50]),
            previous_context=previous_context,
            query=query,
        )

        try:
            from langchain_core.messages import HumanMessage
            result = await asyncio.wait_for(
                self.classifier.ainvoke([HumanMessage(content=prompt)]),
                timeout=CLASSIFICATION_TIMEOUT_MS / 1000,
            )

            content = result.content if hasattr(result, "content") else str(result)
            # Extract JSON from LLM response
            classification = self._parse_classification(content)
            trace.increment_llm_calls(1)

            trace.end_step(
                decision="proceed" if classification["confidence"] >= MIN_CLASSIFICATION_CONFIDENCE else "low_confidence",
                confidence=classification["confidence"],
                input_summary={"query": query},
                output_summary={"intent": classification["intent"],
                                "confidence": classification["confidence"]},
            )

            if classification["confidence"] < MIN_CLASSIFICATION_CONFIDENCE:
                raise ClassificationError(
                    f"Low confidence: {classification['confidence']:.2f}",
                    confidence=classification["confidence"],
                )

            return classification

        except asyncio.TimeoutError:
            trace.end_step(
                decision="fallback",
                error="Classification timeout",
            )
            raise ClassificationError("Classification timed out")

        except ClassificationError:
            raise

        except Exception as e:
            trace.end_step(
                decision="fallback",
                error=str(e),
            )
            raise ClassificationError(f"Classification failed: {e}")

    @staticmethod
    def _parse_classification(llm_response: str) -> dict:
        """Extract JSON classification from LLM response."""
        # Try to find JSON in the response
        text = llm_response.strip()

        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            import re
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
            else:
                raise ClassificationError("Could not parse classification JSON")

        # Validate required fields
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
        """Handle follow-up queries by modifying the previous retrieval result."""
        trace.start_step("retrieval")

        entities = classification.get("entities", {})
        result = RetrievalResult(
            action="proceed",
            model=last_context.get("model", ""),
            explore=last_context.get("explore", ""),
            dimensions=last_context.get("dimensions", []) + entities.get("dimensions", []),
            measures=last_context.get("measures", []),
            filters=dict(last_context.get("filters", {})),
            confidence=0.85,
        )

        trace.end_step(
            decision="proceed",
            confidence=0.85,
            input_summary={"follow_up_entities": entities},
            output_summary={"model": result.model, "explore": result.explore},
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
            # Return raw filters as fallback
            return entities.get("filters", {})

    def _build_prompt(self, result: RetrievalResult) -> str:
        """Build the augmented system prompt from retrieval result."""
        return AUGMENTED_PROMPT.format(
            confidence=result.confidence,
            model=result.model,
            explore=result.explore,
            dimensions=", ".join(result.dimensions) or "(none)",
            measures=", ".join(result.measures) or "(none)",
            filters=json.dumps(result.filters) if result.filters else "(none)",
        )

    # ---- Phase 3: response building --------------------------------------

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

        # Build retrieval context for follow-ups
        retrieval_context = {
            "model": retrieval_result.model,
            "explore": retrieval_result.explore,
            "dimensions": retrieval_result.dimensions,
            "measures": retrieval_result.measures,
            "filters": retrieval_result.filters,
        }

        pipeline_trace = trace.build(action=retrieval_result.action)
        self._trace_store[pipeline_trace.trace_id] = pipeline_trace

        # Keep trace store bounded
        if len(self._trace_store) > 1000:
            oldest = sorted(self._trace_store.keys())[:500]
            for k in oldest:
                del self._trace_store[k]

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
                "total_duration_ms": pipeline_trace.total_duration_ms,
            },
        }

        if debug:
            response["trace"] = pipeline_trace.to_dict()

        return response

    def _out_of_scope(
        self, query: str, classification: dict, trace: TraceBuilder,
    ) -> dict:
        """Response for out-of-scope queries."""
        pipeline_trace = trace.build(action="out_of_scope")
        return {
            "answer": (
                "I can help with data queries about American Express business metrics. "
                "Try asking about billed business, card issuance, travel bookings, "
                "or customer segments."
            ),
            "data": None,
            "sql": None,
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
        """Response asking user to rephrase."""
        pipeline_trace = trace.build(action="clarify")
        return {
            "answer": (
                "I wasn't able to match your question to a specific dataset. "
                "Could you rephrase using more specific terms? "
                "For example, mention a metric like 'billed business' "
                "or a dimension like 'card product'."
            ),
            "data": None,
            "sql": None,
            "follow_ups": [],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    def _disambiguate_response(
        self, query: str, result: RetrievalResult, trace: TraceBuilder,
    ) -> dict:
        """Response presenting disambiguation options."""
        pipeline_trace = trace.build(action="disambiguate")
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
            "data": None,
            "sql": None,
            "follow_ups": [f"Use {opt['explore']}" for opt in options],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    def _error_response(
        self, query: str, message: str, trace: TraceBuilder, step: str = "",
    ) -> dict:
        """Build an error response."""
        pipeline_trace = trace.build(action="error")
        self._trace_store[pipeline_trace.trace_id] = pipeline_trace
        return {
            "answer": f"Something went wrong: {message}",
            "data": None,
            "sql": None,
            "follow_ups": [],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": {"message": message, "step": step, "recoverable": False},
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    async def _fallback(
        self,
        query: str,
        history: list[dict],
        trace: TraceBuilder,
        reason: str,
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
        self._trace_store[pipeline_trace.trace_id] = pipeline_trace

        return {
            "answer": raw.get("content", "I could not process your query."),
            "data": None,
            "sql": None,
            "follow_ups": [],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {"trace_id": pipeline_trace.trace_id,
                          "fallback_reason": reason},
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
        return {
            "answer": raw.get("content", ""),
            "data": None,
            "sql": None,
            "follow_ups": [],
            "retrieval_context": None,
            "trace": pipeline_trace.to_dict(),
            "error": None,
            "metadata": {"trace_id": pipeline_trace.trace_id},
        }

    # ---- Helpers ----------------------------------------------------------

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
                        return {"rows": data, "columns": list(data[0].keys()) if data else [], "row_count": len(data)}
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
            import re
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
```

---

## 8. FastAPI Server (`api/server.py`)

```python
"""Cortex FastAPI server.

Endpoints:
  POST /query         -- synchronous query, returns CortexResponse
  POST /query/stream  -- SSE streaming with pipeline step events
  GET  /health        -- dependency health check
  POST /feedback      -- user feedback for learning loop
  GET  /trace/{id}    -- retrieve a specific pipeline trace
  GET  /capabilities  -- available models, explores, demo queries

Startup sequence:
  1. Load config (Config.from_env())
  2. Initialize SafeChain (MCPToolLoader.load_tools())
  3. Connect to PostgreSQL (pgvector + AGE)
  4. Load FAISS index (in-memory)
  5. Load filter catalog (config/filter_catalog.json)
  6. Initialize CortexOrchestrator (wires everything together)
  7. Start FastAPI (uvicorn)

If any step in 1-5 fails, the server starts in DEGRADED mode:
  - /health returns degraded status with failed component
  - /query falls back to raw AgentOrchestrator (no retrieval)
  - /query/stream returns error event immediately

Deployment:
  GKE pod with MCP Toolbox sidecar. Container runs:
    uvicorn src.api.server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# ---- Application state (module-level singletons) --------------------------
# These are populated during startup and injected into endpoints.

_cortex: Any = None           # CortexOrchestrator
_start_time: float = 0.0
_startup_errors: list[str] = []


# ---- Startup / Shutdown ---------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize dependencies on startup."""
    global _cortex, _start_time, _startup_errors
    _start_time = time.monotonic()
    _startup_errors = []

    logger.info("Starting Cortex API server...")

    # Step 1: Load config
    config = None
    try:
        from ee_config.config import Config
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv())
        config = Config.from_env()
        logger.info("[1/6] Config loaded")
    except Exception as e:
        msg = f"Config load failed: {e}"
        logger.error(msg)
        _startup_errors.append(msg)

    # Step 2: Initialize SafeChain
    tools = []
    model_id = "gemini-2.0-flash"
    if config:
        try:
            from safechain.tools.mcp import MCPToolLoader, MCPToolAgent
            tools = await MCPToolLoader.load_tools(config)
            model_id = getattr(config, "model_id", model_id)
            logger.info("[2/6] SafeChain initialized (%d tools)", len(tools))
        except Exception as e:
            msg = f"SafeChain init failed: {e}"
            logger.error(msg)
            _startup_errors.append(msg)

    # Step 3: Connect to PostgreSQL
    pg_conn = None
    try:
        import psycopg2
        pg_conn = psycopg2.connect(os.getenv("POSTGRES_URL", ""))
        logger.info("[3/6] PostgreSQL connected")
    except Exception as e:
        msg = f"PostgreSQL connection failed: {e}"
        logger.warning(msg)
        _startup_errors.append(msg)

    # Step 4: Load FAISS index
    faiss_loaded = False
    try:
        # FAISS is loaded lazily by fewshot module
        faiss_loaded = True
        logger.info("[4/6] FAISS index ready (lazy load)")
    except Exception as e:
        msg = f"FAISS load failed: {e}"
        logger.warning(msg)
        _startup_errors.append(msg)

    # Step 5: Load filter catalog (auto-loaded at import time by filters.py)
    try:
        from src.retrieval.filters import FILTER_VALUE_MAP
        logger.info("[5/6] Filter catalog loaded (%d dimensions)", len(FILTER_VALUE_MAP))
    except Exception as e:
        msg = f"Filter catalog failed: {e}"
        logger.warning(msg)
        _startup_errors.append(msg)

    # Step 6: Initialize CortexOrchestrator
    try:
        from access_llm.chat import AgentOrchestrator
        from safechain.tools.mcp import MCPToolAgent
        from src.retrieval.orchestrator import RetrievalOrchestrator
        from src.pipeline.cortex_orchestrator import CortexOrchestrator

        # Embedding function (SafeChain or local fallback)
        def embed_fn(text: str) -> list[float]:
            # TODO: Route through SafeChain embedding endpoint
            raise NotImplementedError("Embedding function not yet wired")

        agent_orchestrator = AgentOrchestrator(
            model_id=model_id,
            tools=tools,
            max_iterations=5,
        )
        classifier_agent = MCPToolAgent(model_id, tools=[])
        retrieval = RetrievalOrchestrator(pg_conn, embed_fn)

        _cortex = CortexOrchestrator(
            agent_orchestrator=agent_orchestrator,
            retrieval=retrieval,
            classifier_agent=classifier_agent,
            embed_fn=embed_fn,
        )
        logger.info("[6/6] CortexOrchestrator initialized")
    except Exception as e:
        msg = f"CortexOrchestrator init failed: {e}"
        logger.error(msg)
        _startup_errors.append(msg)

    if _startup_errors:
        logger.warning("Server starting in DEGRADED mode: %s", _startup_errors)
    else:
        logger.info("Cortex API server ready")

    yield  # Application runs here

    # Shutdown
    logger.info("Shutting down Cortex API server...")
    if pg_conn:
        try:
            pg_conn.close()
        except Exception:
            pass


# ---- FastAPI app -----------------------------------------------------------

app = FastAPI(
    title="Cortex API",
    description="AI intelligence pipeline for natural language to SQL via Looker",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGINS", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Request logging middleware -------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log request method, path, and response time."""
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s -> %d (%.0fms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


# ---- Endpoints ------------------------------------------------------------

@app.post("/query")
async def query_endpoint(request_body: dict):
    """Synchronous query endpoint.

    Request: {query, history?, session_id?, user_id?, debug?,
              last_retrieval_context?}
    Response: CortexResponse
    """
    if not _cortex:
        raise HTTPException(
            status_code=503,
            detail="Cortex is not initialized. Check /health for details.",
        )

    query = request_body.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    history = request_body.get("history", [])
    debug = request_body.get("debug", False)
    last_ctx = request_body.get("last_retrieval_context")

    response = await _cortex.run(
        query=query,
        conversation_history=history,
        debug=debug,
        last_retrieval_context=last_ctx,
    )
    return response


@app.post("/query/stream")
async def query_stream_endpoint(request_body: dict):
    """SSE streaming endpoint.

    Same request as /query. Streams pipeline step events as SSE.
    Final event is the complete CortexResponse.
    """
    if not _cortex:
        raise HTTPException(status_code=503, detail="Cortex is not initialized.")

    query = request_body.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    history = request_body.get("history", [])
    last_ctx = request_body.get("last_retrieval_context")

    async def event_generator():
        """Generate SSE events from the streaming pipeline."""
        import json

        heartbeat_interval = 15  # seconds
        last_heartbeat = time.monotonic()

        try:
            async for event in _cortex.run_streaming(
                query=query,
                conversation_history=history,
                last_retrieval_context=last_ctx,
            ):
                event_type = event.get("event_type", "unknown")
                data = json.dumps(event)
                yield f"event: {event_type}\ndata: {data}\n\n"

                # Send heartbeat if needed
                now = time.monotonic()
                if now - last_heartbeat > heartbeat_interval:
                    heartbeat = json.dumps({
                        "event_type": "heartbeat",
                        "progress": event.get("progress", 0.0),
                    })
                    yield f"event: heartbeat\ndata: {heartbeat}\n\n"
                    last_heartbeat = now

        except Exception as e:
            error = json.dumps({"event_type": "error", "message": str(e)})
            yield f"event: error\ndata: {error}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.get("/health")
async def health_endpoint():
    """Health check. Verifies connectivity to all dependencies.

    Returns 200 with component status. Returns 503 if non-recoverable
    components are down (SafeChain, PostgreSQL).
    """
    uptime = time.monotonic() - _start_time
    components = {}

    # SafeChain
    if any("SafeChain" in e for e in _startup_errors):
        components["safechain"] = {"status": "error", "message": "Not initialized"}
    else:
        components["safechain"] = {"status": "ok"}

    # PostgreSQL
    if any("PostgreSQL" in e for e in _startup_errors):
        components["postgresql"] = {"status": "error", "message": "Not connected"}
    else:
        components["postgresql"] = {"status": "ok"}

    # FAISS
    components["faiss"] = {"status": "ok"}

    # MCP Toolbox
    mcp_url = os.getenv("MCP_TOOLBOX_URL", "http://localhost:5000")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{mcp_url}/health")
            if resp.status_code == 200:
                components["mcp_toolbox"] = {"status": "ok"}
            else:
                components["mcp_toolbox"] = {"status": "degraded",
                                              "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        components["mcp_toolbox"] = {"status": "error", "message": str(e)}

    # Overall status
    statuses = [c.get("status", "ok") for c in components.values()]
    if "error" in statuses:
        overall = "error"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "version": "0.1.0",
        "uptime_seconds": round(uptime, 1),
        "components": components,
        "startup_errors": _startup_errors if _startup_errors else None,
    }


@app.post("/feedback")
async def feedback_endpoint(request_body: dict):
    """User feedback endpoint. Feeds ADR-008 learning loop.

    If the user corrects a filter value, log it as a synonym suggestion.
    """
    query = request_body.get("query", "")
    session_id = request_body.get("session_id", "")
    rating = request_body.get("rating")
    comment = request_body.get("comment")
    filter_correction = request_body.get("filter_correction")

    if filter_correction:
        logger.info(
            "Filter correction: %s -> %s for dim %s (session=%s)",
            filter_correction.get("user_term"),
            filter_correction.get("correct_value"),
            filter_correction.get("dimension"),
            session_id,
        )
        # TODO: Write to synonym_suggestions table in PostgreSQL

    if rating is not None:
        logger.info(
            "Feedback: rating=%d query='%s' session=%s comment='%s'",
            rating, query[:100], session_id, (comment or "")[:100],
        )
        # TODO: Write to query_feedback table

    return {"status": "logged"}


@app.get("/trace/{trace_id}")
async def trace_endpoint(trace_id: str):
    """Retrieve a specific pipeline trace for debugging."""
    if not _cortex:
        raise HTTPException(status_code=503, detail="Cortex not initialized")

    trace = _cortex.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    return trace.to_dict()


@app.get("/capabilities")
async def capabilities_endpoint():
    """What can this system do? Used by frontend for onboarding."""
    return {
        "models": ["cortex_finance"],
        "explores": [
            "finance_cardmember_360",
            "finance_merchant_profitability",
            "finance_travel_sales",
            "finance_card_issuance",
            "finance_customer_risk",
        ],
        "demo_queries": [
            {"question": "What was total billed business last quarter?",
             "category": "Spending"},
            {"question": "Show new card issuance by generation",
             "category": "Issuance"},
            {"question": "What is travel booking revenue by vertical?",
             "category": "Travel"},
            {"question": "Compare Gold vs Platinum card spend",
             "category": "Spending"},
            {"question": "How many active premium cardmembers are there?",
             "category": "Customer"},
        ],
        "field_count": 41,
        "business_units": ["Finance"],
    }
```

---

## 9. CLI Interface (`cli/cortex_cli.py`)

```python
#!/usr/bin/env python3
"""Cortex CLI -- interactive pipeline testing tool.

This is the FIRST thing that needs to work. It proves the full pipeline
end-to-end: intent classification -> hybrid retrieval -> Looker MCP SQL
generation -> formatted response with trace.

Usage:
    python -m src.cli.cortex_cli

Commands:
    /trace   - Show last pipeline trace
    /debug   - Toggle verbose mode (shows full step details)
    /tools   - List available MCP tools
    /clear   - Clear conversation history
    /history - Show conversation history
    /quit    - Exit

Features:
    - Real-time pipeline step visualization (rich library)
    - Debug mode: per-step timing, inputs, outputs, decisions
    - Multi-turn: maintains conversation history + retrieval context
    - Graceful fallback: if pipeline fails, falls back to raw chat.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

# Rich library for terminal UI
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.layout import Layout


console = Console()

# ---- Pipeline Step Display ------------------------------------------------

STEP_ICONS = {
    "intent_classification": "[bold blue]INTENT[/]",
    "entity_extraction":     "[bold blue]ENTITIES[/]",
    "retrieval":             "[bold yellow]RETRIEVAL[/]",
    "filter_resolution":     "[bold yellow]FILTERS[/]",
    "prompt_augmentation":   "[bold cyan]PROMPT[/]",
    "react_execution":       "[bold green]EXECUTE[/]",
    "sql_validation":        "[bold green]VALIDATE[/]",
    "response_formatting":   "[bold cyan]FORMAT[/]",
    "fallback":              "[bold red]FALLBACK[/]",
    "passthrough":           "[bold magenta]PASSTHROUGH[/]",
}

STEP_DESCRIPTIONS = {
    "intent_classification": "Classifying query intent...",
    "entity_extraction":     "Extracting business entities...",
    "retrieval":             "Searching for matching fields...",
    "filter_resolution":     "Resolving filter values...",
    "prompt_augmentation":   "Building augmented prompt...",
    "react_execution":       "Executing Looker query...",
    "sql_validation":        "Validating generated SQL...",
    "response_formatting":   "Formatting response...",
    "fallback":              "Falling back to direct mode...",
}


def render_trace_table(trace: dict, verbose: bool = False) -> Table:
    """Render a pipeline trace as a rich Table."""
    table = Table(title="Pipeline Trace", show_header=True, header_style="bold magenta")
    table.add_column("Step", style="cyan", min_width=20)
    table.add_column("Duration", justify="right", style="green", min_width=10)
    table.add_column("Decision", style="yellow", min_width=12)
    table.add_column("Confidence", justify="right", min_width=10)

    if verbose:
        table.add_column("Details", min_width=30)

    for step in trace.get("steps", []):
        name = step.get("name", "unknown")
        duration = f"{step.get('duration_ms', 0):.0f}ms"
        decision = step.get("decision", "-")
        confidence = f"{step.get('confidence', 0):.0%}" if step.get("confidence") is not None else "-"

        row = [name, duration, decision, confidence]

        if verbose:
            details_parts = []
            if step.get("input"):
                details_parts.append(f"in: {json.dumps(step['input'], default=str)[:60]}")
            if step.get("output"):
                details_parts.append(f"out: {json.dumps(step['output'], default=str)[:60]}")
            if step.get("error"):
                details_parts.append(f"[red]err: {step['error']}[/red]")
            row.append("\n".join(details_parts) if details_parts else "-")

        table.add_row(*row)

    # Summary row
    total_ms = trace.get("total_duration_ms", 0)
    llm_calls = trace.get("llm_calls", 0)
    mcp_calls = trace.get("mcp_calls", 0)
    table.add_section()
    summary = f"Total: {total_ms:.0f}ms | LLM calls: {llm_calls} | MCP calls: {mcp_calls}"
    confidence = trace.get("confidence", 0)
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_ms:.0f}ms[/bold]",
        trace.get("action", "-"),
        f"[bold]{confidence:.0%}[/bold]",
        *([summary] if verbose else []),
    )

    return table


def render_response(response: dict, debug: bool = False) -> None:
    """Render a CortexResponse to the console."""
    answer = response.get("answer", "No response.")

    # Main answer
    console.print()
    console.print(Panel(
        Markdown(answer),
        title="[bold cyan]Cortex[/bold cyan]",
        border_style="cyan",
        expand=True,
    ))

    # SQL (if present)
    sql = response.get("sql")
    if sql:
        console.print(Panel(sql, title="SQL", border_style="dim", expand=False))

    # Data summary (if present)
    data = response.get("data")
    if data and data.get("rows"):
        rows = data["rows"]
        cols = data.get("columns", [])
        if rows and cols:
            data_table = Table(title=f"Results ({data.get('row_count', len(rows))} rows)",
                               show_header=True, header_style="bold")
            for col in cols[:10]:  # Cap at 10 columns
                data_table.add_column(col)
            for row in rows[:20]:  # Cap at 20 rows
                data_table.add_row(*[str(row.get(c, "")) for c in cols[:10]])
            console.print(data_table)

    # Follow-ups
    follow_ups = response.get("follow_ups", [])
    if follow_ups:
        console.print()
        console.print("[dim]Suggested follow-ups:[/dim]")
        for i, fu in enumerate(follow_ups, 1):
            console.print(f"  [dim]{i}.[/dim] {fu}")

    # Trace (debug mode or always show summary)
    trace = response.get("trace")
    if trace:
        if debug:
            console.print()
            console.print(render_trace_table(trace, verbose=True))
        else:
            total_ms = trace.get("total_duration_ms", 0)
            confidence = trace.get("confidence", 0)
            action = trace.get("action", "-")
            console.print(
                f"\n[dim]{total_ms:.0f}ms | confidence: {confidence:.0%} | action: {action} | "
                f"trace: {trace.get('trace_id', '-')[:8]}[/dim]"
            )

    # Error
    error = response.get("error")
    if error:
        console.print(Panel(
            f"[red]{error.get('message', 'Unknown error')}[/red]\n"
            f"Step: {error.get('step', 'unknown')} | "
            f"Recoverable: {error.get('recoverable', False)}",
            title="[bold red]Error[/bold red]",
            border_style="red",
        ))


class CortexCLI:
    """Interactive CLI session wrapping CortexOrchestrator."""

    def __init__(self, cortex: Any, tools: list | None = None):
        self.cortex = cortex
        self.tools = tools or []
        self.conversation_history: list[dict] = []
        self.last_trace: dict | None = None
        self.last_retrieval_context: dict | None = None
        self.debug = False

    async def handle_query(self, user_input: str) -> None:
        """Send a query through the Cortex pipeline and display results."""
        # Show progress spinner during execution
        with console.status("[bold green]Processing...[/bold green]", spinner="dots"):
            try:
                response = await self.cortex.run(
                    query=user_input,
                    conversation_history=self.conversation_history,
                    debug=True,  # Always get trace for CLI
                    last_retrieval_context=self.last_retrieval_context,
                )
            except Exception as e:
                console.print(f"[red]Pipeline error: {e}[/red]")
                import traceback
                if self.debug:
                    traceback.print_exc()
                return

        # Update state
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response.get("answer", "")})
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

        self.last_trace = response.get("trace")
        self.last_retrieval_context = response.get("retrieval_context")

        # Render
        render_response(response, debug=self.debug)

    async def handle_streaming_query(self, user_input: str) -> None:
        """Stream a query with live pipeline step updates."""
        final_response = None

        with Live(console=console, refresh_per_second=10) as live:
            steps_display = Table(show_header=False, box=None, padding=(0, 1))
            steps_display.add_column("Icon", width=12)
            steps_display.add_column("Status", min_width=40)

            async for event in self.cortex.run_streaming(
                query=user_input,
                conversation_history=self.conversation_history,
                last_retrieval_context=self.last_retrieval_context,
            ):
                event_type = event.get("event_type", "")
                step = event.get("step", "")

                if event_type == "step_start":
                    icon = STEP_ICONS.get(step, "[dim]STEP[/dim]")
                    msg = event.get("message", "Processing...")
                    progress = event.get("progress", 0)
                    steps_display.add_row(icon, f"{msg} [dim]({progress:.0%})[/dim]")
                    live.update(steps_display)

                elif event_type == "step_complete":
                    duration = event.get("duration_ms", 0)
                    result = event.get("result", {})
                    icon = STEP_ICONS.get(step, "[dim]STEP[/dim]")
                    detail = json.dumps(result, default=str)[:80] if result else ""
                    steps_display.add_row(
                        f"  [green]OK[/green]",
                        f"[green]{duration:.0f}ms[/green] {detail}",
                    )
                    live.update(steps_display)

                elif event_type == "step_error":
                    steps_display.add_row(
                        f"  [red]ERR[/red]",
                        f"[red]{event.get('message', 'Error')}[/red]",
                    )
                    live.update(steps_display)

                elif event_type == "answer":
                    final_response = event.get("answer", {})

                elif event_type == "error":
                    console.print(f"\n[red]Error: {event.get('message', 'Unknown')}[/red]")
                    return

        if final_response:
            self.conversation_history.append({"role": "user", "content": user_input})
            self.conversation_history.append({"role": "assistant", "content": final_response.get("answer", "")})
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

            self.last_trace = final_response.get("trace")
            self.last_retrieval_context = final_response.get("retrieval_context")
            render_response(final_response, debug=self.debug)

    def cmd_trace(self) -> None:
        """Show the last pipeline trace."""
        if not self.last_trace:
            console.print("[dim]No trace available. Run a query first.[/dim]")
            return
        console.print(render_trace_table(self.last_trace, verbose=True))

    def cmd_debug(self) -> None:
        """Toggle debug mode."""
        self.debug = not self.debug
        state = "ON" if self.debug else "OFF"
        console.print(f"[yellow]Debug mode: {state}[/yellow]")

    def cmd_tools(self) -> None:
        """List available MCP tools."""
        if not self.tools:
            console.print("[dim]No tools loaded.[/dim]")
            return

        table = Table(title="MCP Tools", show_header=True, header_style="bold")
        table.add_column("Name", style="cyan")
        table.add_column("Description")

        for tool in self.tools:
            name = getattr(tool, "name", str(tool))
            desc = getattr(tool, "description", "")[:60]
            table.add_row(name, desc)

        console.print(table)
        console.print(f"\n[dim]Total: {len(self.tools)} tools[/dim]")

    def cmd_clear(self) -> None:
        """Clear conversation history and retrieval context."""
        self.conversation_history = []
        self.last_trace = None
        self.last_retrieval_context = None
        console.print("[yellow]Conversation cleared.[/yellow]")

    def cmd_history(self) -> None:
        """Show conversation history."""
        if not self.conversation_history:
            console.print("[dim]No conversation history.[/dim]")
            return

        for msg in self.conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]
            style = "blue" if role == "user" else "green"
            console.print(f"[{style}]{role}:[/{style}] {content}")

    def cmd_help(self) -> None:
        """Show help."""
        console.print(Panel(
            "[bold]Commands:[/bold]\n"
            "  /trace    Show last pipeline trace (step timing, decisions)\n"
            "  /debug    Toggle verbose debug mode\n"
            "  /tools    List available MCP tools\n"
            "  /clear    Clear conversation history\n"
            "  /history  Show conversation history\n"
            "  /stream   Toggle streaming mode (live step updates)\n"
            "  /quit     Exit\n"
            "\n"
            "[bold]Example queries:[/bold]\n"
            "  What was total billed business for small businesses last quarter?\n"
            "  Show new card issuance by generation\n"
            "  Break that down by card product  (follow-up)\n"
            "  What data is available about travel?  (schema browse)",
            title="Cortex CLI",
            border_style="cyan",
        ))


# ---- Main Entry Point -----------------------------------------------------

async def main():
    """Initialize dependencies and start the interactive loop."""
    console.print(Panel(
        "[bold]Cortex[/bold] -- AI Pipeline for Semantic Layer\n"
        "Natural Language to SQL via Looker + Hybrid Retrieval",
        title="cortex v0.1.0",
        border_style="cyan",
    ))
    console.print()

    # ---- Step 1: Load config ----
    console.print("[1/4] Loading configuration...", end=" ")
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv())
        from ee_config.config import Config
        config = Config.from_env()
        console.print("[green]OK[/green]")
    except Exception as e:
        console.print(f"[red]FAILED: {e}[/red]")
        console.print("[yellow]Cannot proceed without config. Check .env file.[/yellow]")
        return

    # ---- Step 2: Load MCP tools ----
    console.print("[2/4] Loading MCP tools...", end=" ")
    try:
        from safechain.tools.mcp import MCPToolLoader, MCPToolAgent
        tools = await MCPToolLoader.load_tools(config)
        console.print(f"[green]OK ({len(tools)} tools)[/green]")
    except Exception as e:
        console.print(f"[red]FAILED: {e}[/red]")
        console.print("[yellow]Cannot proceed without SafeChain. Check credentials.[/yellow]")
        return

    # ---- Step 3: Initialize retrieval ----
    console.print("[3/4] Initializing retrieval pipeline...", end=" ")
    retrieval = None
    pg_conn = None
    try:
        import os
        import psycopg2
        from src.retrieval.orchestrator import RetrievalOrchestrator

        pg_url = os.getenv("POSTGRES_URL", "")
        if pg_url:
            pg_conn = psycopg2.connect(pg_url)

            def embed_fn(text: str) -> list[float]:
                # Local embedding for testing
                from src.adapters.model_adapter import get_embedding
                return get_embedding(text)

            retrieval = RetrievalOrchestrator(pg_conn, embed_fn)
            console.print("[green]OK[/green]")
        else:
            console.print("[yellow]SKIP (no POSTGRES_URL)[/yellow]")
    except Exception as e:
        console.print(f"[yellow]DEGRADED: {e}[/yellow]")

    # ---- Step 4: Build CortexOrchestrator ----
    console.print("[4/4] Initializing orchestrator...", end=" ")

    model_id = (
        getattr(config, "model_id", None)
        or getattr(config, "model", None)
        or "gemini-2.0-flash"
    )

    from access_llm.chat import AgentOrchestrator
    agent_orchestrator = AgentOrchestrator(
        model_id=model_id,
        tools=tools,
        max_iterations=5,
    )

    if retrieval:
        from src.pipeline.cortex_orchestrator import CortexOrchestrator
        classifier_agent = MCPToolAgent(model_id, tools=[])

        def embed_fn_safe(text: str) -> list[float]:
            from src.adapters.model_adapter import get_embedding
            return get_embedding(text)

        cortex = CortexOrchestrator(
            agent_orchestrator=agent_orchestrator,
            retrieval=retrieval,
            classifier_agent=classifier_agent,
            embed_fn=embed_fn_safe,
        )
        console.print("[green]OK (full pipeline)[/green]")
    else:
        # Fallback: wrap AgentOrchestrator in a minimal adapter
        cortex = _MinimalCortexAdapter(agent_orchestrator)
        console.print("[yellow]OK (direct mode, no retrieval)[/yellow]")

    console.print()

    # ---- Interactive loop ----
    cli = CortexCLI(cortex, tools)
    cli.cmd_help()
    streaming_mode = False

    console.print("\nType your question or command.\n")

    while True:
        try:
            user_input = console.input("[bold blue]You:[/bold blue] ").strip()

            if not user_input:
                continue

            # Commands
            cmd = user_input.lower()
            if cmd == "/quit" or cmd == "/exit":
                console.print("\n[dim]Goodbye.[/dim]")
                break
            elif cmd == "/trace":
                cli.cmd_trace()
                continue
            elif cmd == "/debug":
                cli.cmd_debug()
                continue
            elif cmd == "/tools":
                cli.cmd_tools()
                continue
            elif cmd == "/clear":
                cli.cmd_clear()
                continue
            elif cmd == "/history":
                cli.cmd_history()
                continue
            elif cmd == "/help":
                cli.cmd_help()
                continue
            elif cmd == "/stream":
                streaming_mode = not streaming_mode
                state = "ON" if streaming_mode else "OFF"
                console.print(f"[yellow]Streaming mode: {state}[/yellow]")
                continue

            # Query
            if streaming_mode and hasattr(cortex, "run_streaming"):
                await cli.handle_streaming_query(user_input)
            else:
                await cli.handle_query(user_input)

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye.[/dim]")
            break
        except EOFError:
            console.print("\n[dim]Goodbye.[/dim]")
            break

    # Cleanup
    if pg_conn:
        try:
            pg_conn.close()
        except Exception:
            pass


class _MinimalCortexAdapter:
    """Minimal adapter when retrieval is unavailable.

    Wraps AgentOrchestrator to match the CortexOrchestrator interface
    so the CLI works in degraded mode (no retrieval, no trace).
    """

    def __init__(self, agent: Any):
        self.agent = agent

    async def run(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
        debug: bool = False,
        last_retrieval_context: dict | None = None,
    ) -> dict:
        history = conversation_history or []
        messages = [*history, {"role": "user", "content": query}]
        result = await self.agent.run(messages)
        return {
            "answer": result.get("content", ""),
            "data": None,
            "sql": None,
            "trace": None,
            "follow_ups": [],
            "retrieval_context": None,
            "error": None,
            "metadata": {"mode": "direct"},
        }


def run():
    """Entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
```

---

## 10. Startup Sequence

```
                    STARTUP SEQUENCE
    ============================================

    [1] Config.from_env()
         |
         +-- Reads .env: CIBIS creds, POSTGRES_URL,
         |   MCP_TOOLBOX_URL, model_id
         |
         +-- FAILS? -> Server starts, /health = error,
             /query returns 503

    [2] MCPToolLoader.load_tools(config)
         |
         +-- Connects to SafeChain CIBIS
         +-- Discovers MCP servers
         +-- Returns tool list (33 tools, filtered to 5)
         |
         +-- FAILS? -> Server starts, /query falls back
             to error response (no LLM access at all)

    [3] psycopg2.connect(POSTGRES_URL)
         |
         +-- pgvector + Apache AGE on same instance
         +-- Used by: vector search, graph validation,
         |   filter catalog, query logging
         |
         +-- FAILS? -> Server starts DEGRADED,
             /query falls back to raw AgentOrchestrator
             (no retrieval, no graph, just LLM + MCP)

    [4] FAISS index (lazy loaded)
         |
         +-- In-memory index of golden query embeddings
         +-- Loaded on first few-shot search call
         |
         +-- FAILS? -> Retrieval runs without few-shot
             signal (coverage + graph still work)

    [5] Filter catalog (config/filter_catalog.json)
         |
         +-- Auto-loaded at import time by filters.py
         +-- Merged with hardcoded fallbacks
         |
         +-- FAILS? -> Hardcoded maps still available,
             lower resolution accuracy

    [6] CortexOrchestrator.__init__()
         |
         +-- Wires: AgentOrchestrator + RetrievalOrchestrator
         |   + classifier_agent + embed_fn
         |
         +-- FAILS? -> Server starts but /query returns 503
             (nothing to route queries to)

    [7] FastAPI starts (uvicorn)
         |
         +-- All endpoints available
         +-- /health reflects component status
         +-- Ready to serve queries
```

### Dependency Injection Pattern

No DI framework. Module-level singletons initialized in `lifespan()`:

```python
_cortex: CortexOrchestrator | None = None

@asynccontextmanager
async def lifespan(app):
    global _cortex
    # ... init sequence ...
    _cortex = CortexOrchestrator(...)
    yield
    # ... cleanup ...

@app.post("/query")
async def query(request):
    if not _cortex:
        raise HTTPException(503, "Not initialized")
    return await _cortex.run(...)
```

Why no DI framework: This is a single-pod deployment. One instance of each component. FastAPI's `Depends()` adds indirection without benefit here. If we move to multi-tenant (multiple BUs with different configs), revisit.

---

## 11. Error Handling Flow

```
    User Query
        |
        v
    +-------------------+
    | Classification    |-----> ClassificationError (recoverable)
    | (1 LLM call)      |          |
    +-------------------+          +---> FALLBACK to raw AgentOrchestrator
        |                                 (PoC behavior, no retrieval)
        v
    +-------------------+
    | Retrieval         |-----> RetrievalError (recoverable)
    | (pgvec+AGE+FAISS) |          |
    +-------------------+          +---> FALLBACK to raw AgentOrchestrator
        |
        v
    +-------------------+
    | Filter Resolution |-----> FilterResolutionError (recoverable)
    |                   |          |
    +-------------------+          +---> Use raw filter values (lower accuracy)
        |
        v
    +-------------------+
    | ReAct Execution   |-----> SafeChainError (NOT recoverable)
    | (LLM + MCP)       |          |
    +-------------------+          +---> Return error response with trace
        |                               (user sees "Something went wrong")
        |
        |                  -----> TimeoutError (NOT recoverable, 10s budget)
        |                          |
        |                          +---> Return timeout response
        v
    +-------------------+
    | Post-Processing   |-----> Exception (extremely unlikely)
    |                   |          |
    +-------------------+          +---> Return raw content, skip formatting
        |
        v
    CortexResponse (always has `answer`, optionally has `error`)
```

### Error Response Contract

Every response has the same shape. On error, `answer` contains a human-readable message and `error` contains structured details:

```json
{
    "answer": "Something went wrong: SafeChain authentication failed.",
    "data": null,
    "sql": null,
    "trace": { "trace_id": "...", "steps": [...] },
    "follow_ups": [],
    "error": {
        "message": "SafeChain authentication failed",
        "step": "safechain",
        "recoverable": false,
        "details": {}
    }
}
```

### Per-Step Time Budgets

```
Total budget: 10,000ms
  |
  +-- Classification:    2,000ms (asyncio.wait_for)
  +-- Retrieval:           500ms (pgvector + AGE + FAISS, all local)
  +-- Filter Resolution:   100ms (deterministic, in-memory)
  +-- ReAct Execution:   5,000ms (asyncio.wait_for)
  +-- Post-Processing:     100ms (no external calls)
  +-- Headroom:          2,300ms (network variance, retries)
```

If any step exceeds its budget, `asyncio.wait_for` raises `TimeoutError`, which the orchestrator catches and converts to a `PipelineTimeoutError`.

---

## 12. Session Management Design

### Stateless Multi-Turn Protocol

The API is fully stateless. The frontend maintains state:

```
Turn 1:
  Request:  {query: "Total billed business last quarter?", history: []}
  Response: {answer: "$4.2B", retrieval_context: {model, explore, measures, filters}}

Turn 2:
  Request:  {query: "Break that down by card product",
             history: [
               {role: "user", content: "Total billed business last quarter?"},
               {role: "assistant", content: "$4.2B"}
             ],
             last_retrieval_context: {model, explore, measures, filters}}
  Response: {answer: "By card product: Platinum $2.1B, Gold $1.3B...",
             retrieval_context: {model, explore, dimensions: ["card_prod_id"], ...}}
```

### Follow-Up Detection

When the intent classifier detects `follow_up` and `last_retrieval_context` is provided:

1. Reuse the previous model/explore/measures from `last_retrieval_context`
2. Merge new entities (e.g., `dimensions: ["card_prod_id"]`) with existing
3. Skip full retrieval -- go straight to prompt augmentation
4. Confidence is set to 0.85 (slightly lower, since we're modifying a previous result)

### Why Stateless

- **Horizontal scaling:** Any GKE replica can handle any request. No sticky sessions.
- **Frontend controls history:** ChatGPT Enterprise already manages conversation state. Duplicating it server-side is waste.
- **Debuggability:** Every request is self-contained. You can replay any request without server state.
- **Failure isolation:** If a server restarts, no sessions are lost.

### History Window

Max 20 messages (10 turns). Same as `chat.py`. Beyond 20, older messages are truncated. This keeps the LLM context window reasonable (~4K tokens for history) while preserving enough context for multi-turn.

---

## 13. Open Questions

| Question | Impact | Owner | Deadline |
|----------|--------|-------|----------|
| SafeChain embedding endpoint -- does it support text-embedding-005? | Blocks pgvector (Phase 1) | Verify with Ravi J | Before demo |
| ChatGPT Enterprise connector -- how does it send conversation history? | Affects QueryRequest shape | Saheb + ChatGPT team | Post-demo |
| Do we need authentication on the FastAPI endpoints? | Security | Saheb + Ashok | Before prod |
| Rate limiting -- do we need per-user query limits? | Cost control | Saheb | Post-demo |
| Trace storage -- PostgreSQL table or just in-memory? | Persistence | Saheb | Post-demo |
| SSE reconnection -- does the frontend handle dropped connections? | UX | Frontend team | Post-demo |

---

## 14. Implementation Priority

```
Phase 1 (Demo): CLI works end-to-end
  [x] pipeline/errors.py
  [x] pipeline/trace.py
  [x] pipeline/cortex_orchestrator.py
  [x] cli/cortex_cli.py

Phase 2 (Integration): API serves ChatGPT connector
  [ ] api/models.py
  [ ] api/events.py
  [ ] api/server.py
  [ ] api/middleware.py

Phase 3 (Production): Health, feedback, monitoring
  [ ] /health with real dependency checks
  [ ] /feedback with PostgreSQL persistence
  [ ] /trace with persistent storage
  [ ] /capabilities with dynamic field catalog
  [ ] Request authentication
  [ ] Rate limiting
```
