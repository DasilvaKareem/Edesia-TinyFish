"""User preference management tools."""

import asyncio
from typing import Optional
from langchain_core.tools import tool
from lib.firebase import update_user_preferences as update_prefs_firebase, get_user_preferences as get_prefs_firebase
from lib.redis import update_user_preferences as update_prefs_redis


def _geocode_address_sync(address: str) -> dict:
    """Geocode an address synchronously (for use in sync tool functions).

    Returns dict with label, raw_address, formatted_address, latitude, longitude, place_id.
    Falls back to raw address only if geocoding fails.
    """
    from tools.google_places import _geocode_address_internal

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(_geocode_address_internal(address))
        if "error" not in result:
            return {
                "raw_address": address,
                "formatted_address": result.get("formatted_address", address),
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
                "place_id": result.get("place_id"),
            }
    except Exception:
        pass

    # Fallback: save raw address without coordinates
    return {"raw_address": address}


@tool
def update_user_food_preferences(
    user_id: str,
    dietary_restrictions: Optional[list[str]] = None,
    allergies: Optional[list[str]] = None,
    favorite_cuisines: Optional[list[str]] = None,
    disliked_cuisines: Optional[list[str]] = None,
    spice_preference: Optional[str] = None,
    budget_per_person: Optional[float] = None,
    work_address: Optional[str] = None,
    home_address: Optional[str] = None,
) -> dict:
    """
    Update a user's food preferences in their profile.

    Use this tool when a user wants to update their dietary preferences,
    allergies, cuisine preferences, spice tolerance, budget, or saved addresses.

    Args:
        user_id: The user's ID (required)
        dietary_restrictions: List of dietary restrictions (e.g., ["Vegetarian", "Gluten-Free"])
        allergies: List of food allergies (e.g., ["Nuts", "Shellfish"])
        favorite_cuisines: List of preferred cuisines (e.g., ["Italian", "Japanese"])
        disliked_cuisines: List of cuisines to avoid (e.g., ["Indian", "Thai"])
        spice_preference: Spice tolerance level ("Mild", "Medium", "Spicy", "Extra Spicy")
        budget_per_person: Default budget per person in dollars
        work_address: Work/office address for delivery defaults (e.g., "123 Main St, Memphis, TN 38103")
        home_address: Home address for delivery (e.g., "456 Oak Ave, Memphis, TN 38104")

    Returns:
        Result of the update operation
    """
    if not user_id or user_id == "anonymous":
        return {
            "success": False,
            "error": "Cannot update preferences for anonymous users. Please sign in.",
        }

    # Build preferences dict with only provided values
    preferences = {}

    if dietary_restrictions is not None:
        preferences["dietary_restrictions"] = dietary_restrictions

    if allergies is not None:
        preferences["allergies"] = allergies

    if favorite_cuisines is not None:
        preferences["favorite_cuisines"] = favorite_cuisines

    if disliked_cuisines is not None:
        preferences["disliked_cuisines"] = disliked_cuisines

    if spice_preference is not None:
        preferences["spice_preference"] = spice_preference

    if budget_per_person is not None:
        preferences["budget_per_person"] = budget_per_person

    if work_address is not None:
        addr_data = _geocode_address_sync(work_address)
        addr_data["label"] = "work"
        preferences["work_address"] = addr_data

    if home_address is not None:
        addr_data = _geocode_address_sync(home_address)
        addr_data["label"] = "home"
        preferences["home_address"] = addr_data

    if not preferences:
        return {
            "success": False,
            "error": "No preferences provided to update.",
        }

    # Run the async Firebase update
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        success = loop.run_until_complete(update_prefs_firebase(user_id, preferences))

        # Also sync to Redis so preferences are available immediately on next message
        try:
            update_prefs_redis(user_id, preferences)
        except Exception as e:
            print(f"[PREFERENCES] Redis sync failed for user {user_id}: {e}")  # Best-effort; Firestore is source of truth

        if success:
            # Build confirmation message
            updated_fields = []
            if dietary_restrictions is not None:
                updated_fields.append(f"dietary restrictions: {', '.join(dietary_restrictions) if dietary_restrictions else 'cleared'}")
            if allergies is not None:
                updated_fields.append(f"allergies: {', '.join(allergies) if allergies else 'cleared'}")
            if favorite_cuisines is not None:
                updated_fields.append(f"favorite cuisines: {', '.join(favorite_cuisines) if favorite_cuisines else 'cleared'}")
            if disliked_cuisines is not None:
                updated_fields.append(f"cuisines to avoid: {', '.join(disliked_cuisines) if disliked_cuisines else 'cleared'}")
            if spice_preference is not None:
                updated_fields.append(f"spice preference: {spice_preference}")
            if budget_per_person is not None:
                updated_fields.append(f"budget: ${budget_per_person}/person")
            if work_address is not None:
                display = preferences["work_address"].get("formatted_address") or work_address
                updated_fields.append(f"work address: {display}")
            if home_address is not None:
                display = preferences["home_address"].get("formatted_address") or home_address
                updated_fields.append(f"home address: {display}")

            return {
                "success": True,
                "message": f"Updated your preferences: {'; '.join(updated_fields)}",
                "updated_fields": list(preferences.keys()),
            }
        else:
            return {
                "success": False,
                "error": "Failed to update preferences. Please try again.",
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error updating preferences: {str(e)}",
        }


@tool
def get_user_food_preferences(user_id: str) -> dict:
    """
    Get a user's current food preferences.

    Use this tool to check what preferences a user has saved.

    Args:
        user_id: The user's ID

    Returns:
        The user's current food preferences
    """
    if not user_id or user_id == "anonymous":
        return {
            "success": False,
            "error": "Cannot get preferences for anonymous users.",
        }

    # Run the async Firebase get
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        prefs = loop.run_until_complete(get_prefs_firebase(user_id))

        if prefs:
            return {
                "success": True,
                "preferences": prefs,
            }
        else:
            return {
                "success": True,
                "preferences": {},
                "message": "No preferences saved yet.",
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error getting preferences: {str(e)}",
        }


preferences_tools = [update_user_food_preferences, get_user_food_preferences]
