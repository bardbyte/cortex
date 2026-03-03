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
gh label create "pipeline"      --color "0e8a16" --description "LangGraph orchestration pipeline" --force
gh label create "taxonomy"      --color "d93f0b" --description "Business term taxonomy + LookML generation" --force
gh label create "evaluation"    --color "fbca04" --description "Golden dataset + accuracy measurement" --force
gh label create "deployment"    --color "5319e7" --description "GKE, infrastructure, CI/CD" --force
gh label create "connector"     --color "006b75" --description "Looker MCP, BigQuery, ChatGPT connectors" --force
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
- The MCP server connects to our Looker instance and wraps the API.

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
- [ ] Chunking: per-field (NOT per-view, NOT per-explore)
- [ ] Each document includes: field name, type, description, view, explore, model
- [ ] Structured metadata (`structData`) for filtering
- [ ] Search function that returns top-K fields by semantic similarity
- [ ] Unit tests

## Starting Point
- `src/retrieval/vector.py` — `build_search_corpus()` function ready to implement
- `scripts/build_vertex_corpus.py` — create this script

## Key Design Decision
Per-field chunking is intentional. Per-view returns too many irrelevant fields alongside
the ones you need. Per-field lets retrieval pinpoint exact matches.

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
- [ ] McpToolset connected to deployed Looker MCP server (tool_filter to restrict to 5 tools)
- [ ] Retrieval tool calls real vector + graph search
- [ ] BigQuery execution + validation tool
- [ ] One working query: "What was total spend last quarter?" → correct answer

## Starting Point
- `src/pipeline/agent.py` — ADK agent structure and implementation guide
- `src/pipeline/state.py` — state schema
- ADK docs: https://google.github.io/adk-docs/
- McpToolset docs: https://google.github.io/adk-docs/tools/mcp-tools/

## Dependencies
- Needs: Neo4j loaded (#1), Looker MCP deployed (#2), Vertex Search indexed (#3)

## Acceptance Criteria
1. `python -m src.pipeline.agent --query "What was total spend last quarter?"` returns correct answer
2. Can trace each tool call in the agent's output
3. Pipeline handles simple query without crashing

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
Create taxonomy YAML entries for all business terms in the Finance BU's 7 views + 1 model.

## Deliverables
- [ ] Taxonomy YAML file for each key business term (target: 30-50 terms)
- [ ] Each entry: canonical_name, definition, formula (if metric), synonyms, column_mappings, lookml_target
- [ ] Focus on SYNONYM QUALITY — list every name people use for each concept
- [ ] Validate all entries: `python -m src.taxonomy.schema validate taxonomy/finance/`
- [ ] Generate enriched LookML descriptions from taxonomy

## Starting Point
- `taxonomy/finance/_template.yaml` — copy this for each term
- `src/taxonomy/schema.py` — validates your entries

## Why Synonyms Matter
When a user says "CAC" but the LookML field is `acq_cost_per_unit`, vector search
fails without synonyms. Every synonym you add directly improves retrieval accuracy.
The description format is: Definition + "Also known as: [synonyms]" + Usage note.

## Acceptance Criteria
1. 30+ taxonomy entries for Finance BU
2. Each entry has at least 3 synonyms
3. All entries pass schema validation
4. Generated LookML descriptions include synonyms

## Due: End of Week 4
EOF
)"

gh issue create \
  --title "Implement structural validation gate (Neo4j)" \
  --label "retrieval,P0-critical" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Implement the Neo4j Cypher queries that validate whether candidate fields from vector search
are structurally reachable from a single Explore.

## Why This Matters
This is the single most important quality gate in the system. Vector search returns
semantically similar fields but doesn't understand LookML structure. The graph check
prevents the #1 error: selecting fields from incompatible explores.

## Deliverables
- [ ] `validate_fields_in_explore()` — given field names, find explores containing ALL of them
- [ ] `get_explore_schema()` — all fields available in an explore
- [ ] `resolve_business_term()` — business term → LookML fields via taxonomy nodes
- [ ] `get_partition_filters()` — required filters for cost control
- [ ] Load BusinessTerm nodes from taxonomy YAML into Neo4j
- [ ] Integration tests with real Neo4j

## Starting Point
- `src/retrieval/graph_search.py` — all 5 Cypher queries are written, class structure ready

## Acceptance Criteria
1. Given ["total_amount", "category_name"], returns "transactions" explore
2. Given fields from different explores, returns empty (correctly rejects)
3. Business term "CAC" resolves to the correct LookML field
4. Partition filter query returns `always_filter` requirements

## Due: End of Week 5
EOF
)"

gh issue create \
  --title "Build golden dataset (50 queries, Finance BU)" \
  --label "evaluation,P0-critical" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Create the first golden dataset — 50 human-verified {question → expected answer} pairs
for the Finance BU.

