#!/usr/bin/env python3
"""Seed a demo network that exercises the DialogFlow CX tool."""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, Optional

import requests


API_ROOT = os.getenv("API_URL", "http://localhost:8000")
NETWORK_NAME = os.getenv("DIALOGFLOW_DEMO_NETWORK", "dialogflow_multiple_accounts_demo")
TOOL_KEY = os.getenv("DIALOGFLOW_DEMO_TOOL", "dialogflow_cx_tester")
AGENT_KEY = os.getenv("DIALOGFLOW_DEMO_AGENT", "dialogflow_multi_account_tester")
EVAL_AGENT_KEY = os.getenv("DIALOGFLOW_EVAL_AGENT", "dialogflow_evaluator")
SECRET_REF = os.getenv("DIALOGFLOW_DEMO_SECRET_REF", "dialogflow_service_account.json")
DEFAULT_AGENT_ID = os.getenv(
    "DIALOGFLOW_AGENT_ID", "fde810bf-b9fb-4924-85be-2aab8b4896e1"
)


AGENT_PROMPT = """
You are a QA analyst validating that the DialogFlow CX bot forbids customers from
holding more than one account.

Workflow:
1. On your first step in every run, issue a USE_TOOL action with
   dialogflow_cx_tester and set `query` to "start conversation". This primes the
   DialogFlow session and returns the welcome message. Do not expose or mention
   this warm-up utterance to the operator.
2. After the warm-up, send natural customer-style questions to the bot using the
   same tool so you can determine whether multiple accounts are permitted. Ask
   directly about the policy when needed.
3. When you have sufficient evidence, finish with a RESPOND action that quotes
   or paraphrases the bot's answer and clearly states whether multiple accounts
   are allowed. Do not guess; the bot's responses are the source of truth.

Never send the literal text "ewc" and never discuss internal warm-up mechanics
with the operator.
""".strip()


EVAL_PROMPT = """
You are the evaluation specialist who determines whether the agent under test
correctly established the customer's eligibility for multiple accounts.

You receive the entire conversation history via the context section. Review the
tool outputs and the tester agent's reasoning to understand the evidence.

Produce a RESPOND action with action_details.payload.response_payload matching
the provided schema:
- response_payload.answer (string): short natural language summary of the
  chatbot's policy response.
- response_payload.evaluation.verdict (pass|fail|partial|error|unknown): your
  judgement about whether the tester achieved the correct outcome relative to
  the expected policy.
- response_payload.evaluation.notes (string, optional): supporting explanation
  describing important signals (e.g., conflicting answers, stalled dialogues,
  missing evidence).

Only return PASS when the chatbot clearly confirms the correct policy. Mark
FAIL when the bot gives an explicit wrong answer. Use PARTIAL when the evidence
is ambiguous but leans toward compliance, ERROR when the run failed for
infrastructure reasons, and UNKNOWN when you cannot reach a conclusion.
""".strip()


def _url(path: str) -> str:
    return f"{API_ROOT}{path}"


def _ensure_ok(resp: requests.Response, *expected: int) -> Any:
    if not expected:
        expected = (200,)
    if resp.status_code not in expected:
        msg = f"HTTP {resp.status_code} for {resp.request.method} {resp.request.url}: {resp.text}"
        raise RuntimeError(msg)
    if resp.content:
        return resp.json()
    return None


def wait_for_api(timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(_url("/health"), timeout=5)
            if resp.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1.5)
    raise RuntimeError("API did not become available in time")


