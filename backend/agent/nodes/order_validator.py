"""Order validator node for budget and dietary validation."""

import weave
from langchain_core.messages import AIMessage

from agent.state import AgentState
from models.orders import FoodOrderContext, VendorOption


def _check_budget(food_order: FoodOrderContext) -> tuple[list[str], list[str]]:
    """Check if order is within budget."""
    errors = []
    warnings = []

    total = food_order.total or 0
    budget_total = food_order.budget_total

    if budget_total:
        if total > budget_total:
            overage = total - budget_total
            errors.append(f"Order exceeds budget by ${overage:.2f} (${total:.2f} vs ${budget_total:.2f} budget)")
        elif total > budget_total * 0.9:
            pct = (total / budget_total) * 100
            warnings.append(f"Order is at {pct:.0f}% of budget (${total:.2f} of ${budget_total:.2f})")

    # Check per-person budget
    headcount = food_order.headcount or 1
    per_person = total / headcount if total else 0
    budget_pp = food_order.budget_per_person

    if budget_pp and per_person > budget_pp:
        overage = per_person - budget_pp
        errors.append(f"Per-person cost ${per_person:.2f} exceeds budget of ${budget_pp:.2f}/person")

    return errors, warnings


def _check_required_fields(food_order: FoodOrderContext) -> list[str]:
    """Check that all required fields are present."""
    errors = []

    if not food_order.headcount or food_order.headcount < 1:
        errors.append("Headcount must be specified (how many people?)")

    if not food_order.delivery_address:
        errors.append("Delivery address must be specified")

    if not food_order.event_date:
        errors.append("Delivery date must be specified")

    if not food_order.selected_vendor:
        errors.append("No restaurant selected")

    return errors


def _check_dietary(food_order: FoodOrderContext) -> list[str]:
    """Check dietary restrictions against menu items."""
    warnings = []

    # This is a simplified check - in production you'd have item-level dietary info
    restrictions = food_order.dietary_restrictions or []

    if restrictions and food_order.menu_items:
        # Just warn that we can't verify dietary compliance
        restrictions_str = ", ".join(restrictions)
        warnings.append(
            f"Dietary restrictions noted: {restrictions_str}. "
            "Please verify with the restaurant that your order accommodates these needs."
        )

    return warnings


def _format_validation_message(errors: list[str], warnings: list[str]) -> str:
    """Format validation results for display."""
    lines = []

    if errors:
        lines.append("**Issues to fix before ordering:**")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    if warnings:
        lines.append("**Warnings:**")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    if errors:
        lines.append("Please address the issues above before continuing.")
    elif warnings:
        lines.append("You can proceed, but please review the warnings above.")

    return "\n".join(lines)


def _format_order_summary(food_order: FoodOrderContext) -> str:
    """Format order summary for review."""
    vendor = food_order.selected_vendor
    if isinstance(vendor, dict):
        vendor = VendorOption(**vendor)

    lines = [
        "**Order Summary:**",
        f"Restaurant: {vendor.name if vendor else 'Not selected'}",
        f"Headcount: {food_order.headcount or 'Not specified'} people",
        f"Delivery: {food_order.event_date or 'TBD'} at {food_order.event_time or 'TBD'}",
        f"Address: {food_order.delivery_address or 'Not specified'}",
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
    if food_order.delivery_fee:
        lines.append(f"Delivery Fee: ${food_order.delivery_fee:.2f}")
    if food_order.service_fee:
        lines.append(f"Service Fee: ${food_order.service_fee:.2f}")
    lines.append(f"**Total: ${food_order.total or 0:.2f}**")

    if food_order.headcount:
        per_person = (food_order.total or 0) / food_order.headcount
        lines.append(f"(${per_person:.2f}/person)")

    return "\n".join(lines)


@weave.op()
def order_validator_node(state: AgentState) -> dict:
    """
    Validate order against budget and dietary constraints.

    This is the evaluator in the evaluator-optimizer pattern.
    If validation fails, we route back to order_builder.
    If validation passes, we proceed to approval.
    """
    food_order = state.get("food_order")

    if not food_order:
        return {
            "messages": [AIMessage(content="No food order in progress.")],
        }

    if isinstance(food_order, dict):
        food_order = FoodOrderContext(**food_order)

    # Run all validation checks
    all_errors = []
    all_warnings = []

    # Check required fields
    required_errors = _check_required_fields(food_order)
    all_errors.extend(required_errors)

    # Check budget (only if we have pricing)
    if food_order.total:
        budget_errors, budget_warnings = _check_budget(food_order)
        all_errors.extend(budget_errors)
        all_warnings.extend(budget_warnings)

    # Check dietary
    dietary_warnings = _check_dietary(food_order)
    all_warnings.extend(dietary_warnings)

    # Update food order with validation results
    food_order.validation_errors = all_errors
    food_order.validation_warnings = all_warnings

    if all_errors:
        # Validation failed - go back to build_order
        food_order.current_step = "build_order"

        validation_msg = _format_validation_message(all_errors, all_warnings)

        return {
            "messages": [AIMessage(content=validation_msg)],
            "food_order": food_order.model_dump(),
        }

    # Validation passed - proceed to confirm
    food_order.current_step = "confirm_order"
    if "review_order" not in food_order.completed_steps:
        food_order.completed_steps.append("review_order")

    # Generate summary and ask for confirmation
    summary = _format_order_summary(food_order)

    if all_warnings:
        warning_msg = _format_validation_message([], all_warnings)
        summary = f"{summary}\n\n{warning_msg}"

    summary += "\n\nDoes this look correct? Say 'confirm' to place the order, or let me know what you'd like to change."

    return {
        "messages": [AIMessage(content=summary)],
        "food_order": food_order.model_dump(),
    }
