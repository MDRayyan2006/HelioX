"""
Concept Taxonomy: Static + dynamic entity → concept grouping for generalization.

Maps individual entities to higher-level concepts so the system can
transfer learning signals between related entities. For example,
if "qdrant" performs well, the parent concept "vector database" receives
a damped boost, which can then be inferred for unseen siblings like "pinecone".

Supports both static (hand-curated) and dynamic (discovered) concepts.

Deterministic, no ML, no external lookups.
"""

from typing import Dict, List, Set

# ---------------------------------------------------------------------------
# Concept → Entity mapping (static, authoritative source of truth)
# ---------------------------------------------------------------------------

CONCEPT_MAP: Dict[str, List[str]] = {
    "vector database":     ["qdrant", "pinecone", "milvus", "weaviate", "chroma",
                            "faiss", "pgvector"],
    "embedding model":     ["minilm", "bge", "e5", "openai embedding",
                            "cohere embed", "sentence-transformers", "instructor"],
    "sparse retrieval":    ["bm25", "tf-idf", "splade", "sparse vector"],
    "reranking":           ["cross-encoder", "colbert", "reranker", "bi-encoder"],
    "llm":                 ["gpt", "claude", "gemini", "llama", "mistral",
                            "openai", "anthropic"],
    "chunking":            ["chunk", "splitting", "segmentation", "tokenization",
                            "text splitter"],
    "indexing":            ["hnsw", "ivf", "flat index", "annoy", "scann"],
    "retrieval strategy":  ["hybrid search", "semantic search", "keyword search",
                            "dense retrieval", "retrieval"],
    "evaluation":          ["ndcg", "mrr", "recall", "precision", "f1",
                            "hit rate", "map"],
}

# Dynamic concepts discovered from co-occurrence (mutable at runtime)
_dynamic_concepts: Dict[str, List[str]] = {}


# ---------------------------------------------------------------------------
# Derived lookups (rebuilt when dynamic concepts change)
# ---------------------------------------------------------------------------

def _build_inverted_index(
    concept_map: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """Build entity → [concepts] inverted index from a concept map."""
    inv: Dict[str, List[str]] = {}
    for concept, members in concept_map.items():
        for member in members:
            key = member.lower().strip()
            if key not in inv:
                inv[key] = []
            inv[key].append(concept)
    return inv


def _rebuild_index() -> None:
    """Rebuild the combined inverted index from static + dynamic maps."""
    global ENTITY_TO_CONCEPTS
    combined = {}
    combined.update(CONCEPT_MAP)
    combined.update(_dynamic_concepts)
    ENTITY_TO_CONCEPTS = _build_inverted_index(combined)


ENTITY_TO_CONCEPTS: Dict[str, List[str]] = _build_inverted_index(CONCEPT_MAP)


# ---------------------------------------------------------------------------
# Dynamic concept management
# ---------------------------------------------------------------------------

def register_dynamic_concepts(concepts: Dict[str, List[str]]) -> int:
    """
    Register dynamically discovered concepts.

    Replaces all previously registered dynamic concepts with the new set.

    Args:
        concepts: Dict mapping concept name → list of member entities.

    Returns:
        Number of concepts registered.
    """
    global _dynamic_concepts
    _dynamic_concepts = dict(concepts)
    _rebuild_index()
    return len(_dynamic_concepts)


def get_all_concepts() -> Dict[str, List[str]]:
    """
    Get combined static + dynamic concept map.

    Returns:
        Dict mapping concept name → list of member entities.
    """
    combined = {}
    combined.update(CONCEPT_MAP)
    combined.update(_dynamic_concepts)
    return combined


def get_dynamic_concepts() -> Dict[str, List[str]]:
    """Get only dynamically discovered concepts."""
    return dict(_dynamic_concepts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_concepts(entity: str) -> List[str]:
    """
    Get all parent concepts (static + dynamic) for an entity.

    Args:
        entity: Entity name (case-insensitive).

    Returns:
        List of concept names the entity belongs to.
        Empty list if entity is not in any concept group.
    """
    key = entity.lower().strip()

    # Direct lookup
    if key in ENTITY_TO_CONCEPTS:
        return list(ENTITY_TO_CONCEPTS[key])

    # Substring match: check if entity contains or is contained by a known member
    for member, concepts in ENTITY_TO_CONCEPTS.items():
        if member in key or key in member:
            return list(concepts)

    return []


def get_siblings(entity: str) -> List[str]:
    """
    Get sibling entities that share a concept with the given entity.

    Args:
        entity: Entity name (case-insensitive).

    Returns:
        List of sibling entity names (excluding the input entity).
    """
    key = entity.lower().strip()
    concepts = get_concepts(key)
    if not concepts:
        return []

    all_maps = get_all_concepts()
    siblings: Set[str] = set()
    for concept in concepts:
        for member in all_maps.get(concept, []):
            m = member.lower().strip()
            if m != key:
                siblings.add(m)

    return sorted(siblings)


def get_concept_members(concept: str) -> List[str]:
    """
    Get all members of a concept group (static or dynamic).

    Args:
        concept: Concept name (case-insensitive).

    Returns:
        List of entity names in the concept group.
    """
    key = concept.lower().strip()
    all_maps = get_all_concepts()
    return list(all_maps.get(key, []))


def get_concept_size(concept: str) -> int:
    """
    Get the number of members in a concept group.

    Args:
        concept: Concept name.

    Returns:
        Number of members, or 0 if concept doesn't exist.
    """
    key = concept.lower().strip()
    all_maps = get_all_concepts()
    return len(all_maps.get(key, []))
