"""
Reasoner Agent: Synthesizes final answer from retrieved chunks.

Takes query and top-k chunks, extracts most relevant information,
and produces a coherent answer without hallucination.
"""

from typing import List, Dict, Any
import re
from core.logger import get_logger

from services.query.analyzer import analyze_query, extract_entities, STOPWORDS


def reason(query: str, chunks: List[Dict[str, Any]]) -> str:
    """
    Generate a final answer from retrieved chunks.

    Strategy:
        1. Extract query keywords and entities for relevance scoring
        2. For each top chunk, split into sentences and score by keyword/entity overlap
        3. Select top sentences across all chunks (by score and chunk ranking)
        4. Concatenate into a coherent answer
        5. If no good matches, return a fallback message

    Args:
        query: Original user query
        chunks: List of top-k retrieved chunks (from retriever agent), each with 'text' and 'final_score'

    Returns:
        Final answer string (deterministic, no hallucination)
    """
    logger = get_logger("REASONER")
    logger.info(f"Reasoning over {len(chunks)} chunks")

    if not chunks:
        return "No relevant information found."

    # Extract query keywords and entities for relevance scoring
    structured = analyze_query(query)
    keywords = [kw.lower() for kw in structured.keywords]
    entities = [ent.lower() for ent in structured.entities]

    logger.info(f"Query keywords: {keywords}")
    logger.info(f"Query entities: {entities}")

    # Score all sentences from all chunks
    sentence_scores: List[Dict[str, Any]] = []

    for chunk_idx, chunk in enumerate(chunks):
        chunk_text = chunk['text']
        chunk_score = chunk.get('final_score', 0.0)
        chunk_id = chunk.get('chunk_id', f'chunk_{chunk_idx}')

        # Split into sentences (simple regex)
        sentences = re.split(r'[.!?]+', chunk_text)
        sentences = [s.strip() for s in sentences if s.strip()]

        for sent in sentences:
            sent_lower = sent.lower()

            # Count keyword hits (partial matches)
            kw_hits = sum(1 for kw in keywords if kw in sent_lower or sent_lower.startswith(kw))

            # Count entity hits (exact/partial matches)
            ent_hits = sum(1 for ent in entities if ent in sent_lower)

            # Simple scoring: 1 point per keyword, 2 points per entity
            score = kw_hits + 2 * ent_hits

            # Bonus: if chunk itself has high retrieval score, slightly boost
            score += chunk_score * 0.5

            sentence_scores.append({
                'sentence': sent,
                'score': score,
                'chunk_idx': chunk_idx,
                'chunk_id': chunk_id
            })

    if not sentence_scores:
        return "No extractable information found."

    # Sort sentences by score descending
    sentence_scores.sort(key=lambda x: x['score'], reverse=True)

    # Select top sentences (limit to avoid excessive length)
    # Take up to 5 best sentences, but only those with non-zero relevance
    top_sentences = [s for s in sentence_scores if s['score'] > 0][:5]

    if not top_sentences:
        # Fallback: use first sentence from highest-scoring chunk
        fallback = chunks[0]['text'].split('.')[0].strip() + '.'
        return fallback if fallback else "No directly relevant information found."

    # Re-sort selected sentences by their original chunk order to maintain coherence
    # (within each chunk, sentences appear in original order)
    top_sentences.sort(key=lambda x: (x['chunk_idx'], x['score']), reverse=False)

    # Extract just the sentence texts
    selected = [s['sentence'] for s in top_sentences]

    # Concatenate into a paragraph
    answer = " ".join(selected) + "."

    logger.info(f"Reasoner generated answer with {len(selected)} sentences")

    return answer
