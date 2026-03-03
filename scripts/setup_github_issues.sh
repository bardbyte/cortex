#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Cortex — GitHub Issues Setup
# ─────────────────────────────────────────────────────────────────
# Run this from your corp laptop after creating the GitHub repo.
#
# Prerequisites:
#   gh auth login
#   cd <repo-root>
#
# Usage:
#   chmod +x scripts/setup_github_issues.sh
#   ./scripts/setup_github_issues.sh
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

echo "=== Setting up Cortex GitHub project management ==="

# ─── LABELS ─────────────────────────────────────────────────────
echo "Creating labels..."

gh label create "retrieval"     --color "1d76db" --description "Hybrid retrieval system (vector + graph + fewshot)" --force
gh label create "pipeline"      --color "0e8a16" --description "ADK agent orchestration pipeline" --force
gh label create "taxonomy"      --color "d93f0b" --description "Business term taxonomy + LookML generation" --force
gh label create "evaluation"    --color "fbca04" --description "Golden dataset + accuracy measurement" --force
gh label create "deployment"    --color "5319e7" --description "GKE, infrastructure, CI/CD" --force
gh label create "connector"     --color "006b75" --description "Looker MCP, BigQuery, LLM access connectors" --force
gh label create "ui"            --color "c2e0c6" --description "UI components" --force
gh label create "P0-critical"   --color "b60205" --description "Blocks May deadline" --force
gh label create "P1-important"  --color "e99695" --description "Important but not blocking" --force
gh label create "P2-nice"       --color "c5def5" --description "Nice to have" --force
gh label create "spike"         --color "d4c5f9" --description "Research / exploration task" --force

# ─── MILESTONES ─────────────────────────────────────────────────
echo "Creating milestones..."

gh api repos/{owner}/{repo}/milestones -f title="M1: Prove the Loop" \
  -f description="ONE query works end-to-end: NL → intent → retrieval → Looker MCP → BigQuery → answer" \
  -f due_on="2026-03-21T00:00:00Z" \
  -f state="open" 2>/dev/null || echo "M1 exists"

gh api repos/{owner}/{repo}/milestones -f title="M2: Reliable Retrieval" \
  -f description=">85% retrieval accuracy on golden dataset. All 3 channels (vector + graph + fewshot) operational." \
  -f due_on="2026-04-11T00:00:00Z" \
  -f state="open" 2>/dev/null || echo "M2 exists"

gh api repos/{owner}/{repo}/milestones -f title="M3: Handle the Edges" \
  -f description=">90% end-to-end accuracy. Boundary detection, disambiguation, caching, response formatting." \
  -f due_on="2026-05-02T00:00:00Z" \
  -f state="open" 2>/dev/null || echo "M3 exists"

gh api repos/{owner}/{repo}/milestones -f title="M4: Production Ready" \
  -f description="May deadline: 3 BUs, feedback loop, cost controls, monitoring, ChatGPT Enterprise integration." \
  -f due_on="2026-05-30T00:00:00Z" \
  -f state="open" 2>/dev/null || echo "M4 exists"

# ─── ISSUES ─────────────────────────────────────────────────────
echo "Creating issues..."

# ──── MILESTONE 1: Prove the Loop (Weeks 1-3) ────

gh issue create \
  --title "Set up LLM access pathway (SafeChain + CIBIS)" \
  --label "connector,P0-critical" \
  --milestone "M1: Prove the Loop" \
  --assignee "bardbyte" \
  --body "$(cat <<'EOF'
## Objective
Set up the SafeChain LLM access pathway so the pipeline can call Gemini through Amex auth.

## Deliverables
- [ ] Implement `src/connectors/safechain_client.py` — bridge SafeChain → ADK BaseLlm
- [ ] Add CIBIS credentials to `.env.example` once validated
- [ ] Add safechain + ee_config + langchain-core==0.3.83 to dependencies
- [ ] Update `examples/verify_setup.py` with SafeChain + LLM checks
- [ ] Document the setup in README

## Context
All LLM access at Amex routes through SafeChain (CIBIS authentication). The PoC in `access_llm/`
demonstrates the pattern: `Config.from_env()` → `MCPToolLoader.load_tools(config)` → `MCPToolAgent`.

