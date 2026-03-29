"""
HelioX RAG 2.1 - Phase 6 Adaptive Multi-Agent Pipeline

Supports two modes:
- Legacy pipeline: Query → Analyze → Retrieve → Rank → Select → Worker Sim
- Multi-agent pipeline: Query → Planner → [Retriever → Workers → Adjudicator → Answer Composer → Critic] loop
  (when use_agents=True)
"""

from typing import List, Dict, Any

from core.logger import get_logger
from core.telemetry_logger import log_event
from models.schemas.query import StructuredQuery
from models.schemas.worker_output import WorkerOutput
from models.schemas.agent_output import AgentOutput
from models.schemas.retry_trace import RetryTrace, RetryAttempt
from services.query.analyzer import analyze_query
from services.retrieval.ranker import merge_rank
from services.retrieval.retriever import get_retriever
from services.retrieval.enhanced_retriever import get_enhanced_retriever
from services.retrieval.reranker import rerank

# Phase 3A/3B/3C/4A/5/6: Multi-agent + adaptive imports
from agents.retriever_agent import retrieve as agent_retrieve
from agents.critic import critique as agent_critique
from agents.query_rewriter import rewrite_query
from agents.worker import process_chunks
from agents.adjudicator import adjudicate
from agents.answer_composer import compose_answer
from services.adaptive.depth_controller import compute_top_k
from services.adaptive.confidence_router import route_by_confidence
from services.adaptive.session_memory import SessionMemory

# ---------------------------------------------------------------------------
# Feedback loop constants
# ---------------------------------------------------------------------------
MAX_RETRIES = 2              # Max retry attempts (total attempts = MAX_RETRIES + 1)
EARLY_STOP_CONFIDENCE = 0.9  # Skip retry if confidence exceeds this
BASE_TOP_K = 3               # Default retrieval depth
EXPLORATION_RATE = 0.1       # Fraction of attempts to explore (e.g., 1 in 10)

