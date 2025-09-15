import json
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from arion_agents.agent_decision import AgentDecision


def test_sun_scenario_with_mocked_llm(monkeypatch):
    """
    Tests the full agent loop for the "sun" scenario by mocking the LLM responses
    and loading the agent configuration from a static snapshot file, bypassing the database.
    """
    # Use monkeypatch to set environment variables BEFORE the app is imported by TestClient
    monkeypatch.setenv("SNAPSHOT_FILE", "tools/sun_snapshot.json")
    monkeypatch.setenv("OTEL_ENABLED", "false")

    # Now that env vars are set, we can import the app and create the client
    from arion_agents.api import app
    client = TestClient(app)

    # 1. Define the exact LLM responses from the E2E report
    # First call: Triage agent decides to use the 'sun' tool
    llm_response_1_raw = '''```json
{
  "action": "USE_TOOL",
  "action_reasoning": "The user is asking for sunrise and sunset times, which directly maps to the 'sun' tool's functionality. The necessary 'lat' and 'lng' parameters are provided in the user's message.",
  "action_details": {
    "tool_name": "sun",
    "tool_params": {
      "lat": 36.72016,
      "lng": -4.42034
    }
  }
}
```'''
    llm_response_1_parsed = AgentDecision.model_validate_json('''
{
  "action": "USE_TOOL",
  "action_reasoning": "The user is asking for sunrise and sunset times, which directly maps to the 'sun' tool's functionality. The necessary 'lat' and 'lng' parameters are provided in the user's message.",
  "action_details": {
    "tool_name": "sun",
    "tool_params": {
      "lat": 36.72016,
      "lng": -4.42034
    }
  }
}
''')

    # Second call: Triage agent receives tool output and decides to respond
    llm_response_2_raw = '''{
  "action": "RESPOND",
  "action_reasoning": "The 'sun' tool was successfully executed and the output is available. I can now respond to the user with the sunrise and sunset times.",
  "action_details": {
    "payload": "The sunrise is at 5:58:54 AM and the sunset is at 6:26:40 PM."
  }
}'''
    llm_response_2_parsed = AgentDecision.model_validate_json('''
{
  "action": "RESPOND",
  "action_reasoning": "The 'sun' tool was successfully executed and the output is available. I can now respond to the user with the sunrise and sunset times.",
  "action_details": {
    "payload": "The sunrise is at 5:58:54 AM and the sunset is at 6:26:40 PM."
  }
}
''')

    # 2. Patch the `gemini_decide` function
    with patch('arion_agents.llm.gemini_decide', side_effect=[
        (llm_response_1_raw, llm_response_1_parsed),
        (llm_response_2_raw, llm_response_2_parsed),
    ]) as mock_gemini_decide:
        # 3. Run the test
        response = client.post(
            '/run',
            json={
                'network': 'unused',
                'user_message': 'When does the sun rise and set for lat 36.7201600 and lng -4.4203400?',
                'debug': True,
            },
        )

    # 4. Assert the results
    assert response.status_code == 200
    out = response.json()

    # Check that the final message is correct
    assert out['final']['response']['message'] == "The sunrise is at 5:58:54 AM and the sunset is at 6:26:40 PM."
    assert out['final']['status'] == 'ok'

    # Check that the LLM was called exactly twice
    assert mock_gemini_decide.call_count == 2

    # Optional: Check that the tool log contains the correct execution
    tool_log = out.get('tool_log', {})
    assert len(tool_log) == 1, "There should be exactly one tool call in the log"
    tool_execution_id = list(tool_log.keys())[0]
    assert tool_log[tool_execution_id]['tool_key'] == 'sun'
    assert 'sunrise' in tool_log[tool_execution_id]['result']
