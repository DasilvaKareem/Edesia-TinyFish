"""Approval node for human-in-the-loop confirmation."""

import os
import weave
from langchain_core.messages import AIMessage

from agent.state import AgentState
from agent.prompts.templates import (
    RESERVATION_TEMPLATE,
    CATERING_QUOTE_TEMPLATE,
    POLL_TEMPLATE,
    FOOD_ORDER_TEMPLATE,
)
from models.orders import VendorOption

APPROVAL_BASE_URL = os.environ.get("POLL_BASE_URL", "https://your-modal-app.modal.run")


@weave.op()
def approval_node(state: AgentState) -> dict:
    """
    Generate approval request for pending actions.

    All actions require human approval before execution.
    """
    pending_actions = state.get("pending_actions", [])

    if not pending_actions:
        return {"needs_approval": False}

    # Generate approval messages for each pending action
    approval_messages = []

    for action in pending_actions:
        action_type = action.get("action_type")
        payload = action.get("payload", {})

        if action_type == "reservation":
            msg = RESERVATION_TEMPLATE.format(
                restaurant_name=payload.get("restaurant_name", "Unknown"),
                party_size=payload.get("party_size", "?"),
                date=payload.get("date", "TBD"),
                time=payload.get("time", "TBD"),
                contact_name=payload.get("contact_name", ""),
                contact_email=payload.get("contact_email", ""),
                special_requests=(
                    f"\n**Special Requests:** {payload.get('special_requests')}"
                    if payload.get("special_requests") else ""
                ),
            )
            approval_messages.append(msg)

        elif action_type == "catering_order":
            pricing = payload.get("pricing", {})
            items = payload.get("items", [])
            items_list = "\n".join(f"- {item}" for item in items) if isinstance(items, list) else str(items)

            msg = CATERING_QUOTE_TEMPLATE.format(
                caterer_name=payload.get("caterer_name", "Unknown"),
                items_list=items_list,
                subtotal=pricing.get("subtotal", 0),
                tax=pricing.get("tax", 0),
                delivery_fee=pricing.get("delivery_fee", 0),
                total=pricing.get("total", 0),
                headcount=payload.get("headcount", 1),
                per_person=pricing.get("per_person", 0),
                valid_until=payload.get("valid_until", "24 hours"),
            )
            approval_messages.append(msg)

        elif action_type == "poll_send":
            poll_data = payload.get("poll_data", {})
            options = poll_data.get("options", [])
            options_list = "\n".join(
                f"{i+1}. {opt.get('text', opt)}"
                for i, opt in enumerate(options)
            )

            msg = POLL_TEMPLATE.format(
                question=poll_data.get("question", ""),
                options_list=options_list,
                deadline=poll_data.get("deadline", "24 hours"),
            )
            approval_messages.append(msg)

        elif action_type == "food_order":
            food_order = payload.get("food_order", {})
            quote = payload.get("doordash_quote", {})
            vendor_data = payload.get("vendor", {})

            # Get vendor name
            vendor_name = "Unknown"
            if isinstance(vendor_data, dict):
                vendor_name = vendor_data.get("name", "Unknown")
            elif hasattr(vendor_data, "name"):
                vendor_name = vendor_data.name

            # Format items list
            items = food_order.get("menu_items", [])
            if items:
                items_list = "\n".join(
                    f"- {item.get('name', 'Item')} x{item.get('quantity', 1)} - ${item.get('price', 0):.2f}"
                    for item in items
                )
            else:
                items_list = "- Standard order (items to be confirmed with restaurant)"

            # Calculate totals
            subtotal = food_order.get("subtotal", 0)
            tax = food_order.get("tax", 0)
            delivery_fee = quote.get("fee_cents", 0) / 100
            service_fee = food_order.get("service_fee", 0)
            total = subtotal + tax + delivery_fee + service_fee
            headcount = food_order.get("headcount", 1)
            per_person = total / headcount if headcount else total

            msg = FOOD_ORDER_TEMPLATE.format(
                restaurant_name=vendor_name,
                headcount=headcount,
                delivery_date=food_order.get("event_date", "Today"),
                delivery_time=food_order.get("event_time", "ASAP"),
                delivery_address=food_order.get("delivery_address", "TBD"),
                items_list=items_list,
                subtotal=subtotal,
                tax=tax,
                delivery_fee=delivery_fee,
                service_fee=service_fee,
                total=total,
                per_person=per_person,
                estimated_pickup=quote.get("estimated_pickup_time", "Soon"),
                estimated_delivery=quote.get("estimated_dropoff_time", "Soon"),
            )
            approval_messages.append(msg)

        elif action_type == "doordash_order":
            # Legacy DoorDash order format
            food_order = payload.get("food_order", {})
            vendor_name = food_order.get("vendor_name", payload.get("vendor_name", "Unknown"))
            delivery_fee = payload.get("delivery_fee", "$0.00")
            estimated_dropoff = payload.get("estimated_dropoff", "Soon")

            msg = f"""**DoorDash Delivery Request**

**Restaurant:** {vendor_name}
**Delivery to:** {food_order.get("delivery_address", "TBD")}

**Delivery Fee:** {delivery_fee}
**Estimated Arrival:** {estimated_dropoff}

Approve this delivery request?"""
            approval_messages.append(msg)

        else:
            approval_messages.append(
                f"**Pending Action:** {action.get('description', 'Unknown action')}\n\n"
                f"Action ID: `{action.get('action_id')}`\n\n"
                "Please approve or reject this action."
            )

    # Combine all approval requests
    combined_message = "\n\n---\n\n".join(approval_messages)

    # Add action IDs and shareable approval links
    action_ids = [a.get("action_id") for a in pending_actions]
    combined_message += f"\n\n**Action IDs:** {', '.join(action_ids)}"
    combined_message += "\n\nTo approve, call POST /approve/{action_id} with `{\"approved\": true}`"

    # Add shareable approval links for each action
    for action in pending_actions:
        action_type = action.get("action_type", "")
        if action_type in ("food_order", "catering_order", "reservation", "doordash_order"):
            approval_url = f"{APPROVAL_BASE_URL}/o/{action.get('action_id')}"
            combined_message += f"\n\nApproval link: {approval_url}"

    return {
        "messages": [AIMessage(content=combined_message)],
        "needs_approval": True,
    }
