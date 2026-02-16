"""Order submit node for DoorDash Drive submission with approval thresholds."""

import uuid
from datetime import datetime
import weave
from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from agent.state import AgentState
from models.orders import FoodOrderContext, VendorOption
from tools.doordash_delivery import create_delivery_quote


async def _check_approval_threshold(user_id: str, total: float) -> dict | None:
    """Check whether the order total exceeds the company's approval threshold.

    Returns None if no threshold or within limit.
    Returns dict with approver info if manager approval is required.
    """
    from lib.firebase import get_db

    db = get_db()
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        return None

    user_data = user_doc.to_dict()
    company_id = user_data.get("companyId")
    if not company_id:
        return None

    company_doc = db.collection("companies").document(company_id).get()
    if not company_doc.exists:
        return None

    company = company_doc.to_dict()
    threshold = company.get("approvalThreshold")
    if threshold is None or total <= threshold:
        return None

    return {
        "requires_manager_approval": True,
        "threshold": threshold,
        "total": total,
        "approver_email": company.get("approverEmail"),
        "approver_name": company.get("approverName", "your manager"),
        "company_name": company.get("name", ""),
        "use_corporate_card": company.get("useCorporateCard", False),
        "company_id": company_id,
    }


def _format_order_for_approval(food_order: FoodOrderContext, quote: dict) -> str:
    """Format order details for approval message."""
    vendor = food_order.selected_vendor
    if isinstance(vendor, dict):
        vendor = VendorOption(**vendor)

    lines = [
        f"**Restaurant:** {vendor.name if vendor else 'Unknown'}",
        f"**Headcount:** {food_order.headcount} people",
        f"**Delivery:** {food_order.event_date or 'Today'} at {food_order.event_time or 'ASAP'}",
        f"**Address:** {food_order.delivery_address}",
        "",
    ]

    # Items
    if food_order.menu_items:
        lines.append("**Items:**")
        for item in food_order.menu_items:
            lines.append(f"- {item.name} x{item.quantity} - ${item.price:.2f}")
        lines.append("")

    # Pricing
    lines.append("**Pricing:**")
    lines.append(f"Subtotal: ${food_order.subtotal or 0:.2f}")
    if food_order.tax:
        lines.append(f"Tax: ${food_order.tax:.2f}")
    lines.append(f"Delivery Fee: {quote.get('fee_dollars', '$0.00')}")
    if food_order.service_fee:
        lines.append(f"Service Fee: ${food_order.service_fee:.2f}")

    total = (food_order.subtotal or 0) + (food_order.tax or 0) + (quote.get('fee_cents', 0) / 100) + (food_order.service_fee or 0)
    lines.append(f"**Total: ${total:.2f}**")

    if food_order.headcount:
        per_person = total / food_order.headcount
        lines.append(f"(${per_person:.2f}/person)")

    lines.append("")
    lines.append(f"**Estimated Pickup:** {quote.get('estimated_pickup_time', 'Soon')}")
    lines.append(f"**Estimated Delivery:** {quote.get('estimated_dropoff_time', 'Soon')}")

    return "\n".join(lines)


