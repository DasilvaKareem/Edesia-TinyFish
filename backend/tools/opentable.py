"""OpenTable integration for restaurant search and reservations."""

import os
from typing import Optional
from datetime import datetime
from langchain_core.tools import tool
import httpx

# Note: OpenTable doesn't have a public API, so this uses mock data
# In production, you could integrate with booking.com's API or similar

MOCK_RESTAURANTS = [
    {
        "id": "rest-001",
        "name": "The Capital Grille",
        "cuisine": "Steakhouse",
        "price_range": "$$$$",
        "rating": 4.7,
        "location": "Downtown",
        "available_times": ["6:00 PM", "7:00 PM", "8:00 PM", "9:00 PM"],
    },
    {
        "id": "rest-002",
        "name": "Olive Garden",
        "cuisine": "Italian",
        "price_range": "$$",
        "rating": 4.2,
        "location": "Midtown",
        "available_times": ["5:30 PM", "6:00 PM", "7:30 PM", "8:00 PM"],
    },
    {
        "id": "rest-003",
        "name": "Nobu",
        "cuisine": "Japanese",
        "price_range": "$$$$",
        "rating": 4.8,
        "location": "Downtown",
        "available_times": ["6:30 PM", "8:00 PM", "9:30 PM"],
    },
    {
        "id": "rest-004",
        "name": "Chipotle Catering",
        "cuisine": "Mexican",
        "price_range": "$",
        "rating": 4.0,
        "location": "Various",
        "available_times": ["11:00 AM", "12:00 PM", "1:00 PM", "6:00 PM"],
    },
    {
        "id": "rest-005",
        "name": "The Cheesecake Factory",
        "cuisine": "American",
        "price_range": "$$",
        "rating": 4.3,
        "location": "Mall District",
        "available_times": ["5:00 PM", "6:00 PM", "7:00 PM", "8:00 PM", "9:00 PM"],
    },
]


@tool
def search_restaurants(
    location: str,
    party_size: int,
    date: str,
    cuisine: Optional[str] = None,
    price_range: Optional[str] = None,
) -> list[dict]:
    """
    Search for available restaurants.

    Args:
        location: City or neighborhood to search in
        party_size: Number of guests
        date: Date for reservation (YYYY-MM-DD)
        cuisine: Optional cuisine type filter (e.g., "Italian", "Japanese")
        price_range: Optional price range filter ("$", "$$", "$$$", "$$$$")

    Returns:
        List of available restaurants with details
    """
    results = []

    for restaurant in MOCK_RESTAURANTS:
        # Apply filters
        if cuisine and cuisine.lower() not in restaurant["cuisine"].lower():
            continue
        if price_range and restaurant["price_range"] != price_range:
            continue

        results.append({
            "id": restaurant["id"],
            "name": restaurant["name"],
            "cuisine": restaurant["cuisine"],
            "price_range": restaurant["price_range"],
            "rating": restaurant["rating"],
            "location": restaurant["location"],
            "available_times": restaurant["available_times"],
            "max_party_size": 20,  # Mock value
        })

    return results


@tool
def get_restaurant_details(restaurant_id: str) -> dict:
    """
    Get detailed information about a restaurant.

    Args:
        restaurant_id: The restaurant's unique identifier

    Returns:
        Restaurant details including menu highlights, dress code, etc.
    """
    for restaurant in MOCK_RESTAURANTS:
        if restaurant["id"] == restaurant_id:
            return {
                **restaurant,
                "address": "123 Main Street",
                "phone": "(555) 123-4567",
                "dress_code": "Business Casual",
                "parking": "Valet available",
                "private_dining": True,
                "menu_highlights": [
                    "Dry-aged ribeye",
                    "Lobster mac and cheese",
                    "Flourless chocolate cake",
                ],
                "average_cost_per_person": 75.00,
            }

    return {"error": "Restaurant not found"}


@tool
def make_reservation(
    restaurant_id: str,
    party_size: int,
    date: str,
    time: str,
    contact_name: str,
    contact_email: str,
    contact_phone: Optional[str] = None,
    special_requests: Optional[str] = None,
) -> dict:
    """
    Create a reservation request (requires approval).

    Args:
        restaurant_id: The restaurant's unique identifier
        party_size: Number of guests
        date: Date for reservation (YYYY-MM-DD)
        time: Time for reservation (e.g., "7:00 PM")
        contact_name: Name for the reservation
        contact_email: Email for confirmation
        contact_phone: Optional phone number
        special_requests: Optional special requests (dietary, seating, etc.)

    Returns:
        Pending reservation details requiring approval
    """
    import uuid

    # Find restaurant
    restaurant = None
    for r in MOCK_RESTAURANTS:
        if r["id"] == restaurant_id:
            restaurant = r
            break

    if not restaurant:
        return {"error": "Restaurant not found"}

    # Create pending action
    action = {
        "action_id": str(uuid.uuid4()),
        "action_type": "reservation",
        "status": "pending_approval",
        "description": f"Reservation at {restaurant['name']} for {party_size} on {date} at {time}",
        "payload": {
            "restaurant_id": restaurant_id,
            "restaurant_name": restaurant["name"],
            "party_size": party_size,
            "date": date,
            "time": time,
            "contact_name": contact_name,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "special_requests": special_requests,
        },
    }

    return action


opentable_tools = [search_restaurants, get_restaurant_details, make_reservation]
