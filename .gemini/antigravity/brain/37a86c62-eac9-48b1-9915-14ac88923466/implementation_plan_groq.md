# Refactoring Worker Pool to Use Groq

## Problem
The multi-agent worker pool currently uses the Mistral API, which hits steep rate limits on large documents. The user has provided 3 Groq API keys to distribute the load and evaluate chunks much faster using Groq's high-speed Llama 3 models. The user explicitly requested to *only* change the worker pool.

## Proposed Changes

1. **Install Groq**: Install the `groq` Python SDK.
2. **Update Worker Agent (`workers/worker.py`)**:
   - Strip out the `mistralai` client from the `_call_llm` method.
   - Introduce a list of the 3 provided Groq API keys.
   - Instantiate `groq.AsyncGroq()` using a randomly selected key (or round-robin) from the list for each worker invocation to distribute the load evenly.
   - Update the chat completion payload to use the Groq API syntax and target a fast Groq model (e.g., `llama3-70b-8192` or `llama3-8b-8192`).
3. **Keep Other Components Intact**: We will deliberately *not* touch `SummaryGenerator` or other parts of the pipeline as per the constraint "only change worker pool".

## Verification Plan
1. Run `python run_pipeline.py` with the query "what is OLAP" over `04OLAP.pdf`.
2. Observe "Stage 5: Multi-Agent Worker Pool" to confirm that the workers execute successfully using the Groq API without 429s or crashes, returning `SUFFICIENT` or `INSUFFICIENT` verdicts correctly based on Groq's Llama 3 analysis.
