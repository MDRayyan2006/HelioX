# HelioX 3.0 — Multi-Agent Reasoning Layer

## Goal

Design a minimal, production-ready multi-agent reasoning layer that sits on top of the existing retrieval pipeline. The system decomposes complex queries, leverages existing retrieval, synthesizes grounded answers, and validates output quality — all in a deterministic, linear flow.

---

## Architecture Diagram

```text
                         ┌───────────────────────┐
                         │     User Query        │
                         └───────────┬───────────┘
                                     │
                         ┌───────────▼───────────┐
                         │    PLANNER AGENT       │
                         │  • Classify complexity │
                         │  • Decompose → sub-Qs  │
                         │  • Generate plan        │
                         └───────────┬───────────┘
                                     │ PlanOutput
                         ┌───────────▼───────────┐
                         │   RETRIEVER AGENT      │
                    ┌────│  • For each sub-query:  │
                    │    │    analyze → retrieve    │
                    │    │    → rank → rerank      │
                    │    │  • Merge all chunks     │ ← Uses existing pipeline
                    │    │  • Deduplicate          │   (retriever, ranker, reranker)
                    │    └───────────┬───────────┘
                    │                │ RetrievalOutput
                    │    ┌───────────▼───────────┐
  Existing pipeline │    │    REASONER AGENT      │
  UNTOUCHED         │    │  • Per-chunk reasoning  │
                    │    │  • Synthesize answer    │
                    │    │  • Cite sources         │
                    │    │  • Flag low-confidence  │
                    │    └───────────┬───────────┘
                    │                │ ReasonerOutput
                    │    ┌───────────▼───────────┐
                    └────│     CRITIC AGENT       │
                         │  • Validate claims      │
                         │  • Check coverage       │
                         │  • Detect hallucination │
                         │  • Score confidence     │
                         └───────────┬───────────┘
                                     │ CriticOutput
                         ┌───────────▼───────────┐
                         │   ORCHESTRATOR        │
                         │  • Assemble final     │
                         │    response           │
                         │  • Format + return    │
                         └───────────────────────┘
```

**Data Flow Summary:**

```text
Query → PlanOutput → RetrievalOutput → ReasonerOutput → CriticOutput → FinalAnswer
```

No loops. No retries. Deterministic left-to-right pipeline.

---

## Agent Responsibilities

### 1. Planner Agent

| Aspect | Detail |
|--------|--------|
| **Input** | Raw user query (string) |
| **Output** | `PlanOutput` — sub-queries + query type + strategy |
| **Location** | `agents/planner.py` |
| **Uses LLM?** | No (deterministic heuristics) |

**Logic:**
1. Classify query complexity: `SIMPLE` (single-hop) vs `COMPOUND` (multi-hop)
2. If `SIMPLE` → pass through as single sub-query
3. If `COMPOUND` → split on conjunctions (`and`, `or`, `,`), question words, and semicolons
4. Tag each sub-query with intent: `FACTUAL`, `COMPARISON`, `PROCEDURAL`

```python
class PlanOutput(BaseModel):
    original_query: str
    query_type: str          # "SIMPLE" | "COMPOUND"
    sub_queries: List[str]   # 1 for simple, N for compound
    strategy: str            # "DIRECT" | "MERGE_ANSWERS"
```

**Why no LLM**: For Phase 1, rule-based decomposition is predictable, fast, and debuggable. LLM decomposition can be added later as a hot-swap.

---

### 2. Retriever Agent

| Aspect | Detail |
|--------|--------|
| **Input** | `PlanOutput` (list of sub-queries) |
| **Output** | `RetrievalOutput` — deduplicated ranked chunks per sub-query |
| **Location** | `agents/retriever_agent.py` |
| **Uses LLM?** | No |

**Logic:**
1. For each sub-query in `PlanOutput.sub_queries`:
   - Call existing `analyze_query()` → `StructuredQuery`
   - Call existing `retriever.retrieve()` → entity + vector hits
   - Call existing `merge_rank()` → ranked results
   - Call existing `rerank()` → top K reranked
