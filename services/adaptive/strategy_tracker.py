"""
Strategy Performance Tracker: Meta-learning layer to score system strategies.

Tracks which query rewriting strategies, retrieval depths, and routing configs
work best across attempts. Uses Exponential Moving Average (EMA) to weight
recent outcomes more heavily.

Features:
- Best-first prioritization based on EMA score.
- Auto-disabling of weak strategies (score < threshold after N attempts).

Deterministic, with persistent storage via MemoryStore.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from core.logger import get_logger

logger = get_logger("STRATEGY_TRACKER")

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
EMA_ALPHA = 0.3               # weight of new outcome vs old score
INITIAL_SCORE = 0.5           # neutral starting score
DISABLE_THRESHOLD = 0.2       # strategies falling below this are ignored
MIN_ATTEMPTS_TO_DISABLE = 5   # require N attempts before disabling


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class StrategyRecord:
    """Tracks performance of a single strategy variant."""
    score: float = INITIAL_SCORE
    attempts: int = 0
    successes: int = 0
    last_confidence: float = 0.0


class StrategyTracker:
    """
    Maintains performance scores for different strategy domains.

    Domains:
    - rewrite: "context-aware", "intent-rephrase", "synonym-expand", "broadened"
    - depth: "k=2", "k=3", etc.
    - routing: "fb=True,bd=False", etc.
    """

    def __init__(self):
        # domain -> strategy_key -> record
        self._domains: Dict[str, Dict[str, StrategyRecord]] = {
            "rewrite": {},
            "depth": {},
            "routing": {},
        }
        # Ephemeral tracking for the current attempt
        self._current_strategies: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def record_strategy(self, domain: str, strategy_key: str) -> None:
        """
        Record that a strategy was used in the current attempt.

        Args:
            domain: The strategy domain ("rewrite", "depth", "routing").
            strategy_key: The specific choice made (e.g., "intent-rephrase").
        """
        if domain not in self._domains:
            self._domains[domain] = {}

        if strategy_key not in self._domains[domain]:
            self._domains[domain][strategy_key] = StrategyRecord()

        self._current_strategies[domain] = strategy_key
        logger.info(f"Recorded strategy use: {domain} = '{strategy_key}'")

    def record_outcome(self, confidence: float, is_success: bool) -> None:
        """
        Apply the outcome (confidence) to all strategies used in this attempt.

        Uses EMA scoring: new_score = alpha * outcome + (1 - alpha) * old_score.

        Args:
            confidence: Critic confidence from the attempt (0-1).
            is_success: Whether the attempt yielded a PASS verdict.
        """
        if not self._current_strategies:
            return

        updates = []
        for domain, key in self._current_strategies.items():
            rec = self._domains[domain][key]
            
            # EMA Update
            old_score = rec.score
            new_score = (EMA_ALPHA * confidence) + ((1.0 - EMA_ALPHA) * old_score)
            
            rec.score = round(new_score, 4)
            rec.attempts += 1
            if is_success:
                rec.successes += 1
            rec.last_confidence = confidence

            updates.append(f"{domain}:'{key}' ({old_score:.2f}→{rec.score:.2f})")

        logger.info(f"Updated strategy scores from outcome: {', '.join(updates)}")
        self._current_strategies.clear()

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_strategy_scores(self, domain: str) -> Dict[str, float]:
        """Get all scores for a domain."""
        if domain not in self._domains:
            return {}
        return {k: v.score for k, v in self._domains[domain].items()}

    def is_disabled(self, domain: str, strategy_key: str) -> bool:
        """
        Check if a strategy has performed so poorly it should be skipped.

        A strategy is disabled if it has been tried at least MIN_ATTEMPTS_TO_DISABLE
        times and its EMA score is below DISABLE_THRESHOLD.
        """
        if domain not in self._domains or strategy_key not in self._domains[domain]:
            return False
            
        rec = self._domains[domain][strategy_key]
        if rec.attempts >= MIN_ATTEMPTS_TO_DISABLE and rec.score < DISABLE_THRESHOLD:
            return True
        return False

    def get_best_strategy(self, domain: str) -> Optional[str]:
        """
        Get the highest-scoring strategy for a domain, ignoring disabled ones.
        Returns None if no strategies have been tracked for the domain.
        """
        if domain not in self._domains or not self._domains[domain]:
            return None

        valid_strategies = [
            (key, rec.score)
            for key, rec in self._domains[domain].items()
            if not self.is_disabled(domain, key)
        ]

        if not valid_strategies:
            return None

        # Sort by score descending
        valid_strategies.sort(key=lambda x: x[1], reverse=True)
        best_key, best_score = valid_strategies[0]
        
        # Only return if the score is actually better than neutral starting score
        if best_score > INITIAL_SCORE:
            logger.info(f"Selected best {domain} strategy: '{best_key}' (score={best_score:.2f})")
            return best_key
            
        return None

    # ------------------------------------------------------------------
    # Serialization (for MemoryStore persistence)
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict:
        """Serialize tracker state."""
        data = {}
        for domain, strategies in self._domains.items():
            data[domain] = {}
            for key, rec in strategies.items():
                data[domain][key] = {
                    "score": rec.score,
                    "attempts": rec.attempts,
                    "successes": rec.successes,
                    "last_confidence": rec.last_confidence,
                }
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "StrategyTracker":
        """Deserialize tracker state."""
        instance = cls()
        if not data or not isinstance(data, dict):
            return instance

        for domain, strategies_data in data.items():
            if domain not in instance._domains:
                instance._domains[domain] = {}
                
            for key, rec_data in strategies_data.items():
                instance._domains[domain][key] = StrategyRecord(
                    score=rec_data.get("score", INITIAL_SCORE),
                    attempts=rec_data.get("attempts", 0),
                    successes=rec_data.get("successes", 0),
                    last_confidence=rec_data.get("last_confidence", 0.0),
                )

        count = sum(len(d) for d in instance._domains.values())
        logger.info(f"Loaded strategy tracker state: {count} strategies across {len(data)} domains")
        return instance
