"""
Adjudicator Agent: Authority-aware conflict resolution for worker outputs.

4-stage deterministic resolution:
  1. Dedup      — merge claims with high n-gram similarity (Jaccard > 0.6)
  2. Authority  — score each claim group by source quality and citation density
  3. Conflict   — detect contradictions via negation patterns
  4. Resolve    — score by improved consensus formula, keep top claims

Scoring formula (per claim group):
  claim_score = 0.4×agreement + 0.3×authority_weighted_conf
              + 0.2×citation_strength - 0.1×conflict_penalty

No LLM, no randomness. Operates purely on worker output analysis.
"""

from typing import List, Dict, Tuple, Set
import re

from core.logger import get_logger
from models.schemas.worker_output import WorkerOutput
from models.schemas.adjudication_output import AdjudicationOutput


# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------
JACCARD_DEDUP_THRESHOLD = 0.6   # similarity above this → duplicate
CLAIM_SCORE_THRESHOLD = 0.3     # minimum score to keep a claim
MAX_FINAL_CLAIMS = 25           # cap on output claims
NGRAM_SIZE = 2                  # bigrams for Jaccard similarity

# Authority weight distribution
W_RETRIEVAL_RANK = 0.3
W_SOURCE_TYPE = 0.3
W_CITATION_DENSITY = 0.2
W_METADATA_QUALITY = 0.2

# Source type scores
SOURCE_SCORES = {
    "entity": 1.0,
    "vector": 0.7,
    "unknown": 0.5,
}

# Consensus weight distribution
W_AGREEMENT = 0.4
W_AUTHORITY_CONF = 0.3
W_CITATION_STRENGTH = 0.2
W_CONFLICT_PENALTY = 0.1


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _word_ngrams(text: str, n: int) -> Set[Tuple[str, ...]]:
    """Generate word-level n-grams as a set of tuples."""
    words = re.findall(r'\w+', text.lower())
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _contains_negation(text: str, concept: str) -> bool:
    """Check if text negates a concept (e.g., 'not X', 'no X')."""
    pattern = rf'\b(?:not|no|never|cannot|without|doesn\'t|don\'t|isn\'t|aren\'t)\s+(?:\w+\s+){{0,2}}{re.escape(concept)}\b'
    return bool(re.search(pattern, text.lower()))


def _citation_density(supporting_span: str, claim: str) -> float:
    """Ratio of supporting span words to claim words, clamped [0, 1]."""
    claim_words = len(claim.split())
    span_words = len(supporting_span.split())
    if claim_words == 0:
        return 0.0
    return min(1.0, span_words / claim_words)


# ---------------------------------------------------------------------------
# Authority scoring
# ---------------------------------------------------------------------------

def _compute_authority(worker: WorkerOutput) -> float:
    """
    Compute authority score for a single worker output.

    Formula:
        authority = 0.3×retrieval_rank + 0.3×source_type
                  + 0.2×citation_density + 0.2×metadata_quality
    """
    # Retrieval rank score (already 0-1)
    retrieval_rank = min(1.0, max(0.0, worker.retrieval_score))

    # Source type score
    source_score = SOURCE_SCORES.get(worker.source_type, 0.5)

    # Citation density
    cit_density = _citation_density(worker.supporting_span, worker.claim)

    # Metadata quality: has source + has retrieval score
    has_source = 1.0 if worker.source_type != "unknown" else 0.0
    has_score = 1.0 if worker.retrieval_score > 0.0 else 0.0
    meta_quality = 0.5 * has_source + 0.5 * has_score

    authority = (
        W_RETRIEVAL_RANK * retrieval_rank
        + W_SOURCE_TYPE * source_score
        + W_CITATION_DENSITY * cit_density
        + W_METADATA_QUALITY * meta_quality
    )
    return round(min(1.0, max(0.0, authority)), 4)


# ---------------------------------------------------------------------------
# Stage 1: Deduplication
# ---------------------------------------------------------------------------

