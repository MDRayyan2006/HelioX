"""
Embedding Service: Generates vector embeddings for text using sentence-transformers.

Uses singleton pattern for efficient model caching and reuse.
"""

from typing import List
import threading

# Global singleton instance (thread-safe lazy initialization)
_embedder_instance = None
_lock = threading.Lock()


class Embedder:
    """
    Embedding generator using sentence-transformers.

    Loads the model once and reuses it for all embedding calls.
    Uses intfloat/multilingual-e5-small by default (384-dimensional vectors).
    """

    _model = None
    _model_name = "intfloat/multilingual-e5-small"

    def __init__(self, model_name: str = None):
        """
        Initialize embedder with specified model.

        Args:
            model_name: HuggingFace model name (default: intfloat/multilingual-e5-small)
        """
        if model_name:
            self._model_name = model_name

        # Lazy load model on first use
        self._ensure_model_loaded()

    def _ensure_model_loaded(self) -> None:
        """Load model if not already loaded (thread-safe)."""
        global _embedder_instance
        if Embedder._model is None:
            with _lock:
                if Embedder._model is None:
                    from sentence_transformers import SentenceTransformer
                    Embedder._model = SentenceTransformer(self._model_name)

    def preload(self) -> None:
        """Pre-warm the embedding model so the first request is fast."""
        self._ensure_model_loaded()

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding vector for a single text string.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector
        """
        import hashlib
        import json
        
        # 1. Check Cache
        client = None
        cache_key = None
        try:
            from core.cache.redis_client import get_redis_client
            client = get_redis_client()
            if client:
                query_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
                cache_key = f"embedding:{query_hash}"
                cached = client.get(cache_key)
                if cached:
                    return json.loads(cached)
        except Exception as e:
            # Drop errors gracefully
            pass

        # 2. Compute embedding
        self._ensure_model_loaded()
        embedding = Embedder._model.encode(text)
        embedding_list = embedding.tolist()

        # 3. Store in cache
        try:
            if client and cache_key:
                client.setex(cache_key, 86400, json.dumps(embedding_list))
        except Exception as e:
            pass

        return embedding_list

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batch optimization).

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        self._ensure_model_loaded()
        embeddings = Embedder._model.encode(texts)
        return embeddings.tolist()


# Singleton accessor for convenience
_default_embedder = None


def get_embedder() -> Embedder:
    """
    Get default embedder instance (singleton).

    Returns:
        Shared Embedder instance
    """
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = Embedder()
    return _default_embedder
