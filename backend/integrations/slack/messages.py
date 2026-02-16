"""Block Kit message builders for Slack interactive messages."""

from typing import Optional
from models.orders import VendorOption, FoodOrderContext, OrderItem


def build_vendor_options_blocks(vendors: list[VendorOption], session_id: str) -> list[dict]:
    """Build Block Kit blocks for vendor selection cards.

    Each vendor gets a section with info and a 'Select' button.
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Restaurant Options", "emoji": True},
        },
        {"type": "divider"},
    ]

    for i, vendor in enumerate(vendors):
        rating = f"{vendor.rating}/5" if vendor.rating else "N/A"
        price = vendor.price_level or ""
        categories = ", ".join(vendor.categories[:3]) if vendor.categories else ""
        distance = f" | {vendor.distance:.1f} mi" if vendor.distance else ""

        text = f"*{i + 1}. {vendor.name}* {price}\n{rating} | {categories}{distance}"
        if vendor.address:
            text += f"\n{vendor.address}"

        section = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Select"},
                "action_id": f"vendor_select_{vendor.vendor_id}",
                "value": vendor.vendor_id,
            },
        }

        if vendor.image_url:
            section["accessory"] = {
                "type": "image",
                "image_url": vendor.image_url,
                "alt_text": vendor.name,
            }
            # Move button to an actions block after the section
            blocks.append(section)
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": f"Select {vendor.name}"},
                        "action_id": f"vendor_select_{vendor.vendor_id}",
                        "value": vendor.vendor_id,
                    }
                ],
            })
        else:
            blocks.append(section)

        blocks.append({"type": "divider"})

    return blocks


def build_order_summary_blocks(food_order: FoodOrderContext, action_id: str) -> list[dict]:
    """Build Block Kit blocks for an order summary with Approve/Reject buttons."""
    vendor_name = food_order.selected_vendor.name if food_order.selected_vendor else "Unknown"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Order from {vendor_name}"},
        },
        {"type": "divider"},
    ]

    # Items
    if food_order.menu_items:
        items_text = ""
        for item in food_order.menu_items:
            items_text += f"  {item.quantity}x {item.name} — ${item.price * item.quantity:.2f}\n"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Items:*\n{items_text}"},
        })

    # Pricing breakdown
    pricing_parts = []
    if food_order.subtotal is not None:
        pricing_parts.append(f"Subtotal: ${food_order.subtotal:.2f}")
    if food_order.tax is not None:
        pricing_parts.append(f"Tax: ${food_order.tax:.2f}")
    if food_order.delivery_fee is not None:
        pricing_parts.append(f"Delivery: ${food_order.delivery_fee:.2f}")
    if food_order.service_fee is not None:
        pricing_parts.append(f"Service fee: ${food_order.service_fee:.2f}")
    if food_order.total is not None:
        pricing_parts.append(f"*Total: ${food_order.total:.2f}*")
        if food_order.headcount:
            per_person = food_order.total / food_order.headcount
            pricing_parts.append(f"(${per_person:.2f}/person for {food_order.headcount} people)")

    if pricing_parts:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(pricing_parts)},
        })

    # Delivery info
    delivery_parts = []
    if food_order.delivery_address:
        delivery_parts.append(f"Delivering to: {food_order.delivery_address}")
    if food_order.event_date:
        delivery_parts.append(f"Date: {food_order.event_date}")
    if food_order.event_time:
        delivery_parts.append(f"Time: {food_order.event_time}")

    if delivery_parts:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": " | ".join(delivery_parts)}],
        })

    blocks.append({"type": "divider"})

    # Approve / Reject buttons
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Approve Order"},
                "style": "primary",
                "action_id": "order_approve",
                "value": action_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Reject"},
                "style": "danger",
                "action_id": "order_reject",
                "value": action_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Modify"},
                "action_id": "order_modify",
                "value": action_id,
            },
        ],
    })

    return blocks


def build_poll_blocks(poll_id: str, question: str, options: list[dict]) -> list[dict]:
    """Build Block Kit blocks for an interactive Slack poll.

    Each option is a button. Votes update the message in-place.
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": question},
        },
        {"type": "divider"},
    ]

    # Option buttons
    elements = []
    for opt in options:
        votes = opt.get("votes", 0)
        label = opt["text"] if votes == 0 else f"{opt['text']} ({votes})"
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": label[:75]},  # Slack limit
            "action_id": f"poll_vote_{opt['option_id']}",
            "value": f"{poll_id}:{opt['option_id']}",
        })

    # Slack allows max 25 elements per actions block, split if needed
    for i in range(0, len(elements), 5):
        blocks.append({
            "type": "actions",
            "elements": elements[i:i + 5],
        })

    # Vote count context
    total_votes = sum(opt.get("votes", 0) for opt in options)
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"{total_votes} vote{'s' if total_votes != 1 else ''} so far"}],
    })

    return blocks


