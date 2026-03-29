# HelioX RAG 3.0 — Walkthrough

## What Was Built

A complete enterprise-grade architecture blueprint and PRD for **HelioX RAG 3.0**, a Retrieval-Guided Multi-Agent Deliberative System.

- [architecture_blueprint.md](file:///d:/HelioX/architecture_blueprint.md)
- [prd.md](file:///d:/HelioX/prd.md)

## Deliverables Covered

| # | Deliverable | Blueprint Section |
|---|---|---|
| 1 | High-level technical architecture | §2 — 13-layer stack, orchestrator hard limits, mode controller, ingestion pipeline, expert profiling, query pipeline, retrieval engine, workers, synthesis, adjudication, composer, confidence engine, session memory |
| 2 | Service breakdown | §3 — 14 services with deployment model, protocol, scaling strategy, and Mermaid dependency graph |
| 3 | Data flow diagram | §4 — Query-time (Heavy Mode) and ingestion-time ASCII flow diagrams |
| 4 | Folder structure | §5 — Full `heliox-rag/` tree with 15 top-level modules and deployment configs |
| 5 | API boundary definitions | §6 — External REST endpoints (`/v1/query`, `/v1/ingest`, `/v1/session`, `/health`) with request/response schemas; internal gRPC RPCs for all 9 service-to-service calls |
| 6 | Orchestrator interaction map | §7 — Full state machine (IDLE → INIT → MODE_SELECT → pipeline → VALIDATE → DELIVER/EXPAND/CLARIFY → IDLE); decision point table with 8 gating conditions |
| 7 | Failure-handling model | §8 — 4-tier failure taxonomy, retry policies per dependency, circuit breaker configs, 4-level degradation ladder, timeout cascade with per-phase walls |
| 8 | Cost-control strategy | §9 — Token budget allocation per phase, 6 cost levers, per-query cost tracking schema, organizational guardrails, and 11 observability metrics |

## PRD Deliverables

| # | Section | Highlights |
|---|---------|------------|
| 1 | Product Vision | Mission, strategic goals, what HelioX is NOT |
| 2 | Target Users | 5 primary personas + 2 secondary + assumptions |
| 3 | Problem Statement | 6 industry pain points → desired state |
| 4 | Functional Requirements | 50+ requirements across 11 categories (FR-1 to FR-11), all prioritized P0/P1/P2 |
| 5 | Non-Functional Requirements | Reliability, observability, maintainability, testability |
| 6 | Performance Targets | Per-mode latency (P50/P95/P99), per-phase budgets, throughput |
| 7 | Scalability | MVP (10K docs) → Full (1M docs, 50M chunks), multi-tenancy |
| 8 | Security | Auth (OAuth+RBAC), encryption, PII, audit, network |
| 9 | Cost Constraints | Per-query targets, token budgets, org guardrails, infra cost |
| 10 | Evaluation Metrics | 10 offline + 10 online metrics, calibration protocol |
| 11 | Failure Handling | Taxonomy, retry policies, circuit breakers, degradation ladder |
| 12 | MVP vs Full Version | Feature matrix (40+ features), 8-milestone delivery plan (26 weeks) |
