# Build Hybrid Retrieval Engine

## Planning
- [x] Review architecture blueprint §2.7 + existing schemas
- [x] Write implementation plan
- [x] Get user approval on plan

## Implementation
- [/] Create `retrieval_engine/` package structure
- [/] Create `retrieval_engine/config.py` — retrieval settings
- [/] Create `retrieval_engine/schemas.py` — retrieval DTOs + scored chunks
- [ ] Create `retrieval_engine/metadata_filter.py` — Stage 1 (PostgreSQL filters)
- [ ] Create `retrieval_engine/entity_matcher.py` — Stage 2 (entity overlap)
- [ ] Create `retrieval_engine/vector_search.py` — Stage 3 (Qdrant similarity)
- [ ] Create `retrieval_engine/fallback.py` — Stage 4 (broad retrieval)
- [ ] Create `retrieval_engine/scorer.py` — relevance scoring + query coverage
- [ ] Create `retrieval_engine/dynamic_k.py` — adaptive K reduction
- [ ] Create `retrieval_engine/orchestrator.py` — retrieval cascade
- [ ] Create `retrieval_engine/routes.py` — API endpoint
- [ ] Update `pyproject.toml` and `.env.example`

## Verification
- [ ] Create `tests/test_retrieval_engine.py`
- [ ] Run full test suite
