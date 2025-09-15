from arion_agents.agent_decision import AgentDecision


def test_agent_decision_schema_does_not_contain_additional_properties():
    """
    Verify that the generated JSON schema for AgentDecision does not contain
    the 'additionalProperties' field, which is not supported by the Gemini API.
    """
    schema = AgentDecision.model_json_schema()

    # Check the top-level object
    assert "additionalProperties" not in schema, "Top-level schema should not have additionalProperties"

    # Check all sub-models defined in $defs
    if "$defs" in schema:
        for model_name, model_schema in schema["$defs"].items():
            assert "additionalProperties" not in model_schema, f"Sub-model {model_name} should not have additionalProperties"
