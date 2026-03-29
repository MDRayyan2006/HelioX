"""
Query Rewriter: Context-aware, intent-driven query refinement.

4-strategy approach (applied in priority order):
  1. Context-aware refinement — inject ungrounded concepts + entity boosts
  2. Intent rephrase — restructure query around missing concepts
  3. Synonym expansion — add related terms for missing keywords
  4. Broadening — remove restrictive phrases

Returns structured output with rewritten query and reason.

No LLM, no randomness. Deterministic string analysis.
"""

from typing import List, Dict, Optional, Any
import re

from core.logger import get_logger
from services.query.analyzer import analyze_query, STOPWORDS


# ---------------------------------------------------------------------------
# Intent classification patterns
# ---------------------------------------------------------------------------

_INTENT_PATTERNS = {
    "FACTUAL":     re.compile(r'\b(?:what|which|who|when|where)\b', re.I),
    "PROCEDURAL":  re.compile(r'\b(?:how|steps?|process|procedure|method)\b', re.I),
    "COMPARISON":  re.compile(r'\b(?:compare|differ|versus|vs\.?|between)\b', re.I),
    "CAUSAL":      re.compile(r'\b(?:why|cause|reason|because|result)\b', re.I),
}

# Common synonym map for retrieval expansion (domain-agnostic terms)
_SYNONYM_MAP = {
    "use":       ["utilize", "leverage", "employ"],
    "perform":   ["execute", "carry out", "run"],
    "search":    ["query", "lookup", "find"],
    "store":     ["save", "persist", "keep"],
    "create":    ["generate", "build", "produce"],
    "fast":      ["quick", "rapid", "efficient"],
    "error":     ["issue", "problem", "fault"],
    "config":    ["configuration", "setup", "settings"],
    "data":      ["information", "records", "content"],
    "method":    ["approach", "technique", "strategy"],
    "optimize":  ["improve", "enhance", "tune"],
    "retrieval": ["search", "fetching", "lookup"],
    "ranking":   ["scoring", "ordering", "sorting"],
    "embedding": ["vector", "representation", "encoding"],
}

# Phrases that restrict retrieval — removed during broadening
_RESTRICTIVE_PHRASES = [
    "specifically",
    "exactly",
    "only",
    "precisely",
    "in particular",
]


# ---------------------------------------------------------------------------
# Intent analysis
# ---------------------------------------------------------------------------

def _classify_intent(query: str) -> str:
    """Classify query intent: FACTUAL, PROCEDURAL, COMPARISON, or CAUSAL."""
    for intent, pattern in _INTENT_PATTERNS.items():
        if pattern.search(query):
            return intent
    return "FACTUAL"  # default


def _extract_missing_terms(issues: List[str]) -> List[str]:
    """Parse critic issues for missing key terms."""
    missing = []
    for issue in issues:
        match = re.search(r'Missing key terms?:\s*(.+)', issue, re.IGNORECASE)
        if match:
            terms = [t.strip() for t in match.group(1).split(',')]
            missing.extend(t for t in terms if t and len(t) > 1)
    return missing


def _extract_ungrounded_concepts(issues: List[str]) -> List[str]:
    """Parse critic issues for ungrounded sentence fragments."""
    concepts = []
    for issue in issues:
        match = re.search(r'Ungrounded sentence:\s*"(.+?)\.{3}"', issue)
        if match:
            # Extract key nouns from the ungrounded sentence
            words = match.group(1).lower().split()
            concepts.extend(
                w for w in words
                if w not in STOPWORDS and len(w) > 3
            )
    return concepts


def _has_completeness_issue(issues: List[str]) -> bool:
    """Check if critic flagged incomplete coverage of query segments."""
    return any("not fully address" in issue for issue in issues)


# ---------------------------------------------------------------------------
# Rewrite strategies
# ---------------------------------------------------------------------------