## Three Sources (In Priority Order)

### Source 1: Looker Query History (highest value)
1. Export top 100 most-run queries from Looker for Finance BU
2. Use LLM to generate natural language versions
3. Manually verify the NL ↔ query pairing
4. Add to golden dataset

### Source 2: SME Questions
1. Ask 3 Finance analysts: "What are the 20 questions you ask most?"
2. Map their questions to LookML {explore, dimensions, measures}
3. Add to golden dataset

### Source 3: Synthetic Generation
1. For each Finance explore, use LLM to generate 10 questions
2. Manually validate and correct
3. Add to golden dataset

## Deliverables
- [ ] 50+ golden queries in `tests/golden_queries/finance/`
- [ ] JSON format per `_template.json`
- [ ] Coverage: at least 5 queries per complexity level (simple/moderate/complex)
- [ ] Each query has: NL question, expected model/explore/dimensions/measures
- [ ] Run evaluation: `python scripts/run_eval.py --dataset=tests/golden_queries/finance/`

## Starting Point
- `tests/golden_queries/finance/_template.json`
- `src/evaluation/golden.py` — loader + evaluator ready

## Acceptance Criteria
1. 50+ verified golden queries
2. Mix of simple (20), moderate (20), complex (10)
3. Evaluation script runs and produces metrics report

## Due: End of Week 5
EOF
)"

gh issue create \
  --title "Implement RRF fusion layer" \
  --label "retrieval,P0-critical" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Implement Reciprocal Rank Fusion to merge vector + graph + fewshot results,
plus the structural validation gate.

## Deliverables
- [ ] `reciprocal_rank_fusion()` — merge ranked lists with configurable weights
- [ ] `fuse_and_validate()` — full pipeline: RRF → group by explore → validate → decide
- [ ] Decision logic: proceed / disambiguate / clarify / no_match
- [ ] Weights from config: graph=1.5, fewshot=1.2, vector=1.0
- [ ] Unit tests with mock retrieval results
- [ ] Integration test with real Neo4j validation

## Starting Point
- `src/retrieval/fusion.py` — full implementation ready for testing/refinement

## Acceptance Criteria
1. Given 3 ranked lists, produces correct fused ranking
2. Structural validation correctly rejects cross-explore field combinations
3. Disambiguation triggers when 2+ explores score similarly
4. Configurable weights via `config/retrieval.yaml`

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
- Predictions/forecasting: "Predict next quarter's revenue"
- Causal analysis: "Why did X happen?"
- Data modifications: "Update/delete X"
- PII queries: "Show me customer SSNs"
- Non-data: "Write me an email"

## Deliverables
- [ ] Boundary detection in intent classification stage
- [ ] Graceful refusal with 2-3 alternative suggestions
- [ ] PII detection (refuse queries targeting PII columns)
- [ ] 20+ boundary test cases in golden dataset

## Acceptance Criteria
1. "Predict next quarter's revenue" → refusal + alternative suggestions
2. "Show me customer SSNs" → refusal
3. Zero hallucinated answers for out-of-scope queries

## Due: End of Week 7
EOF
)"

gh issue create \
  --title "Add complexity-aware routing (EllieSQL pattern)" \
  --label "pipeline,P1-important" \
  --milestone "M3: Handle the Edges" \
  --body "$(cat <<'EOF'
## Objective
Route simple queries directly to Looker MCP (skip retrieval), saving 40% of tokens.

## Routing Logic
- **Simple** (single table, single measure, obvious mapping): fast path → Looker MCP
- **Moderate** (joins, filters, time ranges): standard path → retrieval → Looker MCP
- **Complex** (multi-hop, cross-domain): deep path → decompose + retrieve per sub-query

## Deliverables
- [ ] Complexity classifier in intent stage
- [ ] Simple query fast path (skip retrieval)
- [ ] Complex query decomposition into sub-queries
- [ ] Latency and token measurements per path

## Acceptance Criteria
1. "What was total revenue?" routes to simple path (no retrieval)
2. "Spend by merchant category last quarter" routes to moderate path
3. Token savings measured: >30% reduction for simple queries

## Due: End of Week 8
EOF
)"

gh issue create \
  --title "Add disambiguation flow" \
  --label "pipeline,P1-important" \
  --milestone "M3: Handle the Edges" \
  --body "$(cat <<'EOF'
## Objective
When the query is ambiguous (e.g., "revenue" could mean 3 things), present options
to the user instead of guessing.

## Deliverables
- [ ] Disambiguation detection in fusion layer (multiple explores score similarly)
- [ ] User-facing disambiguation response with clear options
- [ ] Store user preference for future queries (personalization)
- [ ] 10+ disambiguation test cases

## Acceptance Criteria
1. "Show me revenue" → presents gross/net/card fee options
2. User selects "net revenue" → correct query executes
3. Next time user says "revenue" → defaults to net (personalized)

