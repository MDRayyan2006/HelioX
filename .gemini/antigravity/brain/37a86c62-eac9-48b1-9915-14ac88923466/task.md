# Configuring Models for Pipeline Stages

- [x] Update `profiling/summary_generator.py` to use Groq (`llama-3.1-8b-instant`) with the provided profiling API key.
- [x] Update `profiling/entity_extractor.py` to use Groq (`llama-3.1-8b-instant`) with the provided profiling API key.
- [x] Update `adjudication/engine.py` to conditionally use Groq (`llama-3.3-70b-versatile`) if `mode == HEAVY`, else Mistral.
- [x] Update `composer/generator.py` to conditionally use Groq (`llama-3.3-70b-versatile`) if `mode == HEAVY`, else Mistral.
- [x] Update `orchestrator/orchestrator.py` and `run_pipeline.py` to actively pass the execution `mode` into the Adjudicator and Composer.
- [x] Test `run_pipeline.py` to ensure all execution environments pass.
