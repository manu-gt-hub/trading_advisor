import re
import httpx
from openai import OpenAI
from dotenv import load_dotenv
import os
import logging
from tools.general import ssl_verify as _ssl_verify

logger = logging.getLogger(__name__)

if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

# Timeout for LLM HTTP calls (seconds): connect, read
_LLM_TIMEOUT = (30, 120)

# ---------------------------------------------------------------------------
# LLM AS AUDITOR (NOT a decision system)
# The technical engine is the sole decider. The LLM is invoked only when the
# technical signal is BUY and may ONLY: (1) flag incoherence between the
# structured technical output and the raw indicators, and (2) propose a small
# bounded confidence adjustment. It must NOT re-classify the signal.
# ---------------------------------------------------------------------------
audit_system_prompt = (
    "You are a technical-analysis AUDITOR, not a decision maker. "
    "A deterministic quantitative engine has ALREADY decided BUY. You cannot change that decision. "
    "Your ONLY job is to: (1) verify internal COHERENCE between the engine's regime, sub-scores "
    "(trend_score, momentum_score, risk_score) and the raw indicators, and (2) propose a SMALL bounded "
    "confidence adjustment. Do NOT re-classify to HOLD/SELL and do NOT output a new decision. "
    "Flag INCOHERENT only when the structured output clearly contradicts the indicators "
    "(e.g. BUY with strong bearish divergence, overbought exhaustion, or distribution regime). "
    "Otherwise flag COHERENT."
)


def generate_audit_prompt(metrics, current_price, technical_result, bounds):
    lo, hi = bounds
    regime = technical_result.get("regime", "UNKNOWN")
    strength = technical_result.get("strength", "UNKNOWN")
    sub = technical_result.get("sub_scores", {})
    return (
        f"The engine decided BUY for a stock priced at {current_price}.\n"
        f"Structured technical output:\n"
        f"- regime = {regime}\n"
        f"- strength = {strength}\n"
        f"- trend_score = {sub.get('trend_score')}\n"
        f"- momentum_score = {sub.get('momentum_score')}\n"
        f"- risk_score = {sub.get('risk_score')}\n\n"
        f"Raw indicators:\n{metrics}\n\n"
        f"AUDIT TASK: Check coherence between the structured output and the raw indicators. "
        f"Propose a confidence adjustment in the range [{lo}, {hi}] (use {hi} only if everything aligns, "
        f"negative if you find contradictions/risks).\n"
        f"Output EXACTLY this format on one line:\n"
        f"COHERENT|INCOHERENT | adjustment=<float> | <reason, max 20 words>"
    )


def parse_audit_response(text, bounds):
    """
    Parse an auditor response into a structured dict.
    Returns: {"coherent": bool, "adjustment": float, "reason": str, "raw": str}
    Defaults are conservative (coherent=True, adjustment=0.0) when parsing fails.
    """
    lo, hi = bounds
    result = {"coherent": True, "adjustment": 0.0, "reason": "", "raw": text if isinstance(text, str) else ""}
    if not isinstance(text, str):
        return result

    upper = text.upper()
    if "INCOHERENT" in upper:
        result["coherent"] = False
    elif "COHERENT" in upper:
        result["coherent"] = True

    match = re.search(r"adjustment\s*=\s*([+-]?\d*\.?\d+)", text, re.IGNORECASE)
    if match:
        try:
            adj = float(match.group(1))
            result["adjustment"] = max(lo, min(hi, adj))
        except ValueError:
            pass

    parts = text.split("|")
    if parts:
        result["reason"] = parts[-1].strip()
    return result


def audit_buy_signal(signals, symbol, current_price, technical_result):
    """
    Audit a technical BUY signal with the LLM. The LLM only checks coherence and
    proposes a bounded confidence adjustment; it never re-classifies.

    Returns the structured dict from parse_audit_response.
    """
    from tools import technical_engine

    bounds = technical_engine.load_config().get("llm_audit", {}).get(
        "confidence_adjustment_bounds", [-0.3, 0.1]
    )
    check_llm_env()
    model_name = os.getenv("GPT_MODEL_NAME", "gpt-4o")
    metrics = "\n".join([f"{k} = {v} " for k, v in signals.items()])
    prompt = generate_audit_prompt(metrics, current_price, technical_result, bounds)

    try:
        with httpx.Client(verify=_ssl_verify(), timeout=_LLM_TIMEOUT) as http_client:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": audit_system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
        raw = response.choices[0].message.content
        logger.info(f"LLM audit for {symbol}: {raw}")
        return parse_audit_response(raw, bounds)
    except Exception as e:
        logger.error(f"LLM audit failed for {symbol}: {e}")
        # Fail conservative: flag incoherent and apply max negative adjustment
        # so a broken LLM never green-lights a risky trade
        return {"coherent": False, "adjustment": bounds[0], "reason": f"audit error: {e}", "raw": ""}

def check_llm_env():
    """
    Ensure the necessary environment variables are set for the LLM API key, model name, and revenue percentage.
    """
    missing_env_vars = []
    
    if not os.getenv("OPENAI_API_KEY"):
        missing_env_vars.append("OPENAI_API_KEY")

    if not os.getenv('GPT_MODEL_NAME'):
        missing_env_vars.append("GPT_MODEL_NAME")

    if not os.getenv('REVENUE_PERCENTAGE'):
        missing_env_vars.append("REVENUE_PERCENTAGE")

    if missing_env_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_env_vars)}")
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_env_vars)}")
