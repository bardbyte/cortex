"""Model adapter — unified interface for SafeChain (production) and local dev.

In production (Amex), models are accessed via SafeChain's IDaaS/CIBIS auth layer.
For local development, we fall back to open-source models:
  - Embedding: sentence-transformers BAAI/bge-large-en-v1.5 (1024-dim)
  - LLM: Anthropic Claude via API (requires ANTHROPIC_API_KEY)

Usage:
    from src.adapters.model_adapter import get_model
    embed_client = get_model('2')       # Embedding model
    llm_client = get_model('1')         # LLM model
    vector = embed_client.embed_query("total spend")
    text = llm_client.invoke("Extract entities from: ...")
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def get_model(model_idx: str):
    """Get a model client. Tries SafeChain first, falls back to local."""
    try:
        from safechain.lcel import model
        client = model(model_idx)
        logger.info("Using SafeChain model idx=%s", model_idx)
        return client
    except (ImportError, Exception) as e:
        logger.info("SafeChain unavailable (%s), using local adapter for idx=%s", e, model_idx)
        return LocalModelClient(model_idx)


class LocalModelClient:
    """Local development model client using open-source models."""

    def __init__(self, model_idx: str):
        self.model_idx = model_idx
        self._embed_model = None
        self._llm_client = None

        if model_idx == '2':
            self._init_embedding()
        elif model_idx == '1':
            self._init_llm()

    def _init_embedding(self):
        """Initialize BGE-large-en-v1.5 via sentence-transformers."""
        try:
            from sentence_transformers import SentenceTransformer
            self._embed_model = SentenceTransformer('BAAI/bge-large-en-v1.5')
            logger.info("Loaded BGE-large-en-v1.5 (1024-dim) for local embedding")
        except ImportError:
            raise ImportError(
                "sentence-transformers required for local embedding. "
                "Install: pip install 'cortex[local]'"
            )

    def _init_llm(self):
        """Initialize LLM — tries Anthropic Claude, then falls back to None."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            try:
                import anthropic
                self._llm_client = anthropic.Anthropic(api_key=api_key)
                logger.info("Using Anthropic Claude for local LLM")
                return
            except ImportError:
                pass

        logger.warning(
            "No LLM available for local dev. Set ANTHROPIC_API_KEY or install anthropic. "
            "Entity extraction will use rule-based fallback."
        )

    def embed_query(self, text: str) -> list[float]:
        """Generate embedding for text using BGE-large-en-v1.5."""
        if self._embed_model is None:
            raise RuntimeError("Embedding model not initialized")
        embedding = self._embed_model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def invoke(self, prompt: str) -> str:
        """Run LLM inference for entity extraction."""
        if self._llm_client is not None:
            response = self._llm_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        # Rule-based fallback for known demo queries
        return self._rule_based_extract(prompt)

    @staticmethod
    def _rule_based_extract(prompt: str) -> str:
        """Rule-based entity extraction for known query patterns."""
        prompt_lower = prompt.lower()

        # Match known demo queries
        if "total billed business" in prompt_lower and "open" in prompt_lower:
            return json.dumps({
                "measures": ["total billed business"],
                "dimensions": [],
                "time_range": None,
                "filters": [{"field_hint": "bus_seg", "values": ["OPEN"], "operator": "="}],
            })

        if "attrited" in prompt_lower and "generation" in prompt_lower:
            return json.dumps({
                "measures": ["attrited customer count"],
                "dimensions": ["generation"],
                "time_range": None,
                "filters": [],
            })

        if "attrition rate" in prompt_lower:
            return json.dumps({
                "measures": ["attrition rate"],
                "dimensions": [],
                "time_range": "Q4 2025",
                "filters": [],
            })

        if "highest" in prompt_lower and "merchant" in prompt_lower:
            return json.dumps({
                "measures": ["max merchant spend"],
                "dimensions": ["merchant category"],
                "time_range": None,
                "filters": [],
            })

        if "top 5" in prompt_lower and "travel" in prompt_lower:
            return json.dumps({
                "measures": ["total gross sales", "total bookings"],
                "dimensions": ["travel vertical"],
                "time_range": None,
                "filters": [],
            })

        if "millennial" in prompt_lower and "apple pay" in prompt_lower:
            return json.dumps({
                "measures": ["active customers"],
                "dimensions": [],
                "time_range": None,
                "filters": [
                    {"field_hint": "generation", "values": ["Millennial"], "operator": "="},
                    {"field_hint": "apple_pay_wallet_flag", "values": ["Y"], "operator": "="},
                ],
            })

        # Generic fallback
        return json.dumps({
            "measures": ["count"],
            "dimensions": [],
            "time_range": None,
            "filters": [],
        })
