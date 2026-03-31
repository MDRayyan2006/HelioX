# HelioX RAG 2.1 - Decision Log

## Understanding Lock (Confirmed)

**What is being built:** HelioX RAG 2.1 – a Retrieval-Guided Multi-Agent Deliberative Architecture from scratch.
**Why it exists:** To provide grounded answers with citations, mitigate hallucinations, lower token usage, and perform selective multi-agent reasoning.
**Who it is for:** Internal business users (analysts, engineers) querying large document collections (technical PDFs, research reports, structured datasets).
**Key constraints:** Requires deterministic preprocessing, metadata-first retrieval, evidence-bound generation, and selective expert activation.
**Explicit non-goals:** Uncited claims, full-context reasoning (reading entire documents unnecessarily), and pure probabilistic reliance (LLM speculation).

**Clarifications:**
1. The system must strictly follow a deterministic ingestion pipeline before any LLM reasoning.
2. Retrieval should prioritize metadata and entity matching before vector similarity.
3. Multi-agent reasoning should activate only the minimal required expert chunks.
4. Every factual output must include supporting citations from retrieved spans.
5. If retrieval coverage is insufficient, the system should explicitly respond with "Insufficient evidence."

**Assumptions (Medium Scale):**
*   **Scale:** Hundreds of thousands of documents, dozens of concurrent queries.
*   **Components needed:** Distributed retrieval, caching layers, and scalable asynchronous parallel worker execution.
*   **Infrastructure capabilities:** The underlying tech stack supports a Vector DB, Metadata DB, and Redis cache.

---

## Decisions
*(To be populated during design exploration)*

### 1. Orchestration Layer (Phases 4 & 5)
*   **Decision:** Custom Asynchronous Reactor using Python `asyncio` and `FastAPI`.
*   **Alternatives Considered:** Framework-Native (LangGraph/AutoGen) and Message Broker Driven (Redis Pub/Sub, RabbitMQ).
*   **Rationale:** Provides precise control over worker activation, citation enforcement, and confidence scoring without framework abstraction lock-in. 
*   **Note:** Worker execution must remain stateless and modular to allow for future extraction into a distributed worker service if scaling demands increase.

### 2. Document Ingestion Pipeline (Phase 1)
*   **Decision:** Simplified Event-Driven Pipeline using Redis-backed queues (e.g., Celery or RQ).
*   **Alternatives Considered:** Unidirectional Batch Pipeline (Airflow/Dagster) and Synchronous API (FastAPI Background Tasks).
*   **Rationale:** Preserves near real-time document availability (critical for internal analysts) while keeping the infrastructure lightweight. 
*   **Note:** Pipeline stages (parse → clean → structure → chunk → profile → index) must be idempotent to allow safe retries on failure without corrupting the document graph.

### 3. Storage Architecture (Phase 2)
*   **Decision:** Specialized Split Database System (Qdrant + PostgreSQL + Redis).
*   **Alternatives Considered:** Unified Relational (PostgreSQL pgvector) and Unified Search Engine (Elasticsearch).
*   **Rationale:** Qdrant provides high-speed vector and metadata filtering for expert profiles. PostgreSQL remains the source of truth for document state and the structural graph. Redis serves as the hot cache.
*   **Note:** Vector writes must be idempotent and traceable back to the Postgres document graph to prevent orphaned embeddings.

### 4. Adjudication Engine (Phase 5)
*   **Decision:** Hybrid Conflict Resolution (Deterministic Filter → LLM Escalation).
*   **Alternatives Considered:** Pure LLM-as-Judge and Pure Deterministic Weighting.
*   **Rationale:** Balances cost, speed, and accuracy. It applies a deterministic formula (`(recency) + (source_rank) + (citation_density) + (worker_confidence)`) first. If the score gap is large (>20%), the top score wins. If close (<10%) or a contradiction exists, it escalates to an LLM evaluator.
*   **Note:** The LLM adjudicator must be strictly evidence-bound (only reasoning over provided citation spans, no external knowledge permitted).

### 5. Evidence-Bound Answer Composer (Phase 6)
*   **Decision:** Partial Answer with Explicit Flags.
*   **Alternatives Considered:** Strict Refusal (Hard Fallback) and Switch to General AI (Escalation).
*   **Rationale:** Provides usability for analysts by providing partial information when full context isn't available, maintaining strict non-hallucination.
*   **Note:** Must output in the strict format: 
    1. Direct Answer (citation-bound)
    2. Supporting Evidence (linked citation spans)
    3. Unverified or Missing Information (explicitly flagged)
    4. Constraints Applied
    5. Confidence Score
### 6. Query Analyzer (Phase 3)

Decision: Lightweight LLM-assisted structured decomposition with deterministic fallback.

Rationale:
- Enables intent classification, entity extraction, and constraint identification.
- Prevents over-reliance on LLM by enforcing schema validation and fallback defaults.

Note:
- Must enforce strict JSON schema validation.
- Must fallback to deterministic parsing if LLM fails.
### 7. Retrieval Ranking Strategy

Decision: Weighted Hybrid Scoring

score =
0.4 * semantic_similarity +
0.3 * entity_match_score +
0.2 * metadata_filter_score +
0.1 * recency_score

Rationale:
- Ensures semantic meaning remains dominant while respecting constraints.

Note:
- All scores must be normalized (0–1).
- Retrieval must return score breakdown for explainability.
### 8. Confidence Scoring Layer

Decision: Composite Confidence Metric

confidence =
0.35 * retrieval_coverage +
0.25 * citation_density +
0.20 * worker_agreement +
0.20 * conflict_penalty_inverse

Rationale:
- Separates answer quality from LLM confidence.

Note:
- If confidence < threshold:
    → trigger retrieval expansion OR
    → return "Insufficient evidence"
### 9. Worker Activation Strategy

Decision: Top-K Adaptive Activation

- Start with K = 3
- If coverage < threshold → expand to K = 5–7

Rationale:
- Reduces unnecessary LLM calls
- Maintains latency bounds

Note:
- Each worker must receive only top relevant spans (not full chunk)
### 10. Failure Handling

Decision: Graceful Degradation

Cases:
- LLM failure → fallback to deterministic extraction
- Retrieval failure → return "Insufficient evidence"
- Partial worker failure → continue with available outputs

Note:
- No silent failures allowed