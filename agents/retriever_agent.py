"""
Retriever Agent: Wraps routing, ranking, and reranking pipeline.

Accepts a query (or list of sub-queries), executes retrieval + ranking + reranking,
and returns top-k relevant chunks.

Phase 4A: Uses StructuredQueryAnalyzer and RoutingEngine.
"""

from typing import List, Dict, Any, Union, Optional
from core.logger import get_logger

from services.query.structured_analyzer import analyze_query, analyze_query as analyze_query_enhanced
from services.retrieval.router import get_router
from services.retrieval.ranker import merge_rank
from services.retrieval.reranker import rerank
from services.retrieval.enhanced_retriever import get_enhanced_retriever, EnhancedRetriever


def retrieve(
    query: Union[str, List[str]],
    top_k: int = 3,
    retrieval_top_k: int = 50,
    chunk_scores: Optional[Dict[str, float]] = None,
    chunk_score_weight: float = 0.1,
    rerank_threshold: float = 0.0,
    use_enhanced: bool = False,
) -> List[Dict[str, Any]]:
    """
    Execute retrieval pipeline for one or multiple queries.

    For multiple sub-queries:
        1. Run retrieval+ranking for each sub-query independently
        2. Merge all results (deduplicate by chunk_id)
        3. Take top N from merged list
        4. Rerank using the ORIGINAL full query (first in list if multiple)

    Phase 4A: Uses StructuredQueryAnalyzer and RoutingEngine.
    Optionally uses enhanced retriever for improved context understanding.

    Args:
        query: Original query string, or list of sub-queries from planner
        top_k: Number of final chunks to return after reranking
        retrieval_top_k: Number of candidates to retrieve per sub-query (before merge)
        use_enhanced: If True, use enhanced retriever with semantic understanding

    Returns:
        List of top-k chunk dictionaries with final scores, sorted by relevance
    """
    logger = get_logger("RETRIEVER_AGENT")

    # Use enhanced retriever if requested
    if use_enhanced:
        enhanced_retriever = get_enhanced_retriever()
        logger.info("Using enhanced retriever with semantic understanding")

        # Normalize to list
        if isinstance(query, str):
            queries = [query]
        else:
            queries = list(query)

        # Use original query for reranking (first query)
        original_query = queries[0]

        logger.info(f"Enhanced Retriever Agent processing {len(queries)} query(ies)")
        logger.info(f"Original query for reranking: {original_query[:50]}...")

        # Collect all ranked results from each sub-query
        all_ranked_results: List[Dict[str, Any]] = []

        for i, q in enumerate(queries):
            logger.info(f"Processing sub-query {i+1}/{len(queries)}: {q[:50]}...")

            # Analyze query with enhanced analyzer (semantic understanding)
            structured_query = analyze_query_enhanced(q)
            logger.info(f"Enhanced analysis: intent={structured_query.intent}, "
                        f"entities={structured_query.entities}, "
                        f"constraints keys={list(getattr(structured_query, 'constraints', {}).keys())}")

            # Retrieve with enhanced retriever — returns ALREADY merged+scored results
            # (vector + elastic + entity + metadata scores are combined inside enhanced_retriever)
            merged_results, vector_hits = enhanced_retriever.retrieve(
                structured_query,
                top_k=retrieval_top_k
            )
            logger.info(f"Enhanced retrieval: {len(merged_results)} merged results, {len(vector_hits)} vector hits")

            # Skip merge_rank — enhanced_retriever already produces final scores
            # Only apply diversity ranking (coverage-based MMR) to reduce redundancy
            from services.retrieval.ranker import apply_coverage_ranking
            ranked = apply_coverage_ranking(merged_results)
            logger.info(f"Diversity-ranked {len(ranked)} results for sub-query {i+1}")

            all_ranked_results.extend(ranked)

        if not all_ranked_results:
            logger.warning("No retrieval results from any sub-query")
            return []

        # Deduplicate by chunk_id, keeping highest scored version
        logger.info(f"Total results before deduplication: {len(all_ranked_results)}")
        best_by_chunk: Dict[str, Dict[str, Any]] = {}
        for chunk in all_ranked_results:
            chunk_id = chunk['chunk_id']
            if chunk_id not in best_by_chunk or chunk['final_score'] > best_by_chunk[chunk_id]['final_score']:
                best_by_chunk[chunk_id] = chunk

        deduplicated = list(best_by_chunk.values())
        logger.info(f"After deduplication: {len(deduplicated)} unique chunks")

        # Sort by final_score and take top candidates for reranking
        deduplicated.sort(key=lambda x: x['final_score'], reverse=True)
        top_n_for_rerank = min(10, len(deduplicated))
        candidates = deduplicated[:top_n_for_rerank]
        logger.info(f"Selected top {top_n_for_rerank} candidates for reranking")

        # Rerank with cross-encoder using ORIGINAL query
        reranked = rerank(original_query, candidates, top_k=top_k, threshold=rerank_threshold)
        logger.info(f"Reranked to {len(reranked)} final results")

        return reranked

    # Fallback to original implementation
    else:
        from services.query.structured_analyzer import analyze_query
        from services.retrieval.router import get_router

        router = get_router()

        # Normalize to list
        if isinstance(query, str):
            queries = [query]
        else:
            queries = list(query)

        # Use original query for reranking (first query)
        original_query = queries[0]

        logger.info(f"Retriever Agent processing {len(queries)} query(ies)")
        logger.info(f"Original query for reranking: {original_query[:50]}...")

        # Collect all ranked results from each sub-query
        all_ranked_results: List[Dict[str, Any]] = []

        for i, q in enumerate(queries):
            logger.info(f"Processing sub-query {i+1}/{len(queries)}: {q[:50]}...")

            # Analyze query with structured analyzer (intent, entities, constraints)
            structured_query = analyze_query(q)
            logger.info(f"Analyzed: intent={structured_query.intent}, "
                        f"entities={structured_query.entities}, "
                        f"constraints={list(structured_query.constraints.keys())}")

            # Route retrieval with constraint filtering and fallback
            entity_hits, vector_hits = router.route(
                structured_query,
                top_k=retrieval_top_k,
                fallback=True
            )
            logger.info(f"Routed retrieval: {len(entity_hits)} entity hits, {len(vector_hits)} vector hits")

            # Rank and merge
            ranked = merge_rank(
                entity_hits, vector_hits,
                chunk_scores=chunk_scores,
                chunk_score_weight=chunk_score_weight
            )
            logger.info(f"Ranked {len(ranked)} results for sub-query {i+1}")

            all_ranked_results.extend(ranked)

        if not all_ranked_results:
            logger.warning("No retrieval results from any sub-query")
            return []

        # Deduplicate by chunk_id, keeping highest scored version
        logger.info(f"Total results before deduplication: {len(all_ranked_results)}")
        best_by_chunk: Dict[str, Dict[str, Any]] = {}
        for chunk in all_ranked_results:
            chunk_id = chunk['chunk_id']
            if chunk_id not in best_by_chunk or chunk['final_score'] > best_by_chunk[chunk_id]['final_score']:
                best_by_chunk[chunk_id] = chunk

        deduplicated = list(best_by_chunk.values())
        logger.info(f"After deduplication: {len(deduplicated)} unique chunks")

        # Sort by final_score and take top candidates for reranking
        deduplicated.sort(key=lambda x: x['final_score'], reverse=True)
        top_n_for_rerank = min(10, len(deduplicated))
        candidates = deduplicated[:top_n_for_rerank]
        logger.info(f"Selected top {top_n_for_rerank} candidates for reranking")

        # Rerank with cross-encoder using ORIGINAL query
        reranked = rerank(original_query, candidates, top_k=top_k, threshold=rerank_threshold)
        logger.info(f"Reranked to {len(reranked)} final results")

        return reranked


