import re
from typing import List, Set

from models.schemas.query import StructuredQuery

# Query type classification patterns (same as structured_analyzer)
_QUERY_TYPE_PATTERNS = {
    "LIST":        re.compile(r'\b(?:list|name\s*all|names|all\s+items|enumerate|what\s+are\s+the\s+types|types|show\s+all)\b', re.I),
    "FACTUAL":     re.compile(r'\b(?:what|which|who|when|where)\b', re.I),
    "PROCEDURAL":  re.compile(r'\b(?:how|steps?|process|procedure|method|guide|tutorial)\b', re.I),
    "COMPARISON":  re.compile(r'\b(?:compare|differ|versus|vs\.?|between|difference|contrast)\b', re.I),
    "CAUSAL":      re.compile(r'\b(?:why|cause|reason|because|result|effect|impact|consequence)\b', re.I),
}

# Deterministic synonym expansion dictionary
# Extend this dictionary as needed for domain-specific terms
SYNONYMS = {
    "embedding": ["vector", "representation", "encoding"],
    "search": ["retrieval", "lookup", "query", "find"],
    "document": ["file", "text", "doc", "page"],
    "chunk": ["segment", "fragment", "passage", "section"],
    "score": ["rank", "weight", "relevance"],
    "model": ["architecture", "network", "system"],
    "vector": ["embedding", "representation"],
    "retrieval": ["search", "lookup", "query"],
    "optimization": ["optimisation", "improvement", "enhancement"],
    "qdrant": ["vector database", "vector store"],
    "bm25": ["best matching 25", "ranking function"],
}

def expand_keywords(keywords: List[str]) -> List[str]:
    """
    Expand keywords with known synonyms (deterministic, no LLM).

    Args:
        keywords: Original list of keywords

    Returns:
        Extended list with synonyms added, deduplicated
    """
    expanded = list(keywords)
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in SYNONYMS:
            expanded.extend(SYNONYMS[kw_lower])
    # Deduplicate while preserving order (roughly)
    return list(dict.fromkeys(expanded))

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

def extract_entities(text: str) -> List[str]:
    """
    Extract capitalized words and quoted phrases as entities.

    Args:
        text: Input text to extract entities from

    Returns:
        List of unique entity strings
    """
    entities: Set[str] = set()

    # Extract quoted phrases
    quoted = re.findall(r'"([^"]+)"', text)
    entities.update(quoted)

    # Extract capitalized words (not at start of sentence, proper nouns/entities)
    # Match sequences of 2+ capital letters or title-case words
    capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    # Also catch acronyms with 2+ capital letters
    acronyms = re.findall(r'\b[A-Z]{2,}\b', text)

    entities.update(capitalized)
    entities.update(acronyms)

    return list(entities)

def extract_keywords(text: str) -> List[str]:
    """
    Extract lowercase keywords by removing stopwords and punctuation.

    Args:
        text: Input text to extract keywords from

    Returns:
        List of lowercase keyword strings
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

    keywords = [word for word in expanded_words if word not in STOPWORDS and len(word) > 1]

    return list(dict.fromkeys(keywords))

def _classify_query_type(query: str) -> str:
    """Classify query type using rule-based patterns."""
    for qtype, pattern in _QUERY_TYPE_PATTERNS.items():
        if pattern.search(query):
            return qtype
    return "FACTUAL"  # default


def analyze_query(raw_query: str) -> StructuredQuery:
    """
    Deterministic query analyzer - extracts entities, keywords, intent, and constraints.

    Args:
        raw_query: The user's raw query string

    Returns:
        StructuredQuery with extracted entities, keywords, expanded_keywords,
        intent, and constraints (empty constraints for backward compatibility)
    """
    entities = extract_entities(raw_query)
    keywords = extract_keywords(raw_query)
    expanded_keywords = expand_keywords(keywords)
    query_type = _classify_query_type(raw_query)
    constraints = {}  # Simple analyzer does not extract constraints

    return StructuredQuery(
        raw_query=raw_query,
        keywords=keywords,
        entities=entities,
        query_type=query_type,
        constraints=constraints,
        expanded_keywords=expanded_keywords
    )
