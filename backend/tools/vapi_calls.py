"""Vapi integration for outbound voice calls to restaurants, caterers, and chefs."""

import os
import re
import uuid
from typing import Optional
from langchain_core.tools import tool
import httpx

VAPI_API_URL = "https://api.vapi.ai"


def get_vapi_headers():
    """Get headers for Vapi API requests."""
    return {
        "Authorization": f"Bearer {os.getenv('VAPI_API_KEY')}",
        "Content-Type": "application/json",
    }


def normalize_phone(number: str) -> str:
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX for US)."""
    digits = re.sub(r'\D', '', number)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if number.startswith("+"):
        return number
    return f"+{digits}"


# Edesia voice assistant configuration for outbound calls
EDESIA_ASSISTANT_CONFIG = {
    "name": "Edesia Outbound Caller",
    "model": {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "temperature": 0.4,
        "messages": [
            {
                "role": "system",
                "content": """You are Edesia, an AI assistant placing calls on behalf of a company. Be direct and efficient.

RULES:
- State your purpose in the FIRST sentence. No small talk.
- NEVER recap what they just said back to them. Move forward.
- Ask only what you need. One question at a time.
- When you have all the info you need, confirm the key details ONCE, say thanks, and end the call.
- Keep responses under 2 sentences.
- If they put you on hold, wait silently.
- If they can't help, ask who can and end the call.

