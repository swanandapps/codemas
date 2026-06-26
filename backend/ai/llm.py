"""Shared OpenAI client for all three async AI features.

Design rules:
- Reads OPENAI_API_KEY from the environment. If it is missing, every call raises
  LLMUnavailable so the calling Celery task can log-and-skip cleanly — the AI
  features are strictly additive and must never break the core pipeline.
- All calls force a JSON object response so callers get structured data, no parsing
  of free-form prose.
- A conservative timeout keeps a hung provider from tying up a Celery worker.
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

# gpt-4o-mini is cheap and fast — these are all small, async, best-effort calls.
DEFAULT_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
REQUEST_TIMEOUT = int(os.environ.get('OPENAI_TIMEOUT', '30'))  # seconds


class LLMUnavailable(Exception):
    """Raised when no API key is configured or the provider call fails."""
    pass


def _client():
    """Build an OpenAI client, or raise LLMUnavailable if not configured/installed."""
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise LLMUnavailable('OPENAI_API_KEY is not set')
    try:
        from openai import OpenAI  # imported lazily so the app loads without the lib
    except ImportError as e:
        raise LLMUnavailable(f'openai package not installed: {e}')
    return OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT)


def call_json(system_prompt, user_prompt, model=None):
    """Run one chat completion that must return a JSON object.

    Returns the parsed dict. Raises LLMUnavailable on any failure (no key,
    network error, malformed JSON) so callers have a single thing to catch.
    """
    client = _client()
    try:
        response = client.chat.completions.create(
            model=model or DEFAULT_MODEL,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            response_format={'type': 'json_object'},  # structured output, no prose
            temperature=0.2,  # low — we want consistent, graded judgements
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except LLMUnavailable:
        raise
    except Exception as e:  # network, rate limit, JSON decode — all best-effort
        logger.warning('LLM call failed: %s', e)
        raise LLMUnavailable(str(e))