def _strategy_intent_rephrase(
    query: str,
    intent: str,
    missing_terms: List[str]
) -> str:
    """
    Strategy 1: Rephrase query to foreground missing concepts.

    Instead of just appending keywords, restructure the query to place
    missing terms in a context the retriever is more likely to match.
    """
    if not missing_terms:
        return ""

    # Deduplicate
    seen = set()
    unique = []
    query_lower = query.lower()
    for t in missing_terms:
        tl = t.lower()
        if tl not in seen and tl not in query_lower:
            seen.add(tl)
            unique.append(t)

    if not unique:
        return ""

    terms_str = " ".join(unique)

    # Build a rephrase based on intent type
    if intent == "PROCEDURAL":
        return f"{query} including {terms_str} process"
    elif intent == "COMPARISON":
        return f"{query} comparing {terms_str}"
    elif intent == "CAUSAL":
        return f"{query} explaining {terms_str}"
    else:  # FACTUAL
        return f"{query} {terms_str}"


def _strategy_synonym_expand(query: str, missing_terms: List[str]) -> str:
    """
    Strategy 2: Expand query with synonyms of missing terms.

    Adds 1 synonym per missing term to increase retrieval recall
    without bloating the query.
    """
    expansions = []
    query_lower = query.lower()

    for term in missing_terms:
        term_lower = term.lower()
        if term_lower in _SYNONYM_MAP:
            # Pick first synonym not already in query
            for syn in _SYNONYM_MAP[term_lower]:
                if syn.lower() not in query_lower:
                    expansions.append(syn)
                    break

    if not expansions:
        return ""

    return f"{query} {' '.join(expansions)}"


def _strategy_broaden(query: str) -> str:
    """
    Strategy 3: Remove restrictive phrases to widen retrieval.
    """
    broadened = query
    for phrase in _RESTRICTIVE_PHRASES:
        broadened = re.sub(
            rf'\b{re.escape(phrase)}\b', '', broadened, flags=re.IGNORECASE
        )
    broadened = re.sub(r'\s+', ' ', broadened).strip()
    return broadened if broadened != query else ""


# ---------------------------------------------------------------------------
# Strategy 4: Context-aware refinement (NEW)
# ---------------------------------------------------------------------------

