"""
Evaluator: Validates pipeline outputs against expected criteria.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


def evaluate(
    result: Dict[str, Any],
    expected: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluate pipeline execution result.

    Checks:
    - Pipeline success
    - Top 3 results exist
    - Scores in [0,1] range
    - Results sorted descending by final_score
    - Optional: keyword/entity correctness against expected

    Args:
        result: Output from run_query()
        expected: Optional dict with expected values:
            - min_results: int (default 3)
            - keywords: List[str] to check presence in chunks
            - entities: List[str] to check presence in chunks

    Returns:
        Evaluation report with pass/fail flags and messages
    """
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "query": result["query"],
        "success": result["success"],
        "checks": {},
        "overall_pass": False,
        "issues": []
    }

    # Check pipeline success
    if not result["success"]:
        report["issues"].append(f"Pipeline failed: {result['error']}")
        report["checks"]["pipeline_success"] = False
        report["error"] = result["error"]  # Include error for diagnosis
        return report

    report["checks"]["pipeline_success"] = True

    # Define expected parameters
    min_results = expected.get("min_results", 3) if expected else 3
    expected_keywords = expected.get("keywords", []) if expected else []
    expected_entities = expected.get("entities", []) if expected else []

    outputs = result["worker_outputs"]

    # Check 1: Minimum results count
    results_ok = len(outputs) >= min_results
    report["checks"]["min_results"] = {
        "pass": results_ok,
        "actual": len(outputs),
        "expected": min_results
    }
    if not results_ok:
        report["issues"].append(f"Only {len(outputs)} results, need at least {min_results}")

    # Check 2: Score validity and range
    score_valid = True
    for i, output in enumerate(outputs):
        confidence = output.get("confidence")
        if not isinstance(confidence, (int, float)):
            score_valid = False
            report["issues"].append(f"Result {i}: confidence not numeric")
        elif not (0 <= confidence <= 1):
            score_valid = False
            report["issues"].append(f"Result {i}: confidence {confidence} out of range [0,1]")

    report["checks"]["score_validity"] = {"pass": score_valid}

    # Check 3: Sorted descending
    sorted_ok = True
    for i in range(len(outputs) - 1):
        if outputs[i].get("confidence", 0) < outputs[i + 1].get("confidence", 0):
            sorted_ok = False
            report["issues"].append(
                f"Results not sorted: index {i} ({outputs[i]['confidence']}) < "
                f"index {i+1} ({outputs[i+1]['confidence']})"
            )

    report["checks"]["sorted_descending"] = {"pass": sorted_ok}

    # Check 4: Keyword presence (if expected keywords provided)
    if expected_keywords:
        keyword_matches = _check_keyword_presence(outputs, expected_keywords)
        keyword_ok = keyword_matches["all_present"]
        report["checks"]["keyword_presence"] = {
            "pass": keyword_ok,
            "matches": keyword_matches
        }
        if not keyword_ok:
            missing = keyword_matches["missing"]
            report["issues"].append(f"Missing keywords: {missing}")

    # Check 5: Entity presence (if expected entities provided)
    if expected_entities:
        entity_matches = _check_entity_presence(outputs, expected_entities)
        entity_ok = entity_matches["all_present"]
        report["checks"]["entity_presence"] = {
            "pass": entity_ok,
            "matches": entity_matches
        }
        if not entity_ok:
            missing = entity_matches["missing"]
            report["issues"].append(f"Missing entities: {missing}")

    # Determine overall pass
    all_checks = []
    for check in report["checks"].values():
        if isinstance(check, dict):
            all_checks.append(check.get("pass", True))
        else:
            all_checks.append(bool(check))
    report["overall_pass"] = all(all_checks) and len(report["issues"]) == 0

    return report


def _check_keyword_presence(
    outputs: List[Dict[str, Any]],
    keywords: List[str]
) -> Dict[str, Any]:
    """
    Check if expected keywords appear in any of the top result texts.

    Args:
        outputs: List of worker output dicts
        keywords: List of lowercase keywords to find

    Returns:
        Dict with found/missing lists and overall flag
    """
    found = []
    missing = []

    for keyword in keywords:
        kw_lower = keyword.lower()
        present = any(kw_lower in output.get("supporting_span", "").lower() for output in outputs)
        if present:
            found.append(keyword)
        else:
            missing.append(keyword)

    return {
        "found": found,
        "missing": missing,
        "all_present": len(missing) == 0
    }


def _check_entity_presence(
    outputs: List[Dict[str, Any]],
    entities: List[str]
) -> Dict[str, Any]:
    """
    Check if expected entities (case-sensitive-ish) appear in any of the top result texts.

    Args:
        outputs: List of worker output dicts
        entities: List of entity strings to find

    Returns:
        Dict with found/missing lists and overall flag
    """
    found = []
    missing = []

    for entity in entities:
        # Try both exact case and lower case match
        present = any(
            entity in output.get("supporting_span", "") or
            entity.lower() in output.get("supporting_span", "").lower()
            for output in outputs
        )
        if present:
            found.append(entity)
        else:
            missing.append(entity)

    return {
        "found": found,
        "missing": missing,
        "all_present": len(missing) == 0
    }
