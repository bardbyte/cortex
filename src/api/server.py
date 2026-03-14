"""Cortex API server -- FastAPI with SSE streaming.

Endpoints:
  POST /query         -- Synchronous query, returns full CortexResponse
  POST /query/stream  -- SSE streaming, pipeline events + response
  GET  /health        -- Health check (SafeChain, PostgreSQL, FAISS)
  POST /feedback      -- User feedback for learning loop (ADR-008)
  GET  /trace/{id}    -- Retrieve pipeline trace by ID

Architecture decision (AI engineer review):
  v1 uses CortexOrchestrator directly (proven SafeChain path), NOT
  ADK Runner. The ADK Runner + SafeChainLlm adapter path is preserved
  in CortexAgent for when we need Agent Engine deployment. Two-way door.

Usage:
  uvicorn src.api.server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cortex API",
    description="NL2SQL pipeline for American Express via Looker semantic layer.",
    version="0.3.0",
)

# CORS -- restrictive in production, permissive in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to ChatGPT Enterprise domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ─────────────────────────────────────

class QueryRequest(BaseModel):
    """Request body for /query and /query/stream."""
    query: str
    history: list[dict] = []
    session_id: str | None = None
    user_id: str | None = None
    debug: bool = False


class FeedbackRequest(BaseModel):
    """Request body for /feedback."""
    query: str
    session_id: str
    rating: int | None = None           # 1-5
    filter_correction: dict | None = None  # {user_term, correct_value, dimension}
    comment: str | None = None


class HealthResponse(BaseModel):
    """Response for /health."""
    status: str
    safechain: str
    postgresql: str
    faiss: str


# ── Globals (initialized at startup) ──────────────────────────────

_orchestrator = None


@app.on_event("startup")
async def startup():
    """Initialize CortexOrchestrator at server start."""
    global _orchestrator

    from src.pipeline.bootstrap import create_cortex_orchestrator

    logger.info("Starting Cortex API server...")

    try:
        _orchestrator = await create_cortex_orchestrator(sql_gen_only=True)
        logger.info("CortexOrchestrator ready.")
    except Exception as e:
        logger.error("Failed to initialize Cortex: %s", e, exc_info=True)
        raise


# ── Endpoints ─────────────────────────────────────────────────────

@app.post("/query")
async def query(request: QueryRequest) -> dict:
    """Synchronous query endpoint. Returns full response + trace."""
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Cortex not initialized")

    result = await _orchestrator.run(
        query=request.query,
        conversation_history=request.history,
        debug=request.debug,
    )
    return result


@app.post("/query/stream")
async def query_stream(request: QueryRequest) -> StreamingResponse:
    """SSE streaming endpoint. Streams pipeline events + response.

    Event types:
      step_start          -- Pipeline step beginning
      step_complete       -- Pipeline step finished (with duration_ms)
      answer              -- Final response dict
      error               -- Error occurred
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Cortex not initialized")

    async def event_generator():
        try:
            async for event in _orchestrator.run_streaming(
                query=request.query,
                conversation_history=request.history,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error("Stream error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'event_type': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'event_type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/trace/{trace_id}")
async def get_trace(trace_id: str) -> dict:
    """Retrieve a pipeline trace by ID."""
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Cortex not initialized")

    trace = _orchestrator.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    return trace.to_dict()


@app.get("/health")
async def health() -> HealthResponse:
    """Health check -- verifies SafeChain, PostgreSQL, and FAISS."""
    sc_status = await _check_safechain()
    pg_status = _check_postgresql()
    faiss_status = _check_faiss()

    overall = "ok" if all(
        s == "ok" for s in [sc_status, pg_status, faiss_status]
    ) else "degraded"

    return HealthResponse(
        status=overall,
        safechain=sc_status,
        postgresql=pg_status,
        faiss=faiss_status,
    )


@app.post("/feedback")
async def feedback(request: FeedbackRequest) -> dict:
    """User feedback on query results. Feeds learning loop (ADR-008)."""
    logger.info(
        "Feedback received: session=%s, rating=%s, correction=%s",
        request.session_id,
        request.rating,
        request.filter_correction,
    )

    if request.filter_correction:
        logger.info(
            "Filter correction: user_term=%s -> correct_value=%s (dimension=%s)",
            request.filter_correction.get("user_term"),
            request.filter_correction.get("correct_value"),
            request.filter_correction.get("dimension"),
        )

    return {"status": "logged", "session_id": request.session_id}


@app.get("/capabilities")
async def capabilities() -> dict:
    """Return system capabilities for the frontend."""
    return {
        "version": "0.3.0",
        "mode": "sql_gen_only",
        "features": {
            "sql_generation": True,
            "sql_execution": False,
            "streaming": True,
            "confidence_scores": True,
            "pipeline_trace": True,
            "feedback": True,
        },
    }


# ── Health Check Helpers ──────────────────────────────────────────

async def _check_safechain() -> str:
    try:
        from ee_config.config import Config
        Config.from_env()
        return "ok"
    except Exception as e:
        logger.warning("SafeChain health check failed: %s", e)
        return f"error: {e}"


def _check_postgresql() -> str:
    try:
        from src.connectors.postgres_age_client import get_engine
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        logger.warning("PostgreSQL health check failed: %s", e)
        return f"error: {e}"


def _check_faiss() -> str:
    try:
        from src.retrieval import fewshot  # noqa: F401
        return "ok"
    except Exception as e:
        logger.warning("FAISS health check failed: %s", e)
        return f"error: {e}"
