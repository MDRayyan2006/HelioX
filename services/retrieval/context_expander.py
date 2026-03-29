"""
Context Expander: Enhances retrieved chunks with neighboring context.

For each retrieved chunk, fetch the previous and next chunks from the same
document (based on source and chunk_index) and merge them into a single
context block.

Design principles:
- Preserve order of retrieved chunks
- Avoid duplicate chunks in final output (handled upstream)
- Graceful degradation: if metadata missing or neighbor not found, use original text
"""

from typing import List, Dict, Any, Set, Tuple, Optional
from core.logger import get_logger

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False


def expand_chunks_with_context(
    chunks: List[Dict[str, Any]],
    vector_store,
    include_previous: bool = True,
    include_next: bool = True,
    context_separator: str = "\n\n"
) -> List[Dict[str, Any]]:
    """
    Expand each chunk with its neighboring chunks' context.

    For each chunk that has source and chunk_index metadata, fetch
    the previous and next chunks from the same document (if exist)
    and merge them into a context_text field.

    Args:
        chunks: List of retrieved chunk dictionaries (final reranked list)
        vector_store: VectorStore instance to fetch neighbor chunks (must have get_chunks_by_metadata)
        include_previous: Whether to include previous chunk (default True)
        include_next: Whether to include next chunk (default True)
        context_separator: String to separate chunks in context (default "\n\n")

    Returns:
        List of chunks with added 'context_text' field.
        Original order preserved.
    """
    logger = get_logger("CONTEXT_EXPANDER")
    if not chunks:
        return chunks

    # Step 1: Extract source and chunk_index from each chunk's payload
    # We'll also keep track of which chunks are expandable
    chunk_metadata = []  # List of (original_index, source, chunk_index, chunk_dict)
    for idx, chunk in enumerate(chunks):
        payload = chunk.get('payload', {})
        source = payload.get('source')
        chunk_index = payload.get('chunk_index')
        # Ensure chunk_index is an integer if present
        if chunk_index is not None:
            try:
                chunk_index = int(chunk_index)
            except (ValueError, TypeError):
                chunk_index = None
        chunk_metadata.append((idx, source, chunk_index, chunk))

    # Step 2: Determine which neighbor chunks we need to fetch
    # Set of (source, index) tuples needed
    needed: Set[Tuple[str, int]] = set()
    # Track which original chunk indices are eligible for expansion
    expandable_indices: List[int] = []

    for idx, source, chunk_index, _ in chunk_metadata:
        if source is None or chunk_index is None:
            continue
        expandable_indices.append(idx)
        if include_previous:
            needed.add((source, chunk_index - 1))
        if include_next:
            needed.add((source, chunk_index + 1))

    if not needed:
        logger.info("No chunks eligible for context expansion (missing source/chunk_index).")
        # No expansion possible; just add context_text = original text
        for chunk in chunks:
            chunk['context_text'] = chunk.get('text', '')
        return chunks

    # Step 3: Group needed neighbors by source for batched fetching
    needed_by_source: Dict[str, List[int]] = {}
    for source, idx in needed:
        if source not in needed_by_source:
            needed_by_source[source] = []
        needed_by_source[source].append(idx)

    # Step 4: Fetch neighbor chunks from vector store
    # Mapping: (source, chunk_index) -> neighbor chunk dict
    neighbor_map: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for source, indices in needed_by_source.items():
        unique_indices = list(set(indices))
        try:
            fetched = vector_store.get_chunks_by_metadata(source, unique_indices)
            # Index fetched chunks by their actual chunk_index for quick lookup
            for fchunk in fetched:
                fpayload = fchunk.get('payload', {})
                fsource = fpayload.get('source')
                findex = fpayload.get('chunk_index')
                if fsource is not None and findex is not None:
                    try:
                        findex = int(findex)
                        neighbor_map[(fsource, findex)] = fchunk
                    except (ValueError, TypeError):
                        continue
            logger.debug(f"Fetched {len(fetched)} neighbor chunks for source {source}")
        except Exception as e:
            logger.warning(f"Failed to fetch neighbor chunks for source {source}: {e}")

    # Step 5: Build expanded chunks
    # We'll create new chunk dicts with context_text to avoid mutating original
    expanded_chunks = []
    for original_idx, source, chunk_index, chunk in chunk_metadata:
        # Build context list: [prev? , current, next?]
        context_parts = []

        # Add previous if available and requested
        if include_previous and source is not None and chunk_index is not None:
            prev = neighbor_map.get((source, chunk_index - 1))
            if prev:
                context_parts.append(prev['text'])

        # Add current chunk's text (always)
        current_text = chunk.get('text', '')
        if current_text:
            context_parts.append(current_text)

        # Add next if available and requested
        if include_next and source is not None and chunk_index is not None:
            nxt = neighbor_map.get((source, chunk_index + 1))
            if nxt:
                context_parts.append(nxt['text'])

        # If we couldn't fetch any neighbors or chunk not expandable, just use original text
        if not context_parts:
            context_text = current_text
        else:
            context_text = context_separator.join(context_parts)

        # Create enhanced chunk with context_text field
        enhanced_chunk = chunk.copy()
        enhanced_chunk['context_text'] = context_text
        expanded_chunks.append(enhanced_chunk)

    logger.info(f"Expanded {len(expandable_indices)} chunks with context (from {len(chunks)} total)")
    return expanded_chunks


