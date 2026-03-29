"""
Adaptive Depth Controller: Dynamic top_k based on confidence signals.

Adjusts retrieval breadth per attempt:
  - Low confidence (<0.5)  → widen search (more chunks)
  - High confidence (>0.8) → narrow search (fewer, focused)
  - Mid confidence         → default depth

Deterministic, no LLM.
"""

from core.logger import get_logger

logger = get_logger("DEPTH_CONTROLLER")

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------
LOW_CONFIDENCE = 0.5     # below this → widen
HIGH_CONFIDENCE = 0.8    # above this → narrow
MAX_TOP_K = 10           # ceiling for widened retrieval
MIN_TOP_K = 2            # floor for narrowed retrieval


def compute_top_k(
    confidence: float,
    attempt: int,
    base_k: int = 3,
    *,
    memory_quality: float = 0.0,
    is_list_query: bool = False,
) -> int:
    """
    Compute adaptive top_k for retrieval based on confidence, attempt,
    and session memory quality.

    Rules:
        - confidence < 0.5: widen by +2 per attempt (cap at MAX_TOP_K)
          (negative memory widens more aggressively: +3 per attempt)
        - confidence > 0.8: narrow to base_k - 1 (floor at MIN_TOP_K)
        - mid confidence + positive memory (> 0.3): narrow to base_k - 1
        - otherwise: use base_k

    Args:
        confidence: Previous attempt's confidence (0-1). Use 0.0 for first attempt.
        attempt: Current attempt number (0-indexed).
        base_k: Default retrieval depth.
        memory_quality: Session memory quality signal (-1 to +1).

    Returns:
        Adapted top_k value.
    """
    # List queries fundamentally require broad context up-front, skipping standard depths
    if is_list_query:
        adapted = max(base_k, 8)
        logger.info(f"List query detected: forcing widened top_k={adapted}")
        return adapted

    if attempt == 0:
        # First attempt: always use base
        logger.info(f"Attempt 0: using base top_k={base_k}")
        return base_k

    if confidence < LOW_CONFIDENCE:
        # Negative memory → widen more aggressively
        step = 3 if memory_quality < -0.2 else 2
        adapted = min(base_k + step * attempt, MAX_TOP_K)
        logger.info(
            f"Low confidence ({confidence:.2f} < {LOW_CONFIDENCE}), "
            f"memory={memory_quality:.2f}: widened top_k={adapted} "
            f"(step={step}, attempt {attempt})"
        )
        return adapted

    if confidence > HIGH_CONFIDENCE:
        adapted = max(base_k - 1, MIN_TOP_K)
        logger.info(
            f"High confidence ({confidence:.2f} > {HIGH_CONFIDENCE}): "
            f"narrowed top_k={adapted}"
        )
        return adapted

    # Mid confidence — positive memory allows narrower retrieval
    if memory_quality > 0.3:
        adapted = max(base_k - 1, MIN_TOP_K)
        logger.info(
            f"Mid confidence ({confidence:.2f}), positive memory "
            f"({memory_quality:.2f}): narrowed top_k={adapted}"
        )
        return adapted

    logger.info(f"Mid confidence ({confidence:.2f}): using base top_k={base_k}")
    return base_k
