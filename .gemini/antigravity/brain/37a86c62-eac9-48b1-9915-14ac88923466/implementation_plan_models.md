# Implementation Plan: Model Routing for Pipeline Stages

## Request
- **Heavy Model Principal LLM**: `llama-3.3-70b-versatile` (Groq API: `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`)
- **Light Model Principal LLM**: Mistral (`mistral-small-latest` via existing `.env` Mistral key)
- **Profiling Stage (profiling_pg)**: `llama-3.1-8b-instant` (Groq API: `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`)

## Architectural Adjustments

### 1. Profiling Stage (`profiling/`)
The profiling stage runs at the very beginning of ingestion (Stage 0). It uses two components: `SummaryGenerator` and `EntityExtractor`.
We will replace the `mistralai` logic in both components with the `groq.AsyncGroq` logic, using the `llama-3.1-8b-instant` model and the specified key. We'll retain the `tenacity` retry loops we built earlier.

### 2. Principal LLMs (Adjudicator & Composer)
The "Principal LLM" is invoked inside `adjudication/engine.py` (LLM tiebreaker) and `composer/generator.py` (Final Answer Synthesis). These components are initialized once per pipeline run, but execute differently depending on whether the query was classified as `LIGHT` or `HEAVY`.

**Changes:**
1. Update their `__init__` methods to construct *both* the Mistral client (for Light Mode) and the Groq client (for Heavy Mode).
2. Update `adjudicate()` and `generate()` to accept a new `mode: ExecutionMode = ExecutionMode.HEAVY` argument.
3. Update their internal `_call_llm` equivalents to dynamically select `self._groq_client` (Llama 3.3 70B) if `mode == "HEAVY"`, or `self._mistral_client` (Mistral Small) if `mode == "LIGHT"`.

### 3. Orchestrator Updates
We need to pipe the `mode` variable correctly into these engines.
- In `orchestrator/orchestrator.py`, pass the resolved `mode` variable into `adjudicator.adjudicate(..., mode=mode)` and `composer.generate(..., mode=mode)`.
- In `run_pipeline.py`, do the exact same thing in the main execution block (Stage 6 and Stage 7).

## Verification
Run `run_pipeline.py` one final time.
1. The terminal profiling stage (Stage 0) should execute successfully using Groq's 8B model.
2. The Mode selection will default to HEAVY or escalate to HEAVY, routing the Adjudicator and Composer through the Groq 70B Versatile model.
