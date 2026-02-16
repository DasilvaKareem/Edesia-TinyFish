"""Catering search tool using Yelp Fusion API."""

import os
import uuid
from typing import Optional
from langchain_core.tools import tool
import httpx

# Yelp Fusion API (requires API key)
YELP_API_URL = "https://api.yelp.com/v3"

# Mock caterers for development
MOCK_CATERERS = [
    {
        "id": "cat-001",
        "name": "Corporate Catering Co",
        "cuisine": ["American", "Mediterranean"],
        "rating": 4.6,
        "price_per_person_range": [15, 35],
        "min_headcount": 10,
        "delivery": True,
        "setup_included": True,
    },
    {
        "id": "cat-002",
        "name": "Fresh & Fast Lunches",
        "cuisine": ["Sandwiches", "Salads", "Wraps"],
        "rating": 4.4,
        "price_per_person_range": [10, 20],
        "min_headcount": 5,
        "delivery": True,
        "setup_included": False,
    },
    {
        "id": "cat-003",
        "name": "Taco Fiesta Catering",
        "cuisine": ["Mexican", "Tex-Mex"],
        "rating": 4.7,
        "price_per_person_range": [12, 25],
        "min_headcount": 15,
        "delivery": True,
        "setup_included": True,
    },
    {
        "id": "cat-004",
        "name": "Sushi for Business",
        "cuisine": ["Japanese", "Sushi"],
        "rating": 4.8,
        "price_per_person_range": [20, 45],
        "min_headcount": 8,
        "delivery": True,
        "setup_included": True,
    },
    {
        "id": "cat-005",
        "name": "Pizza Party Pros",
        "cuisine": ["Italian", "Pizza"],
        "rating": 4.3,
        "price_per_person_range": [8, 15],
        "min_headcount": 5,
        "delivery": True,
        "setup_included": False,
    },
]

MOCK_MENUS = {
    "cat-001": {
        "packages": [
            {
                "name": "Executive Lunch",
                "price_per_person": 25,
                "items": ["Choice of protein", "Two sides", "Salad", "Dessert", "Beverages"],
            },
            {
                "name": "Premium Buffet",
                "price_per_person": 35,
                "items": ["Three proteins", "Four sides", "Salad bar", "Dessert station", "Full beverage service"],
            },
        ],
        "individual_items": [
            {"name": "Grilled Chicken Breast", "price": 12},
            {"name": "Roasted Vegetables", "price": 6},
            {"name": "Caesar Salad", "price": 8},
        ],
    },
    "cat-002": {
        "packages": [
            {
                "name": "Sandwich Spread",
                "price_per_person": 12,
                "items": ["Assorted sandwiches", "Chips", "Cookie", "Bottled water"],
            },
            {
                "name": "Salad Bar",
                "price_per_person": 15,
                "items": ["Build-your-own salads", "Protein options", "Dressings", "Bread", "Drinks"],
            },
        ],
    },
    "cat-003": {
        "packages": [
            {
                "name": "Taco Bar",
                "price_per_person": 15,
                "items": ["Choice of proteins", "Tortillas", "Toppings bar", "Rice", "Beans", "Chips & salsa"],
            },
            {
                "name": "Fiesta Buffet",
                "price_per_person": 22,
                "items": ["Fajitas", "Enchiladas", "Taco bar", "Rice & beans", "Churros", "Margarita bar (non-alc)"],
            },
        ],
    },
}


@tool
def search_caterers(
    location: str,
    headcount: Optional[int] = None,
    cuisine: Optional[str] = None,
    max_price_per_person: Optional[float] = None,
) -> list[dict]:
    """
    Search for caterers in an area.

    Args:
        location: City or address for delivery
        headcount: Number of people to feed (optional, filters by min headcount if provided)
        cuisine: Optional cuisine preference
        max_price_per_person: Optional maximum budget per person

    Returns:
        List of matching caterers
    """
    # Try Yelp API first
    yelp_key = os.getenv("YELP_API_KEY")
    if yelp_key:
        try:
            return _search_yelp(location, headcount or 10, cuisine, yelp_key)
        except Exception:
            pass  # Fall back to mock data

    # Use mock data
    results = []
    for caterer in MOCK_CATERERS:
        # Filter by headcount if provided
        if headcount and headcount < caterer["min_headcount"]:
            continue

        # Filter by cuisine
        if cuisine and not any(cuisine.lower() in c.lower() for c in caterer["cuisine"]):
            continue

        # Filter by price
        if max_price_per_person and caterer["price_per_person_range"][0] > max_price_per_person:
            continue

        results.append({
            "id": caterer["id"],
            "name": caterer["name"],
            "cuisines": caterer["cuisine"],
            "rating": caterer["rating"],
            "price_range": f"${caterer['price_per_person_range'][0]}-${caterer['price_per_person_range'][1]}/person",
            "min_headcount": caterer["min_headcount"],
            "delivery": caterer["delivery"],
            "setup_included": caterer["setup_included"],
        })

    return results


