# Cortex Platform — May/June 2026 Feature Delivery

**Prepared by:** Saheb Singh | **Date:** March 18, 2026 | **For:** Abhishek
**Status:** Planning — feature scope for alignment

---

## Overview

Four layers shipping by end of June 2026:

| Layer | What It Is | Primary User |
|-------|-----------|-------------|
| **Platform Foundation** | Databases, embedding pipelines, auth, deployment infrastructure | Engineering team |
| **Cortex AI Pipeline** | Natural language → SQL via semantic understanding | Finance analysts, BU leads |
| **Metric Playground** | Interactive metric definition + real-time AI impact visualization | Data stewards, analysts, executives |
| **Control Plane** | Centralized metadata corpus management + governance dashboard | Data stewards, data governance leads |

Plus **Semantic Enrichment (Lumi)** — Renuka's workstream feeding metadata into all three.

---

## 0. Platform Foundation — Infrastructure That Powers Everything

Before any feature works, these foundational layers must exist. Most are delivered or in progress.

### 0.1 Data Infrastructure (Delivered)

| # | Component | Description | Status |
|---|-----------|-------------|--------|
| F1 | **PostgreSQL + pgvector** | Vector database for field-level embeddings (1024-dim BGE-large). Stores `field_embeddings` table with cosine similarity search. Single instance serves both vector search and relational storage. | Delivered |
| F2 | **Apache AGE Graph Database** | LookML structural graph — Model → Explore → View → Field nodes with join relationships. Powers structural validation ("are all matched fields reachable from a single explore?") and partition filter discovery. | Delivered |
| F3 | **LookML Parser + Graph Ingestion** | Parses `.view.lkml` and `.explore.lkml` files → loads into AGE graph. Creates Field nodes with type, description, sql expression. Refreshed on every LookML deploy. | Delivered |
| F4 | **Embedding Pipeline (BGE-large)** | Generates 1024-dim embeddings for every measure and dimension across all indexed explores. Uses BGE-large with query/document prefix distinction. Batch-loadable for new BU onboarding. | Delivered |
| F5 | **Filter Catalog Generation** | Auto-derives known dimension values from LookML parse → `filter_catalog.json`. Includes value_map, synonyms, yesno_dimensions, partition_fields per explore. | Delivered |
| F6 | **SafeChain / CIBIS Gateway** | All LLM calls (Gemini Flash) and embedding calls (text-embedding-005) route through Amex's SafeChain gateway. Handles auth, audit logging, model routing. Integrated at module level. | Delivered |
| F7 | **MCP Toolbox Sidecar** | Looker MCP server running as sidecar container. Exposes 33 Looker tools (query-sql, get-explore, list-fields, etc.) via Model Context Protocol. Cortex API calls MCP for deterministic SQL generation. | Delivered |
| F8 | **FastAPI Server + SSE Streaming** | Production API server with streaming Server-Sent Events. Endpoints: `/query`, `/trace`, `/feedback`, `/capabilities`, `/health`. CORS-ready for ChatGPT Enterprise frontend. | Delivered |

### 0.2 Platform Infrastructure (Shipping May–June)

| # | Component | Description | Target |
|---|-----------|-------------|--------|
| F9 | **GKE Deployment Architecture** | Cortex API + MCP sidecar as GKE pod. Auto-scaling, health probes, config volumes, secret management. Production-grade container orchestration. | June |
| F10 | **LookML Auto-Generation Pipeline** | Enrichment metadata (from Lumi) → auto-generates LookML view definitions with descriptions, labels, required_filters, synonyms. Git-based workflow: generate → PR → review → merge → graph refresh. | June |
| F11 | **Embedding Refresh Pipeline** | Scheduled job to re-embed fields when LookML changes. Detects new/modified fields, generates embeddings, updates pgvector. Ensures vector index stays current with semantic layer. | May |
| F12 | **BQ Log Mining Pipeline** | ETL job that scans 180 days of BigQuery query logs (INFORMATION_SCHEMA.JOBS). Extracts dimension value patterns from WHERE clauses to bootstrap filter catalog for new BUs. | May |
| F13 | **Golden Dataset Infrastructure** | Evaluation pipeline: 150+ verified query patterns (50/BU), stratified by complexity. Automated regression testing on every pipeline change. Tracks intent accuracy, retrieval precision, filter accuracy, E2E correctness. | May |
| F14 | **FAISS Index Build Pipeline** | Batch job to embed golden queries → build IVF index (256 centroids) for few-shot matching. Rebuilt on golden dataset expansion. Loaded at server startup. | May |
| F15 | **Observability Stack** | Structured logging (per-step timing, LLM call counts, confidence scores), trace persistence in PostgreSQL, health check endpoints with component-level status (pgvector, AGE, SafeChain, MCP). | May |
| F16 | **CI/CD Pipeline** | GitHub Actions: lint → type-check → unit tests → golden dataset regression → container build → staging deploy. PR-gated with accuracy regression checks. | June |
| F17 | **Redis Conversation Store** | Replace in-memory conversation state with Redis. Enables horizontal scaling (multiple API pods) and session persistence across deploys. | June |

