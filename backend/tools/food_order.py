"""Tool for LLM to update food order details (populates sidebar)."""

from typing import Optional
from langchain_core.tools import tool


@tool
def update_food_order(
    vendor_name: str,
    headcount: int,
    event_date: Optional[str] = None,
    event_time: Optional[str] = None,
    delivery_address: Optional[str] = None,
    vendor_address: Optional[str] = None,
    vendor_phone: Optional[str] = None,
    items: Optional[list[dict]] = None,
    subtotal: Optional[float] = None,
    tax: Optional[float] = None,
    delivery_fee: Optional[float] = None,
    service_fee: Optional[float] = None,
    total: Optional[float] = None,
    special_instructions: Optional[str] = None,
) -> dict:
    """Update the food order details for the sidebar tracker. ALWAYS call this when you have order info.

    Call this tool whenever you:
    - Know the restaurant/vendor name
    - Know the headcount, date, or delivery time
    - Have built a suggested order with items and prices
    - Have updated the order after user changes

    Args:
        vendor_name: Restaurant or vendor name.
        headcount: Number of people being fed.
        event_date: Date of the order (e.g. "2025-02-05" or "Tomorrow").
        event_time: Delivery/pickup time (e.g. "12:00 PM").
        delivery_address: Where to deliver the food.
        vendor_address: Restaurant address.
        vendor_phone: Restaurant phone number.
        items: List of order items, each with: name, quantity, price. Example: [{"name": "Burger", "quantity": 2, "price": 10.99}]
        subtotal: Order subtotal before tax/fees.
        tax: Tax amount.
        delivery_fee: Delivery fee.
        service_fee: Service fee.
        total: Total order cost.
        special_instructions: Any special instructions for the order.

    Returns:
        Confirmation of the updated order details.
    """
    # Build the order context dict — this gets picked up by executor_node
    order_data = {
        "__food_order_update__": True,  # Marker for executor to detect
        "selected_vendor": {
            "name": vendor_name,
            "phone": vendor_phone or "",
            "address": vendor_address or "",
        },
        "headcount": headcount,
        "event_date": event_date,
        "event_time": event_time,
        "delivery_address": delivery_address,
        "menu_items": [],
        "subtotal": subtotal,
        "tax": tax,
        "delivery_fee": delivery_fee,
        "service_fee": service_fee,
        "total": total,
        "special_instructions": special_instructions,
    }

    # Convert items to OrderItem-compatible dicts
    if items:
        for item in items:
            order_data["menu_items"].append({
                "name": item.get("name", ""),
                "quantity": item.get("quantity", 1),
                "price": item.get("price", 0),
                "notes": item.get("notes", ""),
            })

    return order_data


food_order_tools = [update_food_order]