## Due: End of Week 8
EOF
)"

gh issue create \
  --title "Implement caching (3 layers)" \
  --label "pipeline,P1-important" \
  --milestone "M3: Handle the Edges" \
  --body "$(cat <<'EOF'
## Objective
Add caching to reduce latency and cost.

## Three Layers
1. **Exact match** — hash(normalize(query)) → cached result (TTL: 15min)
2. **Semantic** — embedding similarity > 0.95 → cached result (TTL: 1hr)
3. **Metadata** — cache Looker MCP get_models/get_explores (TTL: 5min)

## Target
- Combined cache hit rate: 60%+ at steady state
- Exact match latency: <5ms
- Semantic cache latency: ~50ms

## Deliverables
- [ ] Exact match cache (Redis or in-memory)
- [ ] Semantic cache (embedding similarity check)
- [ ] Metadata cache (Looker MCP responses)
- [ ] Cache hit/miss metrics
- [ ] TTLs configurable via `config/retrieval.yaml`

## Due: End of Week 9
EOF
)"

# ──── MILESTONE 4: Production Ready ────

gh issue create \
  --title "Evaluate Conversational Analytics API vs Cortex" \
  --label "spike,P0-critical" \
  --milestone "M1: Prove the Loop" \
  --body "$(cat <<'EOF'
## Objective
Run the same queries through Google's Conversational Analytics API and Cortex.
Make the final Build vs Compose decision with data.

## Test Plan
1. Select 20 queries from golden dataset (mix of simple/moderate/complex)
2. Run through Conversational Analytics API
3. Run through Cortex pipeline
4. Compare: accuracy, latency, disambiguation handling, cost
5. Document findings

## Evaluation Criteria
| Criterion | Weight |
|-----------|--------|
| Accuracy on moderate/complex queries | 40% |
| Disambiguation handling | 20% |
| Enterprise guardrails (PII, cost control) | 20% |
| Latency | 10% |
| Cost predictability | 10% |

## Expected Outcome
Validate the COMPOSE strategy: own the agent brain (intent, retrieval, guardrails),
use Looker MCP for SQL generation, benchmark against API for simple queries.

## Deliverables
- [ ] Benchmark notebook: `notebooks/03_conv_analytics_comparison.ipynb`
- [ ] Results table with per-query comparison
- [ ] Decision document: Compose confirmed or revised
- [ ] Share findings with team

## Due: End of Week 1
EOF
)"

gh issue create \
  --title "Build feedback loop (user corrections → taxonomy + golden)" \
  --label "pipeline,P1-important" \
  --milestone "M4: Production Ready" \
  --body "$(cat <<'EOF'
## Objective
User corrections feed back into the system to improve accuracy over time.

## Feedback Types
- Thumbs up → implicit correct, add to golden dataset candidates
- Thumbs down → flag for review
- "I meant X not Y" → new synonym mapping
- User corrects term → update taxonomy

## Deliverables
- [ ] Feedback capture in response format
- [ ] Pipeline: correction → golden dataset queue (for human review)
- [ ] Pipeline: new synonym → taxonomy update PR
- [ ] Dashboard: feedback volume, correction rate, common mismatches

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

## Metrics
- Per-stage latency (intent, retrieval, SQL gen, execution, formatting)
- Retrieval accuracy (daily golden dataset eval)
- Cache hit rates (exact, semantic, metadata)
- Token usage per query
- BigQuery bytes scanned + cost per query
- User satisfaction (thumbs up/down rate)

## Deliverables
- [ ] Structured logging at each pipeline stage
- [ ] Metrics export (Prometheus/Cloud Monitoring)
- [ ] Dashboard: latency P50/P90/P99 by stage
- [ ] Dashboard: accuracy trend over time
- [ ] Dashboard: cost per query trend
- [ ] Alerting: accuracy drops below 85%, latency P90 > 10s

## Due: End of Week 13
EOF
)"

gh issue create \
  --title "Looker project read-only viewer UI" \
  --label "taxonomy,P2-nice" \
  --milestone "M2: Reliable Retrieval" \
  --body "$(cat <<'EOF'
## Objective
Build a read-only UI to browse the Looker project structure (models, explores, views, fields).
Helps the team understand what's available without needing Looker access.

## Deliverables
- [ ] Web UI showing model → explore → view → field hierarchy
- [ ] Search by field name or description
- [ ] Show field descriptions, types, and join relationships
- [ ] Read-only (no modifications)

## Due: End of Week 5
EOF
)"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Created:"
echo "  - 10 labels"
echo "  - 4 milestones (M1-M4)"
echo "  - 15 issues"
echo ""
echo "Next steps:"
echo "  1. Assign issues to team members"
echo "  2. Pin the milestone board view"
echo "  3. Start with M1 issues"
