"""Pipeline events for SSE streaming to the frontend.

Each pipeline step emits events that the ADK runner surfaces.
The FastAPI SSE endpoint serializes these as JSON for the frontend.

Event flow example:
  classify_intent:STARTED  ->  classify_intent:COMPLETED  ->
  retrieve_fields:STARTED  ->  retrieve_fields:COMPLETED  ->
  resolve_filters:COMPLETED ->
  validate_query:COMPLETED  ->
  query_execution:STARTED   ->  query_execution:COMPLETED ->
  format_response:STARTED   ->  format_response:COMPLETED ->
  pipeline:COMPLETED (with total timing)

Frontend rendering:
  [v] Classifying intent... (200ms)
  [v] Retrieving fields... (260ms)
  [v] Resolving filters... (15ms)
  [v] Validating query... (5ms)
  [ ] Executing query...

Note on ADK Event compatibility:
  ADK's Event base class is a Pydantic model (or dataclass, depending
  on version). PipelineStepEvent extends it so the ADK runner can yield
  it alongside standard LLM events. If the ADK Event class changes
  signature, this is a thin wrapper -- easy to adapt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    """Status of a pipeline step."""
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class PipelineStepEvent:
    """Event emitted at each pipeline step boundary.

    The ADK runner yields these alongside LLM events. The SSE endpoint
    serializes them for the frontend.

    NOTE: This is intentionally a plain dataclass, not inheriting from
    ADK's Event class. The CortexAgent yields these via a wrapper that
    the ADK runner treats as custom events. This avoids tight coupling
    to ADK's internal Event hierarchy, which has changed across versions.
    """

    step: str = ""
    status: StepStatus = StepStatus.STARTED
    detail: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_sse_dict(self) -> dict[str, Any]:
        """Serialize for Server-Sent Events."""
        return {
            "type": "pipeline_step",
            "step": self.step,
            "status": self.status.value,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 1),
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize as JSON string for SSE data field."""
        return json.dumps(self.to_sse_dict())


# ── Thinking Events ───────────────────────────────────────────────
# Reused from access_llm/chat.py for compatibility with the existing
# ConsoleThinkingCallback. The ADK pipeline emits these for the CLI
# and the SSE endpoint converts them for the web frontend.

class ThinkingType(str, Enum):
    """Types of thinking events for visualization."""
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"
    PIPELINE_STEP = "pipeline_step"


@dataclass
class ThinkingEvent:
    """Represents a thinking event from the agent.

    Compatible with the ConsoleThinkingCallback in access_llm/chat.py.
    """
    type: ThinkingType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_sse_dict(self) -> dict[str, Any]:
        """Serialize for SSE."""
        return {
            "type": self.type.value,
            "content": self.content,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize as JSON string."""
        return json.dumps(self.to_sse_dict())