PICKUP ORDERS: State items → get total → get wait time → give name for order → done.
RESERVATIONS: State date/time/party size → get confirmation → done.
CATERING: State event details → get availability + pricing → done.
CHEF INQUIRY: State event details → get availability + pricing → done."""
            }
        ]
    },
    "voice": {
        "provider": "vapi",
        "voiceId": "Savannah"
    },
    "firstMessage": "Hi, this is Edesia calling on behalf of {{companyName}} regarding {{purpose}}.",
    "endCallMessage": "Thanks, bye!",
    "transcriber": {
        "provider": "deepgram",
        "model": "nova-2",
        "language": "en"
    },
    "silenceTimeoutSeconds": 20,
    "maxDurationSeconds": 300,  # 5 minute max — should be done well before this
    "backgroundSound": "office",
    "analysisPlan": {
        "summaryPrompt": "Extract: 1) Order/reservation confirmed? (yes/no) 2) Items ordered 3) Total cost 4) Pickup/ready time 5) Confirmation number if given 6) Any issues"
    }
}


@tool
async def call_restaurant(
    restaurant_name: str,
    phone_number: str,
    company_name: str,
    purpose: str = "inquiry",
    order_items: Optional[str] = None,
    pickup_time: Optional[str] = None,
    date: Optional[str] = None,
    time: Optional[str] = None,
    party_size: Optional[int] = None,
    special_requests: Optional[str] = None,
) -> dict:
    """
    Make an outbound call to a restaurant for pickup orders, reservations, or general inquiries.
    REQUIRES APPROVAL — the call will not be placed until the user approves.

    Args:
        restaurant_name: Name of the restaurant to call
        phone_number: Phone number to call (e.g., 555-123-4567 or +15551234567)
        company_name: Company name placing the order or reservation
        purpose: One of "pickup_order", "reservation", or "inquiry"
        order_items: For pickup orders — items to order (e.g., "2x Vegan Burger, 1x Sweet Potato Fries")
        pickup_time: For pickup orders — desired pickup time (e.g., "12:30 PM")
        date: For reservations — desired date (e.g., "Friday, March 15th")
        time: For reservations — desired time (e.g., "7:00 PM")
        party_size: For reservations — number of guests
        special_requests: Any special requests (dietary, private room, etc.)

    Returns:
        Pending action requiring user approval before the call is placed
    """
    action_id = str(uuid.uuid4())
    normalized = normalize_phone(phone_number)

    if purpose == "pickup_order":
        description = f"Call {restaurant_name} at {normalized} to place a pickup order: {order_items or 'items TBD'}"
        if pickup_time:
            description += f" (pickup around {pickup_time})"
    elif purpose == "reservation":
        description = f"Call {restaurant_name} at {normalized} to inquire about a reservation for {party_size or '?'} people on {date or 'TBD'} at {time or 'TBD'}"
    else:
        description = f"Call {restaurant_name} at {normalized} for a general inquiry"

    return {
        "action_id": action_id,
        "action_type": "call_restaurant",
        "description": description,
        "payload": {
            "restaurant_name": restaurant_name,
            "phone_number": normalized,
            "company_name": company_name,
            "purpose": purpose,
            "order_items": order_items,
            "pickup_time": pickup_time,
            "date": date,
            "time": time,
            "party_size": party_size,
            "special_requests": special_requests,
        },
        "status": "pending",
    }


@tool
async def call_caterer(
    caterer_name: str,
    phone_number: str,
    company_name: str,
    event_type: str,
    event_date: str,
    guest_count: int,
    budget_per_person: Optional[float] = None,
    dietary_requirements: Optional[str] = None,
    location: Optional[str] = None,
) -> dict:
    """
    Make an outbound call to a caterer for event catering inquiry.
    REQUIRES APPROVAL — the call will not be placed until the user approves.

    Args:
        caterer_name: Name of the catering company
        phone_number: Phone number to call (e.g., 555-123-4567 or +15551234567)
        company_name: Company name requesting catering
        event_type: Type of event (lunch meeting, corporate dinner, team celebration, etc.)
        event_date: Date of the event
        guest_count: Expected number of guests
        budget_per_person: Optional budget per person
        dietary_requirements: Any dietary requirements (vegetarian options, allergies, etc.)
        location: Event location for delivery

    Returns:
        Pending action requiring user approval before the call is placed
    """
    action_id = str(uuid.uuid4())
    normalized = normalize_phone(phone_number)

    return {
        "action_id": action_id,
        "action_type": "call_caterer",
        "description": f"Call {caterer_name} at {normalized} to inquire about catering for {guest_count} guests on {event_date}",
        "payload": {
            "caterer_name": caterer_name,
            "phone_number": normalized,
            "company_name": company_name,
            "event_type": event_type,
            "event_date": event_date,
            "guest_count": guest_count,
            "budget_per_person": budget_per_person,
            "dietary_requirements": dietary_requirements,
            "location": location,
        },
        "status": "pending",
    }


@tool
async def call_chef(
    chef_name: str,
    phone_number: str,
    company_name: str,
    event_type: str,
    event_date: str,
    guest_count: int,
    cuisine_preference: Optional[str] = None,
    budget: Optional[float] = None,
    event_location: Optional[str] = None,
) -> dict:
    """
    Make an outbound call to a private chef for event inquiry.
    REQUIRES APPROVAL — the call will not be placed until the user approves.

    Args:
        chef_name: Name of the chef or culinary service
        phone_number: Phone number to call (e.g., 555-123-4567 or +15551234567)
        company_name: Company name requesting the chef
        event_type: Type of event (executive dinner, team building, cooking class, etc.)
        event_date: Date of the event
        guest_count: Expected number of guests
        cuisine_preference: Preferred cuisine type (Italian, Japanese, etc.)
        budget: Total budget for the chef services
        event_location: Where the event will be held

    Returns:
        Pending action requiring user approval before the call is placed
    """
    action_id = str(uuid.uuid4())
    normalized = normalize_phone(phone_number)

    return {
        "action_id": action_id,
        "action_type": "call_chef",
        "description": f"Call {chef_name} at {normalized} to inquire about a private chef for {guest_count} guests on {event_date}",
        "payload": {
            "chef_name": chef_name,
            "phone_number": normalized,
            "company_name": company_name,
            "event_type": event_type,
            "event_date": event_date,
            "guest_count": guest_count,
            "cuisine_preference": cuisine_preference,
            "budget": budget,
            "event_location": event_location,
        },
        "status": "pending",
    }


@tool
async def get_call_status(call_id: str) -> dict:
    """
    Get the status and details of an outbound call.

    Args:
        call_id: The Vapi call ID to check

    Returns:
        Call status, transcript, and summary if available
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{VAPI_API_URL}/call/{call_id}",
            headers=get_vapi_headers(),
            timeout=30.0
        )

        if response.status_code == 200:
            call_data = response.json()
            return {
                "success": True,
                "call_id": call_id,
                "status": call_data.get("status"),
                "duration": call_data.get("duration"),
                "started_at": call_data.get("startedAt"),
                "ended_at": call_data.get("endedAt"),
                "end_reason": call_data.get("endedReason"),
                "transcript": call_data.get("transcript"),
                "summary": call_data.get("analysis", {}).get("summary"),
                "recording_url": call_data.get("recordingUrl"),
                "metadata": call_data.get("metadata")
            }
        else:
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }


