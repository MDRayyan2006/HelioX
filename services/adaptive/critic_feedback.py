"""
Critic Feedback: Extract actionable signals from CriticOutput for memory updates.

Converts the critic's validation results into structured signals that
guide concept discovery, entity scoring, and co-occurrence tracking.

Signals:
  - hallucination_penalty: extra negative delta for entities involved in ungrounded claims
  - coverage_boost: signal to accelerate concept discovery for missing terms
  - missing_terms: specific keywords the answer failed to cover
  - penalize_concepts: flag to apply extra penalty to active concepts
  - boost_discovery: flag to inject synthetic co-occurrence pairs
"""

from dataclasses import dataclass, field
from typing import List, Optional
import re

from core.logger import get_logger

logger = get_logger("CRITIC_FEEDBACK")

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
HALLUCINATION_THRESHOLD = 0.3     # hallucination_risk above this triggers penalty
HALLUCINATION_PENALTY_SCALE = 0.1 # max penalty magnitude: -0.1 × hallucination_risk
COVERAGE_BOOST_THRESHOLD = 0.5    # coverage below this triggers discovery boost
COVERAGE_BOOST_SCALE = 0.10       # boost magnitude for co-occurrence weights
CONCEPT_FAIL_PENALTY = 0.05       # extra penalty to concepts on FAIL verdict


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class CriticSignals:
    """Actionable signals extracted from critic feedback."""
    hallucination_penalty: float = 0.0      # 0.0 to -0.15 (extra neg delta)
    coverage_boost: float = 0.0             # 0.0 to +0.10 (discovery weight)
    missing_terms: List[str] = field(default_factory=list)
    penalize_concepts: bool = False         # true if hallucination high
    boost_discovery: bool = False           # true if coverage low
    concept_fail_penalty: float = 0.0       # extra penalty for FAIL verdict


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def extract_signals(
    confidence: float,
    verdict: str,
    hallucination_risk: float = 0.0,
    coverage_score: float = 1.0,
    issues: Optional[List[str]] = None,
) -> CriticSignals:
    """
    Extract actionable learning signals from critic feedback.

    Args:
        confidence: Critic confidence score (0-1).
        verdict: Critic verdict ("PASS", "PARTIAL", "FAIL").
        hallucination_risk: Fraction of ungrounded claims (0-1).
        coverage_score: Fraction of query keywords covered (0-1).
        issues: List of critic issue strings.

    Returns:
        CriticSignals with penalty/boost values and flags.
    """
    signals = CriticSignals()

    # --- Rule 1: Hallucination penalty ---
    if hallucination_risk > HALLUCINATION_THRESHOLD:
        # Penalty scales with hallucination risk
        signals.hallucination_penalty = round(
            -HALLUCINATION_PENALTY_SCALE * hallucination_risk, 4
        )
        signals.penalize_concepts = True
        logger.info(
            f"Hallucination penalty: {signals.hallucination_penalty:.4f} "
            f"(risk={hallucination_risk:.2f})"
        )

    # --- Rule 2: Missing coverage boost ---
    if coverage_score < COVERAGE_BOOST_THRESHOLD:
        signals.boost_discovery = True
        # Boost scales inversely with coverage (lower coverage = higher boost)
        signals.coverage_boost = round(
            COVERAGE_BOOST_SCALE * (1.0 - coverage_score), 4
        )

        # Extract missing terms from critic issues
        if issues:
            for issue in issues:
                match = re.search(r"Missing key terms?:\s*(.+)", issue)
                if match:
                    terms = [t.strip().lower() for t in match.group(1).split(",")]
                    signals.missing_terms.extend(terms)

        logger.info(
            f"Coverage boost: {signals.coverage_boost:.4f} "
            f"(coverage={coverage_score:.2f}, "
            f"missing={signals.missing_terms})"
        )

    # --- Rule 3: Concept fail penalty ---
    if verdict == "FAIL":
        signals.concept_fail_penalty = CONCEPT_FAIL_PENALTY
        signals.penalize_concepts = True
        logger.info(
            f"Concept fail penalty: -{signals.concept_fail_penalty} "
            f"(verdict=FAIL)"
        )

    return signals