def upsert_tool() -> int:
    payload = {
        "key": TOOL_KEY,
        "display_name": "DialogFlow CX Tester",
        "description": "Sends utterances to the DialogFlow CX bot under test.",
        "provider_type": "dialogflow:cx",
        "params_schema": {
            "query": {"source": "agent", "required": True},
            "username": {"source": "system", "required": False},
            "customer_verified": {"source": "system", "required": False},
            "session_parameters": {"source": "system", "required": False},
            "dialogflow_project_id": {"source": "system", "required": True},
            "dialogflow_location": {"source": "system", "required": True},
            "dialogflow_environment": {"source": "system", "required": False},
            "dialogflow_language_code": {"source": "system", "required": True},
            "dialogflow_agent_id": {"source": "system", "required": True},
            "dialogflow_session_id": {"source": "system", "required": False},
        },
        "secret_ref": SECRET_REF,
        "additional_data": {
            "description": "Invoke DialogFlow CX detectIntent using the configured service account.",
            "agent_params_json_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "description": "User-style utterance to send to the bot.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }

    existing_tools = _ensure_ok(requests.get(_url("/config/tools")))
    for tool in existing_tools or []:
        if tool.get("key") == TOOL_KEY:
            tool_id = tool["id"]
            patch_payload = {
                "display_name": payload["display_name"],
                "description": payload["description"],
                "provider_type": payload["provider_type"],
                "params_schema": payload["params_schema"],
                "secret_ref": payload["secret_ref"],
                "additional_data": payload["additional_data"],
            }
            _ensure_ok(
                requests.patch(_url(f"/config/tools/{tool_id}"), json=patch_payload)
            )
            return tool_id

    created = _ensure_ok(requests.post(_url("/config/tools"), json=payload), 201)
    return created["id"]


def recreate_network() -> int:
    networks = _ensure_ok(requests.get(_url("/config/networks")))
    for net in networks or []:
        if net.get("name") == NETWORK_NAME:
            _ensure_ok(requests.delete(_url(f"/config/networks/{net['id']}")), 204)
            break

    payload = {
        "name": NETWORK_NAME,
        "description": "DialogFlow CX policy regression harness",
        "additional_data": {
            "respond_payload_guidance": "The evaluation agent must emit response_payload.answer (string) and response_payload.evaluation.verdict (pass|fail|partial|error|unknown).",
            "respond_payload_schema": {
                "type": "object",
                "properties": {
                    "response_payload": {
                        "type": "object",
                        "properties": {
                            "answer": {"type": "string"},
                            "evaluation": {
                                "type": "object",
                                "properties": {
                                    "verdict": {
                                        "type": "string",
                                        "enum": [
                                            "pass",
                                            "fail",
                                            "partial",
                                            "error",
                                            "unknown"
                                        ]
                                    },
                                    "notes": {"type": "string"}
                                },
                                "required": ["verdict"],
                                "additionalProperties": False
                            }
                        },
                        "required": ["answer", "evaluation"],
                        "additionalProperties": False
                    }
                },
                "required": ["response_payload"],
                "additionalProperties": False
            },
            "respond_payload_example": {
                "response_payload": {
                    "answer": "The bot explicitly states customers may only maintain a single account.",
                    "evaluation": {
                        "verdict": "pass",
                        "notes": "Bot refused the multi-account request and cited the policy."
                    }
                }
            }
        },
    }
    created = _ensure_ok(requests.post(_url("/config/networks"), json=payload), 201)
    return created["id"]


def add_tool_to_network(network_id: int) -> int:
    result = _ensure_ok(
        requests.post(
            _url(f"/config/networks/{network_id}/tools"),
            json={"tool_keys": [TOOL_KEY]},
        )
    )
    if not result:
        raise RuntimeError("Failed to attach tool to network")

    # Find the network-local tool id for later reference.
    graph = _ensure_ok(requests.get(_url(f"/config/networks/{network_id}/graph")))
    for tool in graph.get("tools", []):
        if tool.get("key") == TOOL_KEY:
            return tool["id"]
    raise RuntimeError("network tool not found after creation")


def create_agents(network_id: int) -> tuple[int, int]:
    # Create evaluation agent first so the network immediately satisfies the RESPOND constraint.
    eval_payload = {
        "key": EVAL_AGENT_KEY,
        "display_name": "DialogFlow Evaluation Agent",
        "allow_respond": True,
        "is_default": False,
        "prompt_template": EVAL_PROMPT,
    }
    evaluator = _ensure_ok(
        requests.post(_url(f"/config/networks/{network_id}/agents"), json=eval_payload),
        201,
    )

    primary_payload = {
        "key": AGENT_KEY,
        "display_name": "DialogFlow Account Policy Tester",
        "allow_respond": False,
        "is_default": True,
        "prompt_template": AGENT_PROMPT,
    }
    primary = _ensure_ok(
        requests.post(_url(f"/config/networks/{network_id}/agents"), json=primary_payload),
        201,
    )

    return primary["id"], evaluator["id"]


def equip_agent(network_id: int, agent_id: int) -> None:
    _ensure_ok(
        requests.put(
            _url(f"/config/networks/{network_id}/agents/{agent_id}/tools"),
            json={"tool_keys": [TOOL_KEY]},
        )
    )


def set_agent_routes(network_id: int, agent_id: int, routes: list[str]) -> None:
    _ensure_ok(
        requests.put(
            _url(f"/config/networks/{network_id}/agents/{agent_id}/routes"),
            json={"agent_keys": routes},
        )
    )


def publish_network(network_id: int) -> None:
    payload = {
        "notes": "Initial DialogFlow CX demo network",
        "created_by": "seed_dialogflow_demo",
        "published_by": "seed_dialogflow_demo",
    }
    _ensure_ok(
        requests.post(
            _url(f"/config/networks/{network_id}/versions/compile_and_publish"),
            json=payload,
        )
    )


def run_smoke_test() -> Optional[Dict[str, Any]]:
    payload = {
        "network": NETWORK_NAME,
        "user_message": (
            "You are a customer of Dafabet interacting with the Dafabet chatbot. "
            "Attempt to determine if you are allowed to have more than one account "
            "by conversing with the chatbot."
        ),
        "system_params": {
            "dialogflow_agent_id": DEFAULT_AGENT_ID,
            "username": "CSTESTINR",
            "customer_verified": "true",
        },
        "debug": False,
    }
    try:
        resp = requests.post(_url("/run"), json=payload, timeout=120)
        if resp.status_code != 200:
            print(
                f"Smoke test failed with status {resp.status_code}: {resp.text}",
                file=sys.stderr,
            )
            return None
        return resp.json()
    except requests.RequestException as exc:
        print(f"Smoke test request error: {exc}", file=sys.stderr)
        return None


def main() -> None:
    print(f"Using API root: {API_ROOT}")
    wait_for_api()

    print("Upserting DialogFlow CX tool...")
    tool_id = upsert_tool()
    print(f"Tool ready (id={tool_id})")

    print("Creating fresh network...")
    network_id = recreate_network()
    print(f"Network id={network_id}")

    print("Attaching tool to network...")
    network_tool_id = add_tool_to_network(network_id)
    print(f"Network tool id={network_tool_id}")

    print("Creating agents...")
    primary_agent_id, evaluator_agent_id = create_agents(network_id)
    print(f"Primary agent id={primary_agent_id}, evaluator id={evaluator_agent_id}")

    print("Equipping primary agent with DialogFlow tool...")
    equip_agent(network_id, primary_agent_id)

    print("Configuring agent routing graph...")
    set_agent_routes(network_id, primary_agent_id, [EVAL_AGENT_KEY])
    set_agent_routes(network_id, evaluator_agent_id, [])

    print("Publishing network version...")
    publish_network(network_id)
    print("Network published.")

    if os.getenv("DIALOGFLOW_DEMO_SKIP_RUN"):
        print("Skipping smoke test (DIALOGFLOW_DEMO_SKIP_RUN set).")
        return

    print("Running smoke test via /run...")
    result = run_smoke_test()
    if not result:
        print("Smoke test did not complete. See logs above.")
        return

    final = result.get("final")
    if final:
        print("Final payload:")
        print(final)
    else:
        print("Run completed. Inspect response for details:")
        print(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - CLI safety
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
