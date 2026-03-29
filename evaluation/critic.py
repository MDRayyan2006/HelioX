"""
Critic: Generates human-readable diagnosis from evaluation reports.
"""

from typing import Dict, Any, List


def diagnose(evaluation_report: Dict[str, Any]) -> List[str]:
    """
    Generate human-readable issue diagnoses from evaluation report.

    Args:
        evaluation_report: Output from evaluator.evaluate()

    Returns:
        List of diagnostic message strings
    """
    messages = []

    if evaluation_report["overall_pass"]:
        messages.append("[PASS] All checks passed")
        return messages

    checks = evaluation_report["checks"]

    # Pipeline failed
    if not checks.get("pipeline_success", True):
        messages.append(f"[FAIL] Pipeline execution failed: {evaluation_report.get('error', 'Unknown error')}")
        return messages  # Can't do other checks if pipeline failed

    messages.append(f"[DIAGNOSE] Query: {evaluation_report['query']}")

    # Check each failure
    for check_name, check_data in checks.items():
        # Skip pipeline_success (already handled) and check if it's a dict
        if check_name == "pipeline_success":
            continue
        if isinstance(check_data, dict) and not check_data.get("pass", True):
            _diagnose_check(messages, check_name, check_data)

    # Summary
    issues = evaluation_report["issues"]
    if issues:
        messages.append(f"\n[SUMMARY] {len(issues)} issue(s) detected:")
        for i, issue in enumerate(issues, 1):
            messages.append(f"  {i}. {issue}")
    else:
        messages.append("\n[SUMMARY] No specific issues detected beyond failed checks")

    return messages


def _diagnose_check(messages: List[str], check_name: str, check_data: Dict[str, Any]) -> None:
    """Generate diagnostic for a specific failed check."""
    if check_name == "min_results":
        actual = check_data["actual"]
        expected = check_data["expected"]
        messages.append(f"[FAIL] Insufficient results: got {actual}, expected ≥{expected}")

    elif check_name == "score_validity":
        messages.append("[FAIL] Score validation failed: see issues list for details")

    elif check_name == "sorted_descending":
        messages.append("[FAIL] Results not in descending order by score")

    elif check_name == "keyword_presence":
        missing = check_data["matches"]["missing"]
        found = check_data["matches"]["found"]
        messages.append(f"[FAIL] Missing keywords: {missing}")
        messages.append(f"       Found keywords: {found}")

    elif check_name == "entity_presence":
        missing = check_data["matches"]["missing"]
        found = check_data["matches"]["found"]
        messages.append(f"[FAIL] Missing entities: {missing}")
        messages.append(f"       Found entities: {found}")


def format_diagnosis(evaluation_report: Dict[str, Any]) -> str:
    """
    Format evaluation report as a readable diagnostic string.

    Args:
        evaluation_report: Output from evaluator.evaluate()

    Returns:
        Formatted multi-line string
    """
    lines = diagnose(evaluation_report)
    return "\n".join(lines)
