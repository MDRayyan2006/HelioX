import os
from agents.query_rewriter import rewrite_query

class MockCriticOutput:
    pass

# Mock data
issues = ["Missing key terms: AI, Database", "Ungrounded sentence: \"The database is scalable...\""]

ctx = {
    "confidence": 0.4, # Should trigger LLM
    "adjudication_claims": [],
    "ungrounded_sentences": issues,
    "conflicts_detected": False,
    "entity_boosts": {},
    "chunk_scores": {},
    "concept_scores": {},
    "concept_importance": {},
    "memory_quality": 0.8,
    "allow_broaden": True,
}

from dotenv import load_dotenv
load_dotenv()

print("Running test WITH GROQ_API_KEY...")

result = rewrite_query("Test Original Query", issues, context=ctx)
print("\nFinal Rewritten Reason:")
print(result["reason"])
print("Final Query:")
print(result["rewritten_query"])
