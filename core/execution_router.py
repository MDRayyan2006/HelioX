"""
Execution Router: Intelligent routing between lightweight and multi-agent pipelines.

This module provides the main entry point for query processing, automatically
determining the appropriate execution mode based on query complexity analysis.

Architecture:
1. Complexity Analyzer: Analyzes query characteristics to estimate processing requirements
2. Execution Router: Routes to appropriate pipeline and returns standardized response
3. Both pipelines: Unified output format {answer, mode}

Author: HelioX Engineering Team
Version: 1.0.0
"""

import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from core.logger import get_logger
from services.query.analyzer import analyze_query
from services.retrieval.retriever import get_retriever
from services.retrieval.enhanced_retriever import get_enhanced_retriever
from services.retrieval.reranker import rerank
from services.retrieval.ranker import merge_rank
from agents.worker import process_chunks
from agents.adjudicator import adjudicate
from agents.answer_composer import compose_answer

# Multi-agent pipeline
from api.engine.pipeline import run_pipeline as run_multi_agent_pipeline

# ---------------------------------------------------------------------------
# Complexity Classification
# ---------------------------------------------------------------------------

@dataclass
class ComplexityMetrics:
    """Numeric metrics extracted from query for complexity scoring."""
    word_count: int = 0
    entity_count: int = 0
    keyword_count: int = 0
    constraint_count: int = 0
    query_type: str = "FACTUAL"
    has_multiple_entities: bool = False
    has_temporal_constraint: bool = False
    has_domain_constraint: bool = False
    has_filters: bool = False
    is_comparison_type: bool = False
    is_procedural_type: bool = False
    is_causal_type: bool = False
    has_list_intent: bool = False
    question_count: int = 0  # Number of question marks
    readability_score: float = 0.0  # Simple heuristic (avg word length)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/telemetry."""
        return {
            "word_count": self.word_count,
            "entity_count": self.entity_count,
            "keyword_count": self.keyword_count,
            "constraint_count": self.constraint_count,
            "query_type": self.query_type,
            "has_multiple_entities": self.has_multiple_entities,
            "has_temporal_constraint": self.has_temporal_constraint,
            "has_domain_constraint": self.has_domain_constraint,
            "has_filters": self.has_filters,
            "is_comparison_type": self.is_comparison_type,
            "is_procedural_type": self.is_procedural_type,
            "is_causal_type": self.is_causal_type,
            "has_list_intent": self.has_list_intent,
            "question_count": self.question_count,
            "readability_score": self.readability_score,
        }


