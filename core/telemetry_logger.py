"""
Telemetry Logger: Lightweight JSONL event logging for pipeline observability.

Logs are appended to logs/telemetry.jsonl in JSON format.
Each line is a complete JSON object representing one pipeline execution.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from core.logger import get_logger

logger = get_logger("TELEMETRY")

# Default log file path (relative to project root)
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "telemetry.jsonl"


def log_event(data: Dict[str, Any], log_file: str = DEFAULT_LOG_FILE) -> None:
    """
    Append a telemetry event to the JSONL log file.

    Args:
        data: Dictionary containing telemetry data for the event.
              Will be enriched with 'query_id' and 'timestamp' if missing.
        log_file: Path to the log file (default: logs/telemetry.jsonl)

    The function creates the log directory and file if they don't exist.
    Logs are written atomically (one JSON object per line).
    """
    try:
        log_path = Path(log_file)

        # Ensure parent directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Enrich with required fields if missing
        event = data.copy()
        if not event.get("query_id"):
            event["query_id"] = _generate_query_id()
        if not event.get("timestamp"):
            event["timestamp"] = _iso_timestamp()

        # Attempt PostgreSQL logging
        try:
            from core.db.postgres_client import get_db_client
            db = get_db_client()
            
            # Format attributes
            query_id = event["query_id"]
            timestamp_str = event["timestamp"]
            
            # 1. Insert Queries
            db.execute_query(
                "INSERT INTO queries (id, query_text, timestamp) VALUES (%s, %s, %s)",
                (query_id, event.get("query"), timestamp_str)
            )
            
            # 2. Insert Metrics
            metrics = event.get("pipeline_metrics", {})
            outcome = event.get("final_outcome", {})
            db.execute_query(
                "INSERT INTO metrics (query_id, confidence, retry_count, hallucination_risk, verdict) VALUES (%s, %s, %s, %s, %s)",
                (query_id, outcome.get("confidence"), metrics.get("retry_count"), outcome.get("hallucination_risk"), outcome.get("verdict"))
            )
            
            # 3. Insert Strategies
            strategies = event.get("strategies_used", {})
            db.execute_query(
                "INSERT INTO strategies (query_id, rewrite_strategy, depth_k, routing) VALUES (%s, %s, %s, %s)",
                (query_id, strategies.get("rewrite"), strategies.get("depth_k"), strategies.get("routing"))
            )
            
            logger.debug(f"Telemetry saved to PostgreSQL: {query_id}")
            return  # Successfully logged to DB, skip JSONL
        except Exception as e:
            logger.warning(f"PostgreSQL logging failed ({e}), falling back to JSONL.")

        # Append as a single JSON line
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')

        logger.debug(f"Telemetry logged: {event['query_id']}")

    except Exception as e:
        logger.error(f"Failed to log telemetry: {e}")
        # Don't raise — telemetry failures shouldn't crash the pipeline


def _generate_query_id() -> str:
    """Generate a UUID valid string."""
    import uuid
    return str(uuid.uuid4())


def _iso_timestamp() -> str:
    """Generate ISO 8601 timestamp with Z suffix."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
