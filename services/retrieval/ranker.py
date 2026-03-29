import re
from typing import List, Dict, Any, Optional

def _extract_entities(text: str) -> set:
    """Extract capitalized words as a simple proxy for entities/concepts."""
    return set(re.findall(r'\b[A-Z][a-z]+\b', text))

def _calculate_novelty(text: str, seen_text: str) -> float:
    """Calculate proportion of new words in text compared to seen_text."""
    words = set(re.findall(r'\b\w+\b', text.lower()))
    if not words: return 0.0
    seen_words = set(re.findall(r'\b\w+\b', seen_text.lower()))
    new_words = words - seen_words
    return len(new_words) / len(words)

def apply_coverage_ranking(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply advanced coverage-based ranking with adaptive penalty and novelty boost.
    Uses Greedy MMR selection dynamically adjusting scores to prevent redundancy.
    """
    if not hits:
        return hits

    remaining = hits.copy()
    selected = []
    seen_text = ""
    seen_entities = set()
    selected_sections = set()
    section_counts = {}
    MAX_CHUNKS_PER_SECTION = 2
    
    while remaining:
        best_idx = -1
        best_score = -float('inf')
        best_penalty = 0.0
        best_reward = 0.0
        best_coverage = 0.0
        
        for i, candidate in enumerate(remaining):
            payload = candidate.get('payload', {})
            section = candidate.get('section') or payload.get('section') or "unknown"
            
            # HARD GUARANTEE: Max chunks per section constraint
            if section != "unknown" and section_counts.get(section, 0) >= MAX_CHUNKS_PER_SECTION:
                continue
                
            text = candidate.get('text', '')
            base_score = candidate.get('final_score', 0.0)
            
            chunk_entities = _extract_entities(text)
            novel_words_ratio = _calculate_novelty(text, seen_text)
            
            same_section = (section in selected_sections) and (section != "unknown")
            low_new_info = novel_words_ratio < 0.2
            adds_new_info = novel_words_ratio >= 0.2
            new_entities = bool(chunk_entities - seen_entities)
            
            # Adaptive Penalty
            penalty = 0.0
            if same_section:
                if low_new_info:
                    penalty = 0.1
                elif adds_new_info:
                    penalty = 0.03
            
            # CRITICAL RULE: NEVER let penalty > base relevance score
            penalty = min(penalty, base_score)
            
            # Novelty Boost (ONLY if meaningful)
            if new_entities:
                reward = 0.1
            else:
                reward = 0.03
                
            # Coverage Score
            temp_unique_sections = len(selected_sections | {section})
            total_sections = len(selected) + 1
            coverage = temp_unique_sections / total_sections
            coverage_bonus = 0.1 * coverage
            
            new_score = base_score + reward + coverage_bonus - penalty
            
            if new_score > best_score:
                best_score = new_score
                best_idx = i
                best_penalty = penalty
                best_reward = reward
                best_coverage = coverage_bonus
                
        # If all remaining candidates were skipped due to constraints, terminate early
        if best_idx == -1:
            break
            
        # Pick the best candidate
        winner = remaining.pop(best_idx)
        winner['final_score'] = round(best_score, 4)
        winner['coverage_bonus'] = round(best_coverage, 4)
        winner['novelty_reward'] = round(best_reward, 4)
        winner['diversity_penalty'] = round(best_penalty, 4)
        
        selected.append(winner)
        
        # Update seen states
        seen_text += " " + winner.get('text', '')
        seen_entities.update(_extract_entities(winner.get('text', '')))
        
        win_payload = winner.get('payload', {})
        win_section = winner.get('section') or win_payload.get('section') or "unknown"
        if win_section != "unknown":
            selected_sections.add(win_section)
            section_counts[win_section] = section_counts.get(win_section, 0) + 1
            
    return selected


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

        # Get text and payload from whichever hit has it
        best_hit = entity_hit or vector_hit or elastic_hit
        text = best_hit['text']
        payload = best_hit.get('payload', {})

        merged_results.append({
            'chunk_id': chunk_id,
            'text': text,
            'final_score': round(final_score, 4),
            'vector_score': round(vector_score, 4),
            'entity_score': round(entity_score, 4),
            'elastic_score': round(elastic_score, 4),
            'metadata_score': round(metadata_score, 4),
            'payload': payload
        })

    # Sort initially by base formula final_score descending for stability
    merged_results.sort(key=lambda x: x['final_score'], reverse=True)

    # Apply adaptive coverage ranking (MMR)
    diversified_results = apply_coverage_ranking(merged_results)

    return diversified_results