class ComplexityAnalyzer:
    """
    Analyzes query complexity using rule-based scoring heuristics.

    Complexity factors considered:
    - Length metrics (word count, entities, keywords)
    - Query type (COMPARISON, CAUSAL, PROCEDURAL are more complex)
    - Constraints (temporal, domain, filters increase complexity)
    - Multiple entities (requires synthesis)
    - Question multiplicity (multiple questions)
    - Readability (longer words may indicate technical content)

    The analyzer is deterministic and does not use LLMs, ensuring
    consistent routing decisions.
    """

    # Thresholds for complexity scoring
    SIMPLE_MAX_WORDS = 15
    SIMPLE_MAX_ENTITIES = 2
    SIMPLE_MAX_KEYWORDS = 5
    SIMPLE_MAX_CONSTRAINTS = 0
    COMPLEX_MIN_SCORE = 4.5  # Minimum score to be considered COMPLEX

    # Query type weights (COMPLEXITY_SCORE_WEIGHTS)
    TYPE_WEIGHTS = {
        "LIST": 1.0,
        "FACTUAL": 1.0,
        "PROCEDURAL": 6.0,  # Procedural requires multi-step explanation
        "COMPARISON": 7.0,  # Comparison requires analyzing multiple items
        "CAUSAL": 7.0,      # Causal requires reasoning about relationships
    }

    # Feature weights (COMPLEXITY_SCORE_WEIGHTS)
    WEIGHT_WORD_COUNT = 0.3
    WEIGHT_ENTITY_COUNT = 1.5
    WEIGHT_KEYWORD_COUNT = 0.2
    WEIGHT_CONSTRAINT_COUNT = 1.0
    WEIGHT_MULTIPLE_ENTITIES = 2.0
    WEIGHT_TEMPORAL = 1.0
    WEIGHT_DOMAIN = 0.5
    WEIGHT_FILTERS = 0.5
    WEIGHT_MULTIPLE_QUESTIONS = 2.0
    WEIGHT_COMPARISON_CAUSAL = 1.5
    WEIGHT_PROCEDURAL = 1.0

    def analyze(self, raw_query: str, structured_query: Any) -> ComplexityMetrics:
        """
        Extract complexity metrics from query.

        Args:
            raw_query: Original user query string
            structured_query: StructuredQuery from analyzer

        Returns:
            ComplexityMetrics with all extracted features
        """
        words = raw_query.split()
        word_count = len(words)

        # Basic counts
        entity_count = len(structured_query.entities)
        keyword_count = len(structured_query.keywords)
        query_type = structured_query.query_type

        # Constraints analysis
        constraints = structured_query.constraints or {}
        constraint_keys = list(constraints.keys())
        constraint_count = len(constraint_keys)
        has_temporal = "temporal" in constraints
        has_domain = "domain" in constraints
        has_filters = "filters" in constraints and len(constraints["filters"]) > 0

        # Advanced features
        has_multiple_entities = entity_count > 1
        question_count = raw_query.count("?")
        has_list_intent = query_type == "LIST"
        is_comparison = query_type == "COMPARISON"
        is_causal = query_type == "CAUSAL"
        is_procedural = query_type == "PROCEDURAL"

        # Readability heuristic: average word length (longer words = more technical)
        avg_word_len = sum(len(w) for w in words) / max(word_count, 1)
        readability_score = avg_word_len

        metrics = ComplexityMetrics(
            word_count=word_count,
            entity_count=entity_count,
            keyword_count=keyword_count,
            constraint_count=constraint_count,
            query_type=query_type,
            has_multiple_entities=has_multiple_entities,
            has_temporal_constraint=has_temporal,
            has_domain_constraint=has_domain,
            has_filters=has_filters,
            is_comparison_type=is_comparison,
            is_procedural_type=is_procedural,
            is_causal_type=is_causal,
            has_list_intent=has_list_intent,
            question_count=question_count,
            readability_score=readability_score,
        )

        return metrics

    def calculate_complexity_score(self, metrics: ComplexityMetrics) -> float:
        """
        Calculate a weighted complexity score from metrics.

        Returns:
            float: Complexity score (higher = more complex)
        """
        score = 0.0

        # Word count contribution
        if metrics.word_count > self.SIMPLE_MAX_WORDS:
            excess_words = metrics.word_count - self.SIMPLE_MAX_WORDS
            score += excess_words * self.WEIGHT_WORD_COUNT

        # Entity count
        if metrics.entity_count > self.SIMPLE_MAX_ENTITIES:
            excess_entities = metrics.entity_count - self.SIMPLE_MAX_ENTITIES
            score += excess_entities * self.WEIGHT_ENTITY_COUNT
        else:
            # Small base penalty for having ANY entities (even simple ones have some)
            if metrics.entity_count > 0:
                score += 0.3  # Minimal presence penalty

        # Keyword count
        if metrics.keyword_count > self.SIMPLE_MAX_KEYWORDS:
            excess_keywords = metrics.keyword_count - self.SIMPLE_MAX_KEYWORDS
            score += excess_keywords * self.WEIGHT_KEYWORD_COUNT
        else:
            score += metrics.keyword_count * self.WEIGHT_KEYWORD_COUNT * 0.5

        # Constraints
        score += metrics.constraint_count * self.WEIGHT_CONSTRAINT_COUNT

        # Feature flags
        if metrics.has_multiple_entities:
            score += self.WEIGHT_MULTIPLE_ENTITIES
        if metrics.has_temporal_constraint:
            score += self.WEIGHT_TEMPORAL
        if metrics.has_domain_constraint:
            score += self.WEIGHT_DOMAIN
        if metrics.has_filters:
            score += self.WEIGHT_FILTERS
        if metrics.question_count > 1:
            score += self.WEIGHT_MULTIPLE_QUESTIONS

        # Query type weights
        type_weight = self.TYPE_WEIGHTS.get(metrics.query_type, 1.0)
        score += type_weight - 1.0  # Subtract baseline (FACTUAL=1.0)

        # Readability adjustment: technical content (longer avg words) adds slight complexity
        if metrics.readability_score > 6.0:
            score += (metrics.readability_score - 6.0) * 0.1

        return round(score, 3)

    def is_simple(self, metrics: ComplexityMetrics, score: float) -> bool:
        """
        Determine if query is SIMPLE based on metrics and score.

        A query is considered SIMPLE if:
        - Complexity score is below threshold, AND
        - Meets basic simplicity criteria (short, few entities, no constraints)
        """
        # Quick hard criteria (must satisfy)
        if metrics.word_count > self.SIMPLE_MAX_WORDS:
            return False
        if metrics.entity_count > self.SIMPLE_MAX_ENTITIES:
            return False
        if metrics.constraint_count > self.SIMPLE_MAX_CONSTRAINTS:
            return False
        if metrics.has_temporal_constraint:
            return False
        if metrics.is_comparison_type or metrics.is_causal_type:
            return False

        # Score-based decision
        return score < self.COMPLEX_MIN_SCORE


