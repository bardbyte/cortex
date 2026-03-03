"""MCP tool connection for ADK agents.

Two ways to load Looker MCP tools in Cortex:

  1. SafeChain's MCPToolLoader (see safechain_client.py)
     Pro: Proven, handles auth. Con: Returns LangChain-compatible tools.

  2. ADK's McpToolset (this module)
     Pro: ADK-native, supports tool_filter. Con: Needs MCP server URL.

For the ADK pipeline, use McpToolset (this module). For verification
and testing, use SafeChain's loader (see examples/verify_setup.py).

Prerequisites:
    MCP Toolbox running: ./toolbox --tools-file config/tools.yaml
    MCP_TOOLBOX_URL set in .env (default: http://localhost:5000)

References:
    ADK McpToolset: https://google.github.io/adk-docs/tools/mcp-tools/
    MCP Toolbox: https://googleapis.github.io/genai-toolbox/
"""

from __future__ import annotations

# The 5 Looker tools Cortex needs (out of 33 available).
# Fewer tools = less confusion for the agent.
CORTEX_TOOLS = {
    "get_models",
    "get_explores",
    "get_dimensions",
    "get_measures",
    "query_sql",
}

# Extended set for development and debugging.
DEV_TOOLS = CORTEX_TOOLS | {
    "get_filters",
    "get_parameters",
    "query",
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


async def get_looker_toolset() -> list:
    """Connect ADK to the Looker MCP server.

    Returns ADK-native tools for Agent(tools=[...]).

    Implementation:
        from google.adk.tools import McpToolset
        from mcp.client.sse import SseServerParams
        import os

        url = os.getenv("MCP_TOOLBOX_URL", "http://localhost:5000")
        toolset = McpToolset(
            connection_params=SseServerParams(url=f"{url}/sse"),
            tool_filter=lambda tool, _: tool_filter(tool.name),
        )
        return await toolset.load_tools()
    """
    raise NotImplementedError(
        "Implement: connect to MCP Toolbox via ADK McpToolset. "
        "Requires ./toolbox running at MCP_TOOLBOX_URL."
    )