---

## 1. Cortex AI Pipeline — "Ask your data in plain English"

The core NL2SQL intelligence layer. User types a business question, gets an answer with full explainability.

### 1.1 Delivered (In Demo Today)

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Intent Classification** | Single-LLM-call entity extraction — identifies metrics, dimensions, filters, time ranges, and intent type in ~300ms |
| 2 | **Hybrid Semantic Retrieval** | 3-channel search (vector embeddings + graph validation + few-shot matching) to find the right fields across 8,000+ datasets |
| 3 | **Explore Routing & Scoring** | Multiplicative scoring formula picks the correct data source. Handles 5 explores today, designed for 50+ |
| 4 | **Near-Miss Detection** | When AI confidence is low or two data sources score close, it asks the user to disambiguate instead of guessing |
| 5 | **5-Pass Filter Resolution** | Translates user language ("OPEN segment", "last quarter") to exact database values via exact match → synonyms → fuzzy → embedding → passthrough |
| 6 | **Mandatory Filter Injection** | Auto-applies partition date filters per Finance Data Office governance rules — prevents full-table scans |
| 7 | **SQL Generation via Looker MCP** | Generates deterministic SQL through Looker's semantic layer (not hallucinated SQL) |
| 8 | **Real-Time Pipeline Streaming** | SSE-based step-by-step animation — user sees each pipeline phase complete in real time |
| 9 | **Dual-View UI** | Analyst View (clean chat) + Engineering View (full pipeline trace with timing, confidence scores, scoring breakdown) |
| 10 | **Conversation Context** | Multi-turn follow-up queries within a session ("now break that down by generation") |
| 11 | **Confidence Scoring** | Numerical confidence at every stage — visible to users, not hidden. Enterprise explainability requirement. |
| 12 | **Follow-Up Suggestions** | AI generates 3 contextual follow-up questions after each answer |

### 1.2 Shipping May–June

| # | Feature | Description | Target |
|---|---------|-------------|--------|
| 13 | **Query Execution + Results Display** | Execute generated SQL against BigQuery, render results in paginated table with type-aware formatting | May |
| 14 | **Multi-BU Expansion** | Extend from Finance (1 BU) to 3 Business Units — new explores, field embeddings, filter catalogs per BU | June |
| 15 | **Learning Loop (Filter Synonyms)** | User corrections ("I said 'consumer' but meant 'CPS'") feed back into synonym catalog via Wilson score confidence. Steward-gated approval. | May |
| 16 | **Cost Control Gate** | Dry-run SQL estimation before execution. Budget enforcement per user/department. Prevents expensive runaway queries. | June |
| 17 | **Few-Shot Query Index** | FAISS index of 150+ golden queries (50/BU). Historical correct answers boost accuracy on similar new questions. | May |
| 18 | **Embedding-Based Filter Resolution** | Pass 4 of filter cascade — when exact/synonym/fuzzy all miss, use vector similarity to resolve filter values | May |
| 19 | **SafeChain Token Auto-Refresh** | Automatic token renewal on 401 — eliminates manual server restart on long-running sessions | May |
| 20 | **Feedback Loop** | Thumbs up/down + correction UI on every answer. Feeds golden dataset expansion + filter catalog improvement. | May |
| 21 | **Production Deployment (GKE)** | Cortex API + MCP sidecar on GKE. Auto-scaling, health checks, trace persistence in PostgreSQL. | June |

---

## 2. Semantic Enrichment (Lumi) — Renuka's Workstream

The metadata enrichment layer that feeds Cortex, Looker, and the Control Plane. Renuka owns this. Key deliverables we depend on:

