"""Google Places API tools for location and restaurant search."""

import os
from typing import Optional
import httpx
from langchain_core.tools import tool

PLACES_API_BASE = "https://maps.googleapis.com/maps/api/place"


def _get_api_key() -> str:
    """Get Google Maps API key."""
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY not set")
    return api_key


@tool
async def search_places(
    query: str,
    location: Optional[str] = None,
    radius_meters: int = 5000,
    place_type: Optional[str] = None,
) -> dict:
    """
    Search for places using Google Places API.

    Args:
        query: Search query (e.g., "Italian restaurants", "coffee shops", "catering")
        location: Center point for search as "lat,lng" (e.g., "37.7749,-122.4194" for SF)
        radius_meters: Search radius in meters (default 5000m = ~3 miles)
        place_type: Filter by type (restaurant, cafe, bar, bakery, meal_delivery, meal_takeaway)

    Returns:
        List of places with name, address, rating, and place_id for details
    """
    params = {
        "query": query,
        "key": _get_api_key(),
    }

    if location:
        params["location"] = location
        params["radius"] = radius_meters

    if place_type:
        params["type"] = place_type

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLACES_API_BASE}/textsearch/json",
            params=params,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    if data.get("status") != "OK":
        return {"error": data.get("status"), "message": data.get("error_message", "")}

    places = []
    for place in data.get("results", [])[:10]:
        places.append({
            "place_id": place.get("place_id"),
            "name": place.get("name"),
            "address": place.get("formatted_address"),
            "rating": place.get("rating"),
            "total_ratings": place.get("user_ratings_total"),
            "price_level": "".join(["$"] * place.get("price_level", 0)) or "N/A",
            "types": place.get("types", [])[:3],
            "open_now": place.get("opening_hours", {}).get("open_now"),
            "location": place.get("geometry", {}).get("location"),
        })

    return {
        "total": len(places),
        "places": places,
    }


@tool
async def search_nearby(
    location: str,
    place_type: str = "restaurant",
    radius_meters: int = 1500,
    keyword: Optional[str] = None,
) -> dict:
    """
    Search for nearby places of a specific type.

    Args:
        location: Center point as "lat,lng" (e.g., "37.7749,-122.4194")
        place_type: Type of place (restaurant, cafe, bar, bakery, meal_delivery, meal_takeaway)
        radius_meters: Search radius in meters (default 1500m = ~1 mile)
        keyword: Optional keyword to filter results (e.g., "pizza", "vegan")

    Returns:
        List of nearby places sorted by prominence
    """
    params = {
        "location": location,
        "radius": radius_meters,
        "type": place_type,
        "key": _get_api_key(),
    }

    if keyword:
        params["keyword"] = keyword

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLACES_API_BASE}/nearbysearch/json",
            params=params,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    if data.get("status") != "OK":
        return {"error": data.get("status"), "message": data.get("error_message", "")}

    places = []
    for place in data.get("results", [])[:10]:
        places.append({
            "place_id": place.get("place_id"),
            "name": place.get("name"),
            "address": place.get("vicinity"),
            "rating": place.get("rating"),
            "total_ratings": place.get("user_ratings_total"),
            "price_level": "".join(["$"] * place.get("price_level", 0)) or "N/A",
            "open_now": place.get("opening_hours", {}).get("open_now"),
        })

    return {
        "total": len(places),
        "places": places,
    }


