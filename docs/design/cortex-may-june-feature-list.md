# Radix Platform — May/June 2026 Feature Delivery

**Prepared by:** Saheb Singh | **Date:** March 18, 2026 | **For:** Abhishek

---

## Platform Foundation (Delivered)

| Component | What It Does |
|-----------|-------------|
| PostgreSQL + pgvector | Vector store for semantic field embeddings (1024-dim) |
| Apache AGE Graph | LookML structural graph — explores, views, fields, joins |
| Embedding Pipeline | BGE-large embeddings for all measures + dimensions |
| LookML Parser | Parses .lkml files → graph nodes + filter catalog |
| SafeChain / CIBIS | Auth gateway for all LLM + embedding calls |
| Looker MCP Sidecar | 33 Looker tools via Model Context Protocol |
| FastAPI + SSE | Streaming API server with real-time pipeline events |

**Shipping May–June:** GKE production deployment, CI/CD pipeline, embedding refresh jobs, observability stack, Redis session store

---

## Radix AI Pipeline (Saheb)

*Natural language → SQL via semantic understanding*

| Feature | Status |
|---------|--------|
| Intent classification + entity extraction | Delivered |
| Hybrid semantic retrieval (vector + graph + few-shot) | Delivered |
| Explore routing with multiplicative scoring | Delivered |
| Near-miss detection + disambiguation | Delivered |
| 5-pass filter resolution (exact → synonym → fuzzy → embedding → passthrough) | Delivered |
| Mandatory partition filter injection (governance rules) | Delivered |
| SQL generation via Looker MCP (deterministic, not hallucinated) | Delivered |
| Real-time pipeline streaming (SSE) | Delivered |
| Dual-view UI — Chat mode + Pipeline explainability mode | Delivered |
| Multi-turn conversation context | Delivered |
| Confidence scoring at every stage | Delivered |
| Follow-up question suggestions | Delivered |
| Query execution + results display | May |
| User feedback loop (thumbs up/down + corrections) | May |
| Learning loop — user corrections feed synonym catalog (Wilson score) | May |
| Few-shot query index (FAISS, 150+ golden queries) | May |
| Multi-BU expansion (Finance → 3 BUs) | June |
| Cost control gate (dry-run estimation + budget enforcement) | June |
| Production GKE deployment | June |

---

## Semantic Enrichment — Lumi (Renuka)

*Metadata enrichment that feeds the AI pipeline, Looker, and the Control Plane*

| Feature | Target |
|---------|--------|
| Steward enrichment UX — add descriptions, synonyms, business terms | May |
| Semantic definition workflow — guided metric definition from business intent to LookML | May |
| Synonym registry — business terms → technical column mappings | May |
| Dimension value catalog — known values with business-friendly labels | May |
| Data steward workflow — review queue, approval/rejection, conflict resolution | May |
| LookML auto-generation from enrichment metadata | June |
| Enrichment quality scoring — completeness % per field | June |
| Bulk bootstrap from BigQuery query logs (180-day WHERE clause mining) | May |

---

## Metric Playground

*Interactive workspace — define metrics, see how AI interprets them in real time*

| Feature | Status |
|---------|--------|
| Layer explorer — Raw Column → LookML → Enriched Metric visualization | Delivered |
| Metric hierarchy — governance tiers (Canonical / BU Variant / Team Derived) | Delivered |
| Define a metric — 3 paths: from SQL, from business description, enhance existing | Delivered |
| How AI uses it — pipeline trace with "what if it wasn't enriched?" comparison | Delivered |
| Live metric editor with save to enrichment store | May |
| Synonym sandbox — add/remove synonyms, see instant retrieval impact | May |
| Real-time AI impact preview — before/after scoring on edit | June |
| Metric coverage dashboard — enrichment gaps + highest-traffic unindexed metrics | June |
| Metric lineage graph — source table → LookML → explore → dependents | June |

---

## Control Plane

*Centralized dashboard for metadata corpus management + governance*

| Feature | Target |
|---------|--------|
| Metadata corpus overview — fields indexed, % enriched, coverage per BU | May |
| Field-level detail — description, synonyms, values, usage frequency, enrichment score | May |
| Synonym management — CRUD + steward approval queue + auto-approve rules | May |
| Filter catalog manager — view/edit dimension values, flag conflicts | May |
| Explore health scorecard — quality score per explore | June |
| Query audit trail — every query logged with confidence, explore chosen, feedback | June |
| Governance rules engine — mandatory filters, cost budgets per BU | June |
| BU onboarding wizard — connect explores → embed → bootstrap catalog → assign steward | June |

---

## Key Numbers

| Metric | Today | June Target |
|--------|-------|-------------|
| Business Units | 1 (Finance) | 3 |
| Explores indexed | 5 | 50+ |
| End-to-end accuracy | ~83% | 90%+ |
| P95 latency | ~1.2s | <4s (with execution) |