@weave.op()
async def order_submit_node(state: AgentState) -> dict:
    """
    Submit order to DoorDash Drive API.

    This node:
    1. Gets a delivery quote from DoorDash
    2. Creates a pending action for approval
    3. Actual delivery is created after approval

    Streams progress updates for real-time UI feedback.
    """
    # Get stream writer for status updates
    try:
        writer = get_stream_writer()
    except Exception:
        writer = None

    def emit_status(status: str, details: dict = None):
        if writer:
            writer({"type": "status", "status": status, **(details or {})})

    emit_status("order_submit_start", {"message": "Preparing to submit order..."})

    food_order = state.get("food_order")

    if not food_order:
        return {
            "messages": [AIMessage(content="No food order in progress.")],
        }

    if isinstance(food_order, dict):
        food_order = FoodOrderContext(**food_order)

    vendor = food_order.selected_vendor
    if isinstance(vendor, dict):
        vendor = VendorOption(**vendor)

    if not vendor:
        return {
            "messages": [AIMessage(content="No restaurant selected. Let me help you find one.")],
            "food_order": food_order.model_dump(),
        }

    if not food_order.delivery_address:
        return {
            "messages": [AIMessage(content="I need a delivery address. Where should I send the food?")],
            "food_order": food_order.model_dump(),
        }

    # Get delivery quote from DoorDash
    order_value_cents = int((food_order.subtotal or 0) * 100)
    if order_value_cents < 100:
        order_value_cents = 2500  # Default to $25 if no items

    # Build contact info
    contact_phone = food_order.contact_phone or "+15551234567"
    contact_name = food_order.contact_name or "Office"

    emit_status("getting_delivery_quote", {
        "message": "Getting delivery quote from DoorDash...",
        "vendor_name": vendor.name if vendor else "Unknown",
    })

    try:
        quote = await create_delivery_quote.ainvoke({
            "pickup_address": vendor.address or "Restaurant address needed",
            "pickup_business_name": vendor.name,
            "pickup_phone": vendor.phone or "+15559876543",
            "dropoff_address": food_order.delivery_address,
            "dropoff_business_name": contact_name,
            "dropoff_phone": contact_phone,
            "order_value_cents": order_value_cents,
            "pickup_instructions": "Food order for pickup",
            "dropoff_instructions": food_order.special_instructions,
        })

        if "error" in quote:
            return {
                "messages": [AIMessage(content=f"Couldn't get a delivery quote: {quote.get('error')}. Would you like to try again?")],
                "food_order": food_order.model_dump(),
            }

    except Exception as e:
        return {
            "messages": [AIMessage(content=f"Error getting delivery quote: {str(e)}. Would you like to try again?")],
            "food_order": food_order.model_dump(),
        }

    # Store quote info in food order
    food_order.doordash_quote_id = quote.get("quote_id")
    food_order.doordash_external_id = quote.get("external_delivery_id")
    food_order.delivery_fee = (quote.get("fee_cents", 0) / 100)
    food_order.status = "pending_approval"
    food_order.current_step = "confirm_order"

    if "submit_order" not in food_order.completed_steps:
        food_order.completed_steps.append("submit_order")

    # Calculate total for threshold check
    total = (food_order.subtotal or 0) + (food_order.tax or 0) + (quote.get("fee_cents", 0) / 100) + (food_order.service_fee or 0)

    # Check approval threshold — if over limit, route to manager
    user_id = state.get("user_id", "")
    threshold_info = await _check_approval_threshold(user_id, total) if user_id else None

    action_status = "pending_approval"
    if threshold_info:
        action_status = "pending_manager_approval"
        food_order.status = "pending_manager_approval"

    # Create pending action for approval
    pending_action = {
        "action_id": str(uuid.uuid4()),
        "action_type": "food_order",
        "status": action_status,
        "description": f"Food order from {vendor.name} for {food_order.headcount} people - ${food_order.total:.2f}",
        "payload": {
            "food_order": food_order.model_dump(),
            "doordash_quote": quote,
            "vendor": vendor.model_dump() if hasattr(vendor, 'model_dump') else vendor,
        },
    }

    if threshold_info:
        pending_action["payload"]["threshold_info"] = threshold_info

    # Format approval message
    approval_msg = _format_order_for_approval(food_order, quote)

    if threshold_info:
        approver = threshold_info.get("approver_name", "your manager")
        threshold = threshold_info["threshold"]
        approval_msg += (
            f"\n\n**This order (${total:.2f}) exceeds the ${threshold:.2f} approval threshold.**\n"
            f"I've sent an approval request to {approver}. "
            f"Once approved, the order will be placed automatically."
        )
        # Notify the approver
        emit_status("manager_approval_required", {
            "message": f"Order requires manager approval (${total:.2f} > ${threshold:.2f})",
            "approver_email": threshold_info.get("approver_email"),
        })
        _send_approval_request(pending_action, threshold_info)
    else:
        approval_msg += "\n\n**Reply 'approve' to confirm this order, or let me know if you'd like to make changes.**"

    emit_status("order_ready_for_approval", {
        "message": "Order ready for approval",
        "total": food_order.total,
        "vendor_name": vendor.name if vendor else "Unknown",
        "delivery_fee": quote.get("fee_dollars"),
    })

    return {
        "messages": [AIMessage(content=approval_msg)],
        "food_order": food_order.model_dump(),
        "pending_actions": [pending_action],
        "needs_approval": True,
    }


@weave.op()
async def execute_food_order(action_payload: dict) -> dict:
    """
    Execute approved food order by creating DoorDash delivery.

    This is called after user approves the pending action.
    """
    from tools.doordash_delivery import create_delivery

    food_order_data = action_payload.get("food_order", {})
    quote = action_payload.get("doordash_quote", {})
    vendor_data = action_payload.get("vendor", {})

    food_order = FoodOrderContext(**food_order_data) if isinstance(food_order_data, dict) else food_order_data
    vendor = VendorOption(**vendor_data) if isinstance(vendor_data, dict) else vendor_data

    # Create the actual delivery
    order_value_cents = int((food_order.subtotal or 0) * 100)
    if order_value_cents < 100:
        order_value_cents = 2500

    contact_phone = food_order.contact_phone or "+15551234567"
    contact_name = food_order.contact_name or "Office"

    try:
        delivery = await create_delivery.ainvoke({
            "pickup_address": vendor.address if hasattr(vendor, 'address') else vendor.get('address', ''),
            "pickup_business_name": vendor.name if hasattr(vendor, 'name') else vendor.get('name', ''),
            "pickup_phone": vendor.phone if hasattr(vendor, 'phone') else vendor.get('phone', '+15559876543'),
            "dropoff_address": food_order.delivery_address,
            "dropoff_business_name": contact_name,
            "dropoff_phone": contact_phone,
            "order_value_cents": order_value_cents,
            "pickup_instructions": "Food order for pickup",
            "dropoff_instructions": food_order.special_instructions,
        })

        if "error" in delivery:
            return {
                "success": False,
                "error": delivery.get("error"),
                "details": delivery.get("details"),
            }

        return {
            "success": True,
            "delivery_id": delivery.get("delivery_id"),
            "external_delivery_id": delivery.get("external_delivery_id"),
            "tracking_url": delivery.get("tracking_url"),
            "status": delivery.get("status"),
            "estimated_pickup": delivery.get("estimated_pickup_time"),
            "estimated_delivery": delivery.get("estimated_dropoff_time"),
            "message": f"Order placed! Track your delivery: {delivery.get('tracking_url')}",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def _send_approval_request(pending_action: dict, threshold_info: dict):
    """Fire-and-forget: store the approval request for the manager to act on."""
    from lib.firebase import get_db
    from firebase_admin import firestore

    db = get_db()
    action_id = pending_action["action_id"]
    approver_email = threshold_info.get("approver_email")
    company_id = threshold_info.get("company_id", "")

    db.collection("approval_requests").document(action_id).set({
        "actionId": action_id,
        "companyId": company_id,
        "approverEmail": approver_email,
        "status": "pending",
        "total": threshold_info["total"],
        "threshold": threshold_info["threshold"],
        "description": pending_action["description"],
        "payload": pending_action["payload"],
        "createdAt": firestore.SERVER_TIMESTAMP,
    })
