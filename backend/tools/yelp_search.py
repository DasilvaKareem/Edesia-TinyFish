"""Yelp API tools for searching restaurants, caterers, and food businesses."""

import os
import httpx
from typing import Optional
from langchain_core.tools import tool

from .unsplash import search_unsplash_photo

YELP_API_BASE = "https://api.yelp.com/v3"


def _get_headers():
    """Get Yelp API headers."""
    api_key = os.getenv("YELP_API_KEY")
    if not api_key:
        raise ValueError("YELP_API_KEY not set")
    return {"Authorization": f"Bearer {api_key}"}


@tool
async def yelp_search_restaurants(
    location: str,
    term: Optional[str] = None,
    cuisine: Optional[str] = None,
    price: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """
    Search for restaurants on Yelp with ratings and reviews.

    Args:
        location: City, address, or neighborhood (e.g., "San Francisco, CA")
        term: Search term (e.g., "pizza", "sushi", "italian")
        cuisine: Cuisine type filter (e.g., "mexican", "chinese", "indian")
        price: Price range filter - "1" ($), "2" ($$), "3" ($$$), "4" ($$$$), or combinations like "1,2"
        limit: Number of results to return (max 50)

    Returns:
        List of restaurants with name, rating, address, phone, and price level
    """
    params = {
        "location": location,
        "categories": "restaurants",
        "limit": min(limit, 50),
        "sort_by": "best_match",
    }

    if term:
        params["term"] = term
    if cuisine:
        params["categories"] = cuisine
    if price:
        params["price"] = price

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{YELP_API_BASE}/businesses/search",
            headers=_get_headers(),
            params=params,
        )
        response.raise_for_status()
        data = response.json()

    businesses = []
    for biz in data.get("businesses", []):
        businesses.append({
            "id": biz.get("id"),
            "name": biz.get("name"),
            "image_url": biz.get("image_url"),  # Restaurant photo
            "rating": biz.get("rating"),
            "review_count": biz.get("review_count"),
            "price": biz.get("price", "N/A"),
            "phone": biz.get("phone"),
            "display_phone": biz.get("display_phone"),
            "address": ", ".join(biz.get("location", {}).get("display_address", [])),
            "categories": [c.get("title") for c in biz.get("categories", [])],
            "url": biz.get("url"),
            "is_closed": biz.get("is_closed"),
            "distance_meters": biz.get("distance"),
        })

    # Unsplash fallback for businesses missing photos
    for biz in businesses:
        if not biz.get("image_url"):
            cuisine = biz["categories"][0] if biz.get("categories") else "restaurant"
            biz["image_url"] = await search_unsplash_photo(f"{cuisine} restaurant food") or ""

    return {
        "total": data.get("total", 0),
        "businesses": businesses,
    }


@tool
async def yelp_search_caterers(
    location: str,
    term: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """
    Search for catering services on Yelp (use this for browsing caterers without headcount).

    Args:
        location: City, address, or neighborhood (e.g., "San Francisco, CA")
        term: Search term (e.g., "corporate catering", "wedding catering")
        event_type: Type of event (e.g., "corporate", "wedding", "party")
        limit: Number of results to return (max 50)

    Returns:
        List of caterers with name, rating, address, phone, and services
    """
    search_term = "catering"
    if term:
        search_term = f"{term} catering"
    elif event_type:
        search_term = f"{event_type} catering"

    params = {
        "location": location,
        "term": search_term,
        "categories": "catering,caterers",
        "limit": min(limit, 50),
        "sort_by": "best_match",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{YELP_API_BASE}/businesses/search",
            headers=_get_headers(),
            params=params,
        )
        response.raise_for_status()
        data = response.json()

    businesses = []
    for biz in data.get("businesses", []):
        businesses.append({
            "id": biz.get("id"),
            "name": biz.get("name"),
            "image_url": biz.get("image_url"),  # Caterer photo
            "rating": biz.get("rating"),
            "review_count": biz.get("review_count"),
            "price": biz.get("price", "N/A"),
            "phone": biz.get("phone"),
            "display_phone": biz.get("display_phone"),
            "address": ", ".join(biz.get("location", {}).get("display_address", [])),
            "categories": [c.get("title") for c in biz.get("categories", [])],
            "url": biz.get("url"),
        })

    # Unsplash fallback for caterers missing photos
    for biz in businesses:
        if not biz.get("image_url"):
            biz["image_url"] = await search_unsplash_photo("catering food service") or ""

    return {
        "total": data.get("total", 0),
        "businesses": businesses,
    }


@tool
async def get_business_details(business_id: str) -> dict:
    """
    Get detailed information about a specific Yelp business.

    Args:
        business_id: The Yelp business ID (from search results)

    Returns:
        Detailed business info including hours, photos, and more
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{YELP_API_BASE}/businesses/{business_id}",
            headers=_get_headers(),
        )
        response.raise_for_status()
        biz = response.json()

    # Parse hours
    hours = []
    for day_hours in biz.get("hours", [{}])[0].get("open", []):
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day = days[day_hours.get("day", 0)]
        start = day_hours.get("start", "")
        end = day_hours.get("end", "")
        if start and end:
            hours.append(f"{day}: {start[:2]}:{start[2:]}-{end[:2]}:{end[2:]}")

    return {
        "id": biz.get("id"),
        "name": biz.get("name"),
        "rating": biz.get("rating"),
        "review_count": biz.get("review_count"),
        "price": biz.get("price", "N/A"),
        "phone": biz.get("phone"),
        "display_phone": biz.get("display_phone"),
        "address": ", ".join(biz.get("location", {}).get("display_address", [])),
        "categories": [c.get("title") for c in biz.get("categories", [])],
        "url": biz.get("url"),
        "photos": biz.get("photos", [])[:3],
        "hours": hours,
        "is_open_now": biz.get("hours", [{}])[0].get("is_open_now", False),
        "transactions": biz.get("transactions", []),
    }


@tool
async def get_business_reviews(business_id: str, limit: int = 3) -> dict:
    """
    Get reviews for a specific Yelp business.

    Args:
        business_id: The Yelp business ID (from search results)
        limit: Number of reviews to return (max 3 for API)

    Returns:
        List of reviews with rating, text, and user info
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{YELP_API_BASE}/businesses/{business_id}/reviews",
            headers=_get_headers(),
            params={"limit": min(limit, 3)},
        )
        response.raise_for_status()
        data = response.json()

    reviews = []
    for review in data.get("reviews", []):
        reviews.append({
            "rating": review.get("rating"),
            "text": review.get("text"),
            "time_created": review.get("time_created"),
            "user_name": review.get("user", {}).get("name"),
        })

    return {
        "total": data.get("total", 0),
        "reviews": reviews,
    }


# Export all tools
yelp_tools = [
    yelp_search_restaurants,
    yelp_search_caterers,
    get_business_details,
    get_business_reviews,
]
