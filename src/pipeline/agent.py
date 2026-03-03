"""Cortex ADK agent definition.

This is the entry point. The agent is configured with:
  1. System instructions that enforce the pipeline sequence
  2. Tools for each pipeline stage (intent, extraction, retrieval, etc.)
  3. McpToolset for Looker MCP (query_sql, get_models, get_explores, etc.)
  4. Sub-agents for disambiguation and error recovery

Tool Access:
  Looker MCP tools via ADK McpToolset:
    from src.connectors.mcp_tools import get_looker_toolset, tool_filter

References:
  - ADK: https://google.github.io/adk-docs/
  - McpToolset: https://google.github.io/adk-docs/tools/mcp-tools/
  - Agent Engine: https://google.github.io/adk-docs/deploy/agent-engine/

Implementation guide:

  from google.adk import Agent
  from google.adk.tools import McpToolset
  from src.connectors.mcp_tools import get_looker_toolset, tool_filter

  # 1. Create Looker MCP toolset (5 tools, filtered from 33)
  #    See: src/connectors/mcp_tools.py

  # 2. Create pipeline stage tools
  #    - classify_intent: -> {intent, complexity}
  #    - extract_entities: -> structured entities
  #    - retrieve_fields: -> hybrid retrieval result
  #    - validate_sql: -> partition filter + cost check
  #    - format_response: -> progressive disclosure output

  # 3. System instruction — enforces:
  #    - Tool ordering: classify -> extract -> retrieve -> validate -> format
  #    - Boundaries: refuse predictions, PII, data modifications
  #    - Disambiguation: ask user when ambiguous, never guess
  #    - Cost: always verify partition filter before query

  # 4. Sub-agents
  #    - disambiguation_agent: present options for ambiguous queries
  #    - boundary_agent: graceful refusal with alternatives

  # 5. Assemble
  #    agent = Agent(
  #        model=<llm>,
  #        name="cortex",
  #        instruction=SYSTEM_INSTRUCTION,
  #        tools=[classify_intent, extract_entities, retrieve_fields,
  #               validate_sql, format_response, *looker_mcp_tools],
  #        sub_agents=[disambiguation_agent, boundary_agent],
  #    )
"""