def _estimate_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Estimate token count for text.

    Uses tiktoken if available, otherwise falls back to simple heuristic
    (1 token ~= 4 characters for English text).

    Args:
        text: Text to count tokens for
        model: Model name for tiktoken encoding (default: gpt-3.5-turbo)

    Returns:
        Estimated token count
    """
    if not text:
        return 0

    if _TIKTOKEN_AVAILABLE:
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception as e:
            logger.debug(f"tiktoken failed ({e}), using heuristic fallback")

    # Heuristic: 1 token ≈ 4 characters (rough estimate for English)
    # More conservative: use 3.5 to account for multi-byte characters
    return max(1, len(text) // 4)


def build_context_pack(
    chunks: List[Dict[str, Any]],
    max_context_tokens: int = 4096,
    *,
    use_expanded: bool = True,
    separator: str = "\n\n",
    reserve_tokens: int = 0,
    score_key: str = "final_score",
    avoid_adjacent: bool = True,
    adjacency_radius: int = 1
) -> List[Dict[str, Any]]:
    """
    Build a context pack from chunks respecting a token budget.

    Selects chunks greedily by score (highest first) while staying within
    the max_context_tokens limit. Uses context_text if available (after
    expansion), otherwise raw text.

    Args:
        chunks: List of chunk dictionaries (should have 'text' or 'context_text')
        max_context_tokens: Maximum total tokens for the packed context
        use_expanded: If True, prefer 'context_text' field (default: True)
        separator: String to insert between chunks when counting tokens (default "\n\n")
        reserve_tokens: Tokens to reserve for system prompt/query/etc (subtracted from budget)
        score_key: Key to use for sorting (default 'final_score'). Set to None to preserve order.

    Returns:
        List of selected chunks (subset of input) in order determined by selection.
        Each chunk retains original fields plus 'context_text' if not present.
    """
    logger = get_logger("CONTEXT_PACKER")

    # Adjust budget for reservation
    available_tokens = max(0, max_context_tokens - reserve_tokens)
    if available_tokens == 0:
        logger.warning("No tokens available for context pack after reservation")
        return []

    # Determine which text field to use for each chunk
    # Prefer context_text if available and use_expanded=True; else text
    import hashlib
    chunks_with_text = []
    seen_hashes = set()
    
    for chunk in chunks:
        text = chunk.get('context_text' if use_expanded else 'text', chunk.get('text', ''))
        if not text:
            logger.debug(f"Chunk {chunk.get('chunk_id', 'unknown')} has empty text, skipping")
            continue
            
        # Hash text to eliminate redundant identical context completely
        text_hash = hashlib.md5(text.strip().lower().encode('utf-8')).hexdigest()
        if text_hash in seen_hashes:
            logger.debug(f"Chunk {chunk.get('chunk_id')} is an exact duplicate, dropping to save context.")
            continue
            
        seen_hashes.add(text_hash)
        
        chunks_with_text.append({
            'chunk': chunk,
            'text': text
        })

    if not chunks_with_text:
        logger.warning("No chunks with text to pack")
        return []

    # Sort by score if score_key provided, else preserve original order
    if score_key:
        # score_key might not exist in all chunks, default to 0.0
        chunks_with_text.sort(key=lambda x: x['chunk'].get(score_key, 0.0), reverse=True)

    # Greedy packing: add chunks until budget exhausted
    selected = []
    total_tokens = 0

    for idx, item in enumerate(chunks_with_text):
        text = item['text']
        # Estimate tokens for this chunk plus separator (if not first)
        chunk_tokens = _estimate_tokens(text)
        separator_tokens = _estimate_tokens(separator) if selected else 0
        added_tokens = chunk_tokens + separator_tokens

        if total_tokens + added_tokens > available_tokens:
            # Would exceed budget; skip this chunk but try smaller ones below
            logger.debug(f"Chunk {item['chunk'].get('chunk_id')} exceeds budget "
                         f"({total_tokens + added_tokens} > {available_tokens}), skipping")
            continue

        # Add this chunk
        selected.append(item['chunk'])
        total_tokens += added_tokens
        logger.debug(f"Added chunk {item['chunk'].get('chunk_id')}: ~{chunk_tokens} tokens, "
                     f"total now {total_tokens}/{available_tokens}")

    logger.info(f"Context pack: selected {len(selected)}/{len(chunks_with_text)} chunks, "
                f"total tokens ~{total_tokens}")

    # Optional: adjacency avoidance to reduce contextual overlap
    if avoid_adjacent and len(selected) > 1:
        selected = _apply_adjacency_avoidance(selected, adjacency_radius)
        # Recompute token count after filtering (we may have removed some)
        # Not strictly necessary to re-count for return, but good for logging
        total_tokens = 0
        for i, c in enumerate(selected):
            text = c.get('context_text' if use_expanded else 'text', c.get('text', ''))
            sep = separator if i > 0 else ''
            total_tokens += _estimate_tokens(text + sep)
        logger.info(f"After adjacency avoidance: {len(selected)} chunks, ~{total_tokens} tokens")

    # Return selected chunks in the order they were added (which is sorted by score descending)
    return selected


def _get_chunk_location(chunk: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    """Extract (source, chunk_index) from chunk payload."""
    payload = chunk.get('payload', {})
    source = payload.get('source')
    chunk_index = payload.get('chunk_index')
    if chunk_index is not None:
        try:
            chunk_index = int(chunk_index)
        except (ValueError, TypeError):
            chunk_index = None
    return source, chunk_index


def _apply_adjacency_avoidance(
    selected: List[Dict[str, Any]],
    radius: int = 1
) -> List[Dict[str, Any]]:
    """
    Filter selected chunks to avoid including adjacent chunks from the same document.

    If two chunks are from the same source and their chunk_index differs by <= radius,
    keep only the higher-scored one. This reduces redundant context from overlapping
    neighbors.

    Args:
        selected: List of already selected chunks (sorted by score descending)
        radius: How many positions away constitute "adjacent" (default 1 = immediate neighbors)

    Returns:
        Filtered list of chunks with adjacency conflicts removed
    """
    logger = get_logger("CONTEXT_PACKER")
    if not selected or len(selected) <= 1:
        return selected

    # Build location map: (source, chunk_index) -> chunk
    kept_chunks = []
    blocked_positions = set()  # set of (source, chunk_index) to exclude

    for chunk in selected:
        source, idx = _get_chunk_location(chunk)
        if source is None or idx is None:
            # Cannot determine adjacency, keep it
            kept_chunks.append(chunk)
            continue

        # Check if this position is blocked due to earlier higher-scored neighbor
        blocked = False
        for offset in range(-radius, radius + 1):
            if offset == 0:
                continue
            neighbor_pos = (source, idx + offset)
            if neighbor_pos in blocked_positions:
                logger.debug(f"Chunk {chunk.get('chunk_id')} at ({source}, {idx}) "
                             f"conflicts with neighbor at {neighbor_pos}, dropping")
                blocked = True
                break

        if not blocked:
            kept_chunks.append(chunk)
            blocked_positions.add((source, idx))

    logger.info(f"Adjacency avoidance: {len(selected)} → {len(kept_chunks)} chunks "
                f"({len(selected) - len(kept_chunks)} removed due to neighbor overlap)")
    return kept_chunks

