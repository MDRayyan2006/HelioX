"""
Memory Store: Persistent storage for session memory learning.

Provides JSON-based persistence for entity and chunk performance scores.
Handles file corruption gracefully and limits storage size.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any
from core.logger import get_logger

logger = get_logger("MEMORY_STORE")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_ENTITIES = 1000           # Limit stored entities to top performers
MAX_CHUNKS = 1000             # Limit stored chunks to top performers
MAX_CONCEPTS = 200            # Limit stored concepts
STORAGE_FILE = "memory_store.json"


# ---------------------------------------------------------------------------
# Data Schemas
# ---------------------------------------------------------------------------
def serialize_entity_record(score: float, appearances: int, last_confidence: float) -> Dict[str, Any]:
    """Serialize entity record to JSON-serializable dict."""
    return {
        "score": round(score, 6),
        "appearances": appearances,
        "last_confidence": round(last_confidence, 6)
    }


def serialize_chunk_record(score: float, appearances: int, last_confidence: float, last_verdict: str) -> Dict[str, Any]:
    """Serialize chunk record to JSON-serializable dict."""
    return {
        "score": round(score, 6),
        "appearances": appearances,
        "last_confidence": round(last_confidence, 6),
        "last_verdict": last_verdict
    }


# ---------------------------------------------------------------------------
# Storage Manager
# ---------------------------------------------------------------------------
class MemoryStore:
    """
    Persistent storage for learned entity and chunk scores.

    Features:
      - Load from JSON on startup (graceful handling of corruption)
      - Save on updates (atomic write)
      - Size limits (top N by score)
      - Deterministic serialization
    """

    def __init__(self, storage_path: str = STORAGE_FILE):
        self.storage_path = Path(storage_path)
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._chunks: Dict[str, Dict[str, Any]] = {}
        self._concepts: Dict[str, Dict[str, Any]] = {}
        self._discovery: Dict[str, Any] = {}
        self._strategy_tracker: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """
        Load persisted memory from disk.

        Handles corruption gracefully: if file is missing or corrupted,
        starts with empty state and creates a fresh file on first save.
        """
        if self._loaded:
            return

        try:
            if not self.storage_path.exists():
                logger.info(f"Storage file not found: {self.storage_path} — starting with empty memory")
                self._entities = {}
                self._chunks = {}
                self._concepts = {}
                self._discovery = {}
                self._strategy_tracker = {}
                self._loaded = True
                return

            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate structure
            if not isinstance(data, dict):
                raise ValueError("Root must be a dict")

            raw_entities = data.get("entities", {})
            raw_chunks = data.get("chunks", {})
            raw_concepts = data.get("concepts", {})

            if not isinstance(raw_entities, dict) or not isinstance(raw_chunks, dict):
                raise ValueError("Entities and chunks must be dicts")

            self._entities = raw_entities
            self._chunks = raw_chunks
            self._concepts = raw_concepts if isinstance(raw_concepts, dict) else {}
            self._discovery = data.get("discovery", {})
            if not isinstance(self._discovery, dict):
                self._discovery = {}
            self._strategy_tracker = data.get("strategy_tracker", {})
            if not isinstance(self._strategy_tracker, dict):
                self._strategy_tracker = {}

            logger.info(
                f"Loaded memory: {len(self._entities)} entities, "
                f"{len(self._chunks)} chunks, {len(self._concepts)} concepts"
            )

        except json.JSONDecodeError as e:
            logger.error(f"Corrupted JSON in {self.storage_path}: {e} — starting with empty memory")
            self._entities = {}
            self._chunks = {}
            self._concepts = {}
            self._discovery = {}
            self._strategy_tracker = {}
        except Exception as e:
            logger.error(f"Failed to load memory from {self.storage_path}: {e} — starting with empty memory")
            self._entities = {}
            self._chunks = {}
            self._concepts = {}
            self._discovery = {}
            self._strategy_tracker = {}

        self._loaded = True

    def save(self) -> None:
        """Persist current memory state to disk (atomic write)."""
        try:
            # Enforce size limits before saving
            self._enforce_limits()

            # Prepare serializable data
            data = {
                "entities": self._entities,
                "chunks": self._chunks,
                "concepts": self._concepts,
                "discovery": self._discovery,
                "strategy_tracker": self._strategy_tracker,
            }

            # Atomic write: write to temp file, then rename
            temp_path = self.storage_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            temp_path.replace(self.storage_path)

            logger.info(
                f"Saved memory: {len(self._entities)} entities, "
                f"{len(self._chunks)} chunks, {len(self._concepts)} concepts"
            )

        except Exception as e:
            logger.error(f"Failed to save memory to {self.storage_path}: {e}")
            # Don't raise — persistence failures shouldn't crash the system

    def _enforce_limits(self) -> None:
        """
        Enforce storage size limits by keeping top N entries.

        For entities: keep top MAX_ENTITIES by score (descending)
        For chunks: keep top MAX_CHUNKS by score (descending)
        """
        if len(self._entities) > MAX_ENTITIES:
            # Sort by score descending, keep top MAX_ENTITIES
            sorted_entities = sorted(
                self._entities.items(),
                key=lambda item: item[1].get("score", 0.0),
                reverse=True
            )
            self._entities = dict(sorted_entities[:MAX_ENTITIES])
            logger.info(f"Trimmed entities to top {MAX_ENTITIES}")

        if len(self._chunks) > MAX_CHUNKS:
            # Sort by score descending, keep top MAX_CHUNKS
            sorted_chunks = sorted(
                self._chunks.items(),
                key=lambda item: item[1].get("score", 0.0),
                reverse=True
            )
            self._chunks = dict(sorted_chunks[:MAX_CHUNKS])
            logger.info(f"Trimmed chunks to top {MAX_CHUNKS}")

        if len(self._concepts) > MAX_CONCEPTS:
            sorted_concepts = sorted(
                self._concepts.items(),
                key=lambda item: abs(item[1].get("score", 0.0)),
                reverse=True
            )
            self._concepts = dict(sorted_concepts[:MAX_CONCEPTS])
            logger.info(f"Trimmed concepts to top {MAX_CONCEPTS}")

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_entity_scores(self) -> Dict[str, float]:
        """Get all entity scores."""
        return {
            entity: round(rec["score"], 6)
            for entity, rec in self._entities.items()
        }

    def get_chunk_scores(self) -> Dict[str, float]:
        """Get all chunk scores."""
        return {
            chunk_id: round(rec["score"], 6)
            for chunk_id, rec in self._chunks.items()
        }

    def get_entity_appearances(self) -> Dict[str, int]:
        """Get entity appearance counts."""
        return {
            entity: rec["appearances"]
            for entity, rec in self._entities.items()
        }

    def get_chunk_appearances(self) -> Dict[str, int]:
        """Get chunk appearance counts."""
        return {
            chunk_id: rec["appearances"]
            for chunk_id, rec in self._chunks.items()
        }

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def update_entity(
        self,
        entity_name: str,
        score_delta: float,
        confidence: float,
        clamp_min: float = -1.0,
        clamp_max: float = 1.0
    ) -> None:
        """
        Update an entity's score with delta.

        Creates record if it doesn't exist. Increments appearance count.
        Score is clamped to [clamp_min, clamp_max].
        """
        key = entity_name.lower().strip()
        if not key:
            return

        if key not in self._entities:
            self._entities[key] = {
                "score": 0.0,
                "appearances": 0,
                "last_confidence": 0.0
            }

        rec = self._entities[key]
        rec["score"] = max(clamp_min, min(clamp_max, rec["score"] + score_delta))
        rec["appearances"] += 1
        rec["last_confidence"] = confidence

    def update_chunk(
        self,
        chunk_id: str,
        score_delta: float,
        confidence: float,
        verdict: str,
        clamp_min: float = -1.0,
        clamp_max: float = 1.0
    ) -> None:
        """
        Update a chunk's score with delta.

        Creates record if it doesn't exist. Increments appearance count.
        Score is clamped to [clamp_min, clamp_max].
        """
        if not chunk_id:
            return

        if chunk_id not in self._chunks:
            self._chunks[chunk_id] = {
                "score": 0.0,
                "appearances": 0,
                "last_confidence": 0.0,
                "last_verdict": ""
            }

        rec = self._chunks[chunk_id]
        rec["score"] = max(clamp_min, min(clamp_max, rec["score"] + score_delta))
        rec["appearances"] += 1
        rec["last_confidence"] = confidence
        rec["last_verdict"] = verdict

    def clear(self) -> None:
        """Clear all stored memory (for testing/reset)."""
        self._entities.clear()
        self._chunks.clear()
        self._concepts.clear()
        logger.info("Cleared all memory")

    # ------------------------------------------------------------------
    # Concept storage
    # ------------------------------------------------------------------

    def update_concept(
        self,
        concept_name: str,
        score_delta: float,
        member_count: int = 1,
        clamp_min: float = -0.5,
        clamp_max: float = 0.5,
    ) -> None:
        """
        Update a concept's score with damped delta.

        Creates record if it doesn't exist.
        Score is clamped to [clamp_min, clamp_max] (tighter than entities).
        """
        key = concept_name.lower().strip()
        if not key:
            return

        if key not in self._concepts:
            self._concepts[key] = {
                "score": 0.0,
                "update_count": 0,
                "member_count": member_count,
            }

        rec = self._concepts[key]
        rec["score"] = max(clamp_min, min(clamp_max, rec["score"] + score_delta))
        rec["update_count"] = rec.get("update_count", 0) + 1
        rec["member_count"] = member_count

    def get_concept_scores(self) -> Dict[str, float]:
        """Get all concept scores."""
        return {
            concept: round(rec["score"], 6)
            for concept, rec in self._concepts.items()
        }
