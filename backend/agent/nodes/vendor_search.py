"""Vendor search node for parallel Yelp + Google Places search."""

import asyncio
from datetime import datetime
import weave
from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from agent.state import AgentState
from models.orders import VendorOption, FoodOrderContext
from tools.yelp_search import yelp_search_restaurants, yelp_search_caterers
from tools.google_places import search_places


def _normalize_yelp_vendor(biz: dict) -> VendorOption:
    """Convert Yelp business to VendorOption."""
    return VendorOption(
        vendor_id=biz.get("id", ""),
        name=biz.get("name", "Unknown"),
        rating=biz.get("rating"),
        price_level=biz.get("price", "$$"),
        address=biz.get("address", ""),
        phone=biz.get("display_phone") or biz.get("phone"),
        categories=[c for c in biz.get("categories", [])],
        source="yelp",
        distance=biz.get("distance_meters", 0) / 1609.34 if biz.get("distance_meters") else None,
    )


def _normalize_google_vendor(place: dict) -> VendorOption:
    """Convert Google Place to VendorOption."""
    return VendorOption(
        vendor_id=place.get("place_id", ""),
        name=place.get("name", "Unknown"),
        rating=place.get("rating"),
        price_level=place.get("price_level", "$$"),
        address=place.get("address", ""),
        phone=None,  # Google Places search doesn't return phone
        categories=place.get("types", [])[:3],
        source="google",
        distance=None,
    )


def _format_vendor_options(vendors: list[VendorOption]) -> str:
    """Format vendor options for display."""
    if not vendors:
        return "No vendors found matching your criteria."

    lines = []
    for i, v in enumerate(vendors, 1):
        rating_str = f"{v.rating}/5" if v.rating else "No rating"
        price_str = v.price_level if v.price_level else "$$"
        categories_str = ", ".join(v.categories[:2]) if v.categories else "Restaurant"

        lines.append(f"{i}. **{v.name}** - {rating_str} stars, {price_str}")
        lines.append(f"   {categories_str}")
        lines.append(f"   {v.address}")
        lines.append("")

    return "\n".join(lines)


