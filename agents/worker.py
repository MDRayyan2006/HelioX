"""
Worker Agent: Processes a chunk to produce structured reasoning output.

Each worker independently analyzes a chunk against the structured query,
extracts a supporting span, generates a claim, and computes confidence
based on keyword/entity overlap.

Deterministic, no LLM, parallelizable.
"""

import re
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.logger import get_logger
from models.schemas.query import StructuredQuery
from models.schemas.worker_output import WorkerOutput

logger = get_logger("WORKER_AGENT")


class WorkerAgent:
    """Processes a single chunk to extract claim and supporting span."""

    def process_chunk(
        self,
        structured_query: StructuredQuery,
        chunk: Dict[str, Any]
    ) -> WorkerOutput:
        """
        Process a single chunk.

        Steps:
        1. Split chunk text into sentences.
        2. Score sentences by keyword/entity overlap with query.
        3. Select best sentence as supporting_span.
        4. Generate claim highlighting matched terms.
        5. Compute confidence from coverage ratio + entity bonus.

        Args:
            structured_query: Query with keywords, entities, intent
            chunk: Chunk dict with 'chunk_id' and 'text'

        Returns:
            WorkerOutput with claim, supporting_span, and confidence_local (0-1)
        """
        chunk_id = chunk['chunk_id']
        # Prefer expanded context if available, else fall back to original text
        text = chunk.get('context_text', chunk.get('text', ''))
        source_type = chunk.get('payload', {}).get('source', 'unknown')
        retrieval_score = chunk.get('final_score', 0.0)
        if not text:
            logger.warning(f"Chunk {chunk_id} has empty text")
            return WorkerOutput(
                chunk_id=chunk_id,
                claim="Empty chunk content.",
                supporting_span="",
                confidence=0.0,
                source_type=source_type,
                retrieval_score=retrieval_score,
            )

        # Lowercase for case-insensitive matching
        text_lower = text.lower()

        # Split into sentences (simple regex on .!?)
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        if not sentences:
            supporting_span = text[:200] + ("..." if len(text) > 200 else "")
            claim = "Chunk contains no clear sentence structure."
            confidence = 0.1
            return WorkerOutput(
                chunk_id=chunk_id,
                claim=claim,
                supporting_span=supporting_span,
                confidence=confidence
            )

        # Prepare query terms (lowercase)
        query_keywords = [kw.lower() for kw in structured_query.keywords]
        query_entities = [ent.lower() for ent in structured_query.entities]

        # Score each sentence by keyword/entity relevance
        scored_sentences = []

        for sent in sentences:
            sent_lower = sent.lower()
            # Keyword hits: partial substring matches
            kw_hits = sum(1 for kw in query_keywords if kw in sent_lower)
            # Entity hits: exact substring matches (case-insensitive)
            ent_hits = sum(1 for ent in query_entities if ent in sent_lower)
            # Weighted score: 0.6 keywords, 0.4 entities
            score = 0.6 * kw_hits + 0.4 * ent_hits
            scored_sentences.append((sent, score))

        # Sort by relevance score descending, then by position for stability
        scored_sentences.sort(key=lambda x: -x[1])

        # Best sentence = highest scoring (for supporting_span)
        best_sentence = scored_sentences[0][0] if scored_sentences else sentences[0]
        best_score = scored_sentences[0][1] if scored_sentences else 0.0

        supporting_span = best_sentence

        # Generate claim: extract ACTUAL content sentences (top 2 by relevance)
        # Instead of meta-descriptions like "This chunk discusses X", use real content
        matched_keywords = [kw for kw in query_keywords if kw in text_lower]
        matched_entities = [ent for ent in query_entities if ent in text_lower]

        # Take top 2 relevant sentences as claim content
        top_claim_sentences = []
        for sent, score in scored_sentences[:2]:
            cleaned = sent.strip()
            if cleaned and len(cleaned) > 10:  # skip trivially short
                # Ensure sentence ends with punctuation
                if not cleaned.endswith(('.', '!', '?')):
                    cleaned += '.'
                top_claim_sentences.append(cleaned)

        if top_claim_sentences:
            claim = ' '.join(top_claim_sentences)
        elif sentences:
            # Fallback: use first sentence as claim
            claim = sentences[0].strip()
            if not claim.endswith(('.', '!', '?')):
                claim += '.'
        else:
            claim = "No extractable content from this chunk."

        # Compute confidence: coverage ratio + entity bonus
        total_query_terms = len(query_keywords) + len(query_entities)
        if total_query_terms == 0:
            confidence = 0.5  # neutral if no query terms
        else:
            total_matches = len(matched_keywords) + len(matched_entities)
            coverage = total_matches / total_query_terms
            confidence = coverage
            # Bonus: if at least one entity matches, boost confidence
            if matched_entities:
                confidence = min(1.0, confidence + 0.2)
            # Also incorporate sentence-level best_score indirectly? We could normalize best_score, but not needed.

        # Clamp to [0,1]
        confidence = max(0.0, min(1.0, confidence))

        return WorkerOutput(
            chunk_id=chunk_id,
            claim=claim,
            supporting_span=supporting_span,
            confidence=confidence,
            source_type=source_type,
            retrieval_score=retrieval_score,
        )


def process_chunks_parallel(
    structured_query: StructuredQuery,
    chunks: List[Dict[str, Any]],
    max_workers: int = None
) -> List[WorkerOutput]:
    """
    Process multiple chunks in parallel using ThreadPoolExecutor.

    Args:
        structured_query: The analyzed query
        chunks: List of chunk dictionaries
        max_workers: Max worker threads (default: None = auto)

    Returns:
        List of WorkerOutput sorted by confidence descending (and chunk_id for determinism)
    """
    agent = WorkerAgent()
    logger.info(f"Processing {len(chunks)} chunks in parallel (max_workers={max_workers})")

    if not chunks:
        return []

    # Sequential fallback for single chunk
    if len(chunks) == 1:
        return [agent.process_chunk(structured_query, chunks[0])]

    # Parallel processing
    results: List[WorkerOutput] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Map futures to index for ordering (though we'll sort later)
        future_to_idx = {executor.submit(agent.process_chunk, structured_query, chunk): idx
                         for idx, chunk in enumerate(chunks)}
        # Collect as completed (unordered)
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing chunk index {idx}: {e}")
                # Create error output
                chunk = chunks[idx]
                results.append(WorkerOutput(
                    chunk_id=chunk['chunk_id'],
                    claim=f"Worker error: {str(e)}",
                    supporting_span="",
                    confidence=0.0
                ))

    # Sort by confidence descending, then by chunk_id for deterministic tie-breaking
    results.sort(key=lambda w: (-w.confidence, w.chunk_id))
    return results


def process_chunks(
    structured_query: StructuredQuery,
    chunks: List[Dict[str, Any]],
    parallel: bool = True,
    max_workers: int = None
) -> List[WorkerOutput]:
    """
    Process chunks using WorkerAgent.

    Args:
        structured_query: Analyzed query
        chunks: List of chunk dicts
        parallel: Use parallel execution if True, else sequential
        max_workers: Max threads for parallel

    Returns:
        Sorted list of WorkerOutput (by confidence descending)
    """
    if parallel:
        return process_chunks_parallel(structured_query, chunks, max_workers)
    else:
        agent = WorkerAgent()
        results = [agent.process_chunk(structured_query, chunk) for chunk in chunks]
        results.sort(key=lambda w: (-w.confidence, w.chunk_id))
        return results