Two integration paths to evaluate:
- **Path A**: Custom `BaseLlm` wrapper — ADK Agent calls SafeChain under the hood
- **Path B**: SafeChain's MCPToolAgent for execution, ADK for orchestration

## Acceptance Criteria
1. `verify_setup.py` includes SafeChain auth check + Gemini LLM call check
2. A simple query through SafeChain returns a valid response
3. Team can replicate setup with just `.env.example` + README instructions

## Owner: Saheb
## Due: End of Week 1
EOF
)"

gh issue create \
  --title "Set up Conversational Analytics API PoC" \
  --label "spike,P0-critical" \
  --milestone "M1: Prove the Loop" \
  --assignee "bardbyte" \
  --body "$(cat <<'EOF'
## Objective
Stand up a working PoC of Google's Conversational Analytics API. Run test queries and
document capabilities vs limitations. This informs our Build vs Compose decision.

## Deliverables
- [ ] Working notebook: `notebooks/conv_analytics_poc.ipynb`
- [ ] 10 test queries (simple → complex) with results documented
- [ ] Capabilities table: what it handles vs what it doesn't
- [ ] Latency measurements per query
- [ ] Comparison notes: where Cortex pipeline adds value over raw API

## Key Questions to Answer
1. Does it respect `always_filter` / partition filters?
2. How does it handle ambiguous terms (e.g., "revenue")?
3. Can it handle cross-explore queries?
4. What's the accuracy on moderate/complex queries?
5. Rate limits and pricing post-preview?

## Context
Free until Sept 2026. We want to benchmark it against our pipeline on the same
queries to validate the COMPOSE strategy (own the brain, use Looker for SQL).

## Owner: Saheb
## Due: This week (March 7)
EOF
)"

gh issue create \
  --title "Finance BU: LookML enhancement + field descriptions" \
  --label "taxonomy,P0-critical" \
  --milestone "M1: Prove the Loop" \
  --assignee "Ayush" \
  --body "$(cat <<'EOF'
## Objective
Enhance the Finance BU LookML with rich field descriptions, labels, and group_labels
so that Cortex's retrieval can accurately find the right fields from natural language.

## Deliverables
- [ ] Review all Finance BU views (7 views, 1 model)
- [ ] Add/improve `description` on every dimension and measure
- [ ] Add `group_label` for logical grouping (e.g., "Transaction Metrics", "Customer Attributes")
- [ ] Add `label` where the dimension name isn't intuitive
- [ ] Ensure `always_filter` is set on partitioned tables
- [ ] Document which explores exist and their join relationships

## Why This Matters
Cortex's retrieval accuracy is directly proportional to the quality of field descriptions.
A field with no description = invisible to vector search. Every description you add
directly improves accuracy.

## Format for descriptions
Include the business definition + common synonyms:
```
description: "Total dollar amount of all transactions. Also known as: total spend,
transaction volume, gross amount."
```

## Acceptance Criteria
1. Every dimension and measure in Finance BU has a non-empty description
2. Descriptions include business synonyms (what people actually call it)
3. Group labels applied consistently across views
4. LookML validates and deploys cleanly

## Owner: Ayush (Animesh can help with UI if needed)
## Due: March 10
EOF
)"

gh issue create \
  --title "Finance BU: Looker project viewer UI" \
  --label "ui,taxonomy,P1-important" \
  --milestone "M1: Prove the Loop" \
  --body "$(cat <<'EOF'
## Objective
Build a read-only UI to browse the Finance BU Looker project structure — helps the
team see what models, explores, views, and fields exist without needing Looker access.

## Deliverables
- [ ] Web UI showing model → explore → view → field hierarchy
- [ ] Search by field name or description
- [ ] Show field descriptions, types, and join relationships
- [ ] Read-only (no modifications)

## Context
This supports the LookML enhancement work (see related issue) and helps the whole
team understand the data model they're building retrieval against.

## Owner: Ayush + Animesh (UI)
## Due: March 10
EOF
)"

gh issue create \
  --title "Load LookML into Neo4j knowledge graph" \
  --label "retrieval,P0-critical" \
  --milestone "M1: Prove the Loop" \
  --body "$(cat <<'EOF'
## Objective
Parse LookML files and load the model/explore/view/dimension/measure structure into Neo4j.

