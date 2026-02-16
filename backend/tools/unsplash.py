"""Unsplash API fallback for restaurant and food item photos."""

import os
import httpx
from typing import Optional

UNSPLASH_API_BASE = "https://api.unsplash.com"


def _get_unsplash_headers():
    """Get Unsplash API headers."""
    access_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not access_key:
        raise ValueError("UNSPLASH_ACCESS_KEY not set")
    return {"Authorization": f"Client-ID {access_key}"}


async def search_unsplash_photo(
    query: str,
    per_page: int = 1,
    orientation: Optional[str] = "landscape",
) -> Optional[str]:
    """Search Unsplash for a photo and return the URL.

    Args:
        query: Search term (e.g., "sushi restaurant", "pepperoni pizza")
        per_page: Number of results (default 1)
        orientation: Photo orientation - "landscape", "portrait", or "squarish"

    Returns:
        URL of the best matching photo, or None if not found.
    """
    try:
        params = {
            "query": query,
            "per_page": per_page,
            "content_filter": "high",
        }
        if orientation:
            params["orientation"] = orientation

        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{UNSPLASH_API_BASE}/search/photos",
                headers=_get_unsplash_headers(),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        if not results:
            return None

        # Use "regular" size (1080px wide) — good balance of quality and speed
        return results[0].get("urls", {}).get("regular")
    except Exception as e:
        print(f"[UNSPLASH] Search failed for '{query}': {e}")
        return None


async def get_restaurant_photos(
    restaurant_name: str,
    cuisine_categories: list[str] | None = None,
    count: int = 3,
) -> list[str]:
    """Get fallback restaurant photos from Unsplash.

    Args:
        restaurant_name: Name of the restaurant
        cuisine_categories: Cuisine types (e.g., ["Italian", "Pizza"])
        count: Number of photos to fetch (max 3)

    Returns:
        List of photo URLs.
    """
    queries = []
    # Try cuisine-specific restaurant query first
    if cuisine_categories:
        primary_cuisine = cuisine_categories[0]
        queries.append(f"{primary_cuisine} restaurant food")
    queries.append(f"{restaurant_name} restaurant")
    queries.append("restaurant dining food")

    photos = []
    seen = set()
    for query in queries:
        if len(photos) >= count:
            break
        url = await search_unsplash_photo(query)
        if url and url not in seen:
            photos.append(url)
            seen.add(url)

    return photos[:count]


async def get_food_item_photo(item_name: str) -> Optional[str]:
    """Get a fallback photo for a menu item from Unsplash.

    Args:
        item_name: Name of the food item (e.g., "Margherita Pizza", "Caesar Salad")

    Returns:
        URL of a matching food photo, or None.
    """
    return await search_unsplash_photo(f"{item_name} food dish", orientation="squarish")
