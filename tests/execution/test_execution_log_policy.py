from __future__ import annotations


import pytest

from pydantic import ValidationError

from arion_agents.logs.execution_log_policy import (
    ExecutionLogPolicy,
    build_execution_log_previews,
)


def test_build_execution_log_previews_with_policy() -> None:
    policy = ExecutionLogPolicy.model_validate(
        {
            "defaults": {
                "request_max_chars": 12,
                "response_max_chars": 16,
            },
            "tools": {
                "sun": {
                    "request": [
                        {"path": "lat", "label": "Latitude", "max_chars": 0},
                        {"path": "lng", "label": "Longitude", "max_chars": 0},
                    ],
                    "response": [
                        {"path": "data.sunrise", "label": "Sunrise", "max_chars": 0},
                        {"path": "data.summary", "label": "Summary", "max_chars": 5},
                    ],
                }
            },
        }
    )

    request_payload = {"lat": "1.23456", "lng": "2.34567"}
    response_payload = {"data": {"sunrise": "05:45", "summary": "clear sky"}}

    request_preview, request_excerpt, response_preview, response_excerpt = (
        build_execution_log_previews(
            policy=policy,
            tool_key="sun",
            request_payload=request_payload,
            response_payload=response_payload,
        )
    )

    assert request_preview == "Latitude=1.23456; Longitude=2.34567"
    assert request_excerpt == {"Latitude": "1.23456", "Longitude": "2.34567"}
    assert response_preview == "Sunrise=05:45; Summary=clea…"
    assert response_excerpt == {"Sunrise": "05:45", "Summary": "clea…"}


def test_build_execution_log_previews_without_policy_uses_defaults() -> None:
    long_request = {"query": "x" * 80}
    long_response = {"result": "y" * 150}

    request_preview, request_excerpt, response_preview, response_excerpt = (
        build_execution_log_previews(
            policy=None,
            tool_key="any",
            request_payload=long_request,
            response_payload=long_response,
        )
    )

    assert len(request_preview) <= 50
    assert request_preview.endswith("…")
    assert request_excerpt is None

    assert len(response_preview) <= 100
    assert response_preview.endswith("…")
    assert response_excerpt is None


def test_build_execution_log_previews_missing_paths_fall_back() -> None:
    policy = ExecutionLogPolicy.model_validate(
        {
            "tools": {
                "tool": {
                    "request": [{"path": "missing", "label": "Missing"}],
                    "response": [
                        {"path": "data.value", "label": "Value", "max_chars": 0}
                    ],
                }
            }
        }
    )
    request_payload = {"present": 1}
    response_payload = {"other": "ignored", "data": {"value": "captured"}}

    request_preview, request_excerpt, response_preview, response_excerpt = (
        build_execution_log_previews(
            policy=policy,
            tool_key="tool",
            request_payload=request_payload,
            response_payload=response_payload,
        )
    )

    assert "Missing" not in request_preview
    assert request_excerpt is None
    assert response_preview == "Value=captured"
    assert response_excerpt == {"Value": "captured"}


def test_execution_log_policy_rejects_blank_tool_keys() -> None:
    with pytest.raises(ValidationError):
        ExecutionLogPolicy.model_validate({"tools": {" ": {}}})
