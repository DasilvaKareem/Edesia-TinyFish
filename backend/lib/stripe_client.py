"""Stripe payment client for Edesia."""

import os
import stripe
from typing import Optional
from lib.firebase import get_db

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


async def get_or_create_customer(user_id: str, email: str) -> str:
    """Get existing Stripe customer or create new one. Returns customer ID."""
    db = get_db()
    user_doc = db.collection("users").document(user_id).get()

    if user_doc.exists:
        data = user_doc.to_dict()
        if data.get("stripeCustomerId"):
            return data["stripeCustomerId"]

    # Create new Stripe customer
    customer = stripe.Customer.create(
        email=email,
        metadata={"firebase_uid": user_id},
    )

    # Save to Firestore
    db.collection("users").document(user_id).update({
        "stripeCustomerId": customer.id,
    })

    return customer.id


async def create_setup_intent(customer_id: str) -> dict:
    """Create SetupIntent for saving a card."""
    intent = stripe.SetupIntent.create(
        customer=customer_id,
        payment_method_types=["card"],
    )
    return {"client_secret": intent.client_secret, "id": intent.id}


async def charge_customer(
    customer_id: str,
    amount_cents: int,
    description: str,
    metadata: dict = None,
) -> dict:
    """Charge customer's default payment method. Returns payment result."""
    # Get default payment method
    methods = stripe.PaymentMethod.list(customer=customer_id, type="card", limit=1)
    if not methods.data:
        return {"success": False, "error": "no_payment_method"}

    payment_method_id = methods.data[0].id

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            customer=customer_id,
            payment_method=payment_method_id,
            off_session=True,
            confirm=True,
            description=description,
            metadata=metadata or {},
        )

        return {
            "success": intent.status == "succeeded",
            "payment_intent_id": intent.id,
            "status": intent.status,
        }
    except stripe.error.CardError as e:
        return {
            "success": False,
            "error": e.user_message or "Card declined",
            "code": e.code,
        }


async def get_payment_methods(customer_id: str) -> list:
    """List customer's saved cards."""
    methods = stripe.PaymentMethod.list(customer=customer_id, type="card")
    return [
        {
            "id": pm.id,
            "brand": pm.card.brand,
            "last4": pm.card.last4,
            "exp_month": pm.card.exp_month,
            "exp_year": pm.card.exp_year,
        }
        for pm in methods.data
    ]


async def detach_payment_method(payment_method_id: str) -> bool:
    """Remove a saved payment method."""
    stripe.PaymentMethod.detach(payment_method_id)
    return True


# ── Corporate card & company-level billing ──────────────────────────


async def get_company_payment_config(company_id: str) -> dict:
    """Get the company's payment configuration (corporate card, approval thresholds)."""
    db = get_db()
    doc = db.collection("companies").document(company_id).get()
    if not doc.exists:
        return {
            "use_corporate_card": False,
            "approval_threshold": None,
            "approver_email": None,
        }
    data = doc.to_dict()
    return {
        "use_corporate_card": data.get("useCorporateCard", False),
        "stripe_customer_id": data.get("stripeCustomerId"),
        "approval_threshold": data.get("approvalThreshold"),
        "approver_email": data.get("approverEmail"),
        "company_name": data.get("name", ""),
    }


async def create_corporate_card_setup(company_id: str, admin_email: str) -> dict:
    """Create a SetupIntent so a company admin can save a corporate card.

    Returns the client_secret for the frontend to complete card collection.
    """
    db = get_db()
    doc = db.collection("companies").document(company_id).get()
    data = doc.to_dict() if doc.exists else {}

    # Reuse or create Stripe customer for the company
    customer_id = data.get("stripeCustomerId")
    if not customer_id:
        customer = stripe.Customer.create(
            email=admin_email,
            metadata={"company_id": company_id, "type": "corporate"},
            description=f"Corporate card — {data.get('name', company_id)}",
        )
        customer_id = customer.id
        db.collection("companies").document(company_id).set(
            {"stripeCustomerId": customer_id}, merge=True,
        )

    intent = stripe.SetupIntent.create(
        customer=customer_id,
        payment_method_types=["card"],
        metadata={"company_id": company_id},
    )

    return {
        "client_secret": intent.client_secret,
        "setup_intent_id": intent.id,
        "customer_id": customer_id,
    }


async def get_company_payment_methods(company_id: str) -> list:
    """List saved corporate cards for a company."""
    db = get_db()
    doc = db.collection("companies").document(company_id).get()
    if not doc.exists:
        return []

    customer_id = doc.to_dict().get("stripeCustomerId")
    if not customer_id:
        return []

    methods = stripe.PaymentMethod.list(customer=customer_id, type="card")
    return [
        {
            "id": pm.id,
            "brand": pm.card.brand,
            "last4": pm.card.last4,
            "exp_month": pm.card.exp_month,
            "exp_year": pm.card.exp_year,
            "is_default": pm.id == _get_default_pm(customer_id),
        }
        for pm in methods.data
    ]


async def charge_corporate_card(
    company_id: str,
    amount_cents: int,
    description: str,
    order_id: str,
    metadata: dict = None,
) -> dict:
    """Charge the company's corporate card for an order.

    Falls back to the default payment method on the Stripe customer.
    """
    db = get_db()
    doc = db.collection("companies").document(company_id).get()
    if not doc.exists:
        return {"success": False, "error": "company_not_found"}

    customer_id = doc.to_dict().get("stripeCustomerId")
    if not customer_id:
        return {"success": False, "error": "no_corporate_card"}

    methods = stripe.PaymentMethod.list(customer=customer_id, type="card", limit=1)
    if not methods.data:
        return {"success": False, "error": "no_payment_method"}

    meta = {"company_id": company_id, "order_id": order_id, **(metadata or {})}

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            customer=customer_id,
            payment_method=methods.data[0].id,
            off_session=True,
            confirm=True,
            description=description,
            metadata=meta,
        )
        return {
            "success": intent.status == "succeeded",
            "payment_intent_id": intent.id,
            "status": intent.status,
        }
    except stripe.error.CardError as e:
        return {
            "success": False,
            "error": e.user_message or "Card declined",
            "code": e.code,
        }


def _get_default_pm(customer_id: str) -> Optional[str]:
    """Return the default payment method for a customer, if any."""
    cust = stripe.Customer.retrieve(customer_id)
    return cust.invoice_settings.default_payment_method if cust.invoice_settings else None
