"""SafeChain LLM client — authenticates Cortex to call Gemini.

All LLM access at Amex goes through SafeChain (CIBIS authentication).
This module will bridge SafeChain auth into the ADK pipeline.

Status: NOT YET IMPLEMENTED — see GitHub issue.

When implemented, this module should:
  1. Load CIBIS credentials and authenticate via SafeChain
  2. Provide a BaseLlm adapter so ADK Agent can route through SafeChain
  3. Handle model routing (config.yml → model_id)

Reference: access_llm/ PoC (SafeChain + MCPToolAgent pattern)
"""

from __future__ import annotations

from typing import Any


def get_config() -> Any:
    """Load SafeChain config with CIBIS authentication.

    Returns:
        Authenticated config object.
    """
    raise NotImplementedError("LLM access pathway — not yet set up. See GitHub issue.")


def create_llm_adapter(config: Any) -> Any:
    """Create an ADK-compatible BaseLlm that routes through SafeChain.

    Returns:
        google.adk.models.BaseLlm instance.
    """
    raise NotImplementedError("LLM access pathway — not yet set up. See GitHub issue.")
