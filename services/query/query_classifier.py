import re
from typing import Dict, Union

class QueryComplexityClassifier:
    """
    Analyzes a query to route it to either a fast single-pass retriever 
    or a deep multi-agent reasoning pipeline.
    """
    
    # Linguistic markers that strongly imply complex reasoning
    REASONING_WORDS = {"why", "how", "explain", "analyze", "evaluate", "synthesize", "cause", "impact"}
    
    # Markers that imply multi-document traversal
    COMPARISON_WORDS = {"vs", "versus", "difference", "compare", "better", "pros", "cons", "similarities"}
    
    # Markers that imply bulk extraction operations
    LIST_WORDS = {"all", "list", "every", "multiple", "types", "examples"}
    
    def __init__(self, length_threshold: int = 15, entity_threshold: int = 3):
        self.length_threshold = length_threshold
        self.entity_threshold = entity_threshold

    def _extract_entities_mock(self, query: str) -> list:
        """Lightweight regex-based pseudo-entity extractor (capitalized words)"""
        return re.findall(r'\b[A-Z][a-z]+\b', query)

    def classify_heuristically(self, query: str) -> Dict[str, Union[str, float]]:
        """
        Fast execution: O(1) latency using keyword sets and heuristics.
        Returns the required schema: complexity (str), score (float), reason (str).
        """
        query_lower = query.lower()
        words = set(re.findall(r'\b\w+\b', query_lower))
        word_count = len(words)
        
        score_accumulator = 0.0
        reasons = []

        # Factor 1: Query Length
        if word_count > self.length_threshold:
            score_accumulator += 0.3
            reasons.append(f"Long query ({word_count} words)")

        # Factor 2: Entity Density
        entities = self._extract_entities_mock(query)
        if len(entities) >= self.entity_threshold:
            score_accumulator += 0.3
            reasons.append(f"High entity density ({len(entities)} entities)")

        # Factor 3: Intent Analysis
        if words.intersection(self.REASONING_WORDS):
            score_accumulator += 0.4
            reasons.append("Reasoning intent detected")
            
        if words.intersection(self.COMPARISON_WORDS):
            score_accumulator += 0.5
            reasons.append("Comparison intent detected")
            
        if words.intersection(self.LIST_WORDS):
            score_accumulator += 0.2
            reasons.append("List aggregation intent detected")
            
        if "and" in words and word_count > 8:
            score_accumulator += 0.2
            reasons.append("Multi-step conjunction detected")

        # Normalize score
        final_score = min(1.0, score_accumulator)
        
        # Threshold for COMPLEX vs SIMPLE (0.5 or above is complex)
        complexity = "COMPLEX" if final_score >= 0.5 else "SIMPLE"
        reason_str = " | ".join(reasons) if reasons else "Direct factoid query"

        return {
            "complexity": complexity,
            "score": round(final_score, 2),
            "reason": reason_str
        }