def build_tracking_update_blocks(status: str, order_data: dict) -> list[dict]:
    """Build Block Kit blocks for delivery tracking status updates."""
    vendor_name = order_data.get("vendor_name", "your restaurant")
    tracking_url = order_data.get("tracking_url", "")

    status_emoji = {
        "created": ":receipt:",
        "confirmed": ":white_check_mark:",
        "dasher_confirmed": ":car:",
        "dasher_confirmed_pickup_arrival": ":round_pushpin:",
        "picked_up": ":package:",
        "dasher_confirmed_dropoff_arrival": ":house:",
        "dropped_off": ":tada:",
        "cancelled": ":x:",
    }

    status_text = {
        "created": f"Order from *{vendor_name}* has been placed.",
        "confirmed": f"*{vendor_name}* confirmed your order.",
        "dasher_confirmed": f"A driver has been assigned for your *{vendor_name}* order.",
        "picked_up": f"Your order from *{vendor_name}* has been picked up and is on the way!",
        "dropped_off": f"Your order from *{vendor_name}* has been delivered!",
        "cancelled": f"Your order from *{vendor_name}* has been cancelled.",
    }

    emoji = status_emoji.get(status, ":bell:")
    text = status_text.get(status, f"Order update from *{vendor_name}*: {status}")

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{emoji} {text}"},
        },
    ]

    if tracking_url and status not in ("dropped_off", "cancelled"):
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Track Delivery"},
                    "url": tracking_url,
                    "action_id": "track_delivery",
                },
            ],
        })

    return blocks


def build_receipt_blocks(order_data: dict) -> list[dict]:
    """Build Block Kit blocks for a receipt posted to the finance channel."""
    vendor = order_data.get("vendor_name", "Unknown")
    total = order_data.get("total", 0)
    headcount = order_data.get("headcount", 0)
    date = order_data.get("date", "")
    items = order_data.get("items", [])

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Receipt: {vendor}"},
        },
        {"type": "divider"},
    ]

    # Items summary
    if items:
        items_text = ""
        for item in items[:15]:  # Cap at 15 items for readability
            name = item.get("name", "")
            qty = item.get("quantity", 1)
            price = item.get("price", 0)
            items_text += f"  {qty}x {name} — ${price * qty:.2f}\n"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Items:*\n{items_text}"},
        })

    # Totals
    per_person = total / headcount if headcount > 0 else total
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*Total:*\n${total:.2f}"},
            {"type": "mrkdwn", "text": f"*Per Person:*\n${per_person:.2f}"},
            {"type": "mrkdwn", "text": f"*Headcount:*\n{headcount}"},
            {"type": "mrkdwn", "text": f"*Date:*\n{date}"},
        ],
    })

    blocks.append({"type": "divider"})

    return blocks


def agent_response_to_blocks(text: str) -> list[dict]:
    """Convert a plain-text agent response into Block Kit sections.

    Used when the agent responds with markdown text that needs to be
    posted to Slack as Block Kit blocks.
    """
    # Split long text into 3000-char chunks (Slack section text limit)
    chunks = []
    while text:
        if len(text) <= 3000:
            chunks.append(text)
            break
        # Find a good break point
        break_at = text.rfind("\n", 0, 3000)
        if break_at == -1:
            break_at = 3000
        chunks.append(text[:break_at])
        text = text[break_at:].lstrip("\n")

    blocks = []
    for chunk in chunks:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": chunk},
        })

    return blocks
