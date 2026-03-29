import logging
from typing import Optional

def get_logger(stage: str) -> logging.Logger:
    """
    Factory function to create a structured logger for a specific stage.

    Args:
        stage: The stage name for the logger (e.g., 'QUERY', 'RETRIEVAL')

    Returns:
        A configured logger instance with stage-level formatting
    """
    logger = logging.getLogger(f"heliox.{stage.lower()}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(f"[{stage.upper()}] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
