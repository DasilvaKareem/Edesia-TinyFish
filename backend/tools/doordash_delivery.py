"""DoorDash Drive API tools for delivery services."""

import os
import time
import uuid
import base64
import hmac
import hashlib
import json
from typing import Optional
import httpx
from langchain_core.tools import tool

DOORDASH_API_BASE = "https://openapi.doordash.com/drive/v2"


def _create_jwt() -> str:
    """Create a JWT token for DoorDash API authentication."""
    developer_id = os.getenv("DOORDASH_DEVELOPER_ID")
    key_id = os.getenv("DOORDASH_KEY_ID")
    signing_secret = os.getenv("DOORDASH_SIGNING_SECRET")

    if not all([developer_id, key_id, signing_secret]):
        raise ValueError("DoorDash API credentials not configured")

    # JWT Header
    header = {
        "alg": "HS256",
        "typ": "JWT",
        "dd-ver": "DD-JWT-V1"
    }

    # JWT Payload
    now = int(time.time())
    payload = {
        "aud": "doordash",
        "iss": developer_id,
        "kid": key_id,
        "exp": now + 300,  # 5 minutes
        "iat": now
    }

    # Encode header and payload
    def b64_encode(data: dict) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(data, separators=(',', ':')).encode()
        ).rstrip(b'=').decode()

    header_b64 = b64_encode(header)
    payload_b64 = b64_encode(payload)
    message = f"{header_b64}.{payload_b64}"

    # Sign with HMAC-SHA256
    secret_bytes = base64.urlsafe_b64decode(signing_secret + '==')
    signature = hmac.new(
        secret_bytes,
        message.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()

    return f"{message}.{signature_b64}"


def _get_headers() -> dict:
    """Get DoorDash API headers with JWT auth."""
    return {
        "Authorization": f"Bearer {_create_jwt()}",
        "Content-Type": "application/json"
    }


@tool
async def create_delivery_quote(
    pickup_address: str,
    pickup_business_name: str,
    pickup_phone: str,
    dropoff_address: str,
    dropoff_business_name: str,
    dropoff_phone: str,
    order_value_cents: int,
    pickup_instructions: Optional[str] = None,
    dropoff_instructions: Optional[str] = None,
) -> dict:
    """
    Get a delivery quote from DoorDash Drive.

    Args:
        pickup_address: Full address for pickup (e.g., "123 Main St, San Francisco, CA 94102")
        pickup_business_name: Name of the pickup location
        pickup_phone: Phone number for pickup contact (e.g., "+14155551234")
        dropoff_address: Full address for delivery
        dropoff_business_name: Name/person at delivery location
        dropoff_phone: Phone number for delivery contact
        order_value_cents: Order value in cents (e.g., 2500 for $25.00)
        pickup_instructions: Optional instructions for pickup
        dropoff_instructions: Optional instructions for dropoff

    Returns:
        Delivery quote with estimated fee, time, and quote ID
    """
    external_delivery_id = f"edesia-{uuid.uuid4().hex[:12]}"

    payload = {
        "external_delivery_id": external_delivery_id,
        "pickup_address": pickup_address,
        "pickup_business_name": pickup_business_name,
        "pickup_phone_number": pickup_phone,
        "dropoff_address": dropoff_address,
        "dropoff_business_name": dropoff_business_name,
        "dropoff_phone_number": dropoff_phone,
        "order_value": order_value_cents,
    }

    if pickup_instructions:
        payload["pickup_instructions"] = pickup_instructions
    if dropoff_instructions:
        payload["dropoff_instructions"] = dropoff_instructions

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DOORDASH_API_BASE}/quotes",
            headers=_get_headers(),
            json=payload,
            timeout=30.0
        )

        if response.status_code != 200:
            return {
                "error": f"DoorDash API error: {response.status_code}",
                "details": response.text
            }

        data = response.json()

    return {
        "quote_id": data.get("id"),
        "external_delivery_id": external_delivery_id,
        "fee_cents": data.get("fee"),
        "fee_dollars": f"${data.get('fee', 0) / 100:.2f}",
        "estimated_pickup_time": data.get("pickup_time_estimated"),
        "estimated_dropoff_time": data.get("dropoff_time_estimated"),
        "currency": data.get("currency", "USD"),
        "expires_at": data.get("expires_at"),
    }


