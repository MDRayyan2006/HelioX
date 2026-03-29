"""
Answer Composer: Converts adjudicated claims into structured final answer.

Takes adjudication output and produces a verifiable, citation-bound response
with extracted constraints from the original structured query.

Deterministic composition logic:
- Combine claims into coherent text
- Preserve claim-citation mapping
- Apply evidence threshold rules
"""

from typing import List, Dict, Any, Optional
import re
from core.logger import get_logger


from services.llm.groq_client import generate

def compose_answer(
    adjudication: Dict[str, Any],
    structured_query: Dict[str, Any],
    use_lightweight: bool = False,
    chunks: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Convert adjudicated worker outputs into a structured final answer.

    Args:
        adjudication: Output from adjudicator containing:
            - final_claims: List[str]
            - citations: List[str]
            - confidence: float
            - conflicts_detected: bool
        structured_query: Parsed query structure containing:
            - constraints: Dict[str, Optional[str]]
            - raw_query: str
        use_lightweight: If True, use the lightweight Groq model (llama-3.1-8b-instant)
                        with its dedicated API key. If False, use the default multi-agent model.

    Returns:
        Dict with:
            - answer: str (combined claims or "Insufficient evidence")
            - citations: List[str] (aligned with claims)
            - confidence: float (from adjudication)
            - constraints_applied: List[str] (extracted from query.constraints)
    """
    logger = get_logger("ANSWER_COMPOSER")
    logger.info("Composing final answer from adjudicated claims")

    # Extract adjudication data
    final_claims = adjudication.get("final_claims", [])
    citations = adjudication.get("citations", [])
    confidence = adjudication.get("confidence", 0.0)

    logger.info(f"Input: {len(final_claims)} claims, confidence={confidence}")

    # Ensure claim-citation alignment without truncating valuable claims
    if len(final_claims) != len(citations):
        logger.warning(
            f"Claim-citation mismatch: {len(final_claims)} claims, "
            f"{len(citations)} citations. Padding citations."
        )
        while len(citations) < len(final_claims):
            citations.append("Uncited supporting segment.")

    # Evidence threshold: empty claims (completely missed)
    if not final_claims:
        logger.info(
            f"Insufficient evidence: "
            f"claims_empty={len(final_claims) == 0}"
        )
        return {
            "answer": "Insufficient evidence",
            "citations": [],
            "confidence": 0.0,
            "constraints_applied": [],
        }

    # Extract constraints from structured query
    constraints = structured_query.get("constraints", {})
    constraints_applied = []
    for key, value in constraints.items():
        if value:
            constraints_applied.append(f"{key}: {value}")
        else:
            constraints_applied.append(key)
    logger.info(f"Constraints applied: {constraints_applied}")

    # ----------------------------------
    # Deterministic Fast Paths (skip LLM)
    # ----------------------------------
    query_type = structured_query.get("query_type", "FACTUAL")
    raw_query = structured_query.get("raw_query", "")

    # Path 1: Very high confidence + single claim → direct answer
    if confidence >= 0.85 and len(final_claims) == 1:
        logger.info(f"High confidence single claim, skipping LLM. Answer: {final_claims[0][:80]}...")
        return {
            "answer": final_claims[0],
            "citations": citations[:1],
            "confidence": confidence,
            "constraints_applied": constraints_applied,
        }

    # Path 2: LIST queries → deterministic aggregation from actual chunk text
    if query_type == "LIST":
        items = []
        # Extract items from actual chunk content, not meta-claims
        source_texts = []
        if chunks:
            source_texts = [c.get('text', '') for c in chunks if c.get('text')]
        if not source_texts:
            source_texts = final_claims  # fallback to claims if no chunks

        for text in source_texts:
            # Split into sentences and extract meaningful items
            sents = re.split(r'[.!?]+', text)
            for sent in sents:
                sent = sent.strip()
                if not sent or len(sent) < 5:
                    continue
                # Remove common meta-prefixes
                cleaned = sent
                for prefix in ["This chunk discusses ", "This chunk covers ",
                               "This chunk is about ", "Found: "]:
                    if cleaned.startswith(prefix):
                        cleaned = cleaned[len(prefix):]
                cleaned = cleaned.strip()
                if cleaned:
                    # Split on commas, semicolons, and 'and' for list items
                    parts = re.split(r'[,;]|\sand\s', cleaned)
                    for part in parts:
                        part = part.strip(" .\"'")
                        # Keep only substantive items (not too short, not full sentences over 100 chars)
                        if part and 3 < len(part) < 100:
                            items.append(part)

        # Deduplicate by normalized form while preserving best casing
        seen_lower = {}
        for item in items:
            key = item.lower().strip()
            if key not in seen_lower or len(item) > len(seen_lower[key]):
                seen_lower[key] = item
        unique_items = sorted(seen_lower.values(), key=lambda x: x.lower())

        if unique_items:
            answer_text = "Found: " + ", ".join(unique_items) + "."
            logger.info(f"Deterministic LIST answer with {len(unique_items)} items")
            return {
                "answer": answer_text,
                "citations": citations,
                "confidence": confidence,
                "constraints_applied": constraints_applied,
            }
        else:
            logger.warning("LIST query but no items extracted; falling back to LLM")

    # ----------------------------------
    # LLM Synthesis Path
    # ----------------------------------
    # Pass full chunk content as evidence for LLM synthesis (not single-sentence citations)
    if chunks:
        evidence_text = "\n\n".join(
            f"[{i+1}] {c.get('text', '')}" for i, c in enumerate(chunks) if c.get('text')
        )
    else:
        # Fallback to citations if no chunks provided
        evidence_text = "\n".join(f"- {c}" for c in citations)

    prompt = f"""
You are HelioX, an advanced adaptive RAG assistant designed to produce highly accurate and reliable answers.

========================
CORE OBJECTIVE
========================
Your task is to:
1. Understand the user query deeply
2. Analyze the quality and relevance of retrieved evidence
3. Decide the best answering strategy:
   - Direct Answer (if evidence is clear and sufficient)
   - Multi-step Reasoning (if query is complex)
   - Retrieval Correction (if evidence is weak, incomplete, or irrelevant)
4. Generate a precise and correct final answer

========================
RETRIEVAL ANALYSIS
========================
Before answering, evaluate:
- Is the evidence relevant to the query?
- Is it complete enough to answer confidently?
- Are there contradictions?

If evidence is:
- STRONG → Use it directly
- PARTIAL → Fill gaps with reasoning (but stay grounded)
- WEAK/IRRELEVANT → Acknowledge uncertainty and rely on general knowledge carefully

========================
REASONING STRATEGY
========================
- Break complex queries into sub-parts
- Cross-check multiple evidence chunks
- Prefer factual consistency over verbosity
- Avoid hallucination at all costs

========================
OUTPUT RULES (VERY IMPORTANT)
========================
- You MUST enclose ONLY the final answer inside <final_answer> tags
- Do NOT include reasoning inside <final_answer>
- Do NOT use markdown inside <final_answer>
- Keep the answer clear, structured, and concise

========================
FAILSAFE BEHAVIOR
========================
If evidence is insufficient:
- Say clearly that information is incomplete
- Provide the best possible answer without guessing blindly

========================
INPUT
========================
User Query:
{raw_query}

Retrieved Evidence:
{evidence_text}

========================
PROCESS (INTERNAL)
========================
Think step-by-step:
- Query understanding
- Evidence validation
- Strategy selection
- Answer synthesis

(Do NOT include this process in final output)

========================
FINAL OUTPUT FORMAT
========================
<final_answer>
Your final answer here
</final_answer>
"""

    answer_text = None
    try:
        logger.info("Attempting LLM answer synthesis...")
        import re

        # Choose API credentials based on mode
        if use_lightweight:
            from core.config import get_config
            cfg = get_config()
            api_key = cfg.groq_lightweight_api_key
            model = cfg.groq_lightweight_model
            logger.info(f"Using lightweight model: {model}")
        else:
            api_key = None  # Will use default from config.groq_api_key
            model = None     # Will use config.groq_model
            logger.info("Using multi-agent model")

        raw_response = generate(prompt, api_key=api_key, model=model)
        if raw_response:
            # Extract whatever is inside <final_answer> tags
            match = re.search(r'<final_answer>(.*?)</final_answer>', raw_response, re.DOTALL | re.IGNORECASE)
            if match:
                answer_text = match.group(1).strip()
            else:
                # Fallback if the LLM forgot the tags
                answer_text = raw_response.strip()
    except Exception as e:
        logger.error(f"LLM synthesis failed: {e}")

    # Fallback to deterministic concatenation if LLM fails
    if not answer_text:
        logger.info("Falling back to deterministic claim concatenation.")
        if len(final_claims) == 1:
            answer_text = final_claims[0]
        else:
            # Build paragraph from multiple claims
            sentences = []
            for i, claim in enumerate(final_claims):
                # Ensure claim ends with punctuation
                claim_clean = claim.rstrip()
                if not claim_clean.endswith(('.', '!', '?')):
                    claim_clean += '.'
                sentences.append(claim_clean)
            answer_text = ' '.join(sentences)

    logger.info(f"Composed answer: {len(answer_text)} characters")

    # Citation alignment check (pre‑emptive)
    if citations and answer_text:
        # Simple bigram overlap per sentence
        def _bigrams(text: str) -> set:
            words = re.findall(r'\w+', text.lower())
            return set(zip(words, words[1:])) if len(words) >= 2 else set()
        answer_sents = re.split(r'[.!?]+', answer_text)
        unaligned = []
        for sent in answer_sents:
            sent = sent.strip()
            if not sent:
                continue
            sent_bigrams = _bigrams(sent)
            if not sent_bigrams:
                continue
            # Check overlap with any citation
            aligned = any(bool(sent_bigrams & _bigrams(cite)) for cite in citations)
            if not aligned:
                unaligned.append(sent[:80])
        if unaligned:
            logger.warning(f"{len(unaligned)} answer sentences have weak citation support: {unaligned}")
            # Could regenerate or adjust, but for now we just log

    return {
        "answer": answer_text,
        "citations": citations,
        "confidence": round(confidence, 4),
        "constraints_applied": constraints_applied,
    }
