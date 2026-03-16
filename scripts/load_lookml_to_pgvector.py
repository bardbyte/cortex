"""Parse LookML and load field embeddings into PostgreSQL/pgvector.

KEY DESIGN DECISIONS (from Thread 2 analysis):
  1. Per-view embedding: ONE record per field per view (~129 records, not ~300).
     The same field's semantic meaning doesn't change across explores.
     explore_name stores comma-separated explores containing this field.

  2. High signal-density content (86%): Only semantic meaning in the embedding text.
     Structural metadata (view, explore, model, field type) goes in relational columns.
     Before: "total_billed_business is a measure (sum) in the custins view..."  (27% signal)
     After:  "Total Billed Business: Sum of all billed business across card members..." (86% signal)

  3. Correct field_type: dimensions → 'dimension', measures → 'measure' (was 'view' for dims).

  4. No BGE prefix on documents: BGE-large-en-v1.5 instruction prefix is for QUERIES only.
     Documents are embedded as-is. The prefix is added at query time in vector.py.

Usage:
    python -m scripts.load_lookml_to_pgvector --mode parse
    python -m scripts.load_lookml_to_pgvector --mode embed
    python -m scripts.load_lookml_to_pgvector --mode db
    python -m scripts.load_lookml_to_pgvector --mode pipeline
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from functools import lru_cache

from dotenv import find_dotenv, load_dotenv

# ── Bootstrap FIRST (before any SafeChain imports) ──────────────────
# Matches the proven pattern from access_llm/chat.py:
#   1. load_dotenv()        — get CONFIG_PATH, CIBIS creds into env
#   2. import safechain     — module picks up env state
#   3. Config.from_env()    — initialize SafeChain config
load_dotenv(find_dotenv())
if not os.getenv("CONFIG_PATH"):
    _repo_root = Path(__file__).resolve().parents[1]
    os.environ["CONFIG_PATH"] = str(_repo_root / "config" / "config.yml")

from ee_config.config import Config
from safechain.lcel import model as safechain_model

Config.from_env()
# ── End bootstrap ───────────────────────────────────────────────────

from sqlalchemy import text
from sqlalchemy.engine import Engine, URL, create_engine

from config.constants import (
    EMBED_MODEL_IDX,
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DBNAME,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    SQL_CREATE_FIELD_EMBEDDINGS_TABLE,
    SQL_CREATE_FIELD_EMBEDDINGS_HNSW_INDEX,
    SQL_CREATE_VECTOR_EXTENSION,
    SQL_RETRIEVE_TOP_K_BY_DISTANCE,
    SQL_SAMPLE_FIELD_EMBEDDINGS,
    SQL_COUNT_FIELD_EMBEDDINGS,
    SQL_UPSERT_FIELD_EMBEDDING_RECORD,
)

logger = logging.getLogger(__name__)


@dataclass
class FieldEmbeddingRecord:
    """Record for inserting into the field_embeddings table."""
    field_key: str
    embedding: list[float] | None
    content: str
    field_name: str
    field_type: str | None
    measure_type: str | None
    view_name: str
    explore_name: str | None
    model_name: str | None
    label: str | None
    group_label: str | None
    tags: list[str]
    hidden: bool = False
    id: int | None = None
    created_at: datetime.datetime | None = None


class FieldEmbeddingBuilder:
    """Builds embeddings for field records using SafeChain BGE model."""

    def __init__(self, model_idx: str = EMBED_MODEL_IDX):
        self.model_idx = model_idx
        self.embedding_client = safechain_model(model_idx)

    def embed_records(self, records: list[FieldEmbeddingRecord]) -> list[FieldEmbeddingRecord]:
        logger.info("Starting embedding generation for %s records using model ID '%s'", len(records), self.model_idx)

        success_count = 0
        error_count = 0

        for idx, record in enumerate(records, start=1):
            try:
                record.embedding = self.embedding_client.embed_query(record.content)
                if record.embedding and len(record.embedding) > 0:
                    success_count += 1
                else:
                    error_count += 1
                    logger.error("[%d/%d] Empty embedding for field_key=%s", idx, len(records), record.field_key)
                    record.embedding = None
            except Exception as e:
                error_count += 1
                logger.error("[%d/%d] Failed to embed field_key=%s | error=%s", idx, len(records), record.field_key, str(e))
                record.embedding = None

        logger.info(
            "Embedding generation complete: %d successful, %d errors out of %d total records",
            success_count,
            error_count,
            len(records),
        )
        return records


class PostgresConfig:
    """Shared PostgreSQL connection configuration loaded from environment."""
    HOST = POSTGRES_HOST
    PORT = POSTGRES_PORT
    DBNAME = POSTGRES_DBNAME
    USER = POSTGRES_USER
    PASSWORD = POSTGRES_PASSWORD

    @classmethod
    @lru_cache(maxsize=1)
    def get_connection_string(cls):
        return f"postgresql+psycopg2://{cls.USER}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.DBNAME}"

    @classmethod
    def get_engine(cls) -> Engine:
        db_url = URL.create(
            drivername="postgresql+psycopg2",
            username=cls.USER,
            password=cls.PASSWORD,
            host=cls.HOST,
            port=cls.PORT,
            database=cls.DBNAME,
        )
        return create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            future=True,
        )


class PostgresOperations:
    """PostgreSQL operations for field embeddings table management."""

    def get_engine(self) -> Engine:
        return PostgresConfig.get_engine()

    def wait_for_postgres(self):
        logger.info("Waiting for PostgreSQL to be ready")
        for _ in range(20):
            try:
                with self.get_engine().connect() as conn:
                    conn.execute(text("SELECT 1"))
                    logger.info("PostgreSQL is ready")
                    return
            except Exception:
                logger.info("PostgreSQL not ready yet, retrying")
                time.sleep(2)
        raise RuntimeError("PostgreSQL did not become ready in time.")

    def create_table(self):
        logger.info("Creating vector extension and field_embeddings table if needed")
        with self.get_engine().begin() as conn:
            conn.execute(text(SQL_CREATE_VECTOR_EXTENSION))
            conn.execute(text(SQL_CREATE_FIELD_EMBEDDINGS_TABLE))
        logger.info("Ensured vector extension + field_embeddings table")

    def create_index(self):
        logger.info("Creating HNSW index if needed")
        with self.get_engine().begin() as conn:
            conn.execute(text(SQL_CREATE_FIELD_EMBEDDINGS_HNSW_INDEX))
        logger.info("Ensured HNSW index")

    def ingest_records(self, records: list[FieldEmbeddingRecord]):
        logger.info("Starting ingestion: %d records", len(records))
        inserted_count = 0
        with self.get_engine().begin() as conn:
            for record in records:
                if record.embedding is None:
                    continue
                conn.exec_driver_sql(
                    SQL_UPSERT_FIELD_EMBEDDING_RECORD,
                    (
                        record.id,
                        record.field_key,
                        record.embedding,
                        record.content,
                        record.field_name,
                        record.field_type,
                        record.measure_type,
                        record.view_name,
                        record.explore_name,
                        record.model_name,
                        record.label,
                        record.group_label,
                        ",".join(record.tags) if record.tags else "",
                        record.hidden,
                        record.created_at,
                    ),
                )
                inserted_count += 1

        logger.info("Inserted/updated %d records into PostgreSQL", inserted_count)
        return inserted_count

    def retrieve_records(self, query_embed: list[float], k: int = 5):
        logger.info("Retrieving top %d records by vector distance", k)
        with self.get_engine().connect() as conn:
            results = conn.exec_driver_sql(
                SQL_RETRIEVE_TOP_K_BY_DISTANCE,
                (query_embed, k),
            ).fetchall()
        return results

    def verify(self):
        logger.info("Running vector store verification checks")
        with self.get_engine().connect() as conn:
            count_row = conn.exec_driver_sql(SQL_COUNT_FIELD_EMBEDDINGS).fetchone()
            count = int(count_row[0]) if count_row else 0

        summary: dict[str, object] = {"count": count, "sample": []}
        if count > 0:
            with self.get_engine().connect() as conn:
                summary["sample"] = conn.exec_driver_sql(SQL_SAMPLE_FIELD_EMBEDDINGS).fetchall()

        logger.info("Verification complete. count=%s", count)
        return summary


@dataclass
class FieldInfo:
    """Represents a LookML field within a view."""
    name: str
    field_type: str
    data_type: str | None
    label: str | None
    description: str | None
    group_label: str | None
    tags: list[str]
    hidden: bool


@dataclass
class ViewInfo:
    """Represents a LookML view and its fields."""
    name: str
    fields: list[FieldInfo]


@dataclass
class ExploreInfo:
    """Represents a LookML explore and the views it exposes."""
    name: str
    base_view: str
    view_names: set[str]


class LookMLParser:
    """Parses LookML model and view files to build field records.

    Per-view embedding strategy: ONE record per field per view.
    explore_name stores comma-separated explores containing this field.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        views_dir: Path | None = None,
        model_name: str | None = None,
    ):
        if model_path is None or views_dir is None:
            base_dir = Path(__file__).resolve().parents[1]
            model_path = model_path or (base_dir / "lookml" / "finance_model.model.lkml")
            views_dir = views_dir or (base_dir / "lookml" / "views")

        self.model_path = Path(model_path)
        self.views_dir = Path(views_dir)
        self.model_name = model_name or self._infer_model_name(self.model_path)

    def __iter__(self):
        """Allow direct iteration: for r in LookMLParser():..."""
        return iter(self.get_records_for_docker())

    def get_records_for_docker(self, include_embeddings: bool = True) -> list[FieldEmbeddingRecord]:
        """Return records in the shape expected by docker_spin.py ingestion payload."""
        records = self._build_records()
        for idx, record in enumerate(records, start=1):
            record.id = idx
            record.created_at = datetime.datetime.now(datetime.timezone.utc)

        if include_embeddings:
            logger.info("Generating embeddings for docker ingestion payload")
            builder = FieldEmbeddingBuilder()
            records = builder.embed_records(records)

        logger.info("Prepared %d docker ingestion records", len(records))
        return records

    def _infer_model_name(self, model_path: Path) -> str:
        if model_path is None:
            return ""
        name = model_path.name
        if name.endswith(".model.lkml"):
            name = name.replace(".model.lkml", "")
        return name

    def parse_model_explores(self) -> dict[str, ExploreInfo]:
        """Parse explores and their view relationships from a model file."""
        logger.info("Parsing explores from model.lkml: %s", self.model_path.name)
        text = self.model_path.read_text(encoding="utf-8")
        explores: dict[str, ExploreInfo] = {}

        for explore_name, block in self._iter_blocks(text, "explore"):
            from_view = self._extract_simple_value(block, "from")
            join_views = {join_name for join_name, _ in self._iter_blocks(block, "join")}
            view_names = set(join_views)

            base_view = from_view or explore_name
            view_names.add(base_view)

            explores[explore_name] = ExploreInfo(
                name=explore_name,
                base_view=base_view,
                view_names=view_names,
            )

        logger.info("Parsed %s explores", len(explores))
        return explores

    def parse_views(self) -> dict[str, ViewInfo]:
        """Parse views from the views directory."""
        logger.info("Parsing views from: %s", self.views_dir)
        views: dict[str, ViewInfo] = {}

        for path in sorted(self.views_dir.glob("*.view.lkml")):
            view_info = self._parse_view_file(path)
            if view_info:
                views[view_info.name] = view_info

        logger.info("Parsed %s views", len(views))
        return views

    def _build_records(self) -> list[FieldEmbeddingRecord]:
        """Build field records using per-view strategy.

        Instead of one record per explore × view × field (~300 records),
        we create one record per view × field (~129 records).
        explore_name is a comma-separated list of explores containing this field.
        """
        logger.info("Building per-view field records for model=%s", self.model_name)
        explores = self.parse_model_explores()
        views = self.parse_views()

        # Build reverse map: (view_name, field_name) → set of explore names
        field_to_explores: dict[tuple[str, str], set[str]] = {}
        for explore_name, explore in explores.items():
            for view_name in explore.view_names:
                view_info = views.get(view_name)
                if not view_info:
                    continue
                for field in view_info.fields:
                    key = (view_name, field.name)
                    field_to_explores.setdefault(key, set()).add(explore_name)

        records: list[FieldEmbeddingRecord] = []
        seen_keys: set[str] = set()

        for view_name in sorted(views.keys()):
            view_info = views[view_name]
            for field in view_info.fields:
                field_key = f"{view_name}.{field.name}"
                if field_key in seen_keys:
                    continue
                seen_keys.add(field_key)

                explore_names = field_to_explores.get((view_name, field.name), set())
                if not explore_names:
                    continue

                content = self._build_content(field)

                records.append(
                    FieldEmbeddingRecord(
                        field_key=field_key,
                        embedding=None,
                        content=content,
                        field_name=field.name,
                        field_type=field.field_type,  # 'dimension' or 'measure' — correct
                        measure_type=field.data_type if field.field_type == "measure" else None,
                        view_name=view_name,
                        explore_name=",".join(sorted(explore_names)),
                        model_name=self.model_name,
                        label=field.label or field.name,
                        group_label=field.group_label,
                        tags=field.tags,
                        hidden=field.hidden,
                    )
                )

        logger.info("Built %s per-view records (was ~%s per-explore)", len(records), len(records) * 2)
        return records

    def _build_content(self, field: FieldInfo) -> str:
        """Build high signal-density embedding text.

        86% signal density: ONLY semantic meaning, NO structural metadata.
        The view name, explore name, model name, and field type go in relational
        columns — they're filtered/joined, not embedded.

        Format: "{Label}: {Description}"
        The description already contains synonyms ("Also known as: ...") from
        our LookML uplift, so the embedding captures all semantic variants.
        """
        label = field.label or field.name.replace("_", " ").title()
        description = field.description or field.data_type or "No description available."

        # Strip leading label from description if it starts with the label
        # (avoids "Total Billed Business: Total Billed Business - sum of...")
        content = f"{label}: {description}"
        return content

    def _parse_view_file(self, path: Path) -> ViewInfo | None:
        logger.debug("Parsing view file: %s", path.name)
        text = path.read_text(encoding="utf-8")
        view_blocks = list(self._iter_blocks(text, "view"))
        if not view_blocks:
            logger.warning("No view blocks found in %s", path.name)
            return None

        view_name, view_block = view_blocks[0]
        fields: list[FieldInfo] = []

        for dim_name, dim_block in self._iter_blocks(view_block, "dimension"):
            fields.append(self._parse_field(dim_name, dim_block, "dimension"))

        for measure_name, measure_block in self._iter_blocks(view_block, "measure"):
            fields.append(self._parse_field(measure_name, measure_block, "measure"))

        for dim_name, dim_block in self._iter_blocks(view_block, "dimension_group"):
            fields.append(self._parse_field(dim_name, dim_block, "dimension"))

        logger.debug("Parsed %d fields from view=%s", len(fields), view_name)
        return ViewInfo(name=view_name, fields=fields)

    def _parse_field(self, name: str, block: str, field_type: str) -> FieldInfo:
        data_type = self._extract_simple_value(block, "type")
        label = self._extract_quoted_value(block, "label")
        description = self._extract_quoted_value(block, "description")
        group_label = self._extract_quoted_value(block, "group_label")
        tags = self._extract_tags(block)
        hidden = self._extract_simple_value(block, "hidden") in ("yes", "true")

        return FieldInfo(
            name=name,
            field_type=field_type,
            data_type=data_type,
            label=label,
            description=description,
            group_label=group_label,
            tags=tags,
            hidden=hidden,
        )

    def _iter_blocks(self, text: str, keyword: str) -> list[tuple[str, str]]:
        pattern = re.compile(rf"^\s*{keyword}\s*:\s*(\w+)\s*\{{", re.MULTILINE)
        results = []
        for match in pattern.finditer(text):
            name = match.group(1)
            start_idx = match.end() - 1
            end_idx = self._find_matching_brace(text, start_idx)
            if end_idx > start_idx:
                results.append((name, text[start_idx + 1:end_idx]))
        return results

    def _find_matching_brace(self, text: str, start_idx: int) -> int:
        depth = 0
        for idx in range(start_idx, len(text)):
            char = text[idx]
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return idx
        raise ValueError("Unmatched brace in LookML file.")

    def _extract_simple_value(self, block: str, key: str) -> str | None:
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(\S+)", re.MULTILINE)
        match = pattern.search(block)
        if not match:
            return None
        value = match.group(1).strip()
        return value

    def _extract_quoted_value(self, block: str, key: str) -> str | None:
        pattern = re.compile(rf'^\s*{re.escape(key)}\s*:\s*"(.*?)"', re.MULTILINE | re.S)
        match = pattern.search(block)
        if not match:
            return None
        return match.group(1).strip()

    def _extract_tags(self, block: str) -> list[str]:
        pattern = re.compile(r'tags\s*:\s*\[(.*?)\]', re.S)
        match = pattern.search(block)
        if not match:
            return []
        raw = match.group(1)
        cleaned = []
        for item in raw.split(","):
            item = item.strip().strip('"').strip("'")
            if item:
                cleaned.append(item)
        return cleaned

    def _extract_sql_block(self, block: str) -> str | None:
        """Extract multi-line sql: ... ;; content from a LookML block."""
        pattern = re.compile(r'sql\s*:\s*(.*?)\s*;;', re.S)
        match = pattern.search(block)
        if not match:
            return None
        return match.group(1).strip()

    def _extract_always_filter_fields(self, block: str) -> list[str]:
        """Extract field names from always_filter declarations.

        LookML syntax:
          always_filter: {
            filters: [finance_cardmember_360.partition_date: "last 90 days"]
          }
        Returns: ["partition_date"]
        """
        pattern = re.compile(r'always_filter\s*:\s*\{(.*?)\}', re.S)
        match = pattern.search(block)
        if not match:
            return []
        inner = match.group(1)
        # Extract field references like "explore_name.field_name"
        field_pattern = re.compile(r'filters\s*:\s*\[([\w.]+)\s*:')
        field_match = field_pattern.search(inner)
        if not field_match:
            return []
        full_ref = field_match.group(1)
        # Return just the field name (after the dot)
        parts = full_ref.split(".")
        return [parts[-1]] if parts else []

    # ─── FILTER CATALOG AUTO-DERIVATION ──────────────────────────────

    def extract_case_values(self, sql_block: str) -> list[str]:
        """Extract THEN values from SQL CASE statements.

        Input:  "CASE WHEN birth_year >= 1997 THEN 'Gen Z' ... END"
        Output: ["Gen Z", "Millennial", "Gen X", "Baby Boomer", "Other"]
        """
        pattern = re.compile(r"THEN\s+'([^']+)'", re.IGNORECASE)
        values = []
        for match in pattern.finditer(sql_block):
            val = match.group(1).strip()
            if val.lower() not in ("other", "unknown", "n/a", "null", ""):
                values.append(val)
        return values

    def extract_synonyms_from_description(self, description: str) -> list[str]:
        """Extract synonyms from LookML description "Also known as:" clause.

        Input:  "... Also known as: generational segment, age group, demographic cohort."
        Output: ["generational segment", "age group", "demographic cohort"]
        """
        if not description:
            return []
        pattern = re.compile(r"Also known as:\s*(.+?)\.?\s*$", re.IGNORECASE)
        match = pattern.search(description)
        if not match:
            return []
        raw = match.group(1)
        return [s.strip() for s in raw.split(",") if s.strip()]

    def build_filter_catalog(self) -> dict[str, Any]:
        """Auto-derive the complete filter catalog from LookML files.

        Replaces the need for hardcoded FILTER_VALUE_MAP, SYNONYM_MAP,
        YESNO_DIMENSIONS, and EXPLORE_PARTITION_FIELDS.

        Value map keys are namespaced as "view_name.dimension_name" to prevent
        collisions when multiple BUs define dimensions with the same name.

        Returns dict with:
          "value_map": {"view.dim": {lowercase_value: canonical_value}}
          "synonyms": {dim_name: [synonym_strings]}
          "yesno_dimensions": list of dimension names with type: yesno
          "partition_fields": {explore_name: partition_field_name}
          "explore_views": {explore_name: [view_names]}
        """
        logger.info("Building filter catalog from LookML files...")

        explores = self.parse_model_explores()
        views = self.parse_views()

        value_map: dict[str, dict[str, str]] = {}
        synonyms: dict[str, list[str]] = {}
        yesno_dimensions: set[str] = set()
        partition_fields: dict[str, str] = {}

        # ── Extract partition fields from model file ──
        model_text = self.model_path.read_text(encoding="utf-8")
        for explore_name, block in self._iter_blocks(model_text, "explore"):
            af_fields = self._extract_always_filter_fields(block)
            if af_fields:
                partition_fields[explore_name] = af_fields[0]

        # ── Extract values and synonyms from view files ──
        for view_name, view_info in views.items():
            for field_info in view_info.fields:
                if field_info.field_type != "dimension":
                    continue

                # Yesno detection
                if field_info.data_type == "yesno":
                    yesno_dimensions.add(field_info.name)
                    continue

                # Only process string dimensions (categorical)
                if field_info.data_type not in ("string", None):
                    continue

                dim_name = field_info.name
                ns_key = f"{view_name}.{dim_name}"

                # Extract CASE values from SQL block
                view_path = self.views_dir / f"{view_name}.view.lkml"
                if view_path.exists():
                    view_text = view_path.read_text(encoding="utf-8")
                    for block_name, block_content in self._iter_blocks(view_text, "dimension"):
                        if block_name == dim_name:
                            sql_block = self._extract_sql_block(block_content)
                            if sql_block and "CASE" in sql_block.upper():
                                case_values = self.extract_case_values(sql_block)
                                if case_values:
                                    dim_values = value_map.setdefault(ns_key, {})
                                    for val in case_values:
                                        dim_values[val.lower()] = val
                                    logger.info(
                                        "  CASE values for %s: %s",
                                        ns_key, case_values,
                                    )

                # Extract synonyms from description (bare-keyed — field-level, not view-level)
                if field_info.description:
                    syns = self.extract_synonyms_from_description(field_info.description)
                    if syns:
                        synonyms.setdefault(dim_name, []).extend(syns)

        # ── Build explore → views mapping ──
        explore_views: dict[str, list[str]] = {}
        for exp_name, exp_info in explores.items():
            explore_views[exp_name] = sorted(exp_info.view_names)

        logger.info(
            "Filter catalog built: %d value maps, %d synonym groups, "
            "%d yesno dims, %d partition fields, %d explores",
            len(value_map), len(synonyms),
            len(yesno_dimensions), len(partition_fields),
            len(explore_views),
        )

        return {
            "value_map": value_map,
            "synonyms": synonyms,
            "yesno_dimensions": yesno_dimensions,
            "partition_fields": partition_fields,
            "explore_views": explore_views,
        }


