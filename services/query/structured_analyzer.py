"""
Structured Query Analyzer: Analyzes raw queries into structured representations.

Features:
- Intent classification (rule-based): FACTUAL, PROCEDURAL, COMPARISON, CAUSAL
- Entity extraction (capitalized words, quoted phrases, acronyms)
- Keyword extraction (stopword removal, normalization)
- Constraint extraction (temporal, domain, filters)

Replaces the Planner in Phase 4A with deterministic, intent-aware analysis.
"""

import re
from typing import List, Dict, Optional, Set
from core.logger import get_logger
from models.schemas.query import StructuredQuery

logger = get_logger("STRUCTURED_ANALYZER")

# ---------------------------------------------------------------------------
# Query type classification patterns
# ---------------------------------------------------------------------------
QUERY_TYPE_PATTERNS = {
    "LIST":        re.compile(r'\b(?:list|name\s*all|names|all\s+items|enumerate|what\s+are\s+the\s+types|types|show\s+all)\b', re.I),
    "FACTUAL":     re.compile(r'\b(?:what|which|who|when|where)\b', re.I),
    "PROCEDURAL":  re.compile(r'\b(?:how|steps?|process|procedure|method|guide|tutorial)\b', re.I),
    "COMPARISON":  re.compile(r'\b(?:compare|differ|versus|vs\.?|between|difference|contrast)\b', re.I),
    "CAUSAL":      re.compile(r'\b(?:why|cause|reason|because|result|effect|impact|consequence)\b', re.I),
}

# ---------------------------------------------------------------------------
# Temporal constraint patterns
# ---------------------------------------------------------------------------
TEMPORAL_PATTERNS = {
    "latest": ["latest", "recent", "newest", "current", "today", "now"],
    "historical": ["historical", "past", "old", "previous", "former", "earlier"],
    "future": ["future", "upcoming", "planned", "scheduled", "next"],
    "specific_period": re.compile(r'\b(?:in|during|since|before|after)\s+\d{4}\b', re.I),
    "relative_time": re.compile(r'\b\d+\s+(?:days?|weeks?|months?|years?)\s+(?:ago|from now)\b', re.I),
}

# ---------------------------------------------------------------------------
# Filter patterns (restrictive words)
# ---------------------------------------------------------------------------
FILTER_WORDS = {
    "only", "exactly", "specifically", "precisely", "just", "solely",
    "excluding", "without", "except", "not", "never"
}

# Domain keywords (can be extended)
DOMAIN_KEYWORDS = {
    "technical": ["code", "api", "database", "server", "architecture", "implementation"],
    "business": ["revenue", "cost", "market", "customer", "strategy", "performance"],
    "analysis": ["metrics", "data", "report", "statistics", "trends", "analysis"],
}

# ---------------------------------------------------------------------------
# Stopwords (from existing analyzer)
# ---------------------------------------------------------------------------
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

# Synonym expansion dictionary (from existing analyzer)
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


def _classify_query_type(query: str) -> str:
    """Classify query type using rule-based patterns."""
    query_lower = query.lower()
    for qtype, pattern in QUERY_TYPE_PATTERNS.items():
        if pattern.search(query):
            logger.debug(f"Query type matched: {qtype} (pattern: {pattern.pattern})")
            return qtype
    logger.debug("No query type pattern matched, defaulting to FACTUAL")
    return "FACTUAL"


def _extract_entities(text: str) -> List[str]:
    """Extract capitalized words and quoted phrases as entities."""
    entities: Set[str] = set()

    # Extract quoted phrases
    quoted = re.findall(r'"([^"]+)"', text)
    entities.update(quoted)

    # Extract capitalized words (proper nouns/entities)
    capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    # Acronyms with 2+ capital letters
    acronyms = re.findall(r'\b[A-Z]{2,}\b', text)

    entities.update(capitalized)
    entities.update(acronyms)

    return list(entities)


def _extract_keywords(text: str) -> List[str]:
    """Extract lowercase keywords by removing stopwords and punctuation."""
    # Convert to lowercase and remove punctuation
    normalized = re.sub(r'[^\w\s]', ' ', text.lower())
    # Split into words and filter stopwords
    words = normalized.split()
    keywords = [word for word in words if word not in STOPWORDS and len(word) > 1]
    return keywords


def _extract_temporal_constraint(query: str) -> Optional[str]:
    """Extract temporal constraint from query."""
    query_lower = query.lower()

    # Check for explicit temporal keywords
    for constraint_type, patterns in TEMPORAL_PATTERNS.items():
        if isinstance(patterns, list):
            if any(keyword in query_lower for keyword in patterns):
                logger.debug(f"Temporal constraint detected: {constraint_type}")
                return constraint_type
        elif isinstance(patterns, re.Pattern):
            if patterns.search(query):
                logger.debug(f"Temporal constraint detected: {constraint_type}")
                return constraint_type

    return None


def _extract_domain_constraint(query: str) -> Optional[str]:
    """Detect domain constraint based on keyword overlap."""
    query_lower = query.lower()
    words = set(query_lower.split())

    best_domain = None
    best_score = 0

    for domain, keywords in DOMAIN_KEYWORDS.items():
        overlap = words.intersection(set(keywords))
        score = len(overlap)
        if score > best_score:
            best_score = score
            best_domain = domain

    if best_score >= 1:
        logger.debug(f"Domain constraint detected: {best_domain} (score: {best_score})")
        return best_domain

    return None


def _extract_filter_constraints(query: str) -> List[str]:
    """Extract filter constraints (restrictive words like 'only', 'exactly')."""
    query_lower = query.lower()
    filters = [word for word in FILTER_WORDS if word in query_lower]
    if filters:
        logger.debug(f"Filter constraints detected: {filters}")
    return filters


def _expand_keywords(keywords: List[str]) -> List[str]:
    """Expand keywords with known synonyms (deterministic)."""
    expanded = list(keywords)
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in SYNONYMS:
            expanded.extend(SYNONYMS[kw_lower])
    # Deduplicate while preserving order
    return list(dict.fromkeys(expanded))


def analyze_query(raw_query: str) -> StructuredQuery:
    """
    Analyze raw query into structured representation with intent and constraints.

    Args:
        raw_query: The user's raw query string

    Returns:
        StructuredQuery with raw_query, keywords, entities, intent, constraints, and expanded_keywords
    """
    logger.info(f"Analyzing query: {raw_query[:80]}...")

    # Extract core components
    entities = _extract_entities(raw_query)
    keywords = _extract_keywords(raw_query)

    # Classify query type
    query_type = _classify_query_type(raw_query)

    # Extract constraints
    constraints = {
        "temporal": _extract_temporal_constraint(raw_query),
        "domain": _extract_domain_constraint(raw_query),
        "filters": _extract_filter_constraints(raw_query),
    }
    # Remove None values from constraints
    constraints = {k: v for k, v in constraints.items() if v is not None and v != []}

    # Expand keywords
    expanded_keywords = _expand_keywords(keywords)

    logger.info(f"Analysis complete: query_type={query_type}, entities={len(entities)}, "
                f"keywords={len(keywords)}, constraints={list(constraints.keys())}")

    return StructuredQuery(
        raw_query=raw_query,
        keywords=keywords,
        entities=entities,
        query_type=query_type,
        constraints=constraints,
        expanded_keywords=expanded_keywords
    )
