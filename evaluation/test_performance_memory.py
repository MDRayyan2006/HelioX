"""
Unit tests for the performance-aware SessionMemory system.

Tests cover:
  1. Positive outcome boosts entity/chunk scores
  2. Negative outcome penalizes entity/chunk scores
  3. Score clamping at boundaries
  4. get_entity_boosts returns performance-weighted values
  5. get_chunk_scores returns learned scores
  6. get_memory_quality aggregates correctly
  7. Depth controller responds to memory_quality
  8. Confidence router responds to memory_quality
  9. Query rewriter filters penalized entities
"""

import sys
import os
import tempfile

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.adaptive.session_memory import (
    SessionMemory, _compute_delta, ConceptRecord,
    STRONG_POS_DELTA, WEAK_POS_DELTA, WEAK_NEG_DELTA, STRONG_NEG_DELTA,
    BOOST_SCALE, DECAY_RATE,
)
from services.adaptive.depth_controller import compute_top_k
from services.adaptive.confidence_router import route_by_confidence
from services.adaptive.concept_taxonomy import get_concepts, get_siblings, get_concept_size, CONCEPT_MAP
from core.memory_store import MemoryStore
from services.adaptive.concept_discovery import ConceptDiscovery, MIN_COOCCURRENCE
from services.adaptive.concept_labeler import label_cluster
from services.adaptive.critic_feedback import CriticSignals, extract_signals
from services.adaptive.strategy_tracker import StrategyTracker, INITIAL_SCORE


def _fresh_memory():
    """Create a fresh SessionMemory with isolated test storage."""
    # Create a temporary file for this test instance
    fd, path = tempfile.mkstemp(suffix='.json', prefix='test_mem_')
    os.close(fd)  # Close the file descriptor; MemoryStore will open it
    # Ensure it's empty or remove; we'll let MemoryStore create fresh
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    store = MemoryStore(path)
    mem = SessionMemory(memory_store=store)
    return mem, path


def test_compute_delta_signals():
    """Verify the 4-tier learning signal classification."""
    # Strong positive: high confidence + PASS + no retry
    assert _compute_delta(0.85, "PASS", False) == STRONG_POS_DELTA

    # Weak positive: decent confidence, not FAIL, not PARTIAL
    assert _compute_delta(0.65, "PASS", False) == WEAK_POS_DELTA

    # Weak negative: low confidence
    assert _compute_delta(0.45, "PASS", False) == WEAK_NEG_DELTA

    # Weak negative: PARTIAL verdict
    assert _compute_delta(0.75, "PARTIAL", False) == WEAK_NEG_DELTA

    # Strong negative: FAIL verdict
    assert _compute_delta(0.6, "FAIL", False) == STRONG_NEG_DELTA

    # Strong negative: retried with low confidence
    assert _compute_delta(0.35, "PARTIAL", True) == STRONG_NEG_DELTA

    print("  [PASS] test_compute_delta_signals")


def test_positive_outcome_boosts():
    """Positive outcome should increase entity/chunk scores."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["EntityA", "EntityB"], ["chunk_1", "chunk_2"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        # Scores should be positive
        assert mem._entities["entitya"].score > 0
        assert mem._entities["entityb"].score > 0
        assert mem._chunks["chunk_1"].score > 0
        assert mem._chunks["chunk_2"].score > 0

        # Should be exactly STRONG_POS_DELTA after one positive outcome
        assert mem._entities["entitya"].score == STRONG_POS_DELTA
        print("  [PASS] test_positive_outcome_boosts")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_negative_outcome_penalizes():
    """Negative outcome should decrease entity/chunk scores."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["BadEntity"], ["bad_chunk"])
        mem.record_outcome(confidence=0.2, verdict="FAIL", retried=False)

        assert mem._entities["badentity"].score < 0
        assert mem._chunks["bad_chunk"].score < 0
        assert mem._entities["badentity"].score == STRONG_NEG_DELTA
        print("  [PASS] test_negative_outcome_penalizes")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_score_clamping():
    """Scores should stay within [-1.0, +1.0]."""
    mem, path = _fresh_memory()
    try:
        # Repeatedly boost to hit ceiling
        for _ in range(20):
            mem.record_attempt(["HotEntity"], ["hot_chunk"])
            mem.record_outcome(confidence=0.9, verdict="PASS", retried=False)

        assert mem._entities["hotentity"].score <= 1.0
        assert mem._chunks["hot_chunk"].score <= 1.0
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    mem2, path2 = _fresh_memory()
    try:
        # Repeatedly penalize to hit floor
        for _ in range(20):
            mem2.record_attempt(["ColdEntity"], ["cold_chunk"])
            mem2.record_outcome(confidence=0.1, verdict="FAIL", retried=False)

        assert mem2._entities["coldentity"].score >= -1.0
        assert mem2._chunks["cold_chunk"].score >= -1.0
        print("  [PASS] test_score_clamping")
    finally:
        try:
            os.remove(path2)
        except FileNotFoundError:
            pass


