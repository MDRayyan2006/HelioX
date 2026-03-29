# Ingestion Service — Implementation Plan

Build the deterministic Ingestion Pipeline as a FastAPI service. No embeddings — purely structural preprocessing.

## Proposed Changes

### Project Scaffolding

#### [NEW] [pyproject.toml](file:///d:/HelioX/pyproject.toml)
Dependencies: `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `pydantic`, `python-multipart`, `PyPDF2`, `beautifulsoup4`, `tiktoken`, `uuid`, `aiofiles`.

#### [NEW] [.env.example](file:///d:/HelioX/.env.example)
Template for `DATABASE_URL`, `UPLOAD_DIR`, `MAX_FILE_SIZE_MB`.

---

### Database Layer

#### [NEW] [ingestion/db/models.py](file:///d:/HelioX/ingestion/db/models.py)
SQLAlchemy ORM models for the Structured Document Graph:
- `IngestionJob` — tracks upload + processing status (queued → processing → completed → failed)
- `Document` — source file metadata (filename, format, hash, timestamps)
- `Section` — hierarchical sections with `parent_id` self-referential FK, `level`, `title`
- `Chunk` — text chunks with `token_count`, `span_start/end`, `overlap_prev`, `parent_section_id` FK

#### [NEW] [ingestion/db/session.py](file:///d:/HelioX/ingestion/db/session.py)
Async SQLAlchemy engine + session factory. `get_db()` dependency for FastAPI.

#### [NEW] [ingestion/db/init_db.py](file:///d:/HelioX/ingestion/db/init_db.py)
`create_all` utility to bootstrap tables from ORM models.

---

### Data Models (Pydantic)

#### [NEW] [ingestion/schemas.py](file:///d:/HelioX/ingestion/schemas.py)
- Request: `IngestionRequest` (metadata alongside upload)
- Response: `IngestionJobResponse`, `DocumentResponse`, `SectionResponse`, `ChunkResponse`, `DocumentGraphResponse`
- Internal: `ParsedSection`, `ParsedChunk`, `DocumentGraph` (used between service layers)

---

### Parsers & Processing

#### [NEW] [ingestion/parsers/detector.py](file:///d:/HelioX/ingestion/parsers/detector.py)
Detect file format from extension + MIME sniffing. Returns enum: `PDF | TXT | CSV | HTML`.

#### [NEW] [ingestion/parsers/pdf_parser.py](file:///d:/HelioX/ingestion/parsers/pdf_parser.py)
Extract text from PDF using PyPDF2. Identify page breaks as section hints.

#### [NEW] [ingestion/parsers/txt_parser.py](file:///d:/HelioX/ingestion/parsers/txt_parser.py)
Plain text parser. Uses blank-line heuristics for paragraph detection, heading-like patterns for sections.

#### [NEW] [ingestion/parsers/csv_parser.py](file:///d:/HelioX/ingestion/parsers/csv_parser.py)
CSV → structured JSON table representation. Each row group becomes a section.

#### [NEW] [ingestion/parsers/html_parser.py](file:///d:/HelioX/ingestion/parsers/html_parser.py)
BeautifulSoup-based HTML parser. Extracts heading hierarchy (h1–h6), paragraphs, tables, lists.

#### [NEW] [ingestion/parsers/\_\_init\_\_.py](file:///d:/HelioX/ingestion/parsers/__init__.py)
`get_parser(format)` factory function returning the appropriate parser.

---

### Processing Pipeline

#### [NEW] [ingestion/processing/noise_removal.py](file:///d:/HelioX/ingestion/processing/noise_removal.py)
Remove boilerplate: excessive whitespace, repeated headers/footers, page number patterns, watermark patterns.

#### [NEW] [ingestion/processing/structural_parser.py](file:///d:/HelioX/ingestion/processing/structural_parser.py)
Build section hierarchy from raw parsed output. Assigns levels, titles, parent references.

#### [NEW] [ingestion/processing/graph_builder.py](file:///d:/HelioX/ingestion/processing/graph_builder.py)
Constructs the parent–child `DocumentGraph` from flat sections. Assigns UUIDs, links parent→child, computes depth.

#### [NEW] [ingestion/processing/chunker.py](file:///d:/HelioX/ingestion/processing/chunker.py)
Adaptive chunking:
- Target: 800–1200 tokens (measured via `tiktoken`)
- 15% overlap with previous chunk
- Prefer sentence/paragraph boundaries
- Track `span_start`, `span_end` offsets into original section text

---

### Pipeline Orchestrator

#### [NEW] [ingestion/pipeline.py](file:///d:/HelioX/ingestion/pipeline.py)
`IngestionPipeline.run(file_path, format)` orchestrates:
1. Parse (via format-specific parser)
2. Noise removal
3. Structural parsing → sections
4. Graph construction → document graph
5. Adaptive chunking → chunks per section
6. Returns `DocumentGraph` for persistence

---

### API & App

#### [NEW] [ingestion/routes.py](file:///d:/HelioX/ingestion/routes.py)
FastAPI router:
- `POST /v1/ingest` — upload file, create job, run pipeline, persist graph
- `GET /v1/ingest/{job_id}` — get job status + results
- `GET /v1/documents` — list ingested documents
- `GET /v1/documents/{document_id}/graph` — get full document graph (sections + chunks)

#### [NEW] [ingestion/config.py](file:///d:/HelioX/ingestion/config.py)
Pydantic `Settings` with env var loading: DB URL, upload dir, max file size, chunk config.

#### [NEW] [ingestion/main.py](file:///d:/HelioX/ingestion/main.py)
FastAPI app entrypoint. Mounts router, runs `init_db` on startup, configures CORS.

---

## Verification Plan

### Automated Test

#### [NEW] [tests/test_ingestion_smoke.py](file:///d:/HelioX/tests/test_ingestion_smoke.py)
A smoke test using FastAPI `TestClient` (no real DB needed — uses SQLite in-memory):
1. Upload a `.txt` file → verify 200/202 response
2. Check job status → verify `completed`
3. Get document graph → verify sections and chunks are present, chunk token counts are in [680, 1380] range (800–1200 ± overlap)

```
cd d:\HelioX
pip install -e ".[test]"
pytest tests/test_ingestion_smoke.py -v
```

### Manual Verification
Start the dev server and upload a sample file via the interactive Swagger docs:
```
cd d:\HelioX
uvicorn ingestion.main:app --reload
```
Then open `http://127.0.0.1:8000/docs` and:
1. Use `POST /v1/ingest` to upload a sample PDF or TXT file
2. Use `GET /v1/ingest/{job_id}` to check the result
3. Use `GET /v1/documents/{document_id}/graph` to inspect the chunked document graph
