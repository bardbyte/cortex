"""Model adapter — SafeChain model access via CIBIS/IDaaS.

Model indices (from config.yml):
  "1" = Gemini 2.5 Pro (LLM, chat)
  "2" = BGE-large-en-v1.5 (embedding, 1024-dim)
  "3" = Gemini 2.5 Flash (LLM, chat)

Usage:
    from src.adapters.model_adapter import get_model
    embed_client = get_model('2')
    llm_client = get_model('1')
    vector = embed_client.embed_query("total spend")
"""

from __future__ import annotations

import logging

from ee_config.config import Config
from safechain.lcel import model

logger = logging.getLogger(__name__)

_config_initialized = False


def get_model(model_idx: str):
    """Get a SafeChain model client by config.yml index."""
    global _config_initialized
    if not _config_initialized:
        Config.from_env()
        _config_initialized = True
    return model(model_idx)
