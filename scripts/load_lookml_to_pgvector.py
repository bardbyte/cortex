"""Parse LookML and load field embeddings into PostgreSQL/pgvector.

This script combines three capabilities in one place:
  1) LookML parsing:
     - Reads model + view .lkml files
     - Extracts explores, views, dimensions, and measures
     - Builds one embedding record per field

  2) Embedding generation:
     - Uses safechain model wrapper (BGE embedding model via model id from config)
     - Embeds each field content: payload and stores vectors on records

  3) pgvector operations:
     - Wait for PostgreSQL readiness
     - Create vector extension, table, and HNSW index
     - Upsert records and run verification queries

Usage examples:
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
from sqlalchemy import text
from sqlalchemy.engine import Engine, URL, create_engine

try:
    from safechain.lct import model
except ImportError:
    model = None

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
    SQL_VERIFY_VECTOR_SELF_MATCH,
)

logger = logging.getLogger(__name__)


def _bootstrap_environment() -> None:
    """Load .env and ensure CONFIG_PATH is available for safechain/ee_config."""
    load_dotenv(find_dotenv())
    if not os.getenv("CONFIG_PATH"):
        repo_root = Path(__file__).resolve().parents[1]
        default_config_path = repo_root / "config.yml"
        os.environ["CONFIG_PATH"] = str(default_config_path)
        logger.info("[load_lookml_to_pgvector] CONFIG_PATH set to: %s", default_config_path)
    else:
        logger.info("[load_lookml_to_pgvector] CONFIG_PATH already set to: %s", os.getenv("CONFIG_PATH"))


_bootstrap_environment()


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
    """Builds embeddings for field records using safechain model wrapper."""

    def __init__(self, model_idx: str = EMBED_MODEL_IDX):
        self.model_idx = model_idx
        self.embedding_client = model(self.model_idx)

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
                    logger.error("[%d/%d] Failed to embed field_key=%s | error=%s", idx, len(records), record.field_key, str(e))
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
        logger.info("Starting ingestion: %d records with %d records", len(records), len(records))
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
                        record.tags,
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

        summary: dict[str, object] = {"count": count, "self_match": []}
        if count > 0:
            with self.get_engine().connect() as conn:
                count_row = conn.exec_driver_sql(SQL_SAMPLE_FIELD_EMBEDDINGS).fetchone()
                count = int(count_row[0]) if count_row else 0
                summary["sample"] = conn.exec_driver_sql(SQL_VERIFY_VECTOR_SELF_MATCH).fetchall()

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
    view_names: set[str]


class LookMLParser:
    """Parses LookML model and view files to build field records."""

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
        return iter(self._get_records_for_docker())

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
            if from_view:
                view_names.add(from_view)
            else:
                view_names.add(explore_name)

            explores[explore_name] = ExploreInfo(name=explore_name, view_names=view_names)

        logger.info("Parsed %s explores", len(explores))
        return explores

    def parse_views(self) -> dict[str, ViewInfo]:
        """Parsing views from the views directory."""
        logger.info("Parsing views from: %s", self.views_dir)
        views: dict[str, ViewInfo] = {}

        for path in sorted(self.views_dir.glob("*.view.lkml")):
            view_info = self._parse_view_file(path)
            if view_info:
                views[view_info.name] = view_info

        logger.info("Parsed %s views", len(views))
        return views

    def _build_records(self) -> list[FieldEmbeddingRecord]:
        """Build field records by joining explores with views and fields."""
        logger.info("Building field records for model=%s", self.model_name)
        explores = self.parse_model_explores()
        views = self.parse_views()

        records: list[FieldEmbeddingRecord] = []

        for explore_name in sorted(explores.keys()):
            explore = explores[explore_name]
            for view_name in sorted(explore.view_names):
                view_info = views.get(view_name)
                if not view_info:
                    continue
                for field in view_info.fields:
                    content = self._build_content(
                        field_key=self._build_field_key(self.model_name, explore_name, view_name, field.name),
                        explore_name=explore_name,
                        view_name=view_name,
                        model_name=self.model_name,
                        field=field,
                    )
                    records.append(
                        FieldEmbeddingRecord(
                            field_key=self._build_field_key(
                                self.model_name, explore_name, view_name, field.name
                            ),
                            embedding=None,
                            content=content,
                            field_name=field.name,
                            field_type=field.field_type if field.field_type == "measure" else "view",
                            measure_type=field.field_type if field.field_type == "measure" else None,
                            view_name=view_name,
                            explore_name=explore_name,
                            model_name=self.model_name,
                            label=field.label or field.name,
                            group_label=field.group_label,
                            tags=field.tags,
                            hidden=field.hidden,
                        )
                    )

        logger.info("Built %s records", len(records))
        return records

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
        logger.debug("Parsing field=%s from view, type=%s", name, field_type)
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

    def _build_field_key(self, model: str, explore: str, view: str, field: str) -> str:
        return f"{model}.{explore}.{view}.{field}"

    def _build_content(self, field_key: str, explore_name: str, view_name: str, model_name: str, field: FieldInfo) -> str:
        description = field.description or field.data_type or "No description provided."
        type_detail = field.data_type or "unknown"
        content = (
            f"{field.name} is a {field.field_type} ({type_detail}) in the {view_name} view.\n"
            f"Accessible through the {explore_name} explore in the {model_name} model.\n"
            f"({field.label}): {description}"
        )
        logger.debug("Built content for field_key=%s", field_key)
        return content

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


def _demo_run() -> None:
    """Demo runner for parser, embedding, and db operations in this module."""
    cli = argparse.ArgumentParser(description="LookML -> pgvector loader demo")
    cli.add_argument("--mode", choices=["parse", "embed", "db", "pipeline"], default="parse")
    cli.add_argument("--query", type=str, default="customer")
    cli.add_argument("--top-k", type=int, default=5)
    args = cli.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelnames)s %(name)s | Query: {args.query} | Top-K: {args.top_k}")
    print(f"\n{'=' * 80}")
    print(f"Model: {args.mode} | Query: {args.query} | Top-K: {args.top_k}")

    base_dir = Path(__file__).resolve().parents[1]
    model_path = base_dir / "lookml" / "finance_model.model.lkml"
    views_dir = base_dir / "lookml" / "views"

    print(f"Initialized LookML parser and resolved model/view paths.")

    if args.mode == "parse":
        parser = LookMLParser(model_path=model_path, views_dir=views_dir)
        print("[PARSE] Building records from LookML files...")
        records = parser._build_records()
        logger.info("Parsed %d records from %s", len(records), model_path.name)
        for record in records[:3]:
            logger.info("Sample field_key: %s, content[:50]=%s", record.field_key, record.content[:50])
        print(f"[PARSE] Done. Records built: {len(records)}")
        return

    if args.mode == "embed":
        parser = LookMLParser(model_path=model_path, views_dir=views_dir)
        print("[EMBED] Building records without embeddings...")
        records = parser.get_records_for_docker(include_embeddings=False)
        print("[EMBED] Generating embeddings for records...")
        builder = FieldEmbeddingBuilder()
        records = builder.embed_records(records)
        success_count = sum(1 for record in records if record.embedding)
        logger.info("[EMBED] Done. Successful embeddings: %d/%d", success_count, len(records))
        return

    if args.mode == "db":
        pg_ops = PostgresOperations()
        print("[DB] Waiting for PostgreSQL readiness...")
        pg_ops.wait_for_postgres()
        logger.info("[DB] Running verification checks...")
        summary = pg_ops.verify()
        logger.info("[DB] Verify count=%s", summary.get("count"))
        return

    if args.mode == "pipeline":
        print("[PIPELINE] Ensuring vector extension/table/index...")
        pg_ops = PostgresOperations()
        pg_ops.create_table()
        pg_ops.create_index()
        records = parser.get_records_for_docker(include_embeddings=True)
        print(f"[PIPELINE] Ingesting {len(records)} records...")
        pg_ops.ingest_records(records)
        print("[PIPELINE] Running retrieval test...")
        from src.retrieval.vector import EntityExtractor
        query_embedding = FieldEmbeddingBuilder().embedding_client.embed_query(args.query)
        rows = pg_ops.retrieve_records(query_embedding, k=args.top_k)
        logger.info("Retrieved %d rows for query='%s'", len(rows), args.query)
        print(f"[PIPELINE] Retrieved rows: {len(rows)}")
        return


if __name__ == "__main__":
    _demo_run()
