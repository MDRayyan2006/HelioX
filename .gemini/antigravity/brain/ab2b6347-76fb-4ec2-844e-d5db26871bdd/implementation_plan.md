# Expert Profiling Service — Implementation Plan

Build **Layer 4 (Multi-Vector Expert Profiling)** per the architecture blueprint §2.5.
For each chunk from the ingestion pipeline, generate and store multi-vector embeddings, constraint metadata, and authority scores across Qdrant, PostgreSQL, and Redis.

---

## Proposed Changes

### Infrastructure Layer

#### [MODIFY] [config.py](file:///c:/HelioX/ingestion/config.py)

Add settings for Qdrant, PostgreSQL (async), Redis, and embedding model:

```python
# Qdrant
qdrant_url: str = "http://localhost:6333"
qdrant_api_key: str | None = None

# PostgreSQL (profiling metadata)
postgres_url: str = "postgresql+asyncpg://heliox:heliox@localhost:5432/heliox"

# Redis
redis_url: str = "redis://localhost:6379/0"
redis_ttl_seconds: int = 3600

# Embedding
embedding_model: str = "text-embedding-3-small"
embedding_dimensions: int = 1536
openai_api_key: str | None = None

# Profiling
profiling_batch_size: int = 32
hyde_max_tokens: int = 200
```

#### [MODIFY] [.env.example](file:///c:/HelioX/.env.example)

Add all new environment variables with sensible defaults.

#### [MODIFY] [pyproject.toml](file:///c:/HelioX/pyproject.toml)

Add optional dependency group `profiling`:

```toml
profiling = [
    "qdrant-client>=1.12.0",
    "asyncpg>=0.30.0",
    "redis[hiredis]>=5.0.0",
    "openai>=1.50.0",
]
```

---

### New `profiling/` Package

#### [NEW] [__init__.py](file:///c:/HelioX/profiling/__init__.py)

Empty init.

#### [NEW] [clients.py](file:///c:/HelioX/profiling/clients.py)

Async client wrappers providing singleton access:

| Client | Library | Purpose |
|--------|---------|---------|
| `get_qdrant_client()` | `qdrant_client.AsyncQdrantClient` | Vector storage |
| `get_postgres_engine()` | `sqlalchemy.ext.asyncio` | Profiling metadata |
| `get_redis_client()` | `redis.asyncio.Redis` | Hot cache |

---

### Schema & Models

#### [NEW] [models.py](file:///c:/HelioX/profiling/models.py)

SQLAlchemy models for profiling metadata tables (PostgreSQL):

```
chunk_profiles
├─ id (PK, UUID)
├─ chunk_id (FK → chunks.id)
├─ document_id (FK → documents.id)
├─ section_id
├─ embedding_model_id (str)
├─ embedding_model_version (str)
├─ authority_score (float)
├─ temporal_start (datetime, nullable)
├─ temporal_end (datetime, nullable)
├─ geographic_scope (JSON array, nullable)
├─ applicability_scope (str, nullable)
├─ entity_list (JSON array)
├─ profiled_at (datetime)
├─ status (enum: pending, completed, failed)
└─ error_message (text, nullable)

embedding_versions
├─ id (PK, UUID)
├─ model_id (str)
├─ model_version (str)
├─ dimensions (int)
├─ created_at (datetime)
└─ is_active (bool)
```

#### [NEW] [schemas.py](file:///c:/HelioX/profiling/schemas.py)

Pydantic DTOs:
- `ChunkProfileRequest` — input from ingestion pipeline
- `ChunkProfileResult` — output with all computed vectors/metadata
- `ConstraintMetadata` — temporal, geographic, applicability scope
- `ProfilingJobStatus` — background job tracking
- `ProfilingStats` — batch stats response

#### [NEW] [qdrant_setup.py](file:///c:/HelioX/profiling/qdrant_setup.py)

Creates 3 Qdrant collections with HNSW configuration:

| Collection | Vector Dim | Distance | HNSW m | ef_construct |
|-----------|-----------|----------|--------|-------------|
| `semantic_embeddings` | 1536 | Cosine | 16 | 100 |
| `entity_vectors` | 1536 | Cosine | 16 | 100 |
| `hyde_embeddings` | 1536 | Cosine | 16 | 100 |

Each collection stores `chunk_id`, `document_id`, and `section_id` as payload fields for filtering.

---

### Core Profiling Services

#### [NEW] [embedder.py](file:///c:/HelioX/profiling/embedder.py)

