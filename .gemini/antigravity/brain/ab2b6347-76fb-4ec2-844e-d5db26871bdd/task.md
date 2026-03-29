# Expert Profiling Service — Task Tracker

## Phase 1: Planning
- [x] Explore existing codebase structure
- [x] Review architecture blueprint (Section 2.5 — Multi-Vector Expert Profiling)
- [x] Review existing DB models, schemas, config, pipeline
- [x] Write implementation plan
- [x] Get user approval on plan

## Phase 2: Infrastructure Layer
- [x] Add new dependencies to `pyproject.toml` (qdrant-client, asyncpg, redis, google-genai)
- [x] Extend `Settings` in `ingestion/config.py` with Qdrant, PostgreSQL, Redis, Gemini config
- [x] Update `.env.example` with new environment variables
- [x] Create `profiling/__init__.py`
- [x] Create `profiling/clients.py` — Qdrant, PostgreSQL, Redis client wrappers

## Phase 3: Schema & Models
- [x] Create `profiling/models.py` — SQLAlchemy models for profiling metadata tables
- [x] Create `profiling/schemas.py` — Pydantic DTOs for profiling data
- [x] Create `profiling/qdrant_setup.py` — Qdrant collection creation & index configuration

## Phase 4: Core Profiling Services
- [x] Create `profiling/embedder.py` — primary semantic embedding generation (Gemini)
- [x] Create `profiling/entity_extractor.py` — NER-based entity vector generation
- [x] Create `profiling/hyde_generator.py` — HyDE embedding generation (Gemini)
- [x] Create `profiling/metadata_extractor.py` — constraint metadata extraction (temporal, geographic, scope)
- [x] Create `profiling/authority.py` — authority score computation

## Phase 5: Orchestration & Background Processing
- [x] Create `profiling/service.py` — main profiling workflow orchestrator
- [x] Create `profiling/cache.py` — Redis hot cache layer
- [x] Create `profiling/tasks.py` — background task runner / queue integration

## Phase 6: Verification
- [x] Create `tests/test_profiling_models.py`
- [x] Create `tests/test_profiling_service.py`
- [x] Run tests and validate — **44/44 passed ✓**
- [x] Write walkthrough