def _deduplicate_claims(
    workers: List[WorkerOutput],
) -> Tuple[List[Dict], int, List[str]]:
    """
    Merge duplicate claims by pairwise Jaccard n-gram similarity.

    Returns:
        (deduplicated_groups, duplicate_count, log_entries)
    """
    log = []
    if not workers:
        return [], 0, log

    claim_ngrams = [_word_ngrams(w.claim, NGRAM_SIZE) for w in workers]
    assigned = [False] * len(workers)
    groups: List[Dict] = []
    duplicate_count = 0

    for i in range(len(workers)):
        if assigned[i]:
            continue

        authority_i = _compute_authority(workers[i])
        group = {
            "claim": workers[i].claim,
            "citation": workers[i].supporting_span,
            "confidences": [workers[i].confidence],
            "authorities": [authority_i],
            "citation_densities": [_citation_density(
                workers[i].supporting_span, workers[i].claim
            )],
            "chunk_ids": [workers[i].chunk_id],
            "member_count": 1,
            "best_confidence": workers[i].confidence,
        }
        assigned[i] = True

        for j in range(i + 1, len(workers)):
            if assigned[j]:
                continue
            sim = _jaccard_similarity(claim_ngrams[i], claim_ngrams[j])
            if sim >= JACCARD_DEDUP_THRESHOLD:
                assigned[j] = True
                authority_j = _compute_authority(workers[j])
                group["confidences"].append(workers[j].confidence)
                group["authorities"].append(authority_j)
                group["citation_densities"].append(_citation_density(
                    workers[j].supporting_span, workers[j].claim
                ))
                group["chunk_ids"].append(workers[j].chunk_id)
                group["member_count"] += 1
                duplicate_count += 1
                if workers[j].confidence > group["best_confidence"]:
                    group["claim"] = workers[j].claim
                    group["citation"] = workers[j].supporting_span
                    group["best_confidence"] = workers[j].confidence
                log.append(
                    f"Merged duplicate: '{workers[j].claim[:50]}...' "
                    f"(sim={sim:.2f})"
                )

        groups.append(group)

    if duplicate_count:
        log.append(f"Dedup: {len(workers)} workers → {len(groups)} groups "
                   f"({duplicate_count} duplicates merged)")

    return groups, duplicate_count, log


# ---------------------------------------------------------------------------
# Stage 2: Contradiction detection
# ---------------------------------------------------------------------------

def _detect_contradictions(
    groups: List[Dict],
) -> Tuple[bool, List[str]]:
    """Detect contradictions between claim groups via negation patterns."""
    log = []
    conflicts_found = False

    for i in range(len(groups)):
        claim_i_lower = groups[i]["claim"].lower()
        words_i = set(re.findall(r'\b\w{4,}\b', claim_i_lower))

        for j in range(i + 1, len(groups)):
            claim_j = groups[j]["claim"]
            for word in words_i:
                if _contains_negation(claim_j, word):
                    conflicts_found = True
                    groups[i]["has_conflict"] = True
                    groups[j]["has_conflict"] = True
                    log.append(
                        f"Contradiction: '{groups[i]['claim'][:40]}...' vs "
                        f"'{groups[j]['claim'][:40]}...' (on '{word}')"
                    )
                    break

            if not groups[j].get("has_conflict"):
                words_j = set(re.findall(r'\b\w{4,}\b', groups[j]["claim"].lower()))
                for word in words_j:
                    if _contains_negation(groups[i]["claim"], word):
                        conflicts_found = True
                        groups[i]["has_conflict"] = True
                        groups[j]["has_conflict"] = True
                        log.append(
                            f"Contradiction: '{groups[j]['claim'][:40]}...' vs "
                            f"'{groups[i]['claim'][:40]}...' (on '{word}')"
                        )
                        break

    return conflicts_found, log


# ---------------------------------------------------------------------------
# Stage 3: Consensus scoring and resolution (UPGRADED)
# ---------------------------------------------------------------------------

