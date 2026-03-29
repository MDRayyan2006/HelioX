# HelioX RAG Evaluation Layer

Multi-agent evaluation system on top of the Phase 1 pipeline.

## 🧩 Components

### `runner.py` - Pipeline Runner
- `run_query(query: str)` → calls `pipeline.run_pipeline()` and returns structured dict
- Wraps pipeline execution with error handling

### `evaluator.py` - Evaluator
- `evaluate(result, expected)` → validation report
- Checks:
  - Pipeline success
  - At least N results (default 3)
  - Confidence scores in [0,1]
  - Results sorted descending
  - Optional: keyword presence in supporting spans
  - Optional: entity presence in supporting spans

### `critic.py` - Diagnostician
- `diagnose(evaluation_report)` → human-readable issue list
- `format_diagnosis(report)` → formatted string

### `testsprite_runner.py` - Test Harness
- `run_testsprite(test_cases=None, test_file=None)` → full loop
- Loads test cases from JSON or uses defaults
- Runs pipeline → evaluate → diagnose for each test
- Prints clean report with [TEST], [CRITIC] prefixes

## 🚀 Usage

### Run with default tests:
```bash
python -m evaluation.testsprite_runner
```

### Run with custom test file:
```bash
python -m evaluation.testsprite_runner --test-file path/to/tests.json
```

### Use programmatically:
```python
from evaluation.runner import run_query
from evaluation.evaluator import evaluate
from evaluation.critic import format_diagnosis

result = run_query("Your query here")
report = evaluate(result, expected={"min_results": 3, "keywords": ["foo"], "entities": ["Bar"]})
print(format_diagnosis(report))
```

## 📄 Test Case Format (JSON)

```json
[
  {
    "name": "Test name",
    "query": "What is RAG?",
    "expected": {
      "min_results": 3,
      "keywords": ["rag", "retrieval"],
      "entities": ["RAG"]
    }
  }
]
```

## 🎯 Output Format

```
[TEST] 1. Test name
[QUERY] "query string"
[CRITIC] [DIAGNOSE] Query: query string
[CRITIC] [FAIL] Missing keywords: ['foo']
[CRITIC]        Found keywords: ['bar']
[CRITIC]
[CRITIC] [SUMMARY] 1 issue(s) detected:
[CRITIC]   1. Missing keywords: ['foo']
```

## 📁 Structure

```
evaluation/
├── __init__.py
├── runner.py        # Pipeline executor
├── evaluator.py     # Output validator
├── critic.py        # Issue diagnoser
├── testsprite_runner.py  # Test harness
└── tests.json       # Sample test cases
```

## ✅ Notes

- All components are deterministic (no external APIs, no async)
- Evaluation uses `supporting_span` (first ~10 words of chunk text) for keyword/entity checks
- Scores are validated to be in [0,1] range
- Results must be sorted descending by confidence
- Exit code: 0 if all tests pass, 1 if any fail