| # | Feature | Description | Intersection with Cortex |
|---|---------|-------------|--------------------------|
| 22 | **Steward Enrichment UX** | Web interface for data stewards to add descriptions, synonyms, business terms to dimensions and measures | Enriched metadata flows into Cortex's vector search + filter catalog |
| 23 | **Synonym Registry** | Structured mapping of business terms → technical column names (e.g., "total spend" → `total_billed_business_amt`) | Directly consumed by Cortex filter resolution + retrieval |
| 24 | **Dimension Value Catalog** | Known values per dimension with business-friendly labels (e.g., `CPS` = "Consumer Personal Services") | Powers Pass 1-2 of filter resolution cascade |
| 25 | **LookML Auto-Generation** | Enrichment metadata auto-generates LookML view definitions — descriptions, labels, required_filters | Cortex reads LookML for graph structure + explore descriptions |
| 26 | **Enrichment Quality Scoring** | Measures completeness per field — % with descriptions, % with synonyms, % with value catalogs | Feeds Metric Playground "enriched vs. not" comparison |
| 27 | **Bulk Import from BQ Logs** | Bootstrap dimension values by analyzing 180 days of BigQuery WHERE clause patterns | Jumpstarts filter catalog for new BUs without manual steward entry |

---

## 3. Metric Playground — "See how your metric lives in the AI"

Interactive workspace where users define metrics, explore hierarchy, and see in real time how AI interprets and uses them. This is the bridge between Renuka's enrichment work and Cortex's AI pipeline — **the place where stewards see their work come alive.**

### 3.1 Delivered (In Demo Today — Static/Educational)

| # | Feature | Description |
|---|---------|-------------|
| 28 | **What Is a Metric (Layer Explorer)** | 3-layer interactive visualization: Raw Column → LookML Definition → Enriched Metric. Click each layer to see transformation. Uses `total_billed_business` as running example. |
| 29 | **Metric Hierarchy (Tree Explorer)** | Visual tree of metric relationships with governance tiers: Canonical (gold standard), BU Variant, Team Derived. Shows inheritance and deduplication warnings. |
| 30 | **Define a Metric (3 Paths)** | Three creation paths: From SQL, From Business Description, Enhance Existing. AI mock suggests synonyms, validates against existing metrics for overlap. |
| 31 | **How AI Uses It (Pipeline Trace)** | 4-step trace animation showing how a metric flows through Intent → Retrieval → Scoring → SQL. "What if it wasn't enriched?" comparison callout. |

### 3.2 Shipping May–June — "Live Playground"

| # | Feature | Description | Target |
|---|---------|-------------|--------|
| 32 | **Live Metric Editor** | Data stewards define a metric (name, SQL aggregation, description, synonyms, required filters) in a guided form — changes save to enrichment store | May |
| 33 | **Real-Time AI Impact Preview** | After editing a metric, user clicks "Test" and sees how Cortex would now route a sample query differently. Side-by-side before/after scoring. | June |
| 34 | **Synonym Sandbox** | Add/remove synonyms and see instant impact on retrieval similarity scores. "If I add 'total spend', does the AI now find this metric when someone says 'total spend'?" | May |
| 35 | **Metric Coverage Dashboard** | Visual heatmap showing which metrics are fully enriched (description + synonyms + value catalog + required filters) vs. gaps. Highlights highest-traffic unindexed metrics. | June |
| 36 | **Metric Lineage Graph** | Interactive visualization showing how a metric connects to its source table → LookML view → explore → other metrics that depend on it. Click any node to inspect. | June |
| 37 | **"What If" Scenario Mode** | User modifies any part of a metric definition and the playground shows predicted impact: which queries would now route differently, confidence score changes, new disambiguation triggers. | June |
| 38 | **Enrichment Diff View** | Before/after LookML diff when a steward changes a metric. Shows exactly what changes in the semantic layer definition. | May |

---

## 4. Control Plane — "See everything about your data, in one place"

Centralized dashboard for data governance leads and stewards to manage the metadata corpus that powers Cortex. Think of it as the "admin panel" for the AI's knowledge base.

