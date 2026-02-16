"""Firebase Admin SDK helper for backend operations."""

import os
import json
from typing import Optional
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore

_db = None


def get_db():
    """Get Firestore database client, initializing if needed."""
    global _db

    if _db is not None:
        return _db

    # Initialize Firebase Admin if not already done
    if not firebase_admin._apps:
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if service_account_json:
            cred = credentials.Certificate(json.loads(service_account_json))
            firebase_admin.initialize_app(cred)
        else:
            raise ValueError("FIREBASE_SERVICE_ACCOUNT environment variable not set")

    _db = firestore.client()
    return _db


# ==================== CALL LOGS ====================

async def add_call_log(chat_id: str, order_id: str, call_data: dict) -> str:
    """Add a call log to an order."""
    db = get_db()

    call_ref = db.collection("chats").document(chat_id) \
                 .collection("orders").document(order_id) \
                 .collection("calls").document()

    call_data["createdAt"] = firestore.SERVER_TIMESTAMP
    call_ref.set(call_data)

    return call_ref.id


async def update_call_log(chat_id: str, order_id: str, call_id: str, updates: dict):
    """Update a call log."""
    db = get_db()

    call_ref = db.collection("chats").document(chat_id) \
                 .collection("orders").document(order_id) \
                 .collection("calls").document(call_id)

    call_ref.update(updates)


async def find_call_by_vapi_id(vapi_call_id: str) -> Optional[dict]:
    """Find a call log by Vapi call ID."""
    db = get_db()

    # Query across all calls subcollections
    # Note: This requires a collection group query
    calls = db.collection_group("calls").where("vapiCallId", "==", vapi_call_id).limit(1).stream()

    for call in calls:
        return {
            "id": call.id,
            "path": call.reference.path,
            **call.to_dict()
        }

    return None


# ==================== ORDERS ====================

async def create_order(chat_id: str, order_data: dict) -> str:
    """Create a new order."""
    db = get_db()

    order_ref = db.collection("chats").document(chat_id) \
                  .collection("orders").document()

    order_data["createdAt"] = firestore.SERVER_TIMESTAMP
    order_data["updatedAt"] = firestore.SERVER_TIMESTAMP
    order_ref.set(order_data)

    return order_ref.id


async def update_order(chat_id: str, order_id: str, updates: dict):
    """Update an order."""
    db = get_db()

    order_ref = db.collection("chats").document(chat_id) \
                  .collection("orders").document(order_id)

    updates["updatedAt"] = firestore.SERVER_TIMESTAMP
    order_ref.update(updates)


async def find_order_by_session(chat_id: str, session_id: str) -> Optional[dict]:
    """Find an existing order by session ID (for multi-turn workflows)."""
    db = get_db()

    orders = db.collection("chats").document(chat_id) \
               .collection("orders") \
               .where("sessionId", "==", session_id) \
               .limit(1).stream()

    for doc in orders:
        return {"id": doc.id, **doc.to_dict()}

    return None


async def find_order_by_delivery_id(delivery_id: str) -> Optional[dict]:
    """Find an order by DoorDash delivery ID (collection group query)."""
    db = get_db()

    orders = db.collection_group("orders") \
               .where("deliveryId", "==", delivery_id) \
               .limit(1).stream()

    for doc in orders:
        path_parts = doc.reference.path.split("/")
        chat_id = path_parts[1]  # chats/{chatId}/orders/{orderId}
        return {"id": doc.id, "chatId": chat_id, **doc.to_dict()}

    return None


async def get_order(chat_id: str, order_id: str) -> Optional[dict]:
    """Get an order by ID."""
    db = get_db()

    order_ref = db.collection("chats").document(chat_id) \
                  .collection("orders").document(order_id)

    doc = order_ref.get()
    if doc.exists:
        return {"id": doc.id, **doc.to_dict()}

    return None


# ==================== MESSAGES ====================

async def add_message(chat_id: str, role: str, content: str) -> str:
    """Add a message to a chat."""
    db = get_db()

    msg_ref = db.collection("chats").document(chat_id) \
                .collection("messages").document()

    msg_ref.set({
        "role": role,
        "content": content,
        "createdAt": firestore.SERVER_TIMESTAMP,
    })

    # Update chat's updatedAt
    db.collection("chats").document(chat_id).update({
        "updatedAt": firestore.SERVER_TIMESTAMP
    })

    return msg_ref.id


# ==================== USER PREFERENCES ====================

