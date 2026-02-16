"""Order builder node for menu selection and item configuration."""

import weave
from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langgraph.config import get_stream_writer

from agent.state import AgentState
from models.orders import FoodOrderContext, OrderItem, VendorOption
from tools.catering import get_catering_menu
from tools.yelp_search import get_business_details


ORDER_BUILDER_PROMPT = """You are helping build a food order for a group.

**Selected Restaurant:** {vendor_name}
**Headcount:** {headcount} people
**Budget:** ${budget_per_person:.2f}/person (${budget_total:.2f} total)
**Dietary Restrictions:** {dietary}

**Available Menu:**
{menu}

Based on this information, suggest a recommended order that:
1. Fits within the budget
2. Provides enough food for {headcount} people
3. Accommodates any dietary restrictions
4. Offers variety

Format your response with clear item recommendations and estimated pricing.
Ask if the user wants to customize anything."""


def _format_menu_for_display(menu: dict) -> str:
    """Format menu data for LLM consumption."""
    lines = []

    # Packages
    packages = menu.get("packages", [])
    if packages:
        lines.append("**Packages:**")
        for pkg in packages:
            price = pkg.get("price_per_person", pkg.get("price", 0))
            lines.append(f"- {pkg['name']}: ${price}/person")
            items = pkg.get("items", [])
            if items:
                lines.append(f"  Includes: {', '.join(items[:5])}")
        lines.append("")

    # Individual items
    individual = menu.get("individual_items", [])
    if individual:
        lines.append("**Individual Items:**")
        for item in individual[:10]:
            price = item.get("price", 0)
            lines.append(f"- {item['name']}: ${price}")
        lines.append("")

    if not lines:
        lines.append("Menu details not available. Would you like me to call the restaurant?")

    return "\n".join(lines)


@weave.op()
async def order_builder_node(state: AgentState) -> dict:
    """
    Build order by fetching menu and configuring items.

    This node:
    1. Fetches the menu for the selected vendor
    2. Uses LLM to suggest an appropriate order
    3. Allows customization

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

    food_order = state.get("food_order")

    if not food_order:
        return {
            "messages": [AIMessage(content="No food order in progress. Would you like to start a new order?")],
        }

    if isinstance(food_order, dict):
        food_order = FoodOrderContext(**food_order)

    # Check if vendor is selected
    if not food_order.selected_vendor:
        # Check if we have vendor options to choose from
        if food_order.vendor_options:
            return {
                "messages": [AIMessage(content="Please select a restaurant first. Which number from the list would you like?")],
                "food_order": food_order.model_dump(),
            }
        else:
            return {
                "messages": [AIMessage(content="Let's find some restaurants first. What type of food are you looking for?")],
                "food_order": food_order.model_dump(),
            }

    vendor = food_order.selected_vendor
    if isinstance(vendor, dict):
        vendor = VendorOption(**vendor)

    emit_status("order_builder_start", {
        "message": f"Building order from {vendor.name}...",
        "vendor_name": vendor.name,
    })

    # Try to get menu
    menu = {}
    menu_display = ""

    emit_status("fetching_menu", {"message": "Fetching menu..."})

    # Try catering menu first (for mock data)
    try:
        menu_result = await get_catering_menu.ainvoke({"caterer_id": vendor.vendor_id})
        if "error" not in menu_result:
            menu = menu_result
            menu_display = _format_menu_for_display(menu)
    except Exception:
        pass

    # If no menu, try getting business details for more info
    if not menu_display:
        try:
            if vendor.source == "yelp":
                details = await get_business_details.ainvoke({"business_id": vendor.vendor_id})
                if "error" not in details:
                    menu_display = f"Categories: {', '.join(details.get('categories', []))}\n"
                    if details.get("transactions"):
                        menu_display += f"Supports: {', '.join(details.get('transactions', []))}\n"
        except Exception:
            pass

    if not menu_display:
        menu_display = "Menu not available online. I can help you place a custom order."

    # Calculate budget info
    headcount = food_order.headcount or 10
    budget_total = food_order.budget_total or 500
    budget_pp = food_order.budget_per_person or (budget_total / headcount)

    emit_status("suggesting_order", {
        "message": "Analyzing menu and suggesting order...",
        "headcount": headcount,
        "budget_per_person": budget_pp,
    })

    # Use LLM to suggest order
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.3,
        max_tokens=800,
    )

    dietary = ", ".join(food_order.dietary_restrictions) if food_order.dietary_restrictions else "None specified"

    response = await llm.ainvoke([
        SystemMessage(content=ORDER_BUILDER_PROMPT.format(
            vendor_name=vendor.name,
            headcount=headcount,
            budget_per_person=budget_pp,
            budget_total=budget_total,
            dietary=dietary,
            menu=menu_display,
        )),
        HumanMessage(content="Suggest a recommended order for this group."),
    ])

    # Update food order state
    food_order.current_step = "build_order"
    if "select_vendor" not in food_order.completed_steps:
        food_order.completed_steps.append("select_vendor")

    emit_status("order_builder_complete", {
        "message": "Order suggestions ready",
        "vendor_name": vendor.name,
    })

    return {
        "messages": [AIMessage(content=response.content)],
        "food_order": food_order.model_dump(),
    }


@weave.op()
def process_order_selection(state: AgentState, selection: dict) -> dict:
    """
    Process user's menu selection and update the order.

    Args:
        state: Current agent state
        selection: Dict with 'items' list and optional 'package'
    """
    food_order = state.get("food_order")

    if isinstance(food_order, dict):
        food_order = FoodOrderContext(**food_order)

    # Add items to order
    items = selection.get("items", [])
    for item in items:
        order_item = OrderItem(
            name=item.get("name", "Unknown Item"),
            quantity=item.get("quantity", 1),
            price=item.get("price", 0),
            notes=item.get("notes"),
        )
        food_order.menu_items.append(order_item)

    # Calculate totals
    headcount = food_order.headcount or 1
    subtotal = sum(item.price * item.quantity for item in food_order.menu_items)

    # Estimate tax and fees
    food_order.subtotal = subtotal
    food_order.tax = round(subtotal * 0.08, 2)
    food_order.delivery_fee = 5.99 if subtotal < 50 else 0
    food_order.service_fee = round(subtotal * 0.15, 2)  # DoorDash service fee
    food_order.total = round(
        food_order.subtotal + food_order.tax + food_order.delivery_fee + food_order.service_fee,
        2
    )

    # Move to review step
    food_order.current_step = "review_order"
    if "build_order" not in food_order.completed_steps:
        food_order.completed_steps.append("build_order")

    return {
        "food_order": food_order.model_dump(),
    }