@tool
async def get_place_details(place_id: str) -> dict:
    """
    Get detailed information about a specific place.

    Args:
        place_id: The Google Place ID (from search results)

    Returns:
        Detailed place info including hours, phone, website, reviews, photos, and service options
    """
    params = {
        "place_id": place_id,
        "fields": ",".join([
            # Basic
            "name", "formatted_address", "types", "business_status", "url",
            # Contact
            "formatted_phone_number", "international_phone_number",
            "website", "opening_hours",
            # Atmosphere / service options
            "rating", "user_ratings_total", "price_level", "reviews",
            "editorial_summary",
            "delivery", "dine_in", "takeout", "curbside_pickup", "reservable",
            "serves_beer", "serves_breakfast", "serves_brunch",
            "serves_dinner", "serves_lunch", "serves_wine",
            "serves_vegetarian_food",
            # Media
            "photos",
        ]),
        "key": _get_api_key(),
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLACES_API_BASE}/details/json",
            params=params,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    if data.get("status") != "OK":
        return {"error": data.get("status"), "message": data.get("error_message", "")}

    place = data.get("result", {})
    api_key = _get_api_key()

    # Parse hours
    hours = []
    opening_hours = place.get("opening_hours", {})
    for day_text in opening_hours.get("weekday_text", []):
        hours.append(day_text)

    # Parse reviews
    reviews = []
    for review in place.get("reviews", [])[:3]:
        reviews.append({
            "rating": review.get("rating"),
            "text": review.get("text", "")[:200],
            "time": review.get("relative_time_description"),
            "author": review.get("author_name"),
        })

    # Build photo URLs from photo references (up to 5)
    photos = []
    for photo in place.get("photos", [])[:5]:
        ref = photo.get("photo_reference")
        if ref:
            photos.append(
                f"{PLACES_API_BASE}/photo?maxwidth=800&photoreference={ref}&key={api_key}"
            )

    # Service options
    service_options = {}
    for key in ("delivery", "dine_in", "takeout", "curbside_pickup", "reservable"):
        if key in place:
            service_options[key] = place[key]

    # Meal types served
    serves = {}
    for key in ("serves_breakfast", "serves_brunch", "serves_lunch",
                "serves_dinner", "serves_beer", "serves_wine",
                "serves_vegetarian_food"):
        if key in place:
            serves[key.replace("serves_", "")] = place[key]

    return {
        "place_id": place_id,
        "name": place.get("name"),
        "address": place.get("formatted_address"),
        "phone": place.get("formatted_phone_number") or place.get("international_phone_number"),
        "website": place.get("website"),
        "google_maps_url": place.get("url"),
        "rating": place.get("rating"),
        "total_ratings": place.get("user_ratings_total"),
        "price_level": "".join(["$"] * place.get("price_level", 0)) or "N/A",
        "business_status": place.get("business_status"),
        "is_open_now": opening_hours.get("open_now"),
        "hours": hours,
        "reviews": reviews,
        "types": place.get("types", [])[:5],
        "photos": photos,
        "editorial_summary": place.get("editorial_summary", {}).get("overview", ""),
        "service_options": service_options,
        "serves": serves,
    }


async def _geocode_address_internal(address: str) -> dict:
    """Geocode an address to coordinates. Internal helper, not a LangChain tool.

    Args:
        address: Full address to geocode.

    Returns:
        Dict with formatted_address, latitude, longitude, location_string, place_id.
        On failure returns dict with error and message keys.
    """
    params = {
        "address": address,
        "key": _get_api_key(),
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    if data.get("status") != "OK":
        return {"error": data.get("status"), "message": data.get("error_message", "")}

    result = data.get("results", [{}])[0]
    location = result.get("geometry", {}).get("location", {})

    return {
        "formatted_address": result.get("formatted_address"),
        "latitude": location.get("lat"),
        "longitude": location.get("lng"),
        "location_string": f"{location.get('lat')},{location.get('lng')}",
        "place_id": result.get("place_id"),
    }


@tool
async def geocode_address(address: str) -> dict:
    """
    Convert an address to latitude/longitude coordinates.

    Args:
        address: Full address to geocode (e.g., "1600 Amphitheatre Parkway, Mountain View, CA")

    Returns:
        Latitude, longitude, and formatted address
    """
    return await _geocode_address_internal(address)


@tool
async def get_distance_matrix(
    origins: str,
    destinations: str,
    mode: str = "driving",
) -> dict:
    """
    Calculate travel time and distance between locations.

    Args:
        origins: Starting address or "lat,lng"
        destinations: Destination address or "lat,lng"
        mode: Travel mode - driving, walking, bicycling, transit

    Returns:
        Distance and duration for the route
    """
    params = {
        "origins": origins,
        "destinations": destinations,
        "mode": mode,
        "key": _get_api_key(),
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params=params,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    if data.get("status") != "OK":
        return {"error": data.get("status"), "message": data.get("error_message", "")}

    element = data.get("rows", [{}])[0].get("elements", [{}])[0]

    if element.get("status") != "OK":
        return {"error": element.get("status")}

    return {
        "origin": data.get("origin_addresses", [""])[0],
        "destination": data.get("destination_addresses", [""])[0],
        "distance_text": element.get("distance", {}).get("text"),
        "distance_meters": element.get("distance", {}).get("value"),
        "duration_text": element.get("duration", {}).get("text"),
        "duration_seconds": element.get("duration", {}).get("value"),
        "mode": mode,
    }


# Export all tools
google_places_tools = [
    search_places,
    search_nearby,
    get_place_details,
    geocode_address,
    get_distance_matrix,
]
