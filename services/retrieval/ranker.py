from typing import List, Dict, Any, Optional


def _compute_metadata_score(hit: Dict[str, Any]) -> float:
    """
    Score chunk metadata richness and quality signals.

    Considers:
    - Presence of source field (0.3)
    - Presence of page or section (structured docs) (0.3)
    - Text length quality: 50 < len < 500 characters (0.4)

    Returns score in [0, 1] range, or 0.1 minimal floor if no metadata.
    """
    payload = hit.get('payload', {})
    score = 0.0
    factors = 0

    # Source type bonus (top-level or payload)
    source = hit.get('source') or payload.get('source')
    if source:
        score += 0.3
        factors += 1

    # Has page/section info (structured docs rank higher)
    page = hit.get('page') or payload.get('page')
    section = hit.get('section') or payload.get('section')
    if page is not None or (section and str(section).strip()):
        score += 0.3
        factors += 1

    # Text length quality (not too short, not too long)
    text_len = len(hit.get('text', ''))
    if 50 < text_len < 500:
        score += 0.4
        factors += 1

    return score if factors > 0 else 0.1


def normalize_scores(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize scores in a hit list to 0-1 range using min-max normalization.

    Args:
        hits: List of hit dictionaries containing at least 'score' key

    Returns:
        New list with normalized 'norm_score' added
    """
    if not hits:
        return hits

    scores = [hit['score'] for hit in hits]
    min_score = min(scores)
    max_score = max(scores)

    # Avoid division by zero if all scores are equal
    range_score = max_score - min_score if max_score > min_score else 1.0

    normalized = []
    for hit in hits:
        hit_copy = hit.copy()
        hit_copy['norm_score'] = (hit['score'] - min_score) / range_score
        normalized.append(hit_copy)

    return normalized

def merge_rank(
    entity_hits: List[Dict[str, Any]],
    vector_hits: List[Dict[str, Any]],
    elastic_hits: Optional[List[Dict[str, Any]]] = None,
    chunk_scores: Optional[Dict[str, float]] = None,
    chunk_score_weight: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Merge and rank entity and vector search results using weighted scoring.

    Scoring formula:
        final = 0.6 * vector_score + 0.3 * entity_score + 0.1 * metadata_score
                + chunk_score_weight * normalized_chunk_score (if provided)

    Args:
        entity_hits: List of entity search results with 'chunk_id', 'text', 'score'
        vector_hits: List of vector search results with 'chunk_id', 'text', 'score'
        chunk_scores: Optional dict mapping chunk_id → learned performance score [-1,1]
        chunk_score_weight: Weight for chunk score component (default 0.1)

    Returns:
        Sorted list (descending by final_score) of merged results with all scores
    """
    # Normalize scores to 0-1 for each hit set
    normalized_entity = normalize_scores(entity_hits)
    normalized_vector = normalize_scores(vector_hits)
    normalized_elastic = normalize_scores(elastic_hits) if elastic_hits else []

    # Build lookup maps for quick access
    entity_map = {hit['chunk_id']: hit for hit in normalized_entity}
    vector_map = {hit['chunk_id']: hit for hit in normalized_vector}
    elastic_map = {hit['chunk_id']: hit for hit in normalized_elastic}

    # Get all unique chunk IDs
    all_chunk_ids = set(entity_map.keys()) | set(vector_map.keys()) | set(elastic_map.keys())

    merged_results = []

    for chunk_id in all_chunk_ids:
        entity_hit = entity_map.get(chunk_id)
        vector_hit = vector_map.get(chunk_id)
        elastic_hit = elastic_map.get(chunk_id)

        # Extract normalized scores (default to 0 if missing from one source)
        entity_score = entity_hit['norm_score'] if entity_hit else 0.0
        vector_score = vector_hit['norm_score'] if vector_hit else 0.0
        elastic_score = elastic_hit['norm_score'] if elastic_hit else 0.0

        # Dynamic metadata score based on actual chunk metadata
        metadata_source = entity_hit or vector_hit or elastic_hit
        metadata_score = _compute_metadata_score(metadata_source)

        if elastic_hits is not None:
            # Weighted scoring when elastic hits are present: Distributed evenly among sparse signals
            final_score = (
                0.5 * vector_score +
                0.2 * entity_score +
                0.2 * elastic_score +
                0.1 * metadata_score
            )
        else:
            final_score = (
                0.6 * vector_score +
                0.3 * entity_score +
                0.1 * metadata_score
            )

        # Incorporate learned chunk score if available (shift [-1,1] → [0,1] and apply weight)
        if chunk_scores and chunk_id in chunk_scores:
            cs = chunk_scores[chunk_id]
            # Normalize to [0, 1]
            normalized_cs = (cs + 1.0) / 2.0
            final_score += chunk_score_weight * normalized_cs

        # Get text from whichever hit has it
        text = (entity_hit or vector_hit or elastic_hit)['text']

        merged_results.append({
            'chunk_id': chunk_id,
            'text': text,
            'final_score': round(final_score, 4),
            'vector_score': round(vector_score, 4),
            'entity_score': round(entity_score, 4),
            'elastic_score': round(elastic_score, 4),
            'metadata_score': round(metadata_score, 4)
        })

    # Sort by final_score descending
    merged_results.sort(key=lambda x: x['final_score'], reverse=True)

    return merged_results


def apply_coverage_ranking(
    results: List[Dict[str, Any]],
    lambda_param: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Apply MMR-style diversity ranking to reduce redundancy in results.

    Uses a greedy selection approach: iteratively picks the next result that
    maximizes (lambda * relevance_score - (1-lambda) * max_similarity_to_selected).

    Textual similarity is approximated via word-overlap (Jaccard) to avoid
    requiring embeddings at this stage.

    Args:
        results: List of result dicts, each must have 'final_score' and 'text'.
        lambda_param: Trade-off between relevance (1.0) and diversity (0.0).
                      Default 0.7 favours relevance while still promoting diversity.

    Returns:
        Reordered list of results with diversity-adjusted scores.
    """
    if not results or len(results) <= 1:
        return results

    def _word_set(text: str) -> set:
        return set(text.lower().split())

    def _jaccard(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    # Pre-compute word sets
    word_sets = [_word_set(r.get('text', '')) for r in results]

    selected_indices: List[int] = []
    remaining = list(range(len(results)))

    # Normalise relevance scores to [0, 1]
    max_score = max(r['final_score'] for r in results)
    min_score = min(r['final_score'] for r in results)
    score_range = max_score - min_score if max_score > min_score else 1.0

    while remaining:
        best_idx = None
        best_mmr = -float('inf')

        for idx in remaining:
            norm_score = (results[idx]['final_score'] - min_score) / score_range

            # Max similarity to any already-selected result
            if selected_indices:
                max_sim = max(
                    _jaccard(word_sets[idx], word_sets[s])
                    for s in selected_indices
                )
            else:
                max_sim = 0.0

            mmr = lambda_param * norm_score - (1 - lambda_param) * max_sim

            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = idx

        selected_indices.append(best_idx)
        remaining.remove(best_idx)

    # Return results in diversity-ranked order, preserving original scores
    return [results[i] for i in selected_indices]
