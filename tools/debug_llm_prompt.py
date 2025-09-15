#!/usr/bin/env python3
import os
import sys
import requests
import json

# This script is for debugging the raw LLM response for a given network and user message.
# It calls the /prompts/resolve endpoint to get the exact prompt, then calls the LLM
# directly and prints the raw response.

API = os.getenv("API_URL", "http://localhost:8000")

def post(path: str, json_payload):
    """Helper for POST requests."""
    return requests.post(f"{API}{path}", json=json_payload)

def ensure_ok(r, expected=200):
    """Check for HTTP errors."""
    if r.status_code != expected:
        print(f"Error {r.status_code} for {r.request.method} {r.request.url}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json() if r.content else {}

def get_resolved_prompt(network: str, user_message: str) -> str:
    """Get the fully-resolved prompt from the API."""
    print(f"Resolving prompt for network '{network}'...")
    payload = {"network": network, "user_message": user_message}
    response_data = ensure_ok(post("/prompts/resolve", json_payload=payload))
    return response_data.get("prompt", "")

def call_gemini_directly(prompt: str) -> str:
    """Call the Gemini API directly to get the raw response."""
    print("Calling Gemini API...")
    try:
        # We are replicating the logic from src/arion_agents/llm.py
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            # Try to read from the local secrets file
            local_path = os.path.join(os.path.dirname(__file__), "..", ".secrets", "gemini_api_key")
            local_path = os.path.normpath(local_path)
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    api_key = f.read().strip()
            except FileNotFoundError:
                pass # Will be handled by the next check
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set and .secrets/gemini_api_key not found.")

        client = genai.Client(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
            ),
        )
        return getattr(resp, "text", "") or ""

    except ImportError:
        print("Error: 'google-generativeai' is not installed. Please install it.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred while calling Gemini: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    """Main function to run the debug script."""
    network_name = "sun_demo"
    user_message = "When does the sun rise and set?"

    # 1. Get the prompt
    prompt = get_resolved_prompt(network_name, user_message)
    if not prompt:
        print("Failed to resolve prompt. Exiting.", file=sys.stderr)
        sys.exit(1)
    
    print("\n" + "="*30)
    print("   RESOLVED PROMPT SENT TO LLM")
    print("="*30 + "\n")
    print(prompt)

    # 2. Get the raw LLM response
    raw_response = call_gemini_directly(prompt)

    print("\n" + "="*30)
    print("      RAW RESPONSE FROM LLM")
    print("="*30 + "\n")
    print(raw_response)

    # 3. Try to parse it to see the error
    print("\n" + "="*30)
    print("      ATTEMPTING TO PARSE")
    print("="*30 + "\n")
    try:
        parsed = json.loads(raw_response)
        print("JSON is valid.")
        # Here you could add Pydantic validation if you want to see the specific error
        from arion_agents.agent_decision import AgentDecision
        AgentDecision.model_validate(parsed)
        print("Pydantic validation successful!")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
    except Exception as e:
        print(f"Pydantic validation failed: {e}")


if __name__ == "__main__":
    main()
