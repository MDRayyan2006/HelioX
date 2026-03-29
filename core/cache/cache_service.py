import json
import hashlib
from typing import Optional, Dict, Any
from core.logger import get_logger
from core.cache.redis_client import get_redis_client

logger = get_logger("CACHE")

def generate_cache_key(query: str) -> str:
    query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()
    return f"rag:query:{query_hash}"

def get_cache(query: str) -> Optional[Dict[str, Any]]:
    client = get_redis_client()
    if not client:
        return None
        
    key = generate_cache_key(query)
    try:
        data = client.get(key)
        if data:
            print("[CACHE] HIT")
            return json.loads(data)
    except Exception as e:
        logger.error(f"Failed to read from cache: {e}")
        
    print("[CACHE] MISS")
    return None

def set_cache(query: str, value: Dict[str, Any], ttl: int = 300) -> None:
    client = get_redis_client()
    if not client:
        return
        
    key = generate_cache_key(query)
    try:
        data = json.dumps(value)
        client.setex(key, ttl, data)
    except Exception as e:
        logger.error(f"Failed to write to cache: {e}")
