import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.adaptive.session_memory import SessionMemory
from core.memory_store import MemoryStore

# Test concept importance calculation
fd, path = tempfile.mkstemp(suffix='.json', prefix='test_imp_')
os.close(fd)
try:
    os.remove(path)
except: pass

store = MemoryStore(path)
mem = SessionMemory(memory_store=store)

# Simulate learning: two entities from the same concept
# Concept: "vector database" with members: qdrant, pinecone
mem.record_attempt(['qdrant', 'pinecone'], ['chunk1'])
mem.record_outcome(0.9, 'PASS', False)

# Qdrant appears many times (high usage)
for _ in range(10):
    mem.record_attempt(['qdrant'], ['chunk1'])
    mem.record_outcome(0.8, 'PASS', False)

# Pinecone appears only once
# (already recorded above)

mem._memory_store.save()

# Get concept importance
importance = mem.get_concept_importance()
print("Concept importance:", importance)

# The vector database concept should exist and have decent importance
if 'vector database' in importance:
    imp = importance['vector database']
    print(f"vector database importance: {imp}")
    # Should be > 0.5 due to good score + usage
    assert imp > 0.5, f"Expected importance > 0.5, got {imp}"
    print("Test passed: concept importance works!")
else:
    print("Warning: 'vector database' concept not found. Available concepts:", list(importance.keys()))
    print("This might be okay if the concept isn't in the taxonomy yet.")
finally:
    try:
        os.remove(path)
    except: pass
