import json
import hashlib
from typing import Optional, Dict, Any
from core.logger import get_logger
from core.cache.redis_client import get_redis_client

logger = get_logger("CACHE")

CORPUS_VERSION_KEY = "rag:corpus:version"
LAST_INGESTED_SOURCE_KEY = "rag:corpus:last_ingested_source"

# In-process fallback when Redis is unavailable.
_last_ingested_source_fallback: Optional[str] = None

def get_corpus_version() -> int:
    """Return the current corpus version used for cache invalidation."""
    client = get_redis_client()
    if not client:
        return 0

    try:
        raw = client.get(CORPUS_VERSION_KEY)
        return int(raw) if raw is not None else 0
    except Exception as e:
        logger.error(f"Failed to read corpus version: {e}")
        return 0


def bump_corpus_version() -> int:
    """Increment corpus version after document ingestion/index updates."""
    client = get_redis_client()
    if not client:
        return 0

    try:
        new_version = int(client.incr(CORPUS_VERSION_KEY))
        logger.info(f"Corpus version bumped to {new_version}")
        return new_version
    except Exception as e:
        logger.error(f"Failed to bump corpus version: {e}")
        return get_corpus_version()


def set_last_ingested_source(source: str) -> None:
    """Record the most recently ingested source for source-aware retrieval."""
    global _last_ingested_source_fallback

    source_clean = (source or "").strip()
    if not source_clean:
        return

    _last_ingested_source_fallback = source_clean
    client = get_redis_client()
    if not client:
        return

    try:
        client.set(LAST_INGESTED_SOURCE_KEY, source_clean)
    except Exception as e:
        logger.error(f"Failed to set last ingested source: {e}")


def get_last_ingested_source() -> Optional[str]:
    """Return the latest ingested source, using Redis with in-process fallback."""
    global _last_ingested_source_fallback

    client = get_redis_client()
    if not client:
        return _last_ingested_source_fallback

    try:
        source = client.get(LAST_INGESTED_SOURCE_KEY)
        if source:
            _last_ingested_source_fallback = source
            return source
    except Exception as e:
        logger.error(f"Failed to read last ingested source: {e}")

    return _last_ingested_source_fallback


def generate_cache_key(query: str, namespace: str = "default", corpus_version: Optional[int] = None) -> str:
    query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()
    version = get_corpus_version() if corpus_version is None else corpus_version
    safe_namespace = namespace or "default"
    return f"rag:query:{safe_namespace}:v{version}:{query_hash}"

def get_cache(query: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
    client = get_redis_client()
    if not client:
        return None
        
    key = generate_cache_key(query, namespace=namespace)
    try:
        data = client.get(key)
        if data:
            print("[CACHE] HIT")
            return json.loads(data)
    except Exception as e:
        logger.error(f"Failed to read from cache: {e}")
        
    print("[CACHE] MISS")
    return None

def set_cache(query: str, value: Dict[str, Any], ttl: int = 300, namespace: str = "default") -> None:
    client = get_redis_client()
    if not client:
        return
        
    key = generate_cache_key(query, namespace=namespace)
    try:
        data = json.dumps(value)
        client.setex(key, ttl, data)
    except Exception as e:
        logger.error(f"Failed to write to cache: {e}")
