# Hybrid Retrieval Engine — Implementation Plan

Build a 4-stage retrieval cascade per architecture §2.7. Takes a locked SQO and returns a ranked, dynamically-sized chunk set with relevance scores and confidence estimation.

## Proposed Changes

### Retrieval Engine Package

---

#### [NEW] [config.py](file:///c:/HelioX/retrieval_engine/config.py)

Retrieval-specific settings:

| Setting | Default | Purpose |
|---------|---------|---------|
| `initial_k` | 25 | Stage 3 max candidates |
| `final_k_min` / `final_k_max` | 5 / 12 | Dynamic K clamp range |
| `coverage_gain_epsilon` | 0.02 | Stop criterion for K reduction |
| `min_recall_threshold` | 0.60 | Stage 4 activation threshold |
| `max_retrieval_expansions` | 2 | Fallback retry limit |
| `authority_score_threshold` | 0.3 | Stage 1 filter cutoff |
| `scoring_weights` | w1–w6 per blueprint | Tunable per-deployment |
| Qdrant/PostgreSQL connection | from env | Reuse existing env vars |

---

#### [NEW] [schemas.py](file:///c:/HelioX/retrieval_engine/schemas.py)

| Schema | Purpose |
|--------|---------|
| `ChunkCandidate` | Candidate chunk with metadata (from PostgreSQL) |
| `ScoredChunk` | Chunk + all 6 scoring signals + weighted_score |
| `RelevanceScores` | Breakdown of 6 scoring components |
| `RetrievalResult` | Final output: ranked chunks, confidence, coverage, stage stats |
| `RetrievalRequest` | API input: locked SQO |

---

#### [NEW] [metadata_filter.py](file:///c:/HelioX/retrieval_engine/metadata_filter.py) — Stage 1

Filter chunk candidates via PostgreSQL metadata:
- Temporal: `chunk.temporal_start/end` overlaps SQO temporal range
- Geographic: `chunk.geographic_scope` intersects SQO geo constraints
- Regulatory: entity overlap with SQO regulatory constraints
- Authority: `chunk.authority_score ≥ threshold`
- Returns `list[ChunkCandidate]` (chunk IDs + metadata)

> **Stub**: Uses in-memory filtering on a provided chunk list since actual DB queries require PostgreSQL tables.

---

#### [NEW] [entity_matcher.py](file:///c:/HelioX/retrieval_engine/entity_matcher.py) — Stage 2

Entity overlap filtering:
- Intersect SQO entities with each chunk's entity list
- Retain chunks with overlap ≥ 1
- Returns filtered `list[ChunkCandidate]` sorted by overlap count

---

#### [NEW] [vector_search.py](file:///c:/HelioX/retrieval_engine/vector_search.py) — Stage 3

Qdrant vector similarity search:
- Embed the query via Gemini embedding model
- Search within Stage 2 candidate IDs (Qdrant filtered search)
- Initial K = 25, returns cosine similarity scores
- Returns `list[ScoredChunk]` with `cosine_similarity` populated

> **Stub**: Accepts pre-computed embeddings + mock Qdrant results for testability.

---

#### [NEW] [fallback.py](file:///c:/HelioX/retrieval_engine/fallback.py) — Stage 4

Activated only when recall < `min_recall_threshold`:
- Broadens metadata filters (drop geographic, raise temporal window)
- Optionally enables HyDE embedding for query expansion
- Bounded by `max_retrieval_expansions` (2)
- Returns additional `list[ChunkCandidate]` merged with existing

---

#### [NEW] [scorer.py](file:///c:/HelioX/retrieval_engine/scorer.py)

Relevance-aware scoring implementing the blueprint formula:

```
weighted_score =
    (0.10 × recency)
  + (0.15 × source_rank)
  + (0.10 × citation_density)
  + (0.10 × worker_confidence)    [0 on first pass]
  + (0.35 × cosine_similarity)
  + (0.20 × query_coverage_score)
```

Also implements:
- **Query coverage scoring**: measures what fraction of SQO fact_components are addressed by a chunk's entity/keyword overlap
- **Confidence estimation**: overall retrieval confidence based on top-K score distribution and coverage

---

#### [NEW] [dynamic_k.py](file:///c:/HelioX/retrieval_engine/dynamic_k.py)

Adaptive K reduction per blueprint §2.7:
1. Start with ranked candidates (up to K₀=25)
2. For each chunk i: compute `coverage_gain(i) = coverage(1..i) − coverage(1..i−1)`
3. If `coverage_gain(i) < ε (0.02)` → stop, set K = i−1
4. Clamp: `final K ∈ [5, 12]`

---

#### [NEW] [orchestrator.py](file:///c:/HelioX/retrieval_engine/orchestrator.py)

Main retrieval orchestrator coordinating all 4 stages:
1. Stage 1: metadata filter → candidate IDs
2. Stage 2: entity matching → filtered candidates
3. Stage 3: vector search → scored chunks
4. Check recall → Stage 4 fallback if needed
5. Score all chunks (6-signal formula)
6. Dynamic K reduction
7. Return `RetrievalResult` with confidence

---

#### [NEW] [routes.py](file:///c:/HelioX/retrieval_engine/routes.py)

`POST /v1/retrieve` — takes a locked SQO, returns ranked chunk set.

---

#### [MODIFY] [pyproject.toml](file:///c:/HelioX/pyproject.toml)

Add `retrieval_engine*` to packages, add `retrieval` optional deps group (qdrant-client, asyncpg, numpy).

#### [MODIFY] [.env.example](file:///c:/HelioX/.env.example)

Add retrieval engine config (K settings, weights, thresholds).

---

## Verification Plan

### Automated Tests

#### [NEW] [test_retrieval_engine.py](file:///c:/HelioX/tests/test_retrieval_engine.py)

| Test Class | Coverage |
|------------|----------|
| `TestMetadataFilter` | Temporal, geographic, regulatory, authority filtering |
| `TestEntityMatcher` | Overlap ≥ 1, no overlap, partial, sorting |
| `TestRelevanceScorer` | 6-signal weighted scoring, query coverage, edge cases |
| `TestDynamicK` | Convergence, epsilon stop, clamping [5,12] |
| `TestFallbackRetrieval` | Filter broadening, expansion limits |
| `TestRetrievalOrchestrator` | Full cascade integration, fallback trigger |
| `TestConfidenceEstimation` | High/low score distributions |
| `TestRetrievalSchemas` | Serialization, defaults |

```
cd c:\HelioX && python -m pytest tests/test_retrieval_engine.py -v
```
