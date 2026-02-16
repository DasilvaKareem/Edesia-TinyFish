"""Interactive action handlers for Slack Block Kit buttons and modals."""

import logging
from slack_bolt import App

logger = logging.getLogger(__name__)


def register_actions(app: App):
    """Register all Block Kit action handlers with the Bolt app."""

    # ==================== Vendor Selection ====================

    @app.action({"action_id": "vendor_select_.*"})
    async def handle_vendor_select(ack, action, body, client):
        """Handle vendor selection from search results.

        When a user clicks 'Select' on a vendor card, forward the
        selection to the agent as a follow-up message.
        """
        await ack()

        vendor_id = action["value"]
        channel_id = body["channel"]["id"]
        team_id = body["team"]["id"]
        slack_user_id = body["user"]["id"]

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
            thread_ts=body.get("message", {}).get("ts"),
        )

        # Tell the agent which vendor was selected
        await invoke_agent_for_slack(
            session_id=session_id,
            user_message=f"I'll go with vendor {vendor_id}",
            slack_context=context,
            client=client,
            thread_ts=context.thread_ts,
        )

    # ==================== Order Approval ====================

    @app.action("order_approve")
    async def handle_order_approve(ack, action, body, client):
        """Handle order approval button click.

        Delegates to the existing /approve endpoint logic.
        """
        await ack()

        action_id = action["value"]
        channel_id = body["channel"]["id"]
        slack_user_id = body["user"]["id"]
        message_ts = body["message"]["ts"]

        try:
            import modal
            actions_dict = modal.Dict.from_name("edesia-actions", create_if_missing=True)
            stored_action = actions_dict.get(action_id)

            if not stored_action:
                await client.chat_postMessage(
                    channel=channel_id,
                    text="This action has expired or already been processed.",
                    thread_ts=message_ts,
                )
                return

            # Check manager approval requirement
            payload = stored_action.get("payload", {})
            if payload.get("requires_manager_approval"):
                manager_slack_id = payload.get("manager_slack_id")
                if manager_slack_id and slack_user_id != manager_slack_id:
                    await client.chat_postMessage(
                        channel=channel_id,
                        text=f"This order requires approval from <@{manager_slack_id}>.",
                        thread_ts=message_ts,
                    )
                    return

            # Execute the approved action using the same logic as /approve
            from integrations.slack.approval import execute_slack_approval
            result = await execute_slack_approval(action_id, stored_action, slack_user_id)

            if result.get("error"):
                await client.chat_postMessage(
                    channel=channel_id,
                    text=f"Approval failed: {result['error']}",
                    thread_ts=message_ts,
                )
            else:
                # Update the original message to show approved status
                await client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text=f"Order approved by <@{slack_user_id}>",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f":white_check_mark: *Order approved* by <@{slack_user_id}>\n{result.get('message', 'Processing...')}",
                            },
                        }
                    ],
                )

        except Exception as e:
            logger.error(f"Order approval failed: {e}", exc_info=True)
            await client.chat_postMessage(
                channel=channel_id,
                text="Failed to process approval. Please try again.",
                thread_ts=message_ts,
            )

    @app.action("order_reject")
    async def handle_order_reject(ack, action, body, client):
        """Handle order rejection button click."""
        await ack()

        action_id = action["value"]
        channel_id = body["channel"]["id"]
        slack_user_id = body["user"]["id"]
        message_ts = body["message"]["ts"]

        try:
            import modal
            actions_dict = modal.Dict.from_name("edesia-actions", create_if_missing=True)
            stored_action = actions_dict.get(action_id)

            if stored_action:
                stored_action["status"] = "rejected"
                stored_action["approved_by"] = slack_user_id
                actions_dict[action_id] = stored_action

            await client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=f"Order rejected by <@{slack_user_id}>",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":x: *Order rejected* by <@{slack_user_id}>",
                        },
                    }
                ],
            )

        except Exception as e:
            logger.error(f"Order rejection failed: {e}", exc_info=True)

    @app.action("order_modify")
    async def handle_order_modify(ack, action, body, client):
        """Handle order modification request — opens a modal or sends to agent."""
        await ack()

        action_id = action["value"]
        channel_id = body["channel"]["id"]
        team_id = body["team"]["id"]
        slack_user_id = body["user"]["id"]
        message_ts = body["message"]["ts"]

        from integrations.slack.session import get_or_create_session
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
            thread_ts=message_ts,
        )

        await invoke_agent_for_slack(
            session_id=session_id,
            user_message="I want to modify this order. Show me the current items so I can make changes.",
            slack_context=context,
            client=client,
            thread_ts=message_ts,
        )

    # ==================== Poll Voting ====================

    @app.action({"action_id": "poll_vote_.*"})
    async def handle_poll_vote(ack, action, body, client):
        """Handle poll vote button click.

        Updates the poll in Firestore and edits the Slack message in-place
        with updated vote counts.
        """
        await ack()

        value = action["value"]  # "poll_id:option_id"
        poll_id, option_id = value.split(":", 1)
        slack_user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        from lib.firebase import get_poll_doc, update_poll_doc
        from integrations.slack.messages import build_poll_blocks

        poll = get_poll_doc(poll_id)
        if not poll:
            return

        # Check if user already voted
        existing_votes = poll.get("votes", [])
        already_voted = any(v.get("voter_id") == slack_user_id for v in existing_votes)

        if already_voted:
            # Change vote: remove old vote, add new
            old_option_id = None
            new_votes = []
            for v in existing_votes:
                if v.get("voter_id") == slack_user_id:
                    old_option_id = v.get("option_id")
                else:
                    new_votes.append(v)

            # Decrement old option
            if old_option_id:
                for opt in poll["options"]:
                    if opt["option_id"] == old_option_id:
                        opt["votes"] = max(0, opt["votes"] - 1)
                        break

            existing_votes = new_votes

        # Increment new option
        for opt in poll["options"]:
            if opt["option_id"] == option_id:
                opt["votes"] = opt.get("votes", 0) + 1
                break

        # Record vote
        from datetime import datetime
        existing_votes.append({
            "voter_id": slack_user_id,
            "option_id": option_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Update Firestore
        update_poll_doc(poll_id, {
            "options": poll["options"],
            "votes": existing_votes,
            "total_votes": sum(o.get("votes", 0) for o in poll["options"]),
        })

        # Rebuild and update the Slack message
        blocks = build_poll_blocks(poll_id, poll["question"], poll["options"])

        await client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=poll["question"],
            blocks=blocks,
        )

    # ==================== Delivery Tracking ====================

    @app.action("track_delivery")
    async def handle_track_delivery(ack, action, body, client):
        """Handle track delivery button — this is a URL button, just acknowledge."""
        await ack()
