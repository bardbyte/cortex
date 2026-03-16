# Slack Message — Likhita + Rajesh

**Channel:** DM or team channel
**Copy-paste ready:**

---

Hey Likhita, Rajesh — quick update on retrieval strategy and what I need from you.

**Where we are:**
Your retrieval branch (`feature/likhita-rajesh-retrieval-implementation`) is good foundational work — entity extraction, vector search, and graph validation are all structurally sound. I pulled from your branch and built the full orchestration pipeline on top in `saheb/orchestrator-v1`.

**What changed while building on top:**
While integrating the retrieval pipeline with the orchestrator (SSE streaming, Looker MCP, multi-turn conversations), I found several issues that need to be addressed in your branch before we merge. The big ones:

1. **Coverage calculation bug** — `coverage = total_entities / total_entities` always returns 1.0. Should be `supported_entities_count / total_entities`. This makes the scoring formula unable to distinguish between a good and bad explore match.

2. **Sequential embedding calls** — Right now each entity gets its own embedding API call. For a query with 5 entities, that's 5 sequential calls (~1 second). SafeChain's embedding client supports `embed_documents()` for batching — one call instead of five.

3. **BGE query prefix missing** — The BGE model needs a specific prefix on query-side embeddings. Without it, recall drops ~15%.

4. **No pre-extracted entity support** — The orchestrator already extracts entities during intent classification. If retrieval extracts again, that's a wasted LLM call (~300ms). Need a `pre_extracted` parameter.

5. **`get_top_explore()` needs confidence + action routing** — The orchestrator needs to know: proceed, disambiguate, or clarify. Right now it only returns the top explore name.

**The plan:**
1. I wrote a detailed PR review with file-by-file changes: `docs/pr-reviews/pr-likhita-rajesh-retrieval-cleanup.md` (on `saheb/orchestrator-v1` — I'll push shortly, or I can paste it here)
2. You make those changes on your branch
3. You merge to `main`
4. I rebase the orchestrator branch on top and merge

This way your branch is the foundation in main, and my orchestration layer goes on top cleanly.

**Priority for you:**
- P0 (blocks demo): Coverage bug fix, batch embedding, accept `extractor` param
- P1 (blocks orchestrator): `pre_extracted` support, BGE prefix, confidence/action in `get_top_explore`, singleton engine, EXPLORE_DESCRIPTIONS in constants
- P2 (cleanup): Fix `_get_explore_names` parsing, remove generic dimension suffix

Would love your thoughts on the scoring changes especially — the original additive formula (`raw_score + coverage - penalty`) wasn't discriminating well between explores in our 12-query test set. I moved to a multiplicative formula on my branch that gets 83% accuracy, but I want your input on whether that makes sense for intent classification long-term.

Let me know if anything is unclear — happy to walk through any of it.
