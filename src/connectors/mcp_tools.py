"""MCP tool connection for ADK agents.

Two ways to load Looker MCP tools in Cortex:

  1. SafeChain's MCPToolLoader (see safechain_client.py)
     Pro: Proven, handles auth. Con: Returns LangChain-compatible tools.

  2. ADK's McpToolset (this module)
     Pro: ADK-native, supports tool_filter. Con: Needs MCP server URL.

For the ADK pipeline, use McpToolset (this module). For verification
and testing, use SafeChain's loader (see examples/verify_setup.py).

IMPORTANT: The production CORTEX_TOOLS set includes BOTH query_sql and
query as separate tools. This enables the two-step validation flow:
  1. query_sql generates SQL (no execution)
  2. validate_sql checks the SQL
  3. query executes and returns data

Prerequisites:
    MCP Toolbox running: ./toolbox --tools-file config/tools.yaml
    MCP_TOOLBOX_URL set in .env (default: http://localhost:5000)

References:
    ADK McpToolset: https://google.github.io/adk-docs/tools/mcp-tools/
    MCP Toolbox: https://googleapis.github.io/genai-toolbox/
    Looker query_sql: https://googleapis.github.io/genai-toolbox/resources/tools/looker/looker-query-sql/
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# The 6 Looker tools Cortex needs (out of 33 available).
# Fewer tools = less confusion for the agent.
# NOTE: query AND query_sql are both needed for the validate-then-execute flow.
CORTEX_TOOLS = {
    "get_models",
    "get_explores",
    "get_dimensions",
    "get_measures",
    "query_sql",     # generates SQL only (no execution)
    "query",         # executes and returns data
}

# Extended set for development and debugging.
DEV_TOOLS = CORTEX_TOOLS | {
    "get_filters",
    "get_parameters",
    "run_look",
    "get_dashboards",
    "get_projects",
    "get_project_files",
    "get_project_file",
}


def tool_filter(tool_name: str, production: bool = True) -> bool:
    """Filter for ADK McpToolset. Restricts agent to needed tools only.

    MCP tool names use hyphens, ADK normalizes to underscores.
    """
    allowlist = CORTEX_TOOLS if production else DEV_TOOLS
    return tool_name.replace("-", "_") in allowlist


async def get_looker_toolset(production: bool = True) -> list:
    """Connect ADK to the Looker MCP server via ADK McpToolset.

    Returns ADK-native tools for Agent(tools=[...]).

    Requires MCP Toolbox running at MCP_TOOLBOX_URL.
    The toolset connects over SSE (Server-Sent Events) to the
    MCP Toolbox sidecar, which proxies to the Looker API.

    Args:
        production: If True, filters to CORTEX_TOOLS (6 tools).
            If False, includes DEV_TOOLS (13 tools) for debugging.

    Returns:
        List of ADK-native tool objects.
    """
    from google.adk.tools import McpToolset
    from mcp.client.sse import SseServerParams

    url = os.getenv("MCP_TOOLBOX_URL", "http://localhost:5000")

    toolset = McpToolset(
        connection_params=SseServerParams(url=f"{url}/sse"),
        tool_filter=lambda tool, _ctx: tool_filter(tool.name, production),
    )
    tools = await toolset.load_tools()

    tool_names = [t.name for t in tools]
    logger.info(
        "Loaded %d Looker MCP tools via ADK McpToolset: %s",
        len(tools),
        tool_names,
    )
    return tools
