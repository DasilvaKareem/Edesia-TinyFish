"""Firestore-backed stores for Slack OAuth (multi-workspace install)."""

import uuid
import logging
from typing import Optional
from datetime import datetime, timedelta

from slack_sdk.oauth.installation_store import InstallationStore
from slack_sdk.oauth.installation_store.models.installation import Installation
from slack_sdk.oauth.state_store import OAuthStateStore

logger = logging.getLogger(__name__)


class FirestoreInstallationStore(InstallationStore):
    """Store Slack workspace installations in Firestore."""

    def save(self, installation: Installation) -> None:
        from lib.firebase import get_db

        db = get_db()
        team_id = installation.team_id or installation.enterprise_id or ""
        if not team_id:
            logger.error("Cannot save installation without team_id or enterprise_id")
            return

        doc_ref = db.collection("slack_installations").document(team_id)
        data = {
            "appId": installation.app_id or "",
            "teamId": installation.team_id or "",
            "teamName": installation.team_name or "",
            "enterpriseId": installation.enterprise_id or "",
            "botToken": installation.bot_token or "",
            "botId": installation.bot_id or "",
            "botUserId": installation.bot_user_id or "",
            "botScopes": list(installation.bot_scopes or []),
            "installedBy": installation.user_id or "",
            "installedAt": datetime.utcnow().isoformat(),
            "isEnterpriseInstall": installation.is_enterprise_install or False,
        }

        # merge=True preserves existing fields like financeChannelId
        doc_ref.set(data, merge=True)
        logger.info(f"Saved Slack installation for team {team_id}")

    def find_installation(
        self,
        *,
        enterprise_id: Optional[str] = None,
        team_id: Optional[str] = None,
        user_id: Optional[str] = None,
        is_enterprise_install: Optional[bool] = None,
    ) -> Optional[Installation]:
        from lib.firebase import get_db

        db = get_db()
        doc_id = team_id or enterprise_id
        if not doc_id:
            return None

        doc = db.collection("slack_installations").document(doc_id).get()
        if not doc.exists:
            return None

        data = doc.to_dict()
        return Installation(
            app_id=data.get("appId", ""),
            enterprise_id=data.get("enterpriseId") or None,
            team_id=data.get("teamId", ""),
            team_name=data.get("teamName", ""),
            bot_token=data.get("botToken", ""),
            bot_id=data.get("botId", ""),
            bot_user_id=data.get("botUserId", ""),
            bot_scopes=data.get("botScopes", []),
            user_id=data.get("installedBy", ""),
            is_enterprise_install=data.get("isEnterpriseInstall", False),
        )

    def delete_installation(
        self,
        *,
        enterprise_id: Optional[str] = None,
        team_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        from lib.firebase import get_db

        db = get_db()
        doc_id = team_id or enterprise_id
        if doc_id:
            db.collection("slack_installations").document(doc_id).delete()
            logger.info(f"Deleted Slack installation for {doc_id}")


class FirestoreOAuthStateStore(OAuthStateStore):
    """Store OAuth state tokens in Firestore for CSRF protection."""

    def __init__(self, expiration_seconds: int = 600):
        self.expiration_seconds = expiration_seconds

    def issue(self, *args, **kwargs) -> str:
        from lib.firebase import get_db

        db = get_db()
        state = str(uuid.uuid4())
        db.collection("slack_oauth_states").document(state).set({
            "createdAt": datetime.utcnow().isoformat(),
            "expiresAt": (
                datetime.utcnow() + timedelta(seconds=self.expiration_seconds)
            ).isoformat(),
        })
        return state

    def consume(self, state: str) -> bool:
        from lib.firebase import get_db

        db = get_db()
        doc_ref = db.collection("slack_oauth_states").document(state)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        data = doc.to_dict()
        expires_at = datetime.fromisoformat(data.get("expiresAt", ""))

        # One-time use — delete immediately
        doc_ref.delete()

        if datetime.utcnow() > expires_at:
            return False

        return True
