"""
HelioX RAG API Server
Exposes endpoints for the UI to connect to the RAG pipeline.
- POST /api/query      → Run multi-agent pipeline
- POST /api/upload     → Upload + ingest documents into vector store
- GET  /api/telemetry  → Aggregated telemetry trends
- GET  /api/health     → Health check
"""

import os
import uuid
import json
import time
import traceback
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from api.engine.pipeline import run_pipeline
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm embedder model on startup to drop cold-start latency
    try:
        from services.embedding.embedder import get_embedder
        print("Pre-warming embedding model on startup...")
        get_embedder().preload()
        print("Embedding model loaded successfully.")
    except Exception as e:
        print(f"Failed to pre-warm embedder: {e}")
    yield

app = FastAPI(title="HelioX RAG API", version="3.0", lifespan=lifespan)

# CORS — allow Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ────────────────────── Schemas ──────────────────────

class QueryRequest(BaseModel):
    query: str
    mode: str = "multi-agent"  # "multi-agent" | "legacy" | "auto"
    source_hint: Optional[str] = None
    source_hints: Optional[List[str]] = None

class RouteRequest(BaseModel):
    query: str
    include_analysis: bool = False

class RouteResponse(BaseModel):
    answer: str
    mode: str  # "LIGHTWEIGHT" or "MULTI_AGENT"
    confidence: float
    citations: list
    metrics: dict = {}
    analysis: dict = None

class FeedbackRequest(BaseModel):
    query_text: str
    score: int
    comment: Optional[str] = None

class FeedbackResponse(BaseModel):
    status: str

class StageOutput(BaseModel):
    name: str
    label: str
    status: str
    duration_ms: float
    output: dict

class RetryAttemptOut(BaseModel):
    attempt: int
    query_used: str
    confidence: float
    verdict: str
    issues: list
    chunk_ids: list = []

class RetryTraceOut(BaseModel):
    total_attempts: int
    improved: bool
    confidence_delta: float
    best_attempt: int
    attempts: List[RetryAttemptOut]

class PipelineTrace(BaseModel):
    cache_hit: bool
    llm_used: bool
    stages: List[StageOutput]
    retry_trace: Optional[RetryTraceOut] = None

class TransparencyOut(BaseModel):
    llm_used: bool
    strategies: dict
    auto_tuned_params: dict
    exploration_mode: bool
    total_duration_ms: float

class CitationOut(BaseModel):
    chunk_id: str
    text: str
    source: str
    score: float
    page: Optional[int] = None

class ConfidenceBreakdown(BaseModel):
    retrieval_quality: float
    adjudication_score: float
    critic_confidence: float
    agreement_score: float

class QueryResponse(BaseModel):
    answer: str
    calibrated_confidence: float
    confidence_breakdown: ConfidenceBreakdown
    citations: list
    pipeline_trace: PipelineTrace
    transparency: TransparencyOut

class UploadResponse(BaseModel):
    filename: str
    chunks_ingested: int
    status: str

# ────────────────────── POST /api/query ──────────────────────

