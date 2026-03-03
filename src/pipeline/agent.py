"""Cortex ADK agent definition.

This is the entry point. The agent is configured with:
  1. System instructions that enforce the pipeline sequence
  2. Tools for each pipeline stage (intent, extraction, retrieval, etc.)
  3. McpToolset for Looker MCP (query_sql, get_models, get_explores, etc.)
  4. Sub-agents for disambiguation and error recovery

LLM Access:
  All LLM calls go through SafeChain (CIBIS auth). Two integration paths:

  Path A — Custom BaseLlm wrapper (recommended):
    from src.connectors.safechain_client import get_config, create_agent
    config = get_config()
    # Implement google.adk.models.BaseLlm that routes through SafeChain
    agent = Agent(model=SafeChainLlm(config), ...)

  Path B — SafeChain agent with ADK orchestration structure:
    Use SafeChain's MCPToolAgent for LLM+tool execution,
    ADK Agent pattern for pipeline orchestration above it.

Tool Access:
  Looker MCP tools via ADK McpToolset:
    from src.connectors.mcp_tools import get_looker_toolset, tool_filter

References:
  - ADK: https://google.github.io/adk-docs/
  - McpToolset: https://google.github.io/adk-docs/tools/mcp-tools/
  - Agent Engine: https://google.github.io/adk-docs/deploy/agent-engine/
  - Connectors: src/connectors/safechain_client.py, src/connectors/mcp_tools.py

Implementation guide:

  from google.adk import Agent
  from google.adk.tools import McpToolset
  from src.connectors.mcp_tools import get_looker_toolset, tool_filter
  from src.connectors.safechain_client import get_config

  # 1. Authenticate via SafeChain
  #    config = get_config()

  # 2. Create Looker MCP toolset (5 tools, filtered from 33)
  #    See: src/connectors/mcp_tools.py

  # 3. Create pipeline stage tools
  #    - classify_intent: → {intent, complexity}
  #    - extract_entities: → structured entities
  #    - retrieve_fields: → hybrid retrieval result
  #    - validate_sql: → partition filter + cost check
  #    - format_response: → progressive disclosure output

  # 4. System instruction — enforces:
  #    - Tool ordering: classify → extract → retrieve → validate → format
  #    - Boundaries: refuse predictions, PII, data modifications
  #    - Disambiguation: ask user when ambiguous, never guess
  #    - Cost: always verify partition filter before query

  # 5. Sub-agents
  #    - disambiguation_agent: present options for ambiguous queries
  #    - boundary_agent: graceful refusal with alternatives

  # 6. Assemble
  #    agent = Agent(
  #        model=SafeChainLlm(config),
  #        name="cortex",
  #        instruction=SYSTEM_INSTRUCTION,
  #        tools=[classify_intent, extract_entities, retrieve_fields,
  #               validate_sql, format_response, *looker_mcp_tools],
  #        sub_agents=[disambiguation_agent, boundary_agent],
  #    )
"""