# ---------------------------------------------------------------------------
# Execution Router
# ---------------------------------------------------------------------------

logger = get_logger("EXECUTION_ROUTER")


class ExecutionRouter:
    """
    Routes queries to appropriate execution pipeline based on complexity.

    Modes:
    - LIGHTWEIGHT: Single-pass retrieval + answer composition (no retry loop)
    - MULTI_AGENT: Full multi-agent pipeline with adaptive strategies and retry logic

    The router performs:
    1. Query analysis (using structured analyzer)
    2. Complexity assessment (using ComplexityAnalyzer)
    3. Pipeline selection
    4. Execution and result formatting
    """

    def __init__(self):
        """Initialize router with complexity analyzer."""
        self.complexity_analyzer = ComplexityAnalyzer()
        logger.info("ExecutionRouter initialized")

    def route(self, raw_query: str) -> Dict[str, Any]:
        """
        Main entry point: Analyze query complexity and execute appropriate pipeline.

        Args:
            raw_query: User's query string

        Returns:
            Dict with:
                - answer: str (composed answer)
                - mode: "LIGHTWEIGHT" | "MULTI_AGENT"
                - confidence: float (optional, if available)
                - citations: List[Dict] (optional)
                - metrics: Dict (complexity metrics, score, timing)
        """
        start_time = time.perf_counter()
        logger.info(f"Routing query: {raw_query[:80]}...")

        # Step 1: Analyze query structure
        structured = analyze_query(raw_query)
        logger.info(
            f"Query analysis: type={structured.query_type}, "
            f"entities={len(structured.entities)}, keywords={len(structured.keywords)}"
        )

        # Step 2: Compute complexity metrics and score
        metrics = self.complexity_analyzer.analyze(raw_query, structured)
        complexity_score = self.complexity_analyzer.calculate_complexity_score(metrics)
        is_simple = self.complexity_analyzer.is_simple(metrics, complexity_score)

        logger.info(
            f"Complexity assessment: score={complexity_score:.3f}, "
            f"mode={'LIGHTWEIGHT' if is_simple else 'MULTI_AGENT'}"
        )

        # Step 3: Route and execute
        if is_simple:
            result = self._execute_lightweight(raw_query, structured)
            mode = "LIGHTWEIGHT"
        else:
            result = self._execute_multi_agent(raw_query)
            mode = "MULTI_AGENT"

        # Step 4: Standardize response format
        execution_time_ms = (time.perf_counter() - start_time) * 1000

        response = {
            "answer": result.get("answer", ""),
            "mode": mode,
            "confidence": result.get("confidence", 0.0),
            "citations": result.get("citations", []),
            "metrics": {
                "complexity_score": complexity_score,
                "execution_time_ms": round(execution_time_ms, 2),
                "query_analysis": metrics.to_dict(),
            }
        }

        logger.info(
            f"Query completed: mode={mode}, time={execution_time_ms:.1f}ms, "
            f"confidence={response['confidence']:.3f}"
        )
        logger.info(f"mode_used = {mode}")

        return response

    def _execute_lightweight(self, raw_query: str, structured: Any) -> Dict[str, Any]:
        """
        Execute lightweight pipeline: retrieval → workers → adjudication → answer.

        Single pass with minimal retrieval depth (top_k=3). Vector only.
        No retry loop, no critic, no adaptive strategies.

        Args:
            raw_query: User query
            structured: StructuredQuery from analyzer

        Returns:
            Dict with answer, confidence, citations
        """
        logger.info("Starting lightweight pipeline")

        # Stage 1: Retrieval (use enhanced retriever, vector only)
        retriever = get_enhanced_retriever()
        formatted_hits, _ = retriever.retrieve(structured, top_k=3, vector_only=True)  # Minimal depth, vector only

        # Stage 2: Skipping Ranking & Reranking for Lightweight pipeline
        top_chunks = formatted_hits[:3]

        logger.info(f"Lightweight retrieval: got {len(top_chunks)} chunks")

        # Stage 3: Worker processing
        worker_outputs = process_chunks(structured, top_chunks, parallel=False)
        logger.info(f"Lightweight workers: generated {len(worker_outputs)} outputs")

        # Stage 4: Adjudication
        adjudication = adjudicate(worker_outputs)
        logger.info(
            f"Lightweight adjudication: {len(adjudication.final_claims)} claims, "
            f"confidence={adjudication.confidence}"
        )

        # Stage 5: Answer composition (use lightweight model)
        composed = compose_answer(
            adjudication.dict(),
            structured.dict(),
            use_lightweight=True
        )

        return {
            "answer": composed["answer"],
            "confidence": composed["confidence"],
            "citations": composed["citations"],
        }

    def _execute_multi_agent(self, raw_query: str) -> Dict[str, Any]:
        """
        Execute full multi-agent adaptive pipeline.

        Uses the existing run_pipeline with use_agents=True.

        Args:
            raw_query: User query

        Returns:
            Dict with answer, confidence, citations, plus retry_trace
        """
        logger.info("Starting multi-agent pipeline")

        # Use existing multi-agent pipeline
        agent_output = run_multi_agent_pipeline(raw_query, use_agents=True)

        # Handle cached dict result
        if isinstance(agent_output, dict):
            return {
                "answer": agent_output.get("answer", ""),
                "confidence": agent_output.get("confidence", 0.0),
                "citations": agent_output.get("citations", []),
            }

        # Compute calibrated confidence from components (since AgentOutput doesn't store it directly)
        critique = agent_output.critique
        adjudication = agent_output.adjudication
        worker_outputs = agent_output.worker_outputs or []

        # Component confidences
        critic_conf = critique.confidence if critique else 0.0
        adj_conf = adjudication.confidence if adjudication else 0.0

        # Retrieval quality: average worker confidence
        if worker_outputs:
            retrieval_q = sum(w.confidence for w in worker_outputs) / len(worker_outputs)
        else:
            retrieval_q = 0.0

        # Agreement: average authority score from adjudication
        auth_scores = adjudication.authority_scores if adjudication and hasattr(adjudication, 'authority_scores') and adjudication.authority_scores else []
        agreement = sum(auth_scores) / len(auth_scores) if auth_scores else 0.0

        # Calibrated confidence (same formula as api_server)
        calibrated = round(
            0.25 * retrieval_q + 0.25 * adj_conf + 0.25 * critic_conf + 0.25 * agreement,
            4
        )

        # Extract results
        result = {
            "answer": agent_output.answer,
            "confidence": calibrated,
            "citations": agent_output.citations if hasattr(agent_output, 'citations') else [],
        }

        # Include retry trace if available
        if agent_output.retry_trace:
            result["retry_trace"] = {
                "total_attempts": agent_output.retry_trace.total_attempts,
                "improved": agent_output.retry_trace.improved,
                "confidence_delta": agent_output.retry_trace.confidence_delta,
                "best_attempt": agent_output.retry_trace.best_attempt,
            }

        return result


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def execute_query(query: str) -> Dict[str, Any]:
    """
    Convenience function: Execute query with automatic routing.

    Args:
        query: User query string

    Returns:
        Dict with answer, mode, confidence, citations, metrics
    """
    router = ExecutionRouter()
    return router.route(query)


