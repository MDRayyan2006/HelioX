import redis

def test_redis():
    results = {}
    
    # Test localhost
    try:
        r1 = redis.Redis(host='localhost', port=6379, decode_responses=True, socket_connect_timeout=2)
        r1.set('heliox_test', 'working_localhost')
        val = r1.get('heliox_test')
        print(f"LOCALHOST works: {val}")
        results['localhost'] = True
    except Exception as e:
        print(f"LOCALHOST failed: {e}")
        results['localhost'] = False

    # Test WSL IP
    try:
        r2 = redis.Redis(host='172.26.148.172', port=6379, decode_responses=True, socket_connect_timeout=2)
        r2.set('heliox_test', 'working_wsl_ip')
        val = r2.get('heliox_test')
        print(f"WSL_IP works: {val}")
        results['172.26.148.172'] = True
    except Exception as e:
        print(f"WSL_IP failed: {e}")
        results['172.26.148.172'] = False
        
    return results

if __name__ == "__main__":
    test_redis()