2. Merge results across sub-queries
3. Deduplicate by `chunk_id` (keep highest score)
4. Return unified chunk pool

```python
class RetrievalOutput(BaseModel):
    sub_query_results: Dict[str, List[Dict]]  # sub_query → ranked chunks
    merged_chunks: List[Dict]                  # deduplicated, sorted
    total_chunks: int
```

> [!IMPORTANT]
> This agent does NOT modify the retrieval pipeline. It wraps and calls it per sub-query.

---

### 3. Reasoner Agent

| Aspect | Detail |
|--------|--------|
| **Input** | `RetrievalOutput` + original query |
| **Output** | `ReasonerOutput` — synthesized answer with citations |
| **Location** | `agents/reasoner.py` |
| **Uses LLM?** | **Yes** (for synthesis) — OR deterministic for Phase 1 |

**Logic (Phase 1 — Deterministic):**
1. For each top chunk, extract the most relevant sentence (substring match to query keywords)
2. Compose answer by concatenating extracted spans with citation markers
3. Calculate coverage: fraction of sub-queries with at least 1 supporting chunk
4. Flag sub-queries with no supporting evidence

**Logic (Phase 2 — LLM):**
1. Build context window from top chunks
2. Prompt LLM: *"Answer ONLY using the provided sources. Cite as [1], [2]. If insufficient, say 'Not enough evidence.'"*
3. Parse citations from response

```python
class ReasonerOutput(BaseModel):
    answer: str
    citations: List[Dict]          # [{chunk_id, text_span, citation_idx}]
    coverage: float                # 0-1: fraction of sub-queries covered
    uncovered_queries: List[str]   # sub-queries with no evidence
    confidence: float              # 0-1: overall reasoning confidence
```

---

### 4. Critic Agent

| Aspect | Detail |
|--------|--------|
| **Input** | `ReasonerOutput` + `RetrievalOutput` |
| **Output** | `CriticOutput` — validation verdict |
| **Location** | `agents/critic.py` |
| **Uses LLM?** | No (deterministic validation) |

**Logic:**
1. **Citation check**: Every claim references a real chunk_id from `RetrievalOutput`
2. **Coverage check**: `coverage >= 0.5` threshold
3. **Hallucination check**: Verify answer text can be traced back to retrieved spans
4. **Confidence check**: Reasoner confidence > threshold
5. Produce verdict: `PASS`, `PARTIAL`, or `FAIL`

```python
class CriticOutput(BaseModel):
    verdict: str                   # "PASS" | "PARTIAL" | "FAIL"
    issues: List[str]              # detected problems
    citation_valid: bool
    coverage_score: float
    hallucination_risk: float      # 0-1
    recommendation: str            # "ACCEPT" | "FLAG_REVIEW" | "REJECT"
```

---

## Orchestrator

| Aspect | Detail |
|--------|--------|
| **Location** | `agents/orchestrator.py` |
| **Role** | Runs agents in sequence, assembles final output |

```python
class AgentPipelineResult(BaseModel):
    query: str
    plan: PlanOutput
    retrieval: RetrievalOutput
    reasoning: ReasonerOutput
    critique: CriticOutput
    final_answer: str
    accepted: bool
```

**Flow:**

```python
def run_agent_pipeline(query: str) -> AgentPipelineResult:
    plan     = PlannerAgent().run(query)
    chunks   = RetrieverAgent().run(plan)
    answer   = ReasonerAgent().run(chunks, query)
    critique = CriticAgent().run(answer, chunks)

    return AgentPipelineResult(
        query=query,
        plan=plan,
        retrieval=chunks,
        reasoning=answer,
        critique=critique,
        final_answer=answer.answer,
        accepted=critique.verdict != "FAIL"
    )
```

---

## Folder Structure

