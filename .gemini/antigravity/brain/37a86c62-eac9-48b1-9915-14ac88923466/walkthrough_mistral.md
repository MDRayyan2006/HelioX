# Walkthrough: Fixing Mistral API Rate Limits

## Problem
When processing larger documents like `04OLAP.pdf` (which extracts into 59 chunks), the pipeline was immediately crashing with `mistralai.models.sdkerror.SDKError: API error occurred: Status 429. Body: {"object":"error","message":"Rate limit exceeded"}`.

This occurred because the `SummaryGenerator` completely bypassed rate limits by indiscriminately sending all 59 chunk summarization requests via `asyncio.gather()` at the exact same time. A similar issue existed in `workers/pool.py`, where up to 12 Multi-Agent evaluators were fired against the Mistral API simultaneously, breaching Free/Dev Tier RPM (Requests Per Minute) limits.

## Changes Made

### 1. Exponential Backoff Retries
Added the `tenacity` library to both Mistral execution layers (`profiling/summary_generator.py` and `workers/worker.py`).
- Wrapped the raw `CompleteAsync` calls in a `@retry` decorator.
- Configured it to catch `SDKError` specifically, explicitly stopping after 5 attempts.
- Used an exponential wait bounded between 2 to 15 seconds per retry, allowing the Mistral API quota to naturally reset without crashing the pipeline.

### 2. Concurrency Control (Semaphores)
Retries help, but we shouldn't intentionally hammer the API. I added `asyncio.Semaphore` gates to the heavy ingestion layers.
- **`SummaryGenerator`**: Added an `asyncio.Semaphore(2)` so only 2 simultaneous summary requests run. Added an `asyncio.sleep(0.5)` stagger.
- **`WorkerPool`**: Added an `asyncio.Semaphore(4)` before the worker execution loop to ensure the Multi-Agent pool doesn't exceed 4 concurrent evaluations at once.

## Verification
- Successfully reran `python run_pipeline.py` with `04OLAP.pdf`. 
- **Stage 0 (Profiling)** gracefully took 4.6 seconds to chunk and summarize 59 blocks, relying on the semaphore flow.
- **Stage 5 (Worker Pool)** successfully dispatched 12 chunk evaluations through the LLM gate without erroring out, successfully returning evaluating claims.
