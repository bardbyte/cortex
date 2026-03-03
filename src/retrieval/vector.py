"""Vector search via Vertex AI Search.

Finds LookML fields whose descriptions are semantically similar to the user's query.

How it works:
  INDEXING (offline, triggered on LookML deploy):
    - One document per field (NOT per-view, NOT per-explore)
    - Each doc = field name + description + explore/view context + taxonomy synonyms
    - Structured metadata (structData) for filtering: field_type, view, explore, model
    - Embedding model: text-embedding-005 (768-dim, fine-tunable for Amex terminology)

  QUERYING (runtime, <200ms):
    - Embed extracted entities (e.g. "total spend", "merchant category")
    - Search corpus for top-K similar fields
    - Return FieldCandidate list ranked by cosine similarity

Why per-field chunking?
  Per-view returns 50 irrelevant fields alongside the 2 you need.
  Per-field lets retrieval pinpoint exact matches. Precision > recall here.

Fine-tuning opportunity:
  Google reports up to 41% improvement from domain-specific embedding tuning.
  Train pairs: ("CAC", "customer_acquisition_cost description") → positive
  This matters enormously for Amex financial terminology.

What to implement:
  1. build_search_corpus() — parse LookML, enrich with taxonomy, create docs
  2. index_corpus() — upload to Vertex AI Search datastore
  3. search() — query the corpus, return ranked FieldCandidates

Dependencies:
  - google-cloud-discoveryengine (Vertex AI Search client)
  - Taxonomy YAML files for synonym enrichment (src/taxonomy/)
  - Parsed LookML (use lkml library)
"""

from src.retrieval.models import FieldCandidate


def build_search_corpus(lookml_models: list, taxonomy: dict | None = None) -> list[dict]:
    """Build Vertex AI Search corpus from parsed LookML.

    Args:
        lookml_models: Parsed LookML model objects (from lkml library).
        taxonomy: Optional {field_name: TaxonomyEntry} for synonym enrichment.

    Returns:
        List of documents ready for Vertex AI Search ingestion.
        Each document:
          {
            "id": "model.explore.view.field",
            "content": "field_name is a [type] in [view], accessible through [explore]...",
            "structData": {"field_name", "field_type", "view", "explore", "model", ...}
          }
    """
    raise NotImplementedError


def search(
    query: str,
    *,
    project_id: str,
    datastore_id: str,
    top_k: int = 20,
    explore_filter: str | None = None,
) -> list[FieldCandidate]:
    """Search Vertex AI Search for semantically similar fields.

    Args:
        query: Natural language search text (e.g. "total spend").
        project_id: GCP project ID.
        datastore_id: Vertex AI Search datastore ID.
        top_k: Number of results to return.
        explore_filter: Optional explore name to scope results.

    Returns:
        FieldCandidate list ranked by semantic similarity.
    """
    raise NotImplementedError
