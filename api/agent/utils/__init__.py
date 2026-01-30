import logging
import os
from typing import List, Optional, Any, Dict
from openai import AsyncOpenAI
import httpx

from .provider_clients import client_for_model

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
REQ_TIMEOUT = httpx.Timeout(60.0, connect=5.0, read=60.0, write=10.0)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

async def generate_with_fallback(
    client: AsyncOpenAI,
    messages: List[Dict[str, Any]],
    models: Optional[List[str]] = None,
    max_retries: int = 1,
    **kwargs
) -> Any:
    """Generate a response using a fallback chain.

    For non-OpenAI providers exposed via OpenAI-compatible endpoints (e.g.,
    DeepSeek, Gemini), the underlying AsyncOpenAI client is selected from a
    small in-process cache to avoid per-request client construction overhead.
    """
    chain = models or DEFAULT_MODEL_CHAIN
    last_exception = None

    for model in chain:
        for attempt in range(max_retries + 1):
            try:
                generation_client = client_for_model(model=model, default_client=client).with_options(
                    timeout=REQ_TIMEOUT)

                logger.info(f"Attempting generation with model: {model} (attempt {attempt + 1})")
                response = await generation_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **kwargs
                )
                return response
            except Exception as e:
                logger.warning(f"Error with model {model}: {e}")
                last_exception = e
                pass
    
    logger.error(f"All models failed. Last error: {last_exception}")
    raise last_exception or Exception("All models failed generation.")


async def generate_stream_with_fallback(
    client: AsyncOpenAI,
    messages: List[Dict[str, Any]],
    models: Optional[List[str]] = None,
    max_retries: int = 1,
    **kwargs
) -> Any:
    """
    Attempts to start a streaming response using a fallback chain.
    Returns an async generator of chunks.
    """
    chain = models or DEFAULT_MODEL_CHAIN
    last_exception = None

    for model in chain:
        for attempt in range(max_retries + 1):
            try:
                generation_client = client_for_model(model=model, default_client=client).with_options(
                    timeout=REQ_TIMEOUT)
                logger.info(f"Attempting stream with model: {model} (attempt {attempt + 1})")
                stream = await generation_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=True,
                    **kwargs
                )
                logger.info(f"Stream established successfully with model: {model}")
                # If we get here, the stream connection is established.
                # We yield from it. If it breaks mid-stream, we can't easily fallback retry 
                # without re-generating text, so we assume connection open = success for now.
                return stream
            except Exception as e:
                logger.warning(f"Stream init failed with model {model}: {e}")
                last_exception = e
                pass

    logger.error(f"All streaming models failed. Last error: {last_exception}")
    # Fallback to yielding a friendly error message as a stream
    async def error_stream():
        yield type('Chunk', (object,), {'choices': [type('Choice', (object,), {'delta': type('Delta', (object,), {'content': "I apologize, but the AI service is currently unavailable."})()})()]})()
    
    return error_stream()
