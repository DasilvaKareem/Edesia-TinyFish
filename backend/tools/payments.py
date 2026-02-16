"""Payment LangGraph tools for cost splitting and corporate cards."""

from typing import Optional
from langchain_core.tools import tool


@tool
def create_payment_split(
    order_id: str,
    total_amount: float,
    attendee_emails: list[str],
    equal_split: bool = True,
) -> dict:
    """
    Create Stripe payment links to split an order cost among attendees.

    Each attendee receives a unique payment link for their share.
    Once all have paid, the order can be submitted.

    Args:
        order_id: The order ID to split
        total_amount: Total amount to split
        attendee_emails: List of attendee email addresses
        equal_split: Whether to split equally (default True)

    Returns:
        Payment links per attendee and per-person amount
    """
    import stripe
    import os

    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

    if not attendee_emails:
        return {"error": "No attendees to split with."}

    per_person = round(total_amount / len(attendee_emails), 2)
    per_person_cents = int(per_person * 100)

    links = []

    for email in attendee_emails:
        try:
            # Create a Stripe Price for this split
            price = stripe.Price.create(
                unit_amount=per_person_cents,
                currency="usd",
                product_data={
                    "name": f"Lunch order share (Order {order_id[:8]})",
                },
            )

            # Create Payment Link
            link = stripe.PaymentLink.create(
                line_items=[{"price": price.id, "quantity": 1}],
                metadata={
                    "order_id": order_id,
                    "attendee_email": email,
                    "split_type": "equal",
                },
                after_completion={
                    "type": "redirect",
                    "redirect": {
                        "url": f"{os.environ.get('FRONTEND_URL', 'https://edesia-agent.vercel.app')}/payment-success?order={order_id}",
                    },
                },
            )

            links.append({
                "email": email,
                "amount": per_person,
                "payment_url": link.url,
                "link_id": link.id,
            })

        except Exception as e:
            links.append({
                "email": email,
                "amount": per_person,
                "error": str(e),
            })

    # Store split info in Firestore
    from lib.firebase import get_db
    from firebase_admin import firestore

    db = get_db()
    db.collection("payment_splits").document(order_id).set({
        "orderId": order_id,
        "totalAmount": total_amount,
        "perPerson": per_person,
        "attendees": links,
        "paidCount": 0,
        "totalAttendees": len(attendee_emails),
        "status": "pending",
        "createdAt": firestore.SERVER_TIMESTAMP,
    })

    return {
        "order_id": order_id,
        "total": total_amount,
        "per_person": per_person,
        "attendee_count": len(attendee_emails),
        "payment_links": links,
        "message": f"Split ${total_amount:.2f} among {len(attendee_emails)} people (${per_person:.2f} each). Send the payment links to each attendee.",
    }


@tool
def check_split_payment_status(order_id: str) -> dict:
    """
    Check how many attendees have paid their share of a split order.

    Args:
        order_id: The order ID to check

    Returns:
        Payment status for each attendee and overall progress
    """
    from lib.firebase import get_db

    db = get_db()
    doc = db.collection("payment_splits").document(order_id).get()

    if not doc.exists:
        return {"error": f"No payment split found for order {order_id}."}

    data = doc.to_dict()

    paid = data.get("paidCount", 0)
    total = data.get("totalAttendees", 0)
    status = data.get("status", "pending")

    return {
        "order_id": order_id,
        "status": status,
        "paid": paid,
        "total": total,
        "remaining": total - paid,
        "per_person": data.get("perPerson", 0),
        "total_amount": data.get("totalAmount", 0),
        "all_paid": paid >= total,
        "message": f"{paid}/{total} attendees have paid." + (
            " All paid — order can be submitted!" if paid >= total else ""
        ),
    }


payment_tools = [create_payment_split, check_split_payment_status]