```text
helioLasthope/
├── agents/                          # NEW: Multi-agent layer
│   ├── __init__.py
│   ├── base.py                      # Agent protocol/interface
│   ├── planner.py                   # Query decomposition
│   ├── retriever_agent.py           # Wraps existing retrieval
│   ├── reasoner.py                  # Answer synthesis
│   ├── critic.py                    # Validation & gap detection
│   └── orchestrator.py             # Sequential pipeline runner
├── models/schemas/
│   └── agent_io.py                  # NEW: All agent I/O models
├── api/engine/
│   └── pipeline.py                  # MODIFY: Add agent mode entry point
└── evaluation/
    └── testsprite_runner.py         # MODIFY: Add agent pipeline tests
```

---

## Integration Into Existing Pipeline

The agent layer replaces `simulate_worker()` in [pipeline.py](file:///c:/helioLasthope/api/engine/pipeline.py#L16-L49). The existing retrieval stages remain untouched.

**Before (current):**
```text
analyze → retrieve → rank → rerank → simulate_worker → return
```

**After (with agents):**
```text
# Option A: Full agent mode (replaces pipeline)
run_agent_pipeline(query) → Planner → Retriever → Reasoner → Critic → return

# Option B: Hybrid mode (backward-compatible)
run_pipeline(query, use_agents=False)  # existing path
run_pipeline(query, use_agents=True)   # new agent path
```

Option B is recommended — add a `use_agents` flag so testsprite can test both paths.

---

## Implementation Plan (Phase Order)

| Step | Files | Depends On | Effort |
|------|-------|------------|--------|
| 1 | `models/schemas/agent_io.py` — all Pydantic models | Nothing | 30 min |
| 2 | `agents/base.py` — Agent protocol | Step 1 | 15 min |
| 3 | `agents/planner.py` — query decomposition | Step 1, 2 | 30 min |
| 4 | `agents/retriever_agent.py` — wraps existing pipeline | Step 1, 2 | 30 min |
| 5 | `agents/reasoner.py` — deterministic synthesis | Step 1, 2 | 45 min |
| 6 | `agents/critic.py` — validation checks | Step 1, 2 | 30 min |
| 7 | `agents/orchestrator.py` — sequential runner | Steps 3–6 | 20 min |
| 8 | Update `pipeline.py` — add `use_agents` flag | Step 7 | 15 min |
| 9 | Update `testsprite_runner.py` — agent pipeline tests | Step 8 | 20 min |

> [!TIP]
> Total: ~9 new/modified files, ~3.5 hours estimated. All agents are deterministic in Phase 1 — no LLM dependency.

---

## Verification Plan

### Testsprite

```bash
cd c:\helioLasthope
python -m evaluation.testsprite_runner
```

Add new test cases to `DEFAULT_TEST_CASES` that exercise compound queries:

```python
{
    "name": "Compound query (agent decomposition)",
    "query": "How does HelioX embed documents and what ranking algorithm does it use?",
    "expected": {
        "min_results": 3,
        "keywords": ["embed", "ranking"],
        "entities": ["HelioX"]
    }
}
```

### Validation Criteria

| Check | Expected |
|-------|----------|
| Simple query → Planner produces 1 sub-query | ✅ |
| Compound query → Planner produces 2+ sub-queries | ✅ |
| Retriever returns chunks for each sub-query | ✅ |
| Reasoner answer contains only retrieved text | ✅ |
| Critic passes on well-grounded answers | ✅ |
| Critic flags when coverage < 0.5 | ✅ |
| Full pipeline runs under 5 seconds (without LLM) | ✅ |

---

## Constraints Checklist

- ✅ Modular — each agent is an independent class with typed I/O
- ✅ No overengineering — deterministic heuristics, no loops, no retries
- ✅ Minimal agents — exactly 4 (Planner, Retriever, Reasoner, Critic)
- ✅ Deterministic flow — strictly linear, no branching
- ✅ Existing retrieval UNTOUCHED — Retriever Agent wraps it
- ✅ Backward compatible — `use_agents=False` preserves old path
- ✅ Testable — all agents return Pydantic models, testsprite validates