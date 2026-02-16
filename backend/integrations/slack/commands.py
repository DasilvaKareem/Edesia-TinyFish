"""Slash command handlers for Slack (/lunch, /poll)."""

import logging
from slack_bolt import App

from integrations.slack.session import (
    reset_session,
    save_slack_context,
    get_linked_firebase_user,
    get_installation,
)
from integrations.slack.messages import build_poll_blocks, agent_response_to_blocks
from integrations.slack.agent_bridge import invoke_agent_for_slack
from models.integrations import SlackContext

logger = logging.getLogger(__name__)


def register_commands(app: App):
    """Register all slash command handlers with the Bolt app."""

    @app.command("/lunch")
    async def handle_lunch(ack, command, say, client):
        """Handle /lunch command — start a food ordering flow.

        Usage:
            /lunch                    → Start ordering with defaults
            /lunch 15 people tomorrow → Parse headcount and date
            /lunch pizza for 10       → Parse cuisine and headcount
        """
        await ack()

        team_id = command["team_id"]
        channel_id = command["channel_id"]
        slack_user_id = command["user_id"]
        text = command.get("text", "").strip()

        # Create a fresh session for this ordering flow
        session_id = await reset_session(team_id, channel_id, slack_user_id)

        # Build Slack context for response routing
        context = SlackContext(
            team_id=team_id,
            channel_id=channel_id,
            user_id=slack_user_id,
            firebase_user_id=await get_linked_firebase_user(slack_user_id),
        )

        # Load workspace config for finance channel
        installation = await get_installation(team_id)
        if installation:
            context.finance_channel_id = installation.get("financeChannelId")

        await save_slack_context(session_id, context)

        # Post initial "working on it" message
        result = await client.chat_postMessage(
            channel=channel_id,
            text="On it! Starting your lunch order...",
        )

        # Store message_ts for future updates
        context.message_ts = result["ts"]
        context.thread_ts = result["ts"]
        await save_slack_context(session_id, context)

        # Build the user message for the agent
        if text:
            user_message = f"Order lunch: {text}"
        else:
            user_message = "Order lunch for the team"

        # Invoke the LangGraph agent and post response to Slack
        await invoke_agent_for_slack(
            session_id=session_id,
            user_message=user_message,
            slack_context=context,
            client=client,
        )

    @app.command("/poll")
    async def handle_poll(ack, command, say, client):
        """Handle /poll command — create an interactive Slack poll.

        Usage:
            /poll What should we order? | Pizza | Sushi | Tacos | Salads
        """
        await ack()

        text = command.get("text", "").strip()
        channel_id = command["channel_id"]

        if not text or "|" not in text:
            await client.chat_postMessage(
                channel=channel_id,
                text="Usage: `/poll Question? | Option 1 | Option 2 | Option 3`",
            )
            return

        parts = [p.strip() for p in text.split("|")]
        question = parts[0]
        options = [p for p in parts[1:] if p]

        if len(options) < 2:
            await client.chat_postMessage(
                channel=channel_id,
                text="A poll needs at least 2 options. Separate them with `|`.",
            )
            return

        if len(options) > 10:
            await client.chat_postMessage(
                channel=channel_id,
                text="Maximum 10 options per poll.",
            )
            return

        # Create poll in Firestore using existing poll tool
        from tools.poll import create_poll
        poll_result = create_poll.invoke({
            "question": question,
            "options": options,
            "deadline_hours": 24,
        })

        if "error" in poll_result:
            await client.chat_postMessage(
                channel=channel_id,
                text=f"Failed to create poll: {poll_result['error']}",
            )
            return

        poll_id = poll_result["poll_id"]

        # Build Block Kit poll with interactive buttons
        from lib.firebase import get_poll_doc
        poll_data = get_poll_doc(poll_id)

        blocks = build_poll_blocks(poll_id, question, poll_data["options"])

        # Post the poll as an interactive message
        result = await client.chat_postMessage(
            channel=channel_id,
            text=question,  # Fallback for notifications
            blocks=blocks,
        )

        # Store the message_ts on the poll so we can update it on votes
        from lib.firebase import update_poll_doc
        update_poll_doc(poll_id, {
            "slackChannelId": channel_id,
            "slackMessageTs": result["ts"],
            "slackTeamId": command["team_id"],
        })