## Deliverables
- [ ] Script that parses `.lkml` files using the `lkml` library
- [ ] Creates Neo4j nodes: Model, Explore, View, Dimension, Measure
- [ ] Creates edges: CONTAINS, BASE_VIEW, JOINS, HAS_DIMENSION, HAS_MEASURE
- [ ] Handles `always_filter`, `sql_on`, join relationship types
- [ ] Unit tests for parser + graph loading
- [ ] Works on the Finance BU LookML files (7 views, 1 model)

## Starting Point
- `scripts/load_lookml_to_neo4j.py` — starter script with schema
- `src/retrieval/graph_search.py` — Cypher queries this enables
- Run Neo4j locally: `docker compose up neo4j`

## Acceptance Criteria
1. Can load all Finance BU LookML into Neo4j
2. Can query: "What explores exist in the finance model?" → correct answer
3. Can query: "What dimensions are in the transactions explore?" → correct answer
4. Script is idempotent (re-run safely)

## Due: End of Week 2
EOF
)"

gh issue create \
  --title "Deploy Looker MCP Server on GKE" \
  --label "deployment,connector,P0-critical" \
  --milestone "M1: Prove the Loop" \
  --body "$(cat <<'EOF'
## Objective
Deploy the Looker MCP Server so the pipeline can call `query_sql` to generate deterministic SQL.

## Deliverables
- [ ] GKE deployment manifest for Looker MCP server
- [ ] Service account with Looker API credentials
- [ ] Health check endpoint
- [ ] Verify all critical MCP tools work:
  - `get_models` → returns list of models
  - `get_explores` → returns explores for a model
  - `get_dimensions` / `get_measures` → returns fields
  - `query_sql` → generates correct SQL from {model, explore, fields, filters}
- [ ] Document the endpoint URL and auth for team use

## Context
- Looker MCP has 33 tools. We only need ~8 for the pipeline.
- Critical tool: `query_sql` — this is what replaces LLM SQL generation.

## Acceptance Criteria
1. MCP server is running on GKE and accessible from dev environment
2. `query_sql` returns valid BigQuery SQL for a test query
3. Other team members can call the endpoint

## Due: End of Week 2
EOF
)"

gh issue create \
  --title "Index LookML fields into Vertex AI Search" \
  --label "retrieval,P0-critical" \
  --milestone "M1: Prove the Loop" \
  --body "$(cat <<'EOF'
## Objective
Build the Vertex AI Search corpus from LookML field descriptions for semantic search.

## Deliverables
- [ ] Script to build corpus: one document per field, enriched with explore/view context
- [ ] Each document includes: field name, type, description, view, explore, model
- [ ] Structured metadata for filtering
- [ ] Search function that returns top-K fields by semantic similarity
- [ ] Unit tests

## Starting Point
- `src/retrieval/vector.py` — `build_search_corpus()` function ready to implement

## Key Design Decision
Per-field chunking is intentional. Per-view returns too many irrelevant fields.

## Acceptance Criteria
1. Corpus built from Finance BU LookML
2. Search "total spend" → returns `transactions.total_amount` in top-3
3. Search "merchant category" → returns `merchants.category_name` in top-3

## Due: End of Week 2
EOF
)"

gh issue create \
  --title "Build end-to-end pipeline skeleton (ADK)" \
  --label "pipeline,P0-critical" \
  --milestone "M1: Prove the Loop" \
  --body "$(cat <<'EOF'
## Objective
Wire up the ADK agent with tools for each pipeline stage so ONE query works end-to-end.

## Deliverables
- [ ] ADK root agent with system instruction enforcing pipeline sequence
- [ ] Tools registered: classify_intent, extract_entities, retrieve_fields, validate_sql, format_response
- [ ] McpToolset connected to deployed Looker MCP server
- [ ] One working query: "What was total spend last quarter?" → correct answer

## Starting Point
- `src/pipeline/agent.py` — ADK agent structure and implementation guide
- `src/pipeline/state.py` — state schema
- ADK docs: https://google.github.io/adk-docs/

## Dependencies
- Needs: LLM access (#1), Neo4j loaded (#5), Looker MCP deployed (#6), Vertex Search indexed (#7)

## Acceptance Criteria
1. `python -m src.pipeline.agent --query "What was total spend last quarter?"` → correct answer
2. Can trace each tool call in the agent's output

## Due: End of Week 3
EOF
)"

