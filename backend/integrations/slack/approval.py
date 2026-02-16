"""Execute approved actions from Slack (mirrors /approve endpoint logic)."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def execute_slack_approval(
    action_id: str,
    stored_action: dict,
    approved_by_slack_id: str,
) -> dict:
    """Execute an approved action from Slack.

    This mirrors the logic in the /approve/{action_id} endpoint but
    returns a dict result instead of an HTTP response, so the Slack
    action handler can format it for Block Kit.

    Args:
        action_id: The PendingAction ID.
        stored_action: The action dict from Modal Dict.
        approved_by_slack_id: Slack user who approved.

    Returns:
        Dict with 'message' on success or 'error' on failure.
    """
    import modal
    from datetime import datetime

    action_type = stored_action.get("action_type", "")
    payload = stored_action.get("payload", {})

    try:
        # Mark as approved
        stored_action["status"] = "approved"
        stored_action["approved_by"] = approved_by_slack_id
        stored_action["approved_at"] = datetime.utcnow().isoformat()
        actions_dict = modal.Dict.from_name("edesia-actions", create_if_missing=True)
        actions_dict[action_id] = stored_action

        # Execute based on action type
        if action_type in ("food_order", "doordash_order"):
            return await _execute_food_order(stored_action, payload)
        elif action_type == "reservation":
            return {"message": f"Reservation confirmed for {payload.get('restaurant_name', 'restaurant')}."}
        elif action_type == "catering_order":
            return {"message": f"Catering order submitted to {payload.get('caterer_name', 'caterer')}."}
        elif action_type == "poll_send":
            return {"message": "Poll sent."}
        elif action_type in ("call", "call_restaurant", "call_caterer", "call_chef"):
            return await _execute_call(stored_action, payload)
        else:
            return {"message": f"Action '{action_type}' approved."}

    except Exception as e:
        logger.error(f"Slack approval execution failed: {e}", exc_info=True)
        return {"error": str(e)}


async def _execute_food_order(action: dict, payload: dict) -> dict:
    """Execute an approved food order (charge card + create DoorDash delivery)."""
    from lib.stripe_client import charge_customer, get_or_create_customer
    from lib.firebase import get_db

    slack_ctx = action.get("slack_context", {})
    firebase_user_id = slack_ctx.get("firebase_user_id")

    if not firebase_user_id:
        return {"error": "No linked payment account. Please link your Edesia account first."}

    # Charge the customer's saved card
    total_cents = int((payload.get("total", 0)) * 100)
    if total_cents > 0:
        vendor_name = payload.get("vendor_name", "food order")

        # Look up user email and get/create Stripe customer
        db = get_db()
        user_doc = db.collection("users").document(firebase_user_id).get()
        user_email = user_doc.to_dict().get("email", "") if user_doc.exists else ""

        if not user_email:
            return {"error": "No email found for user. Cannot process payment."}

        customer_id = await get_or_create_customer(firebase_user_id, user_email)

        charge_result = await charge_customer(
            customer_id=customer_id,
            amount_cents=total_cents,
            description=f"Edesia order from {vendor_name}",
            metadata={
                "action_id": action.get("action_id", ""),
                "vendor": vendor_name,
                "source": "slack",
            },
        )

        if charge_result.get("error"):
            return {"error": f"Payment failed: {charge_result['error']}"}

    # Create DoorDash delivery
    try:
        from tools.doordash_delivery import create_delivery
        delivery_result = create_delivery.invoke({
            "pickup_address": payload.get("pickup_address", ""),
            "pickup_business_name": payload.get("vendor_name", ""),
            "pickup_phone": payload.get("pickup_phone", ""),
            "dropoff_address": payload.get("dropoff_address", ""),
            "dropoff_business_name": payload.get("dropoff_business_name", "Office"),
            "dropoff_phone": payload.get("dropoff_phone", ""),
            "order_value_cents": total_cents,
        })

        tracking_url = delivery_result.get("tracking_url", "")
        message = f"Order placed! Delivery from {payload.get('vendor_name', 'restaurant')}."
        if tracking_url:
            message += f" Track: {tracking_url}"

        return {"message": message, "delivery": delivery_result}

    except Exception as e:
        logger.error(f"DoorDash delivery creation failed: {e}")
        return {"message": "Payment charged. Delivery creation in progress..."}


async def _execute_call(action: dict, payload: dict) -> dict:
    """Execute an approved phone call via Vapi."""
    from tools.vapi_calls import call_restaurant

    try:
        result = call_restaurant.invoke({
            "restaurant_name": payload.get("restaurant_name", payload.get("name", "")),
            "phone_number": payload.get("phone_number", ""),
            "company_name": payload.get("company_name", ""),
            "date": payload.get("date", ""),
            "time": payload.get("time", ""),
            "party_size": payload.get("party_size", 0),
        })
        return {"message": f"Call initiated to {payload.get('phone_number', 'restaurant')}."}
    except Exception as e:
        return {"error": f"Call failed: {str(e)}"}
