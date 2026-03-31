"""
Lightweight RAG Pipeline

Ultra-fast single-pass retrieval and answer composition for simple queries.
No agents, no retries, no adaptive strategies.

Designed for:
- Simple factual questions
- Fast response times (< 30s)
- Minimal computational overhead

Usage:
    from core.lightweight_pipeline import run_lightweight_pipeline
    result = run_lightweight_pipeline("What is HelioX?")
"""

import time
import logging
import re
from typing import Dict, Any, List

from core.logger import get_logger
from services.query.analyzer import analyze_query
from services.retrieval.enhanced_retriever import get_enhanced_retriever
from services.retrieval.ranker import apply_coverage_ranking
from services.retrieval.reranker import rerank
from agents.adjudicator import adjudicate
from agents.answer_composer import compose_answer

logger = get_logger("LIGHTWEIGHT_PIPELINE")


def _is_anchor_query(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:observation|section|table|figure|appendix|clause|item|point)\s*[-:#]?\s*\d+\b",
            text.lower(),
        )
    )


def run_lightweight_pipeline(query: str, top_k: int = 3) -> Dict[str, Any]:
    """
    Execute a fast single-pass RAG pipeline.

    Steps:
    1. Embed query (via enhanced retriever)
    2. Retrieve top-k chunks (hybrid: vector + BM25)
    3. Rank & rerank
    4. Generate worker outputs (single pass, no retries)
    5. Adjudicate claims
    6. Compose final answer

    Args:
        query: User query string
        top_k: Number of top chunks to retrieve (default: 3)

    Returns:
        Dict with:
            - answer: str (composed answer)
            - confidence: float (0-1)
            - citations: List[Dict] (with chunk_id, text, source, page)
            - metrics: Dict (execution_time_ms, chunks_retrieved, etc.)
    """
    start_time = time.perf_counter()
    logger.info(f"Starting lightweight pipeline for query: {query[:80]}...")

    # Step 1: Analyze query (needed for retrieval)
    structured = analyze_query(query)
    logger.info(f"Analyzed: {len(structured.keywords)} keywords, {len(structured.entities)} entities")

    # Step 2: Hybrid retrieval (vector + BM25) with enhanced retriever
    retriever = get_enhanced_retriever()
    merged_hits, vector_hits = retriever.retrieve(structured, top_k=top_k)
    logger.info(f"Retrieved: {len(merged_hits)} merged hits, {len(vector_hits)} vector hits")

    # Step 3: Preserve strict relevance ordering for anchor/reference queries.
    if _is_anchor_query(query):
        ranked = sorted(merged_hits, key=lambda x: x.get("final_score", 0.0), reverse=True)
        logger.info(f"Score ranking (anchor query): {len(ranked)} candidates")
    else:
        ranked = apply_coverage_ranking(merged_hits)
        logger.info(f"Diversity ranking: {len(ranked)} candidates")

    # Step 4: Rerank top candidates (skip if lexical confidence is already very strong)
    top_lexical = ranked[0].get("lexical_score", 0.0) if ranked else 0.0
    top_score = ranked[0].get("final_score", 0.0) if ranked else 0.0
    if ranked and top_lexical >= 0.75 and top_score >= 0.8:
        top_chunks = ranked[:top_k]
        logger.info("Skipped cross-encoder rerank due to high lexical confidence")
    else:
        rerank_top = min(20 if _is_anchor_query(query) else 10, len(ranked))
        reranked = rerank(query, ranked[:rerank_top], top_k=top_k)
        top_chunks = reranked[:top_k]
        logger.info(f"Reranked: {len(top_chunks)} final chunks")

    # Step 5: Worker processing (single pass)
    from agents.worker import process_chunks
    worker_outputs = process_chunks(structured, top_chunks, parallel=False)
    logger.info(f"Generated {len(worker_outputs)} worker outputs")

    # Step 6: Adjudication
    adjudication = adjudicate(worker_outputs)
    logger.info(f"Adjudicated: {len(adjudication.final_claims)} claims, confidence={adjudication.confidence:.3f}")

    # Step 7: Answer composition
    compose_input = structured.dict()
    compose_input["raw_query"] = query
    compose_input["retrieved_context"] = [
        c.get("context_text") or c.get("text", "")
        for c in top_chunks if isinstance(c, dict)
    ]
    composed = compose_answer(adjudication.dict(), compose_input)
    logger.info(f"Composed answer: {len(composed['answer'])} characters")

    # Build citations from chunks
    citations = []
    if top_chunks:
        for chunk in top_chunks:
            citations.append({
                "chunk_id": chunk.get("chunk_id", "unknown"),
                "text": chunk.get("text", ""),
                "source": chunk.get("metadata", {}).get("source", "Unknown"),
                "page": chunk.get("metadata", {}).get("page"),
                "score": chunk.get("final_score", 0.0),
            })

    # Metrics
    execution_time_ms = (time.perf_counter() - start_time) * 1000

    result = {
        "answer": composed["answer"],
        "confidence": composed["confidence"],
        "citations": citations,
        "metrics": {
            "execution_time_ms": round(execution_time_ms, 2),
            "chunks_retrieved": len(top_chunks),
            "worker_outputs": len(worker_outputs),
            "claims_final": len(adjudication.final_claims),
            "query_analysis": {
                "keywords": len(structured.keywords),
                "entities": len(structured.entities),
                "query_type": structured.query_type,
            }
        }
    }

    logger.info(f"Lightweight pipeline completed in {execution_time_ms:.1f}ms")
    return result


