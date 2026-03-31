"""
Enhanced Query Analyzer: Improved query understanding with semantic expansion
and intent-aware processing for better context retrieval.
"""

import re
from typing import List, Set, Dict, Any
from models.schemas.query import StructuredQuery

# Enhanced query type classification with more granular patterns
_QUERY_TYPE_PATTERNS = {
    "LIST":        re.compile(r'\b(?:list|name\s*all|names|all\s+items|enumerate|what\s+are\s+the\s+types|types|show\s+all)\b', re.I),
    "FACTUAL":     re.compile(r'\b(?:what|which|who|when|where|name|identify)\b', re.I),
    "PROCEDURAL":  re.compile(r'\b(?:how|steps?|process|procedure|method|guide|tutorial|way to|technique)\b', re.I),
    "COMPARISON":  re.compile(r'\b(?:compare|differ|versus|vs\.?|between|difference|contrast|better|worse|advantage|disadvantage)\b', re.I),
    "CAUSAL":      re.compile(r'\b(?:why|cause|reason|because|result|effect|impact|consequence|lead to|due to)\b', re.I),
    "EXPLORATORY": re.compile(r'\b(?:explain|describe|overview|summary|introduction|basics|fundamentals|what is|tell me about)\b', re.I),
    "RELATIONAL":  re.compile(r'\b(?:relationship|connection|link|association|correlate|interact|influence|affect)\b', re.I),
}

# Extended synonym dictionary with semantic groupings
SEMANTIC_SYNONYMS = {
    # Core retrieval concepts
    "search": ["retrieval", "lookup", "query", "find", "locate", "discover"],
    "vector": ["embedding", "representation", "encoding", "feature"],
    "document": ["file", "text", "doc", "page", "content", "paper"],
    "chunk": ["segment", "fragment", "passage", "section", "piece", "block"],
    "score": ["rank", "weight", "relevance", "importance", "similarity"],
    "model": ["architecture", "network", "system", "framework", "approach"],
    "optimization": ["optimisation", "improvement", "enhancement", "refinement", "tuning"],

    # Technical terms
    "qdrant": ["vector database", "vector store", "similarity search", "ann"],
    "bm25": ["best matching 25", "ranking function", "tf-idf", "sparse retrieval"],
    "embedding": ["vector", "representation", "encoding", "feature vector"],
    "rerank": ["re-rank", "re-scoring", "cross-encoder", "precision"],

    # Process terms
    "pipeline": ["workflow", "process", "stage", "step", "flow"],
    "analysis": ["examination", "study", "investigation", "evaluation", "assessment"],
    "method": ["approach", "technique", "procedure", "technique", "way"],
}

# Domain-specific expansions (can be extended)
DOMAIN_TERMS = {
    "machine learning": ["ml", "deep learning", "neural network", "ai", "artificial intelligence"],
    "database": ["db", "data store", "storage", "repository"],
    "algorithm": ["algo", "method", "technique", "approach"],
}

# Intent-based weighting for different retrieval components
QUERY_TYPE_WEIGHTS = {
    "LIST": {"vector": 0.5, "entity": 0.3, "keyword": 0.2},
    "FACTUAL": {"vector": 0.8, "entity": 0.15, "keyword": 0.05},
    "PROCEDURAL": {"vector": 0.6, "entity": 0.2, "keyword": 0.2},
    "COMPARISON": {"vector": 0.5, "entity": 0.3, "keyword": 0.2},
    "CAUSAL": {"vector": 0.6, "entity": 0.25, "keyword": 0.15},
    "EXPLORATORY": {"vector": 0.7, "entity": 0.2, "keyword": 0.1},
    "RELATIONAL": {"vector": 0.5, "entity": 0.3, "keyword": 0.2},
}

# Common English stopwords to filter out during keyword extraction
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "i", "you", "he", "she", "it",
    "we", "they", "what", "which", "who", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "but", "also", "if", "then", "from", "into", "about",
    "through", "during", "before", "after", "above", "below", "between"
}