async def update_user_preferences(user_id: str, preferences: dict) -> bool:
    """Update user food preferences in Firebase.

    Args:
        user_id: The user's Firebase UID.
        preferences: Dict of preference fields to update.

    Returns:
        True if updated successfully, False otherwise.
    """
    if not user_id:
        return False

    db = get_db()
    user_ref = db.collection("users").document(user_id)

    # Map preference field names and prepare update
    update_data = {}

    # Handle dietary restrictions
    if "dietary_restrictions" in preferences:
        update_data["dietaryRestrictions"] = preferences["dietary_restrictions"]

    # Handle allergies
    if "allergies" in preferences:
        update_data["allergies"] = preferences["allergies"]

    # Handle favorite cuisines
    if "favorite_cuisines" in preferences:
        update_data["favoriteCuisines"] = preferences["favorite_cuisines"]

    # Handle disliked cuisines
    if "disliked_cuisines" in preferences:
        update_data["dislikedCuisines"] = preferences["disliked_cuisines"]

    # Handle spice preference
    if "spice_preference" in preferences:
        # Map backend values to frontend values
        spice_map = {
            "none": "Mild",
            "mild": "Mild",
            "medium": "Medium",
            "hot": "Spicy",
            "extra_hot": "Extra Spicy"
        }
        update_data["spicePreference"] = spice_map.get(
            preferences["spice_preference"],
            preferences["spice_preference"]
        )

    # Handle budget
    if "budget_per_person" in preferences:
        update_data["budgetPerPerson"] = preferences["budget_per_person"]

    # Handle addresses
    if "work_address" in preferences:
        addr = preferences["work_address"]
        update_data["workAddress"] = {
            "label": addr.get("label", "work"),
            "rawAddress": addr.get("raw_address", ""),
            "formattedAddress": addr.get("formatted_address", ""),
            "latitude": addr.get("latitude"),
            "longitude": addr.get("longitude"),
            "placeId": addr.get("place_id"),
        }

    if "home_address" in preferences:
        addr = preferences["home_address"]
        update_data["homeAddress"] = {
            "label": addr.get("label", "home"),
            "rawAddress": addr.get("raw_address", ""),
            "formattedAddress": addr.get("formatted_address", ""),
            "latitude": addr.get("latitude"),
            "longitude": addr.get("longitude"),
            "placeId": addr.get("place_id"),
        }

    if not update_data:
        return False

    update_data["updatedAt"] = firestore.SERVER_TIMESTAMP

    try:
        user_ref.update(update_data)
        return True
    except Exception as e:
        print(f"Error updating user preferences: {e}")
        return False


# ==================== INBOUND CALLS ====================

async def save_inbound_call(call_id: str, call_data: dict):
    """Save an inbound call record to the inbound_calls collection."""
    db = get_db()
    call_data["createdAt"] = firestore.SERVER_TIMESTAMP
    db.collection("inbound_calls").document(call_id).set(call_data)


async def find_inbound_calls_by_email(email: str) -> list[dict]:
    """Find inbound call records by caller email, most recent first."""
    db = get_db()
    docs = (
        db.collection("inbound_calls")
        .where("callerEmail", "==", email)
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)
    return results


# ==================== POLLS ====================

def create_poll_doc(poll_id: str, poll_data: dict):
    """Create a poll document in Firestore."""
    db = get_db()
    db.collection("polls").document(poll_id).set(poll_data)


def get_poll_doc(poll_id: str) -> Optional[dict]:
    """Get a poll document from Firestore."""
    db = get_db()
    doc = db.collection("polls").document(poll_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


def update_poll_doc(poll_id: str, updates: dict):
    """Update a poll document in Firestore."""
    db = get_db()
    db.collection("polls").document(poll_id).update(updates)


# ==================== FORMS ====================

def create_form_doc(form_id: str, form_data: dict):
    """Create a form document in Firestore."""
    db = get_db()
    db.collection("forms").document(form_id).set(form_data)


def get_form_doc(form_id: str) -> Optional[dict]:
    """Get a form document from Firestore."""
    db = get_db()
    doc = db.collection("forms").document(form_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


def update_form_doc(form_id: str, updates: dict):
    """Update a form document in Firestore."""
    db = get_db()
    db.collection("forms").document(form_id).update(updates)


async def get_user_preferences(user_id: str) -> Optional[dict]:
    """Get user food preferences from Firebase.

    Args:
        user_id: The user's Firebase UID.

    Returns:
        User preferences dict if found, None otherwise.
    """
    if not user_id:
        return None

    db = get_db()
    user_ref = db.collection("users").document(user_id)

    try:
        doc = user_ref.get()
        if doc.exists:
            data = doc.to_dict()
            # Map Firebase field names to backend field names
            prefs = {
                "dietary_restrictions": data.get("dietaryRestrictions", []),
                "allergies": data.get("allergies", []),
                "favorite_cuisines": data.get("favoriteCuisines", []),
                "disliked_cuisines": data.get("dislikedCuisines", []),
                "spice_preference": data.get("spicePreference", ""),
                "budget_per_person": data.get("budgetPerPerson"),
            }

            # Map address fields
            work_addr = data.get("workAddress")
            if work_addr:
                prefs["work_address"] = {
                    "label": work_addr.get("label", "work"),
                    "raw_address": work_addr.get("rawAddress", ""),
                    "formatted_address": work_addr.get("formattedAddress", ""),
                    "latitude": work_addr.get("latitude"),
                    "longitude": work_addr.get("longitude"),
                    "place_id": work_addr.get("placeId"),
                }

            home_addr = data.get("homeAddress")
            if home_addr:
                prefs["home_address"] = {
                    "label": home_addr.get("label", "home"),
                    "raw_address": home_addr.get("rawAddress", ""),
                    "formatted_address": home_addr.get("formattedAddress", ""),
                    "latitude": home_addr.get("latitude"),
                    "longitude": home_addr.get("longitude"),
                    "place_id": home_addr.get("placeId"),
                }

            return prefs
    except Exception as e:
        print(f"Error getting user preferences: {e}")

    return None
