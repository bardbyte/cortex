"""Cortex pipeline — ADK-based agent orchestration.

The pipeline is built with Google's Agent Development Kit (ADK).
ADK gives us:
  - Tool-based agent architecture (each pipeline stage = a tool)
  - McpToolset for Looker MCP integration
  - Vertex AI Agent Engine for managed deployment
  - Session state management for multi-turn conversations

Key design constraint:
  The agent's system instructions constrain tool ordering to keep the
  pipeline deterministic: classify → extract → retrieve → generate → validate → format.
  ADK handles the orchestration, but the INSTRUCTIONS enforce the sequence.
"""
