# Walkthrough: Wiring Frontend to HelioX Backend

## Problem
The React frontend at `http://localhost:5173/` was returning generic, hardcoded mock answers ("Based on the provided corpus...") because it was completely disconnected from the Python backend. Uploading `04OLAP.pdf` and asking "what is OLAP" failed because the PDF was never actually sent to Python for RAG pipeline processing.

## Changes Made

### 1. Created FastAPI Backend ([server.py](file:///c:/HelioX/server.py))
Built a brand new FastAPI server that exposes the `run_pipeline.py` logic natively:
- **`POST /api/upload`**: Accepts `04OLAP.pdf`, saves it temporarily, and calls the `ingest_file` pipeline to chunk and store the document in memory for the active session.
- **`POST /api/query`**: Accepts a JSON payload containing the query ("what is OLAP?"), the mode ("auto/light/heavy"), and the document context references. It then runs the full 9-layer RAG process: Intent Analysis -> Retrieval -> Multi-Worker execution -> Adjudication -> Final LLM Composition.

### 2. Connected React Frontend
- **[DocumentUploader.jsx](file:///c:/HelioX/frontend/src/components/DocumentUploader.jsx)**: Replaced the `setTimeout` mock with an actual `FormData` and `fetch` call to upload the file to `http://localhost:8000/api/upload`.
- **[api.js](file:///c:/HelioX/frontend/src/services/api.js)**: Replaced the hardcoded JSON return block with a `fetch` call to `http://localhost:8000/api/query`, returning the real structured response containing the true answer, citations, and confidence score.

## Verification
- Both `uvicorn server:app` (Backend) and `npm run dev` (Frontend) are now running.
- Performed end-to-end programmatic testing on the backend validating that `04OLAP.pdf` is successfully ingested and the query "what is OLAP" returns a correct definition directly from the source text with a high confidence score. 
