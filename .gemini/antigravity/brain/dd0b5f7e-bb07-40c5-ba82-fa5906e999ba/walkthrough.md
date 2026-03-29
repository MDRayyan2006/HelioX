# Fix: PostgreSQL Chunk Data Population

## Problem

`run_pipeline.py` ingested documents into SQLite but **never wrote chunk profiles to PostgreSQL**. The `chunk_profiles` table remained empty because the pipeline skipped the profiling service entirely.

## Root Cause

The pipeline runner built mock `ScoredChunk` objects directly from ingested chunks for retrieval simulation — it never called `ProfilingService._insert_postgres()` which is responsible for populating the `chunk_profiles` table.

## Changes Made

### [run_pipeline.py](file:///c:/HelioX/run_pipeline.py)

Added **Stage 0.5 — Expert Profiling → PostgreSQL** between ingestion and query analysis:

render_diffs(file:///c:/HelioX/run_pipeline.py)

**What the new stage does:**
1. Builds `ChunkProfileRequest` objects from ingested chunks via `_build_profile_requests()`
2. Runs deterministic sub-services (constraint extraction + authority scoring) — no external API calls needed
3. Constructs `ChunkProfileResult` objects with placeholder embeddings 
4. Creates the `chunk_profiles` table via `ProfilingBase.metadata.create_all` if it doesn't exist
5. Inserts all profiles into PostgreSQL with `status = COMPLETED`

### [.env](file:///c:/HelioX/.env)

Created from `.env.example` so the application picks up `POSTGRES_URL` and other connection settings.

## How to Verify

**Prerequisite**: PostgreSQL must be running at `localhost:5432` with database `heliox` and user `heliox:heliox`.

```bash
python run_pipeline.py
# Enter any query when prompted
```

Then connect to PostgreSQL and check:
```sql
SELECT chunk_id, document_id, section_id, authority_score, status 
FROM chunk_profiles LIMIT 10;
```

You should see rows with `status = 'completed'` and valid chunk/document/section IDs.

## Validation

- ✅ Syntax check passed (`py_compile`)
- ⏳ Runtime test requires PostgreSQL running locally
