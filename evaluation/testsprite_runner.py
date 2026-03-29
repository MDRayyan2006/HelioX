"""
Testsprite Runner: End-to-end testing harness for pipeline evaluation.

Loads test cases, runs pipeline, evaluates, and diagnoses issues.
"""

import json
from typing import Dict, Any, List, Optional

from .runner import run_query
from .evaluator import evaluate
from .critic import format_diagnosis


# Default test cases if no file provided
DEFAULT_TEST_CASES = [
    {
        "name": "Basic RAG query",
        "query": "How does HelioX perform vector search using Qdrant?",
        "expected": {
            "min_results": 3,
            "keywords": ["vector", "search", "qdrant"],
            "entities": ["HelioX", "Qdrant"]
        }
    },
    {
        "name": "Sparse retrieval query",
        "query": "What is BM25 sparse retrieval optimization?",
        "expected": {
            "min_results": 3,
            "keywords": ["bm25", "sparse", "retrieval", "optimization"],
            "entities": ["BM25"]
        }
    },
    {
        "name": "Embedding model query",
        "query": "Which embedding model does HelioX use?",
        "expected": {
            "min_results": 3,
            "keywords": ["embedding", "model"],
            "entities": ["HelioX", "MiniLM"]
        }
    }
]


def load_test_cases(filepath: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Load test cases from JSON file or use defaults.

    JSON format:
    [
        {
            "name": "test name",
            "query": "the query string",
            "expected": {
                "min_results": 3,
                "keywords": ["keyword1", ...],
                "entities": ["entity1", ...]
            }
        }
    ]

    Args:
        filepath: Path to JSON test file (optional)

    Returns:
        List of test case dictionaries
    """
    if filepath:
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                print(f"[WARNING] Invalid JSON format in {filepath}, using defaults")
                return DEFAULT_TEST_CASES
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[WARNING] Failed to load {filepath}: {e}, using defaults")
            return DEFAULT_TEST_CASES
    else:
        return DEFAULT_TEST_CASES


def run_testsprite(
    test_cases: Optional[List[Dict[str, Any]]] = None,
    test_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run full evaluation loop over test cases.

    Process:
    1. Load test cases
    2. For each test:
       - Run pipeline
       - Evaluate result
       - Diagnose issues
    3. Aggregate summary

    Args:
        test_cases: Direct list of test cases (overrides test_file)
        test_file: Path to JSON test file

    Returns:
        Summary dict with pass/fail counts and per-test results
    """
    cases = test_cases or load_test_cases(test_file)

    results = []
    passed = 0
    failed = 0

    print("\n" + "="*80)
    print("TESTSPRITE EVALUATION RUN")
    print("="*80 + "\n")

    for idx, test in enumerate(cases, 1):
        name = test.get("name", f"Test {idx}")
        query = test["query"]
        expected = test.get("expected", {})

        print(f"[TEST] {idx}. {name}")
        print(f"[QUERY] \"{query}\"")

        # Step 1: Run pipeline
        result = run_query(query)

        # Step 2: Evaluate
        report = evaluate(result, expected)

        # Step 3: Diagnose
        diagnosis_lines = format_diagnosis(report)
        for line in diagnosis_lines.split("\n"):
            print(f"[CRITIC] {line}")

        # Track pass/fail
        if report["overall_pass"]:
            passed += 1
        else:
            failed += 1

        results.append({
            "name": name,
            "query": query,
            "report": report
        })

        print()  # blank line between tests

    # Summary
    total = len(cases)
    print("="*80)
    print(f"SUMMARY: {passed}/{total} passed, {failed}/{total} failed")
    print("="*80 + "\n")

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "results": results
    }


if __name__ == "__main__":
    # Run with default test cases
    summary = run_testsprite()

    # Exit with appropriate code
    exit(0 if summary["failed"] == 0 else 1)
