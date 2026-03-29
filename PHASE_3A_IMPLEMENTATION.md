# Phase 3A: Multi-Agent RAG System Implementation

## Overview
Implemented a modular multi-agent pipeline that coexists with the legacy RAG pipeline. The system toggles between modes using the `use_agents` parameter.

## Agents Implemented

### 1. Planner Agent (`agents/planner.py`)
- **Input:** Raw query string
- **Output:** List of sub-query strings
- **Strategy:**
  - Simple queries (<10 words, no conjunctions) → return as-is
  - Complex queries → split on conjunctions (`and`, `or`, `with`, `using`) and commas
  - Deduplicates, filters short fragments, returns at least one query

### 2. Retriever Agent (`agents/retriever_agent.py`)
- **Input:** `query` (str or List[str]), `top_k` (default=3), `retrieval_top_k` (default=50)
- **Output:** List of top-k chunk dictionaries with final scores
- **Strategy:**
  - For each sub-query: analyze → retrieve → rank
  - Merge all results (deduplicate by chunk_id, keep highest score)
  - Rerank merged candidates using the original (first) query
  - Return top-k final chunks

### 3. Reasoner Agent (`agents/reasoner.py`)
- **Input:** Original query string, list of top-k chunks
- **Output:** Final answer string (deterministic synthesis)
- **Strategy:**
  - Extract query keywords/entities
  - Score sentences from chunks by keyword/entity overlap + chunk score boost
  - Select top non-zero sentences (max 5), preserve chunk order
  - Concatenate into coherent paragraph

## Pipeline Integration (`api/engine/pipeline.py`)

### Changes
- Added `use_agents: bool = False` parameter to `run_pipeline()`
- Changed return type to `Union[List[WorkerOutput], str]`
  - Legacy mode (default): `List[WorkerOutput]`
  - Multi-agent mode: `str` (final answer)

### Conditional Flow
```python
if use_agents:
    sub_queries = plan_query(raw_query)
    top_chunks = agent_retrieve(sub_queries, top_k=3)
    answer = agent_reason(raw_query, top_chunks)
    return answer
else:
    # Existing legacy pipeline unchanged
    ...
```

## Backward Compatibility
- **Default unchanged:** `run_pipeline(query)` behaves exactly as before
- **Evaluation compatibility:** `evaluation/runner.py` calls without `use_agents`, expects `List[WorkerOutput]` → passes all tests
- **No breaking changes** to existing retrieval/ranking logic
- **Deterministic** operations throughout

## Validation Results

### TestSprite (Legacy Mode)
```
[TEST] 1. Basic RAG query → PASS
[TEST] 2. Sparse retrieval query → PASS
[TEST] 3. Embedding model query → PASS
SUMMARY: 3/3 passed, 0/3 failed
```

### Multi-Agent Mode (Manual Test)
```
Query: "How does HelioX perform vector search using Qdrant?"
Planner output: ['How does HelioX perform vector search']
Answer: "HelioX performs vector search using Qdrant for production deployments HelioX supports both dense and sparse retrieval methods Vector similarity search uses cosine distance for embeddings."
```

## Usage

### Legacy Mode (Default)
```python
from api.engine.pipeline import run_pipeline
worker_outputs = run_pipeline("your query")  # List[WorkerOutput]
```

### Multi-Agent Mode
```python
from api.engine.pipeline import run_pipeline
answer = run_pipeline("your query", use_agents=True)  # str
```

## Files Modified/Created

### Created
- `agents/__init__.py`
- `agents/planner.py`
- `agents/retriever_agent.py`
- `agents/reasoner.py`

### Modified
- `api/engine/pipeline.py` (added multi-agent support)

## Design Principles Followed
- Minimal changes to existing system
- Deterministic, testable agents
- Clear separation of concerns
- No degradation of baseline performance
- Easy to extend for Phase 3B (Critic Agent)
