"""
Confidence Router: Returns routing hints based on confidence level.

Controls downstream behavior:
  - use_fallback: whether retriever should use fallback paths
  - broaden: whether rewriter should apply broadening strategy
  - skip_rerank: (reserved) whether to skip cross-encoder reranking

Deterministic, no LLM.
"""

from typing import Dict
from core.logger import get_logger

logger = get_logger("CONFIDENCE_ROUTER")

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
HIGH_CONFIDENCE = 0.8
LOW_CONFIDENCE = 0.5


def route_by_confidence(
    confidence: float,
    attempt: int,
    *,
    memory_quality: float = 0.0,
) -> Dict[str, bool]:
    """
    Produce routing hints based on confidence, attempt, and memory quality.

    Args:
        confidence: Previous confidence score (0-1). Use 0.0 for first attempt.
        attempt: Current attempt number (0-indexed).
        memory_quality: Session memory quality signal (-1 to +1).
            Positive = memory has learned good patterns.
            Negative = mostly failure signals.

    Returns:
        Dict with routing hints:
            - use_fallback: bool — enable retriever fallback paths
            - broaden: bool — enable rewriter broadening
            - skip_rerank: bool — skip cross-encoder reranking (reserved)
    """
    if attempt == 0:
        # First attempt: default routing
        hints = {"use_fallback": True, "broaden": False, "skip_rerank": False}
        logger.info(f"Attempt 0: default routing {hints}")
        return hints

    # Memory-influenced overrides
    # Strong negative memory → always broaden regardless of confidence
    if memory_quality < -0.2:
        hints = {"use_fallback": True, "broaden": True, "skip_rerank": False}
        logger.info(
            f"Negative memory ({memory_quality:.2f}): forced broad routing {hints}"
        )
        return hints

    if confidence >= HIGH_CONFIDENCE:
        hints = {"use_fallback": False, "broaden": False, "skip_rerank": False}
        logger.info(
            f"High confidence ({confidence:.2f}): focused routing {hints}"
        )
        return hints

    if confidence < LOW_CONFIDENCE:
        hints = {"use_fallback": True, "broaden": True, "skip_rerank": False}
        logger.info(
            f"Low confidence ({confidence:.2f}): broad routing {hints}"
        )
        return hints

    # Mid confidence — positive memory can reduce fallback
    use_fb = memory_quality <= 0.3
    hints = {"use_fallback": use_fb, "broaden": False, "skip_rerank": False}
    logger.info(
        f"Mid confidence ({confidence:.2f}), memory={memory_quality:.2f}: "
        f"routing {hints}"
    )
    return hints
