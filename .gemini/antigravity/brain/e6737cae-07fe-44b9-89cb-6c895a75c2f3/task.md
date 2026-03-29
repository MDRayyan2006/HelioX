# Tasks

## Setup and Config
- [x] Add `elasticsearch_url` to `ingestion/config.py` and `.env`.
- [x] Add `get_elasticsearch_client()` to `profiling/clients.py`.

## Data Models
- [x] Replace `ChunkProfile` with `RawChunk` in `profiling/models.py`.

## Pipeline Ingestion Updates
- [x] Update `run_pipeline.py` to persist text to `RawChunk` in Postgres.
- [x] Update `run_pipeline.py` to store chunk profiles + summaries in Redis.
- [x] Update `run_pipeline.py` to index chunks to Elasticsearch.
- [x] Update `run_pipeline.py` to upsert embeddings to Qdrant.

## Retrieval Updates
- [x] Create `retrieval/elastic_search.py` for BM25 queries.
- [x] Refactor `retrieval/engine.py` to execute Qdrant, ES, and Redis queries concurrently using `asyncio.gather`, pulling actual chunk texts from Postgres.

## Testing
- [ ] Test the pipeline via `run_pipeline.py`.
