"""Redis configuration for LangGraph checkpointer and long-term memory."""

import os
import json
import ssl
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import contextmanager, asynccontextmanager
from langgraph.checkpoint.redis import RedisSaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
import redis
import redis.asyncio as aioredis


# Key prefixes for different data types
PREFERENCES_PREFIX = "edesia:user_prefs:"

# Path to Redis Cloud CA certificate (bundled with the app)
CA_CERT_PATH = Path(__file__).parent / "redis_ca.pem"


def get_redis_config() -> dict:
    """Get Redis connection configuration."""
    return {
        "host": os.environ.get("REDIS_HOST", "localhost"),
        "port": int(os.environ.get("REDIS_PORT", "6379")),
        "password": os.environ.get("REDIS_PASSWORD", ""),
        "username": os.environ.get("REDIS_USER", "default"),
        "decode_responses": False,  # Required for LangGraph checkpointer
    }


def get_redis_url() -> str:
    """Build Redis URL from environment variables.

    Note: This is primarily used for user preferences (direct Redis client).
    The checkpointer uses get_redis_config() with explicit clients.
    """
    config = get_redis_config()
    host = config["host"]
    port = config["port"]
    password = config["password"]
    user = config["username"]

    # Use SSL (rediss://) for Redis Cloud
    protocol = "rediss"

    if password:
        return f"{protocol}://{user}:{password}@{host}:{port}"
    return f"{protocol}://{host}:{port}"


def _create_redis_client(decode_responses: bool = False) -> redis.Redis:
    """Create a Redis client with SSL configured for Redis Cloud."""
    config = get_redis_config()

    return redis.Redis(
        host=config["host"],
        port=config["port"],
        username=config["username"],
        password=config["password"],
        ssl=True,
        ssl_cert_reqs=None,  # Don't verify - Redis Cloud uses valid certs
        decode_responses=decode_responses,
    )


@contextmanager
def get_checkpointer() -> RedisSaver:
    """Get a sync Redis checkpointer instance for LangGraph.

    Use this for synchronous operations only.
    """
    # Create Redis client with SSL configured
    client = _create_redis_client(decode_responses=False)
    saver = RedisSaver(redis_client=client)
    saver.setup()
    try:
        yield saver
    finally:
        client.close()


def _create_async_redis_client() -> aioredis.Redis:
    """Create an async Redis client with SSL configured for Redis Cloud."""
    config = get_redis_config()

    return aioredis.Redis(
        host=config["host"],
        port=config["port"],
        username=config["username"],
        password=config["password"],
        ssl=True,
        ssl_cert_reqs=None,  # Don't verify - Redis Cloud uses valid certs
        decode_responses=False,
    )


@asynccontextmanager
async def get_async_checkpointer() -> AsyncRedisSaver:
    """Get an async Redis checkpointer instance for LangGraph.

    Use this for async operations (ainvoke, astream).
    """
    # Create async Redis client with SSL configured
    client = _create_async_redis_client()
    saver = AsyncRedisSaver(redis_client=client)
    await saver.asetup()
    try:
        yield saver
    finally:
        await client.aclose()


def get_redis_client() -> redis.Redis:
    """Get a Redis client for direct operations (preferences, etc.)."""
    url = get_redis_url()
    # Use CA cert for SSL verification
    ssl_ca_certs = str(CA_CERT_PATH) if CA_CERT_PATH.exists() else None
    return redis.from_url(url, decode_responses=True, ssl_ca_certs=ssl_ca_certs)


# ==================== User Preferences Long-Term Memory ====================

def get_user_preferences(user_id: str) -> Optional[dict]:
    """Load user food preferences from Redis.

    Args:
        user_id: The user's unique identifier.

    Returns:
        User preferences dict if found, None otherwise.
    """
    if not user_id or user_id == "anonymous":
        return None

    client = get_redis_client()
    key = f"{PREFERENCES_PREFIX}{user_id}"

    data = client.get(key)
    if data:
        return json.loads(data)
    return None


def save_user_preferences(user_id: str, preferences: dict) -> bool:
    """Save user food preferences to Redis.

    Args:
        user_id: The user's unique identifier.
        preferences: The preferences dict to save.

    Returns:
        True if saved successfully, False otherwise.
    """
    if not user_id or user_id == "anonymous":
        return False

    client = get_redis_client()
    key = f"{PREFERENCES_PREFIX}{user_id}"

    # Update the updated_at timestamp
    preferences["updated_at"] = datetime.utcnow().isoformat()

    # Ensure user_id is set
    preferences["user_id"] = user_id

    # If no created_at, set it
    if "created_at" not in preferences:
        preferences["created_at"] = datetime.utcnow().isoformat()

    client.set(key, json.dumps(preferences))
    return True


