# PR Review: #14 — pgvector parsing and entity extraction

**Status:** Changes Requested

---

## What's good

- SafeChain embedding integration actually works (`safechain.lcel.model()`) — this is valuable, our `safechain_client.py` was still a stub
- Per-field document chunking matches ADR-004 spec exactly
- Docker pipeline (setup → ingest → verify) is clean and reusable
- LookML parser extracts explores, views, dimensions, measures correctly

---

## Bugs — fix before anything else

1. **`_bootstrap_environment()` calls itself inside its own body** — infinite recursion on import. Both `embedding_generator.py` and `entity_extractor.py`. Move the call outside the function.

2. **`except Exception:` without `as e`** — `embedding_generator.py` references `str(e)` but never captures it. Will crash on any embedding failure.

3. **`time_range=None` should be `time_ranges=None`** — `entity_extractor.py` uses wrong kwarg name for `ExtractedEntities` dataclass. TypeError on any failed extraction.

4. **`StructuredEntities` is an identical duplicate of `ExtractedEntities`** — remove one.

5. **Orphaned loop at bottom of `format_results()`** — second `for rank, match` loop references stale `matches` variable from last iteration. Remove it.

6. **Missing `f` prefix** on f-string in `format_results()` — prints literal `{results['query']}`.

---

## Architecture — must align with Cortex

**Your code needs to implement the existing Cortex interfaces, not create a parallel structure.**

| What you have | Where it should go |
|---|---|
| `pgvector_parser/embedding_generator.py` | `cortex/src/retrieval/vector.py` (implement the existing `search()` and `build_field_embeddings()` stubs) |
| `FieldEmbeddingRecord` | Split: storage fields stay internal, search results return `FieldCandidate` from `models.py` |
| `entity_extractor.py` extract logic | `cortex/src/pipeline/` — entity extraction is a pre-processing stage (ADR-005), not part of retrieval |
| `entity_extractor.py` search logic | Fold into `vector.py` — the orchestrator calls `vector.search()`, not a standalone extractor |
| `common/constants.py` | SQL stays in the module that uses it. Config moves to `config/retrieval.yaml` |
| `docker_spin.py` | Keep as-is at repo root — this is the setup/ingestion script |

**Key issue:** `constants.py` crashes on import if env vars aren't set. You can't even run tests. Make the connection loading lazy (factory function, not module-level).

---

## Missing — not blocking, but flag as TODOs

1. **No graph validation** — AGE container runs but zero Cypher in code. This is the critical quality gate that ensures fields can be queried together. Next PR priority.
2. **No confidence gates** — orchestrator defines `SIMILARITY_FLOOR=0.70`, near-miss detection, disambiguation. Your search returns raw scores with no decision logic.
3. **Dimension enrichment is naive** — `"Also known as: attribute, segment, grouping"` appended to every dimension. Use the taxonomy system (`schema.py`) for real synonyms instead.
4. **No filter value resolution** — user says "Millennial", system needs to map to `basic_cust_noa="Millennial"`.

---

## Action items

| Priority | What | When |
|---|---|---|
| P0 | Fix bugs 1-6 | This branch |
| P0 | Restructure into `cortex/src/retrieval/vector.py` | Next push |
| P1 | Implement AGE graph validation | Follow-up PR |
| P1 | Add confidence gates from orchestrator | Follow-up PR |
| P2 | Taxonomy integration, filter resolution | After graph works |

Good momentum — the embedding pipeline and docker orchestration are solid building blocks. Fix the bugs, move the code into Cortex structure, and this becomes the foundation for the vector search channel.