def _search_yelp(location: str, headcount: int, cuisine: Optional[str], api_key: str) -> list[dict]:
    """Search Yelp Fusion API for caterers."""
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {
        "location": location,
        "term": f"{cuisine} catering" if cuisine else "catering",
        "categories": "catering",
        "limit": 10,
    }

    with httpx.Client() as client:
        response = client.get(f"{YELP_API_URL}/businesses/search", headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    return [
        {
            "id": biz["id"],
            "name": biz["name"],
            "cuisines": [cat["title"] for cat in biz.get("categories", [])],
            "rating": biz.get("rating"),
            "price_range": biz.get("price", "$$"),
            "phone": biz.get("phone"),
            "address": ", ".join(biz["location"].get("display_address", [])),
        }
        for biz in data.get("businesses", [])
    ]


@tool
def get_catering_menu(caterer_id: str) -> dict:
    """
    Get menu and pricing for a caterer.

    Args:
        caterer_id: The caterer's unique identifier

    Returns:
        Menu with packages and individual items
    """
    # Check mock data
    menu = MOCK_MENUS.get(caterer_id)
    if menu:
        caterer = next((c for c in MOCK_CATERERS if c["id"] == caterer_id), None)
        return {
            "caterer_id": caterer_id,
            "caterer_name": caterer["name"] if caterer else "Unknown",
            "packages": menu.get("packages", []),
            "individual_items": menu.get("individual_items", []),
        }

    return {"error": "Menu not found for this caterer"}


@tool
def request_catering_quote(
    caterer_id: str,
    headcount: int,
    package_name: Optional[str] = None,
    items: Optional[list[str]] = None,
    delivery_date: str = None,
    delivery_time: str = None,
    delivery_address: str = None,
    dietary_notes: Optional[str] = None,
) -> dict:
    """
    Request a catering quote (requires approval to place order).

    Args:
        caterer_id: The caterer's unique identifier
        headcount: Number of people to feed
        package_name: Name of a package to order
        items: List of individual items if not using a package
        delivery_date: Date for delivery (YYYY-MM-DD)
        delivery_time: Time for delivery
        delivery_address: Delivery address
        dietary_notes: Any dietary restrictions or notes

    Returns:
        Quote details with pending approval status
    """
    caterer = next((c for c in MOCK_CATERERS if c["id"] == caterer_id), None)
    if not caterer:
        return {"error": "Caterer not found"}

    menu = MOCK_MENUS.get(caterer_id, {})

    # Calculate price
    if package_name:
        package = next((p for p in menu.get("packages", []) if p["name"] == package_name), None)
        if not package:
            return {"error": f"Package '{package_name}' not found"}
        subtotal = package["price_per_person"] * headcount
        items_desc = package["items"]
    else:
        # Calculate from individual items
        subtotal = sum(
            next((i["price"] for i in menu.get("individual_items", []) if i["name"] == item), 10)
            for item in (items or [])
        ) * headcount
        items_desc = items or []

    tax = round(subtotal * 0.08, 2)
    delivery_fee = 25.00 if headcount < 20 else 0
    total = subtotal + tax + delivery_fee

    # Create pending action
    action = {
        "action_id": str(uuid.uuid4()),
        "action_type": "catering_order",
        "status": "pending_approval",
        "description": f"Catering order from {caterer['name']} for {headcount} people - ${total:.2f}",
        "payload": {
            "caterer_id": caterer_id,
            "caterer_name": caterer["name"],
            "headcount": headcount,
            "package": package_name,
            "items": items_desc,
            "delivery_date": delivery_date,
            "delivery_time": delivery_time,
            "delivery_address": delivery_address,
            "dietary_notes": dietary_notes,
            "pricing": {
                "subtotal": subtotal,
                "tax": tax,
                "delivery_fee": delivery_fee,
                "total": total,
                "per_person": round(total / headcount, 2),
            },
        },
    }

    return action


catering_tools = [search_caterers, get_catering_menu, request_catering_quote]