@weave.op()
async def vendor_search_node(state: AgentState) -> dict:
    """
    Search for food vendors using Yelp and Google Places in parallel.

    Automatically applies user's stored food preferences (dietary restrictions,
    favorite cuisines, etc.) to the search.

    Streams progress updates via get_stream_writer() for real-time UI feedback.

    Returns updated state with vendor_options populated.
    """
    # Get stream writer for status updates
    try:
        writer = get_stream_writer()
    except Exception:
        writer = None

    def emit_status(status: str, details: dict = None):
        if writer:
            writer({"type": "status", "status": status, **(details or {})})

    emit_status("vendor_search_start", {"message": "Starting restaurant search..."})

    food_order = state.get("food_order")
    user_preferences = state.get("user_preferences")

    if not food_order:
        # Initialize food order context if not present
        food_order = FoodOrderContext()
    elif isinstance(food_order, dict):
        food_order = FoodOrderContext(**food_order)

    # Apply user's stored preferences to the food order if not already set
    if user_preferences:
        # Apply dietary restrictions from long-term memory
        if user_preferences.get("dietary_restrictions") and not food_order.dietary_restrictions:
            food_order.dietary_restrictions = user_preferences["dietary_restrictions"]

        # Apply favorite cuisines as search preference
        if user_preferences.get("favorite_cuisines") and not food_order.cuisine_preferences:
            food_order.cuisine_preferences = user_preferences["favorite_cuisines"]

        # Apply budget preference
        if user_preferences.get("default_budget_per_person") and not food_order.budget_per_person:
            food_order.budget_per_person = user_preferences["default_budget_per_person"]

    # Get search parameters
    location = food_order.delivery_address or ""
    cuisine_prefs = food_order.cuisine_preferences or []
    dietary = food_order.dietary_restrictions or []
    headcount = food_order.headcount or 10

    if not location:
        # Try to get from event_details
        event_details = state.get("event_details")
        if event_details:
            location = event_details.get("location", "") if isinstance(event_details, dict) else getattr(event_details, "location", "")

    if not location:
        # Fallback to saved work address
        if user_preferences:
            work_addr = user_preferences.get("work_address")
            if work_addr and isinstance(work_addr, dict):
                location = work_addr.get("formatted_address") or work_addr.get("raw_address", "")

    if not location:
        return {
            "messages": [AIMessage(content="I need a delivery address to search for restaurants. Where should the food be delivered?")],
            "food_order": food_order.model_dump(),
        }

    # Build search terms - include dietary restrictions in search
    search_term = cuisine_prefs[0] if cuisine_prefs else "restaurant"

    # Add dietary keywords to search for better results
    dietary_search_terms = []
    if dietary:
        dietary_map = {
            "vegetarian": "vegetarian",
            "vegan": "vegan",
            "gluten-free": "gluten free",
            "halal": "halal",
            "kosher": "kosher",
        }
        for d in dietary:
            if d.lower() in dietary_map:
                dietary_search_terms.append(dietary_map[d.lower()])

    # Enhance search term with dietary if applicable
    if dietary_search_terms:
        search_term = f"{dietary_search_terms[0]} {search_term}"

    is_catering = headcount > 15  # Use catering search for larger groups

    emit_status("vendor_search_parallel", {
        "message": "Searching Yelp and Google Places in parallel...",
        "search_term": search_term,
        "location": location,
        "is_catering": is_catering,
    })

    # Run parallel searches
    search_tasks = []

    # Yelp search
    if is_catering:
        search_tasks.append(
            yelp_search_caterers.ainvoke({
                "location": location,
                "term": search_term,
                "limit": 5,
            })
        )
    else:
        search_tasks.append(
            yelp_search_restaurants.ainvoke({
                "location": location,
                "term": search_term,
                "limit": 5,
            })
        )

    # Google Places search
    search_tasks.append(
        search_places.ainvoke({
            "query": f"{search_term} restaurant near {location}",
            "place_type": "restaurant",
        })
    )

    # Execute searches in parallel
    results = await asyncio.gather(*search_tasks, return_exceptions=True)

    emit_status("vendor_search_processing", {"message": "Processing search results..."})

    # Process results
    all_vendors: list[VendorOption] = []
    seen_names: set[str] = set()

    for result in results:
        if isinstance(result, Exception):
            continue

        # Process Yelp results
        if "businesses" in result:
            for biz in result.get("businesses", []):
                name_lower = biz.get("name", "").lower()
                if name_lower not in seen_names:
                    seen_names.add(name_lower)
                    all_vendors.append(_normalize_yelp_vendor(biz))

        # Process Google Places results
        if "places" in result:
            for place in result.get("places", []):
                name_lower = place.get("name", "").lower()
                if name_lower not in seen_names:
                    seen_names.add(name_lower)
                    all_vendors.append(_normalize_google_vendor(place))

    # Sort by rating and take top 5
    all_vendors.sort(key=lambda x: x.rating or 0, reverse=True)
    top_vendors = all_vendors[:5]

    emit_status("vendor_search_complete", {
        "message": f"Found {len(top_vendors)} restaurant options",
        "vendor_count": len(top_vendors),
        "vendors": [v.name for v in top_vendors],
    })

    # Update food order state
    food_order.vendor_options = top_vendors
    food_order.current_step = "select_vendor"
    if "search_vendors" not in food_order.completed_steps:
        food_order.completed_steps.append("search_vendors")

    # Format response message
    if top_vendors:
        vendor_list = _format_vendor_options(top_vendors)

        # Add note about applied preferences
        pref_note = ""
        if dietary:
            pref_note = f"\n\n*Filtered for: {', '.join(dietary)}*"
        if user_preferences and user_preferences.get("allergies"):
            pref_note += f"\n⚠️ *Remember: {', '.join(user_preferences['allergies'])} allergy*"

        message = f"I found {len(top_vendors)} options for your order:\n\n{vendor_list}{pref_note}\nWhich restaurant would you like to order from? Just tell me the number or name."
    else:
        message = f"I couldn't find any restaurants matching '{search_term}' near {location}. Would you like me to search for something else?"

    return {
        "messages": [AIMessage(content=message)],
        "food_order": food_order.model_dump(),
        "cached_vendor_search": {
            "vendors": [v.model_dump() for v in top_vendors],
            "timestamp": datetime.utcnow().isoformat(),
            "location": location,
            "search_term": search_term,
        },
    }
