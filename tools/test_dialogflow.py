#!/usr/bin/env python3
"""Test script for DialogFlow CX tool."""

import os
import sys
import json
from typing import Any, Dict

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from arion_agents.tools.dialogflow import DialogFlowCXTool
from arion_agents.tools.base import ToolConfig, ToolRunInput
from google.oauth2 import service_account
from google.cloud import dialogflowcx_v3

def main():
    """Run a test of the DialogFlowCXTool."""
    with open(".secrets/dialogflow_service_account.json") as f:
        service_account_info = json.load(f)
    
    credentials = service_account.Credentials.from_service_account_info(service_account_info)

    tool_config = ToolConfig(
        id=1,
        key="dialogflow_cx_tester",
        display_name="DialogFlow CX Tester",
        description="Sends utterances to the DialogFlow CX bot under test.",
        provider_type="dialogflow:cx",
        params_schema={},
        secret_ref="dialogflow_service_account.json",
        metadata={},
    )

    tool = DialogFlowCXTool(tool_config, json.dumps(service_account_info))

    system_params = {
        "dialogflow_project_id": "satacs-be-prd",
        "dialogflow_location": "global",
        "dialogflow_agent_id": "fde810bf-b9fb-4924-85be-2aab8b4896e1",
        "dialogflow_language_code": "en",
        "dialogflow_environment": "draft", # This is the parameter causing the issue
    }

    agent_params = {"query": "Am I allowed to have multiple accounts?"}

    tool_input = ToolRunInput(
        params=agent_params,
        system=system_params,
        metadata={},
    )

    result = tool.run(tool_input)

    print(json.dumps(result.dict(), indent=2))


if __name__ == "__main__":
    main()