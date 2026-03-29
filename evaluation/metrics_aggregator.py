"""
Metrics Aggregator: Compute statistics from telemetry logs.

Provides functions to calculate:
- Average confidence
- Retry rate
- Hallucination rate
- Per-strategy win rates
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict, Counter
from core.logger import get_logger

logger = get_logger("METRICS_AGG")


def load_logs(log_file: str = "logs/telemetry.jsonl") -> List[Dict[str, Any]]:
    """
    Load telemetry logs from JSONL file.

    Args:
        log_file: Path to the telemetry log file.

    Returns:
        List of telemetry event dictionaries. Returns empty list if file not found.
    """
    logs = []
    path = Path(log_file)
    if not path.exists():
        logger.warning(f"Telemetry log not found: {log_file}")
        return logs

    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    logs.append(event)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse log line: {e}")
                    continue
        logger.info(f"Loaded {len(logs)} telemetry events from {log_file}")
    except Exception as e:
        logger.error(f"Failed to read log file {log_file}: {e}")

    return logs


def compute_avg_confidence(logs: List[Dict[str, Any]], window: Optional[int] = None) -> float:
    """
    Compute average confidence from logs.

    Args:
        logs: List of telemetry events.
        window: Optional number of most recent events to consider (rolling window).
                If None, use all logs.

    Returns:
        Average confidence in [0,1], or 0.0 if no logs.
    """
    if not logs:
        return 0.0

    events = logs[-window:] if window else logs

    total = 0.0
    count = 0
    for event in events:
        outcome = event.get("final_outcome", {})
        conf = outcome.get("confidence")
        if conf is not None:
            total += float(conf)
            count += 1

    return round(total / count, 4) if count > 0 else 0.0


def compute_retry_rate(logs: List[Dict[str, Any]], window: Optional[int] = None) -> float:
    """
    Compute retry rate: fraction of queries that required at least one retry.

    Args:
        logs: List of telemetry events.
        window: Optional rolling window size.

    Returns:
        Retry rate as a float between 0 and 1.
    """
    if not logs:
        return 0.0

    events = logs[-window:] if window else logs

    retry_count = 0
    total = 0
    for event in events:
        metrics = event.get("pipeline_metrics", {})
        retries = metrics.get("retry_count")
        if retries is not None:
            total += 1
            if int(retries) > 0:
                retry_count += 1

    return round(retry_count / total, 4) if total > 0 else 0.0


def compute_avg_retries_per_query(logs: List[Dict[str, Any]], window: Optional[int] = None) -> float:
    """
    Compute average number of retries per query.

    Args:
        logs: List of telemetry events.
        window: Optional rolling window size.

    Returns:
        Average retries per query as float.
    """
    if not logs:
        return 0.0

    events = logs[-window:] if window else logs

    total_retries = 0
    count = 0
    for event in events:
        metrics = event.get("pipeline_metrics", {})
        retries = metrics.get("retry_count")
        if retries is not None:
            total_retries += int(retries)
            count += 1

    return round(total_retries / count, 4) if count > 0 else 0.0


def compute_hallucination_rate(logs: List[Dict[str, Any]], window: Optional[int] = None, threshold: float = 0.3) -> float:
    """
    Compute hallucination rate: fraction of queries with high hallucination risk.

    Args:
        logs: List of telemetry events.
        window: Optional rolling window size.
        threshold: Risk threshold above which counts as hallucination event (default 0.3).

    Returns:
        Hallucination rate as a float between 0 and 1.
    """
    if not logs:
        return 0.0

    events = logs[-window:] if window else logs

    hall_count = 0
    total = 0
    for event in events:
        outcome = event.get("final_outcome", {})
        risk = outcome.get("hallucination_risk")
        if risk is not None:
            total += 1
            if float(risk) >= threshold:
                hall_count += 1

    return round(hall_count / total, 4) if total > 0 else 0.0


def compute_strategy_win_rates(logs: List[Dict[str, Any]], strategy_domain: str = "rewrite") -> Dict[str, float]:
    """
    Compute win rate (PASS fraction) for each strategy value in a given domain.

    Args:
        logs: List of telemetry events.
        strategy_domain: Domain key in strategies_used (e.g., "rewrite", "depth", "routing").

    Returns:
        Dict mapping strategy key to win rate (0-1). Only includes strategies with at least 3 samples.
    """
    stats = defaultdict(lambda: {"passes": 0, "total": 0})

    for event in logs:
        strategies = event.get("strategies_used", {})
        strategy_val = strategies.get(strategy_domain)
        if not strategy_val:
            continue
        outcome = event.get("final_outcome", {})
        verdict = outcome.get("verdict", "").upper()
        stats[strategy_val]["total"] += 1
        if verdict == "PASS":
            stats[strategy_val]["passes"] += 1

    win_rates = {}
    for strategy, counts in stats.items():
        if counts["total"] >= 3:
            win_rates[strategy] = round(counts["passes"] / counts["total"], 4)

    return win_rates


# Alias for backward compatibility
compute_win_rate_by_rewrite = compute_strategy_win_rates


def get_summary_metrics(log_file: str = "logs/telemetry.jsonl", window: int = 100) -> Dict[str, Any]:
    """
    Compute a summary dashboard of key metrics.

    Args:
        log_file: Path to telemetry log.
        window: Rolling window size (default 100 most recent queries).

    Returns:
        Dictionary with summary metrics.
    """
    logs = load_logs(log_file)

    return {
        "total_queries": len(logs),
        "window": window,
        "avg_confidence": compute_avg_confidence(logs, window),
        "retry_rate": compute_retry_rate(logs, window),
        "avg_retries_per_query": compute_avg_retries_per_query(logs, window),
        "hallucination_rate": compute_hallucination_rate(logs, window),
        "rewrite_win_rates": compute_strategy_win_rates(logs, "rewrite"),
        "depth_win_rates": compute_strategy_win_rates(logs, "depth_k"),
    }
