"""Preference management node for extracting and saving user food preferences."""

import weave
from agent.state import AgentState
from lib.redis import extract_preferences_from_text, update_user_preferences, get_user_preferences


@weave.op()
async def preferences_node(state: AgentState) -> dict:
    """Extract food preferences from user messages and save to Redis.

    This node runs at the start of each conversation turn to:
    1. Load existing preferences if not already in state
    2. Detect new preferences in the latest user message
    3. Save any detected preferences to Redis

    Args:
        state: Current agent state.

    Returns:
        State updates with user_preferences and preferences_updated flag.
    """
    user_id = state.get("user_id")

    # Can't save preferences for anonymous users
    if not user_id or user_id == "anonymous":
        return {}

    # Get the latest user message
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_message = messages[-1]
    content = (
        last_message.get("content", "")
        if isinstance(last_message, dict)
        else getattr(last_message, "content", "")
    )

    # Only process user messages
    msg_type = (
        last_message.get("role", "")
        if isinstance(last_message, dict)
        else getattr(last_message, "type", "")
    )
    if msg_type not in ("user", "human"):
        return {}

    # Extract preferences from the message
    detected = extract_preferences_from_text(content)

    updates = {}

    if detected:
        # Save to Redis and get updated preferences
        updated_prefs = update_user_preferences(user_id, detected)
        if updated_prefs:
            updates["user_preferences"] = updated_prefs
            updates["preferences_updated"] = True
    else:
        # Load preferences if not already in state
        if not state.get("user_preferences"):
            existing = get_user_preferences(user_id)
            if existing:
                updates["user_preferences"] = existing

    return updates


def get_preference_acknowledgment(detected: dict) -> str:
    """Generate a brief acknowledgment message for detected preferences.

    Args:
        detected: Dict of newly detected preferences.

    Returns:
        Acknowledgment message string, or empty string if nothing to acknowledge.
    """
    parts = []

    if detected.get("dietary_restrictions"):
        restrictions = ", ".join(detected["dietary_restrictions"])
        parts.append(f"I'll remember you're {restrictions}")

    if detected.get("allergies"):
        allergies = ", ".join(detected["allergies"])
        parts.append(f"I've noted your {allergies} allergy - I'll flag this on all orders")

    if detected.get("favorite_cuisines"):
        cuisines = ", ".join(detected["favorite_cuisines"])
        parts.append(f"Got it, you like {cuisines} food")

    if detected.get("disliked_cuisines"):
        cuisines = ", ".join(detected["disliked_cuisines"])
        parts.append(f"Noted, I'll avoid {cuisines} options")

    if detected.get("spice_preference"):
        pref = detected["spice_preference"]
        if pref == "none":
            parts.append("I'll make sure to suggest non-spicy options")
        elif pref in ("hot", "extra_hot"):
            parts.append("I'll look for spicy options when possible")

    if parts:
        return ". ".join(parts) + " for future orders."

    return ""
