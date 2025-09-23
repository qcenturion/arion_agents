#!/usr/bin/env python3
"""Helper for printing raw Gemini responses and usage metadata."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from arion_agents.llm import GeminiDecideResult, LLMNotConfigured, gemini_decide


def _to_json(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect raw Gemini API responses")
    parser.add_argument("prompt", help="Prompt to send to Gemini")
    parser.add_argument("--model", help="Override GEMINI_MODEL")
    args = parser.parse_args()

    try:
        result: GeminiDecideResult = gemini_decide(args.prompt, args.model)
    except LLMNotConfigured as exc:
        sys.stderr.write(f"Gemini not configured: {exc}\n")
        return 2
    except Exception as exc:  # pragma: no cover - runtime debugging helper
        sys.stderr.write(f"Gemini call failed: {exc}\n")
        return 1

    print("=== Gemini Decide Result ===")
    print("Text:")
    print(result.text)
    print()
    print("Usage (normalized):")
    print(_to_json(result.usage))
    print()
    print("Usage (raw attempts):")
    print(_to_json(result.usage_raw))
    print()
    print("Full response payload:")
    print(_to_json(result.response_payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
