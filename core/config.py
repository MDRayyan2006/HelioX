"""
Configuration Management: Loads environment-specific settings.

Supports environment variables with fallback to defaults.
For Qdrant: Use QDRANT_URL and QDRANT_API_KEY environment variables.
"""

import os
from dataclasses import dataclass

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, will use only environment variables


@dataclass
class Config:
    """Application configuration."""

    # Qdrant Configuration
    qdrant_url: str = os.getenv("QDRANT_URL", None)  # None = use in-memory by default
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", None)
    qdrant_collection_name: str = os.getenv("QDRANT_COLLECTION", "heliox_chunks_e5")

    # Embedding Configuration
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

    # Pipeline Configuration
    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "50"))

    # Groq LLM Configuration
    # Multi-agent pipeline uses qwen/qwen3-32b (default)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")
    # Lightweight pipeline uses llama-3.1-8b-instant with separate API key
    groq_lightweight_api_key: str = os.getenv("GROQ_LIGHTWEIGHT_API_KEY", "")
    groq_lightweight_model: str = os.getenv("GROQ_LIGHTWEIGHT_MODEL", "llama-3.1-8b-instant")


# Global config instance
_config: Config = None


def get_config() -> Config:
    """
    Get or create configuration singleton.

    Returns:
        Config instance with loaded settings
    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(**kwargs) -> None:
    """
    Override configuration values (useful for testing or CLI args).

    Args:
        **kwargs: Configuration fields to override
    """
    global _config
    if _config is None:
        _config = Config()

    for key, value in kwargs.items():
        if hasattr(_config, key):
            setattr(_config, key, value)