# ──── MILESTONE 2: Reliable Retrieval (Weeks 3-6) ────

gh issue create \
  --title "Map business terms to LookML (7 views, Finance BU)" \
  --label "taxonomy,P0-critical" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Create taxonomy YAML entries for all business terms in the Finance BU's 7 views.

## Deliverables
- [ ] 30-50 taxonomy YAML entries
- [ ] Each entry: canonical_name, definition, synonyms, lookml_target
- [ ] Focus on SYNONYM QUALITY — list every name people use for each concept
- [ ] Validate: `python -m src.taxonomy.schema validate taxonomy/finance/`

## Why Synonyms Matter
When a user says "CAC" but the field is `acq_cost_per_unit`, vector search fails
without synonyms. Every synonym you add directly improves retrieval accuracy.

## Acceptance Criteria
1. 30+ taxonomy entries for Finance BU
2. Each entry has at least 3 synonyms
3. All entries pass schema validation

## Due: End of Week 4
EOF
)"

gh issue create \
  --title "Implement structural validation gate (Neo4j)" \
  --label "retrieval,P0-critical" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Implement Neo4j Cypher queries that validate whether candidate fields are structurally
reachable from a single Explore. This is the #1 quality gate.

## Deliverables
- [ ] `validate_fields_in_explore()` — given fields, find explores containing ALL of them
- [ ] `get_explore_schema()` — all fields available in an explore
- [ ] `resolve_business_term()` — business term → LookML fields via taxonomy nodes
- [ ] `get_partition_filters()` — required filters for cost control
- [ ] Integration tests with real Neo4j

## Starting Point
- `src/retrieval/graph_search.py` — Cypher queries written, class structure ready

## Acceptance Criteria
1. Given ["total_amount", "category_name"], returns "transactions" explore
2. Given fields from different explores, returns empty (correctly rejects)
3. Partition filter query returns `always_filter` requirements

## Due: End of Week 5
EOF
)"

gh issue create \
  --title "Build golden dataset (50 queries, Finance BU)" \
  --label "evaluation,P0-critical" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Create 50 human-verified {question → expected answer} pairs for the Finance BU.

## Three Sources
1. **Looker Query History** — export top 100 queries, generate NL versions
2. **SME Questions** — ask Finance analysts their top 20 questions
3. **Synthetic** — LLM-generated, manually validated

## Deliverables
- [ ] 50+ golden queries in `tests/golden_queries/finance/`
- [ ] Mix: simple (20), moderate (20), complex (10)
- [ ] Run: `python scripts/run_eval.py --dataset=tests/golden_queries/finance/`

## Starting Point
- `tests/golden_queries/finance/_template.json`
- `src/evaluation/golden.py` — loader + evaluator

## Due: End of Week 5
EOF
)"

gh issue create \
  --title "Implement RRF fusion layer" \
  --label "retrieval,P0-critical" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Implement Reciprocal Rank Fusion to merge vector + graph + fewshot results.

## Deliverables
- [ ] `reciprocal_rank_fusion()` — merge ranked lists with configurable weights
- [ ] `fuse_and_validate()` — RRF → group by explore → validate → decide
- [ ] Decision logic: proceed / disambiguate / clarify / no_match
- [ ] Weights from config: graph=1.5, fewshot=1.2, vector=1.0
- [ ] Unit tests with mock retrieval results

## Starting Point
- `src/retrieval/fusion.py` — implementation ready for testing/refinement
- `config/retrieval.yaml` — configurable weights

## Due: End of Week 5
EOF
)"

# ──── MILESTONE 3: Handle the Edges (Weeks 6-10) ────

gh issue create \
  --title "Add boundary detection (graceful refusal)" \
  --label "pipeline,P1-important" \
  --milestone "M3: Handle the Edges" \
  --body "$(cat <<'EOF'
## Objective
Detect unanswerable queries and refuse gracefully with helpful alternatives.

## Out-of-Scope Queries
- Predictions: "Predict next quarter's revenue"
- Causal: "Why did X happen?"
- Data mods: "Update/delete X"
- PII: "Show me customer SSNs"

