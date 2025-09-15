from __future__ import annotations

import os
from typing import Optional
import re


class LLMNotConfigured(Exception):
    pass


def _read_local_key() -> Optional[str]:
    # Try project-local secrets file first
    local_path = os.path.join(os.path.dirname(__file__), "..", "..", ".secrets", "gemini_api_key")
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
        raise LLMNotConfigured("GEMINI_API_KEY not set and no .secrets/gemini_api_key found")
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


def gemini_decide(prompt: str, model: Optional[str] = None):
    """Structured decision in JSON mode without response_schema + robust parsing with one retry.

    Returns a tuple (raw_text, parsed AgentDecision).
    """
    api_key, default_model = _require_gemini_config()

    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
    from arion_agents.agent_decision import AgentDecision

    client = genai.Client(api_key=api_key)
    model_name = model or default_model

    def _call(p: str) -> str:
        resp = client.models.generate_content(
            model=model_name,
            contents=p,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
            ),
        )
        return getattr(resp, "text", "") or ""

    text = _call(prompt)
    try:
        clean = _strip_code_fences(text)
        parsed = AgentDecision.model_validate_json(clean)
        return text, parsed
    except Exception as e1:
        retry_prompt = f"{prompt}\n\nIMPORTANT: Return only raw JSON (no markdown, no backticks), nothing else."
        text2 = _call(retry_prompt)
        clean2 = _strip_code_fences(text2)
        parsed2 = AgentDecision.model_validate_json(clean2)
        return text2, parsed2
