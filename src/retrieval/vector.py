"""Entity extraction and vector field matching for retrieval.

This module implements a query-to-entities retrieval flow:
  1) Extract structured entities from natural language using LLM.
  2) Normalize extracted entities to reduce model drift.
  3) Generate embeddings for measures/dimensions with BGE instruction prefix.
  4) Search pgvector 'field_embeddings' for top-k similar fields.
  5) Return output with candidates and filters for downstream SQL planning.

Usage:
    python -m src.retrieval.vector
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import text
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """Custom SQLAlchemy type for pgvector."""
    cache_ok = True
    name = "vector"


from src.adapters.model_adapter import get_model
from config.constants import (
    LLM_MODEL_IDX,
    EMBED_MODEL_IDX,
    BGE_QUERY_PREFIX,
    SQL_SEARCH_SIMILAR_FIELDS,
    SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE,
)
from src.connectors.postgres_age_client import get_engine

logger = logging.getLogger(__name__)


def _bootstrap_environment() -> None:
    """Load .env and ensure CONFIG_PATH is available for safechain/ee_config."""
    load_dotenv(find_dotenv())
    if not os.getenv("CONFIG_PATH"):
        repo_root = Path(__file__).resolve().parents[2]
        default_config_path = repo_root / "config" / "config.yml"
        os.environ["CONFIG_PATH"] = str(default_config_path)
        logger.info("[retrieval.vector] CONFIG_PATH set to: %s", default_config_path)
    else:
        logger.info("[retrieval.vector] CONFIG_PATH already set to: %s", os.getenv("CONFIG_PATH"))


_bootstrap_environment()


@dataclass
class ExtractedEntity:
    """Represents an extracted entity from user query."""
    entity_type: str
    raw_text: str
    embedding: list[float] | None = None


@dataclass
class FieldMatch:
    """Represents a matched field from the database."""
    field_key: str
    field_name: str
    label: str | None
    explore_name: str
    view_name: str
    similarity: float
    field_type: str | None = None
    measure_type: str | None = None


@dataclass
class EntityCandidate:
    """Represents a candidate field match for an entity."""
    explore: str
    field_key: str
    field_name: str
    similarity: float


@dataclass
class Entity:
    """Represents an entity in the structured output format."""
    id: str
    type: str
    weight: float
    candidates: list[EntityCandidate] | None = None
    operators: list[str] | None = None
    values: list[str] | None = None


@dataclass
class ExtractedEntities:
    """Structured entity extraction result."""
    measures: list[str]
    dimensions: list[str]
    time_range: str | None
    filters: list[dict[str, Any]]


class EntityExtractor:
    """Extract entities from user queries and match them to database fields."""

    ENTITY_EXTRACTION_PROMPT = """You are an expert at extracting structured entities from natural language queries about business data.

Given a user question, extract:
1. measures: KPIs or numerics being requested
2. dimensions: categories/attributes being requested (do not include filter values here)
3. time_range: time expression if present
4. filters: explicit filter conditions

For filters:
  - Use "field_hint" to describe the conceptual field
  - Extract raw values exactly as written
  - Do NOT add partition filters
  - Do NOT duplicate filter values in dimensions
  - If there is no explicit aggregation intent (count/sum/avg/total), prefer returning dimensions + filters and keep measures empty

Return ONLY valid JSON.

Example:
  User: "Customer counts for Millennial customers last quarter"
  Output:
  {{
    "measures": ["customer count"],
    "dimensions": ["generation"],
    "time_range": "last quarter",
    "filters": [
        {{"field_hint": "generation",
         "values": ["Millennial"],
         "operator": "="}}
    ]
  }}

Now extract entities from this query:
  User: "{query}"
  Output:
