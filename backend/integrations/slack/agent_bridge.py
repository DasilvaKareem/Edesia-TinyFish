"""Bridge between Slack interactions and the LangGraph agent.

Provides a single entry point for invoking the existing agent from Slack,
using the same graph, checkpointer, and state shape as the web chat endpoint.
"""

import logging
from typing import Optional

from models.integrations import SlackContext
from integrations.slack.messages import (
    agent_response_to_blocks,
    build_order_summary_blocks,
    build_vendor_options_blocks,
)

logger = logging.getLogger(__name__)


async def invoke_agent_for_slack(
    session_id: str,
    user_message: str,
    slack_context: SlackContext,
    client,  # slack_sdk.web.async_client.AsyncWebClient
    thread_ts: Optional[str] = None,
):
    """Invoke the LangGraph agent and post the response to Slack.

    This is the main bridge between Slack and the agent. It:
    1. Loads user preferences (if linked to a Firebase account)
    2. Invokes the graph with the same state shape as /chat
    3. Posts the response as Block Kit messages to Slack
    4. Handles pending actions (posts approve/reject buttons)

    Args:
        session_id: LangGraph thread_id.
        user_message: The user's message text.
        slack_context: Slack routing context.
        client: Slack WebClient for posting messages.
        thread_ts: Optional thread timestamp to reply in a thread.
    """
    from agent import create_agent_graph
    from lib.redis import get_async_checkpointer, get_user_preferences

    user_id = slack_context.firebase_user_id or "anonymous"
    user_preferences = get_user_preferences(user_id) if user_id != "anonymous" else None

    # Load user profile from Firestore if linked
    user_profile = None
    if user_id != "anonymous":
        try:
            from lib.firebase import get_db
            db = get_db()
            user_doc = db.collection("users").document(user_id).get()
            if user_doc.exists:
                user_profile = user_doc.to_dict()
        except Exception as e:
            logger.warning(f"Failed to load user profile: {e}")

    # Determine timezone from user profile or default
    timezone = None
    if user_profile:
        timezone = user_profile.get("timezone", "America/New_York")

    try:
        async with get_async_checkpointer() as checkpointer:
            graph = create_agent_graph(checkpointer=checkpointer)

            config = {
                "configurable": {
                    "thread_id": session_id,
                    "user_id": user_id,
                }
            }

            # Check existing state
            existing_state = await graph.aget_state(config)
            has_existing = (
                existing_state
                and existing_state.values
                and existing_state.values.get("messages")
            )

            if has_existing:
                messages_to_send = [{"role": "user", "content": user_message}]
            else:
                messages_to_send = [{"role": "user", "content": user_message}]

            initial_input = {
                "messages": messages_to_send,
                "user_id": user_id,
                "user_preferences": user_preferences,
                "timezone": timezone,
                "user_profile": user_profile,
                "has_images": False,
                "chat_id": None,  # Slack sessions don't use Firestore chat docs
                "source_channel": "slack",
                "slack_context": slack_context.model_dump(),
            }

            result = await graph.ainvoke(initial_input, config=config)

        # Extract response
        last_message = result.get("messages", [])[-1] if result.get("messages") else None
        response_text = ""
        if last_message:
            response_text = (
                last_message.content
                if hasattr(last_message, "content")
                else last_message.get("content", "")
            )

        pending_actions = result.get("pending_actions", [])

        # Post response to Slack
        post_kwargs = {
            "channel": slack_context.channel_id,
            "text": response_text[:3000],  # Fallback text
        }

        if thread_ts or slack_context.thread_ts:
            post_kwargs["thread_ts"] = thread_ts or slack_context.thread_ts

        # Check if we have vendor options to display as rich cards
        food_order = result.get("food_order")
        cached_vendors = result.get("cached_vendor_search")

        if cached_vendors and isinstance(cached_vendors, dict):
            vendor_options = cached_vendors.get("vendors", [])
            if vendor_options:
                from models.orders import VendorOption
                vendors = []
                for v in vendor_options:
                    if isinstance(v, dict):
                        vendors.append(VendorOption(**v))
                    else:
                        vendors.append(v)
                blocks = build_vendor_options_blocks(vendors, session_id)
                post_kwargs["blocks"] = blocks

        elif pending_actions:
            # Show approve/reject buttons for pending actions
            for action in pending_actions:
                if food_order:
                    from models.orders import FoodOrderContext
                    fo = (
                        FoodOrderContext(**food_order)
                        if isinstance(food_order, dict)
                        else food_order
                    )
                    blocks = build_order_summary_blocks(fo, action.get("action_id", ""))
                    post_kwargs["blocks"] = blocks
                    break
        else:
            # Standard text response → Block Kit sections
            if response_text:
                blocks = agent_response_to_blocks(response_text)
                post_kwargs["blocks"] = blocks

        await client.chat_postMessage(**post_kwargs)

        # Store pending actions in Modal dict for approval lookup
        if pending_actions:
            import modal
            actions_dict = modal.Dict.from_name("edesia-actions", create_if_missing=True)
            for action in pending_actions:
                action["slack_context"] = slack_context.model_dump()
                actions_dict[action["action_id"]] = action

    except Exception as e:
        logger.error(f"Agent invocation failed for Slack: {e}", exc_info=True)
        await client.chat_postMessage(
            channel=slack_context.channel_id,
            text="Something went wrong processing your request. Please try again.",
            thread_ts=thread_ts or slack_context.thread_ts,
        )
