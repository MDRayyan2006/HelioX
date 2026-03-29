"""
Sufficiency Checker: Determines if retrieved context is adequate for answering.

Analyzes coverage, diversity, and worker confidence before answer composition.
Triggers fallback retrieval expansion if insufficient.
"""

from typing import List, Dict, Any, Optional
from core.logger import get_logger
from models.schemas.query import StructuredQuery


def check_sufficiency(
    query: str,
    structured_query: StructuredQuery,
    chunks: List[Dict[str, Any]],
    worker_outputs: Optional[List[Any]] = None,
    thresholds: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Evaluate whether the current retrieval and worker outputs are sufficient
    to answer the query without additional retrieval.

    Args:
        query: Original user query string
        structured_query: Parsed StructuredQuery with keywords, entities, query_type
        chunks: Retrieved chunks (list of dicts with 'text' and optional 'payload')
        worker_outputs: Worker outputs (objects with 'confidence' attribute or dict)
        thresholds: Optional custom thresholds (defaults hardcoded)

    Returns:
        Dict with keys:
            sufficient: bool
            scores: dict of individual metrics
            missing: list of missing keywords/entities
            recommendations: list of suggested actions
    """
    logger = get_logger("SUFFICIENCY")
    logger.info(f"Running sufficiency check for query: {query[:60]}...")

    # Default thresholds
    default_thresholds = {
        "keyword_coverage": 0.6,
        "entity_diversity": 0.5,
        "source_diversity": 0.3,
        "confidence_avg": 0.4,
        "min_chunks": 3
    }
    t = thresholds or default_thresholds

    # Extract query terms
    query_keywords = [k.lower() for k in getattr(structured_query, 'keywords', [])]
    query_entities = [e.lower() for e in getattr(structured_query, 'entities', [])]
    query_type = getattr(structured_query, 'query_type', 'FACTUAL')

    # 1. Keyword coverage in retrieved chunks
    chunk_texts = [c.get('text', '') for c in chunks]
    chunk_texts_lower = [t.lower() for t in chunk_texts]

    kw_found = 0
    for kw in query_keywords:
        if any(kw in text_lower for text_lower in chunk_texts_lower):
            kw_found += 1
    keyword_coverage = kw_found / max(len(query_keywords), 1) if query_keywords else 1.0

    # 2. Entity diversity
    ent_found = 0
    for ent in query_entities:
        if any(ent in text_lower for text_lower in chunk_texts_lower):
            ent_found += 1
    entity_diversity = ent_found / max(len(query_entities), 1) if query_entities else 1.0

    # 3. Source diversity (distinct document sources)
    sources = set()
    for c in chunks:
        src = c.get('payload', {}).get('source')
        if src:
            sources.add(src)
    source_diversity = min(1.0, len(sources) / 3)  # 3+ sources = full

    # 4. Worker confidence average (optional)
    if worker_outputs:
        try:
            confidences = [float(w.confidence) for w in worker_outputs]
        except AttributeError:
            # Fallback if worker_outputs are dicts
            confidences = [float(w.get('confidence', 0.0)) for w in worker_outputs]
        conf_avg = sum(confidences) / len(confidences) if confidences else 0.0
    else:
        # No worker outputs yet; confidence not assessable, assume neutral/pass
        conf_avg = 1.0

    # 5. Chunk count adequacy
    chunk_count_ok = len(chunks) >= t["min_chunks"]

    # Compile scores
    scores = {
        "keyword_coverage": round(keyword_coverage, 3),
        "entity_diversity": round(entity_diversity, 3),
        "source_diversity": round(source_diversity, 3),
        "confidence_avg": round(conf_avg, 3),
        "chunk_count": len(chunks),
        "chunk_count_ok": chunk_count_ok
    }

    # Determine sufficiency
    sufficient = (
        keyword_coverage >= t["keyword_coverage"] and
        entity_diversity >= t["entity_diversity"] and
        source_diversity >= t["source_diversity"] and
        conf_avg >= t["confidence_avg"] and
        chunk_count_ok
    )

    # Special adjustments for query types
    if query_type == "LIST":
        # For LIST, require more chunks and lower confidence threshold
        sufficient = sufficient and len(chunks) >= 5
        if len(chunks) < 5:
            scores["list_chunk_requirement"] = False
            scores["list_missing_count"] = 5 - len(chunks)

    # Identify missing terms
    missing = []
    if keyword_coverage < t["keyword_coverage"]:
        missing.extend([k for k in query_keywords
                       if not any(k in txt for txt in chunk_texts_lower)])
    if entity_diversity < t["entity_diversity"]:
        missing.extend([e for e in query_entities
                       if not any(e in txt for txt in chunk_texts_lower)])

    # Generate recommendations
    recommendations = []
    if keyword_coverage < t["keyword_coverage"]:
        recommendations.append("Expand query with synonyms (query expansion)")
    if entity_diversity < t["entity_diversity"]:
        recommendations.append("Increase retrieval depth (top_k)")
    if source_diversity < t["source_diversity"]:
        recommendations.append("Relax constraint filters to include more sources")
    if conf_avg < t["confidence_avg"]:
        recommendations.append("Review chunk context (context expansion) or adjust worker scoring")
    if not chunk_count_ok:
        recommendations.append(f"Retrieve more chunks (need at least {t['min_chunks']})")

    logger.info(f"Sufficiency: {sufficient} | scores: {scores}")
    if not sufficient:
        logger.warning(f"Insufficient context. Missing: {missing}. Recommendations: {recommendations}")

    return {
        "sufficient": sufficient,
        "scores": scores,
        "missing": list(set(missing)),  # dedup
        "recommendations": recommendations,
        "query_type": query_type
    }
