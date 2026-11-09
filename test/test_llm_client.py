import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from tools import llm_client, technical_engine


@pytest.fixture
def anthropic_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("GPT_MODEL_NAME", raising=False)


def _response(*blocks, stop_reason="end_turn", stop_details=None):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, stop_details=stop_details)


def _mock_anthropic(response=None, side_effect=None):
    client = MagicMock()
    if side_effect is not None:
        client.beta.messages.create.side_effect = side_effect
    else:
        client.beta.messages.create.return_value = response
    return patch("anthropic.Anthropic", return_value=client), client


# ─── Provider / model selection ───────────────────────────────────────

def test_defaults_to_openai(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("GPT_MODEL_NAME", raising=False)
    assert llm_client.provider() == "openai"
    assert llm_client.api_key_env() == "OPENAI_API_KEY"
    assert llm_client.model_name() == "gpt-4o"


def test_anthropic_default_model_and_key(anthropic_env):
    assert llm_client.provider() == "anthropic"
    assert llm_client.api_key_env() == "ANTHROPIC_API_KEY"
    assert llm_client.model_name() == "claude-opus-5-5"


def test_model_name_precedence(monkeypatch, anthropic_env):
    monkeypatch.setenv("GPT_MODEL_NAME", "legacy-model")
    assert llm_client.model_name() == "legacy-model"
    monkeypatch.setenv("MODEL_NAME", "claude-sonnet-5-5")
    assert llm_client.model_name() == "claude-sonnet-5-5"


def test_provider_is_case_insensitive_and_validated(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", " Anthropic ")
    assert llm_client.provider() == "anthropic"
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(llm_client.LLMError):
        llm_client.provider()


# ─── Anthropic request / response handling ────────────────────────────

def test_anthropic_request_shape_and_text_extraction(anthropic_env):
    response = _response(SimpleNamespace(type="thinking", thinking=""),
                         SimpleNamespace(type="text", text="COHERENT | adjustment=0.05 | ok"))
    ctx, client = _mock_anthropic(response)
    with ctx:
        assert llm_client.complete("sys", "prompt") == "COHERENT | adjustment=0.05 | ok"
    kwargs = client.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "prompt"}]
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["fallbacks"] == "default"
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in kwargs  # current Claude models reject it


def test_anthropic_options_can_be_disabled_by_config(anthropic_env):
    cfg = json.loads(json.dumps(technical_engine.load_config()))
    cfg["llm"]["anthropic_effort"] = None
    cfg["llm"]["anthropic_fallbacks"] = None
    ctx, client = _mock_anthropic(_response(SimpleNamespace(type="text", text="NEUTRAL 50% - x")))
    with ctx, patch("tools.technical_engine.load_config", return_value=cfg):
        llm_client.complete("sys", "prompt")
    kwargs = client.beta.messages.create.call_args.kwargs
    assert not {"output_config", "fallbacks", "betas"} & set(kwargs)


def test_anthropic_refusal_raises(anthropic_env):
    ctx, _ = _mock_anthropic(_response(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")))
    with ctx, pytest.raises(llm_client.LLMError, match="refusal"):
        llm_client.complete("sys", "prompt")


def test_anthropic_empty_answer_raises(anthropic_env):
    ctx, _ = _mock_anthropic(_response(SimpleNamespace(type="thinking", thinking=""), stop_reason="max_tokens"))
    with ctx, pytest.raises(llm_client.LLMError, match="max_tokens"):
        llm_client.complete("sys", "prompt")


def test_anthropic_api_errors_become_llm_error(anthropic_env):
    import anthropic
    import httpx2
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    errors = [
        anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=request), body=None),
        anthropic.InternalServerError("boom", response=httpx2.Response(500, request=request), body=None),
        anthropic.APIConnectionError(request=request),
    ]
    for error in errors:
        ctx, _ = _mock_anthropic(side_effect=error)
        with ctx, pytest.raises(llm_client.LLMError):
            llm_client.complete("sys", "prompt")


# ─── Callers keep their behaviour with either provider ────────────────

def test_auditor_with_anthropic(monkeypatch, anthropic_env):
    from tools.llms import audit_buy_signal
    monkeypatch.setenv("REVENUE_PERCENTAGE", "10")
    ctx, _ = _mock_anthropic(_response(SimpleNamespace(type="text", text="INCOHERENT | adjustment=-0.2 | divergence")))
    with ctx:
        result = audit_buy_signal({"RSI": 60}, "AAPL", 150.0, {"regime": "TRENDING_UP", "sub_scores": {}})
    assert result["coherent"] is False and result["adjustment"] == -0.2


def test_auditor_fails_conservative_without_provider_key(monkeypatch, anthropic_env):
    from tools.llms import audit_buy_signal
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("REVENUE_PERCENTAGE", "10")
    result = audit_buy_signal({"RSI": 60}, "AAPL", 150.0, {"regime": "TRENDING_UP", "sub_scores": {}})
    assert result["coherent"] is False and result["adjustment"] < 0
    assert "ANTHROPIC_API_KEY" in result["reason"]


def test_news_sentiment_with_anthropic(anthropic_env):
    from tools.news_sentiment import analyze_news_sentiment_with_llm
    ctx, _ = _mock_anthropic(_response(SimpleNamespace(type="text", text="NEGATIVE 80% - recall")))
    with ctx:
        out = analyze_news_sentiment_with_llm("AAPL", [{"datetime": 1700000000, "headline": "Recall"}])
    assert out["sentiment"] == "NEGATIVE" and out["confidence"] == 0.8


def test_missing_env_names_the_selected_provider_key(monkeypatch, anthropic_env):
    import main
    for n in main.REQUIRED_ENV:
        monkeypatch.setenv(n, "x")
    monkeypatch.setenv("LLM_AUDIT_ENABLED", "true")
    monkeypatch.setenv("SHADOW_MODE_ENABLED", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert main.missing_env() == ["ANTHROPIC_API_KEY"]
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert main.missing_env() == ["LLM_PROVIDER (unsupported value)"]
