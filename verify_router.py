import logging
import sys

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from core.execution_router import ExecutionRouter
import inspect

router = ExecutionRouter()

print("--- SIMPLE QUERY ---")
res_simple = router.route("What is Python?")
print(f"Result mode: {res_simple['mode']}")

print("\n--- COMPLEX QUERY ---")
res_complex = router.route("List all the differences between Pinecone and Qdrant and explain why one is better for dynamic scaling.")
print(f"Result mode: {res_complex['mode']}")
