# Re-Architecting HelioX for Distributed Storage

## Objective Overview
The core objective was to modify the HelioX architecture to transition from a single datastore approach to a **Distributed Storage Architecture**. Specifically, we needed to partition document data across four specialized stores:
1. **PostgreSQL**: Store raw chunk text.
2. **Redis**: Store chunk profiles and summaries.
3. **Qdrant**: Store chunk embeddings.
4. **Elasticsearch**: Index chunk text for BM25 term matching.

## Implementation Details

### 1. Database Schema Updates
- **`RawChunk` in PostgreSQL**: We replaced the monolithic `ChunkProfile` model in `profiling/models.py` with a simple `RawChunk` model to house just the raw chunk text and IDs.
- **Removed `EmbeddingVersion`**: Cleaned up legacy models that are no longer necessary in the new architecture.

### 2. Ingestion Pipeline (`run_pipeline.py`)
- We overhauled the **Expert Profiling stage** to simultaneously upsert data to the four targeted systems. 
- Integrated asynchronous clients for Postgres (`sqlalchemy.ext.asyncio`), Redis (`redis.asyncio`), Elasticsearch (`elasticsearch.AsyncElasticsearch`), and Qdrant.
- Mock implementations were successfully updated to allow seamless end-to-end execution of `run_pipeline.py` without needing the actual databases running locally.

### 3. Retrieval Engine (`retrieval/engine.py`)
- Created `retrieval/elastic_search.py` containing a new `search_bm25` module to perform asynchronous full-text searches against the `chunks` index.
- Refactored `HybridRetrievalEngine` to dispatch three concurrent `asyncio.gather` tasks:
  - Vector search from Qdrant.
  - BM25 text match from Elasticsearch.
  - Profile + summary retrieval from Redis.
- Orchestrated a final join operation using SQLAlchemy against the `RawChunk` Postgres table to rehydrate the missing chunk text based on the union of retrieved chunk IDs.
- The blended similarity model now seamlessly fuses `alpha_semantic` signals with a 30% `BM25` weighting, ranking candidate chunks correctly.

## Verification
- **Test Ingestion & Retrieval**: Ran the unified `run_pipeline.py` script locally via console logging. The pipeline effectively parsed, partitioned into the simulated mock stores (Redis Pipeline mocks, Async Qdrant mocks, ES mocks), queried against these mock targets concurrently, successfully scored them, and generated the Multi-Agent Worker responses.
- **Unit Tests**: Updated `tests/test_profiling_models.py` to create and read `RawChunk` instances using `aiosqlite` and `sqlalchemy` to ensure the core database behavior functions as expected.
