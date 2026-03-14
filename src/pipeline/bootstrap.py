"""Bootstrap the Cortex pipeline with all dependencies.

Single entry point that wires everything together.
Called once at server/CLI startup.

Architecture decision (per AI engineer review):
  v1 uses CortexOrchestrator (direct SafeChain calls) NOT CortexAgent
  (ADK BaseAgent). The BaseLlm adapter is skipped — too fragile for
  the 3-way format translation. CortexAgent is preserved for when we
  need full ADK integration (Agent Engine deployment). Two-way door.

Dependency graph:
  Config (SafeChain CIBIS)
    |
    +-- classifier: safechain.lcel.model("3") (Flash, no tools)
    +-- AgentOrchestrator: MCPToolAgent(Flash) + MCP tools (ReAct loop)
    |
  pg_conn (pgvector + Apache AGE)
    |
    +-- embed_fn: safechain.lcel.model("2").embed_query
    +-- RetrievalOrchestrator
    |
  CortexOrchestrator (root)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


async def create_cortex_orchestrator(
    sql_gen_only: bool = True,
    thinking_callback=None,
):
    """Wire up all dependencies and return a ready CortexOrchestrator.

    This function:
      1. Loads SafeChain config
      2. Creates classifier (Flash, no tools)
      3. Creates AgentOrchestrator (Flash + MCP tools, ReAct loop)
      4. Connects to PostgreSQL (pgvector + AGE)
      5. Creates embedding function
      6. Creates RetrievalOrchestrator
      7. Loads taxonomy terms
      8. Assembles CortexOrchestrator

    Args:
        sql_gen_only: If True (v1), only generate SQL, don't execute.
        thinking_callback: Optional callback for CLI thinking visualization.

    Returns:
        CortexOrchestrator instance ready for CLI or API.

    Raises:
        RuntimeError: If any critical dependency fails to initialize.
    """
    from src.connectors.safechain_client import (
        get_config,
        get_classifier,
        get_embed_fn,
        create_agent_orchestrator,
    )
    from src.pipeline.cortex_orchestrator import CortexOrchestrator
    from src.retrieval.orchestrator import RetrievalOrchestrator

    # ── Step 1: SafeChain config ──
    logger.info("[1/7] Loading SafeChain config...")
    config = await get_config()

    # ── Step 2: Classifier (Flash, no tools) ──
    logger.info("[2/7] Creating classifier (Flash)...")
    classifier = get_classifier()

    # ── Step 3: AgentOrchestrator (Flash + MCP tools) ──
    logger.info("[3/7] Creating AgentOrchestrator with MCP tools...")
    agent_orchestrator = await create_agent_orchestrator(
        config=config,
        sql_gen_only=sql_gen_only,
        thinking_callback=thinking_callback,
    )

    # ── Step 4: PostgreSQL connection ──
    logger.info("[4/7] Connecting to PostgreSQL (pgvector + AGE)...")
    pg_conn = _get_pg_connection()

    # ── Step 5: Embedding function ──
    logger.info("[5/7] Loading embedding model...")
    embed_fn = get_embed_fn()

    # ── Step 6: Retrieval orchestrator ──
    logger.info("[6/7] Creating retrieval orchestrator...")
    model_name = os.getenv("CORTEX_MODEL_NAME", "cortex_finance")
    retrieval = RetrievalOrchestrator(
        pg_conn=pg_conn,
        embed_fn=embed_fn,
        model_name=model_name,
    )

    # ── Step 7: Taxonomy terms ──
    logger.info("[7/7] Loading taxonomy terms...")
    taxonomy_terms = _load_taxonomy_terms()

    # ── Assemble CortexOrchestrator ──
    orchestrator = CortexOrchestrator(
        agent_orchestrator=agent_orchestrator,
        retrieval=retrieval,
        classifier_agent=classifier,
        embed_fn=embed_fn,
        taxonomy_terms=taxonomy_terms,
    )

    mcp_tool_count = len(agent_orchestrator.tools) if hasattr(agent_orchestrator, 'tools') else 0
    logger.info(
        "CortexOrchestrator ready: mcp_tools=%d, taxonomy_terms=%d, sql_gen_only=%s",
        mcp_tool_count,
        len(taxonomy_terms),
        sql_gen_only,
    )
    return orchestrator


def _get_pg_connection():
    """Get PostgreSQL connection using the existing postgres_age_client."""
    from src.connectors.postgres_age_client import get_engine
    engine = get_engine()
    logger.info("PostgreSQL engine ready")
    return engine


def _load_taxonomy_terms() -> list[str]:
    """Load business terms for intent classification.

    Sources (in priority order):
      1. config/taxonomy.yaml (manually curated business terms)
      2. Empty list (graceful degradation)
    """
    taxonomy_path = Path(__file__).resolve().parents[2] / "config" / "taxonomy.yaml"

    if taxonomy_path.exists():
        try:
            import yaml
            with open(taxonomy_path) as f:
                data = yaml.safe_load(f)
            terms = data.get("terms", [])
            logger.info("Loaded %d taxonomy terms from %s", len(terms), taxonomy_path)
            return terms
        except Exception as e:
            logger.warning("Failed to load taxonomy: %s", e)

    logger.info("No taxonomy file found -- classification will work without term hints")
    return []