## Deliverables
- [ ] Boundary detection in intent classification
- [ ] Graceful refusal with 2-3 alternative suggestions
- [ ] 20+ boundary test cases

## Due: End of Week 7
EOF
)"

gh issue create \
  --title "Add complexity-aware routing" \
  --label "pipeline,P1-important" \
  --milestone "M3: Handle the Edges" \
  --body "$(cat <<'EOF'
## Objective
Route simple queries directly to Looker MCP (skip retrieval), saving 40% of tokens.

## Routing: Simple → fast path | Moderate → standard | Complex → decompose

## Deliverables
- [ ] Complexity classifier in intent stage
- [ ] Simple query fast path (skip retrieval)
- [ ] Complex query decomposition
- [ ] Token savings measurements

## Due: End of Week 8
EOF
)"

gh issue create \
  --title "Add disambiguation flow" \
  --label "pipeline,P1-important" \
  --milestone "M3: Handle the Edges" \
  --body "$(cat <<'EOF'
## Objective
When the query is ambiguous, present options to the user instead of guessing.

## Deliverables
- [ ] Disambiguation detection in fusion layer
- [ ] User-facing options with clear descriptions
- [ ] 10+ disambiguation test cases

## Due: End of Week 8
EOF
)"

gh issue create \
  --title "Implement caching (3 layers)" \
  --label "pipeline,P1-important" \
  --milestone "M3: Handle the Edges" \
  --body "$(cat <<'EOF'
## Objective
Add caching: exact match (15min), semantic (1hr), metadata (5min). Target 60%+ hit rate.

## Deliverables
- [ ] Exact match cache
- [ ] Semantic cache (embedding similarity > 0.95)
- [ ] Metadata cache (Looker MCP responses)
- [ ] TTLs configurable via `config/retrieval.yaml`

## Due: End of Week 9
EOF
)"

# ──── MILESTONE 4: Production Ready ────

gh issue create \
  --title "Evaluate Conversational Analytics API vs Cortex" \
  --label "spike,P0-critical" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Run the same 20 queries through Google's Conversational Analytics API and Cortex.
Make the Build vs Compose decision with data.

## Deliverables
- [ ] Benchmark notebook: `notebooks/conv_analytics_comparison.ipynb`
- [ ] Per-query comparison table (accuracy, latency, cost)
- [ ] Decision document: Compose confirmed or revised

## Depends on: Conv Analytics API PoC (#2), Golden dataset (#11)
## Due: End of Week 5
EOF
)"

gh issue create \
  --title "Build feedback loop (user corrections → taxonomy + golden)" \
  --label "pipeline,P1-important" \
  --milestone "M4: Production Ready" \
  --body "$(cat <<'EOF'
## Objective
User corrections feed back to improve accuracy over time.

## Deliverables
- [ ] Feedback capture (thumbs up/down, "I meant X")
- [ ] Pipeline: correction → golden dataset queue
- [ ] Pipeline: new synonym → taxonomy update PR

## Due: End of Week 12
EOF
)"

gh issue create \
  --title "Observability: latency, accuracy, and cost dashboards" \
  --label "pipeline,deployment,P1-important" \
  --milestone "M4: Production Ready" \
  --body "$(cat <<'EOF'
## Objective
Full visibility into pipeline health, accuracy, and cost.

## Deliverables
- [ ] Structured logging at each pipeline stage
- [ ] Dashboard: latency P50/P90/P99 by stage
- [ ] Dashboard: accuracy trend, cost per query
- [ ] Alerting: accuracy < 85%, latency P90 > 10s

## Due: End of Week 13
EOF
)"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Created:"
echo "  - 11 labels"
echo "  - 4 milestones (M1-M4)"
echo "  - 19 issues"
echo ""
echo "Team assignments:"
echo "  - Saheb: LLM access pathway (#1), Conv Analytics API PoC (#2)"
echo "  - Ayush: LookML enhancement (#3, due March 10), Looker viewer UI (#4)"
echo "  - Animesh: Can help Ayush with UI (#4), golden dataset (#11)"
echo "  - Rajesh + Likhita: Neo4j (#5), GKE deployment (#6), graph validation (#10)"
echo ""
echo "Next steps:"
echo "  1. Assign remaining issues to team members"
echo "  2. Pin the milestone board view"
echo "  3. Start with M1 issues"
