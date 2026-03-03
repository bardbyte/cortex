"""Few-shot golden query matching via FAISS.

Finds similar past queries that have known-correct field selections.
TailorSQL research shows historical query patterns improve accuracy by 2x.
A golden query isn't just a test case — it's a retrieval signal.

How it works:
  Two FAISS indices (both 768-dim, flat inner product):
    1. NL index — match by question similarity
       "total spend by merchant" ≈ "spending per merchant type"
    2. Structural index — match by schema pattern
       "explore:transactions dims:merchant_category measures:total_amount"

  At query time, search both indices and return the union of top-K matches.

Bootstrap strategy (you don't have golden queries yet):
  Source 1: Looker query history — export top 500 most-run queries per BU,
            use LLM to generate NL versions, human-validate pairings.
  Source 2: SME interviews — ask 3 analysts per BU their top 20 questions.
  Source 3: Synthetic — generate from explore schemas, manually validate.

What to implement:
  1. GoldenQueryStore class with add() and search_by_nl() methods
  2. Embedding + FAISS index management
  3. Loader from golden query JSON files (tests/golden_queries/)
  4. search() function returning FieldCandidates derived from matched golden queries

Dependencies:
  - faiss-cpu
  - An embedding model (text-embedding-005 or sentence-transformers)
  - Golden query JSON files (see tests/golden_queries/_template.json)
"""

from src.retrieval.models import FieldCandidate, GoldenQuery


def search(query: str, top_k: int = 5) -> list[FieldCandidate]:
    """Find golden queries similar to the input and return their field selections.

    Args:
        query: Natural language query from the user.
        top_k: Number of golden query matches to return.

    Returns:
        FieldCandidate list derived from matched golden queries.
    """
    raise NotImplementedError
