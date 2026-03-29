#!/usr/bin/env python3
"""
Dashboard CLI: Display telemetry metrics in the terminal.

Shows:
- Rolling average confidence, retry rate, hallucination rate
- Recent query log
- Simple alerts based on thresholds
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import get_logger
from evaluation.metrics_aggregator import (
    load_logs,
    compute_avg_confidence,
    compute_retry_rate,
    compute_avg_retries_per_query,
    compute_hallucination_rate,
    get_summary_metrics,
)

logger = get_logger("DASHBOARD")

# Configuration
DEFAULT_WINDOW = 100
ALERT_CONFIDENCE_THRESHOLD = 0.6
ALERT_HALLUCINATION_THRESHOLD = 0.3
MAX_RECENT_QUERIES = 5


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to HH:MM:SS."""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%H:%M:%S")
    except Exception:
        return ts[:19]


def print_header(text: str, char: str = "=") -> None:
    """Print a section header."""
    print(f"\n{char * 60}")
    print(text)
    print(f"{char * 60}")


def print_metrics(metrics: dict) -> None:
    """Print key metrics with simple trend arrows (no trend data stored)."""
    avg_conf = metrics["avg_confidence"]
    retry_rate = metrics["retry_rate"]
    hall_rate = metrics["hallucination_rate"]

    print(f"\nAverage confidence: {avg_conf:.3f}")
    if avg_conf < ALERT_CONFIDENCE_THRESHOLD:
        print("  [WARN]  WARNING: Below confidence threshold!")
    else:
        print("  [OK] Confidence healthy")

    print(f"Retry rate: {retry_rate * 100:.1f}%")
    print(f"  Avg retries per query: {metrics['avg_retries_per_query']:.2f}")

    print(f"Hallucination rate: {hall_rate * 100:.1f}%")
    if hall_rate >= ALERT_HALLUCINATION_THRESHOLD:
        print("  [ALERT] ALERT: High hallucination rate!")
    else:
        print("  [OK] Hallucination rate within limits")


def print_recent_queries(log_file: str, limit: int = 5) -> None:
    """Print a table of recent queries."""
    logs = load_logs(log_file)
    recent = logs[-limit:] if len(logs) > limit else logs
    recent.reverse()  # most recent last for readability

    if not recent:
        print("\nNo queries logged yet.")
        return

    print_header("Recent Queries (most recent first)", char="-")
    print(f"{'Time':<10} | {'Query':<40} | {'Retries':<6} | {'Verdict':<6} | {'Conf':<5} | {'Hall':<5}")
    print("-" * 90)

    for event in recent:
        ts = format_timestamp(event.get("timestamp", ""))
        query = event.get("query", "")[:37] + ("..." if len(event.get("query", "")) > 37 else "")
        metrics = event.get("pipeline_metrics", {})
        retries = metrics.get("retry_count", 0)
        outcome = event.get("final_outcome", {})
        verdict = outcome.get("verdict", "?")[:6]
        conf = f"{outcome.get('confidence', 0):.2f}"
        hall = f"{outcome.get('hallucination_risk', 0):.2f}"
        print(f"{ts:<10} | {query:<40} | {retries:<6} | {verdict:<6} | {conf:<5} | {hall:<5}")


def print_summary(metrics: dict) -> None:
    """Print high-level summary."""
    print_header("HELIOX TELEMETRY DASHBOARD")
    print(f"Total queries recorded: {metrics['total_queries']}")
    print(f"Analyzing window: last {metrics['window']} queries")

    print_metrics(metrics)


def main():
    """Main entry point."""
    log_file = "logs/telemetry.jsonl"

    # Check log file exists
    if not Path(log_file).exists():
        print(f"[WARN]  No telemetry log found at {log_file}")
        print("The pipeline may not have run yet, or telemetry is disabled.")
        sys.exit(1)

    # Load and compute metrics
    logs = load_logs(log_file)
    metrics = get_summary_metrics(log_file, window=DEFAULT_WINDOW)

    # Display
    print_summary(metrics)
    print_recent_queries(log_file, limit=MAX_RECENT_QUERIES)

    # Exit code: 0 if no alerts, 1 if warnings/alerts present
    alerts_present = False
    if metrics["avg_confidence"] < ALERT_CONFIDENCE_THRESHOLD:
        alerts_present = True
    if metrics["hallucination_rate"] >= ALERT_HALLUCINATION_THRESHOLD:
        alerts_present = True

    sys.exit(1 if alerts_present else 0)


if __name__ == "__main__":
    main()
