"""VAPI inbound assistant configuration.

Defines the assistant config dict that gets POSTed to the VAPI API when
registering the inbound assistant. The LLM (Groq) handles the conversation;
our backend only exposes stateless tool endpoints.
"""

INBOUND_SYSTEM_PROMPT = """\
You are Edesia, a friendly AI food-planning assistant on a phone call.

RULES:
- Keep every response under 3 sentences. Callers are listening, not reading.
- Present at most 3 options at a time. Say "I have more if you'd like."
- Collect the caller's name and email early using the collect_caller_info tool. You need these to place reservations or look up orders.
- When listing restaurants or caterers, say name, cuisine, rating, and price only.
- Never read URLs, IDs, or technical details aloud.
- Confirm key details before taking action (reservation, quote, etc.).
- If unsure, ask a clarifying question rather than guessing.
- Be warm but efficient — respect the caller's time.

CAPABILITIES:
1. Search restaurants by location and cuisine
2. Search catering services
3. Get restaurant details (hours, menu, reviews)
4. Get catering menus and packages
5. Make restaurant reservations
6. Request catering quotes
7. Check status of previous orders by email
"""

# Server URL placeholder — replaced at registration time by build_inbound_config()
_SERVER_URL_PLACEHOLDER = "{{SERVER_URL}}"

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_restaurants",
            "description": "Search for restaurants by location and optional cuisine or price filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City, address, or neighborhood (e.g. 'Nashville, TN')",
                    },
                    "term": {
                        "type": "string",
                        "description": "Search term like 'pizza' or 'sushi'",
                    },
                    "cuisine": {
                        "type": "string",
                        "description": "Cuisine filter (e.g. 'mexican', 'italian')",
                    },
                    "price": {
                        "type": "string",
                        "description": "Price range: '1' ($), '2' ($$), '3' ($$$), '4' ($$$$)",
                    },
                },
                "required": ["location"],
            },
        },
        "server": {"url": _SERVER_URL_PLACEHOLDER},
    },
    {
        "type": "function",
        "function": {
            "name": "search_caterers",
            "description": "Search for catering services by location, headcount, and cuisine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City or address for delivery",
                    },
                    "headcount": {
                        "type": "integer",
                        "description": "Number of people to feed",
                    },
                    "cuisine": {
                        "type": "string",
                        "description": "Cuisine preference",
                    },
                    "max_price_per_person": {
                        "type": "number",
                        "description": "Maximum budget per person in dollars",
                    },
                },
                "required": ["location"],
            },
        },
        "server": {"url": _SERVER_URL_PLACEHOLDER},
    },
    {
        "type": "function",
        "function": {
            "name": "get_restaurant_details",
            "description": "Get full details for a restaurant including hours, phone, reviews, and service options.",
            "parameters": {
                "type": "object",
                "properties": {
                    "place_id": {
                        "type": "string",
                        "description": "The Google Place ID from search results",
                    },
                },
                "required": ["place_id"],
            },
        },
        "server": {"url": _SERVER_URL_PLACEHOLDER},
    },
    {
        "type": "function",
        "function": {
            "name": "get_catering_menu",
            "description": "Get a caterer's menu with packages and individual items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caterer_id": {
                        "type": "string",
                        "description": "The caterer's unique identifier from search results",
                    },
                },
                "required": ["caterer_id"],
            },
        },
        "server": {"url": _SERVER_URL_PLACEHOLDER},
    },
    {
        "type": "function",
        "function": {
            "name": "make_reservation",
            "description": "Book a restaurant reservation. Requires party size, date, time, and contact info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {
                        "type": "string",
                        "description": "Restaurant identifier from search results",
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests",
                    },
                    "date": {
                        "type": "string",
                        "description": "Reservation date (YYYY-MM-DD)",
                    },
                    "time": {
                        "type": "string",
                        "description": "Reservation time (e.g. '7:00 PM')",
                    },
                    "contact_name": {
                        "type": "string",
                        "description": "Name for the reservation",
                    },
                    "contact_email": {
                        "type": "string",
                        "description": "Email for confirmation",
                    },
                    "contact_phone": {
                        "type": "string",
                        "description": "Phone number for confirmation",
                    },
                    "special_requests": {
                        "type": "string",
                        "description": "Any special requests (dietary, seating, etc.)",
                    },
                },
                "required": ["restaurant_id", "party_size", "date", "time", "contact_name", "contact_email"],
            },
        },
        "server": {"url": _SERVER_URL_PLACEHOLDER},
    },
    {
        "type": "function",
        "function": {
            "name": "request_catering_quote",
            "description": "Request a catering quote with pricing breakdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caterer_id": {
                        "type": "string",
                        "description": "The caterer's identifier",
                    },
                    "headcount": {
                        "type": "integer",
                        "description": "Number of people to feed",
                    },
                    "package_name": {
                        "type": "string",
                        "description": "Name of a catering package",
                    },
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Individual menu items if not using a package",
                    },
                    "delivery_date": {
                        "type": "string",
                        "description": "Delivery date (YYYY-MM-DD)",
                    },
                    "delivery_time": {
                        "type": "string",
                        "description": "Delivery time",
                    },
                    "delivery_address": {
                        "type": "string",
                        "description": "Delivery address",
                    },
                    "dietary_notes": {
                        "type": "string",
                        "description": "Dietary restrictions or notes",
                    },
                },
                "required": ["caterer_id", "headcount"],
            },
        },
        "server": {"url": _SERVER_URL_PLACEHOLDER},
    },
    {
        "type": "function",
        "function": {
            "name": "check_order_status",
            "description": "Look up existing orders or previous calls by the caller's email address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "The caller's email address",
                    },
                },
                "required": ["email"],
            },
        },
        "server": {"url": _SERVER_URL_PLACEHOLDER},
    },
    {
        "type": "function",
        "function": {
            "name": "collect_caller_info",
            "description": "Save the caller's name and email. Call this early in the conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Caller's full name",
                    },
                    "email": {
                        "type": "string",
                        "description": "Caller's email address",
                    },
                },
                "required": ["name"],
            },
        },
        "server": {"url": _SERVER_URL_PLACEHOLDER},
    },
]

