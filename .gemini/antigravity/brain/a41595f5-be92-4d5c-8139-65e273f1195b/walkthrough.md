# Query Validation Agent — Walkthrough

## What Was Built

A full **Query Validation Agent** (architecture §2.6) replacing the basic `SQOValidator` stub. The agent detects problems, **corrects** the SQO when possible, and locks it only when checks pass.

## Files Created / Modified

| Action | File | Purpose |
|--------|------|---------|
| NEW | [confidence_scorer.py](file:///c:/HelioX/query_pipeline/confidence_scorer.py) | Multi-signal weighted confidence scoring |
| NEW | [validation_agent.py](file:///c:/HelioX/query_pipeline/validation_agent.py) | 6-check validation agent with corrections |
| NEW | [test_validation_agent.py](file:///c:/HelioX/tests/test_validation_agent.py) | 31 tests across 8 test classes |
| MOD | [schemas.py](file:///c:/HelioX/query_pipeline/schemas.py) | Added `ValidationVerdict`, `SQOCorrection`, `ConfidenceBreakdown`, `ValidationReport` |
| MOD | [analyzer.py](file:///c:/HelioX/query_pipeline/analyzer.py) | Re-decompose loop + validation agent integration |
| MOD | [validator.py](file:///c:/HelioX/query_pipeline/validator.py) | Backward-compat shim re-exporting from `validation_agent` |
| MOD | [routes.py](file:///c:/HelioX/query_pipeline/routes.py) | Response includes `validation_report` |

## Confidence Scoring Method

Weighted average of 4 signals:

| Signal | Weight | Source |
|--------|--------|--------|
| Intent confidence | 0.20 | Rule-based classifier |
| Decomposition confidence | 0.35 | LLM self-assessed |
| Entity grounding ratio | 0.25 | grounded / total entities |
| Constraint coverage | 0.20 | populated / 4 dimensions |

## Validation Logic

| Check | On Failure | Correction |
|-------|-----------|------------|
| Ambiguity detection | Warn: no entities, short query, no constraints | Reduce confidence |
| Missing constraints | Inject scope=section-level | Auto-correct |
| Entity grounding | Mark ungrounded entities | Warn (stub mode) |
| Component validation | Fill empty facts from query, inject default reasoning | Auto-correct |
| Confidence scoring | Score < 0.65 → signal re-decompose | Return `needs_redecomposition` |
| SQO lock | All checks pass or corrections applied → lock | Set `locked=True` |

## Three-State Verdict

| Verdict | Meaning | SQO Locked? |
|---------|---------|-------------|
| `valid` | All checks pass, no changes needed | ✅ Yes |
| `corrected` | Issues found and auto-fixed | ✅ Yes |
| `invalid` | Confidence too low, no corrections can help | ❌ No |

## Test Results

**130 total tests pass** (31 new + 55 existing query analyzer + 44 other):

| Test Class | Tests |
|------------|-------|
| `TestConfidenceScorer` | 7 — weighted scoring, clamping, partial grounding |
| `TestAmbiguityDetection` | 4 — no entities, short, no constraints, complete |
| `TestConstraintInjection` | 2 — missing scope injected, existing preserved |
| `TestEntityGrounding` | 4 — all/none/partial grounded, empty |
| `TestComponentValidation` | 4 — empty facts, missing reasoning, no-op for fact |
| `TestValidationVerdict` | 4 — valid/corrected/invalid, low-conf+corrections |
| `TestReDecomposeLoop` | 2 — re-decompose triggered, skipped when confident |
| `TestValidationSchemas` | 4 — enum values, serialization, defaults |