@tool
async def create_delivery(
    pickup_address: str,
    pickup_business_name: str,
    pickup_phone: str,
    dropoff_address: str,
    dropoff_business_name: str,
    dropoff_phone: str,
    order_value_cents: int,
    pickup_instructions: Optional[str] = None,
    dropoff_instructions: Optional[str] = None,
    tip_cents: Optional[int] = None,
) -> dict:
    """
    Create a DoorDash delivery request.

    Args:
        pickup_address: Full address for pickup
        pickup_business_name: Name of the pickup location
        pickup_phone: Phone number for pickup contact
        dropoff_address: Full address for delivery
        dropoff_business_name: Name/person at delivery location
        dropoff_phone: Phone number for delivery contact
        order_value_cents: Order value in cents
        pickup_instructions: Optional instructions for Dasher at pickup
        dropoff_instructions: Optional instructions for Dasher at dropoff
        tip_cents: Optional tip amount in cents

    Returns:
        Delivery details with tracking info and status
    """
    external_delivery_id = f"edesia-{uuid.uuid4().hex[:12]}"

    payload = {
        "external_delivery_id": external_delivery_id,
        "pickup_address": pickup_address,
        "pickup_business_name": pickup_business_name,
        "pickup_phone_number": pickup_phone,
        "dropoff_address": dropoff_address,
        "dropoff_business_name": dropoff_business_name,
        "dropoff_phone_number": dropoff_phone,
        "order_value": order_value_cents,
    }

    if pickup_instructions:
        payload["pickup_instructions"] = pickup_instructions
    if dropoff_instructions:
        payload["dropoff_instructions"] = dropoff_instructions
    if tip_cents:
        payload["tip"] = tip_cents

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DOORDASH_API_BASE}/deliveries",
            headers=_get_headers(),
            json=payload,
            timeout=30.0
        )

        if response.status_code not in [200, 201]:
            return {
                "error": f"DoorDash API error: {response.status_code}",
                "details": response.text
            }

        data = response.json()

    return {
        "delivery_id": data.get("id"),
        "external_delivery_id": external_delivery_id,
        "status": data.get("delivery_status"),
        "fee_cents": data.get("fee"),
        "fee_dollars": f"${data.get('fee', 0) / 100:.2f}",
        "tracking_url": data.get("tracking_url"),
        "estimated_pickup_time": data.get("pickup_time_estimated"),
        "estimated_dropoff_time": data.get("dropoff_time_estimated"),
        "support_reference": data.get("support_reference"),
    }


@tool
async def get_delivery_status(external_delivery_id: str) -> dict:
    """
    Get the status of a DoorDash delivery.

    Args:
        external_delivery_id: The delivery ID returned when creating the delivery

    Returns:
        Current delivery status and Dasher information if assigned
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DOORDASH_API_BASE}/deliveries/{external_delivery_id}",
            headers=_get_headers(),
            timeout=30.0
        )

        if response.status_code != 200:
            return {
                "error": f"DoorDash API error: {response.status_code}",
                "details": response.text
            }

        data = response.json()

    result = {
        "external_delivery_id": external_delivery_id,
        "status": data.get("delivery_status"),
        "pickup_address": data.get("pickup_address"),
        "dropoff_address": data.get("dropoff_address"),
        "tracking_url": data.get("tracking_url"),
        "estimated_pickup_time": data.get("pickup_time_estimated"),
        "estimated_dropoff_time": data.get("dropoff_time_estimated"),
        "actual_pickup_time": data.get("pickup_time_actual"),
        "actual_dropoff_time": data.get("dropoff_time_actual"),
    }

    # Add Dasher info if available
    dasher = data.get("dasher")
    if dasher:
        result["dasher"] = {
            "name": dasher.get("first_name"),
            "phone": dasher.get("phone_number"),
            "location_lat": dasher.get("location", {}).get("lat"),
            "location_lng": dasher.get("location", {}).get("lng"),
        }

    return result


@tool
async def cancel_delivery(external_delivery_id: str) -> dict:
    """
    Cancel a DoorDash delivery.

    Args:
        external_delivery_id: The delivery ID to cancel

    Returns:
        Cancellation confirmation
    """
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{DOORDASH_API_BASE}/deliveries/{external_delivery_id}/cancel",
            headers=_get_headers(),
            timeout=30.0
        )

        if response.status_code != 200:
            return {
                "error": f"DoorDash API error: {response.status_code}",
                "details": response.text
            }

        data = response.json()

    return {
        "external_delivery_id": external_delivery_id,
        "status": "cancelled",
        "cancellation_fee_cents": data.get("cancellation_fee"),
        "message": "Delivery has been cancelled"
    }


# Export all tools
doordash_tools = [
    create_delivery_quote,
    create_delivery,
    get_delivery_status,
    cancel_delivery,
]
