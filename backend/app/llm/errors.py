"""LLM error taxonomy (SEMANTIC_LAYER.md Part 1).

All LLM failures surface as one of these so callers (semantic layer, agent
loop) can branch deterministically — e.g. fall back to a degraded path on
LLMOutputError rather than 500-ing.
"""


class LLMError(Exception):
    """Base class for every LLM failure."""


class LLMConfigError(LLMError):
    """A requested profile is missing required env (base_url/model/api_key)."""


class LLMTimeoutError(LLMError):
    """The provider did not respond within the configured timeout."""


class LLMProviderError(LLMError):
    """The provider returned a non-2xx response after retries."""


class LLMOutputError(LLMError):
    """The response could not be parsed/validated (e.g. malformed JSON, or a
    missing tool-call when one was required)."""
