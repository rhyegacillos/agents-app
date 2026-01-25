import logging
import os
from typing import List, Optional, Any, Dict
from openai import AsyncOpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("agent_api")

# Fallback configuration
DEFAULT_MODEL_CHAIN = ["gpt-5-nano", "gpt-4o-mini", "gpt-3.5-turbo"]

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

async def generate_with_fallback(
    client: AsyncOpenAI,
    messages: List[Dict[str, Any]],
    models: Optional[List[str]] = None,
    max_retries: int = 1,
    **kwargs
) -> Any:
    """
    Generates a response using a list of models for fallback.
    """
    chain = models or DEFAULT_MODEL_CHAIN
    last_exception = None

    for model in chain:
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Attempting generation with model: {model} (attempt {attempt + 1})")
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **kwargs
                )
                return response
            except Exception as e:
                logger.warning(f"Error with model {model}: {e}")
                last_exception = e
                # If it's a rate limit or server error, we might want to retry the same model
                # but for now we proceed to the next model in the chain if retries are exhausted
                pass
    
    logger.error(f"All models failed. Last error: {last_exception}")
    raise last_exception or Exception("All models failed generation.")