def _strategy_context_aware(
    query: str,
    issues: List[str],
    context: Dict[str, Any],
) -> str:
    """
    Strategy 4: Use adjudication + critic context for targeted refinement.

    Injects:
      - Key nouns from ungrounded sentences
      - Performance-weighted entity boosts from session memory
        (skips entities with negative scores — they led to failures)
      - Concepts from conflicting claims
    """
    additions: List[str] = []
    query_lower = query.lower()

    # 1. Extract concepts from ungrounded sentences
    ungrounded = context.get("ungrounded_sentences", [])
    for ug in ungrounded:
        # Parse the issue string for the quoted sentence
        match = re.search(r'Ungrounded sentence:\s*"(.+?)\.{3}"', ug)
        if match:
            words = match.group(1).lower().split()
            for w in words:
                if (w not in STOPWORDS and len(w) > 3
                        and w not in query_lower and w not in additions):
                    additions.append(w)
                    if len(additions) >= 3:
                        break
        if len(additions) >= 3:
            break

    # 2. Inject boosted entities — skip penalized ones (negative scores)
    entity_boosts = context.get("entity_boosts", {})
    for entity, boost in sorted(
        entity_boosts.items(), key=lambda x: x[1], reverse=True
    ):
        if boost <= 0:
            continue  # skip penalized entities
        if entity not in query_lower and entity not in additions:
            additions.append(entity)
            if len(additions) >= 5:
                break

    # 3. Inject high-importance concept names (generalized terms)
    # Prefer concept_importance if available; fall back to concept_scores
    concept_importance = context.get("concept_importance")
    if not concept_importance:
        concept_importance = context.get("concept_scores", {})
    for concept, cscore in sorted(
        concept_importance.items(), key=lambda x: x[1], reverse=True
    ):
        if cscore <= 0:
            continue  # skip low-importance concepts
        if concept not in query_lower and concept not in additions:
            additions.append(concept)
            if len(additions) >= 7:
                break

    # 3b. Exploration forced concept: inject a moderate-importance concept
    # to diversify exploration (overrides normal ordering if present)
    forced_concept = context.get("forced_concept")
    if forced_concept and forced_concept not in query_lower and forced_concept not in additions:
        additions.append(forced_concept)
        # Don't count against the limit; exploration is prioritized

    # 4. If conflicts detected, add "differences" or "comparison" hint
    if context.get("conflicts_detected") and "compar" not in query_lower:
        additions.append("differences")

    if not additions:
        return ""

    return f"{query} {' '.join(additions)}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def rewrite_query(
    original_query: str,
    issues: List[str],
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Rewrite a query using context-aware, intent-driven analysis.

    Applies strategies in order of specificity:
        1. Context-aware refinement (if context provided)
        2. Intent rephrase — restructure around missing concepts
        3. Synonym expansion — add related terms for missed keywords
        4. Broadening — remove restrictive phrases (if routing allows)
        5. Fallback — return original unchanged

    Args:
        original_query: The query from the previous attempt
        issues: List of issue strings from CriticOutput.issues
        context: Optional dict with:
            - adjudication_claims: List[str]
            - ungrounded_sentences: List[str]
            - conflicts_detected: bool
            - entity_boosts: Dict[str, float]
            - allow_broaden: bool

    Returns:
        Dict with:
            - rewritten_query: str — the improved query
            - reason: str — why this rewrite was chosen
    """
    logger = get_logger("REWRITER")
    logger.info(f"Rewriting query: {original_query[:60]}...")
    logger.info(f"Issues to address: {len(issues)}")

    result_unchanged = {
        "rewritten_query": original_query,
        "reason": "no rewrite needed",
    }

    if not issues:
        logger.info("No issues to address")
        return result_unchanged

    ctx = context or {}

    # --- Analyze ---
    intent = _classify_intent(original_query)
    missing_terms = _extract_missing_terms(issues)
    has_completeness_gap = _has_completeness_issue(issues)

    logger.info(f"Intent: {intent}, missing terms: {missing_terms}, "
                f"completeness gap: {has_completeness_gap}")

    # --- LLM Enhancement: Groq API Rewrite (if confidence < 0.6) ---
    confidence = ctx.get("confidence", 1.0)
    if confidence < 0.6:
        logger.info(f"Confidence {confidence} < 0.6. Attempting Groq API rewrite.")
        try:
            from services.llm.groq_client import generate
            issues_text = "\n".join(issues)
            prompt = (
                f"Rewrite this query for better search retrieval.\n"
                f"Original query: {original_query}\n"
                f"Issues found:\n{issues_text}\n"
                f"Return ONLY the rewritten query text."
            )
            llm_rewritten = generate(prompt)
            if llm_rewritten:
                logger.info(f"LLM rewrite successful: {llm_rewritten[:80]}...")
                return {
                    "rewritten_query": llm_rewritten,
                    "reason": "llm_enhancement: groq rewrite due to low confidence",
                }
            else:
                logger.warning("LLM rewrite empty or unavailable. Falling back to deterministic.")
        except Exception as e:
            logger.warning(f"LLM rewrite failed ({e}). Falling back to deterministic.")

    # --- Strategy 1: Context-aware refinement (highest priority) ---
    if ctx:
        refined = _strategy_context_aware(original_query, issues, ctx)
        if refined:
            logger.info(f"Strategy 1 (context-aware): {refined[:80]}...")
            return {
                "rewritten_query": refined,
                "reason": "context-aware: injected ungrounded concepts / entity boosts",
            }

    # --- Strategy 2: Intent rephrase ---
    if missing_terms:
        rephrased = _strategy_intent_rephrase(
            original_query, intent, missing_terms
        )
        if rephrased:
            logger.info(f"Strategy 2 (intent rephrase): {rephrased[:80]}...")
            return {
                "rewritten_query": rephrased,
                "reason": f"intent-rephrase ({intent}): foregrounded "
                          f"missing concepts [{', '.join(missing_terms[:3])}]",
            }

    # --- Strategy 3: Synonym expansion ---
    if missing_terms:
        expanded = _strategy_synonym_expand(original_query, missing_terms)
        if expanded:
            logger.info(f"Strategy 3 (synonym expand): {expanded[:80]}...")
            return {
                "rewritten_query": expanded,
                "reason": "synonym-expand: added related terms for "
                          f"[{', '.join(missing_terms[:3])}]",
            }

    # --- Strategy 4: Broaden (gated by routing hints) ---
    allow_broaden = ctx.get("allow_broaden", True)
    if allow_broaden:
        broadened = _strategy_broaden(original_query)
        if broadened:
            logger.info(f"Strategy 4 (broaden): {broadened[:80]}...")
            return {
                "rewritten_query": broadened,
                "reason": "broadened: removed restrictive phrases",
            }

    # --- Fallback ---
    logger.info("No applicable strategy, returning original")
    return result_unchanged
