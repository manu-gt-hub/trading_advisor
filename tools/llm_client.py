"""
Provider-neutral access to the LLM used by the BUY auditor (llms.py) and the news
sentiment filter (news_sentiment.py). Both are short single-turn classifications that
return one line of text; callers parse it and keep their own failure behaviour.

  LLM_PROVIDER  "openai" (default) or "anthropic"
  MODEL_NAME    model id; when unset, llm.default_models in technical_config.json
                (legacy GPT_MODEL_NAME is still read)
  OPENAI_API_KEY / ANTHROPIC_API_KEY   key of the selected provider
"""
import logging
import os

from tools.general import ssl_verify

logger = logging.getLogger(__name__)

PROVIDER_KEYS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
_DEFAULT_MODELS = {"openai": "gpt-4o", "anthropic": "claude-opus-5-5"}
# Opt-in server-side fallback when a Claude model declines a request
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# (connect, read) seconds
DEFAULT_TIMEOUT = (30, 120)


class LLMError(Exception):
    """Any failure to obtain a usable answer (API error, refusal, empty output)."""


def _cfg():
    from tools import technical_engine
    return technical_engine.load_config().get("llm", {})


def provider():
    name = (os.environ.get("LLM_PROVIDER") or "openai").strip().lower()
    if name not in PROVIDER_KEYS:
        raise LLMError(f"Unsupported LLM_PROVIDER '{name}' (use one of: {', '.join(PROVIDER_KEYS)})")
    return name


def api_key_env():
    """Name of the API-key variable the selected provider needs."""
    return PROVIDER_KEYS[provider()]


def model_name():
    explicit = (os.environ.get("MODEL_NAME") or os.environ.get("GPT_MODEL_NAME") or "").strip()
    if explicit:
        return explicit
    name = provider()
    return _cfg().get("default_models", {}).get(name, _DEFAULT_MODELS[name])


def complete(system, prompt, timeout=DEFAULT_TIMEOUT):
    """Single-turn completion; returns the answer text or raises LLMError."""
    if provider() == "anthropic":
        return _complete_anthropic(system, prompt, timeout)
    return _complete_openai(system, prompt, timeout)


def _complete_openai(system, prompt, timeout):
    import httpx
    from openai import OpenAI

    with httpx.Client(verify=ssl_verify(), timeout=timeout) as http_client:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        response = client.chat.completions.create(
            model=model_name(),
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            temperature=0,
        )
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise LLMError("empty response")
    return text


def _complete_anthropic(system, prompt, timeout):
    import anthropic

    cfg = _cfg()
    request = {
        "model": model_name(),
        "max_tokens": int(cfg.get("anthropic_max_tokens", 4096)),
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Current Claude models reject temperature; effort sets thinking depth and cost
    if cfg.get("anthropic_effort"):
        request["output_config"] = {"effort": cfg["anthropic_effort"]}
    if cfg.get("anthropic_fallbacks"):
        request["fallbacks"] = cfg["anthropic_fallbacks"]
        request["betas"] = [_FALLBACK_BETA]

    connect, read = timeout
    with anthropic.DefaultHttpxClient(verify=ssl_verify()) as http_client:
        client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            http_client=http_client,
            timeout=anthropic.Timeout(read, connect=connect),
        )
        try:
            response = client.beta.messages.create(**request)
        except anthropic.RateLimitError as e:
            raise LLMError(f"rate limited: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"connection error: {e}") from e

    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None) if response.stop_details else None
        raise LLMError(f"model declined the request (refusal, category={category})")
    # Thinking blocks come first and carry no answer text
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise LLMError(f"empty response (stop_reason={response.stop_reason})")
    return text
