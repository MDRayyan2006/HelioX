"""
Session Memory: Performance-aware per-session entity and chunk tracking.

Tracks entities and chunks across retry attempts, learning from outcomes
(confidence, verdict, retry status) to build performance scores that
influence future retrieval and query rewriting.

Learning rules:
  Strong positive: confidence ≥ 0.8, PASS, no retry  → +0.15
  Weak positive:   confidence ≥ 0.5, not FAIL         → +0.05
  Weak negative:   confidence < 0.5 OR PARTIAL         → -0.05
  Strong negative: FAIL OR (retried + conf < 0.4)     → -0.15

Scores are clamped to [-1.0, +1.0].

Deterministic, with persistent storage via MemoryStore.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
from core.logger import get_logger
from core.memory_store import MemoryStore
from services.adaptive.critic_feedback import CriticSignals
import math

logger = get_logger("SESSION_MEMORY")

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
BOOST_SCALE = 0.15            # max boost magnitude from performance score
STRONG_POS_DELTA = 0.15       # score delta: high confidence + PASS + no retry
WEAK_POS_DELTA = 0.05         # score delta: decent confidence, not FAIL
WEAK_NEG_DELTA = -0.05        # score delta: low confidence or PARTIAL
STRONG_NEG_DELTA = -0.15      # score delta: FAIL or retried with low confidence
SCORE_MIN = -1.0
SCORE_MAX = 1.0

# Concept generalization
CONCEPT_DAMPING = 0.3         # entity → concept propagation factor
SIBLING_DAMPING = 0.2         # concept → sibling inference factor (query-time)
CONCEPT_SCORE_MIN = -0.5      # tighter clamp for concepts
CONCEPT_SCORE_MAX = 0.5

# Score decay
DECAY_RATE = 0.02             # multiplicative decay per attempt for unused items (2%)

# Concept discovery
DISCOVERY_INTERVAL = 5        # run discovery every N attempts
LEARNED_CONCEPT_DAMPING = 0.5 # learned concepts propagate at half strength


# ---------------------------------------------------------------------------
# Record types
# ---------------------------------------------------------------------------

@dataclass
class EntityRecord:
    """Performance-tracked entity."""
    appearances: int = 0
    score: float = 0.0
    last_confidence: float = 0.0

@dataclass
class ChunkRecord:
    """Performance-tracked chunk."""
    appearances: int = 0
    score: float = 0.0
    last_confidence: float = 0.0
    last_verdict: str = ""

@dataclass
class ConceptRecord:
    """Performance-tracked concept (generalized from entities)."""
    score: float = 0.0
    update_count: int = 0
    member_count: int = 1


def _clamp(value: float) -> float:
    """Clamp score to [SCORE_MIN, SCORE_MAX]."""
    return max(SCORE_MIN, min(SCORE_MAX, value))


def _compute_delta(confidence: float, verdict: str, retried: bool) -> float:
    """
    Compute the score delta from an outcome.

    Signals (evaluated top-down, first match wins):
      1. Strong positive: confidence ≥ 0.8 AND verdict=PASS AND not retried
      2. Strong negative: verdict=FAIL OR (retried AND confidence < 0.4)
      3. Weak negative:   confidence < 0.5 OR verdict=PARTIAL
      4. Weak positive:   everything else (decent result)
    """
    # Strong positive
    if confidence >= 0.8 and verdict == "PASS" and not retried:
        return STRONG_POS_DELTA

    # Strong negative
    if verdict == "FAIL" or (retried and confidence < 0.4):
        return STRONG_NEG_DELTA

    # Weak negative
    if confidence < 0.5 or verdict == "PARTIAL":
        return WEAK_NEG_DELTA

    # Weak positive (decent result)
    return WEAK_POS_DELTA


class SessionMemory:
    """
    Per-session memory that learns from outcomes across retry attempts.

    Tracks:
        - Per-entity performance scores (success/failure weighted)
        - Per-chunk performance scores (success/failure weighted)
        - Aggregate memory quality signal

    Args:
        memory_store: Optional MemoryStore instance for persistence.
                      If None, creates a new MemoryStore with default storage file.
    """

    def __init__(self, memory_store: Optional[MemoryStore] = None):
        # Lazy import to avoid circular dependency at module level
        from services.adaptive.concept_taxonomy import (
            get_concepts, get_concept_size, CONCEPT_MAP,
            register_dynamic_concepts, get_all_concepts,
        )
        from services.adaptive.concept_discovery import ConceptDiscovery
        from services.adaptive.strategy_tracker import StrategyTracker

        self._get_concepts = get_concepts
        self._get_concept_size = get_concept_size
        self._concept_map = CONCEPT_MAP
        self._register_dynamic = register_dynamic_concepts
        self._get_all_concepts = get_all_concepts

        # Initialize persistence layer
        self._memory_store = memory_store or MemoryStore()
        self._memory_store.load()

        # Initialize concept discovery from persisted state
        self._discovery = ConceptDiscovery.from_dict(
            self._memory_store._discovery
        )
        self._strategy_tracker = StrategyTracker.from_dict(
            self._memory_store._strategy_tracker
        )
        # Re-register any previously learned concepts
        if self._discovery.learned_concepts:
            self._register_dynamic(self._discovery.learned_concepts)

        # Load persisted data into in-memory structures
        self._entities: Dict[str, EntityRecord] = {}
        self._chunks: Dict[str, ChunkRecord] = {}

        # Load entities from persistent store
        for entity, data in self._memory_store._entities.items():
            rec = EntityRecord(
                appearances=data["appearances"],
                score=data["score"],
                last_confidence=data["last_confidence"]
            )
            self._entities[entity] = rec

        # Load chunks from persistent store
        for chunk_id, data in self._memory_store._chunks.items():
            rec = ChunkRecord(
                appearances=data["appearances"],
                score=data["score"],
                last_confidence=data["last_confidence"],
                last_verdict=data.get("last_verdict", "")
            )
            self._chunks[chunk_id] = rec

        self._attempt_count: int = 0
        self._last_entities: List[str] = []
        self._last_chunk_ids: List[str] = []
        self._seen_chunk_ids: Set[str] = set(self._chunks.keys())

        # Load concepts from persistent store
        self._concepts: Dict[str, ConceptRecord] = {}
        for concept, data in self._memory_store._concepts.items():
            self._concepts[concept] = ConceptRecord(
                score=data.get("score", 0.0),
                update_count=data.get("update_count", 0),
                member_count=data.get("member_count", 1),
            )

        logger.info(
            f"SessionMemory initialized: "
            f"{len(self._entities)} entities, {len(self._chunks)} chunks, "
            f"{len(self._concepts)} concepts loaded from persistence"
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_attempt(
        self,
        entities: List[str],
        chunk_ids: List[str],
    ) -> None:
        """
        Record entities and chunk IDs from a completed attempt.

        Updates appearance counts and stores the attempt's items so that
        the subsequent ``record_outcome`` call can apply learning deltas.

        Args:
            entities: Entities found in the query/chunks for this attempt.
            chunk_ids: Chunk IDs retrieved in this attempt.
        """
        self._attempt_count += 1
        self._last_entities = []
        self._last_chunk_ids = []

        for entity in entities:
            key = entity.lower().strip()
            if not key:
                continue
            if key not in self._entities:
                self._entities[key] = EntityRecord()
            self._entities[key].appearances += 1
            self._last_entities.append(key)

        for cid in chunk_ids:
            if cid not in self._chunks:
                self._chunks[cid] = ChunkRecord()
            self._chunks[cid].appearances += 1
            self._last_chunk_ids.append(cid)
            self._seen_chunk_ids.add(cid)

        logger.info(
            f"Recorded attempt {self._attempt_count}: "
            f"{len(self._last_entities)} entities, "
            f"{len(self._last_chunk_ids)} chunks "
            f"(total unique entities: {len(self._entities)}, "
            f"total unique chunks: {len(self._chunks)})"
        )

        # Feed entity pairs to co-occurrence tracker
        if len(self._last_entities) >= 2:
            self._discovery.record_cooccurrence(
                self._last_entities, self._attempt_count
            )

    def record_strategy(self, domain: str, strategy_key: str) -> None:
        """
        Record that a strategy was used in the current attempt.
        """
        if self._strategy_tracker:
            self._strategy_tracker.record_strategy(domain, strategy_key)

    def record_outcome(
        self,
        confidence: float,
        verdict: str,
        retried: bool,
        critic_signals: CriticSignals = None,
    ) -> None:
        """
        Apply learning rules to entities and chunks from the last attempt.

        Must be called after ``record_attempt`` for the same attempt.

        Args:
            confidence: Critic confidence score (0-1).
            verdict: Critic verdict ("PASS", "PARTIAL", "FAIL").
            retried: Whether this attempt will be followed by another retry.
            critic_signals: Optional CriticSignals from critic feedback.
        """
        delta = _compute_delta(confidence, verdict, retried)
        signal = ("strong_pos" if delta == STRONG_POS_DELTA
                  else "weak_pos" if delta == WEAK_POS_DELTA
                  else "weak_neg" if delta == WEAK_NEG_DELTA
                  else "strong_neg")

        logger.info(
            f"Outcome: confidence={confidence:.2f}, verdict={verdict}, "
            f"retried={retried} → signal={signal}, delta={delta:+.2f}"
        )

        # Update entity scores (in-memory)
        for key in self._last_entities:
            rec = self._entities[key]
            rec.score = _clamp(rec.score + delta)
            rec.last_confidence = confidence

        # Update chunk scores (in-memory)
        for cid in self._last_chunk_ids:
            rec = self._chunks[cid]
            rec.score = _clamp(rec.score + delta)
            rec.last_confidence = confidence
            rec.last_verdict = verdict

        # Persist entity/chunk updates to memory store
        for key in self._last_entities:
            self._memory_store.update_entity(key, delta, confidence)

        for cid in self._last_chunk_ids:
            self._memory_store.update_chunk(cid, delta, confidence, verdict)

        # --- Critic-driven hallucination penalty ---
        critic_info = ""
        if critic_signals and critic_signals.hallucination_penalty < 0:
            h_pen = critic_signals.hallucination_penalty
            for key in self._last_entities:
                rec = self._entities[key]
                rec.score = _clamp(rec.score + h_pen)
                self._memory_store.update_entity(key, h_pen, confidence)
            for cid in self._last_chunk_ids:
                rec = self._chunks[cid]
                rec.score = _clamp(rec.score + h_pen)
                self._memory_store.update_chunk(cid, h_pen, confidence, verdict)
            critic_info += f", hallucination_penalty={h_pen:.4f}"
            logger.info(
                f"Applied hallucination penalty {h_pen:.4f} to "
                f"{len(self._last_entities)} entities, "
                f"{len(self._last_chunk_ids)} chunks"
            )

        # --- Concept propagation ---
        # Propagate entity deltas to parent concepts (damped)
        propagated_concepts: Dict[str, float] = {}
        for key in self._last_entities:
            parent_concepts = self._get_concepts(key)
            for concept in parent_concepts:
                member_count = self._get_concept_size(concept)
                # Damped delta: CONCEPT_DAMPING / member_count
                concept_delta = delta * CONCEPT_DAMPING / max(member_count, 1)
                concept_key = concept.lower().strip()

                # Update in-memory concept record
                if concept_key not in self._concepts:
                    self._concepts[concept_key] = ConceptRecord(
                        member_count=member_count,
                    )
                rec = self._concepts[concept_key]
                rec.score = max(CONCEPT_SCORE_MIN,
                                min(CONCEPT_SCORE_MAX, rec.score + concept_delta))
                rec.update_count += 1
                rec.member_count = member_count

                # Persist concept update
                self._memory_store.update_concept(
                    concept_key, concept_delta, member_count,
                    clamp_min=CONCEPT_SCORE_MIN, clamp_max=CONCEPT_SCORE_MAX,
                )

                propagated_concepts[concept_key] = rec.score

        # --- Critic-driven concept penalty ---
        if critic_signals and critic_signals.penalize_concepts:
            c_pen = -(critic_signals.concept_fail_penalty or 0.0)
            if c_pen < 0:
                # Apply to all propagated concepts
                for concept_key in propagated_concepts:
                    if concept_key in self._concepts:
                        rec = self._concepts[concept_key]
                        rec.score = max(CONCEPT_SCORE_MIN,
                                        min(CONCEPT_SCORE_MAX, rec.score + c_pen))
                        self._memory_store.update_concept(
                            concept_key, c_pen, rec.member_count,
                            clamp_min=CONCEPT_SCORE_MIN, clamp_max=CONCEPT_SCORE_MAX,
                        )
                        propagated_concepts[concept_key] = rec.score
                critic_info += f", concept_penalty={c_pen:.4f}"
                logger.info(
                    f"Applied concept penalty {c_pen:.4f} to "
                    f"{len(propagated_concepts)} concepts"
                )

        # --- Co-occurrence success tracking ---
        is_success = verdict == "PASS"
        if len(self._last_entities) >= 2:
            self._discovery.record_success(self._last_entities, is_success)

        # --- Strategy tracking ---
        if self._strategy_tracker:
            self._strategy_tracker.record_outcome(confidence, is_success)

        # --- Critic-driven discovery boost ---
        if (critic_signals and critic_signals.boost_discovery
                and critic_signals.missing_terms):
            # Inject synthetic co-occurrence pairs: existing entities + missing terms
            boosted_entities = list(self._last_entities) + critic_signals.missing_terms
            if len(boosted_entities) >= 2:
                self._discovery.record_cooccurrence(
                    boosted_entities, self._attempt_count
                )
                # Credit as success to accelerate concept formation
                self._discovery.record_success(boosted_entities, success=True)
                critic_info += f", discovery_boost={len(critic_signals.missing_terms)} terms"
                logger.info(
                    f"Boosted discovery with {len(critic_signals.missing_terms)} "
                    f"missing terms: {critic_signals.missing_terms}"
                )

        # --- Periodic concept discovery ---
        discovered_info = ""
        if self._attempt_count % DISCOVERY_INTERVAL == 0:
            # Use get_all_concepts to check against both static + existing dynamic
            all_concepts = self._get_all_concepts()
            static_only = dict(self._concept_map)  # only static for overlap check
            learned = self._discovery.discover_concepts(static_only)
            if learned:
                count = self._register_dynamic(learned)
                # Update concept_map reference for sibling inference
                self._concept_map = self._get_all_concepts()
                # Propagate scores to newly learned concepts
                for concept_name, members in learned.items():
                    concept_key = concept_name.lower().strip()
                    member_count = len(members)
                    if concept_key not in self._concepts:
                        self._concepts[concept_key] = ConceptRecord(
                            member_count=member_count,
                        )
                discovered_info = f", discovered {len(learned)} new concepts"

            # Decay and prune co-occurrences
            self._discovery.decay_and_prune(self._attempt_count)

        # --- Score decay for unused items ---
        # Decay entities not used in this attempt
        decayed_entities = 0
        for entity_key, rec in self._entities.items():
            if entity_key not in self._last_entities and abs(rec.score) > 0.001:
                old_score = rec.score
                rec.score = _clamp(old_score * (1 - DECAY_RATE))
                if entity_key in self._memory_store._entities:
                    store_old = self._memory_store._entities[entity_key]["score"]
                    store_new = _clamp(store_old * (1 - DECAY_RATE))
                    self._memory_store._entities[entity_key]["score"] = store_new
                decayed_entities += 1

        # Decay chunks not used in this attempt
        decayed_chunks = 0
        for cid, rec in self._chunks.items():
            if cid not in self._last_chunk_ids and abs(rec.score) > 0.001:
                old_score = rec.score
                rec.score = _clamp(old_score * (1 - DECAY_RATE))
                if cid in self._memory_store._chunks:
                    store_old = self._memory_store._chunks[cid]["score"]
                    store_new = _clamp(store_old * (1 - DECAY_RATE))
                    self._memory_store._chunks[cid]["score"] = store_new
                decayed_chunks += 1

        # Decay concepts not propagated this attempt
        decayed_concepts = 0
        propagated_keys = set(propagated_concepts.keys())
        for concept_key, rec in self._concepts.items():
            if concept_key not in propagated_keys and abs(rec.score) > 0.001:
                old_score = rec.score
                new_score = max(CONCEPT_SCORE_MIN,
                               min(CONCEPT_SCORE_MAX, old_score * (1 - DECAY_RATE)))
                rec.score = new_score
                if concept_key in self._memory_store._concepts:
                    store_old = self._memory_store._concepts[concept_key]["score"]
                    store_new = max(CONCEPT_SCORE_MIN,
                                    min(CONCEPT_SCORE_MAX, store_old * (1 - DECAY_RATE)))
                    self._memory_store._concepts[concept_key]["score"] = store_new
                decayed_concepts += 1

        # Save state to memory store
        self._memory_store._discovery = self._discovery.to_dict()
        if self._strategy_tracker:
            self._memory_store._strategy_tracker = self._strategy_tracker.to_dict()

        # Save to disk
        self._memory_store.save()

        decay_info = []
        if decayed_entities:
            decay_info.append(f"{decayed_entities} entities decayed")
        if decayed_chunks:
            decay_info.append(f"{decayed_chunks} chunks decayed")
        if decayed_concepts:
            decay_info.append(f"{decayed_concepts} concepts decayed")
        decay_str = f" ({', '.join(decay_info)})" if decay_info else ""

        logger.info(
            f"Updated {len(self._last_entities)} entity scores, "
            f"{len(self._last_chunk_ids)} chunk scores"
            + (f", propagated to {len(propagated_concepts)} concepts: "
               f"{propagated_concepts}" if propagated_concepts else "")
            + decay_str
            + discovered_info
            + critic_info
            + " (persisted)"
        )

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def get_entity_boosts(self) -> Dict[str, float]:
        """
        Get performance-weighted entity boost factors.

        Entities with positive scores get positive boosts; entities with
        negative scores get negative boosts (penalties). Entities with
        zero or near-zero scores are omitted.

        Returns:
            Dict mapping entity → boost value (range ±BOOST_SCALE).
        """
        boosts = {}
        for entity, rec in self._entities.items():
            if rec.appearances >= 2 or abs(rec.score) > 0.0:
                boost = round(rec.score * BOOST_SCALE, 4)
                if abs(boost) > 0.001:
                    boosts[entity] = boost

        # Sibling inference: entities with no direct score get concept-inferred boost
        # Only at query time — never written back to entity scores
        inferred_count = 0
        for concept_key, crec in self._concepts.items():
            if abs(crec.score) < 0.001:
                continue
            # Get members of this concept
            members = self._concept_map.get(concept_key, [])
            for member in members:
                m = member.lower().strip()
                if m not in boosts and m not in self._entities:
                    inferred_boost = round(crec.score * SIBLING_DAMPING * BOOST_SCALE, 4)
                    if abs(inferred_boost) > 0.001:
                        boosts[m] = inferred_boost
                        inferred_count += 1

        if boosts:
            logger.info(f"Entity boosts: {len(boosts)} entries "
                        f"({inferred_count} concept-inferred)")
        return boosts

    def get_chunk_scores(self) -> Dict[str, float]:
        """
        Get learned chunk quality scores.

        Returns:
            Dict mapping chunk_id → performance score [-1.0 .. +1.0].
        """
        scores = {
            cid: round(rec.score, 4)
            for cid, rec in self._chunks.items()
            if abs(rec.score) > 0.001
        }
        if scores:
            logger.info(f"Chunk scores: {len(scores)} entries")
        return scores

    def get_memory_quality(self) -> float:
        """
        Aggregate quality signal from all tracked entities and chunks.

        Returns:
            Float in [-1.0 .. +1.0]. Positive = memory has learned good
            patterns; negative = mostly failure signals.
        """
        all_scores = (
            [rec.score for rec in self._entities.values()]
            + [rec.score for rec in self._chunks.values()]
        )
        if not all_scores:
            return 0.0
        quality = _clamp(sum(all_scores) / len(all_scores))
        logger.info(f"Memory quality: {quality:.3f} "
                    f"(from {len(all_scores)} records)")
        return round(quality, 4)

    def get_novel_chunk_penalty(self, chunk_ids: List[str]) -> float:
        """
        Compute what fraction of chunks are novel (not seen before).

        Returns:
            Fraction of new chunks (0-1). Higher = more novel retrieval.
        """
        if not chunk_ids:
            return 0.0
        novel = sum(1 for cid in chunk_ids if cid not in self._seen_chunk_ids)
        return novel / len(chunk_ids)

    def get_concept_scores(self) -> Dict[str, float]:
        """
        Get learned concept quality scores.

        Returns:
            Dict mapping concept → performance score [-0.5 .. +0.5].
        """
        scores = {
            concept: round(crec.score, 4)
            for concept, crec in self._concepts.items()
            if abs(crec.score) > 0.001
        }
        if scores:
            logger.info(f"Concept scores: {scores}")
        return scores

    def get_concept_importance(self) -> Dict[str, float]:
        """
        Compute importance scores for concepts, combining usage frequency and performance.

        Importance ∈ [0, 1].
        Factors:
          - Usage frequency: total appearances of member entities (log normalized)
          - Average confidence: normalized concept score (shifted from [-0.5, 0.5] to [0, 1])

        Returns:
            Dict mapping concept → importance.
        """
        max_usage = 10000  # normalization cap for total entity appearances
        importance: Dict[str, float] = {}

        for concept, crec in self._concepts.items():
            # --- Usage frequency ---
            # Sum appearances of all member entities
            members = self._concept_map.get(concept, [])
            total_appearances = 0
            for member in members:
                mkey = member.lower().strip()
                if mkey in self._entities:
                    total_appearances += self._entities[mkey].appearances

            # Log scaling to dampen large differences, normalized to [0, 1]
            norm_usage = math.log1p(total_appearances) / math.log1p(max_usage)
            norm_usage = min(norm_usage, 1.0)

            # --- Performance (confidence) ---
            # Concept score in [-0.5, 0.5] → shift to [0, 1]
            norm_score = crec.score + 0.5
            norm_score = max(0.0, min(1.0, norm_score))

            # Weighted average (equal weights)
            imp = (norm_usage + norm_score) / 2
            importance[concept] = round(imp, 4)

        if importance:
            logger.info(f"Concept importance: {importance}")
        return importance

    @property
    def attempt_count(self) -> int:
        return self._attempt_count

    def get_strategy_scores(self, domain: str) -> Dict[str, float]:
        """Get EMA scores for a given strategy domain."""
        if not self._strategy_tracker:
            return {}
        return self._strategy_tracker.get_strategy_scores(domain)

    def get_best_strategy(self, domain: str) -> Optional[str]:
        """Get the highest-scoring strategy for a domain."""
        if not self._strategy_tracker:
            return None
        return self._strategy_tracker.get_best_strategy(domain)
