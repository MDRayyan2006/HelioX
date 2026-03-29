"""
Critic Agent: Deterministic validation layer for the multi-agent RAG pipeline.

Validates the answer against retrieved chunks and adjudication output by checking:
  1. Grounding      — answer sentences traceable to chunk text (n-gram overlap)
  2. Coverage       — query keywords present in the answer
  3. Contradiction  — answer doesn't assert what chunks negate
  4. Completeness   — answer addresses the query's sub-topics
  5. Claim-Citation — each claim aligns with its citation (bigram overlap)
  6. Overconfidence — high confidence with issues = flagged

No LLM, no randomness. Operates purely on string analysis.
"""

from typing import List, Dict, Any
import re

from core.logger import get_logger
from models.schemas.critic_output import CriticOutput
from services.query.analyzer import analyze_query, STOPWORDS


# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------
NGRAM_SIZE = 3            # minimum word overlap to count as grounded
COVERAGE_PASS = 0.5       # keyword coverage threshold
COVERAGE_RETRY = 0.3      # below this → needs_retry
CONFIDENCE_PASS = 0.7     # verdict PASS threshold
CONFIDENCE_PARTIAL = 0.4  # verdict PARTIAL threshold

# Confidence weight distribution (must sum to 1.0)
W_GROUNDING = 0.30
W_COVERAGE = 0.25
W_COMPLETENESS = 0.15
W_CONTRADICTION = 0.10
W_CLAIM_CITATION = 0.20