INBOUND_ASSISTANT_CONFIG = {
    "name": "Edesia Inbound Assistant",
    "model": {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "temperature": 0.4,
        "tools": TOOL_DEFINITIONS,
        "messages": [
            {
                "role": "system",
                "content": INBOUND_SYSTEM_PROMPT,
            }
        ],
    },
    "voice": {
        "provider": "vapi",
        "voiceId": "Savannah",
    },
    "firstMessage": "Hey, this is Edesia. How can I help you today?",
    "transcriber": {
        "provider": "deepgram",
        "model": "nova-2",
        "language": "en",
    },
    "silenceTimeoutSeconds": 20,
    "maxDurationSeconds": 600,  # 10 min for inbound calls
    "backgroundSound": "office",
    "analysisPlan": {
        "summaryPrompt": (
            "Summarize: 1) Caller's intent (reservation, catering, inquiry, order_status) "
            "2) Actions taken 3) Key details (restaurant/caterer, date, headcount, etc.) "
            "4) Whether follow-up is needed"
        ),
        "structuredDataPrompt": (
            "Extract as JSON: {\"callerName\": \"\", \"callerEmail\": \"\", "
            "\"intent\": \"reservation|catering|inquiry|order_status\", "
            "\"actionsPerformed\": [{\"type\": \"\", \"details\": \"\"}], "
            "\"eventDetails\": {\"type\": \"\", \"date\": \"\", \"guestCount\": 0, "
            "\"budget\": \"\", \"location\": \"\", \"dietaryNeeds\": \"\"}, "
            "\"followUpNeeded\": false}"
        ),
    },
}


def build_inbound_config(server_url: str) -> dict:
    """Return a copy of INBOUND_ASSISTANT_CONFIG with server URLs filled in.

    Args:
        server_url: The base URL for tool-call webhooks,
                    e.g. "https://edesia-agent--fastapi-app.modal.run/webhooks/vapi/tool-calls"
    """
    import copy
    config = copy.deepcopy(INBOUND_ASSISTANT_CONFIG)

    for tool_def in config["model"]["tools"]:
        if "server" in tool_def:
            tool_def["server"]["url"] = server_url

    return config
