"""Radix API server — FastAPI with SSE-streaming NL2SQL pipeline.

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

from ee_config.config import Config
from safechain.tools.mcp import MCPToolLoader, MCPToolAgent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from src.retrieval.pipeline import retrieve_with_graph_validation, get_top_explore
from src.pipeline.orchestrator import RadixOrchestrator, ConversationStore
from config.constants import EXPLORE_DESCRIPTIONS

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Radix API",
    description="NL2SQL pipeline for American Express via Looker semantic layer.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Orchestrator (initialized at startup) ────────────────────────────

_orchestrator = None


class ReactAgent:
    """ReAct loop over SafeChain's MCPToolAgent.

    Provides the .run(messages) interface RadixOrchestrator expects.
    """

    def __init__(self, model_id: str, tools: list, max_iterations: int = 10):
        self.agent = MCPToolAgent(model_id, tools)
        self.max_iterations = max_iterations

    @staticmethod
    def _to_langchain(messages: list[dict]) -> list:
        lc = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                lc.append(SystemMessage(content=content))
            elif role == "user":
                lc.append(HumanMessage(content=content))
            elif role == "assistant":
                lc.append(AIMessage(content=content))
            elif role == "tool":
                lc.append(ToolMessage(
                    content=content,
                    tool_call_id=msg.get("tool_call_id", ""),
                    name=msg.get("name", ""),
                ))
        return lc

    async def run(self, messages: list[dict]) -> dict:
        content = ""
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            result = await self.agent.ainvoke(self._to_langchain(messages))
            if isinstance(result, dict):
                content = result.get("content", "")
                tool_results = result.get("tool_results", [])
            else:
                content = getattr(result, "content", str(result))
                tool_results = []
            if not tool_results:
                return {"content": content}
            if content:
                messages.append({"role": "assistant", "content": content})
            for tr in tool_results:
                tool_name = tr.get("tool", "unknown")
                tool_content = (
                    f"Error: {tr['error']}" if "error" in tr
                    else str(tr.get("result", ""))
                )
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_content,
                    "tool_call_id": f"call_{iteration}_{tool_name}",
                })
        return {"content": content or f"Max iterations ({self.max_iterations}) reached."}


@app.on_event("startup")
async def _init_orchestrator():
    """Initialize the RadixOrchestrator at server startup.

    Connects to SafeChain, loads MCP tools, creates the ReAct agent.
    """
    global _orchestrator

    config = Config.from_env()
    tools = await MCPToolLoader.load_tools(config)
    logger.info("Loaded %d MCP tools", len(tools))

    react_agent = ReactAgent(
        model_id="3",  # Gemini 2.5 Flash
        tools=tools,
        max_iterations=10,
    )

    _orchestrator = RadixOrchestrator(
        react_agent=react_agent,
        conversations=ConversationStore(max_turns=20),
        classifier_model_idx="3",
    )

    await _orchestrator.warm_up()
    logger.info("RadixOrchestrator initialized")


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
            "X-Accel-Buffering": "no",
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
    """Retrieve full PipelineTrace for debugging and eval."""
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    trace = _orchestrator.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    return trace.to_dict()


STARTER_QUESTIONS: list[dict[str, str]] = [
    {
        "text": "What is the total billed business for the OPEN segment?",
        "difficulty": "easy",
        "explore": "finance_cardmember_360",
    },
    {
        "text": "How many attrited customers do we have by generation?",
        "difficulty": "medium",
        "explore": "finance_cardmember_360",
    },
    {
        "text": "What is our attrition rate for Q4 2025?",
        "difficulty": "hard",
        "explore": "finance_cardmember_360",
    },
    {
        "text": "What is the highest billed business by merchant category?",
        "difficulty": "medium",
        "explore": "finance_merchant_profitability",
    },
    {
        "text": "Show me the top 5 travel verticals by gross sales and booking count",
        "difficulty": "hard",
        "explore": "finance_travel_sales",
    },
    {
        "text": "Total card issuance volume year over year",
        "difficulty": "easy",
        "explore": "finance_card_issuance",
    },
]

_EXPLORE_QUESTIONS: dict[str, list[str]] = {}
for _q in STARTER_QUESTIONS:
    _EXPLORE_QUESTIONS.setdefault(_q["explore"], []).append(_q["text"])


@app.get("/api/v1/capabilities")
def capabilities_v1() -> dict[str, Any]:
    """Return system capabilities and available explores."""
    explores = []
    for name, desc in EXPLORE_DESCRIPTIONS.items():
        explores.append({
            "name": name,
            "description": desc,
            "sample_questions": _EXPLORE_QUESTIONS.get(name, []),
        })

    return {
        "version": "1.0.0",
        "explores": explores,
        "starter_questions": STARTER_QUESTIONS,
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
    """Log user feedback on query results for the learning loop."""
    logger.info(
        "Feedback received: trace=%s rating=%s comment=%s",
        request.trace_id, request.rating, request.comment,
    )
    # TODO: persist to PostgreSQL query_logs table
    return {"status": "logged", "trace_id": request.trace_id}


@app.get("/api/v1/health")
async def health_v1() -> dict[str, Any]:
    """Component-level health check across SafeChain, PostgreSQL, and orchestrator."""
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
    """[V0] Retrieval-only endpoint (no SQL generation)."""
    result = retrieve_with_graph_validation(request.query, top_k=request.top_k)
    return get_top_explore(result)


@app.get("/health")
async def health() -> HealthResponse:
    """[V0] Simple health check."""
    sc_status = _check_safechain()
    pg_status = _check_postgresql()
    overall = "ok" if all(s == "ok" for s in [sc_status, pg_status]) else "degraded"
    return HealthResponse(status=overall, safechain=sc_status, postgresql=pg_status)


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """[V0] Basic capabilities."""
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
        Config.from_env()
        return "ok"
    except Exception as e:
        logger.warning("SafeChain health check failed: %s", e)
        return f"error: {e}"


def _check_postgresql() -> str:
    from src.connectors.postgres_age_client import get_engine
    from sqlalchemy import text
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        logger.warning("PostgreSQL health check failed: %s", e)
        return f"error: {e}"
