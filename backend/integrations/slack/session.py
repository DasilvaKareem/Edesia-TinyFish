"""Manage Slack <-> LangGraph session mapping via Firestore."""

import uuid
import logging
from typing import Optional
from datetime import datetime

from lib.firebase import get_db
from firebase_admin import firestore
from models.integrations import SlackContext, SlackSession, SlackUserLink

logger = logging.getLogger(__name__)


async def get_or_create_session(
    team_id: str,
    channel_id: str,
    slack_user_id: str,
) -> tuple[str, Optional[str]]:
    """Get an existing LangGraph session for a Slack channel, or create one.

    Args:
        team_id: Slack workspace ID.
        channel_id: Slack channel/DM ID.
        slack_user_id: Slack user who triggered the interaction.

    Returns:
        Tuple of (session_id, firebase_user_id or None).
    """
    db = get_db()
    doc_id = f"{team_id}_{channel_id}"
    session_ref = db.collection("slack_sessions").document(doc_id)

    doc = session_ref.get()
    if doc.exists:
        data = doc.to_dict()
        # Update last_active
        session_ref.update({"lastActive": firestore.SERVER_TIMESTAMP})
        return data["sessionId"], data.get("firebaseUserId")

    # Create new session
    session_id = str(uuid.uuid4())
    firebase_user_id = await get_linked_firebase_user(slack_user_id)

    session_ref.set({
        "teamId": team_id,
        "channelId": channel_id,
        "sessionId": session_id,
        "slackUserId": slack_user_id,
        "firebaseUserId": firebase_user_id,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "lastActive": firestore.SERVER_TIMESTAMP,
    })

    return session_id, firebase_user_id


async def reset_session(team_id: str, channel_id: str, slack_user_id: str) -> str:
    """Create a fresh session for a Slack channel (e.g., new /lunch command).

    Returns:
        New session_id.
    """
    db = get_db()
    doc_id = f"{team_id}_{channel_id}"
    session_ref = db.collection("slack_sessions").document(doc_id)

    session_id = str(uuid.uuid4())
    firebase_user_id = await get_linked_firebase_user(slack_user_id)

    session_ref.set({
        "teamId": team_id,
        "channelId": channel_id,
        "sessionId": session_id,
        "slackUserId": slack_user_id,
        "firebaseUserId": firebase_user_id,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "lastActive": firestore.SERVER_TIMESTAMP,
    })

    return session_id


async def save_slack_context(session_id: str, context: SlackContext):
    """Persist Slack context for response routing.

    Stored alongside the session so webhooks (DoorDash, Stripe)
    can route updates back to the correct Slack channel.
    """
    db = get_db()
    doc_id = f"{context.team_id}_{context.channel_id}"
    db.collection("slack_sessions").document(doc_id).update({
        "slackContext": context.model_dump(),
    })


async def get_slack_context_for_session(session_id: str) -> Optional[SlackContext]:
    """Look up Slack context by LangGraph session_id.

    Used by webhooks to find the right Slack channel for status updates.
    """
    db = get_db()
    docs = db.collection("slack_sessions") \
             .where("sessionId", "==", session_id) \
             .limit(1).stream()

    for doc in docs:
        data = doc.to_dict()
        ctx = data.get("slackContext")
        if ctx:
            return SlackContext(**ctx)

    return None


async def get_slack_context_for_order(order_data: dict) -> Optional[SlackContext]:
    """Look up Slack context from order data.

    Orders store the session_id, which links back to the Slack session.
    """
    session_id = order_data.get("sessionId")
    if not session_id:
        return None
    return await get_slack_context_for_session(session_id)


# ==================== User Linking ====================

async def link_slack_user(slack_user_id: str, firebase_user_id: str, team_id: str):
    """Link a Slack user to a Firebase/Edesia account."""
    db = get_db()
    db.collection("slack_user_links").document(slack_user_id).set({
        "firebaseUserId": firebase_user_id,
        "teamId": team_id,
        "linkedAt": firestore.SERVER_TIMESTAMP,
    })


async def get_linked_firebase_user(slack_user_id: str) -> Optional[str]:
    """Get the Firebase user ID linked to a Slack user."""
    db = get_db()
    doc = db.collection("slack_user_links").document(slack_user_id).get()
    if doc.exists:
        return doc.to_dict().get("firebaseUserId")
    return None


# ==================== Installation ====================

async def get_installation(team_id: str) -> Optional[dict]:
    """Get Slack workspace installation config."""
    db = get_db()
    doc = db.collection("slack_installations").document(team_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


async def save_installation(team_id: str, data: dict):
    """Save Slack workspace installation."""
    db = get_db()
    data["createdAt"] = firestore.SERVER_TIMESTAMP
    db.collection("slack_installations").document(team_id).set(data, merge=True)
