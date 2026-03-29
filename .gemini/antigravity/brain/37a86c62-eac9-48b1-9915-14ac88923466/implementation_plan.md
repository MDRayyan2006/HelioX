# Fixing Mistral API Rate Limits

## Problem
The `run_pipeline.py` script fails with `mistralai.models.sdkerror.SDKError: API error occurred: Status 429. Body: {"object":"error","message":"Rate limit exceeded"}` when processing documents with many chunks (like `04OLAP.pdf` which has 59 chunks).

## Root Cause
1. **Summary Generation**: The pipeline attempts to generate summaries for all 59 chunks concurrently.
2. **Worker Pool Evaluators**: The pipeline dispatches 12 parallel workers at once to evaluate chunks against the query.
3. The Mistral API free/developer tier has strict rate limits (Requests Per Minute and Tokens Per Minute).
4. There is no retry mechanism with exponential backoff on these API calls, so the pipeline crashes immediately upon hitting a 429.

## Proposed Changes

1. **Add Retries with Exponential Backoff**: Wrap the core Mistral LLM calls in a retry loop using the `tenacity` library (or custom async retry loop if not available) that catches `SDKError` with status 429 and backs off.
2. **Add Concurrency Limits (Semaphores)**:
   - In `profiling/summary_generator.py`, limit the `asyncio.gather` batching using a semaphore (e.g., max 3-5 concurrent requests).
   - In `workers/pool.py`, limit the concurrent worker dispatch using a semaphore.

## Verification Plan
1. Attempt to run `python run_pipeline.py` locally with `04OLAP.pdf`.
2. Confirm that `Stage 0 (Expert Profiling)` and `Stage 5 (Multi-Agent Worker Pool)` complete successfully without crashing, and that the logs show graceful handling/slowing down rather than `429` exceptions.
