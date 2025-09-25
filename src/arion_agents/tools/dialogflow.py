from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional, Set

from google.cloud import dialogflowcx_v3
from google.oauth2 import service_account
from google.protobuf.json_format import MessageToDict

from arion_agents.tools.base import BaseTool, ToolRunInput, ToolRunOutput


_WARMED_SESSIONS: Set[str] = set()


class DialogFlowCXTool(BaseTool):
    """Invoke DialogFlow CX detect_intent for a single exchange."""

    SYSTEM_PROJECT = "dialogflow_project_id"
    SYSTEM_LOCATION = "dialogflow_location"
    SYSTEM_ENVIRONMENT = "dialogflow_environment"
    SYSTEM_LANGUAGE = "dialogflow_language_code"
    SYSTEM_AGENT_ID = "dialogflow_agent_id"
    SYSTEM_SESSION_ID = "dialogflow_session_id"
    SYSTEM_SESSION_STARTED = "dialogflow_session_started"
    SYSTEM_USERNAME = "dialogflow_username"

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        try:
            credentials = self._build_credentials()
        except Exception as exc:
            return ToolRunOutput(ok=False, error=f"dialogflow credentials error: {exc}")

        system = payload.system or {}
        agent_params = payload.params or {}

        try:
            project_id = self._required(system, self.SYSTEM_PROJECT)
            location = self._required(system, self.SYSTEM_LOCATION)
            language_code = self._required(system, self.SYSTEM_LANGUAGE)
            agent_id = self._required(system, self.SYSTEM_AGENT_ID)
        except ValueError as exc:
            return ToolRunOutput(ok=False, error=str(exc))

        environment = system.get(self.SYSTEM_ENVIRONMENT)
        session_id = system.get(self.SYSTEM_SESSION_ID) or uuid.uuid4().hex
        user_query = agent_params.get("query")

        if isinstance(user_query, str):
            user_query = user_query.strip()
        if not user_query:
            return ToolRunOutput(
                ok=False, error="query is required for DialogFlow CX tool"
            )

        original_query = user_query
        session_cache_key = f"{project_id}:{agent_id}:{session_id}"
        is_first_call = session_cache_key not in _WARMED_SESSIONS
        effective_query = "ewc" if is_first_call else user_query

        client_options = {"api_endpoint": f"{location}-dialogflow.googleapis.com"}
        client = dialogflowcx_v3.SessionsClient(
            credentials=credentials, client_options=client_options
        )

        if environment:
            session_path = (
                f"projects/{project_id}/locations/{location}/agents/{agent_id}/"
                f"environments/{environment}/sessions/{session_id}"
            )
        else:
            session_path = client.session_path(
                project=project_id,
                location=location,
                agent=agent_id,
                session=session_id,
            )

        session_parameters = self._build_session_parameters(system, agent_params)
        summary_mode = self._resolve_summary_mode(system, agent_params)

        query_params = dialogflowcx_v3.QueryParameters(parameters=session_parameters)

        request = dialogflowcx_v3.DetectIntentRequest(
            session=session_path,
            query_input=dialogflowcx_v3.QueryInput(
                text=dialogflowcx_v3.TextInput(text=effective_query),
                language_code=language_code,
            ),
            query_params=query_params,
        )

        warmup_result: Optional[Dict[str, Any]] = None
        if not system.get(self.SYSTEM_SESSION_STARTED) and effective_query != "ewc":
            warmup_request = dialogflowcx_v3.DetectIntentRequest(
                session=session_path,
                query_input=dialogflowcx_v3.QueryInput(
                    text=dialogflowcx_v3.TextInput(text="ewc"),
                    language_code=language_code,
                ),
                query_params=query_params,
            )
            try:
                warmup_response = client.detect_intent(request=warmup_request)
                warmup_result = MessageToDict(
                    warmup_response._pb, preserving_proto_field_name=True
                )
                system[self.SYSTEM_SESSION_STARTED] = True
                system[self.SYSTEM_SESSION_ID] = session_id
            except Exception as exc:
                return ToolRunOutput(ok=False, error=f"dialogflow warmup failed: {exc}")

        try:
            response = client.detect_intent(request=request)
        except Exception as exc:
            return ToolRunOutput(
                ok=False, error=f"dialogflow detect_intent failed: {exc}"
            )

        response_dict = MessageToDict(response._pb, preserving_proto_field_name=True)
        system[self.SYSTEM_SESSION_STARTED] = True
        system[self.SYSTEM_SESSION_ID] = session_id
        if is_first_call:
            _WARMED_SESSIONS.add(session_cache_key)

        warmup_summary = None
        if warmup_result is not None:
            warmup_summary = self._summarize_response(warmup_result, summary_mode)

        result_summary = self._summarize_response(response_dict, summary_mode)
        if warmup_summary and not result_summary.get("message"):
            result_summary = warmup_summary

        return ToolRunOutput(
            ok=True,
            result={
                "session_id": session_id,
                "query": effective_query,
                "original_query": original_query if original_query != effective_query else None,
                "summary": result_summary,
                "session_parameters": session_parameters,
                "warmup_sent": warmup_result is not None or is_first_call,
                "warmup_summary": warmup_summary,
                "summary_mode": summary_mode,
                "raw_response": response_dict,
            },
        )

    def _build_credentials(self):
        if not self.secret_value:
            raise ValueError("missing service account secret")
        try:
            info = json.loads(self.secret_value)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"invalid JSON credentials: {exc}") from exc
        return service_account.Credentials.from_service_account_info(info)

    @staticmethod
    def _required(data: Dict[str, Any], key: str) -> Any:
        value = data.get(key)
        if value in (None, ""):
            raise ValueError(f"missing system param '{key}'")
        return value

    @staticmethod
    def _normalize_environment_path(
        project_id: str, location: str, agent_id: str, environment: str
    ) -> str:
        environment = environment.strip()
        if "/" in environment:
            return environment
        return (
            f"projects/{project_id}/locations/{location}/agents/{agent_id}/"
            f"environments/{environment}"
        )

    def _build_session_parameters(
        self, system: Dict[str, Any], agent_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        session_params: Dict[str, Any] = {}

        # Check for username in system params, then agent params.
        username = agent_params.get("username") or system.get("username")
        if username:
            session_params["username"] = str(username)

        customer_verified = agent_params.get("customer_verified") or system.get(
            "customer_verified"
        )
        if customer_verified is not None:
            session_params["customer_verified"] = customer_verified

        # Allow for additional, dynamic session parameters.
        extra_params = agent_params.get("session_parameters") or {}
        for key, value in extra_params.items():
            session_params[key] = value

        return session_params

    @staticmethod
    def _resolve_summary_mode(
        system: Dict[str, Any], agent_params: Dict[str, Any]
    ) -> str:
        override = agent_params.get("summary_mode")
        if isinstance(override, str) and override.strip():
            return override.strip().lower()
        sys_mode = system.get("dialogflow_summary_mode")
        if isinstance(sys_mode, str) and sys_mode.strip():
            return sys_mode.strip().lower()
        return "simple"

    @staticmethod
    def _summarize_response(response: Dict[str, Any], mode: str) -> Dict[str, Any]:
        def pick(source: Dict[str, Any], *keys: str) -> Any:
            if not isinstance(source, dict):
                return None
            for key in keys:
                if key in source:
                    return source[key]
            return None

        query_result = pick(response, "queryResult", "query_result") or {}
        if not isinstance(query_result, dict):
            query_result = {}

        messages: list[str] = []
        response_messages = pick(
            query_result, "responseMessages", "response_messages"
        ) or []
        for msg in response_messages or []:
            if isinstance(msg, dict):
                text_block = pick(msg.get("text") or {}, "text")
                if isinstance(text_block, list) and text_block:
                    messages.extend(str(t).strip() for t in text_block if t)

        simple_message = " ".join(m for m in messages if m).strip()

        if mode != "detailed":
            return {"message": simple_message}

        summary: Dict[str, Any] = {
            "response_id": pick(response, "responseId", "response_id"),
            "messages": messages,
            "intent": None,
            "intent_confidence": None,
            "follow_up_prompt": None,
            "message": simple_message,
        }

        intent = pick(query_result, "intent") or {}
        if isinstance(intent, dict):
            name = pick(intent, "displayName", "display_name", "name")
            if name:
                summary["intent"] = name

        confidence = pick(
            query_result, "intentDetectionConfidence", "intent_detection_confidence"
        )
        if isinstance(confidence, (int, float)):
            summary["intent_confidence"] = confidence

        if messages:
            summary["follow_up_prompt"] = messages[-1]

        return summary
