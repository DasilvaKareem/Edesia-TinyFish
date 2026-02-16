"""Slack Bolt app setup for Edesia (multi-workspace OAuth mode)."""

import os
import logging
from slack_bolt import App
from slack_bolt.adapter.starlette import SlackRequestHandler
from slack_bolt.oauth.oauth_settings import OAuthSettings

from integrations.slack.oauth_store import (
    FirestoreInstallationStore,
    FirestoreOAuthStateStore,
)

logger = logging.getLogger(__name__)

installation_store = FirestoreInstallationStore()
state_store = FirestoreOAuthStateStore(expiration_seconds=600)

# Multi-workspace OAuth mode: Bolt looks up bot tokens per-workspace
# from Firestore via the installation store.
slack_app = App(
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET", ""),
    oauth_settings=OAuthSettings(
        client_id=os.environ.get("SLACK_CLIENT_ID", ""),
        client_secret=os.environ.get("SLACK_CLIENT_SECRET", ""),
        scopes=[
            "chat:write",
            "commands",
            "app_mentions:read",
            "im:history",
            "im:write",
            "channels:history",
        ],
        installation_store=installation_store,
        state_store=state_store,
        install_path="/slack/install",
        redirect_uri_path="/slack/oauth/callback",
    ),
    process_before_response=True,  # Required for serverless
)

# Starlette adapter for FastAPI integration
slack_handler = SlackRequestHandler(slack_app)


def register_handlers():
    """Register all Slack command, action, and event handlers.

    Called once during app startup to wire up the Bolt app.
    """
    from integrations.slack.commands import register_commands
    from integrations.slack.actions import register_actions
    from integrations.slack.events import register_events

    register_commands(slack_app)
    register_actions(slack_app)
    register_events(slack_app)

    logger.info("Slack handlers registered")
