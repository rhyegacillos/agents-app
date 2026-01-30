import logging
import os
from typing import Optional, Tuple

from openai import AsyncOpenAI


logger = logging.getLogger("agent_api")


# Simple in-process client cache. Rebuilds if env (key/base_url) changes.
_deepseek_cache: Tuple[Optional[str], Optional[str], Optional[AsyncOpenAI]] = (None, None, None)
_gemini_cache: Tuple[Optional[str], Optional[str], Optional[AsyncOpenAI]] = (None, None, None)


def _get_env_pair(key_name: str, url_name: str, default_url: str) -> Tuple[Optional[str], str]:
    api_key = os.getenv(key_name)
    base_url = os.getenv(url_name, default_url)
    return api_key, base_url


def get_deepseek_client() -> Optional[AsyncOpenAI]:
    """Return a cached DeepSeek OpenAI-compatible client if configured."""
    global _deepseek_cache
    api_key, base_url = _get_env_pair("DEEPSEEK_API_KEY", "DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
    cached_key, cached_url, cached_client = _deepseek_cache

    if not api_key:
        _deepseek_cache = (None, None, None)
        return None

    if cached_client is None or api_key != cached_key or base_url != cached_url:
        logger.info("Initializing cached DeepSeek client")
        cached_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        _deepseek_cache = (api_key, base_url, cached_client)

    return cached_client


def get_gemini_client() -> Optional[AsyncOpenAI]:
    """Return a cached Gemini OpenAI-compatible client if configured."""
    global _gemini_cache
    api_key, base_url = _get_env_pair(
        "GEMINI_API_KEY",
        "GEMINI_API_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    cached_key, cached_url, cached_client = _gemini_cache

    if not api_key:
        _gemini_cache = (None, None, None)
        return None

    if cached_client is None or api_key != cached_key or base_url != cached_url:
        logger.info("Initializing cached Gemini client")
        cached_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        _gemini_cache = (api_key, base_url, cached_client)

    return cached_client


def client_for_model(model: str, default_client: AsyncOpenAI) -> AsyncOpenAI:
    """Pick the appropriate cached client for a given model name."""
    m = (model or "").lower()

    if "deepseek" in m:
        ds = get_deepseek_client()
        if ds is not None:
            return ds

    if "gemini" in m:
        gm = get_gemini_client()
        if gm is not None:
            return gm

    return default_client
