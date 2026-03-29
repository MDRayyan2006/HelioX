# Fix Missing Chunk ID Data in PostgreSQL

## Problem

After running `run_pipeline.py`, PostgreSQL's `chunk_profiles` table is empty — no chunk IDs are stored. The pipeline ingests the PDF into SQLite and simulates retrieval with mock `ScoredChunk` objects built directly from ingested chunks, but **never calls** `ProfilingService._insert_postgres()`.

The bridge module `profiling/integration.py` has `profile_file_async()` that would properly insert chunk profiles, but `run_pipeline.py` bypasses it entirely.

## Proposed Changes

### Ingestion Pipeline Runner

#### [MODIFY] [run_pipeline.py](file:///c:/HelioX/run_pipeline.py)

Add a **Stage 0.5 — Expert Profiling** step between ingestion (Stage 0) and query analysis (Stage 1) that:

1. Builds `ChunkProfileRequest` objects from the ingested `DocumentGraph` using the existing `_build_profile_requests()` from `profiling/integration.py`
2. Runs the profiling pipeline with mocked external services (Qdrant + Redis are already mocked; Gemini embedding also needs mocking)
3. Calls `ProfilingService.profile_document()` which internally calls `_insert_postgres()` to populate `chunk_profiles`
4. Displays profiling stage diagnostics (chunk count, profiling time, etc.)

> [!IMPORTANT]
> Since `run_pipeline.py` already mocks Gemini and Redis, we also need to mock the Qdrant client and the embedding calls that the profiling service makes. The key external dependencies to mock are:
> - `profiling.clients.get_qdrant_client` (Qdrant upserts)
> - `profiling.clients.get_redis_client` (Redis cache warming)
> - `profiling.embedder.SemanticEmbedder.embed_texts` (Gemini embedding API)
> - `profiling.entity_extractor.EntityExtractor.build_entity_vector` (entity embedding)
> - `profiling.hyde_generator.HyDEGenerator.generate_hyde_embeddings` (HyDE embedding)
>
> The constraint extractor and authority scorer are deterministic and don't need mocking.

The `_insert_postgres()` method uses a real PostgreSQL connection via `profiling.clients.get_postgres_engine()`. The user needs PostgreSQL running locally with the `heliox` database and user for this to work.

> [!CAUTION]
> **Prerequisite**: PostgreSQL must be running at `localhost:5432` with database `heliox` and user `heliox:heliox` (matching `POSTGRES_URL` in `.env.example`). If your PostgreSQL has different credentials, update `.env` accordingly.

---

### Environment Configuration

#### [NEW] [.env](file:///c:/HelioX/.env)

Copy `.env.example` to `.env` so the application picks up the correct `POSTGRES_URL`, `QDRANT_URL`, etc.

---

### Database Table Creation

Add a step (at the top of the profiling stage) that creates the `chunk_profiles` table if it doesn't exist, using `ProfilingBase.metadata.create_all()`.

## Verification Plan

### Manual Verification

1. Ensure PostgreSQL is running locally (`localhost:5432`) with a database named `heliox`
2. Run `python run_pipeline.py` and enter a query
3. After the pipeline completes, connect to PostgreSQL and run:
   ```sql
   SELECT chunk_id, document_id, section_id, status FROM chunk_profiles LIMIT 10;
   ```
4. Confirm that rows exist with `status = 'completed'` and valid chunk/document/section IDs

### Existing Tests

Run existing profiling integration tests to ensure nothing breaks:
```
cd c:\HelioX
python -m pytest tests/test_ingest_to_profiling_integration.py -v
```