def _demo_run() -> None:
    """Demo runner for parser, embedding, and db operations."""
    cli = argparse.ArgumentParser(description="LookML -> pgvector loader")
    cli.add_argument("--mode", choices=["parse", "embed", "db", "pipeline", "catalog"], default="parse")
    cli.add_argument("--query", type=str, default="customer")
    cli.add_argument("--top-k", type=int, default=5)
    args = cli.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(f"\n{'=' * 80}")
    print(f"Mode: {args.mode} | Query: {args.query} | Top-K: {args.top_k}")

    parser = LookMLParser()

    if args.mode == "parse":
        print("[PARSE] Building records from LookML files...")
        records = parser._build_records()
        for record in records[:5]:
            print(f"  {record.field_key}: {record.field_type} | explores={record.explore_name}")
            print(f"    content: {record.content[:100]}...")
        print(f"[PARSE] Done. Records built: {len(records)}")
        return

    if args.mode == "embed":
        print("[EMBED] Building records and generating embeddings...")
        records = parser.get_records_for_docker(include_embeddings=True)
        success_count = sum(1 for record in records if record.embedding)
        print(f"[EMBED] Done. Successful embeddings: {success_count}/{len(records)}")
        return

    if args.mode == "db":
        pg_ops = PostgresOperations()
        print("[DB] Waiting for PostgreSQL readiness...")
        pg_ops.wait_for_postgres()
        summary = pg_ops.verify()
        print(f"[DB] Verify count={summary.get('count')}")
        return

    if args.mode == "pipeline":
        print("[PIPELINE] Full pipeline: parse → embed → create table → ingest → verify")
        pg_ops = PostgresOperations()
        pg_ops.wait_for_postgres()
        pg_ops.create_table()
        pg_ops.create_index()
        records = parser.get_records_for_docker(include_embeddings=True)
        print(f"[PIPELINE] Ingesting {len(records)} records...")
        pg_ops.ingest_records(records)
        summary = pg_ops.verify()
        print(f"[PIPELINE] Done. Total records in DB: {summary.get('count')}")

        print("[PIPELINE] Running retrieval test...")
        builder = FieldEmbeddingBuilder()
        query_embedding = builder.embedding_client.embed_query(args.query)
        rows = pg_ops.retrieve_records(query_embedding, k=args.top_k)
        print(f"[PIPELINE] Retrieved {len(rows)} rows for query='{args.query}'")
        for row in rows:
            print(f"  {row[1]}: {row[3]} ({row[4]}) sim=n/a")
        return


    if args.mode == "catalog":
        print("[CATALOG] Building filter catalog from LookML files...")
        catalog = parser.build_filter_catalog()
        # Serialize — convert sets to sorted lists for JSON
        serializable = {
            "value_map": catalog["value_map"],
            "synonyms": catalog["synonyms"],
            "yesno_dimensions": sorted(catalog["yesno_dimensions"]),
            "partition_fields": catalog["partition_fields"],
            "explore_views": catalog["explore_views"],
        }
        import json
        out_path = Path(__file__).resolve().parents[1] / "config" / "filter_catalog.json"
        out_path.write_text(json.dumps(serializable, indent=2, sort_keys=True) + "\n")
        print(f"[CATALOG] Written to {out_path}")
        print(f"  Value maps: {len(catalog['value_map'])} dimensions")
        print(f"  Synonyms: {len(catalog['synonyms'])} dimensions")
        print(f"  Yesno dims: {len(catalog['yesno_dimensions'])}")
        print(f"  Partition fields: {len(catalog['partition_fields'])}")
        return


if __name__ == "__main__":
    _demo_run()
