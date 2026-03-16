"""Cortex API server -- FastAPI with retrieval pipeline.

Endpoints:
  POST /query         -- Run retrieval pipeline, return scored explores + filters
  GET  /health        -- Health check (SafeChain, PostgreSQL)

Usage:
  uvicorn src.api.server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.retrieval.pipeline import retrieve_with_graph_validation, get_top_explore

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cortex API",
    description="NL2SQL retrieval pipeline for American Express via Looker semantic layer.",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to ChatGPT Enterprise domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ─────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class HealthResponse(BaseModel):
    status: str
    safechain: str
    postgresql: str


# ── Endpoints ─────────────────────────────────────────────────────

@app.post("/query")
def query(request: QueryRequest) -> dict[str, Any]:
    """Run retrieval pipeline and return top explore with filters."""
    result = retrieve_with_graph_validation(request.query, top_k=request.top_k)
    return get_top_explore(result)


@app.get("/health")
async def health() -> HealthResponse:
    """Health check — verifies SafeChain and PostgreSQL connectivity."""
    sc_status = _check_safechain()
    pg_status = _check_postgresql()

    overall = "ok" if all(s == "ok" for s in [sc_status, pg_status]) else "degraded"

    return HealthResponse(status=overall, safechain=sc_status, postgresql=pg_status)


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """Return system capabilities for the frontend."""
    return {
        "version": "0.4.0",
        "mode": "retrieval_only",
        "features": {
            "explore_scoring": True,
            "filter_resolution": True,
            "confidence_scores": True,
            "near_miss_detection": True,
        },
    }


# ── Health Check Helpers ──────────────────────────────────────────

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