def update_user_preferences(user_id: str, updates: dict) -> Optional[dict]:
    """Update specific fields in user preferences (merge update).

    Args:
        user_id: The user's unique identifier.
        updates: Dict of fields to update/merge.

    Returns:
        Updated preferences dict if successful, None otherwise.
    """
    if not user_id or user_id == "anonymous":
        return None

    # Load existing preferences or create new
    existing = get_user_preferences(user_id) or {
        "user_id": user_id,
        "dietary_restrictions": [],
        "allergies": [],
        "favorite_cuisines": [],
        "disliked_cuisines": [],
        "favorite_foods": [],
        "disliked_foods": [],
        "favorite_vendors": [],
        "created_at": datetime.utcnow().isoformat(),
    }

    # Merge list fields (add new items, don't duplicate)
    list_fields = [
        "dietary_restrictions", "allergies", "favorite_cuisines",
        "disliked_cuisines", "favorite_foods", "disliked_foods",
        "favorite_vendors"
    ]

    for field in list_fields:
        if field in updates:
            existing_list = existing.get(field, [])
            new_items = updates[field] if isinstance(updates[field], list) else [updates[field]]
            # Add new items without duplicates (case-insensitive)
            existing_lower = [item.lower() for item in existing_list]
            for item in new_items:
                if item.lower() not in existing_lower:
                    existing_list.append(item)
            existing[field] = existing_list

    # Overwrite scalar fields (includes address objects which should replace, not merge)
    scalar_fields = [
        "spice_preference", "default_budget_per_person",
        "preferred_price_level", "notes",
        "work_address", "home_address"
    ]
    for field in scalar_fields:
        if field in updates:
            existing[field] = updates[field]

    # Save the merged preferences
    save_user_preferences(user_id, existing)
    return existing


def delete_user_preferences(user_id: str) -> bool:
    """Delete user preferences from Redis.

    Args:
        user_id: The user's unique identifier.

    Returns:
        True if deleted, False otherwise.
    """
    if not user_id or user_id == "anonymous":
        return False

    client = get_redis_client()
    key = f"{PREFERENCES_PREFIX}{user_id}"
    return client.delete(key) > 0


def extract_preferences_from_text(text: str) -> dict:
    """Extract food preferences from natural language text.

    This function detects dietary restrictions, allergies, and preferences
    mentioned in user messages.

    Args:
        text: The user's message text.

    Returns:
        Dict of detected preferences to merge.
    """
    text_lower = text.lower()
    updates = {}

    # Dietary restrictions detection
    dietary_keywords = {
        "vegetarian": ["vegetarian", "veggie", "no meat"],
        "vegan": ["vegan", "plant-based", "plant based"],
        "gluten-free": ["gluten-free", "gluten free", "no gluten", "celiac"],
        "halal": ["halal"],
        "kosher": ["kosher"],
        "pescatarian": ["pescatarian", "fish only"],
        "keto": ["keto", "ketogenic", "low-carb", "low carb"],
        "paleo": ["paleo"],
        "dairy-free": ["dairy-free", "dairy free", "no dairy", "lactose intolerant", "lactose-free"],
    }

    detected_dietary = []
    for restriction, keywords in dietary_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                detected_dietary.append(restriction)
                break

    if detected_dietary:
        updates["dietary_restrictions"] = detected_dietary

    # Allergy detection
    allergy_keywords = {
        "nuts": ["nut allergy", "allergic to nuts", "no nuts", "nut-free", "peanut allergy"],
        "shellfish": ["shellfish allergy", "allergic to shellfish", "no shellfish"],
        "dairy": ["dairy allergy", "allergic to dairy", "milk allergy"],
        "eggs": ["egg allergy", "allergic to eggs", "no eggs"],
        "soy": ["soy allergy", "allergic to soy", "no soy"],
        "wheat": ["wheat allergy", "allergic to wheat"],
        "fish": ["fish allergy", "allergic to fish"],
        "sesame": ["sesame allergy", "allergic to sesame"],
    }

    detected_allergies = []
    for allergy, keywords in allergy_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                detected_allergies.append(allergy)
                break

    if detected_allergies:
        updates["allergies"] = detected_allergies

    # Cuisine preferences
    cuisine_keywords = [
        "italian", "mexican", "chinese", "japanese", "thai", "indian",
        "mediterranean", "greek", "korean", "vietnamese", "french",
        "american", "southern", "bbq", "middle eastern", "ethiopian"
    ]

    # Detect "love/like/prefer X cuisine" patterns
    like_patterns = ["love ", "like ", "prefer ", "favorite is ", "into "]
    dislike_patterns = ["hate ", "don't like ", "dislike ", "not a fan of ", "avoid "]

    for cuisine in cuisine_keywords:
        # Check for likes
        for pattern in like_patterns:
            if pattern + cuisine in text_lower or cuisine + " is my favorite" in text_lower:
                if "favorite_cuisines" not in updates:
                    updates["favorite_cuisines"] = []
                updates["favorite_cuisines"].append(cuisine.title())
                break

        # Check for dislikes
        for pattern in dislike_patterns:
            if pattern + cuisine in text_lower:
                if "disliked_cuisines" not in updates:
                    updates["disliked_cuisines"] = []
                updates["disliked_cuisines"].append(cuisine.title())
                break

    # Spice preference detection
    if any(phrase in text_lower for phrase in ["no spice", "not spicy", "mild only", "can't handle spice"]):
        updates["spice_preference"] = "none"
    elif any(phrase in text_lower for phrase in ["mild spice", "little spice", "slightly spicy"]):
        updates["spice_preference"] = "mild"
    elif any(phrase in text_lower for phrase in ["medium spice", "moderately spicy"]):
        updates["spice_preference"] = "medium"
    elif any(phrase in text_lower for phrase in ["love spicy", "extra spicy", "very spicy", "super spicy"]):
        updates["spice_preference"] = "extra_hot"
    elif any(phrase in text_lower for phrase in ["spicy", "hot food"]):
        updates["spice_preference"] = "hot"

    return updates
