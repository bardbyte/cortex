"""SafeChain client -- raw SafeChain access for Cortex pipeline.

All LLM access at Amex goes through SafeChain (CIBIS authentication).
This module provides factory functions that return RAW SafeChain clients,
NOT wrapped in ADK's BaseLlm adapter.

Why raw clients instead of SafeChainLlm(BaseLlm)?
  The BaseLlm adapter adds a 3-way format translation (ADK ↔ LangChain ↔
  SafeChain) that introduces fragility without adding value for v1. The
  CortexOrchestrator calls SafeChain directly via LangChain-compatible
  interfaces, which is the same proven pattern as access_llm/chat.py.

  The BaseLlm adapter (safechain_llm.py) is preserved for when we need
  full ADK integration (Agent Engine, checkpointing). Two-way door.

Clients provided:
  1. classifier: model("3") -- Gemini Flash, LangChain-compatible, no tools
  2. agent_orchestrator: AgentOrchestrator -- Flash + Looker MCP tools (ReAct)
  3. reasoning: model("1") -- Gemini Pro, LangChain-compatible, no tools
  4. embed_fn: model("2").embed_query -- BGE embedding

Reference: access_llm/chat.py (same patterns, proven on corp laptop)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

from ee_config.config import Config
from safechain.tools.mcp import MCPToolLoader, MCPToolAgent
from safechain.lcel import model

logger = logging.getLogger(__name__)

# ── Model config indices (from config/config.yml) ────────────────
MODEL_IDX_PRO = "1"       # Gemini 2.5 Pro
MODEL_IDX_EMBED = "2"     # BGE-large-en embedding
MODEL_IDX_FLASH = "3"     # Gemini 2.5 Flash

# V1 tools: SQL generation only, no execution
V1_TOOL_ALLOWLIST = {
    "query_sql",       # generates SQL (no execution)
    "get_models",      # discover available models
    "get_explores",    # discover explores
    "get_dimensions",  # discover dimensions
    "get_measures",    # discover measures
}


async def get_config() -> Config:
    """Load SafeChain config with CIBIS authentication.

    Same Config.from_env() call proven in access_llm/chat.py.
    """
    config = Config.from_env()
    logger.info("SafeChain config loaded")
    return config


def get_classifier() -> Any:
    """Gemini Flash for intent classification -- fast, no tools.

    Returns a LangChain-compatible client. Call via:
        result = await classifier.ainvoke([HumanMessage(content=prompt)])
        text = result.content

    Uses config model idx "3" (Flash).
    """
    client = model(MODEL_IDX_FLASH)
    logger.info("Classifier ready (Flash, model_idx=%s)", MODEL_IDX_FLASH)
    return client


def get_reasoning_model() -> Any:
    """Gemini Pro for complex disambiguation -- accurate, no tools.

    Returns a LangChain-compatible client. Same interface as classifier.
    Uses config model idx "1" (Pro).
    """
    client = model(MODEL_IDX_PRO)
    logger.info("Reasoning model ready (Pro, model_idx=%s)", MODEL_IDX_PRO)
    return client


def get_embed_fn() -> Callable[[str], list[float]]:
    """BGE embedding function for vector search.

    Returns a callable: (text: str) -> list[float] (1024-dim).
    Uses config model idx "2" (BGE-large-en).
    """
    embed_client = model(MODEL_IDX_EMBED)

    def embed_fn(text: str) -> list[float]:
        return embed_client.embed_query(text)

    logger.info("Embedding function ready (model_idx=%s)", MODEL_IDX_EMBED)
    return embed_fn


async def create_agent_orchestrator(
    config: Config | None = None,
    system_prompt: str = "",
    max_iterations: int = 10,
    thinking_callback: Any | None = None,
    sql_gen_only: bool = True,
) -> Any:
    """Create an AgentOrchestrator (from chat.py) with Looker MCP tools.

    This is the Phase 2 ReAct execution engine. It wraps MCPToolAgent
    in a multi-turn loop: LLM calls tool → gets result → calls next tool
    → until final answer.

    Args:
        config: SafeChain Config. Loaded from env if None.
        system_prompt: System prompt (overridden per-query by CortexOrchestrator).
        max_iterations: Max ReAct loop iterations.
        thinking_callback: Optional callback for CLI visualization.
        sql_gen_only: If True (v1), filter out the 'query' tool (no execution).

    Returns:
        AgentOrchestrator instance ready for CortexOrchestrator.
    """
    # Import AgentOrchestrator from the proven PoC
    # access_llm/ is at the repo root alongside src/
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from access_llm.chat import AgentOrchestrator

    if config is None:
        config = await get_config()

    # Load MCP tools via SafeChain (proven path)
    all_tools = await MCPToolLoader.load_tools(config)
    logger.info("Loaded %d raw MCP tools", len(all_tools))

    # Filter for v1: SQL generation only
    if sql_gen_only:
        tools = [t for t in all_tools if t.name in V1_TOOL_ALLOWLIST]
        logger.info(
            "V1 mode: filtered to %d tools (%s)",
            len(tools),
            [t.name for t in tools],
        )
    else:
        tools = all_tools

    # Get model_id from config (same pattern as chat.py line 547)
    model_id = (
        getattr(config, "model_id", None)
        or getattr(config, "model", None)
        or getattr(config, "llm_model", None)
        or "gemini-2.5-flash"
    )

    orchestrator = AgentOrchestrator(
        model_id=model_id,
        tools=tools,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        thinking_callback=thinking_callback,
    )

    logger.info(
        "AgentOrchestrator ready (model=%s, tools=%d, max_iter=%d)",
        model_id, len(tools), max_iterations,
    )
    return orchestrator
