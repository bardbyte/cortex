"""SafeChain LLM client — authenticates Cortex to call Gemini.

All LLM access at Amex goes through SafeChain (CIBIS authentication).
This module wraps that authentication for use by the Cortex pipeline.

How it works:
    ee_config.Config.from_env()
        → reads .env (CIBIS_CONSUMER_KEY, CIBIS_CONSUMER_SECRET, CIBIS_CONFIGURATION_ID)
        → reads config.yml (model_id, endpoint routing)
        → returns authenticated Config object

    MCPToolLoader.load_tools(config)
        → connects to running MCP Toolbox server
        → returns list of tool objects (Looker tools)

    MCPToolAgent(model_id, tools)
        → creates an agent with authenticated LLM + tool bindings
        → ainvoke([messages]) to call

For ADK integration, wrap this in a custom BaseLlm:
    - Implement google.adk.models.BaseLlm
    - Route generate_content() through SafeChain's authenticated client
    - Pass to Agent(model=SafeChainLlm(config))

Required .env variables:
    CIBIS_CONSUMER_KEY, CIBIS_CONSUMER_SECRET, CIBIS_CONFIGURATION_ID, CONFIG_PATH

Run examples/verify_setup.py to confirm this works in your environment.
"""

from __future__ import annotations

from typing import Any


def get_config() -> Any:
    """Load SafeChain config with CIBIS authentication.

    Returns:
        ee_config.config.Config with auth resolved.

    Implementation:
        from ee_config.config import Config
        return Config.from_env()
    """
    raise NotImplementedError(
        "Implement: from ee_config.config import Config; return Config.from_env()"
    )


async def load_tools(config: Any) -> list:
    """Load MCP tools from the running Toolbox server.

    Args:
        config: Config from get_config().

    Returns:
        List of tool objects for MCPToolAgent.

    Implementation:
        from safechain.tools.mcp import MCPToolLoader
        return await MCPToolLoader.load_tools(config)
    """
    raise NotImplementedError(
        "Implement: from safechain.tools.mcp import MCPToolLoader; "
        "return await MCPToolLoader.load_tools(config)"
    )


def get_model_id(config: Any) -> str:
    """Extract model_id from config (set in config.yml, not .env).

    Implementation:
        return (
            getattr(config, 'model_id', None)
            or getattr(config, 'model', None)
            or getattr(config, 'llm_model', None)
            or 'gemini-pro'
        )
    """
    raise NotImplementedError(
        "Implement: read model_id from config attributes"
    )


def create_agent(model_id: str, tools: list) -> Any:
    """Create an authenticated agent with LLM + tool bindings.

    This is the SafeChain agent. For Cortex, wrap this in ADK's
    Agent class via a custom BaseLlm adapter.

    Implementation:
        from safechain.tools.mcp import MCPToolAgent
        return MCPToolAgent(model_id, tools)
    """
    raise NotImplementedError(
        "Implement: from safechain.tools.mcp import MCPToolAgent; "
        "return MCPToolAgent(model_id, tools)"
    )