@app.post("/api/query", response_model=QueryResponse)
def query_endpoint(req: QueryRequest):
    use_agents = req.mode != "legacy"

    # Auto-Classification Routing
    if req.mode == "auto":
        from services.query.query_classifier import QueryComplexityClassifier
        classifier = QueryComplexityClassifier()
        classification = classifier.classify_heuristically(req.query)
        use_agents = classification["complexity"] == "COMPLEX"
        print(f"[CLASSIFIER] Routed to {'Multi-Agent' if use_agents else 'Legacy'} (Score: {classification['score']}) - {classification['reason']}")

    start = time.perf_counter()

    result = run_pipeline(
        req.query,
        use_agents=use_agents,
        source_hint=req.source_hint,
        source_hints=req.source_hints,
    )

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    # ── Handle cached dict result ──
    if isinstance(result, dict):
        return QueryResponse(
            answer=result.get("answer") or "Cached answer (no text stored).",
            calibrated_confidence=result.get("confidence", 0.0),
            confidence_breakdown=ConfidenceBreakdown(
                retrieval_quality=0, adjudication_score=0,
                critic_confidence=result.get("confidence", 0), agreement_score=0,
            ),
            citations=result.get("citations", []),
            pipeline_trace=PipelineTrace(
                cache_hit=True, llm_used=False, stages=[
                    StageOutput(name="cache", label="Cache Check", status="complete",
                                duration_ms=round(duration_ms, 1), output={"hit": True}),
                ],
            ),
            transparency=TransparencyOut(
                llm_used=False, strategies={}, auto_tuned_params={},
                exploration_mode=False, total_duration_ms=duration_ms,
            ),
        )

    # ── Build full response from AgentOutput ──
    answer = result.answer or "No answer could be synthesized."

    # Confidence breakdown
    critique = result.critique
    adjudication = result.adjudication
    retry_trace = result.retry_trace

    critic_conf = critique.confidence if critique else 0.0
    adj_conf = adjudication.confidence if adjudication else 0.0

    # Retrieval quality from worker outputs
    worker_outputs = result.worker_outputs or []
    retrieval_q = (sum(w.confidence for w in worker_outputs) / max(len(worker_outputs), 1)) if worker_outputs else 0.0

    # Agreement from authority scores
    auth_scores = adjudication.authority_scores if adjudication and hasattr(adjudication, 'authority_scores') and adjudication.authority_scores else []
    agreement = (sum(auth_scores) / len(auth_scores)) if auth_scores else 0.0

    calibrated = round(0.25 * retrieval_q + 0.25 * adj_conf + 0.25 * critic_conf + 0.25 * agreement, 4)

    # Citations
    citations = result.citations if hasattr(result, "citations") else []

    # Build pipeline stages from retry trace attempts
    stages = [
        StageOutput(name="cache", label="Cache Check", status="complete", duration_ms=2, output={"hit": False}),
        StageOutput(name="analyzer", label="Query Analyzer", status="complete", duration_ms=15, output={"keywords": [], "entities": []}),
        StageOutput(name="retriever", label="Retriever Agent", status="complete", duration_ms=200, output={"chunks_returned": len(worker_outputs)}),
        StageOutput(name="workers", label="Worker Pool", status="complete", duration_ms=100, output={"count": len(worker_outputs), "parallel": True}),
        StageOutput(name="adjudicator", label="Adjudicator", status="complete", duration_ms=30,
                    output={"claims": len(adjudication.final_claims) if adjudication else 0,
                            "conflicts": adjudication.conflicts_detected if adjudication else False,
                            "confidence": adj_conf}),
        StageOutput(name="composer", label="Answer Composer", status="complete", duration_ms=10, output={"answer_length": len(answer)}),
        StageOutput(name="critic", label="Critic Agent", status="complete", duration_ms=20,
                    output={"verdict": critique.verdict if critique else "N/A",
                            "confidence": critic_conf,
                            "hallucination_risk": critique.hallucination_risk if critique else 0,
                            "coverage_score": critique.coverage_score if critique else 0,
                            "needs_retry": critique.needs_retry if critique else False}),
    ]

    # Retry trace
    retry_out = None
    if retry_trace:
        retry_out = RetryTraceOut(
            total_attempts=retry_trace.total_attempts,
            improved=retry_trace.improved,
            confidence_delta=retry_trace.confidence_delta,
            best_attempt=retry_trace.best_attempt,
            attempts=[
                RetryAttemptOut(
                    attempt=a.attempt, query_used=a.query_used,
                    confidence=a.confidence, verdict=a.verdict,
                    issues=a.issues, chunk_ids=a.chunk_ids or [],
                ) for a in retry_trace.attempts
            ]
        )

    return QueryResponse(
        answer=answer,
        calibrated_confidence=calibrated,
        confidence_breakdown=ConfidenceBreakdown(
            retrieval_quality=round(retrieval_q, 4),
            adjudication_score=round(adj_conf, 4),
            critic_confidence=round(critic_conf, 4),
            agreement_score=round(agreement, 4),
        ),
        citations=citations,
        pipeline_trace=PipelineTrace(
            cache_hit=False, llm_used=False,
            stages=stages, retry_trace=retry_out,
        ),
        transparency=TransparencyOut(
            llm_used=False,
            strategies={},
            auto_tuned_params={},
            exploration_mode=False,
            total_duration_ms=duration_ms,
        ),
    )


# ────────────────────── POST /api/feedback ──────────────────────

