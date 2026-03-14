"""Cortex pipeline error hierarchy.

Every error carries the step name where it occurred and whether the
pipeline can recover (fall back to raw AgentOrchestrator) or must abort.

Recovery matrix:
  ClassificationError   -> recoverable (skip to Phase 2 raw)
  RetrievalError        -> recoverable (skip to Phase 2 raw)
  FilterResolutionError -> recoverable (use raw filter values)
  SafeChainError        -> NOT recoverable (no LLM access at all)
  PipelineTimeoutError  -> NOT recoverable (budget exhausted)
  SQLValidationError    -> NOT recoverable (SQL is unsafe)

Usage from CortexOrchestrator:
    try:
        classification = await self._classify(query, history, trace)
    except ClassificationError as e:
        # e.recoverable is True -> fall back to raw AgentOrchestrator
        return await self._fallback(query, history, trace, str(e))
    except SafeChainError as e:
        # e.recoverable is False -> return error, no fallback possible
        return self._error_response(query, str(e), trace, step=e.step)
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