def rerank_hits(
    query: str,
    entity_hits: List[Dict[str, Any]],
    vector_hits: List[Dict[str, Any]],
    top_k: int = 3,
    chunk_scores: Optional[Dict[str, float]] = None,
    chunk_score_weight: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    Merge, rank, and rerank pre-retrieved entity and vector hits.

    Used by the pipeline when using explicit analyzer → router → retriever_agent flow.

    Args:
        query: Original query string for reranking
        entity_hits: Entity-scored hits from retrieval
        vector_hits: Vector search hits from retrieval
        top_k: Number of final results to return

    Returns:
        List of top-k reranked chunk dictionaries
    """
    logger = get_logger("RETRIEVER_AGENT")
    logger.info(f"Reranking {len(entity_hits)} entity hits, {len(vector_hits)} vector hits")

    # Merge and rank entity + vector results
    ranked = merge_rank(
        entity_hits, vector_hits,
        chunk_scores=chunk_scores,
        chunk_score_weight=chunk_score_weight
    )
    logger.info(f"Ranked {len(ranked)} results")

    if not ranked:
        logger.warning("No ranked results to rerank")
        return []

    # Rerank top candidates with cross-encoder
    top_n_for_rerank = min(10, len(ranked))
    candidates = ranked[:top_n_for_rerank]
    logger.info(f"Selected top {top_n_for_rerank} candidates for reranking")

    reranked = rerank(query, candidates, top_k=top_k)
    logger.info(f"Reranked to {len(reranked)} final results")
    return reranked
