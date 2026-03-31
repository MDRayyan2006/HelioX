"""
Answer Composer: Converts adjudicated claims into structured final answer.

Takes adjudication output and produces a verifiable, citation-bound response
with extracted constraints from the original structured query.

Deterministic composition logic:
- Combine claims into coherent text
- Preserve claim-citation mapping
- Apply evidence threshold rules
"""

from typing import List, Dict, Any
import re
from core.logger import get_logger


from services.llm.groq_client import generate


def _coerce_evidence_blocks(citations: List[str], structured_query: Dict[str, Any]) -> List[str]:
    """Build evidence blocks from retrieved context first, then citation spans."""
    blocks: List[str] = []

    retrieved_context = structured_query.get("retrieved_context", [])
    if isinstance(retrieved_context, list):
        for item in retrieved_context:
            if isinstance(item, str) and item.strip():
                blocks.append(item.strip())
            elif isinstance(item, dict):
                text = (item.get("context_text") or item.get("text") or "").strip()
                if text:
                    blocks.append(text)

    if not blocks:
        for c in citations:
            if isinstance(c, str) and c.strip():
                blocks.append(c.strip())

    return blocks


def _extract_observation_answer(raw_query: str, evidence_blocks: List[str]) -> str:
    """
    Deterministically extract observation text for queries like "Observation 2".
    """
    match = re.search(r"\bobservation\s*[-:]?\s*(\d+)\b", raw_query.lower())
    if not match or not evidence_blocks:
        return ""

    obs_num = match.group(1)
    obs_pattern = re.compile(rf"\bobservation\s*[-:]?\s*{re.escape(obs_num)}\b", re.IGNORECASE)
    obs_any_pattern = re.compile(r"\bobservation\s*[-:]?\s*\d+\b", re.IGNORECASE)

    for block in evidence_blocks:
        block_clean = re.sub(r"\s+", " ", block).strip()
        if not block_clean:
            continue

        if obs_pattern.search(block_clean):
            # Prefer extracting until the next observation marker to avoid spillover.
            target = obs_pattern.search(block_clean)
            if target:
                next_obs = obs_any_pattern.search(block_clean, target.end())
                if next_obs:
                    candidate = block_clean[target.start():next_obs.start()].strip(" .;:-")
                else:
                    candidate = block_clean[target.start():].strip(" .;:-")
                if candidate:
                    sentences = [
                        s.strip() for s in re.split(r"(?<=[.!?])\s+", candidate)
                        if s.strip()
                    ]
                    if sentences:
                        return " ".join(sentences[:2]).strip()
                    return candidate

            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", block_clean) if s.strip()]
            for idx, sentence in enumerate(sentences):
                if obs_pattern.search(sentence):
                    # Include the next sentence when available for better completeness.
                    if idx + 1 < len(sentences):
                        next_sentence = sentences[idx + 1]
                        if re.search(r"\bobservation\s*[-:]?\s*\d+\b", next_sentence, re.IGNORECASE):
                            return sentence
                        return f"{sentence} {next_sentence}".strip()
                    return sentence

            # Fallback to a nearby window around the matched phrase.
            m = obs_pattern.search(block_clean)
            if m:
                start = max(0, m.start() - 80)
                end = min(len(block_clean), m.end() + 220)
                return block_clean[start:end].strip()

    return ""

def compose_answer(
    adjudication: Dict[str, Any],
    structured_query: Dict[str, Any],
    use_lightweight: bool = False
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

    # Evidence threshold: empty claims or low confidence
    if not final_claims or confidence < 0.3:
        logger.info(
            f"Insufficient evidence: "
            f"claims_empty={len(final_claims) == 0}, "
            f"confidence={confidence} < 0.3"
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

    # Attempt LLM Synthesis
    raw_query = structured_query.get("raw_query", "")

    # Pass richer retrieved context to the LLM when available.
    evidence_blocks = _coerce_evidence_blocks(citations, structured_query)
    evidence_text = "\n".join(f"- {c}" for c in evidence_blocks)

    # Deterministic exact extraction path for queries like "Observation 2".
    exact_observation_answer = _extract_observation_answer(raw_query, evidence_blocks)
    if exact_observation_answer:
        logger.info("Using deterministic observation extraction path")
        return {
            "answer": exact_observation_answer,
            "citations": citations,
            "confidence": round(confidence, 4),
            "constraints_applied": constraints_applied,
        }

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

    return {
        "answer": answer_text,
        "citations": citations,
        "confidence": round(confidence, 4),
        "constraints_applied": constraints_applied,
    }
