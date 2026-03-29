"""
Concept Discovery: Automatic concept learning from entity co-occurrence.

Tracks which entities appear together in successful attempts and clusters
frequently co-occurring entities into learned concepts. These dynamic
concepts complement the static taxonomy in concept_taxonomy.py.

Algorithm:
  1. Track entity pair co-occurrences across attempts
  2. Score pairs by success rate (success_count / count)
  3. Cluster via greedy single-linkage (highest score first)
  4. Filter clusters that overlap with static taxonomy
  5. Cap total learned concepts

Deterministic, no ML, no external lookups.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, FrozenSet, Tuple, Optional
from core.logger import get_logger
from services.adaptive.concept_labeler import label_cluster

logger = get_logger("CONCEPT_DISCOVERY")

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
MIN_COOCCURRENCE = 3          # minimum pair appearances to consider
MIN_SUCCESS_RATE = 0.5        # minimum success fraction for grouping
MAX_CONCEPT_SIZE = 8          # maximum members in a learned concept
MAX_LEARNED_CONCEPTS = 20     # hard cap on total discovered concepts
OVERLAP_MERGE_THRESHOLD = 0.5 # skip if >50% overlap with static concepts
STALE_THRESHOLD = 20          # prune pairs not seen in this many attempts
DECAY_RATE = 0.02             # co-occurrence decay rate (matches session memory)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CoOccurrence:
    """Tracks how often an entity pair appears together."""
    count: int = 0
    success_count: int = 0
    last_seen_attempt: int = 0


PairKey = FrozenSet  # FrozenSet[str] — unordered entity pair


class ConceptDiscovery:
    """
    Discovers concepts from entity co-occurrence patterns.

    Maintains a co-occurrence matrix of entity pairs and periodically
    clusters them into learned concepts.
    """

    def __init__(self):
        self._pairs: Dict[PairKey, CoOccurrence] = {}
        self._learned_concepts: Dict[str, List[str]] = {}
        self._current_attempt: int = 0

    # ------------------------------------------------------------------
    # Co-occurrence tracking
    # ------------------------------------------------------------------

    def record_cooccurrence(
        self,
        entities: List[str],
        attempt: int,
    ) -> None:
        """
        Record co-occurrence for all entity pairs in this attempt.

        Args:
            entities: List of entity names (already lowered/stripped).
            attempt: Current attempt number.
        """
        self._current_attempt = attempt
        unique = sorted(set(entities))

        if len(unique) < 2:
            return

        # Generate all pairs
        pairs_added = 0
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                pair_key = frozenset({unique[i], unique[j]})
                if pair_key not in self._pairs:
                    self._pairs[pair_key] = CoOccurrence()
                self._pairs[pair_key].count += 1
                self._pairs[pair_key].last_seen_attempt = attempt
                pairs_added += 1

        logger.info(
            f"Recorded {pairs_added} co-occurrence pairs from "
            f"{len(unique)} entities (total tracked: {len(self._pairs)})"
        )

    def record_success(
        self,
        entities: List[str],
        success: bool,
    ) -> None:
        """
        Update success counts for entity pairs from the last attempt.

        Args:
            entities: List of entity names from the attempt.
            success: Whether this attempt was successful (PASS verdict).
        """
        if not success:
            return

        unique = sorted(set(entities))
        if len(unique) < 2:
            return

        updated = 0
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                pair_key = frozenset({unique[i], unique[j]})
                if pair_key in self._pairs:
                    self._pairs[pair_key].success_count += 1
                    updated += 1

        logger.info(f"Updated success count for {updated} pairs")

    def decay_and_prune(self, current_attempt: int) -> int:
        """
        Decay co-occurrence counts and prune stale pairs.

        Args:
            current_attempt: Current attempt number for staleness check.

        Returns:
            Number of pairs pruned.
        """
        to_prune: List[PairKey] = []

        for pair_key, co in self._pairs.items():
            # Prune stale pairs
            if current_attempt - co.last_seen_attempt > STALE_THRESHOLD:
                to_prune.append(pair_key)
                continue

            # Decay counts (multiplicative)
            co.count = max(0, int(co.count * (1 - DECAY_RATE)))
            co.success_count = max(0, int(co.success_count * (1 - DECAY_RATE)))

            # Prune pairs that decayed to zero
            if co.count == 0:
                to_prune.append(pair_key)

        for pk in to_prune:
            del self._pairs[pk]

        if to_prune:
            logger.info(f"Pruned {len(to_prune)} stale/zero co-occurrence pairs")
        return len(to_prune)

    # ------------------------------------------------------------------
    # Concept discovery
    # ------------------------------------------------------------------

    def discover_concepts(
        self,
        static_concepts: Dict[str, List[str]],
    ) -> Dict[str, List[str]]:
        """
        Discover new concepts from co-occurrence patterns.

        Algorithm:
          1. Filter pairs with count >= MIN_COOCCURRENCE
          2. Score by success rate (success_count / count)
          3. Keep pairs with success_rate >= MIN_SUCCESS_RATE
          4. Greedy single-linkage clustering
          5. Filter against static taxonomy (overlap check)
          6. Cap at MAX_LEARNED_CONCEPTS

        Args:
            static_concepts: The existing static CONCEPT_MAP for overlap check.

        Returns:
            Dict mapping concept name → list of member entities.
        """
        # Step 1-3: Filter and score qualifying pairs
        qualifying: List[Tuple[PairKey, float]] = []
        for pair_key, co in self._pairs.items():
            if co.count < MIN_COOCCURRENCE:
                continue
            success_rate = co.success_count / co.count
            if success_rate >= MIN_SUCCESS_RATE:
                qualifying.append((pair_key, success_rate))

        if not qualifying:
            logger.info("No qualifying pairs for concept discovery")
            return {}

        # Sort by success rate descending (deterministic: break ties by sorted pair)
        qualifying.sort(key=lambda x: (-x[1], sorted(x[0])))

        logger.info(
            f"Concept discovery: {len(qualifying)} qualifying pairs "
            f"from {len(self._pairs)} total"
        )

        # Step 4: Greedy single-linkage clustering
        used_entities: Set[str] = set()
        clusters: List[Set[str]] = []

        for pair_key, score in qualifying:
            members = set(pair_key)

            # Skip if all members already clustered
            if members.issubset(used_entities):
                continue

            # Try to grow cluster with connected entities
            cluster = set(members)
            changed = True
            while changed and len(cluster) < MAX_CONCEPT_SIZE:
                changed = False
                for other_key, other_score in qualifying:
                    if other_score < MIN_SUCCESS_RATE:
                        continue
                    other_members = set(other_key)
                    # Connected if shares at least one member with cluster
                    if (other_members & cluster
                            and not other_members.issubset(cluster)):
                        new_member = other_members - cluster
                        if len(cluster) + len(new_member) <= MAX_CONCEPT_SIZE:
                            cluster.update(new_member)
                            changed = True

            if len(cluster) >= 2:
                clusters.append(cluster)
                used_entities.update(cluster)

            if len(clusters) >= MAX_LEARNED_CONCEPTS:
                break

        # Step 5: Filter against static taxonomy
        static_member_sets: List[Set[str]] = [
            set(m.lower().strip() for m in members)
            for members in static_concepts.values()
        ]

        filtered_clusters: List[Set[str]] = []
        for cluster in clusters:
            # Check overlap with each static concept
            overlaps_too_much = False
            for static_set in static_member_sets:
                if not static_set:
                    continue
                overlap = len(cluster & static_set) / len(cluster)
                if overlap > OVERLAP_MERGE_THRESHOLD:
                    overlaps_too_much = True
                    break

            if not overlaps_too_much:
                filtered_clusters.append(cluster)

        # Step 6: Build named concepts (with semantic labeling)
        learned: Dict[str, List[str]] = {}
        for cluster in filtered_clusters[:MAX_LEARNED_CONCEPTS]:
            members_sorted = sorted(cluster)
            label = label_cluster(members_sorted)
            # Use semantic name if inferred, otherwise raw fallback
            name = label.name if label.is_inferred else f"learned:{'+'.join(members_sorted)}"
            learned[name] = members_sorted

        self._learned_concepts = learned

        logger.info(
            f"Discovered {len(learned)} concepts from "
            f"{len(clusters)} clusters ({len(clusters) - len(filtered_clusters)} "
            f"filtered by overlap)"
        )

        return dict(learned)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def learned_concepts(self) -> Dict[str, List[str]]:
        """Get currently learned concepts."""
        return dict(self._learned_concepts)

    @property
    def pair_count(self) -> int:
        """Number of tracked co-occurrence pairs."""
        return len(self._pairs)

    def get_pair_stats(self) -> List[Dict]:
        """Get co-occurrence pair statistics for debugging."""
        stats = []
        for pair_key, co in sorted(
            self._pairs.items(),
            key=lambda x: x[1].count,
            reverse=True,
        ):
            members = sorted(pair_key)
            rate = co.success_count / co.count if co.count > 0 else 0.0
            stats.append({
                "entities": members,
                "count": co.count,
                "success_rate": round(rate, 3),
                "last_seen": co.last_seen_attempt,
            })
        return stats

    # ------------------------------------------------------------------
    # Serialization (for persistence)
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict:
        """Serialize discovery state (for MemoryStore persistence)."""
        pairs_data = {}
        for pair_key, co in self._pairs.items():
            key_str = "|".join(sorted(pair_key))
            pairs_data[key_str] = {
                "count": co.count,
                "success_count": co.success_count,
                "last_seen_attempt": co.last_seen_attempt,
            }
        return {
            "pairs": pairs_data,
            "learned_concepts": self._learned_concepts,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ConceptDiscovery":
        """Deserialize discovery state from persisted dict."""
        instance = cls()
        if not data or not isinstance(data, dict):
            return instance

        # Load pairs
        for key_str, co_data in data.get("pairs", {}).items():
            members = key_str.split("|")
            if len(members) == 2:
                pair_key = frozenset(members)
                instance._pairs[pair_key] = CoOccurrence(
                    count=co_data.get("count", 0),
                    success_count=co_data.get("success_count", 0),
                    last_seen_attempt=co_data.get("last_seen_attempt", 0),
                )

        # Load learned concepts
        instance._learned_concepts = data.get("learned_concepts", {})

        logger.info(
            f"Loaded discovery state: {len(instance._pairs)} pairs, "
            f"{len(instance._learned_concepts)} learned concepts"
        )
        return instance
