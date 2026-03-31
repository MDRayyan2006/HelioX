"""
Cross-Encoder Reranker: Improves precision by re-scoring top candidates
with a more powerful (but slower) cross-encoder model.

Uses sentence-transformers cross-encoder for contextual query-document scoring.
"""

import os
from typing import List, Dict, Any

from sentence_transformers import CrossEncoder
from core.logger import get_logger

# Global singleton for the cross-encoder model
_reranker_instance = None


def get_reranker():
    """
    Get or initialize the cross-encoder reranker singleton.

    Returns:
        CrossEncoder instance
    """
    global _reranker_instance
    if _reranker_instance is None:
        model_name = os.getenv(
            "RERANKER_MODEL",
            "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        logger = get_logger("RERANKER")
        logger.info(f"Loading cross-encoder model: {model_name}")
        _reranker_instance = CrossEncoder(model_name)
        logger.info("Cross-encoder loaded successfully")
    return _reranker_instance


def rerank(
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int = None,
    threshold: float = 0.0
) -> List[Dict[str, Any]]:
    """
    Rerank a list of candidate chunks using cross-encoder scoring.

    Strategy:
        1. Take top N pre-ranked chunks (typically 10)
        2. Compute relevance score for each (query, chunk.text) pair
        3. Combine with original score (if present) or replace
        4. Return top_k sorted by new rerank_score

    Args:
        query: Original user query string
        chunks: List of chunk dicts from ranking stage, each with 'text' and optionally 'final_score'
        top_k: Number of results to return (defaults to len(chunks) if None)
        threshold: Minimum normalized score required to keep a chunk. Defaults to 0.0.

    Returns:
        New list of chunks with additional 'rerank_score' field, sorted descending
    """
    if not chunks:
        return []

    logger = get_logger("RERANKER")
    reranker = get_reranker()

    # Build cross-encoder input pairs (prefer expanded context when available)
    pairs = [
        (query, chunk.get('context_text') or chunk.get('text', ''))
        for chunk in chunks
    ]

    # Predict relevance scores (higher = more relevant)
    logger.info(f"Reranking {len(chunks)} candidates with cross-encoder")
    raw_scores = reranker.predict(pairs)

    # Normalize cross-encoder scores to [0, 1] (they can be unbounded)
    # Typical cross-encoder outputs are in range ~[-10, 10] depending on model
    min_score = min(raw_scores)
    max_score = max(raw_scores)
    if max_score > min_score:
        normalized_scores = [(s - min_score) / (max_score - min_score) for s in raw_scores]
    else:
        normalized_scores = [0.5] * len(raw_scores)

    # Attach rerank scores and combine with original final_score if present
    reranked = []
    for chunk, norm_score in zip(chunks, normalized_scores):
        if norm_score < threshold:
            continue
            
        # Blend with original score if available (weighted average)
        original_score = chunk.get('final_score')
        if original_score is not None:
            # 50% cross-encoder, 50% original ranking (vector+entity+metadata)
            # This preserves some of the original signal while cleaning up noise
            combined_score = 0.5 * norm_score + 0.5 * original_score
        else:
            combined_score = norm_score

        new_chunk = chunk.copy()
        new_chunk['rerank_score'] = round(float(norm_score), 4)
        new_chunk['final_score'] = round(combined_score, 4)
        reranked.append(new_chunk)

    # Sort by final_score descending
    reranked.sort(key=lambda x: x['final_score'], reverse=True)

    # Return top_k (default all)
    if top_k is not None:
        return reranked[:top_k]
    return reranked
