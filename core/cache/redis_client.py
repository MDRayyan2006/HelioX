import redis
from typing import Optional
from core.logger import get_logger

logger = get_logger("REDIS")

class RedisClient:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            try:
                # We use decode_responses=True to automatically get strings instead of bytes
                # Add timeouts to prevent hanging if Redis is down
                cls._instance = redis.Redis(
                    host="localhost", 
                    port=6379, 
                    db=0, 
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0
                )
                cls._instance.ping()
                logger.info("Connected to Redis successfully.")
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                cls._instance = None
        return cls._instance

def get_redis_client() -> Optional[redis.Redis]:
    return RedisClient.get_instance()