# Alternative: even faster version without workers/adjudication (just answer from chunks)
def run_ultra_lightweight_pipeline(query: str, top_k: int = 3) -> Dict[str, Any]:
    """
    Ultra-fast pipeline: embed → retrieve → direct answer synthesis.

    Skips worker generation and adjudication entirely.
    Uses retrieved chunks directly as context for answer composition.

    Best for: Very simple factual queries where text chunks already contain the answer.

    Note: This may produce lower quality answers for complex queries as there's
    no claim extraction or conflict resolution.
    """
    start_time = time.perf_counter()
    logger.info(f"Starting ultra-lightweight pipeline for query: {query[:80]}...")

    # Analyze and retrieve
    structured = analyze_query(query)
    retriever = get_enhanced_retriever()
    merged_hits, _ = retriever.retrieve(structured, top_k=top_k)
    if _is_anchor_query(query):
        ranked = sorted(merged_hits, key=lambda x: x.get("final_score", 0.0), reverse=True)
    else:
        ranked = apply_coverage_ranking(merged_hits)
    top_lexical = ranked[0].get("lexical_score", 0.0) if ranked else 0.0
    top_score = ranked[0].get("final_score", 0.0) if ranked else 0.0
    if ranked and top_lexical >= 0.75 and top_score >= 0.8:
        top_chunks = ranked[:top_k]
        logger.info("Skipped cross-encoder rerank due to high lexical confidence")
    else:
        rerank_top = 20 if _is_anchor_query(query) else 10
        reranked = rerank(query, ranked[:rerank_top], top_k=top_k)
        top_chunks = reranked[:top_k]

    # Direct answer from top chunks (pass them as "citations" to composer)
    # The answer composer expects adjudication format, so we fake it
    citations_text = [chunk.get("text", "") for chunk in top_chunks]

    # Build synthetic adjudication dict for composer
    fake_adjudication = {
        "final_claims": citations_text,  # Use raw chunk text as claims
        "citations": citations_text,
        "confidence": 1.0,  # Placeholder
    }

    compose_input = structured.dict()
    compose_input["raw_query"] = query
    compose_input["retrieved_context"] = [
        c.get("context_text") or c.get("text", "")
        for c in top_chunks if isinstance(c, dict)
    ]
    composed = compose_answer(fake_adjudication, compose_input)

    # Build citations
    citations = []
    for chunk in top_chunks:
        citations.append({
            "chunk_id": chunk.get("chunk_id", "unknown"),
            "text": chunk.get("text", ""),
            "source": chunk.get("metadata", {}).get("source", "Unknown"),
            "page": chunk.get("metadata", {}).get("page"),
            "score": chunk.get("final_score", 0.0),
        })

    execution_time_ms = (time.perf_counter() - start_time) * 1000

    return {
        "answer": composed["answer"],
        "confidence": composed.get("confidence", 0.5),
        "citations": citations,
        "metrics": {
            "execution_time_ms": round(execution_time_ms, 2),
            "chunks_retrieved": len(top_chunks),
            "worker_outputs": 0,
            "claims_final": len(citations_text),
            "pipeline": "ultra-lightweight",
        }
    }


if __name__ == "__main__":
    # Quick demo
    test_query = "What is HelioX?"

    print("="*80)
    print("LIGHTWEIGHT PIPELINE DEMO")
    print("="*80)
    print(f"\nQuery: {test_query}\n")

    result = run_lightweight_pipeline(test_query)

    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']:.3f}")
    print(f"Execution time: {result['metrics']['execution_time_ms']:.1f}ms")
    print(f"Chunks: {result['metrics']['chunks_retrieved']}")
    print(f"Citations: {len(result['citations'])}")
    print("\n" + "="*80)
