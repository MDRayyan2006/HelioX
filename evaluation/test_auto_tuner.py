import os
import json
import tempfile
import pytest

from services.adaptive.auto_tuner import AutoTuner, TunedParameters

def _create_mock_telemetry(path: str, records: list):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def test_auto_tuner_nominal():
    path = tempfile.mktemp()
    records = [
        {"final_outcome": {"hallucination_risk": 0.0, "confidence": 0.7}, "pipeline_metrics": {"retry_count": 0}}
    ] * 50
    _create_mock_telemetry(path, records)

    try:
        tuner = AutoTuner(log_file=path, cache_file=path + "_cache.json")
        params = tuner.get_tuned_parameters()
        assert params.top_k == 3
        assert params.exploration_rate == 0.1
        assert params.chunk_score_weight == 0.1
        assert params.rerank_threshold == 0.0
    finally:
        os.remove(path)
        if os.path.exists(path + "_cache.json"):
            os.remove(path + "_cache.json")


def test_auto_tuner_hallucinating():
    path = tempfile.mktemp()
    # 20% hallucination rate
    records = [
        {"final_outcome": {"hallucination_risk": 0.5, "confidence": 0.7}, "pipeline_metrics": {"retry_count": 0}}
    ] * 10 + [
        {"final_outcome": {"hallucination_risk": 0.0, "confidence": 0.7}, "pipeline_metrics": {"retry_count": 0}}
    ] * 40
    _create_mock_telemetry(path, records)

    try:
        tuner = AutoTuner(log_file=path, cache_file=path + "_cache.json")
        params = tuner.get_tuned_parameters()
        assert params.top_k == 2  # Max(2, 3-1)
        assert params.exploration_rate == 0.05  # Max(0.0, 0.1 - 0.05)
        assert params.chunk_score_weight == 0.2  # Min(0.3, 0.1 + 0.1)
        assert params.rerank_threshold == 0.3
    finally:
        os.remove(path)
        if os.path.exists(path + "_cache.json"):
            os.remove(path + "_cache.json")


def test_auto_tuner_struggling():
    path = tempfile.mktemp()
    # 30% retry rate
    records = [
        {"final_outcome": {"hallucination_risk": 0.0, "confidence": 0.7}, "pipeline_metrics": {"retry_count": 1}}
    ] * 15 + [
        {"final_outcome": {"hallucination_risk": 0.0, "confidence": 0.7}, "pipeline_metrics": {"retry_count": 0}}
    ] * 35
    _create_mock_telemetry(path, records)

    try:
        tuner = AutoTuner(log_file=path, cache_file=path + "_cache.json")
        params = tuner.get_tuned_parameters()
        assert params.top_k == 4
        assert params.exploration_rate == 0.2
        assert params.chunk_score_weight == 0.05
    finally:
        os.remove(path)
        if os.path.exists(path + "_cache.json"):
            os.remove(path + "_cache.json")


def test_auto_tuner_cruising():
    path = tempfile.mktemp()
    # Avg confidence 0.9, Retries 0%
    records = [
        {"final_outcome": {"hallucination_risk": 0.0, "confidence": 0.9}, "pipeline_metrics": {"retry_count": 0}}
    ] * 50
    _create_mock_telemetry(path, records)

    try:
        tuner = AutoTuner(log_file=path, cache_file=path + "_cache.json")
        params = tuner.get_tuned_parameters()
        assert params.top_k == 2
        assert params.exploration_rate == 0.05
        assert params.chunk_score_weight == 0.15
        assert params.rerank_threshold == 0.1
    finally:
        os.remove(path)
        if os.path.exists(path + "_cache.json"):
            os.remove(path + "_cache.json")


if __name__ == "__main__":
    print("Testing Auto-Tuner Regimes...")
    test_auto_tuner_nominal()
    print("  [PASS] Nominal State")
    test_auto_tuner_hallucinating()
    print("  [PASS] Hallucination Mitigation")
    test_auto_tuner_struggling()
    print("  [PASS] Retry / Struggling Recovery")
    test_auto_tuner_cruising()
    print("  [PASS] Cruising Optimization")
    print("All Auto-Tuner tests passed!")