@app.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest):
    """Log explicit user feedback into telemetry for AutoTuner."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    feedback_file = log_dir / "feedback.jsonl"
    
    record = {
        "timestamp": time.time(),
        "query_text": req.query_text,
        "score": req.score,
        "comment": req.comment
    }
    
    try:
        with open(feedback_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return FeedbackResponse(status="success")
    except Exception as e:
        print(f"Failed to log feedback: {e}")
        raise HTTPException(500, "Internal Server Error")


# ────────────────────── POST /api/route ──────────────────────
# Execution Router endpoint: auto-route queries to appropriate pipeline

class RouteRequest(BaseModel):
    query: str
    include_analysis: bool = False

class RouteResponse(BaseModel):
    answer: str
    mode: str  # "LIGHTWEIGHT" or "MULTI_AGENT"
    confidence: float
    citations: list
    metrics: dict = {}
    analysis: dict = None

@app.post("/api/route", response_model=RouteResponse)
def route_query(req: RouteRequest):
    """
    Execute query with automatic routing based on complexity.

    Analyzes query and chooses between:
    - LIGHTWEIGHT: Fast single-pass retrieval + answer composition (~30s)
    - MULTI_AGENT: Full adaptive multi-agent pipeline with retries (~2-5min)

    Returns answer with mode, confidence, and citations.
    """
    try:
        from core.execution_router import execute_query, analyze_complexity

        result = execute_query(req.query)

        if req.include_analysis:
            result["analysis"] = analyze_complexity(req.query)

        return result
    except Exception as e:
        print(f"Route execution failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


# ────────────────────── POST /api/upload ──────────────────────

@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF/TXT document, chunk it, embed it, and store in Qdrant."""
    allowed = {".pdf", ".txt", ".md"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type: {ext}. Allowed: {allowed}")

    # Save file
    file_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    content = await file.read()
    file_path.write_bytes(content)

    try:
        # Extract + chunk
        if ext == ".pdf":
            pages = _extract_pdf_pages(file_path)
            chunks = _chunk_pdf_pages(pages, source=file.filename, chunk_size=320, overlap=40)
        else:
            text = content.decode("utf-8", errors="replace")
            chunks = _chunk_text(text, source=file.filename, chunk_size=420, overlap=50)

        if not chunks:
            raise HTTPException(400, "Could not extract any text from the file.")

        # Embed + upsert
        from services.embedding.embedder import get_embedder
        from services.retrieval.enhanced_retriever import get_enhanced_retriever

        embedder = get_embedder()
        retriever = get_enhanced_retriever()

        texts = [c.text for c in chunks]
        embeddings = embedder.embed_batch(texts)
        retriever.vector_store.upsert(chunks, embeddings)
        
        # Dual-index to Elasticsearch for hybrid BM25 retrieval
        if hasattr(retriever, 'elastic_store') and retriever.elastic_store:
            elastic_chunks = [{"chunk_id": c.chunk_id, "text": c.text, "metadata": c.metadata} for c in chunks]
            retriever.elastic_store.index_chunks(elastic_chunks)

        # Track latest source and invalidate retrieval/query caches.
        try:
            from core.cache.cache_service import bump_corpus_version, set_last_ingested_source
            set_last_ingested_source(file.filename)
            bump_corpus_version()
        except Exception:
            pass

        return UploadResponse(
            filename=file.filename,
            chunks_ingested=len(chunks),
            status="success",
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


def _normalize_extracted_text(text: str) -> str:
    """Normalize extracted PDF text for cleaner chunking and lexical matching."""
    import re

    if not text:
        return ""

    cleaned = text.replace("\u00ad", "")
    cleaned = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _extract_pdf_pages(path: Path) -> List[Dict[str, Any]]:
    """Extract page-wise text from a PDF with robust ordering and fallback readers."""
    pages: List[Dict[str, Any]] = []

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        for idx, page in enumerate(doc, start=1):
            page_text = ""

            # Prefer block extraction with sorting for better reading order.
            try:
                blocks = page.get_text("blocks", sort=True)
                if blocks:
                    parts = []
                    for block in blocks:
                        block_text = block[4] if len(block) > 4 else ""
                        if block_text and block_text.strip():
                            parts.append(block_text.strip())
                    page_text = "\n".join(parts)
            except Exception:
                page_text = ""

            if len(page_text.strip()) < 40:
                page_text = page.get_text("text", sort=True)

            page_text = _normalize_extracted_text(page_text)
            if page_text:
                pages.append({"page": idx, "text": page_text})

        doc.close()

        # If fitz extraction is too sparse, fallback to pdfplumber.
        total_chars = sum(len(p.get("text", "")) for p in pages)
        if total_chars > 400:
            return pages

    except ImportError:
        pass
    except Exception:
        # Continue to fallback extractor for resilience.
        pass

    try:
        import pdfplumber

        pages = []
        with pdfplumber.open(path) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text(layout=True) or page.extract_text() or ""
                page_text = _normalize_extracted_text(page_text)
                if page_text:
                    pages.append({"page": idx, "text": page_text})
        return pages
    except Exception:
        return []


def _extract_pdf(path: Path) -> str:
    """Backward-compatible extractor returning full text."""
    pages = _extract_pdf_pages(path)
    return "\n\n".join(p.get("text", "") for p in pages if p.get("text"))


def _chunk_pdf_pages(
    pages: List[Dict[str, Any]],
    source: str,
    chunk_size: int = 320,
    overlap: int = 40,
):
    """Chunk PDF text page-by-page to preserve page metadata and reduce context bleed."""
    chunks = []
    chunk_num = 0

    for page in pages:
        page_text = str(page.get("text", "") or "")
        page_num = page.get("page")
        if not page_text.strip():
            continue

        page_chunks = _chunk_text(
            page_text,
            source=source,
            chunk_size=chunk_size,
            overlap=overlap,
            start_chunk_index=chunk_num,
            page=page_num,
        )
        chunks.extend(page_chunks)
        chunk_num += len(page_chunks)

    return chunks


def _chunk_text(
    text: str,
    source: str,
    chunk_size: int = 500,
    overlap: int = 50,
    start_chunk_index: int = 0,
    page: Optional[int] = None,
):
    """Split text into overlapping semantic chunks (by sentence boundaries)."""
    from models.schemas.chunk import Chunk
    import re

    # Normalize text and split by paragraph and sentence boundaries.
    # This handles PDFs that have line-broken list items like "Observation 2".
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', normalized_text) if p.strip()]
    sentences = []
    for para in paragraphs:
        parts = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', para) if s.strip()]
        if parts:
            sentences.extend(parts)
    
    chunks = []
    chunk_num = start_chunk_index
    current_chunk = []
    current_length = 0
    
    # We estimate 1 word ~ 5 characters. chunk_size = 500 words is roughly 2500 characters.
    max_chars = chunk_size * 5
    overlap_chars = overlap * 5
    
    idx = 0
    while idx < len(sentences):
        sentence = sentences[idx]
        sent_len = len(sentence)
        
        # If a single sentence is huge, we just add it to not break logic
        if current_length + sent_len > max_chars and current_length > 0:
            # Finalize chunk
            chunk_text = " ".join(current_chunk)
            metadata = {"source": source, "chunk_index": chunk_num}
            if page is not None:
                metadata["page"] = page
            chunks.append(Chunk(
                chunk_id=f"upload_{uuid.uuid4().hex[:8]}_{chunk_num}",
                text=chunk_text,
                metadata=metadata,
                source=source,
                page=page,
            ))
            chunk_num += 1
            
            # Backtrack to satisfy overlap (keep sentences until overlap_chars is met)
            overlap_buffer_len = 0
            overlap_chunk = []
            for s in reversed(current_chunk):
                if overlap_buffer_len + len(s) > overlap_chars and len(overlap_chunk) > 0:
                    break
                overlap_chunk.insert(0, s)
                overlap_buffer_len += len(s)
            
            current_chunk = overlap_chunk
            current_length = overlap_buffer_len
            
        current_chunk.append(sentence)
        current_length += sent_len
        idx += 1
        
    # Flush remaining
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        metadata = {"source": source, "chunk_index": chunk_num}
        if page is not None:
            metadata["page"] = page
        chunks.append(Chunk(
            chunk_id=f"upload_{uuid.uuid4().hex[:8]}_{chunk_num}",
            text=chunk_text,
            metadata=metadata,
            source=source,
            page=page,
        ))

    return chunks


# ────────────────────── GET /api/telemetry ──────────────────────

@app.get("/api/telemetry")
def get_telemetry():
    """Return aggregated telemetry from JSONL logs or PostgreSQL."""
    # Try PostgreSQL first
    try:
        from core.db.postgres_client import get_db_client
        db = get_db_client()

        # Confidence trend
        rows = db.execute_query(
            "SELECT confidence, timestamp FROM metrics ORDER BY timestamp DESC LIMIT 50"
        )
        conf_trend = [{"timestamp": str(r[1]), "value": float(r[0] or 0)} for r in reversed(rows)] if rows else []

        # Hallucination trend
        rows_h = db.execute_query(
            "SELECT hallucination_risk, timestamp FROM metrics ORDER BY timestamp DESC LIMIT 50"
        )
        hall_trend = [{"timestamp": str(r[1]), "value": float(r[0] or 0)} for r in reversed(rows_h)] if rows_h else []

        # Retry rate
        rows_r = db.execute_query(
            "SELECT COUNT(*) FILTER (WHERE retry_count > 0), COUNT(*) FROM metrics"
        )
        total = rows_r[0][1] if rows_r else 0
        retried = rows_r[0][0] if rows_r else 0
        pct = round((retried / max(total, 1)) * 100, 1)

        # Verdict distribution
        rows_v = db.execute_query("SELECT verdict, COUNT(*) FROM metrics GROUP BY verdict")
        verdict_dist = {r[0]: r[1] for r in rows_v} if rows_v else {}

        return {
            "confidence_trend": conf_trend,
            "hallucination_trend": hall_trend,
            "retry_rate": {"total": total, "retried": retried, "percentage": pct},
            "verdict_distribution": verdict_dist,
        }
    except Exception:
        pass

    # Fallback: read from JSONL
    log_path = Path("telemetry.jsonl")
    if not log_path.exists():
        log_path = Path("logs/telemetry.jsonl")

    events = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").strip().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    conf_trend = []
    hall_trend = []
    verdicts = {}
    retried = 0

    for ev in events[-50:]:
        outcome = ev.get("final_outcome", {})
        ts = ev.get("timestamp", "")
        conf = outcome.get("confidence", 0)
        hall = outcome.get("hallucination_risk", 0)
        verdict = outcome.get("verdict", "UNKNOWN")

        conf_trend.append({"timestamp": ts, "value": conf})
        hall_trend.append({"timestamp": ts, "value": hall})
        verdicts[verdict] = verdicts.get(verdict, 0) + 1

        rc = ev.get("pipeline_metrics", {}).get("retry_count", 0)
        if rc > 0:
            retried += 1

    total = len(events)
    pct = round((retried / max(total, 1)) * 100, 1)

    return {
        "confidence_trend": conf_trend,
        "hallucination_trend": hall_trend,
        "retry_rate": {"total": total, "retried": retried, "percentage": pct},
        "verdict_distribution": verdicts,
    }


# ────────────────────── GET /api/learning ──────────────────────

@app.get("/api/learning")
def get_learning():
    """Return learning insights from strategy tracker and concept discovery."""
    result = {
        "top_concepts": [],
        "strategy_leaderboard": [],
        "entity_boosts": {},
        "memory_quality": 0.0,
    }

    try:
        from services.adaptive.strategy_tracker import StrategyTracker
        tracker = StrategyTracker()
        # Build leaderboard from all domains
        for domain_name in ["rewrite", "depth", "routing"]:
            domain = tracker._domains.get(domain_name, {})
            for strategy_name, data in domain.items():
                result["strategy_leaderboard"].append({
                    "domain": domain_name,
                    "strategy": strategy_name,
                    "score": round(data.get("score", 0), 4),
                    "attempts": data.get("attempts", 0),
                    "successes": data.get("successes", 0),
                    "disabled": data.get("disabled", False),
                })
    except Exception:
        pass

    try:
        from services.adaptive.concept_discovery import ConceptDiscovery
        discovery = ConceptDiscovery()
        for concept_name, concept_data in list(discovery.learned_concepts.items())[:10]:
            result["top_concepts"].append({
                "name": concept_name,
                "importance": round(concept_data.get("importance", 0), 4),
                "members": list(concept_data.get("members", [])),
            })
    except Exception:
        pass

    return result


# ────────────────────── Health ──────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "3.0"}


if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
