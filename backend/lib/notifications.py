"""Notification service for order status updates."""

import os
import httpx
from typing import Optional
from datetime import datetime


class NotificationService:
    """Handle push, Slack, and in-chat notifications for order status."""

    def __init__(self):
        # Configure notification channels
        self.push_enabled = bool(os.getenv("PUSH_NOTIFICATION_URL"))
        self.push_url = os.getenv("PUSH_NOTIFICATION_URL")
        self.push_token = os.getenv("PUSH_NOTIFICATION_TOKEN")

        # Slack client (lazy-initialized)
        self._slack_client = None

    def _get_slack_client(self, team_id: Optional[str] = None):
        """Get Slack WebClient, optionally for a specific workspace.

        For multi-workspace OAuth, looks up the bot token from Firestore.
        Falls back to SLACK_BOT_TOKEN env var for backward compat.
        """
        if team_id:
            try:
                from integrations.slack.oauth_store import FirestoreInstallationStore
                store = FirestoreInstallationStore()
                installation = store.find_installation(team_id=team_id)
                if installation and installation.bot_token:
                    from slack_sdk.web.async_client import AsyncWebClient
                    return AsyncWebClient(token=installation.bot_token)
            except Exception:
                pass

        if self._slack_client is None:
            slack_token = os.getenv("SLACK_BOT_TOKEN")
            if slack_token:
                from slack_sdk.web.async_client import AsyncWebClient
                self._slack_client = AsyncWebClient(token=slack_token)
        return self._slack_client

    @property
    def slack_enabled(self) -> bool:
        return bool(os.getenv("SLACK_BOT_TOKEN") or os.getenv("SLACK_CLIENT_ID"))

    async def send_push(
        self,
        user_id: str,
        title: str,
        message: str,
        data: Optional[dict] = None,
    ) -> bool:
        """
        Send a push notification to a user.

        Args:
            user_id: User ID to notify
            title: Notification title
            message: Notification body
            data: Optional additional data

        Returns:
            True if sent successfully
        """
        if not self.push_enabled:
            return False

        payload = {
            "user_id": user_id,
            "title": title,
            "body": message,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.push_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.push_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0,
                )
                return response.status_code in [200, 201, 202]
        except Exception:
            return False

    def format_order_status_message(self, status: str, order_data: dict) -> tuple[str, str]:
        """
        Format order status for notification.

        Args:
            status: DoorDash status (dasher_confirmed, picked_up, dropped_off, etc.)
            order_data: Order details

        Returns:
            Tuple of (title, message)
        """
        vendor_name = order_data.get("vendor_name", "your restaurant")
        tracking_url = order_data.get("tracking_url", "")

        status_messages = {
            "created": (
                "Order Placed",
                f"Your order from {vendor_name} has been placed."
            ),
            "confirmed": (
                "Order Confirmed",
                f"{vendor_name} has confirmed your order."
            ),
            "dasher_confirmed": (
                "Driver Assigned",
                f"A driver has been assigned to pick up your order from {vendor_name}."
            ),
            "dasher_confirmed_pickup_arrival": (
                "Driver Arriving",
                f"Your driver is arriving at {vendor_name}."
            ),
            "picked_up": (
                "Order Picked Up",
                f"Your order from {vendor_name} is on the way!"
            ),
            "dasher_confirmed_dropoff_arrival": (
                "Driver Nearby",
                "Your driver is almost at your location."
            ),
            "dropped_off": (
                "Order Delivered",
                f"Your order from {vendor_name} has been delivered. Enjoy!"
            ),
            "cancelled": (
                "Order Cancelled",
                f"Your order from {vendor_name} has been cancelled."
            ),
        }

        title, message = status_messages.get(
            status,
            ("Order Update", f"Your order from {vendor_name} has been updated.")
        )

        if tracking_url and status not in ["dropped_off", "cancelled"]:
            message += f" Track: {tracking_url}"

        return title, message

    async def send_slack_message(
        self,
        channel_id: str,
        blocks: list,
        text: str = "",
        thread_ts: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> bool:
        """Post a message to a Slack channel.

        Args:
            channel_id: Slack channel ID.
            blocks: Block Kit blocks.
            text: Fallback text for notifications.
            thread_ts: Optional thread timestamp to reply in a thread.
            team_id: Workspace ID for multi-workspace token lookup.

        Returns:
            True if sent successfully.
        """
        client = self._get_slack_client(team_id=team_id)
        if not client:
            return False

        try:
            kwargs = {
                "channel": channel_id,
                "blocks": blocks,
                "text": text or "Edesia update",
            }
            if thread_ts:
                kwargs["thread_ts"] = thread_ts

            await client.chat_postMessage(**kwargs)
            return True
        except Exception as e:
            print(f"Slack message failed: {e}")
            return False

    async def update_slack_message(
        self,
        channel_id: str,
        message_ts: str,
        blocks: list,
        text: str = "",
    ) -> bool:
        """Update an existing Slack message (for poll results, tracking).

        Args:
            channel_id: Slack channel ID.
            message_ts: Timestamp of the message to update.
            blocks: New Block Kit blocks.
            text: New fallback text.

        Returns:
            True if updated successfully.
        """
        client = self._get_slack_client()
        if not client:
            return False

        try:
            await client.chat_update(
                channel=channel_id,
                ts=message_ts,
                blocks=blocks,
                text=text or "Edesia update",
            )
            return True
        except Exception as e:
            print(f"Slack message update failed: {e}")
            return False

    async def send_slack_dm(
        self,
        slack_user_id: str,
        text: str,
        blocks: Optional[list] = None,
    ) -> bool:
        """Send a direct message to a Slack user.

        Args:
            slack_user_id: Slack user ID to DM.
            text: Message text.
            blocks: Optional Block Kit blocks.

        Returns:
            True if sent successfully.
        """
        client = self._get_slack_client()
        if not client:
            return False

        try:
            # Open a DM channel with the user
            result = await client.conversations_open(users=[slack_user_id])
            dm_channel = result["channel"]["id"]

            kwargs = {"channel": dm_channel, "text": text}
            if blocks:
                kwargs["blocks"] = blocks

            await client.chat_postMessage(**kwargs)
            return True
        except Exception as e:
            print(f"Slack DM failed: {e}")
            return False

    async def notify_slack_order_status(
        self,
        slack_context: dict,
        status: str,
        order_data: dict,
    ) -> bool:
        """Send order status update to Slack channel.

        Args:
            slack_context: Serialized SlackContext dict.
            status: DoorDash delivery status.
            order_data: Order details.

        Returns:
            True if notification sent.
        """
        if not slack_context or not self.slack_enabled:
            return False

        from integrations.slack.messages import build_tracking_update_blocks, build_receipt_blocks

        channel_id = slack_context.get("channel_id")
        thread_ts = slack_context.get("thread_ts")
        finance_channel_id = slack_context.get("finance_channel_id")
        team_id = slack_context.get("team_id")

        if not channel_id:
            return False

        # Post tracking update to the order channel
        blocks = build_tracking_update_blocks(status, order_data)
        await self.send_slack_message(channel_id, blocks, thread_ts=thread_ts, team_id=team_id)

        # On delivery, post receipt to finance channel
        if status == "dropped_off" and finance_channel_id:
            receipt_blocks = build_receipt_blocks(order_data)
            await self.send_slack_message(finance_channel_id, receipt_blocks, text="Order receipt", team_id=team_id)

        return True

    async def notify_order_status(
        self,
        user_id: str,
        status: str,
        order_data: dict,
    ) -> bool:
        """
        Send order status notification to user.

        Args:
            user_id: User to notify
            status: Order status
            order_data: Order details

        Returns:
            True if notification sent
        """
        title, message = self.format_order_status_message(status, order_data)

        return await self.send_push(
            user_id=user_id,
            title=title,
            message=message,
            data={
                "type": "order_status",
                "status": status,
                "order_id": order_data.get("order_id"),
                "external_delivery_id": order_data.get("external_delivery_id"),
            }
        )


# Global notification service instance
notification_service = NotificationService()


def get_status_summary_for_chat(order_updates: list[dict]) -> str:
    """
    Generate a status summary to prepend to chat responses.

    Args:
        order_updates: List of recent order status updates

    Returns:
        Formatted string for chat display
    """
    if not order_updates:
        return ""

    summaries = []
    for update in order_updates:
        status = update.get("status")
        vendor = update.get("vendor_name", "your order")
        timestamp = update.get("timestamp", "")

        status_text = {
            "dasher_confirmed": f"A driver was assigned for {vendor}",
            "picked_up": f"Your order from {vendor} was picked up",
            "dropped_off": f"Your order from {vendor} was delivered",
            "cancelled": f"Your order from {vendor} was cancelled",
        }.get(status, f"Status update for {vendor}: {status}")

        summaries.append(f"- {status_text}")

    if summaries:
        return "**Order Updates:**\n" + "\n".join(summaries) + "\n\n---\n\n"

    return ""
