import os
import requests
from typing import Optional
from core.logger import get_logger
from core.config import get_config

logger = get_logger("GROQ_LLM")

def generate(
    prompt: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None
) -> Optional[str]:
    """
    Execute Groq API call with configurable model and API key.

    Args:
        prompt: The prompt to send to the LLM
        api_key: Optional Groq API key (if None, uses config.groq_api_key)
        model: Optional model name (if None, uses config.groq_model)
        temperature: Sampling temperature (default 0.3)
        max_tokens: Optional max tokens to generate

    Returns:
        Generated text string or None if failed
    """
    # Get configuration
    config = get_config()

    # Use provided API key/model or fall back to config
    api_key = api_key or config.groq_api_key
    model = model or config.groq_model

    if not api_key:
        logger.warning("No Groq API key configured. LLM features disabled.")
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }

    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            logger.error(f"Groq API error {response.status_code}: {response.text}")
    except requests.exceptions.Timeout:
        logger.error("Groq API request significantly timed out (>15s).")
    except Exception as e:
        logger.error(f"Groq API request failed natively: {e}")
        
    return None