| # | Feature | Description | Target |
|---|---------|-------------|--------|
| 39 | **Metadata Corpus Overview** | Dashboard showing: total fields indexed, % enriched, embedding coverage, filter catalog completeness — per BU, per explore, per view | May |
| 40 | **Field-Level Detail View** | Click any field to see: description, synonyms, known values, embedding vector quality, usage frequency (from BQ logs), last updated, enrichment score | May |
| 41 | **Explore Health Scorecard** | Per-explore quality score: % fields with descriptions, % measures with synonyms, filter catalog coverage, graph connectivity, embedding freshness | June |
| 42 | **Synonym Management** | CRUD interface for the synonym registry. Shows pending suggestions from learning loop, steward approval queue, auto-approved (Wilson score > 0.8). | May |
| 43 | **Filter Catalog Manager** | View and edit known dimension values. See which values came from BQ log mining, steward entry, or user feedback. Flag conflicts. | May |
| 44 | **Query Audit Trail** | Every Cortex query logged: what was asked, what was returned, confidence, which explore was chosen, latency, user feedback. Filterable by BU/user/time. | June |
| 45 | **Governance Rules Engine** | Define mandatory filters (e.g., "Finance queries MUST include partition_date within 90 days"), auto-injection rules, cost budget limits per BU. | June |
| 46 | **Enrichment Leaderboard** | Gamified view: which BUs have highest enrichment coverage, which stewards contributed most, which metrics are most queried but least enriched (priority gaps). | June |
| 47 | **BU Onboarding Wizard** | Guided flow to onboard a new Business Unit: connect explores, run embedding pipeline, bootstrap filter catalog from BQ logs, assign steward. | June |
| 48 | **Alert & Notification System** | Alerts when: enrichment score drops below threshold, new unresolved filter values accumulate, embedding index is stale, query accuracy drops for a BU. | June |

---

## Delivery Summary

| Month | Platform Foundation | Cortex Pipeline | Metric Playground | Control Plane | Lumi (Renuka) |
|-------|--------------------|--------------------|-------------------|---------------|---------------|
| **March** | pgvector, AGE, embeddings, SafeChain, MCP, FastAPI (8 delivered) | Demo-ready (12 features) | Static/educational (4 tabs) | — | — |
| **April** | — | Query execution, feedback loop | — | Architecture + wireframes | Steward UX MVP |
| **May** | Embedding refresh, BQ log mining, golden dataset infra, FAISS build, observability | Learning loop, few-shot, SafeChain fix, embedding filter resolution | Live editor, synonym sandbox, diff view | Corpus overview, field detail, synonym mgmt, filter catalog | Synonym registry, value catalog, BQ log import |
| **June** | GKE deploy, LookML auto-gen, CI/CD, Redis conversation store | Multi-BU (3 BUs), cost control | AI impact preview, coverage dashboard, lineage graph, what-if mode | Explore health, audit trail, governance rules, onboarding wizard, alerts | LookML auto-generation, quality scoring |

---

## Key Numbers

| Metric | Today | June Target |
|--------|-------|-------------|
| Business Units covered | 1 (Finance) | 3 |
| Explores indexed | 5 | 50+ |
| Tables accessible | ~20 | 100+ |
| End-to-end accuracy | ~83% | 90%+ |
| P95 latency | ~1.2s (to SQL) | <4s (including execution) |
| Golden dataset queries | 12 | 150+ (50/BU) |
| Filter resolution accuracy | ~85% | 95%+ |

---

## Dependencies Between Workstreams

```
RENUKA (Lumi)                    SAHEB (Cortex)
─────────────                    ──────────────
Steward UX ──────→ Synonym Registry ──────→ Filter Resolution
                                              ↓
Dimension Values ──────→ Filter Catalog ──→ Exact Match (Pass 1)
                                              ↓
LookML Auto-Gen ──────→ Graph Structure ──→ Explore Scoring
                                              ↓
Quality Scoring ──────→ Enrichment Score ──→ Metric Playground
                                              ↓
                                     Control Plane (reads all)
```

**Critical path:** Lumi's synonym registry + dimension value catalog directly gate Cortex's filter resolution accuracy. If steward enrichment stalls, accuracy plateaus at ~85%. With enrichment, 95%+ is achievable.

---

## Team Allocation (May–June)

| Person | Primary Focus | Secondary |
|--------|--------------|-----------|
| **Saheb** | Architecture, Cortex orchestration, Control Plane design | Metric Playground spec |
| **Likhita** | Intent Classification hardening, multi-BU entity extraction | Learning loop implementation |
| **Ravikanth** | Query execution pipeline, results processing, GKE deployment | Cost control gate |
| **Ayush** | Metric Playground (live features), Control Plane UI | UI polish |
| **Animesh** | Golden dataset expansion (3 BUs), evaluation framework | BQ log mining for filter catalog |
| **Accenture** | Filter catalog build-out, synonym bootstrap per BU | Control Plane backend APIs |

---

*65 items across 5 layers. 20 delivered today (8 foundation + 12 pipeline). 45 shipping May–June.*
