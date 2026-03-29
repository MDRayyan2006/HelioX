# Fix PostgreSQL Chunk Data Population

- [x] Investigate why PostgreSQL has no chunk ID data
- [x] Add profiling step to `run_pipeline.py` so chunk profiles get written to PostgreSQL
- [x] Create `.env` from `.env.example`
- [x] Fix `extra` env var validation in all 3 `BaseSettings` classes
- [x] Fix PostgreSQL user permissions (`GRANT ALL ON SCHEMA public`)
- [x] Fix timezone-aware datetime mismatch with `TIMESTAMP WITHOUT TIME ZONE` column
- [x] Verify: 6 rows in `chunk_profiles` with `status=COMPLETED` ✅
