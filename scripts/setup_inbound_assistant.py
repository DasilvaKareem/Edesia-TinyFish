#!/usr/bin/env python3
"""Register the Edesia inbound assistant with VAPI and assign it to the phone number.

Required environment variables:
    VAPI_API_KEY          - VAPI bearer token
    VAPI_PHONE_NUMBER_ID  - ID of the VAPI phone number to assign
    EDESIA_SERVER_URL     - Base URL of the deployed backend
                            (e.g. https://edesia-agent--fastapi-app.modal.run)

Usage:
    export VAPI_API_KEY=...
    export VAPI_PHONE_NUMBER_ID=...
    export EDESIA_SERVER_URL=https://edesia-agent--fastapi-app.modal.run
    python scripts/setup_inbound_assistant.py
"""

import os
import sys
import json
import httpx

# Allow importing from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from integrations.vapi.assistant_config import build_inbound_config

VAPI_API_URL = "https://api.vapi.ai"


def main():
    api_key = os.environ.get("VAPI_API_KEY")
    phone_number_id = os.environ.get("VAPI_PHONE_NUMBER_ID")
    server_url = os.environ.get("EDESIA_SERVER_URL")

    if not api_key:
        sys.exit("Error: VAPI_API_KEY not set")
    if not phone_number_id:
        sys.exit("Error: VAPI_PHONE_NUMBER_ID not set")
    if not server_url:
        sys.exit("Error: EDESIA_SERVER_URL not set")

    tool_calls_url = f"{server_url.rstrip('/')}/webhooks/vapi/tool-calls"
    config = build_inbound_config(tool_calls_url)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Step 1: Create the assistant
    print(f"Creating inbound assistant (tools pointing to {tool_calls_url})...")
    resp = httpx.post(
        f"{VAPI_API_URL}/assistant",
        headers=headers,
        json=config,
        timeout=30.0,
    )

    if resp.status_code not in (200, 201):
        print(f"Failed to create assistant: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    assistant = resp.json()
    assistant_id = assistant["id"]
    print(f"Assistant created: {assistant_id}")

    # Step 2: Assign assistant to phone number for inbound calls
    print(f"Assigning assistant {assistant_id} to phone number {phone_number_id}...")
    resp = httpx.patch(
        f"{VAPI_API_URL}/phone-number/{phone_number_id}",
        headers=headers,
        json={"assistantId": assistant_id},
        timeout=30.0,
    )

    if resp.status_code not in (200, 201):
        print(f"Failed to assign assistant to phone number: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    print(f"Phone number {phone_number_id} now routes inbound calls to assistant {assistant_id}")
    print()
    print("Add this to your Modal secrets (vapi-secret):")
    print(f"  VAPI_INBOUND_ASSISTANT_ID={assistant_id}")


if __name__ == "__main__":
    main()
