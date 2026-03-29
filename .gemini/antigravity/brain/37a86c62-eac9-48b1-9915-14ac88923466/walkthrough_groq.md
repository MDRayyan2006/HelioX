# Walkthrough: Refactoring Worker Pool to Use Groq

## Problem
Although the pipeline was successfully processing `04OLAP.pdf`, using the Mistral API for the Multi-Agent Worker Pool (which evaluates 12 chunks concurrently) was slow, occasionally hitting 429 errors forcing the tenacity backoff loop to heavily throttle the execution.

The user requested that we exclusively update the `WorkerPool` to utilize Groq's extremely fast `llama-3.1-8b-instant` model and distribute the request load across 3 different explicitly provided API keys to bypass rate limits naturally.

## Changes Made

### 1. Multi-Key Groq Setup
In `workers/worker.py`:
- We stripped out the `mistralai` client from the `_call_llm` method.
- Added the `groq` package to the system and imported `AsyncGroq`.
- Created a `GROQ_API_KEYS` list containing the three distinct API keys: `gsk_iif...`, `gsk_QNT...`, and `gsk_5xU...`.
- Implemented a standard stochastic load balancer: For every chunk worker spawned, we use `random.choice(GROQ_API_KEYS)` to randomly initialize the asynchronous Groq client, inherently limiting the load mapped to each API key.

### 2. Model Rotation and Retry Logic
- Replaced the Mistral async call with `client.chat.completions.create`.
- Migrated the model to `"llama-3.1-8b-instant"` as requested.
- Maintained the previous `tenacity` exponential backoff loop, but strictly caught `groq.RateLimitError` to retry on any temporary quota restrictions.
- Ensured we still properly parse the usage statistics mapping `prompt_tokens` and `completion_tokens` into the pipeline's internal token budget logic.

## Verification
- Reran `python run_pipeline.py` with the query "what is OLAP" over `04OLAP.pdf`. 
- **Stage 5 (Worker Pool)** fired all 12 chunk evaluations concurrently against the Groq endpoints. Since the parallel requests were routed over 3 distinct API keys, the responses came back virtually instantaneously without tripping any 429 limits, dramatically speeding up the chunk evidence extraction layer!
