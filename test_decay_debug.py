import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.adaptive.session_memory import SessionMemory, STRONG_POS_DELTA, STRONG_NEG_DELTA, BOOST_SCALE
from core.memory_store import MemoryStore

# Fresh memory
fd, path = tempfile.mkstemp(suffix='.json', prefix='test_mem_')
os.close(fd)
try:
    os.remove(path)
except FileNotFoundError:
    pass
store = MemoryStore(path)
mem = SessionMemory(memory_store=store)

# Good entity: high confidence PASS
mem.record_attempt(['GoodEntity'], ['c1'])
mem.record_outcome(confidence=0.85, verdict='PASS', retried=False)

# Bad entity: FAIL
mem.record_attempt(['BadEntity'], ['c2'])
mem.record_outcome(confidence=0.2, verdict='FAIL', retried=False)

boosts = mem.get_entity_boosts()
print('Boosts:', boosts)
expected_good = round(STRONG_POS_DELTA * BOOST_SCALE, 4)
print('Expected good:', expected_good)
print('Good entity boost:', boosts.get('goodentity', 0))
print('Bad entity boost:', boosts.get('badentity', 0))

# Check
try:
    assert boosts.get('goodentity', 0) > 0, 'Good entity should be positive'
    assert boosts.get('badentity', 0) < 0, 'Bad entity should be negative'
    assert boosts['goodentity'] == expected_good, f'Expected {expected_good}, got {boosts["goodentity"]}'
    print('Test passed')
except AssertionError as e:
    print('Test failed:', e)
    exit(1)
finally:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