# Overconfidence threshold
OVERCONFIDENCE_THRESHOLD = 0.9


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences on . ! ? boundaries."""
    parts = re.split(r'[.!?]+', text)
    return [s.strip() for s in parts if s.strip()]


def _word_ngrams(text: str, n: int) -> set:
    """Generate a set of word-level n-grams from text."""
    words = text.lower().split()
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _extract_keywords(query: str) -> List[str]:
    """Extract meaningful keywords from a query string."""
    structured = analyze_query(query)
    return [kw.lower() for kw in structured.keywords]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_grounding(
    answer_sentences: List[str],
    chunk_texts: List[str]
) -> tuple:
    """
    Verify each answer sentence is traceable to at least one chunk.

    Returns:
        (grounding_score: float, ungrounded: List[str], issues: List[str])
    """
    if not answer_sentences:
        return 1.0, [], []

    # Pre-compute chunk n-grams
    chunk_ngram_sets = [_word_ngrams(ct, NGRAM_SIZE) for ct in chunk_texts]

    grounded_count = 0
    ungrounded = []

    for sent in answer_sentences:
        sent_ngrams = _word_ngrams(sent, NGRAM_SIZE)
        if not sent_ngrams:
            grounded_count += 1  # trivially short sentence
            continue

        # A sentence is grounded if ANY of its n-grams appears in ANY chunk
        is_grounded = False
        for chunk_ngrams in chunk_ngram_sets:
            if sent_ngrams & chunk_ngrams:  # set intersection
                is_grounded = True
                break

        if is_grounded:
            grounded_count += 1
        else:
            ungrounded.append(sent)

    score = grounded_count / len(answer_sentences)
    issues = [f"Ungrounded sentence: \"{s[:80]}...\"" for s in ungrounded]
    return score, ungrounded, issues


def _check_coverage(
    answer: str,
    query_keywords: List[str]
) -> tuple:
    """
    Check what fraction of query keywords appear in the answer.

    Returns:
        (coverage_score: float, missing: List[str], issues: List[str])
    """
    if not query_keywords:
        return 1.0, [], []

    answer_lower = answer.lower()
    found = [kw for kw in query_keywords if kw in answer_lower]
    missing = [kw for kw in query_keywords if kw not in answer_lower]

    score = len(found) / len(query_keywords)
    issues = []
    if missing:
        issues.append(f"Missing key terms: {', '.join(missing)}")
    return score, missing, issues


def _check_contradiction(
    answer: str,
    chunk_texts: List[str]
) -> tuple:
    """
    Detect basic contradictions: answer asserts X, chunks say 'not X' / 'no X'.

    Returns:
        (contradiction_score: float, issues: List[str])
        contradiction_score is 0 if no contradictions, up to 1 if severe.
    """
    issues = []
    answer_lower = answer.lower()
    answer_words = set(answer_lower.split()) - STOPWORDS

    negation_patterns = []
    for ct in chunk_texts:
        ct_lower = ct.lower()
        # Find "not <word>" and "no <word>" patterns in chunks
        for match in re.finditer(r'\b(?:not|no|never|cannot|without)\s+(\w+)', ct_lower):
            negated_word = match.group(1)
            if negated_word not in STOPWORDS and len(negated_word) > 2:
                negation_patterns.append(negated_word)

    # Check if answer positively asserts any negated concept
    contradictions = []
    for neg_word in negation_patterns:
        if neg_word in answer_words:
            # Check that the answer does NOT also negate it
            if not re.search(rf'\b(?:not|no|never|cannot|without)\s+{re.escape(neg_word)}\b', answer_lower):
                contradictions.append(neg_word)

    if contradictions:
        unique = list(set(contradictions))
        issues.append(f"Potential contradiction: answer asserts [{', '.join(unique[:5])}] but chunks negate them")

    # Score: 0 = no contradictions (good), 1 = many contradictions (bad)
    score = min(1.0, len(set(contradictions)) / max(len(answer_words), 1))
    return score, issues


def _check_completeness(
    answer: str,
    query: str
) -> tuple:
    """
    Check if the answer addresses the main topics of the query.

    Uses keyword overlap between answer and different segments of the query.

    Returns:
        (completeness_score: float, issues: List[str])
    """
    # Split query into logical segments (by conjunctions/commas)
    segments = re.split(r'\band\b|\bor\b|,|;', query.lower())
    segments = [s.strip() for s in segments if len(s.strip().split()) >= 2]

    if not segments:
        return 1.0, []

    answer_lower = answer.lower()
    addressed = 0

    for seg in segments:
        seg_words = set(seg.split()) - STOPWORDS
        if not seg_words:
            addressed += 1
            continue
        # A segment is addressed if ≥50% of its non-stop words appear in answer
        overlap = sum(1 for w in seg_words if w in answer_lower)
        if overlap / len(seg_words) >= 0.5:
            addressed += 1

    score = addressed / len(segments)
    issues = []
    if score < 1.0:
        unaddressed = len(segments) - addressed
        issues.append(f"Answer may not fully address {unaddressed}/{len(segments)} query segments")
    return score, issues


# ---------------------------------------------------------------------------
# Check 5: Claim ↔ Citation alignment
# ---------------------------------------------------------------------------

def _check_claim_citation_alignment(
    claims: List[str],
    citations: List[str]
) -> tuple:
    """
    Check that each claim has a citation with meaningful overlap.

    Returns:
        (alignment_score: float, issues: List[str])
    """
    if not claims:
        return 1.0, []

    aligned_count = 0
    issues = []

    for i, claim in enumerate(claims):
        if i >= len(citations) or not citations[i]:
            issues.append(f"Claim {i+1} has no citation")
            continue

        claim_ngrams = _word_ngrams(claim, 2)  # bigrams
        cite_ngrams = _word_ngrams(citations[i], 2)

        if not claim_ngrams or not cite_ngrams:
            aligned_count += 1  # trivially short
            continue

        overlap = len(claim_ngrams & cite_ngrams)
        if overlap > 0:
            aligned_count += 1
        else:
            issues.append(
                f"Claim {i+1} has weak citation support: "
                f"'{claim[:40]}...' ↔ '{citations[i][:40]}...'"
            )

    score = aligned_count / len(claims) if claims else 1.0
    return score, issues


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def critique(
    query: str,
    answer: str,
    chunks: List[Dict[str, Any]],
    *,
    claims: List[str] = None,
    citations: List[str] = None,
    adjudication_confidence: float = None,
) -> CriticOutput:
    """
    Validate the composed answer against retrieved chunks and adjudication.

    Runs six deterministic checks (grounding, coverage, contradiction,
    completeness, claim-citation alignment, overconfidence), computes a
    weighted confidence score, and produces a structured verdict.

    Args:
        query: Original user query
        answer: Synthesized answer from the answer composer
        chunks: Retrieved chunks (each dict must contain 'text')
        claims: Optional list of adjudicated claims
        citations: Optional list of citations aligned with claims
        adjudication_confidence: Optional adjudicator confidence for overconfidence check

    Returns:
        CriticOutput with confidence, issues, verdict, and retry flag
    """
    logger = get_logger("CRITIC")
    logger.info(f"Critiquing answer for query: {query[:60]}...")

    # Edge case: empty answer
    if not answer or answer.strip() == "" or answer == "Insufficient evidence":
        return CriticOutput(
            confidence=0.0,
            issues=["Empty or insufficient answer"],
            needs_retry=True,
            verdict="FAIL",
            citation_valid=False,
            coverage_score=0.0,
            hallucination_risk=1.0,
            claim_citation_score=0.0,
            overconfident=False,
        )

    # Prepare inputs
    answer_sentences = _split_sentences(answer)
    chunk_texts = [c.get('text', '') for c in chunks]
    query_keywords = _extract_keywords(query)

    logger.info(f"Answer has {len(answer_sentences)} sentences, "
                f"{len(chunk_texts)} chunks, {len(query_keywords)} keywords")

    all_issues: List[str] = []

    # --- Check 1: Grounding ---
    grounding_score, ungrounded, grounding_issues = _check_grounding(
        answer_sentences, chunk_texts
    )
    all_issues.extend(grounding_issues)
    logger.info(f"Grounding score: {grounding_score:.2f} "
                f"({len(ungrounded)} ungrounded sentences)")

    # --- Check 2: Coverage ---
    coverage_score, missing_kw, coverage_issues = _check_coverage(
        answer, query_keywords
    )
    all_issues.extend(coverage_issues)
    logger.info(f"Coverage score: {coverage_score:.2f} "
                f"(missing: {missing_kw})")

    # --- Check 3: Contradiction ---
    contradiction_score, contradiction_issues = _check_contradiction(
        answer, chunk_texts
    )
    all_issues.extend(contradiction_issues)
    logger.info(f"Contradiction score: {contradiction_score:.2f}")

    # --- Check 4: Completeness ---
    completeness_score, completeness_issues = _check_completeness(
        answer, query
    )
    all_issues.extend(completeness_issues)
    logger.info(f"Completeness score: {completeness_score:.2f}")

    # --- Check 5: Claim ↔ Citation alignment ---
    claim_citation_score = 1.0  # default if no claims provided
    if claims is not None:
        claim_citation_score, cc_issues = _check_claim_citation_alignment(
            claims, citations or []
        )
        all_issues.extend(cc_issues)
        logger.info(f"Claim-citation alignment: {claim_citation_score:.2f}")

    # --- Aggregate confidence ---
    confidence = (
        W_GROUNDING * grounding_score
        + W_COVERAGE * coverage_score
        + W_COMPLETENESS * completeness_score
        + W_CONTRADICTION * (1.0 - contradiction_score)
        + W_CLAIM_CITATION * claim_citation_score
    )
    confidence = round(min(1.0, max(0.0, confidence)), 4)

    # --- Determine verdict ---
    if confidence >= CONFIDENCE_PASS:
        verdict = "PASS"
    elif confidence >= CONFIDENCE_PARTIAL:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"

    # --- Check 6: Overconfidence detection ---
    overconfident = False
    if adjudication_confidence is not None:
        if adjudication_confidence >= OVERCONFIDENCE_THRESHOLD and len(all_issues) > 0:
            overconfident = True
            all_issues.append(
                f"Overconfident: adjudication confidence "
                f"{adjudication_confidence:.2f} >= {OVERCONFIDENCE_THRESHOLD} "
                f"but {len(all_issues)} issues detected"
            )
            logger.info("Overconfidence detected")

    # --- Retry recommendation ---
    needs_retry = verdict == "FAIL" or coverage_score < COVERAGE_RETRY

    # --- Derived flags ---
    citation_valid = len(ungrounded) == 0
    hallucination_risk = round(1.0 - grounding_score, 4)

    logger.info(f"Verdict: {verdict} | Confidence: {confidence} | "
                f"Retry: {needs_retry} | Overconfident: {overconfident}")

    return CriticOutput(
        confidence=confidence,
        issues=all_issues,
        needs_retry=needs_retry,
        verdict=verdict,
        citation_valid=citation_valid,
        coverage_score=round(coverage_score, 4),
        hallucination_risk=hallucination_risk,
        claim_citation_score=round(claim_citation_score, 4),
        overconfident=overconfident,
    )
