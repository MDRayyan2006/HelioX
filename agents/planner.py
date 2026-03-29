"""
Planner Agent: Decomposes complex queries into sub-queries.

If the query is simple, returns a list with the original query.
If complex, splits heuristically on conjunctions like "and", "or", commas.
"""

from typing import List


def plan_query(raw_query: str) -> List[str]:
    """
    Decompose a query into sub-queries for parallel retrieval.

    Strategy:
        - If query is simple (few words, no complex conjunctions), return [query]
        - If complex, split on " and ", " or ", commas, etc.
        - Clean and deduplicate sub-queries
        - Ensure each sub-query is non-empty

    Args:
        raw_query: The user's original query string

    Returns:
        List of sub-query strings (at least one)
    """
    # Normalize whitespace
    query = raw_query.strip()

    # Simple query detection: short (< 10 words) and no complex conjunctions
    words = query.split()
    if len(words) < 10 and not any(conj in query.lower() for conj in [" and ", " or ", " with ", " using "]):
        return [query]

    # Heuristic splitting on conjunctions and punctuation
    # Replace conjunctions with a uniform delimiter
    normalized = query.replace(" and ", " | ").replace(" or ", " | ").replace(" with ", " | ")
    normalized = normalized.replace(" using ", " | ").replace(" via ", " | ")

    # Also split on commas if they appear between meaningful phrases
    # But be careful not to split in numbers or quoted strings
    parts = []
    for segment in normalized.split("|"):
        # Further split on commas (but limit to avoid excessive fragmentation)
        comma_parts = segment.split(",")
        # Only split on commas if the segment is reasonably long (> 15 chars)
        if len(segment.strip()) > 15:
            parts.extend(comma_parts)
        else:
            parts.append(segment)

    # Clean up each sub-query
    sub_queries = []
    for part in parts:
        cleaned = part.strip()
        # Remove any trailing/leading connectors that may have been left
        cleaned = cleaned.rstrip(" ,.;").lstrip(" ,.;")
        # Ensure minimum length and not just conjunctions
        if cleaned and len(cleaned.split()) >= 2:
            sub_queries.append(cleaned)

    # Deduplicate while preserving order
    seen = set()
    unique_queries = []
    for q in sub_queries:
        q_lower = q.lower()
        if q_lower not in seen:
            seen.add(q_lower)
            unique_queries.append(q)

    # If we ended up with no valid sub-queries, fall back to original
    if not unique_queries:
        return [query]

    return unique_queries
