# Slack Message — Likhita + Rajesh

**Channel:** DM or team channel
**Copy-paste ready:**

---

Hey Likhita, Rajesh —

I built the full orchestration pipeline (`saheb/orchestrator-v1`) on top of your retrieval branch — SSE streaming, Looker MCP integration, multi-turn conversations, the works. Your entity extraction + vector search + graph validation structure held up well as the foundation.

While wiring everything end-to-end, I stress-tested the retrieval layer against a 12-query golden set and identified a few things we need to tighten before merging to main. I wrote up a detailed file-by-file review here: `docs/pr-reviews/pr-likhita-rajesh-retrieval-cleanup.md` (on my branch — pull it or I can paste it).

The highlights:
- Coverage scoring has a bug that makes all explores look equally good (quick fix)
- Embedding calls need batching — 5 sequential API calls → 1 (saves ~800ms per query)
- The pipeline needs to accept pre-extracted entities so the orchestrator doesn't double-call the LLM
- `get_top_explore()` needs confidence scores + action routing (proceed / disambiguate / clarify)

**Merge plan:**
1. You make changes on your branch → merge to `main`
2. I rebase orchestrator on top → your work is the foundation in git history

One thing I want your input on, Likhita — the original additive scoring formula wasn't discriminating well between explores (~33% accuracy on the test set). I moved to a multiplicative formula that gets us to 83%. Want to walk through the math together and get your take on how this fits with intent classification long-term. Let's find 30 min this week.

PR review is detailed with code snippets — should be straightforward to work through. Flag me if anything's unclear.