async def execute_vapi_call(
    action_type: str,
    payload: dict,
    chat_id: Optional[str] = None,
    order_id: Optional[str] = None,
) -> dict:
    """Execute an approved Vapi call. Called from main.py after user approves."""
    import copy

    phone_number = payload.get("phone_number", "")
    company_name = payload.get("company_name", "Unknown")

    # Build purpose string based on action type
    if action_type == "call_restaurant":
        name = payload.get("restaurant_name", "the restaurant")
        call_purpose = payload.get("purpose", "inquiry")

        if call_purpose == "pickup_order":
            order_items = payload.get("order_items", "items to be confirmed")
            pickup_time = payload.get("pickup_time", "as soon as possible")
            purpose = f"placing a pickup order: {order_items}"
            special = payload.get('special_requests')
            context = f"""
ORDER: {order_items}
PICKUP TIME: {pickup_time}
NAME FOR ORDER: {company_name}
{f'SPECIAL REQUESTS: {special}' if special else ''}

DO: State items → get total → get wait time → give name "{company_name}" → end call."""

        elif call_purpose == "reservation":
            purpose = f"a reservation for {payload.get('party_size', '')} on {payload.get('date', '')} at {payload.get('time', '')}"
            special = payload.get('special_requests')
            context = f"""
RESERVATION: {payload.get('party_size', '')} people, {payload.get('date', '')}, {payload.get('time', '')}
NAME: {company_name}
{f'SPECIAL REQUESTS: {special}' if special else ''}

DO: Request reservation → get confirmation number → end call."""

        else:
            purpose = "a general inquiry"
            special = payload.get('special_requests')
            context = f"""
{f'QUESTION: {special}' if special else 'Ask your question.'}

DO: Get the info → end call."""

    elif action_type == "call_caterer":
        name = payload.get("caterer_name", "the caterer")
        purpose = f"catering for {payload.get('guest_count', '')} guests on {payload.get('event_date', '')}"
        budget_str = f"${payload['budget_per_person']}/person" if payload.get('budget_per_person') else ""
        context = f"""
EVENT: {payload.get('event_type', '')}, {payload.get('event_date', '')}, {payload.get('guest_count', '')} guests
COMPANY: {company_name}
{f'BUDGET: {budget_str}' if budget_str else ''}
{f'DIETARY: {payload.get("dietary_requirements")}' if payload.get('dietary_requirements') else ''}
{f'LOCATION: {payload.get("location")}' if payload.get('location') else ''}

DO: State event details → get availability + pricing per person → end call."""

    elif action_type == "call_chef":
        name = payload.get("chef_name", "the chef")
        purpose = f"a private chef for {payload.get('guest_count', '')} guests on {payload.get('event_date', '')}"
        budget_str = f"${payload['budget']}" if payload.get('budget') else ""
        context = f"""
EVENT: {payload.get('event_type', '')}, {payload.get('event_date', '')}, {payload.get('guest_count', '')} guests
COMPANY: {company_name}
{f'CUISINE: {payload.get("cuisine_preference")}' if payload.get('cuisine_preference') else ''}
{f'BUDGET: {budget_str}' if budget_str else ''}
{f'LOCATION: {payload.get("event_location")}' if payload.get('event_location') else ''}

DO: Check availability → get pricing → end call."""
    else:
        return {"success": False, "error": f"Unknown call action type: {action_type}"}

    # Build assistant config
    assistant_config = copy.deepcopy(EDESIA_ASSISTANT_CONFIG)
    assistant_config["firstMessage"] = assistant_config["firstMessage"].replace(
        "{{companyName}}", company_name
    ).replace("{{purpose}}", purpose)
    assistant_config["model"]["messages"][0]["content"] += context

    vapi_payload = {
        "phoneNumberId": os.getenv("VAPI_PHONE_NUMBER_ID"),
        "assistant": assistant_config,
        "customer": {
            "number": phone_number,
            "name": name,
        },
        "metadata": {
            "call_type": action_type,
            "company_name": company_name,
            **({"chat_id": chat_id} if chat_id else {}),
            **({"order_id": order_id} if order_id else {}),
        },
    }

    # Log for debugging
    has_key = bool(os.getenv("VAPI_API_KEY"))
    print(f"[VAPI] Initiating call to {name} at {phone_number}")
    print(f"[VAPI] API key present: {has_key}, key prefix: {os.getenv('VAPI_API_KEY', '')[:8]}...")
    print(f"[VAPI] Payload customer: {vapi_payload.get('customer')}")
    print(f"[VAPI] Payload metadata: {vapi_payload.get('metadata')}")
    print(f"[VAPI] Model: {assistant_config.get('model', {}).get('model')}")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{VAPI_API_URL}/call",
            headers=get_vapi_headers(),
            json=vapi_payload,
            timeout=30.0,
        )

        print(f"[VAPI] Response status: {response.status_code}")
        print(f"[VAPI] Response body: {response.text[:500]}")

        if response.status_code == 201:
            call_data = response.json()
            print(f"[VAPI] Call created: id={call_data.get('id')}")
            return {
                "success": True,
                "call_id": call_data.get("id"),
                "status": "initiated",
                "message": f"Call initiated to {name} at {phone_number}",
            }
        else:
            print(f"[VAPI] CALL FAILED: {response.status_code} — {response.text[:500]}")
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code,
                "message": f"Failed to initiate call to {name}",
            }


vapi_tools = [
    call_restaurant,
    call_caterer,
    call_chef,
    get_call_status,
]
