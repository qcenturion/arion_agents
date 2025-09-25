#!/usr/bin/env python3
"""Single-file test script for DialogFlow CX API."""

import json
import uuid
from google.cloud import dialogflowcx_v3
from google.oauth2 import service_account
from google.protobuf.json_format import MessageToDict

def run_dialogflow_test():
    """Initializes a client and sends a test query to DialogFlow CX."""
    try:
        # 1. Load Credentials
        with open(".secrets/dialogflow_service_account.json") as f:
            service_account_info = json.load(f)
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        print("Successfully loaded credentials.")

        # 2. Define Parameters
        project_id = "satacs-be-prd"
        location = "global"
        agent_id = "fde810bf-b9fb-4924-85be-2aab8b4896e1"
        environment = "draft"
        language_code = "en"
        session_id = uuid.uuid4().hex
        print(f"Using Session ID: {session_id}")

        # 3. Create Client and Session Path
        client_options = {"api_endpoint": f"{location}-dialogflow.googleapis.com"}
        client = dialogflowcx_v3.SessionsClient(credentials=credentials, client_options=client_options)

        session_path = (
            f"projects/{project_id}/locations/{location}/agents/{agent_id}/"
            f"environments/{environment}/sessions/{session_id}"
        )
        print(f"Constructed Session Path: {session_path}")

        # 4. Define Session Parameters
        session_params = {
            "customer_verified": "true",
            "username": "CSTESTINR",
        }
        query_params = dialogflowcx_v3.QueryParameters(parameters=session_params)
        print(f"Using Session Parameters: {session_params}")

        # 5. Send Initial "ewc" Message
        ewc_query = "ewc"
        request = dialogflowcx_v3.DetectIntentRequest(
            session=session_path,
            query_input=dialogflowcx_v3.QueryInput(
                text=dialogflowcx_v3.TextInput(text=ewc_query),
                language_code=language_code,
            ),
            query_params=query_params,
        )
        print(f"\nSending initial message: '{ewc_query}'...")
        response = client.detect_intent(request=request)
        print("Initial message sent successfully.")
        response_dict = MessageToDict(response._pb, preserving_proto_field_name=True)
        print("\n--- Response to 'ewc' ---")
        print(json.dumps(response_dict, indent=2))
        print("--------------------------")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_dialogflow_test()
