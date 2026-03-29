# Execution Router

## Overview

The Execution Router is an intelligent query routing system that automatically selects the appropriate processing pipeline based on query complexity. It reduces unnecessary computational overhead for simple queries while ensuring complex queries get the full multi-agent treatment.

## Architecture

```
┌─────────────────┐
│   User Query    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│      Complexity Analyzer                │
│  • Word count, entities, keywords      │
│  • Query type (FACTUAL, PROCEDURAL,    │
│    COMPARISON, CAUSAL, LIST)           │
│  • Constraints (temporal, domain,      │
│    filters)                            │
│  • Heuristic scoring                   │
└─────────────────┬───────────────────────┘
                  │
          ┌───────┴────────┐
          │ Complexity     │
          │ Score          │
          └───────┬────────┘
                  │
    ┌─────────────┴─────────────┐
    │                            │
    ▼                            ▼
┌─────────────┐      ┌─────────────────────────────┐
│  SIMPLE     │      │      COMPLEX                │
│ Score < 4.5 │      │      Score >= 4.5           │
└──────┬──────┘      └────────────┬────────────────┘
       │                         │
       ▼                         ▼
┌──────────────────┐   ┌──────────────────────────┐
│ LIGHTWEIGHT      │   │ MULTI-AGENT              │
│ Pipeline         │   │ Pipeline                 │
├──────────────────┤   ├──────────────────────────┤
│ • Single-pass    │   │ • Adaptive retry loop    │
│ • Retrieval (k=3)│   │ • Memory-informed        │
│ • Workers (1)    │   │ • Query rewriting        │
│ • Adjudication   │   │ • Critic validation      │
│ • Answer compose │   │ • Confidence calibration │
└────────┬─────────┘   └──────────┬───────────────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
          ┌────────────────────┐
          │   Final Answer     │
          └────────────────────┘
```

## Components

### 1. ComplexityAnalyzer

Deterministic scoring engine that evaluates query complexity.

**Features considered:**
- Word count (longer queries tend to be more complex)
- Entity count (multiple entities require synthesis)
- Keyword count (technical vocabulary)
- Query type (PROCEDURAL, COMPARISON, CAUSAL weighted higher)
- Constraints (temporal, domain, filters)
- Multiple questions
- Readability (average word length heuristic)

**Thresholds:**
- `COMPLEX_MIN_SCORE = 4.5`
- Simple queries: `score < 4.5`
- Hard criteria: Must have ≤15 words, ≤2 entities, 0 constraints

**Type Weights:**
- FACTUAL: 1.0 (baseline)
- LIST: 1.0 (baseline)
- PROCEDURAL: 6.0
- COMPARISON: 7.0
- CAUSAL: 7.0

### 2. ExecutionRouter

Main orchestrator that:
1. Receives raw query
2. Calls `analyze_query()` for structured analysis
3. Computes complexity metrics and score
4. Routes to appropriate pipeline
5. Standardizes response format

**Response format:**
```json
{
  "answer": "string",
  "mode": "LIGHTWEIGHT|MULTI_AGENT",
  "confidence": 0.679,
  "citations": [...],
  "metrics": {
    "complexity_score": 2.4,
    "execution_time_ms": 32100,
    "query_analysis": { /* metrics details */ }
  }
}
```

### 3. Pipelines

**LIGHTWEIGHT:**
- Retrieval: top_k=3 (minimal depth)
- Single worker pass (no retries)
- No critic, no adaptive strategies
- ~30s execution time

**MULTI_AGENT:**
- Full adaptive pipeline with up to 3 attempts
- Query rewriting, memory-informed strategies
- Critic validation with retry triggers
- Confidence calibration
- ~2-5 minutes execution time

## API Endpoints

### POST /api/route

Auto-routing endpoint.

**Request:**
```json
{
  "query": "What is HelioX?",
  "include_analysis": false
}
```

**Response:**
```json
{
  "answer": "HelioX is an intelligent adaptive RAG assistant...",
  "mode": "LIGHTWEIGHT",
  "confidence": 0.679,
  "citations": [
    {
      "chunk_id": "chunk_1",
      "text": "...",
      "source": "Document.pdf",
      "page": 1
    }
  ],
  "metrics": {
    "complexity_score": 0.85,
    "execution_time_ms": 32100,
    "query_analysis": {
      "word_count": 3,
      "entity_count": 1,
      "query_type": "FACTUAL",
      ...
    }
  }
}
```

### POST /api/analyze

Analyze complexity without executing.

**Request:**
```json
{ "query": "Compare Qdrant and Elasticsearch" }
```

**Response:**
```json
{
  "complexity_score": 6.4,
  "is_simple": false,
  "mode": "MULTI_AGENT",
  "metrics": { ... }
}
```

## Usage

### Python

```python
from core.execution_router import execute_query, analyze_complexity

# Execute with automatic routing
result = execute_query("What is HelioX?")
print(f"Answer: {result['answer']}")
print(f"Mode: {result['mode']}")

# Just analyze
analysis = analyze_complexity("How does vector search work?")
print(f"Suggested mode: {analysis['mode']}")
print(f"Complexity score: {analysis['complexity_score']}")
```

### cURL

```bash
# Execute with auto-routing
curl -X POST http://localhost:8000/api/route \
  -H "Content-Type: application/json" \
  -d '{"query": "What is HelioX?"}'

# Include analysis
curl -X POST http://localhost:8000/api/route \
  -H "Content-Type: application/json" \
  -d '{"query": "Compare A and B", "include_analysis": true}'

# Just analyze
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "Why is retrieval important?"}'
```

## Configuration

The complexity analyzer can be tuned by adjusting constants in `ComplexityAnalyzer`:

```python
class ComplexityAnalyzer:
    SIMPLE_MAX_WORDS = 15
    SIMPLE_MAX_ENTITIES = 2
    SIMPLE_MAX_CONSTRAINTS = 0
    COMPLEX_MIN_SCORE = 4.5

    TYPE_WEIGHTS = {
        "LIST": 1.0,
        "FACTUAL": 1.0,
        "PROCEDURAL": 6.0,
        "COMPARISON": 7.0,
        "CAUSAL": 7.0,
    }

    # Feature weights
    WEIGHT_ENTITY_COUNT = 1.5
    WEIGHT_CONSTRAINT_COUNT = 1.0
    ...
```

## Testing

Run the test suite:

```bash
python test_execution_router.py
```

This validates:
- Complexity scoring accuracy
- Routing decisions
- Full pipeline execution

## Design Decisions

### Why heuristic-based vs ML?
- Deterministic decisions (reproducible, debuggable)
- No training data required
- Low latency (domain knowledge encoded in rules)
- Easily tunable for precision/recall trade-offs

### Why separate lightweight pipeline?
- Cost efficiency: Multi-agent is 10x slower and more expensive
- User experience: Simple questions don't need 2-5 minute wait
- Resource utilization: Preserves capacity for complex queries

### Why not use critic in lightweight?
The critic is part of the multi-agent retry loop. For simple queries where we do a single pass, the adjudicator's confidence is sufficient. The lightweight mode prioritizes speed over maximal accuracy.

## Future Enhancements

- Learn optimal routing from historical feedback
- Dynamic threshold adjustment based on time of day/load
- Cache complexity scores for repeated queries
- A/B testing between routing strategies
- Integrate router decision into telemetry for continuous improvement
