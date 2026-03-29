# System Orchestration & Deployment — Implementation Plan

This plan finalizes the system by building **Layer 1 — System Orchestrator**, implementing observability, and providing the required deployment outlines.

## 1. Required Deliverables (Diagrams & Deployment Plan)

### Final Architecture Diagram (Text)

```
                            [ User Request ]
                                   │
                                   ▼
                       ┌───────────────────────┐
                       │  API Gateway (REST)   │
                       └───────────┬───────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  System Orchestrator        │ ◄── [ Observability / Timers ]
                    │   (Coordinates lifecycle)   │
                    └──────┬─────┬────────┬───────┘
                           │     │        │
      ┌────────────────────┘     │        └──────────────────────┐
      ▼                          ▼                               ▼
 ┌─────────┐                ┌─────────┐                     ┌─────────┐
 │ Query   │                │ Session │                     │ Mode    │
 │ Analyzr │                │ Memory  │                     │ Cntrlr  │
 ├─────────┤                └─────────┘                     ├─────────┤
 │ Query   │                   (Redis)                      │ LIGHT / │
 │ Validat │                                                │ HEAVY   │
 └────┬────┘                                                └────┬────┘
      │                                                          │
      ▼                                                          ▼
  [ SQO ] ──────────────────────────────────────────┐     [ Execution ]
                                                    │            │
                                                    ▼            ▼
                                            ┌─────────────────────────┐
                                            │ Hybrid Retrieval Engine │
                                            └─────┬───────────────────┘
                                                  │
                                   [ K Chunks retrieved, min = 5, max = 12 ]
                                                  │
                                                  ▼
                         (Heavy Mode Async Deliberation Cascade)
                                                  │
                                  ┌───────────────▼───────────────┐
                                  │   Parallel Worker Agent Pool  │
                                  └───────────────┬───────────────┘
                                                  ▼
                                  ┌───────────────┴───────────────┐
                                  │   Cross-Chunk Synthesizer     │
                                  └───────────────┬───────────────┘
                                                  ▼
                                  ┌───────────────┴───────────────┐
                                  │      Adjudication Engine      │
                                  └───────────────┬───────────────┘
                                                  ▼
                                  ┌───────────────┴───────────────┐
                                  │   Evidence Answer Composer    │
                                  └───────────────┬───────────────┘
                                                  ▼
                                  ┌───────────────┴───────────────┐
                                  │ Confidence & Self-Validation  │
                                  └───────────────┬───────────────┘
                                                  │
                                                  ▼
                                            [ Deliver / ]
                                            [ Warn /    ]
                                            [ Clarify   ]
```

### Service Interaction Map

1. **Gateway → Orchestrator**: REST to Internal method call. Orchestrator initializes `QueryContext` tracking tokens, latency, and session ID.
2. **Orchestrator ↔ Memory**: Fetches historical session constraints/preferences.
3. **Orchestrator ↔ Query Pipeline**: Analyzes query intent, decomposes into sub-questions, and validates it producing a locked `StructuredQueryObject` (SQO).
4. **Orchestrator ↔ Mode Controller**: Checks SQO Intent/Ambiguity to gate execution into `LIGHT` or `HEAVY`.
5. **Orchestrator ↔ Hybrid Retrieval**: Sends SQO. Retrieval applies Metadata filters (Postgres) → Entity overlap → Vector Search (Qdrant).
6. **Orchestrator ↔ Workers (Heavy)**: Distributes exactly 1 chunk per worker to generate strictly cited claims.
7. **Orchestrator ↔ Synthesizer/Adjudicate (Heavy)**: Merges outputs, detects contradictions, and resolves via rules/re-verification.
8. **Orchestrator ↔ Composer**: Injects resolved claims + SQO constraints into Gemini to generate final `[Cx]` cited text.
9. **Orchestrator ↔ Confidence**: Computes 6-factor metric (Agreement, Constraints, etc.). Auto-escalates Light→Heavy if `< 0.70`, otherwise returns to User.
10. **Orchestrator → Memory**: Saves final verified interaction (drops reasoning traces) and bumps TTL.

### Deployment Plan (Docker + Kubernetes)

**I. Containerization (Docker):**
- **Base image**: `python:3.11-slim` or `3.12-slim`.
- **Services**:
  1. `gateway` (FastAPI orchestrating the synchronous/async pipeline routes).
  2. `worker` (Celery or Python `asyncio` pool processes to handle LLM sub-tasks).
  3. `ingestion` (Offline batch job container).
- **External Dependencies**:
  1. `redis` (Session Memory cache).
  2. `qdrant` (Vector database).
  3. `postgresql` (Metadata / Authority scores).

**II. Orchestration (Kubernetes):**
- **Gateway Deployment**: Horizontal Pod Autoscaler (HPA) checking CPU/Memory (target 70%), minimum 2 pods for HA, deployed with an Ingress Controller.
- **Worker Deployment**: HPA scaling based on custom queue depth metrics (or built-in Kafka/Redis queue length). Needs flexible scale out (min 3, max ~50).
- **Persistent Storage**:
  - StatefulSet for PostgreSQL / Qdrant (or managed RDS/Vector services in AWS/GCP).
  - Redis managed via standard bitnami HELM chart.
- **ConfigMap / Secrets**: `HELOIX_CONFIG` mapped to pod environments, securing external LLM keys natively.

---

## 2. Proposed Changes (Code Implementation)

### [NEW] [orchestrator/observability.py](file:///c:/HelioX/orchestrator/observability.py)
A lightweight context manager and structured logging utility tracking duration, token counts, and step completion status.

### [NEW] [orchestrator/orchestrator.py](file:///c:/HelioX/orchestrator/orchestrator.py)
The `SystemOrchestrator` class that wires the pipeline:
- Input: `query (str)`, `session_id`
- Steps: Analyzes → Validates → Mode check → Retrieves → (Workers/Synthesize/Adjudicate) → Composer → Confidence → Save to Memory.
- Returns comprehensive JSON response containing the Answer, Metadata, and Execution Diagnostics.

---

## Verification Plan
Since this orchestration layer ties together real schemas but potentially missing service logic (e.g. Analyzer API call), verification will be conceptual/dry-run oriented. I will provide a test simulating the Orchestrator execution path avoiding external network calls.
