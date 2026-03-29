# Sanitizing Secrets and Pushing Repository

The push to the remote repository was rejected because GitHub's Push Protection detected hardcoded Groq API keys in the commit history. This plan outlines the steps to remove these secrets from the code and sanitize the Git history to allow a successful push.

## Proposed Changes

### [Secret Sanitization]

I will replace all hardcoded Groq API keys with environment variable lookups using `os.getenv("GROQ_API_KEY")`.

#### [MODIFY] [worker.py](file:///c:/HelioX/workers/worker.py)
#### [MODIFY] [decomposer.py](file:///c:/HelioX/query_pipeline/decomposer.py)
#### [MODIFY] [summary_generator.py](file:///c:/HelioX/profiling/summary_generator.py)
#### [MODIFY] [entity_extractor.py](file:///c:/HelioX/profiling/entity_extractor.py)
#### [MODIFY] [generator.py](file:///c:/HelioX/composer/generator.py)
#### [MODIFY] [engine.py](file:///c:/HelioX/adjudication/engine.py)

### [Git History Cleanup]

To remove the secrets from the commit history, I will:
1. Reset the current branch to `origin/main` (the last clean state).
2. Apply the sanitization fixes to the files.
3. Commit all changes in a new, single "clean" commit.
4. Push the clean branch to the remote.

## Verification Plan

### Automated Tests
- Run `git status` and `git log` to verify the history is clean.
- Run `grep -r "gsk_"` to ensure no hardcoded keys remain in the codebase.

### Manual Verification
- Attempt to push the sanitized branch to the remote repository.
- Verify that the Push Protection error is no longer triggered.
