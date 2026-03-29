from core.telemetry_logger import log_event
import os

test_data = {
    "query": "Test postgres tracking",
    "pipeline_metrics": {
        "retry_count": 0
    },
    "final_outcome": {
        "confidence": 0.95,
        "hallucination_risk": 0.01,
        "verdict": "Valid"
    },
    "strategies_used": {
        "rewrite": "None",
        "depth_k": 3,
        "routing": "Standard"
    }
}
log_event(test_data)

logs_exist = os.path.exists("logs/telemetry.jsonl")
print(f"Log event tested! JSONL Fallback file exists: {logs_exist}")
