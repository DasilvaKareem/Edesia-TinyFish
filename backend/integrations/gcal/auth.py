"""Google Calendar OAuth2 flow and credential management."""

import os
import logging
from typing import Optional
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from lib.firebase import get_db
from firebase_admin import firestore

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


def get_auth_url(user_id: str, redirect_uri: str) -> str:
    """Generate Google OAuth2 authorization URL.

    Args:
        user_id: Firebase user ID (stored in state param for callback).
        redirect_uri: OAuth callback URL.

    Returns:
        Authorization URL to redirect the user to.
    """
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=user_id,
    )
    return auth_url


async def handle_oauth_callback(code: str, user_id: str, redirect_uri: str) -> dict:
    """Exchange authorization code for tokens and store in Firestore.

    Args:
        code: Authorization code from Google.
        user_id: Firebase user ID.
        redirect_uri: Must match the one used in get_auth_url.

    Returns:
        Dict with success status.
    """
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)

    credentials = flow.credentials

    db = get_db()
    db.collection("users").document(user_id).update({
        "gcalTokens": {
            "accessToken": credentials.token,
            "refreshToken": credentials.refresh_token,
            "tokenExpiry": credentials.expiry.isoformat() if credentials.expiry else None,
            "scopes": list(credentials.scopes) if credentials.scopes else SCOPES,
        },
        "gcalConnected": True,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    })

    return {"status": "connected", "user_id": user_id}


async def get_credentials(user_id: str) -> Optional[Credentials]:
    """Load stored Google credentials, refreshing if expired.

    Args:
        user_id: Firebase user ID.

    Returns:
        Google Credentials object, or None if not connected.
    """
    db = get_db()
    doc = db.collection("users").document(user_id).get()

    if not doc.exists:
        return None

    data = doc.to_dict()
    tokens = data.get("gcalTokens")
    if not tokens:
        return None

    creds = Credentials(
        token=tokens.get("accessToken"),
        refresh_token=tokens.get("refreshToken"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        scopes=tokens.get("scopes", SCOPES),
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())

        # Update stored tokens
        db.collection("users").document(user_id).update({
            "gcalTokens.accessToken": creds.token,
            "gcalTokens.tokenExpiry": creds.expiry.isoformat() if creds.expiry else None,
        })

    return creds


async def disconnect(user_id: str) -> bool:
    """Revoke Google Calendar tokens and mark as disconnected.

    Args:
        user_id: Firebase user ID.

    Returns:
        True if disconnected successfully.
    """
    db = get_db()

    try:
        creds = await get_credentials(user_id)
        if creds and creds.token:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": creds.token},
                )
    except Exception as e:
        logger.warning(f"Token revocation failed (non-critical): {e}")

    db.collection("users").document(user_id).update({
        "gcalTokens": firestore.DELETE_FIELD,
        "gcalConnected": False,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    })

    return True