def expand_keywords_semantic(keywords: List[str]) -> List[str]:
    """
    Expand keywords with semantic synonyms and domain-specific terms.

    Args:
        keywords: Original list of keywords

    Returns:
        Extended list with semantic expansions added, deduplicated
    """
    expanded = list(keywords)
    for kw in keywords:
        kw_lower = kw.lower()
        # Add semantic synonyms
        if kw_lower in SEMANTIC_SYNONYMS:
            expanded.extend(SEMANTIC_SYNONYMS[kw_lower])
        # Add domain-specific expansions
        for domain, terms in DOMAIN_TERMS.items():
            if kw_lower in domain or kw_lower in terms:
                expanded.extend([domain] + terms)
                break
    # Deduplicate while preserving order (roughly)
    return list(dict.fromkeys(expanded))


def extract_entities_enhanced(text: str) -> List[str]:
    """
    Enhanced entity extraction with semantic grouping and normalization.

    Args:
        text: Input text to extract entities from

    Returns:
        List of unique entity strings with semantic normalization
    """
    entities = set()

    # Extract quoted phrases
    quoted = re.findall(r'"([^"]+)"', text)
    entities.update(quoted)

    # Extract capitalized words (proper nouns/entities)
    capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    # Also catch acronyms with 2+ capital letters
    acronyms = re.findall(r'\b[A-Z]{2,}\b', text)

    entities.update(capitalized)
    entities.update(acronyms)

    # Semantic normalization: map common variations to canonical forms
    normalized_entities = set()
    for entity in entities:
        entity_lower = entity.lower()
        # Check if it's a variation of a known domain term
        normalized = entity  # default to original
        for canonical, variations in DOMAIN_TERMS.items():
            if entity_lower in [canonical] + [v.lower() for v in variations]:
                normalized = canonical
                break
        normalized_entities.add(normalized)

    return list(normalized_entities)


def extract_keywords_enhanced(text: str) -> List[str]:
    """
    Enhanced keyword extraction with stemming and importance scoring.

    Args:
        text: Input text to extract keywords from

    Returns:
        List of lowercase keyword strings with enhanced filtering
    """
    # Convert to lowercase and remove punctuation
    normalized = re.sub(r'[^\w\s]', ' ', text.lower())

    words = normalized.split()
    expanded_words: List[str] = []
    for word in words:
        expanded_words.append(word)
        parts = re.findall(r"[a-z]+|\d+", word)
        if len(parts) > 1:
            expanded_words.extend(parts)

    keywords = [word for word in expanded_words if word not in STOPWORDS and len(word) > 2]

    # Boost important technical terms (simple heuristic)
    important_terms = []
    for word in keywords:
        # Give extra weight to technical terms by duplicating them
        if len(word) > 5 or word in SEMANTIC_SYNONYMS:
            important_terms.extend([word, word])  # Duplicate for emphasis
        else:
            important_terms.append(word)

    return list(dict.fromkeys(important_terms))


def _classify_query_type_enhanced(query: str) -> str:
    """Classify query type using enhanced rule-based patterns."""
    qtype_scores = {}

    for qtype, pattern in _QUERY_TYPE_PATTERNS.items():
        matches = len(pattern.findall(query))
        if matches > 0:
            qtype_scores[qtype] = matches

    # Return query_type with highest score, default to FACTUAL
    if qtype_scores:
        return max(qtype_scores, key=qtype_scores.get)
    return "FACTUAL"


def analyze_query_enhanced(raw_query: str) -> StructuredQuery:
    """
    Enhanced deterministic query analyzer with semantic understanding.

    Args:
        raw_query: The user's raw query string

    Returns:
        StructuredQuery with enhanced entities, keywords, expanded_keywords,
        intent, and intent-aware constraints
    """
    entities = extract_entities_enhanced(raw_query)
    keywords = extract_keywords_enhanced(raw_query)
    expanded_keywords = expand_keywords_semantic(keywords)
    query_type = _classify_query_type_enhanced(raw_query)

    # Generate intent-based constraints for downstream processing
    constraints = {
        "intent": query_type,
        "intent_weights": QUERY_TYPE_WEIGHTS.get(query_type, QUERY_TYPE_WEIGHTS["FACTUAL"]),
        "query_length": len(raw_query.split()),
        "has_technical_terms": any(
            term in raw_query.lower()
            for term in SEMANTIC_SYNONYMS.keys()
        )
    }

    return StructuredQuery(
        raw_query=raw_query,
        keywords=keywords,
        entities=entities,
        query_type=query_type,
        constraints=constraints,
        expanded_keywords=expanded_keywords
    )