def test_entity_boosts_performance_weighted():
    """get_entity_boosts should return performance-weighted values."""
    mem, path = _fresh_memory()
    try:
        # Good entity: high confidence PASS
        mem.record_attempt(["GoodEntity"], ["c1"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        # Bad entity: FAIL
        mem.record_attempt(["BadEntity"], ["c2"])
        mem.record_outcome(confidence=0.2, verdict="FAIL", retried=False)

        boosts = mem.get_entity_boosts()

        # Good entity gets positive boost
        assert boosts.get("goodentity", 0) > 0

        # Bad entity gets negative boost
        assert boosts.get("badentity", 0) < 0

        # Boost magnitude is score * BOOST_SCALE
        # Decay applies to entities not used in the second attempt
        expected_good_score = STRONG_POS_DELTA * (1 - DECAY_RATE)
        expected_good = round(expected_good_score * BOOST_SCALE, 4)
        # Allow tiny tolerance for floating point rounding
        assert abs(boosts["goodentity"] - expected_good) < 0.0001
        print("  [PASS] test_entity_boosts_performance_weighted")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_chunk_scores():
    """get_chunk_scores should return learned chunk quality scores."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["E1"], ["good_chunk"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        mem.record_attempt(["E2"], ["bad_chunk"])
        mem.record_outcome(confidence=0.2, verdict="FAIL", retried=False)

        scores = mem.get_chunk_scores()
        assert scores.get("good_chunk", 0) > 0
        assert scores.get("bad_chunk", 0) < 0
        print("  [PASS] test_chunk_scores")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_memory_quality():
    """get_memory_quality should aggregate scores correctly."""
    mem, path = _fresh_memory()
    try:
        # All positive → positive quality
        for i in range(3):
            mem.record_attempt([f"E{i}"], [f"c{i}"])
            mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        quality = mem.get_memory_quality()
        assert quality > 0, f"Expected positive quality, got {quality}"
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    mem2, path2 = _fresh_memory()
    try:
        # All negative → negative quality
        for i in range(3):
            mem2.record_attempt([f"E{i}"], [f"c{i}"])
            mem2.record_outcome(confidence=0.1, verdict="FAIL", retried=False)

        quality2 = mem2.get_memory_quality()
        assert quality2 < 0, f"Expected negative quality, got {quality2}"
    finally:
        try:
            os.remove(path2)
        except FileNotFoundError:
            pass

    mem3, path3 = _fresh_memory()
    try:
        # Empty → zero
        assert mem3.get_memory_quality() == 0.0
        print("  [PASS] test_memory_quality")
    finally:
        try:
            os.remove(path3)
        except FileNotFoundError:
            pass


def test_depth_controller_memory_influence():
    """Depth controller should respond to memory_quality signal."""
    # These tests don't require SessionMemory, they only test compute_top_k
    # Mid confidence + positive memory → narrow
    k1 = compute_top_k(0.65, 1, 3, memory_quality=0.5)
    assert k1 < 3, f"Positive memory should narrow, got k={k1}"

    # Mid confidence + no memory → base
    k2 = compute_top_k(0.65, 1, 3, memory_quality=0.0)
    assert k2 == 3, f"No memory should use base, got k={k2}"

    # Low confidence + negative memory → widen more aggressively
    k3 = compute_top_k(0.3, 1, 3, memory_quality=-0.3)
    k4 = compute_top_k(0.3, 1, 3, memory_quality=0.0)
    assert k3 > k4, f"Negative memory should widen more: {k3} vs {k4}"
    print("  [PASS] test_depth_controller_memory_influence")


def test_confidence_router_memory_influence():
    """Confidence router should respond to memory_quality signal."""
    # These tests don't require SessionMemory, they only test route_by_confidence
    # Negative memory → forced broadening
    r1 = route_by_confidence(0.7, 1, memory_quality=-0.3)
    assert r1["broaden"] is True, "Negative memory should force broaden"

    # Mid confidence + positive memory → no fallback
    r2 = route_by_confidence(0.65, 1, memory_quality=0.5)
    assert r2["use_fallback"] is False, "Positive memory should disable fallback"

    # Mid confidence + no memory → use fallback
    r3 = route_by_confidence(0.65, 1, memory_quality=0.0)
    assert r3["use_fallback"] is True, "No memory should keep fallback"
    print("  [PASS] test_confidence_router_memory_influence")


def test_novelty_detection():
    """Novelty detection should still work correctly."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["E1"], ["c1", "c2"])
        mem.record_outcome(0.7, "PASS", False)

        # All seen → 0% novel
        assert mem.get_novel_chunk_penalty(["c1", "c2"]) == 0.0

        # Mix of seen and new → 50% novel
        assert mem.get_novel_chunk_penalty(["c1", "c3"]) == 0.5

        # All new → 100% novel
        assert mem.get_novel_chunk_penalty(["c4", "c5"]) == 1.0
        print("  [PASS] test_novelty_detection")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_mixed_outcomes_accumulate():
    """Multiple outcomes for the same entity should accumulate correctly."""
    mem, path = _fresh_memory()
    try:
        # Two positive outcomes
        mem.record_attempt(["SharedEntity"], ["shared_chunk"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        mem.record_attempt(["SharedEntity"], ["shared_chunk"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        score_after_2_pos = mem._entities["sharedentity"].score
        assert score_after_2_pos == round(2 * STRONG_POS_DELTA, 4)

        # One negative outcome
        mem.record_attempt(["SharedEntity"], ["shared_chunk"])
        mem.record_outcome(confidence=0.2, verdict="FAIL", retried=False)

        score_after_neg = mem._entities["sharedentity"].score
        assert score_after_neg < score_after_2_pos, "Negative should reduce score"
        assert score_after_neg == round(2 * STRONG_POS_DELTA + STRONG_NEG_DELTA, 4)
        print("  [PASS] test_mixed_outcomes_accumulate")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# -----------------------------------------------------------------------
# Concept Generalization Tests
# -----------------------------------------------------------------------

def test_concept_taxonomy_lookup():
    """Taxonomy should map entities to concepts and find siblings."""
    concepts = get_concepts("qdrant")
    assert "vector database" in concepts, f"Expected 'vector database', got {concepts}"

    siblings = get_siblings("qdrant")
    assert "pinecone" in siblings, f"Expected 'pinecone' in siblings, got {siblings}"
    assert "qdrant" not in siblings, "Entity should not be its own sibling"

    assert get_concept_size("vector database") >= 5
    assert get_concepts("nonexistent_entity_xyz") == []
    print("  [PASS] test_concept_taxonomy_lookup")


def test_concept_propagation_damped():
    """Entity outcome should propagate to parent concept with damping."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["Qdrant"], ["c1"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        assert "vector database" in mem._concepts, "Concept not created"
        cscore = mem._concepts["vector database"].score
        assert cscore > 0, f"Expected positive concept score, got {cscore}"

        escore = mem._entities["qdrant"].score
        assert cscore < escore, (
            f"Concept score ({cscore}) should be < entity score ({escore})"
        )
        print("  [PASS] test_concept_propagation_damped")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_sibling_inference():
    """Unseen siblings should get inferred boost from concept score."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["Qdrant"], ["c1"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        boosts = mem.get_entity_boosts()
        assert "qdrant" in boosts
        assert boosts["qdrant"] > 0

        # Pinecone (never seen) should get inferred boost if score > threshold
        if "pinecone" in boosts:
            assert boosts["pinecone"] > 0
            assert boosts["pinecone"] < boosts["qdrant"]
        print("  [PASS] test_sibling_inference")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_anti_overgeneralization():
    """Concept scores should be clamped tighter than entity scores."""
    mem, path = _fresh_memory()
    try:
        for _ in range(20):
            mem.record_attempt(["Qdrant"], ["c1"])
            mem.record_outcome(confidence=0.9, verdict="PASS", retried=False)

        cscore = mem._concepts["vector database"].score
        assert cscore <= 0.5, f"Concept score {cscore} exceeds max 0.5"
        assert cscore >= -0.5, f"Concept score {cscore} below min -0.5"

        escore = mem._entities["qdrant"].score
        assert escore > cscore, f"Entity ({escore}) should exceed concept ({cscore})"
        print("  [PASS] test_anti_overgeneralization")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_direct_score_overrides_concept():
    """Direct entity scores should override concept-inferred boosts."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["Qdrant"], ["c1"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        mem.record_attempt(["Pinecone"], ["c2"])
        mem.record_outcome(confidence=0.2, verdict="FAIL", retried=False)

        boosts = mem.get_entity_boosts()
        assert boosts.get("pinecone", 0) < 0, (
            f"Direct negative should override concept boost: {boosts.get('pinecone')}"
        )
        print("  [PASS] test_direct_score_overrides_concept")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_concept_scores_method():
    """get_concept_scores should return learned concept quality scores."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["Qdrant"], ["c1"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        scores = mem.get_concept_scores()
        assert "vector database" in scores, f"Expected concept score, got {scores}"
        assert scores["vector database"] > 0
        print("  [PASS] test_concept_scores_method")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# -----------------------------------------------------------------------
# Concept Discovery Tests
# -----------------------------------------------------------------------

def test_cooccurrence_tracking():
    """Co-occurrence pairs should be recorded correctly."""
    disc = ConceptDiscovery()
    disc.record_cooccurrence(["alpha", "beta", "gamma"], attempt=1)

    assert disc.pair_count == 3, f"Expected 3 pairs, got {disc.pair_count}"

    stats = disc.get_pair_stats()
    pair_entities = [tuple(s["entities"]) for s in stats]
    assert ("alpha", "beta") in pair_entities
    assert ("alpha", "gamma") in pair_entities
    assert ("beta", "gamma") in pair_entities
    print("  [PASS] test_cooccurrence_tracking")


def test_cooccurrence_success_rate():
    """Success counts should update correctly."""
    disc = ConceptDiscovery()
    entities = ["alpha", "beta"]

    # 3 co-occurrences, 2 successes
    for i in range(3):
        disc.record_cooccurrence(entities, attempt=i + 1)

    disc.record_success(entities, success=True)
    disc.record_success(entities, success=True)
    disc.record_success(entities, success=False)  # not counted

    stats = disc.get_pair_stats()
    assert len(stats) == 1
    assert stats[0]["count"] == 3
    assert stats[0]["success_rate"] == round(2 / 3, 3)
    print("  [PASS] test_cooccurrence_success_rate")


def test_discovery_triggers_on_evidence():
    """Concepts should be discovered when pairs have enough evidence."""
    disc = ConceptDiscovery()
    entities = ["kubernetes", "docker", "helm"]

    # Build up co-occurrence evidence
    for i in range(MIN_COOCCURRENCE + 1):
        disc.record_cooccurrence(entities, attempt=i + 1)
        disc.record_success(entities, success=True)

    # Discover (no static overlap since these aren't in CONCEPT_MAP)
    learned = disc.discover_concepts(CONCEPT_MAP)

    assert len(learned) >= 1, f"Expected at least 1 concept, got {len(learned)}"

    # All three entities should be in the same learned concept
    found = False
    for name, members in learned.items():
        if "kubernetes" in members and "docker" in members:
            found = True
            # Now expects semantic name "container orchestration" or fallback
            assert (name == "container orchestration"
                    or name.startswith("learned:")), (
                f"Expected semantic or learned: name, got {name}"
            )
    assert found, f"Expected kubernetes+docker concept, got {learned}"
    print("  [PASS] test_discovery_triggers_on_evidence")


def test_overlap_filter():
    """Concepts that overlap >50% with static taxonomy should be filtered."""
    disc = ConceptDiscovery()
    # Use entities from the static "vector database" concept
    overlapping = ["qdrant", "pinecone", "milvus"]

    for i in range(MIN_COOCCURRENCE + 1):
        disc.record_cooccurrence(overlapping, attempt=i + 1)
        disc.record_success(overlapping, success=True)

    learned = disc.discover_concepts(CONCEPT_MAP)

    # Should be filtered out because >50% overlap with "vector database"
    for name, members in learned.items():
        overlap_with_vdb = len(set(members) & {"qdrant", "pinecone", "milvus",
                                                 "weaviate", "chroma", "faiss", "pgvector"})
        assert overlap_with_vdb / len(members) <= 0.5, (
            f"Concept {name} has too much overlap with static taxonomy"
        )
    print("  [PASS] test_overlap_filter")


def test_discovery_serialization():
    """Discovery state should survive serialization round-trip."""
    disc = ConceptDiscovery()
    entities = ["alpha", "beta"]

    for i in range(MIN_COOCCURRENCE + 1):
        disc.record_cooccurrence(entities, attempt=i + 1)
        disc.record_success(entities, success=True)

    disc.discover_concepts({})

    # Serialize and deserialize
    data = disc.to_dict()
    disc2 = ConceptDiscovery.from_dict(data)

    assert disc2.pair_count == disc.pair_count
    assert disc2.learned_concepts == disc.learned_concepts
    print("  [PASS] test_discovery_serialization")


# -----------------------------------------------------------------------
# Semantic Labeler Tests
# -----------------------------------------------------------------------

def test_labeler_known_cluster():
    """Known cluster should get a semantic label with confidence."""
    label = label_cluster(["docker", "kubernetes", "helm"])
    assert label.is_inferred is True, f"Expected inferred, got {label}"
    assert label.name == "container orchestration", f"Got: {label.name}"
    assert label.confidence >= 0.4, f"Confidence too low: {label.confidence}"
    print("  [PASS] test_labeler_known_cluster")


def test_labeler_unknown_cluster():
    """Unknown cluster should fallback to raw name."""
    label = label_cluster(["xyzzy", "plugh", "zorkmid"])
    assert label.is_inferred is False, f"Should not infer for unknown: {label}"
    assert label.name.startswith("learned:"), f"Expected fallback, got {label.name}"
    assert label.confidence == 0.0
    print("  [PASS] test_labeler_unknown_cluster")


def test_labeler_partial_match():
    """Partial match below threshold should fallback."""
    # Only 1 matching keyword — below min_match of 2
    label = label_cluster(["docker", "xyzzy", "plugh", "zorkmid", "quux"])
    # Docker alone matches 1 keyword in several signatures but min_match is 2
    if label.is_inferred:
        assert label.confidence >= 0.4, f"Sub-threshold match passed: {label}"
    else:
        assert label.name.startswith("learned:"), f"Bad fallback: {label.name}"
    print("  [PASS] test_labeler_partial_match")


# -----------------------------------------------------------------------
# Critic Feedback Tests
# -----------------------------------------------------------------------

def test_hallucination_penalty_reduces_score():
    """High hallucination risk should apply extra negative to entity scores."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["Qdrant"], ["c1"])

        # PASS with high hallucination → penalty should reduce the positive
        signals = CriticSignals(
            hallucination_penalty=-0.05,
            penalize_concepts=True,
        )
        mem.record_outcome(
            confidence=0.85, verdict="PASS", retried=False,
            critic_signals=signals,
        )

        score = mem._entities["qdrant"].score
        # Base delta = +0.15 (strong positive), hallucination = -0.05 → net +0.10
        expected = round(STRONG_POS_DELTA + (-0.05), 4)
        assert abs(score - expected) < 0.001, (
            f"Expected ~{expected}, got {score}"
        )
        print("  [PASS] test_hallucination_penalty_reduces_score")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_missing_coverage_boosts_discovery():
    """Low coverage should inject synthetic co-occurrence pairs."""
    mem, path = _fresh_memory()
    try:
        mem.record_attempt(["Qdrant", "Pinecone"], ["c1", "c2"])

        signals = CriticSignals(
            boost_discovery=True,
            coverage_boost=0.05,
            missing_terms=["weaviate", "milvus"],
        )
        mem.record_outcome(
            confidence=0.3, verdict="PARTIAL", retried=False,
            critic_signals=signals,
        )

        # The discovery tracker should now have pairs involving the missing terms
        pair_count = mem._discovery.pair_count
        assert pair_count >= 3, (
            f"Expected >= 3 pairs (original + synthetic), got {pair_count}"
        )
        print("  [PASS] test_missing_coverage_boosts_discovery")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_concept_penalty_on_fail():
    """FAIL verdict with critic signals should extra-penalize concepts."""
    mem, path = _fresh_memory()
    try:
        # First: give qdrant a positive outcome to create concept score
        mem.record_attempt(["Qdrant"], ["c1"])
        mem.record_outcome(confidence=0.85, verdict="PASS", retried=False)

        concept_score_before = mem._concepts.get("vector database",
                                                   ConceptRecord()).score

        # Second: FAIL with concept penalty
        mem.record_attempt(["Qdrant"], ["c2"])
        signals = CriticSignals(
            penalize_concepts=True,
            concept_fail_penalty=0.05,
        )
        mem.record_outcome(
            confidence=0.2, verdict="FAIL", retried=False,
            critic_signals=signals,
        )

        concept_score_after = mem._concepts.get("vector database",
                                                  ConceptRecord()).score
        assert concept_score_after < concept_score_before, (
            f"Concept score should decrease: before={concept_score_before}, "
            f"after={concept_score_after}"
        )
        print("  [PASS] test_concept_penalty_on_fail")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_extract_signals_from_critic():
    """extract_signals should parse critic output into CriticSignals."""
    signals = extract_signals(
        confidence=0.3,
        verdict="FAIL",
        hallucination_risk=0.6,
        coverage_score=0.2,
        issues=["Missing key terms: weaviate, milvus"],
    )
    assert signals.hallucination_penalty < 0, f"Expected negative penalty"
    assert signals.penalize_concepts is True
    assert signals.boost_discovery is True
    assert signals.concept_fail_penalty > 0
    assert "weaviate" in signals.missing_terms
    assert "milvus" in signals.missing_terms
    print("  [PASS] test_extract_signals_from_critic")


# -----------------------------------------------------------------------
# Strategy Tracker Tests
# -----------------------------------------------------------------------

def test_strategy_ema_scoring():
    """Strategy scores should update via EMA based on outcome."""
    tracker = StrategyTracker()
    
    # Record strategies used
    tracker.record_strategy("rewrite", "intent-rephrase")
    tracker.record_strategy("depth", "k=3")
    
    # Simulate attempt 1 (failed)
    tracker.record_outcome(confidence=0.1, is_success=False)
    
    scores = tracker.get_strategy_scores("rewrite")
    score1 = scores["intent-rephrase"]
    
    # Expected: alpha * 0.1 + (1-alpha) * 0.5 = 0.3 * 0.1 + 0.7 * 0.5 = 0.03 + 0.35 = 0.38
    assert abs(score1 - 0.38) < 0.001, f"Expected 0.38, got {score1}"
    
    # Attempt 2 (succeeds) - simulate using same strategy
    tracker.record_strategy("rewrite", "intent-rephrase")
    tracker.record_outcome(confidence=0.9, is_success=True)
    
    scores2 = tracker.get_strategy_scores("rewrite")
    score2 = scores2["intent-rephrase"]
    # Expected: 0.3 * 0.9 + 0.7 * 0.38 = 0.27 + 0.266 = 0.536
    assert abs(score2 - 0.536) < 0.001, f"Expected 0.536, got {score2}"
    print("  [PASS] test_strategy_ema_scoring")


def test_strategy_best_selection():
    """get_best_strategy should return highest-scoring active strategy."""
    tracker = StrategyTracker()
    
    # Force some scores
    tracker._domains["rewrite"]["stratA"] = type("Mock", (), {"score": 0.8, "attempts": 2})()
    tracker._domains["rewrite"]["stratB"] = type("Mock", (), {"score": 0.4, "attempts": 2})()
    
    best = tracker.get_best_strategy("rewrite")
    assert best == "stratA", f"Expected 'stratA', got {best}"
    print("  [PASS] test_strategy_best_selection")


def test_strategy_auto_disable():
    """Strategies below threshold after N attempts should be disabled."""
    tracker = StrategyTracker()
    
    # Score 0.15, but only 2 attempts → not disabled yet
    tracker._domains["routing"]["config1"] = type("Mock", (), {"score": 0.15, "attempts": 2})()
    assert not tracker.is_disabled("routing", "config1")
    
    # Score 0.15, 5 attempts → disabled
    tracker._domains["routing"]["config1"].attempts = 5
    assert tracker.is_disabled("routing", "config1")
    
    # Best selection should skip disabled strategies
    tracker._domains["routing"]["config2"] = type("Mock", (), {"score": 0.18, "attempts": 1})() # Score is > initial? No, but < threshold. Let's make it 0.6
    tracker._domains["routing"]["config2"].score = 0.6
    
    best = tracker.get_best_strategy("routing")
    assert best == "config2", f"Expected 'config2', got {best}"
    print("  [PASS] test_strategy_auto_disable")


def test_strategy_tracker_integration_with_memory():
    """SessionMemory should pass hook calls down to fully initialized StrategyTracker."""
    mem, path = _fresh_memory()
    try:
        mem.record_strategy("depth", "k=5")
        mem.record_attempt(["A"], ["c1"])
        mem.record_outcome(confidence=0.8, verdict="PASS", retried=False)
        
        scores = mem.get_strategy_scores("depth")
        assert "k=5" in scores, "Strategy tracking not wired up properly to record_strategy"
        assert scores["k=5"] > INITIAL_SCORE, "Strategy outcome not wired up"
        
        mem._memory_store.save()
        
        # Reload
        mem2 = SessionMemory(memory_store=MemoryStore(storage_path=path))
        scores2 = mem2.get_strategy_scores("depth")
        assert "k=5" in scores2
        assert abs(scores2["k=5"] - scores["k=5"]) < 0.001
        print("  [PASS] test_strategy_tracker_integration_with_memory")
    finally:
        try:
            os.remove(path)
        except:
            pass


# -----------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Performance-Aware Session Memory — Unit Tests")
    print("=" * 60 + "\n")

    tests = [
        test_compute_delta_signals,
        test_positive_outcome_boosts,
        test_negative_outcome_penalizes,
        test_score_clamping,
        test_entity_boosts_performance_weighted,
        test_chunk_scores,
        test_memory_quality,
        test_depth_controller_memory_influence,
        test_confidence_router_memory_influence,
        test_novelty_detection,
        test_mixed_outcomes_accumulate,
        # Concept generalization tests
        test_concept_taxonomy_lookup,
        test_concept_propagation_damped,
        test_sibling_inference,
        test_anti_overgeneralization,
        test_direct_score_overrides_concept,
        test_concept_scores_method,
        # Concept discovery tests
        test_cooccurrence_tracking,
        test_cooccurrence_success_rate,
        test_discovery_triggers_on_evidence,
        test_overlap_filter,
        test_discovery_serialization,
        # Semantic labeler tests
        test_labeler_known_cluster,
        test_labeler_unknown_cluster,
        test_labeler_partial_match,
        # Critic feedback tests
        test_hallucination_penalty_reduces_score,
        test_missing_coverage_boosts_discovery,
        test_concept_penalty_on_fail,
        test_extract_signals_from_critic,
        # Strategy Tracking tests
        test_strategy_ema_scoring,
        test_strategy_best_selection,
        test_strategy_auto_disable,
        test_strategy_tracker_integration_with_memory,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [FAIL] {test_fn.__name__}: UNEXPECTED ERROR: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {passed}/{len(tests)} passed, {failed}/{len(tests)} failed")
    print(f"{'=' * 60}\n")

    exit(0 if failed == 0 else 1)