"""

    METRIC_INTENT_TERMS = {
        "count", "number", "numbers", "total", "sum", "average",
        "maximum", "max", "minimum", "min", "rate", "ratio", "percent",
        "how many", "highest", "lowest", "top",
    }

    GENERIC_CUSTOMER_MEASURES = {
        "customer count",
        "customer's count",
    }

    def __init__(self, llm_model_idx: str = LLM_MODEL_IDX, embedding_model_idx: str = EMBED_MODEL_IDX):
        self.llm_model_idx = llm_model_idx
        self.embedding_model_idx = embedding_model_idx
        logger.info("Initializing LLM model '%s' for entity extraction", llm_model_idx)
        self.llm_client = get_model(llm_model_idx)
        logger.info("Initializing embedding model '%s' for vector search", embedding_model_idx)
        self.embedding_client = get_model(embedding_model_idx)

    def _has_metric_intent(self, query: str) -> bool:
        lowered = query.lower()
        return any(term in lowered for term in self.METRIC_INTENT_TERMS)

    def _normalize_terms(self, query: str, extracted: ExtractedEntities) -> ExtractedEntities:
        logger.info("Normalizing entities for query '%s'", query)
        logger.info(
            "Extracted: measures=%d, dimensions=%d, filters=%d",
            len(extracted.measures),
            len(extracted.dimensions),
            len(extracted.filters),
        )

        dimensions = list(extracted.dimensions)
        measures = list(extracted.measures)

        has_metric_intent = self._has_metric_intent(query)
        query_lower = query.lower()

        if not dimensions and ("customer" in query_lower or "customers" in query_lower):
            dimensions.append("customer")

        if has_metric_intent and not measures:
            for term in self.GENERIC_CUSTOMER_MEASURES:
                if term in query_lower:
                    measures.append(term)
                    break

        if has_metric_intent and not measures:
            measures.append("count")

        return ExtractedEntities(
            measures=measures,
            dimensions=dimensions,
            time_range=extracted.time_range,
            filters=extracted.filters,
        )

    def extract_entities(self, query: str) -> ExtractedEntities:
        prompt = self.ENTITY_EXTRACTION_PROMPT.format(query=query)
        try:
            json_str = self.llm_client.invoke(prompt)
            entities_dict = json.loads(json_str)

            measures = entities_dict.get("measures")
            if measures is None:
                measures = entities_dict.get("Metrics")
            if measures is None:
                measures = entities_dict.get("metrics")
            if measures is None:
                measures = []

            dimensions = entities_dict.get("dimensions")
            if dimensions is None:
                dimensions = entities_dict.get("Dimensions")
            if dimensions is None:
                dimensions = []

            time_range = entities_dict.get("time_range")
            if time_range is None:
                time_range = entities_dict.get("Time_range")

            filters = entities_dict.get("filters")
            if filters is None:
                filters = entities_dict.get("Filters")
            if filters is None:
                filters = []

            return ExtractedEntities(
                measures=measures or [],
                dimensions=dimensions or [],
                time_range=time_range,
                filters=filters or [],
            )
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM response as JSON: %s", exc)
            return ExtractedEntities(measures=[], dimensions=[], time_range=None, filters=[])
        except Exception as exc:
            logger.error("Error during entity extraction: %s", exc)
            return ExtractedEntities(measures=[], dimensions=[], time_range=None, filters=[])

    def embed_text(self, text: str, is_query: bool = True) -> list[float]:
        """Generate embedding with BGE instruction prefix for queries.

        BGE-large-en-v1.5 was trained with asymmetric instructions:
        - Queries need prefix: "Represent this sentence for searching relevant passages: "
        - Documents do NOT get a prefix (they're embedded as-is)
        Omitting the prefix on queries reduces accuracy by 2-5%.
        """
        if is_query:
            text = BGE_QUERY_PREFIX + text
        logger.info("Generating embedding for text snippet (len=%d, is_query=%s)", len(text), is_query)
        return self.embedding_client.embed_query(text)

    def search_similar_fields(
        self,
        entity_text: str,
        embedding: list[float],
        limit: int = 10,
        field_type: str | None = None,
    ) -> list[FieldMatch]:
        """Search pgvector for similar fields, optionally filtered by type."""
        engine = get_engine()
        embedding_literal = "[" + ", ".join(str(x) for x in embedding) + "]"

        with engine.connect() as conn:
            if field_type:
                result = conn.execute(
                    text(SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE).bindparams(
                        embedding=embedding_literal,
                        field_type=field_type,
                        limit=limit,
                    )
                )
            else:
                result = conn.execute(
                    text(SQL_SEARCH_SIMILAR_FIELDS).bindparams(
                        embedding=embedding_literal,
                        limit=limit,
                    )
                )
            rows = result.fetchall()

        results = [
            FieldMatch(
                field_key=row[0],
                field_name=row[1],
                label=row[2],
                explore_name=row[3],
                view_name=row[4],
                field_type=row[5],
                measure_type=row[6],
                similarity=float(row[7]),
            )
            for row in rows
        ]
        return results

    def process_query(self, query: str, top_k: int = 5) -> dict[str, Any]:
        logger.info("Starting process_query for query='%s' with top_k=%d", query, top_k)
        extracted = self.extract_entities(query)
        extracted = self._normalize_terms(query, extracted)

        entities: list[dict[str, Any]] = []
        entity_id_counter = 1

        for measure_text in extracted.measures:
            logger.info("Processing measure entity '%s'", measure_text)
            embedding = self.embed_text(measure_text, is_query=True)
            matches = self.search_similar_fields(
                measure_text, embedding, limit=top_k, field_type="measure"
            )
            candidates = [
                {
                    "explore": match.explore_name,
                    "field_key": match.field_key,
                    "field_name": match.field_name,
                    "label": match.label,
                    "view_name": match.view_name,
                    "measure_type": match.measure_type,
                    "similarity": match.similarity,
                }
                for match in matches
            ]
            entities.append({
                "id": f"E{entity_id_counter}",
                "type": "measure",
                "name": measure_text,
                "weight": 1.0,
                "candidates": candidates,
            })
            entity_id_counter += 1

        for dimension_text in extracted.dimensions:
            logger.info("Processing dimension entity '%s'", dimension_text)
            # No generic enrichment — embed the raw dimension text.
            # The embedding documents already contain rich synonyms via LookML descriptions.
            embedding = self.embed_text(dimension_text, is_query=True)
            matches = self.search_similar_fields(
                dimension_text, embedding, limit=top_k, field_type="dimension"
            )
            candidates = [
                {
                    "explore": match.explore_name,
                    "field_key": match.field_key,
                    "field_name": match.field_name,
                    "label": match.label,
                    "view_name": match.view_name,
                    "measure_type": match.measure_type,
                    "similarity": match.similarity,
                }
                for match in matches
            ]
            entities.append({
                "id": f"E{entity_id_counter}",
                "type": "dimension",
                "name": dimension_text,
                "weight": 1.0,
                "candidates": candidates,
            })
            entity_id_counter += 1

        for filter_item in extracted.filters:
            logger.info("Processing filter entity '%s'", filter_item)
            entities.append({
                "id": f"E{entity_id_counter}",
                "type": "filter",
                "name": filter_item.get("field_hint", "filter"),
                "operator": filter_item.get("operator", "IN"),
                "values": filter_item.get("values", []),
                "weight": 0.8,
            })
            entity_id_counter += 1

        if extracted.time_range:
            logger.info("Processing time range filter '%s'", extracted.time_range)
            entities.append({
                "id": f"E{entity_id_counter}",
                "type": "time_range",
                "name": "time_range",
                "operator": "IN",
                "values": [extracted.time_range],
                "weight": 0.8,
            })

        logger.info("process_query complete: total_entities=%d", len(entities))
        return {"query": query, "entities": entities}

    def format_results(self, results: dict[str, Any]) -> str:
        output = []
        output.append(f"\nQUERY: {results['query']}")
        output.append("=" * 80)

        entities = results.get("entities", [])
        for entity in entities:
            if entity["type"] in ("measure", "dimension"):
                output.append(f"\n  {entity['name']}  (Weight: {entity['weight']:.1f})")
                output.append(f"    Type: {entity['type'].upper()}")
                if entity.get("candidates"):
                    for rank, candidate in enumerate(entity["candidates"], start=1):
                        output.append(
                            f"     Rank {rank}: {candidate.get('field_name', ''):<30} "
                            f"view={candidate.get('view_name', ''):<30} "
                            f"sim={candidate.get('similarity', 0.0):.4f}"
                        )
                else:
                    output.append("     (No candidates found)")
            elif entity["type"] == "filter":
                output.append(f"\n  {entity['name']}  (Weight: {entity['weight']:.1f})")
                output.append(f"    FILTER: {entity.get('name', '')}")
                output.append(f"    Operator: {entity.get('operator', 'IN')}")
                output.append(f"    Values: {entity.get('values', [])}")

        output.append("\n" + "=" * 80)
        return "\n".join(output)


def _demo_run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("\nEntity Extractor Demo (src.retrieval.vector)")
    print("=" * 80)
    print("[1/4] Initializing extractor...")
    extractor = EntityExtractor()

    sample_query = "Total billed business by generation"
    print(f"[2/4] Running query: {sample_query}")
    results = extractor.process_query(sample_query, top_k=5)

    print("[3/4] Rendering formatted output...")
    print(extractor.format_results(results))

    print(f"[4/4] JSON output:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    _demo_run()
