"""Cortex API server — FastAPI with SSE-streaming NL2SQL pipeline.

Endpoints (v1):
  POST /api/v1/query      -- Full pipeline with SSE streaming (new)
  POST /api/v1/followup   -- Follow-up within conversation (new)
  GET  /api/v1/trace/{id} -- Retrieve pipeline trace (new)
  GET  /api/v1/capabilities -- System capabilities (new)
  POST /api/v1/feedback   -- User feedback on results (new)
  GET  /api/v1/health     -- Component-level health check

Legacy (v0, kept for backward compat):
  POST /query             -- Retrieval-only (no SQL generation)
  GET  /health            -- Simple health check
  GET  /capabilities      -- Basic capabilities

Usage:
  uvicorn src.api.server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.retrieval.pipeline import retrieve_with_graph_validation, get_top_explore
from config.constants import EXPLORE_DESCRIPTIONS

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cortex API",
    description="NL2SQL pipeline for American Express via Looker semantic layer.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to ChatGPT Enterprise domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Orchestrator (initialized at startup) ────────────────────────────

_orchestrator = None


@app.on_event("startup")
async def _init_orchestrator():
    """Initialize the CortexOrchestrator at server startup.

    Connects to SafeChain, loads MCP tools, creates the ReAct agent.
    This happens ONCE — the orchestrator is reused across all requests.
    """
    global _orchestrator

    try:
        from ee_config.config import Config
        from safechain.tools.mcp import MCPToolLoader
        from access_llm.chat import AgentOrchestrator
        from src.pipeline.orchestrator import CortexOrchestrator, ConversationStore

        config = Config.from_env()
        tools = await MCPToolLoader.load_tools(config)
        logger.info("Loaded %d MCP tools", len(tools))

        react_agent = AgentOrchestrator(
            model_id="3",  # Gemini 2.5 Flash
            tools=tools,
            max_iterations=5,  # Reduced from 15 — augmented prompt cuts iterations
        )

        conversations = ConversationStore(max_turns=20)

        _orchestrator = CortexOrchestrator(
            react_agent=react_agent,
            conversations=conversations,
            classifier_model_idx="3",
        )

        # Pre-warm caches — first request won't pay cold-start penalties
        await _orchestrator.warm_up()

        logger.info("CortexOrchestrator initialized successfully")

    except Exception as e:
        logger.warning(
            "Orchestrator init failed: %s — v1 endpoints unavailable, v0 still works", e
        )
        _orchestrator = None


# ── Request / Response Models ────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class StreamingQueryRequest(BaseModel):
    query: str
    conversation_id: str | None = None
    session_id: str | None = None
    view_mode: str = "engineering"


class FollowUpRequest(BaseModel):
    query: str
    conversation_id: str
    session_id: str | None = None


class FeedbackRequest(BaseModel):
    trace_id: str
    rating: int | None = None
    filter_correction: dict | None = None
    comment: str | None = None


class HealthResponse(BaseModel):
    status: str
    safechain: str
    postgresql: str


# ── V1 Endpoints (SSE streaming) ─────────────────────────────────────

@app.post("/api/v1/query")
async def query_v1(request: StreamingQueryRequest):
    """Full NL2SQL pipeline with SSE streaming."""
    if _orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not initialized. Check server logs.",
        )

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    async def event_stream():
        async for event in _orchestrator.process_query(
            query=request.query,
            conversation_id=request.conversation_id,
            view_mode=request.view_mode,
        ):
            yield event.to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.post("/api/v1/followup")
async def followup_v1(request: FollowUpRequest):
    """Follow-up question within an existing conversation."""
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    async def event_stream():
        async for event in _orchestrator.process_query(
            query=request.query,
            conversation_id=request.conversation_id,
        ):
            yield event.to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/trace/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    """Retrieve full PipelineTrace for debugging / eval / Engineering View replay."""
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    trace = _orchestrator.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    return trace.to_dict()


@app.get("/api/v1/capabilities")
def capabilities_v1() -> dict[str, Any]:
    """Return system capabilities for the frontend."""
    explores = []
    for name, desc in EXPLORE_DESCRIPTIONS.items():
        explores.append({
            "name": name,
            "description": desc,
            "sample_questions": [],  # TODO: populate from golden dataset
        })

    return {
        "version": "1.0.0",
        "explores": explores,
        "features": {
            "streaming": True,
            "follow_ups": True,
            "disambiguation": True,
            "filter_resolution": True,
            "confidence_scores": True,
            "sql_transparency": True,
        },
        "limits": {
            "max_result_rows": 500,
            "max_conversation_turns": 20,
            "max_query_length": 2000,
        },
    }


@app.post("/api/v1/feedback")
async def feedback(request: FeedbackRequest) -> dict[str, str]:
    """Log user feedback on query results. Feeds the learning loop."""
    logger.info(
        "Feedback received: trace=%s rating=%s comment=%s",
        request.trace_id, request.rating, request.comment,
    )
    # TODO: persist to PostgreSQL query_logs table
    return {"status": "logged", "trace_id": request.trace_id}


@app.get("/api/v1/health")
async def health_v1() -> dict[str, Any]:
    """Component-level health check."""
    sc_status = _check_safechain()
    pg_status = _check_postgresql()

    components = {
        "safechain": {"status": sc_status},
        "postgresql": {"status": pg_status},
        "orchestrator": {"status": "ok" if _orchestrator else "not_initialized"},
    }

    overall = "ok" if all(
        c["status"] == "ok" for c in components.values()
    ) else "degraded"

    return {
        "status": overall,
        "components": components,
        "version": "1.0.0",
    }


# ── Legacy V0 Endpoints (backward compat) ────────────────────────────

@app.post("/query")
def query(request: QueryRequest) -> dict[str, Any]:
    """[V0] Run retrieval pipeline and return top explore with filters."""
    result = retrieve_with_graph_validation(request.query, top_k=request.top_k)
    return get_top_explore(result)


@app.get("/health")
async def health() -> HealthResponse:
    """[V0] Health check — verifies SafeChain and PostgreSQL connectivity."""
    sc_status = _check_safechain()
    pg_status = _check_postgresql()
    overall = "ok" if all(s == "ok" for s in [sc_status, pg_status]) else "degraded"
    return HealthResponse(status=overall, safechain=sc_status, postgresql=pg_status)


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """[V0] Return system capabilities for the frontend."""
    return {
        "version": "1.0.0",
        "mode": "full_pipeline",
        "features": {
            "explore_scoring": True,
            "filter_resolution": True,
            "confidence_scores": True,
            "near_miss_detection": True,
            "streaming": _orchestrator is not None,
        },
    }


# ── Health Check Helpers ──────────────────────────────────────────────

def _check_safechain() -> str:
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