def analyze_complexity(query: str) -> Dict[str, Any]:
    """
    Analyze query complexity without executing.

    Args:
        query: User query string

    Returns:
        Dict with complexity_score, is_simple, metrics
    """
    router = ExecutionRouter()
    structured = analyze_query(query)
    metrics = router.complexity_analyzer.analyze(query, structured)
    score = router.complexity_analyzer.calculate_complexity_score(metrics)
    is_simple = router.complexity_analyzer.is_simple(metrics, score)

    return {
        "complexity_score": score,
        "is_simple": is_simple,
        "mode": "LIGHTWEIGHT" if is_simple else "MULTI_AGENT",
        "metrics": metrics.to_dict(),
    }


# ---------------------------------------------------------------------------
# Testing / Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Demo queries
    test_queries = [
        "What is HelioX?",  # Simple factual
        "How does vector search work?",  # Procedural
        "Compare Qdrant and Elasticsearch",  # Complex comparison
        "What are the types of embeddings? List all of them",  # List
        "Why is retrieval important in RAG?",  # Causal
        "How does HelioX perform vector search using Qdrant with temporal constraints from 2024?",  # Complex
    ]

    print("="*80)
    print("EXECUTION ROUTER DEMO")
    print("="*80)

    router = ExecutionRouter()

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 80)

        # Analyze complexity
        analysis = analyze_complexity(query)
        print(f"Complexity Score: {analysis['complexity_score']:.3f}")
        print(f"Suggested Mode: {analysis['mode']}")
        print(f"Metrics: {analysis['metrics']}")

        # Execute (commented out to avoid full execution time)
        # result = router.route(query)
        # print(f"Answer: {result['answer'][:100]}...")
        # print(f"Executed in: {result['metrics']['execution_time_ms']:.1f}ms")

        print()