`SemanticEmbedder` class:
- `embed_chunks(texts: list[str]) -> list[list[float]]` — batch calls OpenAI embeddings API
- Handles batching by `profiling_batch_size`
- Returns `embedding_model_id` + `embedding_model_version` for versioning

#### [NEW] [entity_extractor.py](file:///c:/HelioX/profiling/entity_extractor.py)

`EntityExtractor` class:
- `extract_entities(text: str) -> list[str]` — lightweight regex + heuristic NER (no external model dependency)
- `build_entity_vector(entities: list[str]) -> list[float]` — embeds joined entity string via the same embedding model
- Returns entity list for PostgreSQL and entity vector for Qdrant

#### [NEW] [hyde_generator.py](file:///c:/HelioX/profiling/hyde_generator.py)

`HyDEGenerator` class:
- `generate_hypothetical_question(chunk_text: str) -> str` — generates a hypothetical question that this chunk would answer using LLM (budget-capped at `hyde_max_tokens`)
- `embed_hypothetical(question: str) -> list[float]` — embeds the question
- Batched processing support

#### [NEW] [metadata_extractor.py](file:///c:/HelioX/profiling/metadata_extractor.py)

`ConstraintExtractor` class:
- `extract_temporal(text: str) -> tuple[datetime | None, datetime | None]` — regex-based date extraction
- `extract_geographic(text: str) -> list[str]` — country/region extraction via keyword matching
- `extract_scope(text: str, section_title: str) -> str` — applicability scope heuristic
- Returns `ConstraintMetadata` DTO

#### [NEW] [authority.py](file:///c:/HelioX/profiling/authority.py)

`AuthorityScorer` class:
- `compute_score(document_metadata, section_level, chunk_position) -> float` — weighted score [0.0–1.0]
- Factors: document source type, section depth, chunk position within section, recency

---

### Orchestration & Background Processing

#### [NEW] [service.py](file:///c:/HelioX/profiling/service.py)

`ProfilingService` class — main orchestrator:

```
profile_document(document_id, chunks) → list[ChunkProfileResult]
│
├── 1. SemanticEmbedder.embed_chunks(texts)  → semantic_embeddings
├── 2. EntityExtractor.extract_all(texts)    → entities + entity_vectors
├── 3. HyDEGenerator.generate_all(texts)     → hyde_embeddings
├── 4. ConstraintExtractor.extract_all(texts) → constraint_metadata
├── 5. AuthorityScorer.score_all(chunks)      → authority_scores
│
├── 6. Upsert to Qdrant (3 collections)
├── 7. Insert to PostgreSQL (chunk_profiles)
└── 8. Warm Redis cache
```

All steps are async. Steps 1–5 run concurrently via `asyncio.gather`.

#### [NEW] [cache.py](file:///c:/HelioX/profiling/cache.py)

`ProfileCache` class:
- `get(chunk_id) -> ChunkProfileResult | None`
- `set(chunk_id, profile, ttl)`
- `invalidate(chunk_id)`
- `warm_batch(profiles: list)` — bulk cache warming after profiling
- JSON serialization of profile results with configurable TTL

#### [NEW] [tasks.py](file:///c:/HelioX/profiling/tasks.py)

Background task runner:
- `BackgroundProfiler` class using `asyncio.Queue`
- `enqueue(document_id, chunks)` — adds profiling job to the queue
- `worker_loop()` — continuously processes queue items
- `start(num_workers=2)` / `stop()` — lifecycle management
- Batch processing with configurable concurrency
- Error handling with retry (max 2 retries per chunk batch)
- Status tracking via PostgreSQL `chunk_profiles.status`

---

## Verification Plan

### Automated Tests

All tests use `pytest` + `pytest-asyncio` with mocked external clients.

#### [NEW] [test_profiling_models.py](file:///c:/HelioX/tests/test_profiling_models.py)

Tests that SQLAlchemy models create tables correctly (same pattern as existing `test_db_init.py`):

```bash
cd c:\HelioX && python -m pytest tests/test_profiling_models.py -v
```

#### [NEW] [test_profiling_service.py](file:///c:/HelioX/tests/test_profiling_service.py)

Tests for the profiling workflow with mocked clients:
- Test `ConstraintExtractor` date parsing
- Test `EntityExtractor` entity extraction
- Test `AuthorityScorer` score computation
- Test `ProfilingService.profile_document()` end-to-end with mocked Qdrant/PostgreSQL/Redis
- Test `ProfileCache` set/get/invalidate
- Test `BackgroundProfiler` queue processing

```bash
cd c:\HelioX && python -m pytest tests/test_profiling_service.py -v
```

#### Run all tests:

```bash
cd c:\HelioX && python -m pytest tests/ -v
```