def _resolve_claims(
    groups: List[Dict],
    total_workers: int,
) -> Tuple[List[Dict], List[str]]:
    """
    Score and resolve claims using authority-weighted consensus.

    Upgraded formula:
        claim_score = 0.4×agreement + 0.3×authority_weighted_conf
                    + 0.2×citation_strength - 0.1×conflict_penalty
    """
    log = []

    if not groups or total_workers == 0:
        return [], log

    for group in groups:
        # Agreement factor
        agreement = group["member_count"] / total_workers

        # Authority-weighted confidence: mean(confidence × authority)
        auth_conf_pairs = zip(group["confidences"], group["authorities"])
        weighted_products = [c * a for c, a in auth_conf_pairs]
        authority_weighted_conf = (
            sum(weighted_products) / len(weighted_products)
        )

        # Citation support strength: mean citation density
        citation_strength = (
            sum(group["citation_densities"]) / len(group["citation_densities"])
        )

        # Conflict penalty
        conflict_penalty = 1.0 if group.get("has_conflict") else 0.0

        # Improved consensus score
        claim_score = (
            W_AGREEMENT * agreement
            + W_AUTHORITY_CONF * authority_weighted_conf
            + W_CITATION_STRENGTH * citation_strength
            - W_CONFLICT_PENALTY * conflict_penalty
        )

        group["claim_score"] = round(max(0.0, claim_score), 4)
        group["agreement_factor"] = round(agreement, 4)
        group["authority_weighted_conf"] = round(authority_weighted_conf, 4)
        group["citation_strength"] = round(citation_strength, 4)
        group["avg_authority"] = round(
            sum(group["authorities"]) / len(group["authorities"]), 4
        )

    # Sort by score descending, then member_count for tie-breaking
    groups.sort(
        key=lambda g: (g["claim_score"], g["member_count"]),
        reverse=True,
    )

    # Resolve contradictions: keep higher-scoring side
    resolved = []
    discarded_concepts: set = set()

    for group in groups:
        if group["claim_score"] < CLAIM_SCORE_THRESHOLD:
            log.append(
                f"Discarded (low score {group['claim_score']:.2f}): "
                f"'{group['claim'][:50]}...'"
            )
            continue

        if group.get("has_conflict"):
            claim_words = set(re.findall(r'\b\w{4,}\b', group["claim"].lower()))
            if claim_words & discarded_concepts:
                log.append(
                    f"Discarded (conflict resolved by consensus): "
                    f"'{group['claim'][:50]}...'"
                )
                continue
            for other in groups:
                if other is group:
                    continue
                if other.get("has_conflict"):
                    other_words = set(
                        re.findall(r'\b\w{4,}\b', other["claim"].lower())
                    )
                    for w in claim_words:
                        if _contains_negation(other["claim"], w):
                            discarded_concepts.add(w)

        resolved.append(group)

        if len(resolved) >= MAX_FINAL_CLAIMS:
            break

    log.append(f"Resolved: {len(resolved)} claims kept from {len(groups)} groups")
    return resolved, log


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def adjudicate(worker_outputs: List[WorkerOutput]) -> AdjudicationOutput:
    """
    Combine multiple worker outputs into a final resolved answer.

    Four-stage deterministic resolution:
        1. Deduplicate claims by n-gram Jaccard similarity
        2. Compute authority scores per worker
        3. Detect contradictions via negation patterns
        4. Score by authority-weighted consensus and resolve

    Args:
        worker_outputs: List of WorkerOutput from worker agents

    Returns:
        AdjudicationOutput with final claims, citations, confidence,
        authority scores, and conflict detection results
    """
    logger = get_logger("ADJUDICATOR")
    logger.info(f"Adjudicating {len(worker_outputs)} worker outputs")

    resolution_log: List[str] = []

    # Edge case: no workers
    if not worker_outputs:
        logger.info("No worker outputs to adjudicate")
        return AdjudicationOutput(
            resolution_log=["No worker outputs provided"],
        )

    # Edge case: single worker
    if len(worker_outputs) == 1:
        w = worker_outputs[0]
        authority = _compute_authority(w)
        logger.info(f"Single worker output, authority={authority}")
        return AdjudicationOutput(
            final_claims=[w.claim],
            citations=[w.supporting_span],
            confidence=w.confidence,
            conflicts_detected=False,
            duplicate_count=0,
            authority_scores=[authority],
            resolution_log=["Single worker: passed through without adjudication"],
        )

    total_workers = len(worker_outputs)

    # --- Stage 1: Deduplication ---
    groups, duplicate_count, dedup_log = _deduplicate_claims(worker_outputs)
    resolution_log.extend(dedup_log)
    logger.info(f"Stage 1 dedup: {total_workers} → {len(groups)} groups "
                f"({duplicate_count} duplicates)")

    # --- Stage 2: Contradiction detection ---
    conflicts_detected, conflict_log = _detect_contradictions(groups)
    resolution_log.extend(conflict_log)
    logger.info(f"Stage 2 conflicts: {conflicts_detected}")

    # --- Stage 3: Consensus scoring and resolution ---
    resolved, resolve_log = _resolve_claims(groups, total_workers)
    resolution_log.extend(resolve_log)
    logger.info(f"Stage 3 resolved: {len(resolved)} final claims")

    # --- Assemble output ---
    final_claims = [g["claim"] for g in resolved]
    citations = [g["citation"] for g in resolved]
    authority_scores = [g["avg_authority"] for g in resolved]

    # Aggregate confidence: mean of claim scores
    if resolved:
        confidence = sum(g["claim_score"] for g in resolved) / len(resolved)
        confidence = round(min(1.0, max(0.0, confidence)), 4)
    else:
        confidence = 0.0

    logger.info(f"Final: {len(final_claims)} claims, "
                f"confidence={confidence}, "
                f"conflicts={conflicts_detected}, "
                f"authorities={authority_scores}")

    return AdjudicationOutput(
        final_claims=final_claims,
        citations=citations,
        confidence=confidence,
        conflicts_detected=conflicts_detected,
        duplicate_count=duplicate_count,
        authority_scores=authority_scores,
        resolution_log=resolution_log,
    )
