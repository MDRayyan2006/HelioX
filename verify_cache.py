import time
from api.engine.pipeline import run_pipeline
from core.cache.redis_client import get_redis_client

# Clear cache first to ensure a MISS
client = get_redis_client()
if client:
    client.flushdb()

query = "What is HelioX fast caching?"

print("\n=== FIRST RUN ===")
start = time.time()
res1 = run_pipeline(query)
print(f"Time: {time.time() - start:.2f}s\n")

print("\n=== SECOND RUN ===")
start = time.time()
res2 = run_pipeline(query)
print(f"Time: {time.time() - start:.2f}s\n")
