"""
Auto-Tuner Meta-Learning Layer

Dynamically adjusts RAG pipeline parameters (top_k, exploration_rate,
chunk_score_weight, rerank_threshold) by analyzing rolling metrics from telemetry.
"""

import json
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from core.logger import get_logger

logger = get_logger("AUTO_TUNER")


@dataclass
class TunedParameters:
    top_k: int = 3
    exploration_rate: float = 0.1
    chunk_score_weight: float = 0.1
    rerank_threshold: float = 0.0


class AutoTuner:
    """Read telemetry and tune system parameters."""

    def __init__(
        self,
        log_file: str = "logs/telemetry.jsonl",
        window_size: int = 50,
        update_frequency: int = 10,
        cache_file: str = "logs/auto_tuner_state.json"
    ):
        self.log_file = log_file
        self.window_size = window_size
        self.update_frequency = update_frequency
        self.cache_file = cache_file

        # Current active base parameters (nominal state)
        self.base_top_k = 3
        self.base_exploration_rate = 0.1
        self.base_chunk_weight = 0.1
        self.base_rerank_threshold = 0.0

    def get_tuned_parameters(self) -> TunedParameters:
        """
        Get the current tuned parameters.
        Re-computes logic only if we hit the update_frequency threshold
        (inferred from the number of lines in the log).
        """
        # If no telemetry exists, return defaults
        if not os.path.exists(self.log_file):
            return self._get_default_params()

        # Load cached state if available
        cached_state = self._load_cache()
        
        # Determine total queries processed (cheap line count approximation)
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                total_queries = sum(1 for _ in f)
        except Exception:
            return self._get_default_params()

        # Check if we should update. If cached and not enough new queries, return cached.
        if cached_state and "last_update_count" in cached_state:
            last_count = cached_state["last_update_count"]
            if total_queries < last_count + self.update_frequency:
                return TunedParameters(
                    top_k=cached_state.get("top_k", self.base_top_k),
                    exploration_rate=cached_state.get("exploration_rate", self.base_exploration_rate),
                    chunk_score_weight=cached_state.get("chunk_score_weight", self.base_chunk_weight),
                    rerank_threshold=cached_state.get("rerank_threshold", self.base_rerank_threshold)
                )

        # Time to re-tune
        return self._compute_and_cache_parameters(total_queries)

    def _get_default_params(self) -> TunedParameters:
        return TunedParameters(
            top_k=self.base_top_k,
            exploration_rate=self.base_exploration_rate,
            chunk_score_weight=self.base_chunk_weight,
            rerank_threshold=self.base_rerank_threshold
        )

    def _compute_and_cache_parameters(self, total_queries: int) -> TunedParameters:
        """Calculate metrics from tail of log file and apply tuning rules."""
        records = self._read_tail(self.window_size)
        
        if not records:
            return self._get_default_params()

        # Calculate metrics
        hallucination_count = 0
        retry_count = 0
        conf_sum = 0.0
        
        for r in records:
            outcome = r.get("final_outcome", {})
            metrics = r.get("pipeline_metrics", {})
            
            if outcome.get("hallucination_risk", 0.0) > 0.3:
                hallucination_count += 1
            if metrics.get("retry_count", 0) > 0:
                retry_count += 1
            conf_sum += outcome.get("confidence", 0.0)

        n = len(records)
        halluc_rate = hallucination_count / n
        retry_rate = retry_count / n
        avg_conf = conf_sum / n

        # Calculate negative feedback rate
        feedback_records = self._read_feedback_tail(self.window_size)
        neg_feedback = sum(1 for f in feedback_records if f.get("score", 0) == -1)
        neg_feedback_rate = neg_feedback / max(1, len(feedback_records))

        logger.info(
            f"Tuner metrics ({n} queries): Halluc={halluc_rate:.2f}, "
            f"Retries={retry_rate:.2f}, AvgConf={avg_conf:.2f}, "
            f"NegFeed={neg_feedback_rate:.2f}"
        )

        params = self._apply_rules(halluc_rate, retry_rate, avg_conf, neg_feedback_rate)

        # Cache it
        self._save_cache({
            "last_update_count": total_queries,
            "top_k": params.top_k,
            "exploration_rate": params.exploration_rate,
            "chunk_score_weight": params.chunk_score_weight,
            "rerank_threshold": params.rerank_threshold
        })

        return params

    def _apply_rules(self, halluc_rate: float, retry_rate: float, avg_conf: float, neg_feedback_rate: float = 0.0) -> TunedParameters:
        """Rule engine mapping signals to parameter shifts."""
        top_k = self.base_top_k
        exp_rate = self.base_exploration_rate
        chunk_wt = self.base_chunk_weight
        rerank_th = self.base_rerank_threshold

        # Rule 0: High Negative User Feedback (Overrides logic directly to broaden search)
        if neg_feedback_rate > 0.20:
            logger.info("Tuner Regime: USER_DISSATISFIED -> Broadening Search / Increasing Quality")
            top_k = min(5, top_k + 2)
            exp_rate = min(0.4, exp_rate + 0.15)
            chunk_wt = max(0.0, chunk_wt - 0.05)
            rerank_th = 0.0
            return TunedParameters(top_k, exp_rate, chunk_wt, rerank_th)

        # Rule 1: High Hallucination Rate (Safety First)
        if halluc_rate > 0.15:
            logger.info("Tuner Regime: HALLUCINATING -> Maximizing Safety")
            top_k = max(2, top_k - 1)
            exp_rate = max(0.0, exp_rate - 0.05)
            chunk_wt = min(0.3, chunk_wt + 0.1)
            rerank_th = 0.3
            return TunedParameters(top_k, exp_rate, chunk_wt, rerank_th)

        # Rule 2: High Retry Rate (Maximize Recall)
        if retry_rate > 0.25:
            logger.info("Tuner Regime: STRUGGLING -> Broadening Search")
            top_k = min(5, top_k + 1)
            exp_rate = min(0.3, exp_rate + 0.1)
            chunk_wt = max(0.0, chunk_wt - 0.05)
            rerank_th = 0.0
            return TunedParameters(top_k, exp_rate, chunk_wt, rerank_th)

        # Rule 3: High Confidence (Optimize Compute)
        if avg_conf > 0.85 and retry_rate < 0.10:
            logger.info("Tuner Regime: CRUISING -> Optimizing Compute")
            top_k = max(2, top_k - 1)
            exp_rate = 0.05
            chunk_wt = 0.15
            rerank_th = 0.1
            return TunedParameters(top_k, exp_rate, chunk_wt, rerank_th)

        logger.debug("Tuner Regime: NOMINAL")
        return TunedParameters(top_k, exp_rate, chunk_wt, rerank_th)

    def _read_tail(self, n: int) -> List[Dict[str, Any]]:
        """Read the last N JSONL records from the log safely."""
        try:
            # We'll use a simple readlines approach since files aren't massive yet.
            # O(M) where M is lines in file, but bounded by size limits in a real system.
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            tail_lines = lines[-n:]
            records = []
            for line in tail_lines:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return records
        except Exception as e:
            logger.error(f"Error reading telemetry: {e}")
            return []

    def _read_feedback_tail(self, n: int) -> List[Dict[str, Any]]:
        """Read the last N JSONL records from the feedback log safely."""
        feedback_file = "logs/feedback.jsonl"
        if not os.path.exists(feedback_file):
            return []
        try:
            with open(feedback_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            tail_lines = lines[-n:]
            records = []
            for line in tail_lines:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return records
        except Exception as e:
            logger.error(f"Error reading feedback telemetry: {e}")
            return []

    def _load_cache(self) -> Optional[Dict[str, Any]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _save_cache(self, data: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save tuner cache: {e}")
