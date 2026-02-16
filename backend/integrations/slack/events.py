"""Slack event handlers for @mentions and direct messages."""

import logging
from slack_bolt import App

logger = logging.getLogger(__name__)


def register_events(app: App):
    """Register all event handlers with the Bolt app."""

    @app.event("app_mention")
    async def handle_app_mention(event, client, say):
        """Handle @edesia mentions in channels.

        Treats the mention text as a chat message to the agent.
        """
        channel_id = event["channel"]
        slack_user_id = event["user"]
        text = event.get("text", "")
        team_id = event.get("team", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        # Strip the bot mention from the text (e.g., "<@U123ABC> order lunch" → "order lunch")
        import re
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()

        if not text:
            await client.chat_postMessage(
                channel=channel_id,
                text="How can I help? Try something like: `@edesia order lunch for 10 people tomorrow`",
                thread_ts=thread_ts,
            )
            return

        from integrations.slack.session import get_or_create_session, save_slack_context, get_linked_firebase_user, get_installation
        from integrations.slack.agent_bridge import invoke_agent_for_slack
        from models.integrations import SlackContext

        session_id, firebase_user_id = await get_or_create_session(
            team_id, channel_id, slack_user_id
        )

        context = SlackContext(
            team_id=team_id,
            channel_id=channel_id,
            user_id=slack_user_id,
            firebase_user_id=firebase_user_id,
            thread_ts=thread_ts,
        )

        installation = await get_installation(team_id)
        if installation:
            context.finance_channel_id = installation.get("financeChannelId")

        await save_slack_context(session_id, context)

        await invoke_agent_for_slack(
            session_id=session_id,
            user_message=text,
            slack_context=context,
            client=client,
            thread_ts=thread_ts,
        )

    @app.event("message")
    async def handle_message(event, client):
        """Handle direct messages to the bot.

        Only handles DMs (channel_type == 'im'). Channel messages
        are handled via app_mention.
        """
        # Only handle DMs, not channel messages
        if event.get("channel_type") != "im":
            return

        # Skip bot messages to avoid loops
        if event.get("bot_id") or event.get("subtype"):
            return

        channel_id = event["channel"]
        slack_user_id = event["user"]
        text = event.get("text", "").strip()
        team_id = event.get("team", "")

        if not text:
            return

        from integrations.slack.session import get_or_create_session, save_slack_context, get_linked_firebase_user
        from integrations.slack.agent_bridge import invoke_agent_for_slack
        from models.integrations import SlackContext

        session_id, firebase_user_id = await get_or_create_session(
            team_id, channel_id, slack_user_id
        )

        context = SlackContext(
            team_id=team_id,
            channel_id=channel_id,
            user_id=slack_user_id,
            firebase_user_id=firebase_user_id,
        )

        await save_slack_context(session_id, context)

        await invoke_agent_for_slack(
            session_id=session_id,
            user_message=text,
            slack_context=context,
            client=client,
        )