def run_pipeline(raw_query: str, use_agents: bool = False) -> Any:
    """
    Execute the full pipeline end-to-end.

    Supports two execution modes:
        - Legacy mode (use_agents=False): Analyzes, retrieves, ranks, and simulates workers
        - Multi-agent mode (use_agents=True): Uses retriever → workers → adjudicator → answer composer → critic
          with bounded retry loop (max 2 retries) when critic flags weak answers

    Args:
        raw_query: User's raw query string
        use_agents: If True, use multi-agent pipeline.
                    If False, use legacy pipeline.

    Returns:
        AgentOutput with fields:
            - answer: synthesized answer (None for legacy mode)
            - worker_outputs: list of WorkerOutput objects (one per top chunk)
            - critique: critic validation output
            - retry_trace: feedback loop trace (if retries occurred)
    """
    pipeline_logger = get_logger("PIPELINE")
    pipeline_logger.info(f"Starting pipeline for query: {raw_query}")

    # --- Check Redis Cache ---
    from core.cache.cache_service import get_cache, set_cache
    cached_result = get_cache(raw_query)
    if cached_result:
        pipeline_logger.info("Found cached result. Returning immediately.")
        return cached_result

    import time
    start_time = time.perf_counter()

    # --- Fetch live auto-tuned parameters ---
    from services.adaptive.auto_tuner import AutoTuner
    tuner = AutoTuner()
    tuned = tuner.get_tuned_parameters()
    pipeline_logger.info(
        f"Auto-Tuner active: top_k={tuned.top_k}, exp_rate={tuned.exploration_rate}, "
        f"chunk_weight={tuned.chunk_score_weight}, rerank_threshold={tuned.rerank_threshold}"
    )

    # Multi-Agent Mode (Phase 3A/3B/3C/3D)
    if use_agents:
        pipeline_logger.info("Using multi-agent pipeline with feedback loop "
                            f"(max {MAX_RETRIES} retries, "
                            f"early stop > {EARLY_STOP_CONFIDENCE})")

        # Phase 4A: Structured Query Analyzer + Routing Engine
        # No planner decomposition; use raw query directly with analyzer→router inside retriever_agent

        # --- Bounded retry loop with adaptive strategies ---
        current_query = raw_query
        attempts: List[RetryAttempt] = []
        best_result = None  # (composed, top_chunks, critique, attempt_num, worker_outputs, adjudication)
        prev_confidence = 0.0  # for adaptive depth / routing
        prev_chunk_scores: Dict[str, float] = {}  # learned chunk scores from previous attempt
        session = SessionMemory()
        best_strategy_info = None  # to capture strategies of best attempt
        current_strategy_info = {}  # initialize before loop to avoid UnboundLocalError

        for attempt in range(MAX_RETRIES + 1):
            pipeline_logger.info(f"--- Attempt {attempt}/{MAX_RETRIES} ---")
            pipeline_logger.info(f"Current query: {current_query[:80]}...")

            # Memory quality signal for adaptive strategies
            mem_quality = session.get_memory_quality()

            # Analyze query intent up-front so we can adjust early pipeline depths (e.g. LIST depth)
            structured = analyze_query(current_query)
            
            # Adaptive retrieval depth (memory-influenced)
            adaptive_k = compute_top_k(
                prev_confidence, attempt, tuned.top_k,
                memory_quality=mem_quality,
                is_list_query=(structured.query_type == "LIST")
            )
            session.record_strategy("depth", f"k={adaptive_k}")
            pipeline_logger.info(f"Adaptive top_k={adaptive_k} (prev_conf={prev_confidence:.2f}, mem_q={mem_quality:.2f})")

            # Confidence-based routing hints (memory-influenced)
            routing = route_by_confidence(
                prev_confidence, attempt, memory_quality=mem_quality,
            )
            # Create a deterministic string key for routing hints
            routing_key = ",".join(f"{k}={v}" for k, v in sorted(routing.items()))
            session.record_strategy("routing", routing_key)

            # Update current strategy info each iteration (so it's valid on attempt 0)
            current_strategy_info = {
                "depth_k": adaptive_k,
                "routing": routing_key,
                "rewrite": current_strategy_info.get("rewrite", "none"),
            }

            # --- Exploration control ---
            # Every Nth attempt we explore more (protect against div by 0)
            if tuned.exploration_rate >= 0.01:
                should_explore = (session.attempt_count % int(1 / tuned.exploration_rate) == 0)
            else:
                should_explore = False
                
            if should_explore:
                retrieval_top_k = 100  # wider net
                chunk_score_weight = max(0.01, tuned.chunk_score_weight * 0.2)  # reduce memory influence
                pipeline_logger.info("Exploration mode: wider retrieval, low chunk weight")
            else:
                retrieval_top_k = 50
                chunk_score_weight = tuned.chunk_score_weight

            # Retrieval: analyzer → router → enhanced retriever_agent (internal)
            top_chunks = agent_retrieve(
                current_query,
                top_k=adaptive_k,
                retrieval_top_k=retrieval_top_k,
                chunk_scores=prev_chunk_scores,
                chunk_score_weight=chunk_score_weight,
                rerank_threshold=tuned.rerank_threshold,
                use_enhanced=True,
            )
            pipeline_logger.info(f"Retriever returned {len(top_chunks)} chunks")

            # Stage X: Context Expansion (expand top_chunks with neighboring context)
            from services.retrieval.context_expander import expand_chunks_with_context, build_context_pack
            from services.retrieval.enhanced_retriever import get_enhanced_retriever
            vector_store = get_enhanced_retriever().vector_store
            top_chunks = expand_chunks_with_context(top_chunks, vector_store)
            
            # --- CONTEXT PACKING (Enforcing Strategy Budgets) ---
            # Shrink and verify dense information down to an acceptable 6000 token limit
            # This completely stops LLM context-drowning and drops exact hashes.
            top_chunks = build_context_pack(top_chunks, max_context_tokens=6000)
            pipeline_logger.info(f"Context Pack filtered down to {len(top_chunks)} final dense chunks")

            # --- RETRIEVAL SUFFICIENCY CHECK ---
            from services.retrieval.sufficiency_check import check_sufficiency
            sufficiency = check_sufficiency(
                query=current_query,
                structured_query=structured,
                chunks=top_chunks,
                worker_outputs=None  # pre-worker, so not available yet
            )
            pipeline_logger.info(f"Sufficiency scores: {sufficiency['scores']}")
            if not sufficiency['sufficient']:
                pipeline_logger.warning(f"Insufficient context coverage: {sufficiency['missing']}. Triggering incremental deeper retrieval.")
                deeper_k = min(adaptive_k + 5, 20)
                # Retrieve additional chunks (incremental, not full replacement)
                extra_chunks = agent_retrieve(
                    current_query,
                    top_k=deeper_k,
                    retrieval_top_k=100,
                    chunk_scores=prev_chunk_scores,
                    chunk_score_weight=chunk_score_weight,
                    rerank_threshold=tuned.rerank_threshold,
                    use_enhanced=True,
                )
                # Merge incrementally: dedup by chunk_id, keep higher score
                seen_ids = {c['chunk_id']: c for c in top_chunks}
                for c in extra_chunks:
                    cid = c['chunk_id']
                    if cid not in seen_ids or c.get('final_score', 0) > seen_ids[cid].get('final_score', 0):
                        seen_ids[cid] = c
                top_chunks = sorted(seen_ids.values(), key=lambda x: x.get('final_score', 0), reverse=True)
                # Re-expand and re-pack to enforce token budget
                top_chunks = expand_chunks_with_context(top_chunks, vector_store)
                top_chunks = build_context_pack(top_chunks, max_context_tokens=6000)
                pipeline_logger.info(f"After deeper retrieval + re-pack: {len(top_chunks)} chunks")

            # Generate worker outputs from retrieved chunks
            worker_outputs = process_chunks(structured, top_chunks, parallel=True)
            pipeline_logger.info(f"Generated {len(worker_outputs)} worker outputs")

            # Adjudicate worker outputs
            adjudication = adjudicate(worker_outputs)
            pipeline_logger.info(
                f"Adjudication: {len(adjudication.final_claims)} claims, "
                f"confidence={adjudication.confidence}, "
                f"conflicts={adjudication.conflicts_detected}"
            )

            # Compose final answer from adjudication (pass chunks for full context evidence)
            s_dict = structured.dict()
            s_dict["raw_query"] = current_query
            composed = compose_answer(adjudication.dict(), s_dict, chunks=top_chunks)
            answer = composed["answer"]
            pipeline_logger.info("Composed final answer from adjudicated claims")

            # Critic (upgraded: claim-citation alignment + overconfidence)
            crit = agent_critique(
                current_query, answer, top_chunks,
                claims=adjudication.final_claims,
                citations=adjudication.citations,
                adjudication_confidence=adjudication.confidence,
            )
            pipeline_logger.info(
                f"Critic verdict: {crit.verdict} "
                f"(confidence={crit.confidence}, "
                f"issues={len(crit.issues)}, "
                f"retry={crit.needs_retry}, "
                f"overconfident={crit.overconfident})"
            )

            # Update session memory — record what was used
            chunk_ids = [c.get('chunk_id', f'chunk_{i}')
                        for i, c in enumerate(top_chunks)]
            session.record_attempt(
                entities=structured.entities,
                chunk_ids=chunk_ids,
            )
            novelty = session.get_novel_chunk_penalty(chunk_ids)

            # Learn from outcome — apply performance signals
            is_retried = crit.needs_retry and attempt < MAX_RETRIES

            # Extract critic feedback signals for memory/discovery
            from services.adaptive.critic_feedback import extract_signals
            critic_signals = extract_signals(
                confidence=crit.confidence,
                verdict=crit.verdict,
                hallucination_risk=crit.hallucination_risk,
                coverage_score=crit.coverage_score,
                issues=crit.issues,
            )

            session.record_outcome(
                confidence=crit.confidence,
                verdict=crit.verdict,
                retried=is_retried,
                critic_signals=critic_signals,
            )
            pipeline_logger.info(
                f"Session memory: novelty={novelty:.2f}, "
                f"outcome recorded (retried={is_retried})"
            )

            # Record this attempt
            attempts.append(RetryAttempt(
                attempt=attempt,
                query_used=current_query,
                confidence=crit.confidence,
                verdict=crit.verdict,
                issues=crit.issues,
                chunk_ids=chunk_ids,
            ))

            # Track best result by confidence
            if (best_result is None
                    or crit.confidence > best_result[2].confidence):
                best_result = (composed, top_chunks, crit, attempt, worker_outputs, adjudication)
                # Capture strategy info for best attempt
                best_strategy_info = current_strategy_info.copy()

            # Update prev_confidence for next iteration's adaptive strategies
            prev_confidence = crit.confidence

            # Update prev_chunk_scores for next iteration's retrieval scoring
            prev_chunk_scores = session.get_chunk_scores()

            # Early stopping: high confidence — skip retry even if flagged
            if crit.confidence >= EARLY_STOP_CONFIDENCE:
                pipeline_logger.info(
                    f"Early stop: confidence {crit.confidence} >= "
                    f"{EARLY_STOP_CONFIDENCE} at attempt {attempt}"
                )
                break

            # Exit early if no retry needed
            if not crit.needs_retry:
                pipeline_logger.info(f"Critic satisfied at attempt {attempt}, "
                                    "exiting loop")
                break

            # Exit if at max retries
            if attempt == MAX_RETRIES:
                pipeline_logger.info(
                    f"Max retries ({MAX_RETRIES}) reached, "
                    "using best result"
                )
                break

            # Build context for context-aware rewriting
            rewrite_context = {
                "adjudication_claims": adjudication.final_claims,
                "ungrounded_sentences": [
                    i for i in crit.issues if "Ungrounded" in i
                ],
                "conflicts_detected": adjudication.conflicts_detected,
                "entity_boosts": session.get_entity_boosts(),
                "chunk_scores": session.get_chunk_scores(),
                "concept_scores": session.get_concept_scores(),
                "concept_importance": session.get_concept_importance(),
                "memory_quality": session.get_memory_quality(),
                "allow_broaden": routing.get("broaden", True),
                "confidence": crit.confidence,
            }

            # Exploration: force injection of a less-important concept to diversify
            if should_explore:
                concept_imp = session.get_concept_importance()
                query_lower = current_query.lower()
                # Candidates: concepts with moderate importance (0.1-0.5) not in query
                candidates = [c for c, imp in concept_imp.items()
                             if 0.1 <= imp <= 0.5 and c not in query_lower]
                if candidates:
                    # Pick least important to explore underused concepts
                    forced_concept = min(candidates, key=lambda c: concept_imp[c])
                    rewrite_context["forced_concept"] = forced_concept
                    pipeline_logger.info(f"Exploration: forced concept '{forced_concept}'")

            # Rewrite query for next attempt (context-aware)
            rewrite_result = rewrite_query(
                current_query, crit.issues, context=rewrite_context
            )
            current_query = rewrite_result["rewritten_query"]
            reason = rewrite_result["reason"]
            
            # Extract strategy name from reason (prefix before colon)
            strategy_name = reason.split(":")[0] if ":" in reason else reason
            session.record_strategy("rewrite", strategy_name)

            # Collect current attempt's strategy info for telemetry
            current_strategy_info = {
                "depth_k": adaptive_k,
                "routing": routing_key,
                "rewrite": strategy_name,
            }

            pipeline_logger.info(
                f"Rewritten query (reason: {reason}): "
                f"{current_query[:80]}..."
            )

        # --- Assemble final output from best result ---
        composed, top_chunks, critique, best_attempt_num, worker_outputs, adjudication = best_result
        answer = composed["answer"]

        # Build retry trace
        initial_conf = attempts[0].confidence
        final_conf = attempts[-1].confidence
        retry_trace = RetryTrace(
            total_attempts=len(attempts),
            improved=final_conf > initial_conf,
            confidence_delta=round(final_conf - initial_conf, 4),
            best_attempt=best_attempt_num,
            attempts=attempts,
        )

        pipeline_logger.info(
            f"Feedback loop complete: {retry_trace.total_attempts} attempts, "
            f"improved={retry_trace.improved}, "
            f"delta={retry_trace.confidence_delta}"
        )

        # Adjudication stats (from best iteration)
        pipeline_logger.info(
            f"Adjudication: {len(adjudication.final_claims)} claims, "
            f"confidence={adjudication.confidence}, "
            f"conflicts={adjudication.conflicts_detected}, "
            f"duplicates={adjudication.duplicate_count}, "
            f"authorities={adjudication.authority_scores}"
        )

        # --- Confidence calibration ---
        # Global confidence from 4 independent signals
        retrieval_quality = (
            sum(c.get('final_score', 0.0) for c in top_chunks)
            / max(len(top_chunks), 1)
        )
        adjudication_score = adjudication.confidence
        critic_confidence = critique.confidence
        agreement_score = (
            sum(
                g for g in adjudication.authority_scores
            ) / max(len(adjudication.authority_scores), 1)
        ) if adjudication.authority_scores else 0.0

        calibrated_confidence = float(round(
            0.25 * float(retrieval_quality)
            + 0.25 * float(adjudication_score)
            + 0.25 * float(critic_confidence)
            + 0.25 * float(agreement_score),
            4
        ))
        pipeline_logger.info(
            f"Confidence calibration: retrieval={retrieval_quality:.2f}, "
            f"adjudication={adjudication_score:.2f}, "
            f"critic={critic_confidence:.2f}, "
            f"agreement={agreement_score:.2f} "
            f"→ calibrated={calibrated_confidence}"
        )

        pipeline_logger.info("Multi-agent pipeline completed successfully")

        # --- Telemetry logging ---
        end_time = time.perf_counter()
        total_duration_ms = float(round((end_time - start_time) * 1000, 2))

        # Compute retry count
        retry_count = max(0, retry_trace.total_attempts - 1)
        max_retries_reached = (best_attempt_num == MAX_RETRIES)

        # Build telemetry event
        telemetry_event = {
            "query_id": None,  # will be auto-generated by log_event
            "timestamp": None,  # auto-generated
            "query": raw_query,
            "pipeline_metrics": {
                "total_duration_ms": total_duration_ms,
                "retry_count": retry_count,
                "max_retries_reached": max_retries_reached,
                "total_chunks_retrieved": len(top_chunks),
            },
            "final_outcome": {
                "verdict": critique.verdict,
                "confidence": float(round(critique.confidence, 4)),
                "hallucination_risk": float(round(critique.hallucination_risk, 4)),
                "coverage_score": float(round(critique.coverage_score, 4)),
            },
            "strategies_used": best_strategy_info or {},
            "knowledge_used": {
                "concepts": list(session.get_concept_scores().keys()),
                "entities": list(session.get_entity_boosts().keys()),
            }
        }

        log_event(telemetry_event)

        # Reconstruct full citations from Adjudicator spans and original top_chunks
        full_citations = []
        if adjudication and hasattr(adjudication, 'citations') and worker_outputs and top_chunks:
            added_ids = set()
            for span in adjudication.citations:
                for w in worker_outputs:
                    if w.supporting_span == span and w.chunk_id not in added_ids:
                        for c in top_chunks:
                            c_id = c.get("chunk_id") if isinstance(c, dict) else getattr(c, "chunk_id", None)
                            if c_id == w.chunk_id:
                                c_text = c.get("text") if isinstance(c, dict) else getattr(c, "text", "")
                                c_meta = c.get("metadata", {}) if isinstance(c, dict) else getattr(c, "metadata", {})
                                full_citations.append({
                                    "chunk_id": c_id,
                                    "text": c_text,
                                    "source": c_meta.get("source", "Unknown Document") if isinstance(c_meta, dict) else "Unknown Document",
                                    "score": float(w.retrieval_score),
                                    "page": c_meta.get("page") if isinstance(c_meta, dict) else None
                                })
                                added_ids.add(c_id)
                                break
                        break

        # Cache the result before returning
        final_response = {
            "answer": answer,
            "confidence": float(calibrated_confidence),
            "citations": full_citations
        }
        set_cache(raw_query, final_response)

        return AgentOutput(
            answer=answer,
            confidence=float(calibrated_confidence),
            adjudication=adjudication,
            critique=critique,
            worker_outputs=worker_outputs,
            retry_trace=retry_trace,
            citations=full_citations
        )
    # Legacy Mode (Phase 1) - unchanged
    query_logger = get_logger("QUERY")
    retrieval_logger = get_logger("RETRIEVAL")
    ranking_logger = get_logger("RANKING")
    worker_logger = get_logger("WORKER")

    query_logger.info(f"Analyzing query: {raw_query}")
    structured_query = analyze_query(raw_query)
    query_logger.info(f"Extracted {len(structured_query.keywords)} keywords: {structured_query.keywords}")
    query_logger.info(f"Extracted {len(structured_query.entities)} entities: {structured_query.entities}")

    # Stage 2: Retrieval (real vector search)
    retrieval_logger.info("Starting retrieval")
    # Use enhanced retriever for better context retrieval
    retriever = get_enhanced_retriever()
    entity_hits, vector_hits = retriever.retrieve(structured_query, top_k=50)

    # Stage 3: Ranking
    ranking_logger.info("Merging and ranking results")
    ranked_results = merge_rank(entity_hits, vector_hits)
    ranking_logger.info(f"Ranked {len(ranked_results)} merged results")

    # Log top 5 for debugging (pre-rerank)
    for i, result in enumerate(ranked_results[:5], 1):
        ranking_logger.info(
            f"Rank {i} (pre-rerank): chunk_id={result['chunk_id']}, final_score={result['final_score']}, "
            f"vector={result['vector_score']}, entity={result['entity_score']}"
        )

    # Stage 3.5: Rerank top candidates with cross-encoder
    reranking_logger = get_logger("RERANKING")
    reranking_logger.info("Reranking top 10 candidates with cross-encoder")
    top_n_for_rerank = min(10, len(ranked_results))
    reranked = rerank(raw_query, ranked_results[:top_n_for_rerank], top_k=3)
    reranking_logger.info(f"Reranked {len(reranked)} results")

    # Log rerank results
    for i, result in enumerate(reranked[:5], 1):
        reranking_logger.info(
            f"Rerank Rank {i}: chunk_id={result['chunk_id']}, final_score={result['final_score']}, "
            f"rerank_score={result.get('rerank_score', 'N/A')}"
        )

    # Stage 4: Select top 3 (from reranked list)
    top_3 = reranked[:3]
    pipeline_logger.info(f"Selected top 3 chunks after reranking")
    for i, chunk in enumerate(top_3, 1):
        pipeline_logger.info(f"Top {i}: {chunk['chunk_id']} (score={chunk['final_score']})")

    # Stage 4.5: Context Expansion
    pipeline_logger.info("Expanding chunks with neighboring context")
    from services.retrieval.context_expander import expand_chunks_with_context
    # Use the vector store from the retriever we already have
    vector_store = retriever.vector_store
    top_3 = expand_chunks_with_context(top_3, vector_store)
    for i, chunk in enumerate(top_3, 1):
        ctx_len = len(chunk.get('context_text', ''))
        pipeline_logger.info(f"Top {i} after context expansion: {chunk['chunk_id']} (context_len={ctx_len})")

    # Stage 5: Worker Agent (parallel, deterministic)
    worker_logger.info("Generating worker outputs with parallel worker agents")
    structured = analyze_query(raw_query)
    worker_outputs = process_chunks(structured, top_3, parallel=True)
    for output in worker_outputs:
        worker_logger.info(
            f"Worker result: chunk_id={output.chunk_id}, confidence={output.confidence:.2f}, "
            f"claim='{output.claim[:50]}...'"
        )

    pipeline_logger.info("Pipeline completed successfully")
    adjudication = adjudicate(worker_outputs)

    # Phase 6: Lightweight Answer Composition
    pipeline_logger.info("Synthesizing lightweight factual answer...")
    s_dict = structured.dict()
    s_dict["raw_query"] = raw_query
    composed = compose_answer(adjudication.dict(), s_dict, use_lightweight=True)
    answer = composed["answer"]

    # Cache the lightweight result
    final_response = {
        "answer": answer,
        "confidence": adjudication.confidence if adjudication else 0.0,
        "citations": adjudication.citations if adjudication and hasattr(adjudication, "citations") else []
    }
    set_cache(raw_query, final_response)

    return AgentOutput(answer=answer, worker_outputs=worker_outputs, adjudication=adjudication)


if __name__ == "__main__":
    # Demo execution with sample query
    sample_query = "How does HelioX perform vector search using Qdrant?"
    result = run_pipeline(sample_query)

    print("\n" + "="*80)
    print("PIPELINE RESULTS - Top 3 Ranked Chunks with Worker Output")
    print("="*80 + "\n")

    if isinstance(result, dict):
        print("CACHED RESULT:")
        print(f"Answer: {result.get('answer')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Citations: {result.get('citations')}")
        print()
    else:
        # Extract worker outputs from AgentOutput
        outputs = result.worker_outputs
    
        for i, output in enumerate(outputs, 1):
            print(f"{i}. Chunk ID: {output.chunk_id}")
            print(f"   Confidence: {output.confidence:.4f}")
            print(f"   Claim: {output.claim}")
            print(f"   Supporting Span: {output.supporting_span}")
            print()
    
        # Also show synthesized answer if available (multi-agent mode)
        if result.answer:
            print("="*80)
            print("SYNTHESIZED ANSWER:")
            print(result.answer)
            print()
