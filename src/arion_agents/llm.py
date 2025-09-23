from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
import re


class LLMNotConfigured(Exception):
    pass


def _read_local_key() -> Optional[str]:
    # Try project-local secrets file first
    local_path = os.path.join(
        os.path.dirname(__file__), "..", "..", ".secrets", "gemini_api_key"
    )
    local_path = os.path.normpath(local_path)
    try:
        with open(local_path, "r", encoding="utf-8") as f:
            key = f.read().strip()
            return key or None
    except Exception:
        return None


def _require_gemini_config() -> tuple[str, str]:
    # Prefer env var; fall back to local file
    api_key = os.getenv("GEMINI_API_KEY") or _read_local_key()
    if not api_key:
        raise LLMNotConfigured(
            "GEMINI_API_KEY not set and no .secrets/gemini_api_key found"
        )
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    return api_key, model


def gemini_complete(prompt: str, model: Optional[str] = None) -> str:
    """Return a simple text completion from Gemini using google-genai client.

    - Uses env `GEMINI_API_KEY` or `.secrets/gemini_api_key`.
    - Disables "thinking" via ThinkingConfig(thinking_budget=0).
    - Falls back to google-generativeai if google-genai is unavailable.
    """
    api_key, default_model = _require_gemini_config()

    # Preferred: google-genai client (new SDK)
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=api_key)
        model_name = model or default_model
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        return getattr(resp, "text", "") or ""
    except Exception:
        # Fallback: older google-generativeai client
        try:
            import google.generativeai as genai_old  # type: ignore
        except Exception as e:  # pragma: no cover
            raise LLMNotConfigured(
                "Neither google-genai nor google-generativeai is installed."
            ) from e

        genai_old.configure(api_key=api_key)
        model_name = model or default_model
        try:
            gm = genai_old.GenerativeModel(model_name)
            resp = gm.generate_content(prompt)
            return getattr(resp, "text", "") or ""
        except Exception as e:
            raise RuntimeError(f"Gemini completion failed: {e}")


def _strip_code_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\n([\s\S]*?)\n```", text)
    return m.group(1) if m else text


@dataclass
class GeminiDecideResult:
    text: str
    parsed: Optional[Any]
    usage: Optional[Dict[str, int]]
    usage_raw: Optional[Dict[str, Any]]
    response_payload: Any


def _usage_model_to_dict(usage: Any) -> Optional[Dict[str, Any]]:
    if usage is None:
        return None
    for attr in ("model_dump", "to_json", "dict", "to_dict"):
        if hasattr(usage, attr):
            method = getattr(usage, attr)
            try:
                data = method() if attr not in ("to_json",) else json.loads(method())
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    if isinstance(usage, dict):
        return usage
    raw: Dict[str, Any] = {}
    for key in (
        "prompt_token_count",
        "response_token_count",
        "candidates_token_count",
        "output_token_count",
        "total_token_count",
    ):
        if hasattr(usage, key):
            raw[key] = getattr(usage, key)
    return raw or None


def _normalize_usage_counts(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    if not raw:
        return None

    def _pick(keys: tuple[str, ...]) -> Optional[int]:
        for key in keys:
            val = raw.get(key)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    continue
        return None

    prompt = _pick(
        (
            "prompt_token_count",
            "promptTokenCount",
            "input_token_count",
            "inputTokenCount",
        )
    )
    response = _pick(
        (
            "response_token_count",
            "candidates_token_count",
            "output_token_count",
            "candidatesTokenCount",
        )
    )
    total = _pick(("total_token_count", "totalTokenCount"))

    if prompt is None and response is None and total is None:
        return None
    return {
        "prompt_tokens": prompt or 0,
        "response_tokens": response or 0,
        "total_tokens": total or ((prompt or 0) + (response or 0)),
    }


def _response_to_payload(resp: Any) -> Any:
    for attr in ("to_json_dict", "model_dump", "dict", "to_dict"):
        if hasattr(resp, attr):
            method = getattr(resp, attr)
            try:
                data = method()
                return data
            except Exception:
                continue
    if hasattr(resp, "to_json"):
        try:
            return json.loads(resp.to_json())
        except Exception:
            pass
    return str(resp)


def _sum_usage_counts(
    items: list[Optional[Dict[str, int]]],
) -> Optional[Dict[str, int]]:
    totals = {"prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0}
    seen = False
    for item in items:
        if not item:
            continue
        seen = True
        for key in totals:
            val = item.get(key)
            if isinstance(val, int):
                totals[key] += val
    return totals if seen else None


def gemini_decide(prompt: str, model: Optional[str] = None) -> GeminiDecideResult:
    """Structured decision in JSON mode without response_schema + robust parsing with one retry."""
    api_key, default_model = _require_gemini_config()

    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
    from arion_agents.agent_decision import AgentDecision

    client = genai.Client(api_key=api_key)
    model_name = model or default_model

    usage_raw_attempts: list[Optional[Dict[str, Any]]] = []
    usage_counts_attempts: list[Optional[Dict[str, int]]] = []
    response_payloads: list[Any] = []

    def _call(p: str) -> Any:
        resp = client.models.generate_content(
            model=model_name,
            contents=p,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
            ),
        )
        usage_raw = _usage_model_to_dict(getattr(resp, "usage_metadata", None))
        usage_counts = _normalize_usage_counts(usage_raw)
        usage_raw_attempts.append(usage_raw)
        usage_counts_attempts.append(usage_counts)
        response_payloads.append(_response_to_payload(resp))
        return resp

    primary_resp = _call(prompt)
    primary_text = getattr(primary_resp, "text", "") or ""
    try:
        clean = _strip_code_fences(primary_text)
        parsed = AgentDecision.model_validate_json(clean)
        combined_usage = _sum_usage_counts(usage_counts_attempts)
        payload: Any = (
            response_payloads if len(response_payloads) > 1 else response_payloads[0]
        )
        attempts_raw = [item for item in usage_raw_attempts if item]
        usage_raw = {"attempts": attempts_raw} if attempts_raw else None
        if usage_raw and combined_usage:
            usage_raw["combined"] = combined_usage
        return GeminiDecideResult(
            text=primary_text,
            parsed=parsed,
            usage=combined_usage,
            usage_raw=usage_raw,
            response_payload=payload,
        )
    except Exception:
        retry_prompt = f"{prompt}\n\nIMPORTANT: Return only raw JSON (no markdown, no backticks), nothing else."
        retry_resp = _call(retry_prompt)
        retry_text = getattr(retry_resp, "text", "") or ""
        clean2 = _strip_code_fences(retry_text)
        parsed2 = AgentDecision.model_validate_json(clean2)
        combined_usage = _sum_usage_counts(usage_counts_attempts)
        payload: Any = (
            response_payloads if len(response_payloads) > 1 else response_payloads[0]
        )
        attempts_raw = [item for item in usage_raw_attempts if item]
        usage_raw = {"attempts": attempts_raw} if attempts_raw else None
        if usage_raw and combined_usage:
            usage_raw["combined"] = combined_usage
        return GeminiDecideResult(
            text=retry_text,
            parsed=parsed2,
            usage=combined_usage,
            usage_raw=usage_raw,
            response_payload=payload,
        )
