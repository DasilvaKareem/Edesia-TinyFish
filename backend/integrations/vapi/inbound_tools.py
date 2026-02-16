"""Inbound VAPI tool handlers.

Each handler wraps an existing LangChain tool, trims the result for voice,
and returns a JSON string that VAPI feeds back to the assistant LLM.
"""

import asyncio
import json
from typing import Callable, Awaitable


# ---------------------------------------------------------------------------
# Voice-output helpers
# ---------------------------------------------------------------------------

# Fields that are useless over voice (image URLs, map links, etc.)
_STRIP_KEYS = {
    "image_url", "url", "photos", "google_maps_url", "photo_reference",
    "location", "geometry", "place_id", "id",
}


def _trim_for_voice(obj, max_items: int = 5):
    """Strip visual-only fields and cap list lengths for voice delivery."""
    if isinstance(obj, dict):
        return {
            k: _trim_for_voice(v, max_items)
            for k, v in obj.items()
            if k not in _STRIP_KEYS
        }
    if isinstance(obj, list):
        return [_trim_for_voice(item, max_items) for item in obj[:max_items]]
    return obj


async def _invoke_tool(tool_fn, params: dict) -> str:
    """Invoke a LangChain @tool (sync or async) and return trimmed JSON."""
    if asyncio.iscoroutinefunction(tool_fn.func if hasattr(tool_fn, "func") else tool_fn):
        result = await tool_fn.ainvoke(params)
    else:
        result = await asyncio.to_thread(tool_fn.invoke, params)
    trimmed = _trim_for_voice(result)
    return json.dumps(trimmed, default=str)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_search_restaurants(params: dict, **_kw) -> str:
    from tools.yelp_search import yelp_search_restaurants
    return await _invoke_tool(yelp_search_restaurants, {
        "location": params.get("location", ""),
        "term": params.get("term"),
        "cuisine": params.get("cuisine"),
        "price": params.get("price"),
        "limit": params.get("limit", 5),
    })


async def handle_search_caterers(params: dict, **_kw) -> str:
    from tools.catering import search_caterers
    return await _invoke_tool(search_caterers, {
        "location": params.get("location", ""),
        "headcount": params.get("headcount"),
        "cuisine": params.get("cuisine"),
        "max_price_per_person": params.get("max_price_per_person"),
    })


async def handle_get_restaurant_details(params: dict, **_kw) -> str:
    from tools.google_places import get_place_details
    return await _invoke_tool(get_place_details, {
        "place_id": params.get("place_id", ""),
    })


async def handle_get_catering_menu(params: dict, **_kw) -> str:
    from tools.catering import get_catering_menu
    return await _invoke_tool(get_catering_menu, {
        "caterer_id": params.get("caterer_id", ""),
    })


async def handle_make_reservation(params: dict, **_kw) -> str:
    from tools.opentable import make_reservation
    return await _invoke_tool(make_reservation, {
        "restaurant_id": params.get("restaurant_id", ""),
        "party_size": params.get("party_size", 2),
        "date": params.get("date", ""),
        "time": params.get("time", ""),
        "contact_name": params.get("contact_name", ""),
        "contact_email": params.get("contact_email", ""),
        "contact_phone": params.get("contact_phone"),
        "special_requests": params.get("special_requests"),
    })


async def handle_request_catering_quote(params: dict, **_kw) -> str:
    from tools.catering import request_catering_quote
    return await _invoke_tool(request_catering_quote, {
        "caterer_id": params.get("caterer_id", ""),
        "headcount": params.get("headcount", 10),
        "package_name": params.get("package_name"),
        "items": params.get("items"),
        "delivery_date": params.get("delivery_date"),
        "delivery_time": params.get("delivery_time"),
        "delivery_address": params.get("delivery_address"),
        "dietary_notes": params.get("dietary_notes"),
    })


async def handle_check_order_status(params: dict, **_kw) -> str:
    """Look up existing inbound call records by caller email."""
    from lib.firebase import find_inbound_calls_by_email

    email = params.get("email", "")
    if not email:
        return json.dumps({"error": "Email is required to look up orders."})

    calls = await find_inbound_calls_by_email(email)
    if not calls:
        return json.dumps({"message": "No previous orders found for that email."})

    # Return a concise summary of recent calls
    summaries = []
    for c in calls[:5]:
        summaries.append({
            "date": c.get("createdAt"),
            "intent": c.get("intent", "unknown"),
            "summary": c.get("summary", ""),
            "status": c.get("status", "unknown"),
        })
    return json.dumps(_trim_for_voice(summaries), default=str)


async def handle_collect_caller_info(params: dict, call_id: str = "", calls_dict=None, **_kw) -> str:
    """Save caller name and email to the in-memory call record."""
    name = params.get("name", "")
    email = params.get("email", "")

    if calls_dict is not None and call_id:
        call_data = calls_dict.get(call_id, {})
        if name:
            call_data["caller_name"] = name
        if email:
            call_data["caller_email"] = email
        calls_dict[call_id] = call_data

    return json.dumps({
        "message": "Got it, thanks!",
        "name": name,
        "email": email,
    })


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

INBOUND_TOOL_HANDLERS: dict[str, Callable[..., Awaitable[str]]] = {
    "search_restaurants": handle_search_restaurants,
    "search_caterers": handle_search_caterers,
    "get_restaurant_details": handle_get_restaurant_details,
    "get_catering_menu": handle_get_catering_menu,
    "make_reservation": handle_make_reservation,
    "request_catering_quote": handle_request_catering_quote,
    "check_order_status": handle_check_order_status,
    "collect_caller_info": handle_collect_caller_info,
}
